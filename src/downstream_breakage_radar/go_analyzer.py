"""Go-specific analysis for downstream breakage detection.

Parses Go source files to extract exported functions, methods, and types,
and detects when they are removed or their signatures change.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

from downstream_breakage_radar.scanner import Finding

# Matches: func ExportedName(...) ...
# Or: func (r Receiver) ExportedName(...) ...
GO_FUNC_PAT = re.compile(
    r'(?m)^\s*func\s+(?:\([^)]+\)\s+)?([A-Z][a-zA-Z0-9_]*)\s*(\([^)]*\))'
)
# Matches type declarations (structs, interfaces, etc.)
GO_TYPE_PAT = re.compile(
    r'(?m)^\s*type\s+([A-Z][a-zA-Z0-9_]*)\s+(struct|interface|type)'
)


def _get_file_content_at_ref(repo_path: Path, ref: str, file_path: str) -> str | None:
    """Get the content of a file at a specific git ref."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), "show", f"{ref}:{file_path}"],
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout
    except subprocess.CalledProcessError:
        return None


def extract_go_symbols(content: str) -> dict[str, str]:
    """Extract exported Go symbols and their signature/definition strings."""
    symbols = {}
    
    # Strip comments to prevent false positives
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    
    for match in GO_FUNC_PAT.finditer(content):
        name = match.group(1)
        sig = match.group(0).strip()
        symbols[f"func:{name}"] = sig
        
    for match in GO_TYPE_PAT.finditer(content):
        name = match.group(1)
        sig = match.group(0).strip()
        symbols[f"type:{name}"] = sig
        
    return symbols


def _is_go_deprecated(content: str, name: str) -> bool:
    """Check if the symbol had a // Deprecated: comment above it in the old content."""
    # Matches a // Deprecated: comment followed by optional comment lines and the func/type
    pattern = re.compile(
        rf'(?mi)//\s*Deprecated:.*?\n(?:[^\n]*\n)*?\s*(?:func|type)\s+(?:\([^)]+\)\s+)?{name}\b'
    )
    return bool(pattern.search(content))


def _find_line_number(content: str, pattern_str: str) -> int:
    """Find the line number of a pattern in the content."""
    try:
        match = re.search(re.escape(pattern_str), content)
        if match:
            return content.count("\n", 0, match.start()) + 1
    except Exception:
        pass
    return 1


def analyze_go(repo_path: Path, changed_files: Iterable[str], base_ref: str) -> list[Finding]:
    """Parse Go files to detect removed symbols and signature changes."""
    findings: list[Finding] = []

    for path in changed_files:
        if not path.endswith(".go"):
            continue

        # Get the old content
        old_content = _get_file_content_at_ref(repo_path, base_ref, path)
        if not old_content:
            continue  # File was likely added

        # Get the new content
        new_path = repo_path / path
        if not new_path.exists():
            continue

        try:
            new_content = new_path.read_text(encoding="utf-8")
        except Exception:
            continue

        old_symbols = extract_go_symbols(old_content)
        new_symbols = extract_go_symbols(new_content)

        for key, old_sig in old_symbols.items():
            sym_type, sym_name = key.split(":", 1)
            search_url = f"https://github.com/search?q={sym_name}+language%3AGo&type=code"
            
            # Find line number in original file
            lineno = _find_line_number(old_content, old_sig)

            if key not in new_symbols:
                # Check for deprecation comment
                if _is_go_deprecated(old_content, sym_name):
                    findings.append(
                        Finding(
                            severity="medium",
                            path=path,
                            message=f"Removed deprecated Go {sym_type}: {sym_name}",
                            migration_note=f"The deprecated Go {sym_type} '{sym_name}' was removed from {path}. [Check downstream impact]({search_url})",
                            line=lineno,
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity="high",
                            path=path,
                            message=f"Removed exported Go {sym_type}: {sym_name}",
                            migration_note=f"The Go {sym_type} '{sym_name}' was removed from {path} without deprecation. Consumers will break. [Check downstream impact]({search_url})",
                            line=lineno,
                        )
                    )
            elif old_sig != new_symbols[key]:
                new_lineno = _find_line_number(new_content, new_symbols[key])
                findings.append(
                    Finding(
                        severity="high",
                        path=path,
                        message=f"Go {sym_type} signature changed: {sym_name}",
                        migration_note=f"The signature of Go {sym_type} '{sym_name}' in {path} was changed. [Check downstream impact]({search_url})",
                        line=new_lineno,
                    )
                )

    return findings
