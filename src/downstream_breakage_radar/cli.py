from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


RISKY_PATH_MARKERS = (
    "src/",
    "lib/",
    "app/",
    "api/",
    "public/",
    "include/",
    "internal/",
    "pkg/",
    "schemas/",
    "proto/",
    "openapi",
)

RISKY_FILENAMES = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "gradle.properties",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    path: str
    message: str
    migration_note: str


def git_changed_files(repo_path: Path, base_ref: str) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def detect_risk(changed_files: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in changed_files:
        lowered = path.lower()
        filename = Path(path).name
        if filename in RISKY_FILENAMES or any(marker in lowered for marker in RISKY_PATH_MARKERS):
            findings.append(
                Finding(
                    severity="medium",
                    path=path,
                    message="Change touches a likely public surface or release-critical file.",
                    migration_note="Review for API compatibility, config drift, and release notes before merging.",
                )
            )
        if lowered.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".cs")):
            findings.append(
                Finding(
                    severity="low",
                    path=path,
                    message="Source code change may affect downstream consumers.",
                    migration_note="Check for renamed symbols, changed defaults, and behavior shifts.",
                )
            )
    return findings


def summarize(findings: list[Finding], changed_files: list[str]) -> dict[str, object]:
    highest = "none"
    if any(f.severity == "medium" for f in findings):
        highest = "medium"
    elif findings:
        highest = "low"

    return {
        "changed_files": changed_files,
        "change_count": len(changed_files),
        "risk_level": highest,
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }


def format_text(report: dict[str, object]) -> str:
    lines = [
        f"Risk level: {report['risk_level']}",
        f"Changed files: {report['change_count']}",
        f"Findings: {report['finding_count']}",
    ]
    for finding in report["findings"]:
        lines.append("")
        lines.append(f"- [{finding['severity']}] {finding['path']}: {finding['message']}")
        lines.append(f"  Migration note: {finding['migration_note']}")
    if not report["findings"]:
        lines.append("")
        lines.append("No obvious breakage risks found.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect likely downstream breakage before release.")
    parser.add_argument("--repo", default=".", help="Path to the repository to scan.")
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    changed_files = git_changed_files(repo_path, args.base)
    report = summarize(detect_risk(changed_files), changed_files)

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

