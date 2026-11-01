"""Guards for the Desktop half (desktop/plugin.js) — stdlib only, no Hermes needed."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import installer  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parents[1]
HALF = ROOT / "desktop" / "plugin.js"
BEGIN = "// BEGIN GENERATED THEMES"


def half_source() -> str:
    return HALF.read_text(encoding="utf-8")


def generated_themes() -> list[dict]:
    """The inlined DesktopTheme array (JSON is valid JS, so this is exact)."""
    match = re.search(rf"{re.escape(BEGIN)}\nconst THEMES = (\[.*?\n\])\n// END GENERATED THEMES",
                      half_source(), re.S)
    if match is None:
        raise AssertionError("desktop/plugin.js is missing its generated THEMES block")
    return json.loads(match.group(1))


def skin_colors(name: str) -> dict[str, str]:
    text = (installer.SKINS / f"{name}.yaml").read_text(encoding="utf-8")
    return {key: value.lower() for key, value in re.findall(r"^  ([a-z_]+): '(#[0-9A-Fa-f]{6})'$", text, re.M)}


class DesktopHalfTest(unittest.TestCase):
    def test_half_ships_the_six_skins_with_their_own_labels(self):
        themes = generated_themes()
        catalog = installer.catalog()
        self.assertEqual([t["name"] for t in themes], [e["skin"] for e in catalog])
        for theme, entry in zip(themes, catalog):
            self.assertEqual(theme["label"], entry["skin"])
            self.assertEqual(theme["description"], entry["description"])
            # the Desktop hard-codes "Hermes skin" for skin-derived entries; this half must not
            self.assertNotEqual(theme["description"], "Hermes skin")

    def test_half_imports_only_the_plugin_sdk(self):
        specifiers = re.findall(r"^\s*import\s+.*?from\s+'([^']+)'", half_source(), re.M)
        self.assertEqual(specifiers, ["@hermes/plugin-sdk"])

    def test_half_palette_matches_the_skins_it_ships(self):
        """Catches a skin edit (or rename) that forgot to regenerate the half."""
        for theme in generated_themes():
            skin = skin_colors(theme["name"])
            colors = theme["colors"]
            for half_key, skin_key in (("background", "background"), ("foreground", "ui_text"),
                                       ("destructive", "ui_error"), ("border", "ui_border"),
                                       ("mutedForeground", "ui_thinking")):
                self.assertEqual(colors[half_key], skin[skin_key],
                                 f"{theme['name']}: {half_key} vs skin {skin_key}")
            self.assertEqual(theme["darkColors"], colors)  # a skin is single-mode

    def test_half_is_a_valid_theme_model(self):
        for theme in generated_themes():
            self.assertTrue(theme["name"] and theme["label"] and theme["description"])
            # the Desktop drops a theme without all three required colour keys
            for key in ("background", "foreground", "primary"):
                self.assertRegex(theme["colors"][key], r"^#[0-9a-f]{6}$")
            for key, value in theme["colors"].items():
                self.assertRegex(value, r"^#[0-9a-f]{6}$", f"{theme['name']}: {key}")

    def test_half_never_shadows_a_desktop_builtin(self):
        builtins = {"nous", "mono", "slate", "daylight", "classic", "ember", "midnight",
                    "cyberpunk", "warm-lightmode", "poseidon", "sisyphus", "charizard", "default"}
        for theme in generated_themes():
            self.assertNotIn(theme["name"].lower(), builtins)
            self.assertTrue(theme["name"].startswith("Gruvbox "), theme["name"])

    def test_half_registers_every_theme_in_the_themes_area(self):
        source = half_source()
        self.assertIn("area: THEMES_AREA", source)
        self.assertIn("ctx.registerMany(", source)
        self.assertIn("id: `gruvbox-theme-${slug(theme.name)}`", source)
        self.assertIn("defaultEnabled: true", source)


if __name__ == "__main__":
    unittest.main()
