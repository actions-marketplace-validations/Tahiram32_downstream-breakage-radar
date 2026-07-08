from __future__ import annotations

import argparse
import sys
from pathlib import Path

from downstream_breakage_radar import ast_analyzer, diff_analyzer, reporter, scanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect likely downstream breakage before release.")
    parser.add_argument("--repo", default=".", help="Path to the repository to scan.")
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff.")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown", "github"),
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    
    # 1. Parse .breakageignore
    ignore_file = repo_path / ".breakageignore"
    ignore_patterns = []
    if ignore_file.exists():
        with open(ignore_file, "r") as f:
            ignore_patterns = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            
    import fnmatch
    def _is_ignored(path_str: str) -> bool:
        for p in ignore_patterns:
            if fnmatch.fnmatch(path_str, p) or path_str.startswith(p.rstrip("/") + "/"):
                return True
        return False

    # Run the core detection
    changed_files = [f for f in scanner.git_changed_files(repo_path, args.base) if not _is_ignored(f)]
    deleted_files = [f for f in scanner.git_deleted_files(repo_path, args.base) if not _is_ignored(f)]
    diff_text = scanner.git_diff(repo_path, args.base)

    findings = scanner.detect_risk(changed_files)
    findings.extend(diff_analyzer.analyze_diff(diff_text, deleted_files))
    findings.extend(ast_analyzer.analyze_python_ast(repo_path, changed_files, args.base))

    report = scanner.summarize(findings, changed_files)

    # Output
    if args.format == "json":
        print(reporter.format_json(report))
    elif args.format == "markdown":
        print(reporter.format_markdown(report))
    elif args.format == "github":
        print(reporter.format_github(report))
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
