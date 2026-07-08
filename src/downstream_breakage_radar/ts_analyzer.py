"""JavaScript and TypeScript-specific analysis for downstream breakage detection.

Parses JS/TS files to extract exported functions, classes, and types,
and detects when they are removed or their signatures change.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable

from downstream_breakage_radar.scanner import Finding

# Matches: export function/class/const/let/var ExportedName
JS_EXPORT_FUNC = re.compile(
    r'(?m)^\s*export\s+(?:async\s+)?function\s+([a-zA-Z0-9_]+)\s*(\([^)]*\))'
)
JS_EXPORT_CLASS = re.compile(
    r'(?m)^\s*export\s+class\s+([a-zA-Z0-9_]+)'
)
JS_EXPORT_CONST = re.compile(
    r'(?m)^\s*export\s+(?:const|let|var)\s+([a-zA-Z0-9_]+)'
)
# For TypeScript declaration files (.d.ts) or TS interfaces
TS_INTERFACE = re.compile(
    r'(?m)^\s*export\s+interface\s+([a-zA-Z0-9_]+)'
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


def extract_js_ts_symbols(content: str) -> dict[str, str]:
    """Extract exported JS/TS symbols and their signature/definition strings."""
    symbols = {}
    
    # Strip comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    
    for match in JS_EXPORT_FUNC.finditer(content):
        name = match.group(1)
        sig = match.group(0).strip()
        symbols[f"func:{name}"] = sig
        
    for match in JS_EXPORT_CLASS.finditer(content):
        name = match.group(1)
        sig = match.group(0).strip()
        symbols[f"class:{name}"] = sig

    for match in JS_EXPORT_CONST.finditer(content):
        name = match.group(1)
        sig = match.group(0).strip()
        symbols[f"const:{name}"] = sig

    for match in TS_INTERFACE.finditer(content):
        name = match.group(1)
        sig = match.group(0).strip()
        symbols[f"interface:{name}"] = sig

    return symbols


def _is_js_ts_deprecated(content: str, name: str) -> bool:
    """Check if the symbol was marked deprecated (using JSDoc @deprecated) in old content."""
    # Matches JSDoc comment with @deprecated followed by the export declaration
    pattern = re.compile(
        rf'(?is)/\*\*.*?\* @deprecated.*?\*/\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var|interface)\s+{name}\b'
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


def analyze_js_ts(repo_path: Path, changed_files: Iterable[str], base_ref: str) -> list[Finding]:
    """Parse JS/TS files to detect removed symbols and signature changes."""
    findings: list[Finding] = []

    for path in changed_files:
        if not (path.endswith(".js") or path.endswith(".ts") or path.endswith(".jsx") or path.endswith(".tsx")):
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

        old_symbols = extract_js_ts_symbols(old_content)
        new_symbols = extract_js_ts_symbols(new_content)

        for key, old_sig in old_symbols.items():
            sym_type, sym_name = key.split(":", 1)
            search_url = f"https://github.com/search?q={sym_name}+language%3ATypeScript&type=code"
            
            lineno = _find_line_number(old_content, old_sig)

            if key not in new_symbols:
                # Check for deprecation
                if _is_js_ts_deprecated(old_content, sym_name):
                    findings.append(
                        Finding(
                            severity="medium",
                            path=path,
                            message=f"Removed deprecated {sym_type}: {sym_name}",
                            migration_note=f"The deprecated exported {sym_type} '{sym_name}' was removed from {path}. [Check downstream impact]({search_url})",
                            line=lineno,
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity="high",
                            path=path,
                            message=f"Removed exported {sym_type}: {sym_name}",
                            migration_note=f"The exported {sym_type} '{sym_name}' was removed from {path} without deprecation. Consumers will break. [Check downstream impact]({search_url})",
                            line=lineno,
                        )
                    )
            elif old_sig != new_symbols[key]:
                new_lineno = _find_line_number(new_content, new_symbols[key])
                findings.append(
                    Finding(
                        severity="high",
                        path=path,
                        message=f"Exported {sym_type} signature changed: {sym_name}",
                        migration_note=f"The signature of exported {sym_type} '{sym_name}' in {path} was changed. [Check downstream impact]({search_url})",
                        line=new_lineno,
                    )
                )

    return findings
