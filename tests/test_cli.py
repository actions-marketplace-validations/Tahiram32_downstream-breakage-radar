from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from downstream_breakage_radar.cli import detect_risk, summarize


class DetectRiskTests(unittest.TestCase):
    def test_flags_public_surface_changes(self) -> None:
        findings = detect_risk(["src/api/client.py", "docs/notes.md"])
        self.assertTrue(any(f.severity == "medium" for f in findings))
        self.assertTrue(any(f.path == "src/api/client.py" for f in findings))

    def test_summarize_reports_change_count(self) -> None:
        report = summarize(detect_risk(["README.md"]), ["README.md"])
        self.assertEqual(report["change_count"], 1)
        self.assertEqual(report["risk_level"], "none")


if __name__ == "__main__":
    unittest.main()
