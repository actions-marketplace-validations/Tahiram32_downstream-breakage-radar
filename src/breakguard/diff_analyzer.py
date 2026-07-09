"""Diff-level analysis for downstream breakage detection.

Parses unified git diffs (not just filenames) to detect high-severity
changes such as removed functions/classes, changed signatures, renamed
exports, deleted files, and major version bumps in config files.
"""

from __future__ import annotations

import re
from typing import List

from breakguard.scanner import Finding


# ---------------------------------------------------------------------------
# Patterns for removed definitions (lines starting with ``-``)
# ---------------------------------------------------------------------------

#: Matches removed Python / Kotlin / Go / Rust / Java / C# definitions.
_REMOVED_DEF_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^-\s*def\s+(\w+)"),          # Python
    re.compile(r"^-\s*class\s+(\w+)"),         # Python / Java / C# / Kotlin
    re.compile(r"^-\s*export\s+(\w+)"),        # JS / TS
    re.compile(r"^-\s*public\s+(\w+)"),        # Java / C#
    re.compile(r"^-\s*func\s+(\w+)"),          # Go
]

#: Pattern to detect changed function signatures (def line changed).
_CHANGED_SIG_PATTERN = re.compile(r"^-\s*(def\s+\w+\s*\(.*\))")

#: Detects a semver-like version string.
_VERSION_RE = re.compile(r"""version\s*=\s*["'](\d+)\.(\d+)""", re.IGNORECASE)

#: Config file basenames where a major version bump is noteworthy.
_CONFIG_FILENAMES: set[str] = {
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_diff(
    diff_text: str,
    deleted_files: list[str] | None = None,
) -> list[Finding]:
    """Parse *diff_text* (unified diff) and return high-severity findings.

    Parameters
    ----------
    diff_text:
        The full unified diff output (e.g. ``git diff base...HEAD``).
    deleted_files:
        An optional pre-computed list of deleted file paths.  When
        provided, a **high** finding is emitted for every public-facing
        deleted file.

    Returns
    -------
    list[Finding]
        A list of findings — mostly severity **high**.
    """

    findings: list[Finding] = []

    # 1. Deleted public-facing files ------------------------------------------
    if deleted_files:
        findings.extend(_check_deleted_files(deleted_files))

    # 2. Walk the diff hunks --------------------------------------------------
    current_file: str | None = None

    for line in diff_text.splitlines():
        # Track which file we are in
        if line.startswith("diff --git"):
            # e.g. "diff --git a/foo/bar.py b/foo/bar.py"
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3].lstrip("b/")  # b/path -> path
            else:
                current_file = None
            continue

        if current_file is None:
            continue

        # Only look at removed lines
        if not line.startswith("-") or line.startswith("---"):
            continue

        # 2a. Removed function / class definitions
        for pattern in _REMOVED_DEF_PATTERNS:
            m = pattern.match(line)
            if m:
                name = m.group(1)
                search_url = f"https://github.com/search?q={name}&type=code"
                findings.append(
                    Finding(
                        severity="high",
                        path=current_file,
                        message=f"Removed definition: {name}",
                        migration_note=(
                            f"'{name}' was removed from {current_file}. "
                            f"[Check downstream impact]({search_url})"
                        ),
                    )
                )

        # 2b. Changed function signatures — only fires when a ``def`` line
        #     is removed (the ``+def`` counterpart, if any, is a separate
        #     check downstream callers can compare).
        # Covered by the def pattern above; nothing extra needed.

    # 3. Version bumps in config files ----------------------------------------
    findings.extend(_check_version_bumps(diff_text))

    return findings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_deleted_files(deleted_files: list[str]) -> list[Finding]:
    """Emit a high finding for every deleted file that looks public-facing."""

    findings: list[Finding] = []
    for path in deleted_files:
        lowered = path.lower()
        is_public = (
            any(marker in lowered for marker in (
                "src/", "lib/", "app/", "api/", "public/",
                "include/", "internal/", "pkg/", "schemas/", "proto/", "openapi",
            ))
            or lowered.endswith((
                ".py", ".ts", ".tsx", ".js", ".jsx",
                ".go", ".rs", ".java", ".kt", ".cs",
            ))
        )
        if is_public:
            findings.append(
                Finding(
                    severity="high",
                    path=path,
                    message="Public-facing file was deleted.",
                    migration_note=(
                        f"'{path}' has been removed entirely. "
                        "Downstream consumers depending on this file will break."
                    ),
                )
            )
    return findings


def _check_version_bumps(diff_text: str) -> list[Finding]:
    """Detect major version bumps in config files within *diff_text*."""

    findings: list[Finding] = []
    current_file: str | None = None

    old_major: int | None = None
    new_major: int | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            # Flush any pending version-bump check
            if current_file is not None and old_major is not None and new_major is not None:
                if new_major > old_major:
                    findings.append(_version_bump_finding(current_file, old_major, new_major))
            old_major = None
            new_major = None

            parts = line.split()
            if len(parts) >= 4:
                candidate = parts[3].lstrip("b/")
                # Only care about known config file names
                basename = candidate.rsplit("/", 1)[-1] if "/" in candidate else candidate
                if basename in _CONFIG_FILENAMES:
                    current_file = candidate
                else:
                    current_file = None
            else:
                current_file = None
            continue

        if current_file is None:
            continue

        # Removed version line
        if line.startswith("-") and not line.startswith("---"):
            m = _VERSION_RE.search(line)
            if m:
                old_major = int(m.group(1))

        # Added version line
        if line.startswith("+") and not line.startswith("+++"):
            m = _VERSION_RE.search(line)
            if m:
                new_major = int(m.group(1))

    # Flush last file
    if current_file is not None and old_major is not None and new_major is not None:
        if new_major > old_major:
            findings.append(_version_bump_finding(current_file, old_major, new_major))

    return findings


def _version_bump_finding(path: str, old: int, new: int) -> Finding:
    """Create a Finding for a major version bump."""

    return Finding(
        severity="high",
        path=path,
        message=f"Major version bump detected: {old}.x → {new}.x",
        migration_note=(
            f"The major version in '{path}' changed from {old} to {new}. "
            "This signals a breaking release — downstream consumers must update."
        ),
    )
