"""API Changelog Generator for Downstream Breakage Radar.

Extracts symbol changes (added, removed, modified) between base and HEAD
and formats them as a clean Markdown changelog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from downstream_breakage_radar import ast_analyzer, go_analyzer, ts_analyzer


def generate_changelog(repo_path: Path, changed_files: Iterable[str], base_ref: str) -> str:
    """Generate a clean markdown diff list of API changes."""
    additions = []
    deletions = []
    modifications = []

    for path in changed_files:
        # Load content
        old_content = None
        new_content = None

        new_file = repo_path / path
        if new_file.exists():
            try:
                new_content = new_file.read_text(encoding="utf-8")
            except Exception:
                pass

        if path.endswith(".py"):
            old_content = ast_analyzer._get_file_content_at_ref(repo_path, base_ref, path)
            if not old_content and not new_content:
                continue

            try:
                old_symbols = {}
                if old_content:
                    old_tree = ast_analyzer.ast.parse(old_content)
                    old_funcs = ast_analyzer._get_public_functions(old_tree)
                    old_classes = ast_analyzer._get_public_classes(old_tree)
                    for k, v in old_funcs.items():
                        old_symbols[f"function:{k}"] = f"def {k}(...)"
                    for k, v in old_classes.items():
                        old_symbols[f"class:{k}"] = f"class {k}"

                new_symbols = {}
                if new_content:
                    new_tree = ast_analyzer.ast.parse(new_content)
                    new_funcs = ast_analyzer._get_public_functions(new_tree)
                    new_classes = ast_analyzer._get_public_classes(new_tree)
                    for k, v in new_funcs.items():
                        new_symbols[f"function:{k}"] = f"def {k}(...)"
                    for k, v in new_classes.items():
                        new_symbols[f"class:{k}"] = f"class {k}"
            except Exception:
                continue

        elif path.endswith(".go"):
            old_content = go_analyzer._get_file_content_at_ref(repo_path, base_ref, path)
            if not old_content and not new_content:
                continue
            old_symbols = go_analyzer.extract_go_symbols(old_content) if old_content else {}
            new_symbols = go_analyzer.extract_go_symbols(new_content) if new_content else {}

        elif path.endswith((".js", ".ts", ".jsx", ".tsx")):
            old_content = ts_analyzer._get_file_content_at_ref(repo_path, base_ref, path)
            if not old_content and not new_content:
                continue
            old_symbols = ts_analyzer.extract_js_ts_symbols(old_content) if old_content else {}
            new_symbols = ts_analyzer.extract_js_ts_symbols(new_content) if new_content else {}
        else:
            continue

        # Compare symbols
        # 1. Added
        for key, new_sig in new_symbols.items():
            if key not in old_symbols:
                sym_type, sym_name = key.split(":", 1)
                additions.append(f"+ **Added** {sym_type} `{sym_name}` in `{path}`")

        # 2. Removed
        for key, old_sig in old_symbols.items():
            if key not in new_symbols:
                sym_type, sym_name = key.split(":", 1)
                deletions.append(f"- **Removed** {sym_type} `{sym_name}` from `{path}`")
            elif old_sig != new_symbols[key]:
                sym_type, sym_name = key.split(":", 1)
                modifications.append(f"* **Modified signature** of {sym_type} `{sym_name}` in `{path}`")

    # Format Markdown
    lines = ["# 📡 API Changelog", "", "API surface changes detected between base and branch:"]
    
    if not additions and not deletions and not modifications:
        lines.append("", "No public API surface changes detected.")
        return "\n".join(lines)

    if deletions:
        lines += ["", "## 🔴 Removals (Breaking Changes)", ""]
        lines.extend(deletions)

    if modifications:
        lines += ["", "## 🟡 Modifications", ""]
        lines.extend(modifications)

    if additions:
        lines += ["", "## 🟢 Additions", ""]
        lines.extend(additions)

    return "\n".join(lines)
