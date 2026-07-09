"""AST-level analysis for downstream breakage detection in Python files.

Uses Python's built-in `ast` module to deeply understand code changes and
detect when public symbols are removed or their signatures change.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from breakguard.scanner import Finding


@dataclass
class FuncDef:
    name: str
    args: list[str]
    kwonlyargs: list[str]
    defaults_count: int
    kw_defaults_count: int
    lineno: int
    deprecated: bool


@dataclass
class ClassDef:
    name: str
    lineno: int
    deprecated: bool


def _is_deprecated(node: ast.AST) -> bool:
    """Check if the node has a deprecation decorator or deprecation docstring."""
    # 1. Check decorators
    if hasattr(node, "decorator_list"):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "deprecated":
                return True
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "deprecated":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "deprecated":
                return True

    # 2. Check docstring
    docstring = ast.get_docstring(node)
    if docstring and ("deprecated" in docstring.lower() or "deprecated" in docstring):
        return True

    return False


def _get_public_functions(tree: ast.AST) -> dict[str, FuncDef]:
    """Extract public functions and their signatures from an AST."""
    funcs = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                args = [arg.arg for arg in node.args.args]
                kwonlyargs = [arg.arg for arg in node.args.kwonlyargs]
                defaults_count = len(node.args.defaults)
                kw_defaults_count = sum(1 for d in node.args.kw_defaults if d is not None)
                
                funcs[node.name] = FuncDef(
                    name=node.name,
                    args=args,
                    kwonlyargs=kwonlyargs,
                    defaults_count=defaults_count,
                    kw_defaults_count=kw_defaults_count,
                    lineno=getattr(node, "lineno", 1),
                    deprecated=_is_deprecated(node),
                )
    return funcs


def _get_public_classes(tree: ast.AST) -> dict[str, ClassDef]:
    """Extract public classes from an AST."""
    classes = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                classes[node.name] = ClassDef(
                    name=node.name,
                    lineno=getattr(node, "lineno", 1),
                    deprecated=_is_deprecated(node),
                )
    return classes


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


def analyze_python_ast(repo_path: Path, changed_files: Iterable[str], base_ref: str) -> list[Finding]:
    """Parse Python ASTs to detect removed symbols and signature changes."""
    findings: list[Finding] = []

    for path in changed_files:
        if not path.endswith(".py"):
            continue

        # Get the old content
        old_content = _get_file_content_at_ref(repo_path, base_ref, path)
        if not old_content:
            continue  # File was likely added, no breakage possible

        # Get the new content
        new_path = repo_path / path
        if not new_path.exists():
            continue  # File deleted; diff_analyzer handles this

        try:
            new_content = new_path.read_text(encoding="utf-8")
        except Exception:
            continue

        try:
            old_tree = ast.parse(old_content)
            new_tree = ast.parse(new_content)
        except SyntaxError:
            continue  # Skip if there's a syntax error (e.g. invalid Python code)

        old_funcs = _get_public_functions(old_tree)
        new_funcs = _get_public_functions(new_tree)

        old_classes = _get_public_classes(old_tree)
        new_classes = _get_public_classes(new_tree)

        # 1. Check for removed classes
        for cls_name, old_cls in old_classes.items():
            if cls_name not in new_classes:
                search_url = f"https://github.com/search?q={cls_name}+language%3Apython&type=code"
                if old_cls.deprecated:
                    findings.append(
                        Finding(
                            severity="medium",
                            path=path,
                            message=f"Removed deprecated class: {cls_name}",
                            migration_note=f"The deprecated class '{cls_name}' was removed from {path}. [Check downstream impact]({search_url})",
                            line=old_cls.lineno,
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity="high",
                            path=path,
                            message=f"Removed public class: {cls_name}",
                            migration_note=f"The class '{cls_name}' was removed from {path} without deprecation. Consumers will break. [Check downstream impact]({search_url})",
                            line=old_cls.lineno,
                        )
                    )

        # 2. Check for removed functions or signature changes
        for name, old_func in old_funcs.items():
            search_url = f"https://github.com/search?q={name}+language%3Apython&type=code"
            if name not in new_funcs:
                if old_func.deprecated:
                    findings.append(
                        Finding(
                            severity="medium",
                            path=path,
                            message=f"Removed deprecated function: {name}",
                            migration_note=f"The deprecated function '{name}' was removed from {path}. [Check downstream impact]({search_url})",
                            line=old_func.lineno,
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity="high",
                            path=path,
                            message=f"Removed public function: {name}",
                            migration_note=f"The function '{name}' was removed from {path} without deprecation. Consumers will break. [Check downstream impact]({search_url})",
                            line=old_func.lineno,
                        )
                    )
            else:
                new_func = new_funcs[name]
                
                # Check if required arguments increased (or defaults removed)
                old_req_args = len(old_func.args) - old_func.defaults_count
                new_req_args = len(new_func.args) - new_func.defaults_count
                
                if new_req_args > old_req_args:
                    findings.append(
                        Finding(
                            severity="high",
                            path=path,
                            message=f"Function signature changed: {name}",
                            migration_note=f"The function '{name}' in {path} now requires more positional arguments. [Check downstream impact]({search_url})",
                            line=new_func.lineno,
                        )
                    )
                    continue

                # Check if named arguments were removed
                old_all_args = set(old_func.args + old_func.kwonlyargs)
                new_all_args = set(new_func.args + new_func.kwonlyargs)
                missing_args = old_all_args - new_all_args
                
                if missing_args:
                    findings.append(
                        Finding(
                            severity="high",
                            path=path,
                            message=f"Function signature changed: {name}",
                            migration_note=f"The function '{name}' in {path} removed arguments: {', '.join(missing_args)}. [Check downstream impact]({search_url})",
                            line=new_func.lineno,
                        )
                    )

    return findings
