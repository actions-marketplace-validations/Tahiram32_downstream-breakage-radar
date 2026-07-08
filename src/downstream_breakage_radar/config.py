"""Configuration parsing for Downstream Breakage Radar.

Parses configuration from pyproject.toml or breakage-radar.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def parse_config(repo_path: Path) -> dict:
    """Parse configuration settings from the repo."""
    config = {
        "ignored_paths": [],
        "public_dirs": None,
        "severity_overrides": {},
    }

    # 1. Try pyproject.toml
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            # Extract [tool.breakage-radar] block
            match = re.search(r'(?s)\[tool\.breakage-radar\](.*?)(?:^\[|\Z)', content)
            if match:
                block = match.group(1)
                
                # Parse ignored_paths = [ ... ]
                ip_match = re.search(r'(?s)ignored_paths\s*=\s*\[(.*?)\]', block)
                if ip_match:
                    config["ignored_paths"] = [
                        x.strip().strip('"').strip("'")
                        for x in ip_match.group(1).split(",")
                        if x.strip()
                    ]
                
                # Parse public_dirs = [ ... ]
                pd_match = re.search(r'(?s)public_dirs\s*=\s*\[(.*?)\]', block)
                if pd_match:
                    config["public_dirs"] = [
                        x.strip().strip('"').strip("'")
                        for x in pd_match.group(1).split(",")
                        if x.strip()
                    ]
                
                # Parse severity_overrides = { ... }
                so_match = re.search(r'(?s)severity_overrides\s*=\s*\{(.*?)\}', block)
                if so_match:
                    # Very simple key-value parser for TOML inline table
                    for pair in so_match.group(1).split(","):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            config["severity_overrides"][k.strip().strip('"').strip("'")] = (
                                v.strip().strip('"').strip("'")
                            )
        except Exception:
            pass

    # 2. Try breakage-radar.json
    br_json = repo_path / "breakage-radar.json"
    if br_json.exists():
        try:
            data = json.loads(br_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config["ignored_paths"].extend(data.get("ignored_paths", []))
                if "public_dirs" in data:
                    config["public_dirs"] = data["public_dirs"]
                if isinstance(data.get("severity_overrides"), dict):
                    config["severity_overrides"].update(data["severity_overrides"])
        except Exception:
            pass

    return config
