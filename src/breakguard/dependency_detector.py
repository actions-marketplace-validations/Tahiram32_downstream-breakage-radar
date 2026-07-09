"""Dependency analysis for checking unused and missing dependencies.

Scans the repository to compare declared dependencies in manifests
against actual imports in code.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

from breakguard.scanner import Finding

# Simple regexes to find imports
PY_IMPORT_PAT = re.compile(r'(?m)^\s*(?:from|import)\s+([a-zA-Z0-9_]+)')
JS_IMPORT_PAT = re.compile(r'(?m)^\s*(?:import\s+.*?\s+from\s+|require\s*\(\s*)["\']([^"\']+)["\']')

# Known node.js built-ins to ignore
NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "dns", "domain", "events", "fs", "http",
    "http2", "https", "inspector", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream",
    "string_decoder", "timers", "tls", "trace_events", "tty", "url", "util",
    "v8", "vm", "wasi", "worker_threads", "zlib"
}


def _get_python_stdlib() -> set[str]:
    """Return the set of Python standard library module names."""
    # sys.stdlib_module_names is available in Python 3.10+
    return getattr(sys, "stdlib_module_names", set())


def parse_pyproject_deps(content: str) -> set[str]:
    """Parse dependencies from pyproject.toml."""
    deps = set()
    # Simple regex search for dependencies = [ ... ]
    match = re.search(r'(?s)dependencies\s*=\s*\[(.*?)\]', content)
    if match:
        for item in re.findall(r'["\']([^"\']+)["\']', match.group(1)):
            dep = re.split(r'[<>=!~]', item)[0].strip()
            if dep:
                deps.add(dep.lower().replace("_", "-"))
    return deps


def parse_requirements_txt(content: str) -> set[str]:
    """Parse dependencies from requirements.txt."""
    deps = set()
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            dep = re.split(r'[<>=!~]', line)[0].strip()
            if dep:
                deps.add(dep.lower().replace("_", "-"))
    return deps


def parse_package_json_deps(content: str) -> set[str]:
    """Parse dependencies from package.json."""
    deps = set()
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            for key in ["dependencies", "devDependencies"]:
                if key in data and isinstance(data[key], dict):
                    for dep in data[key].keys():
                        deps.add(dep.lower())
    except Exception:
        pass
    return deps


def analyze_dependencies(repo_path: Path, ignore_patterns: list[str] = None) -> list[Finding]:
    """Scan codebase and check for missing/unused dependencies."""
    findings: list[Finding] = []
    
    if ignore_patterns is None:
        ignore_patterns = []

    # 1. Load declared dependencies
    declared_py: set[str] = set()
    declared_js: set[str] = set()

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        declared_py.update(parse_pyproject_deps(pyproject.read_text(encoding="utf-8")))

    req_txt = repo_path / "requirements.txt"
    if req_txt.exists():
        declared_py.update(parse_requirements_txt(req_txt.read_text(encoding="utf-8")))

    package_json = repo_path / "package.json"
    if package_json.exists():
        declared_js.update(parse_package_json_deps(package_json.read_text(encoding="utf-8")))

    # If no dependencies are declared, skip check
    if not declared_py and not declared_js:
        return []

    # 2. Scan codebase for imports
    imported_py: set[str] = set()
    imported_js: set[str] = set()

    python_stdlib = _get_python_stdlib()

    for root, dirs, files in os.walk(repo_path):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", "dist", "build")]
        
        # Apply .breakageignore patterns if present
        relative_root = Path(root).relative_to(repo_path)
        
        filtered_files = []
        for f in files:
            file_rel_path = str(relative_root / f) if str(relative_root) != "." else f
            
            ignored = False
            for p in ignore_patterns:
                if fnmatch.fnmatch(file_rel_path, p) or file_rel_path.startswith(p.rstrip("/") + "/"):
                    ignored = True
                    break
            if not ignored:
                filtered_files.append(f)

        for f in filtered_files:
            file_path = Path(root) / f
            
            if f.endswith(".py"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    for imp in PY_IMPORT_PAT.findall(content):
                        imp_lower = imp.lower().replace("_", "-")
                        if imp_lower not in python_stdlib:
                            imported_py.add(imp_lower)
                except Exception:
                    pass
            elif f.endswith((".js", ".ts", ".jsx", ".tsx")):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    for imp in JS_IMPORT_PAT.findall(content):
                        # JS imports can be relative: import x from './y'
                        if not imp.startswith("."):
                            # Handle scoped packages (e.g. @babel/core) vs normal ones
                            parts = imp.split("/")
                            dep_name = parts[0] if not imp.startswith("@") else f"{parts[0]}/{parts[1]}"
                            dep_name = dep_name.lower()
                            if dep_name not in NODE_BUILTINS:
                                imported_js.add(dep_name)
                except Exception:
                    pass

    # 3. Check for mismatches
    # Python unused check
    for dep in declared_py:
        # Simple heuristic: library named 'requests' is imported as 'requests'
        # Sometimes library names differ from import names (e.g. 'pyyaml' is 'yaml').
        # We can account for common mappings or just do a substring check.
        if dep not in imported_py and not any(dep in imp for imp in imported_py):
            findings.append(
                Finding(
                    severity="low",
                    path="pyproject.toml" if pyproject.exists() else "requirements.txt",
                    message=f"Unused Python dependency: {dep}",
                    migration_note=f"Dependency '{dep}' is declared but does not appear to be imported in the code.",
                )
            )

    # JS/TS unused check
    for dep in declared_js:
        if dep not in imported_js:
            findings.append(
                Finding(
                    severity="low",
                    path="package.json",
                    message=f"Unused JS/TS dependency: {dep}",
                    migration_note=f"Dependency '{dep}' is declared but does not appear to be imported in the code.",
                )
            )

    # Python missing check
    for imp in imported_py:
        # Ignore project's own package name if imported
        proj_name = repo_path.name.lower().replace("_", "-")
        if imp == proj_name or imp == "breakguard":
            continue
        # Also ignore local imports (subdirectories of current directory)
        local_dir = repo_path / imp.replace("-", "_")
        if local_dir.is_dir():
            continue
            
        if declared_py and imp not in declared_py and not any(imp in dep for dep in declared_py):
            findings.append(
                Finding(
                    severity="high",
                    path="pyproject.toml" if pyproject.exists() else "requirements.txt",
                    message=f"Missing Python dependency: {imp}",
                    migration_note=f"Module '{imp}' is imported in code but not declared in your dependencies. Installation might fail.",
                )
            )

    # JS/TS missing check
    for imp in imported_js:
        if declared_js and imp not in declared_js:
            findings.append(
                Finding(
                    severity="high",
                    path="package.json",
                    message=f"Missing JS/TS dependency: {imp}",
                    migration_note=f"Module '{imp}' is imported in code but not declared in package.json. Installation might fail.",
                )
            )

    return findings
