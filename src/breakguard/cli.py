from __future__ import annotations

import argparse
import sys
from pathlib import Path

from breakguard import ast_analyzer, changelog, config, dependency_detector, diff_analyzer, go_analyzer, reporter, scanner, ts_analyzer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect likely downstream breakage before release.")
    parser.add_argument("--repo", default=".", help="Path to the repository to scan.")
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff.")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown", "github", "sarif"),
        default="text",
        help="Output format."
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "low", "medium", "high"),
        default="high",
        help="Fail (exit code 1) if overall risk level is >= this severity.",
    )
    parser.add_argument(
        "--draft-release",
        action="store_true",
        help="Automatically draft a GitHub release using the 'gh' CLI if there are findings.",
    )
    parser.add_argument(
        "--changelog",
        action="store_true",
        help="Generate a markdown API changelog (breakage-radar-changelog.md).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    
    # Load in-manifest configuration
    cfg = config.parse_config(repo_path)
    
    # 1. Parse .breakageignore and config ignored_paths
    ignore_file = repo_path / ".breakageignore"
    ignore_patterns = list(cfg.get("ignored_paths", []))
    if ignore_file.exists():
        with open(ignore_file, "r") as f:
            ignore_patterns.extend([line.strip() for line in f if line.strip() and not line.startswith("#")])
            
    import fnmatch
    def _is_ignored(path_str: str) -> bool:
        for p in ignore_patterns:
            if fnmatch.fnmatch(path_str, p) or path_str.startswith(p.rstrip("/") + "/"):
                return True
        return False

    # Run the core detection
    changed_files = [f for f in scanner.git_changed_files(repo_path, args.base) if not _is_ignored(f)]
    deleted_files = [f for f in scanner.git_deleted_files(repo_path, args.base) if not _is_ignored(f)]
    
    # Filter public directories if configured
    public_dirs = cfg.get("public_dirs")
    if public_dirs:
        changed_files = [f for f in changed_files if any(f.startswith(pd.rstrip("/") + "/") for pd in public_dirs)]
        deleted_files = [f for f in deleted_files if any(f.startswith(pd.rstrip("/") + "/") for pd in public_dirs)]
        
    diff_text = scanner.git_diff(repo_path, args.base)

    findings = scanner.detect_risk(changed_files)
    findings.extend(diff_analyzer.analyze_diff(diff_text, deleted_files))
    findings.extend(ast_analyzer.analyze_python_ast(repo_path, changed_files, args.base))
    findings.extend(go_analyzer.analyze_go(repo_path, changed_files, args.base))
    findings.extend(ts_analyzer.analyze_js_ts(repo_path, changed_files, args.base))
    findings.extend(dependency_detector.analyze_dependencies(repo_path, ignore_patterns))

    # Apply severity overrides from configuration
    overrides = cfg.get("severity_overrides", {})
    if overrides:
        new_findings = []
        for f in findings:
            matched_sev = None
            for pattern, new_sev in overrides.items():
                if pattern.lower() in f.message.lower():
                    matched_sev = new_sev
                    break
            if matched_sev:
                new_findings.append(scanner.Finding(
                    severity=matched_sev,
                    path=f.path,
                    message=f.message,
                    migration_note=f.migration_note,
                    line=f.line
                ))
            else:
                new_findings.append(f)
        findings = new_findings

    report = scanner.summarize(findings, changed_files, repo_path)

    # Generate Changelog if requested
    if args.changelog:
        try:
            log_content = changelog.generate_changelog(repo_path, changed_files, args.base)
            (repo_path / "breakage-radar-changelog.md").write_text(log_content, encoding="utf-8")
            print(f"\nGenerated API changelog: breakage-radar-changelog.md", file=sys.stderr)
        except Exception as e:
            print(f"\nWarning: Failed to generate changelog: {e}", file=sys.stderr)

    # Save SVG badge
    try:
        badge_content = reporter.generate_badge(str(report["risk_level"]))
        (repo_path / "breakage-radar-badge.svg").write_text(badge_content, encoding="utf-8")
    except Exception as e:
        print(f"Warning: Failed to generate SVG badge: {e}", file=sys.stderr)

    # Output
    if args.format == "json":
        print(reporter.format_json(report))
    elif args.format == "markdown":
        print(reporter.format_markdown(report))
    elif args.format == "github":
        print(reporter.format_github(report))
    elif args.format == "sarif":
        print(reporter.format_sarif(report))
    else:
        print(reporter.format_text(report))

    # Exit code based on fail-on
    if args.fail_on != "none":
        risk = report["risk_level"]
        order = scanner.SEVERITY_ORDER
        if order.get(risk, 0) >= order.get(args.fail_on, 0):
            print(f"\nError: Overall risk level '{risk}' exceeds threshold '{args.fail_on}'.", file=sys.stderr)
            return 1

    # Draft Release Notes
    if args.draft_release and report["findings"]:
        import uuid
        import subprocess
        notes = reporter.format_markdown(report)
        notes_file = repo_path / "draft-release-notes.md"
        notes_file.write_text(notes, encoding="utf-8")
        try:
            tag = f"draft-{uuid.uuid4().hex[:8]}"
            subprocess.run(
                ["gh", "release", "create", tag, "--draft", "--title", "Upcoming Release (Breakage Report)", "--notes-file", str(notes_file)],
                cwd=repo_path,
                check=True,
                capture_output=True
            )
            print(f"\nDrafted a new GitHub Release: {tag}", file=sys.stderr)
        except Exception as e:
            print(f"\nWarning: Failed to draft release. Is 'gh' CLI installed and authenticated? ({e})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
