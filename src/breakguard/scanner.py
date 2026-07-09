"""Core detection engine for downstream breakage scanning.

Provides the primary data structures and risk-detection logic used by the
CLI and the GitHub Action.  Everything here is stdlib-only.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISKY_PATH_MARKERS: tuple[str, ...] = (
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

RISKY_FILENAMES: set[str] = {
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

SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".rs", ".java", ".kt", ".cs",
)

SEVERITY_ORDER: dict[str, int] = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """A single risk finding produced by the scanner."""

    severity: str
    path: str
    message: str
    migration_note: str
    line: int = 1


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_changed_files(repo_path: Path, base_ref: str) -> list[str]:
    """Return the list of file paths changed between *base_ref* and HEAD."""

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def git_diff(repo_path: Path, base_ref: str) -> str:
    """Return the unified diff between *base_ref* and HEAD."""

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def git_deleted_files(repo_path: Path, base_ref: str) -> list[str]:
    """Return file paths that were deleted between *base_ref* and HEAD."""

    completed = subprocess.run(
        ["git", "-C", str(repo_path), "diff", "--name-only", "--diff-filter=D", f"{base_ref}...HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Risk detection
# ---------------------------------------------------------------------------

def detect_risk(changed_files: Iterable[str]) -> list[Finding]:
    """Analyse *changed_files* and return findings based on path heuristics.

    This function only inspects file names/paths.  For diff-level analysis
    use :func:`breakguard.diff_analyzer.analyze_diff`.
    """

    findings: list[Finding] = []
    for path in changed_files:
        lowered = path.lower()
        filename = Path(path).name

        # Medium: risky path or config file
        if filename in RISKY_FILENAMES or any(marker in lowered for marker in RISKY_PATH_MARKERS):
            findings.append(
                Finding(
                    severity="medium",
                    path=path,
                    message="Change touches a likely public surface or release-critical file.",
                    migration_note="Review for API compatibility, config drift, and release notes before merging.",
                )
            )

        # Low: any source code change
        if lowered.endswith(SOURCE_EXTENSIONS):
            findings.append(
                Finding(
                    severity="low",
                    path=path,
                    message="Source code change may affect downstream consumers.",
                    migration_note="Check for renamed symbols, changed defaults, and behavior shifts.",
                )
            )

    return findings


def find_current_version(repo_path: Path) -> str | None:
    """Attempt to find the current version from common manifests."""
    # Try pyproject.toml
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Try package.json
    package_json = repo_path / "package.json"
    if package_json.exists():
        import json
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "version" in data:
                return str(data["version"])
        except Exception:
            pass

    # Try Cargo.toml
    cargo = repo_path / "Cargo.toml"
    if cargo.exists():
        try:
            content = cargo.read_text(encoding="utf-8")
            match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    return None


def recommend_version_bump(current_version: str | None, risk_level: str) -> tuple[str, str]:
    """Calculate the recommended SemVer bump type and next version string."""
    if risk_level == "high":
        bump_type = "major"
    elif risk_level == "medium":
        bump_type = "minor"
    else:
        bump_type = "patch"

    if not current_version:
        return bump_type, ""

    parts = current_version.split(".")
    if len(parts) != 3:
        return bump_type, ""

    try:
        major, minor, patch = map(int, parts)
        if bump_type == "major":
            new_version = f"{major + 1}.0.0"
        elif bump_type == "minor":
            new_version = f"{major}.{minor + 1}.0"
        else:
            new_version = f"{major}.{minor}.{patch + 1}"
        return bump_type, new_version
    except ValueError:
        return bump_type, ""


# ---------------------------------------------------------------------------
# Summariser
# ---------------------------------------------------------------------------

def summarize(findings: list[Finding], changed_files: list[str], repo_path: Path | None = None) -> dict[str, object]:
    """Build a summary dict from a list of findings and changed files."""

    highest = "none"
    for f in findings:
        sev = f.severity
        if SEVERITY_ORDER.get(sev, 0) > SEVERITY_ORDER.get(highest, 0):
            highest = sev

    current_version = None
    bump_type = "patch"
    recommended_version = ""

    if repo_path:
        current_version = find_current_version(repo_path)
        bump_type, recommended_version = recommend_version_bump(current_version, highest)

    return {
        "changed_files": changed_files,
        "change_count": len(changed_files),
        "risk_level": highest,
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "current_version": current_version,
        "recommended_bump": bump_type,
        "recommended_version": recommended_version,
    }
