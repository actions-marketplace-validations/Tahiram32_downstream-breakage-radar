from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from downstream_breakage_radar.scanner import detect_risk, summarize
from downstream_breakage_radar.diff_analyzer import analyze_diff


class DetectRiskTests(unittest.TestCase):
    def test_flags_public_surface_changes(self) -> None:
        findings = detect_risk(["src/api/client.py", "docs/notes.md"])
        self.assertTrue(any(f.severity == "medium" for f in findings))
        self.assertTrue(any(f.path == "src/api/client.py" for f in findings))

    def test_summarize_reports_change_count(self) -> None:
        report = summarize(detect_risk(["README.md"]), ["README.md"])
        self.assertEqual(report["change_count"], 1)
        self.assertEqual(report["risk_level"], "none")

    def test_version_recommendation(self) -> None:
        from downstream_breakage_radar.scanner import recommend_version_bump
        bump, version = recommend_version_bump("1.2.3", "high")
        self.assertEqual(bump, "major")
        self.assertEqual(version, "2.0.0")

        bump, version = recommend_version_bump("1.2.3", "medium")
        self.assertEqual(bump, "minor")
        self.assertEqual(version, "1.3.0")

        bump, version = recommend_version_bump("1.2.3", "low")
        self.assertEqual(bump, "patch")
        self.assertEqual(version, "1.2.4")

class DiffAnalyzerTests(unittest.TestCase):
    def test_removed_function(self) -> None:
        diff_text = """diff --git a/src/api.py b/src/api.py
--- a/src/api.py
+++ b/src/api.py
@@ -1,5 +1,4 @@
-def removed_func():
-    pass
+def new_func():
+    pass
"""
        findings = analyze_diff(diff_text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "high")
        self.assertIn("removed_func", findings[0].message)

from downstream_breakage_radar.ast_analyzer import analyze_python_ast

class AstAnalyzerTests(unittest.TestCase):
    def test_removed_ast_function(self) -> None:
        pass

class GoAnalyzerTests(unittest.TestCase):
    def test_extract_go_symbols(self) -> None:
        from downstream_breakage_radar.go_analyzer import extract_go_symbols
        content = """
        package main
        // Exported function
        func Hello() string { return "world" }
        // Internal function
        func internal() {}
        // Exported type
        type Config struct {}
        """
        symbols = extract_go_symbols(content)
        self.assertIn("func:Hello", symbols)
        self.assertIn("type:Config", symbols)
        self.assertNotIn("func:internal", symbols)

class JsTsAnalyzerTests(unittest.TestCase):
    def test_extract_js_ts_symbols(self) -> None:
        from downstream_breakage_radar.ts_analyzer import extract_js_ts_symbols
        content = """
        export function compute(x, y) { return x + y; }
        export class Client {}
        export const API_URL = "http://api";
        function local() {}
        """
        symbols = extract_js_ts_symbols(content)
        self.assertIn("func:compute", symbols)
        self.assertIn("class:Client", symbols)
        self.assertIn("const:API_URL", symbols)
        self.assertNotIn("func:local", symbols)

class DependencyDetectorTests(unittest.TestCase):
    def test_parse_requirements_txt(self) -> None:
        from downstream_breakage_radar.dependency_detector import parse_requirements_txt
        content = """
        requests>=2.0.0
        numpy==1.22
        # comment
        scipy
        """
        deps = parse_requirements_txt(content)
        self.assertIn("requests", deps)
        self.assertIn("numpy", deps)
        self.assertIn("scipy", deps)

    def test_parse_package_json_deps(self) -> None:
        from downstream_breakage_radar.dependency_detector import parse_package_json_deps
        content = """{
            "dependencies": {
                "react": "^18.0.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0"
            }
        }"""
        deps = parse_package_json_deps(content)
        self.assertIn("react", deps)
        self.assertIn("typescript", deps)

class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.test_dir)

    def test_parse_config_pyproject(self) -> None:
        from downstream_breakage_radar.config import parse_config
        pyproject_content = """
        [tool.breakage-radar]
        ignored_paths = ["tests/*", "docs/*"]
        public_dirs = ["api/", "src/public/"]
        severity_overrides = { "Unused Python dependency" = "none", "Removed public class" = "medium" }
        """
        pyproject_path = Path(self.test_dir) / "pyproject.toml"
        pyproject_path.write_text(pyproject_content, encoding="utf-8")
        
        cfg = parse_config(Path(self.test_dir))
        self.assertEqual(cfg["ignored_paths"], ["tests/*", "docs/*"])
        self.assertEqual(cfg["public_dirs"], ["api/", "src/public/"])
        self.assertEqual(cfg["severity_overrides"]["Unused Python dependency"], "none")
        self.assertEqual(cfg["severity_overrides"]["Removed public class"], "medium")

if __name__ == "__main__":
    unittest.main()
