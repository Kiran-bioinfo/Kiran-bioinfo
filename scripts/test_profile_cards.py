"""Offline checks: python -m unittest discover -s scripts -p 'test_*.py'."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import render_readme_cards as cards

ROOT = Path(__file__).resolve().parent.parent
NS = {"s": "http://www.w3.org/2000/svg"}


class ProfileCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/contributions.json").read_text(encoding="utf-8"))

    def render(self, function, *args):
        with patch.object(cards, "write") as write:
            function(*args)
        return ET.fromstring(write.call_args.args[1])

    def test_contribution_identity_and_totals(self):
        self.assertEqual(self.data["username"], "Kiran-bioinfo")
        self.assertEqual(self.data["total_contributions"], sum(d["count"] for d in self.data["days"]))
        self.assertEqual(self.data["active_days"], sum(d["count"] > 0 for d in self.data["days"]))
        self.assertEqual(self.data["total_contributions"], sum(m["total"] for m in self.data["monthly"]))

    def test_generated_svgs_and_readme_images(self):
        for path in (ROOT / "cards").glob("*.svg"):
            ET.parse(path)
        for name in ("contrib-heatmap.svg", "stats.svg"):
            ET.parse(ROOT / name)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for image in re.findall(r'(?:src|srcset)="(\./[^"]+)"', readme):
            self.assertTrue((ROOT / image).is_file(), image)
        for name, *_ in cards.REPOS:
            self.assertIn(f'https://github.com/Kiran-bioinfo/{name}', readme)
        self.assertIn('https://www.linkedin.com/in/basanagowda-patil/', readme)
        self.assertNotIn('cards/build.svg', readme)

    def test_active_profile_has_no_original_identity(self):
        paths = [ROOT / "README.md", ROOT / "stats.svg", ROOT / "contrib-heatmap.svg"]
        paths.extend((ROOT / "cards").glob("*.svg"))
        for path in paths:
            text = path.read_text(encoding="utf-8").lower()
            for original in ("avivashishta", "avi vashishta", "12.7m", "27.5k", "engineer at dock"):
                self.assertNotIn(original, text, str(path))

    def test_hero_profile_image_and_reduced_motion(self):
        hero = self.render(cards.hero)
        image = hero.find(".//s:image", NS)
        assert image is not None
        self.assertTrue(image.attrib.get("href", "").startswith("data:image/png;base64,"))
        self.assertEqual(image.attrib.get("preserveAspectRatio"), "xMidYMid slice")
        self.assertFalse(hero.findall('.//s:g[@class="dna-frame"]', NS))
        style = hero.find("s:style", NS)
        assert style is not None and style.text is not None
        css = style.text
        self.assertIn("prefers-reduced-motion", css)
        self.assertNotIn("<script", ET.tostring(hero, encoding="unicode"))

    def test_activity_with_zero_contributions(self):
        data = copy.deepcopy(self.data)
        for month in data["monthly"]:
            month["total"] = 0
        svg = self.render(cards.activity, data)
        bars = svg.findall('.//s:rect[@class="g"]', NS)
        self.assertEqual(len(bars), 12)
        self.assertTrue(all(float(bar.attrib["height"]) == 4 for bar in bars))

    def test_current_month_peak_stays_inside_chart(self):
        data = copy.deepcopy(self.data)
        data["monthly"][-1]["total"] = 100000
        svg = self.render(cards.activity, data)
        for bar in svg.findall('.//s:rect[@class="g"]', NS):
            self.assertGreaterEqual(float(bar.attrib["y"]), 152)
            self.assertLessEqual(float(bar.attrib["height"]), 140)

    def test_zero_and_unavailable_repo_stars(self):
        for stars in (0, None):
            svg = self.render(cards.repo_card, 0, *cards.REPOS[0], stars)
            labels = ["".join(node.itertext()) for node in svg.findall(".//s:text", NS)]
            text = " ".join(labels)
            self.assertEqual("★ 0" in text, stars == 0)
            self.assertNotIn("live", text)

    def test_wrong_account_is_rejected_before_rendering(self):
        env = dict(os.environ, GH_PROFILE_USER="not-the-profile-owner")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/render_readme_cards.py")],
            env=env, capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Fetch contribution data for not-the-profile-owner", result.stderr)
        self.assertNotIn("wrote cards/", result.stdout)


if __name__ == "__main__":
    unittest.main()
