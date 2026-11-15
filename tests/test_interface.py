from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InterfaceTests(unittest.TestCase):
    def test_frontend_copy_is_english(self):
        sources=[p for p in (ROOT/"frontend/src").rglob("*") if p.suffix in (".tsx",".ts",".css")]
        sources += [ROOT/"frontend/index.html",ROOT/"frontend/gis-check/index.html"]
        for source in sources:
            with self.subTest(path=source):
                self.assertIsNone(re.search(r"[\u0400-\u04ff]",source.read_text(encoding="utf-8")))

    def test_removed_features_are_not_mounted_or_imported(self):
        app=(ROOT/"frontend/src/App.tsx").read_text(encoding="utf-8")
        mission=(ROOT/"frontend/src/components/MissionControl.tsx").read_text(encoding="utf-8")
        globe=(ROOT/"frontend/src/components/MarsGlobe.tsx").read_text(encoding="utf-8")
        self.assertNotIn("Terrain3D",app)
        self.assertNotIn("adaptiveGlobe",globe)
        for section in ["mc-missions","mc-discover","mc-jezero","mc-demo","mc-traversability","mc-data-note"]:
            self.assertNotIn(section,mission)
        self.assertNotIn("exaggeration",globe)
        self.assertNotIn("oblique",globe)

    def test_report_has_no_disclaimer_section(self):
        report=(ROOT/"frontend/src/components/expeditionReport.ts").read_text(encoding="utf-8")
        self.assertIn('lang="en"',report)
        self.assertNotIn("traversabilityNotice",report)
        self.assertNotIn("route.warnings",report)
        self.assertNotIn('class="notice"',report)

    def test_workspaces_have_no_editorial_chrome(self):
        for relative in ["frontend/src/App.tsx","frontend/src/components/MissionControl.tsx"]:
            source=(ROOT/relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertNotIn("<em>",source)
                self.assertNotIn('className="eyebrow"',source)
                self.assertNotIn('className="mc-kicker"',source)
                self.assertNotIn('className="step"',source)
                self.assertNotIn("mc-planet-facts",source)
        for relative in ["frontend/src/components/mission.css","frontend/src/styles/local-mission.css"]:
            source=(ROOT/relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertNotIn("Georgia",source)
                self.assertNotIn("color-scheme:light",source)


if __name__=="__main__":
    unittest.main()
