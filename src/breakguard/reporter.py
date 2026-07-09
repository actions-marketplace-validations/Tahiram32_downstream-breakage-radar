"""Output formatting for scan reports.

Supports plain text, JSON, and Markdown (suitable for PR comments).
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Emoji / badge helpers
# ---------------------------------------------------------------------------

_SEVERITY_EMOJI: dict[str, str] = {
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢",
    "none": "⚪",
}

_SEVERITY_LABEL: dict[str, str] = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "none": "None",
}


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_text(report: dict[str, Any]) -> str:
    """Format *report* as human-readable plain text."""

    lines = [
        f"Risk level: {report['risk_level']}",
        f"Changed files: {report['change_count']}",
        f"Findings: {report['finding_count']}",
    ]
    if report.get("recommended_version"):
        lines.append(f"Recommended Bump: {report['recommended_bump'].upper()} (➡️ {report['recommended_version']})")
    elif report.get("recommended_bump"):
        lines.append(f"Recommended Bump: {report['recommended_bump'].upper()}")
    for finding in report["findings"]:
        lines.append("")
        lines.append(f"- [{finding['severity']}] {finding['path']}: {finding['message']}")
        lines.append(f"  Migration note: {finding['migration_note']}")
    if not report["findings"]:
        lines.append("")
        lines.append("No obvious breakage risks found.")
        
    lines.append("")
    lines.append("💡 Support this project: https://github.com/sponsors/Tahiram32")
    return "\n".join(lines)


def format_json(report: dict[str, Any]) -> str:
    """Format *report* as pretty-printed JSON."""

    return json.dumps(report, indent=2, sort_keys=True)


def format_markdown(report: dict[str, Any]) -> str:
    """Format *report* as GitHub-Flavoured Markdown suitable for PR comments."""

    risk = report["risk_level"]
    emoji = _SEVERITY_EMOJI.get(risk, "⚪")
    label = _SEVERITY_LABEL.get(risk, risk)

    lines: list[str] = [
        "## 📡 Downstream Breakage Radar",
        "",
        f"**Risk level:** {emoji} {label}  ",
        f"**Changed files:** {report['change_count']}  ",
        f"**Findings:** {report['finding_count']}",
    ]
    if report.get("recommended_version"):
        lines.append(f"**Recommended Bump:** `{report['recommended_bump'].upper()}` (➡️ `{report['recommended_version']}`)  ")
    elif report.get("recommended_bump"):
        lines.append(f"**Recommended Bump:** `{report['recommended_bump'].upper()}`  ")

    if not report["findings"]:
        lines += ["", "✅ No obvious breakage risks found."]
        return "\n".join(lines)

    lines += ["", "| Severity | File | Message |", "| --- | --- | --- |"]

    for finding in report["findings"]:
        sev = finding["severity"]
        sev_emoji = _SEVERITY_EMOJI.get(sev, "")
        lines.append(
            f"| {sev_emoji} {sev} | `{finding['path']}` | {finding['message']} |"
        )

    # Detailed migration notes
    lines += ["", "### Migration notes", ""]
    for finding in report["findings"]:
        lines.append(f"- **`{finding['path']}`**: {finding['migration_note']}")

    # Sponsor Footer
    lines += [
        "",
        "---",
        "💡 *Downstream Breakage Radar is free and open-source. If it helped protect your release, consider [sponsoring @Tahiram32 on GitHub](https://github.com/sponsors/Tahiram32)!*"
    ]

    return "\n".join(lines)


def format_github(report: dict[str, Any]) -> str:
    """Format *report* as GitHub Actions workflow commands suitable for inline annotations."""
    lines = []
    for finding in report["findings"]:
        sev = finding["severity"]
        if sev == "high":
            cmd = "error"
        elif sev == "medium":
            cmd = "warning"
        elif sev == "low":
            cmd = "notice"
        else:
            continue
            
        path = finding["path"]
        title = finding["message"].replace(",", " ")
        note = finding["migration_note"]
        
        lines.append(f"::{cmd} file={path},title={title}::{note}")
        
    return "\n".join(lines)


def format_sarif(report: dict[str, Any]) -> str:
    """Format *report* as SARIF JSON string for GitHub Code Scanning integration."""
    rules = [
        {
            "id": "downstream-breakage",
            "name": "DownstreamBreakageRule",
            "shortDescription": {
                "text": "Likely breaking change for downstream consumers."
            },
            "fullDescription": {
                "text": "Detects changes that modify or remove public API signatures, leading to potential compile/runtime breakage for downstream library users."
            },
            "defaultConfiguration": {
                "level": "warning"
            }
        }
    ]
    
    results = []
    for finding in report.get("findings", []):
        sev = finding.get("severity", "medium")
        level = "error" if sev == "high" else "warning" if sev == "medium" else "note"
        
        results.append({
            "ruleId": "downstream-breakage",
            "level": level,
            "message": {
                "text": f"{finding['message']}\n\nMigration Note: {finding['migration_note']}"
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": finding["path"]
                        },
                        "region": {
                            "startLine": finding.get("line", 1)
                        }
                    }
                }
            ]
        })
        
    sarif_output = {
        "$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.5.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Downstream Breakage Radar",
                        "informationUri": "https://github.com/Tahiram32/breakguard",
                        "rules": rules
                    }
                },
                "results": results
            }
        ]
    }
    
    return json.dumps(sarif_output, indent=2)


def generate_badge(risk_level: str) -> str:
    """Generate SVG badge content based on the risk level."""
    colors = {
        "none": "#22c55e",
        "low": "#3b82f6",
        "medium": "#eab308",
        "high": "#ef4444",
    }
    color = colors.get(risk_level.lower(), "#555")
    label = risk_level.capitalize()
    
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="130" height="20">
  <linearGradient id="b" lg="90"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <mask id="a"><rect width="130" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#a)">
    <rect width="80" height="20" fill="#555"/>
    <rect x="80" width="50" height="20" fill="{color}"/>
    <rect width="130" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="40" y="15" fill="#010101" fill-opacity=".3">Breakage Risk</text>
    <text x="40" y="14">Breakage Risk</text>
    <text x="105" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="105" y="14">{label}</text>
  </g>
</svg>"""
