"""Installer tests — stdlib only: python3 -m unittest discover -s tests"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import installer  # noqa: E402  (path set above)

# Names are read from the shipped index so a rename never means editing tests.
FIRST = installer.catalog()[0]["skin"]
LAST = installer.catalog()[-1]["skin"]
COUNT = len(installer.catalog())


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def skins_dir(self) -> Path:
        return self.home / "skins"

    def receipt(self) -> dict:
        return json.loads((self.home / "theme-packages" / "hermes-gruvbox.json").read_text())

    def skin_file(self, name: str) -> Path:
        return self.skins_dir() / f"{name}.yaml"

    def write(self, name: str, marker: str) -> Path:
        """Stand in for a user's own file under a pack name."""
        self.skins_dir().mkdir(parents=True, exist_ok=True)
        path = self.skin_file(name)
        path.write_text(f'name: "{name}"\ndescription: {marker}\ncolors: {{}}\n', encoding="utf-8")
        return path

    def test_pack_ships_six_named_variants(self):
        entries = installer.catalog()
        self.assertEqual(COUNT, 6)
        self.assertEqual({e["mode"] for e in entries}, {"dark", "light"})
        # every skin is an explicit contrast cut, display-cased, of one of two families
        self.assertEqual({e["skin"].rsplit(" ", 1)[-1] for e in entries},
                         {"Medium", "Hard", "Soft"})
        self.assertTrue(all(e["skin"].startswith("Gruvbox ") for e in entries))
        self.assertEqual({e["skin"].split()[1] for e in entries}, {"Dark", "Light"})
        for entry in entries:
            text = (installer.SKINS / f"{entry['skin']}.yaml").read_text(encoding="utf-8")
            self.assertIn(f'name: {entry["skin"]}\n', text)
            self.assertIn("background:", text)
            self.assertIn(entry["description"], text)
            # every colour is a long-form hex, as the skin engine requires
            for line in text.splitlines():
                if line.startswith("  ") and ":" in line:
                    value = line.split(":", 1)[1].strip().strip("'")
                    self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$", f"{entry['skin']}: {line}")

    def test_descriptions_name_family_contrast_and_signature_colour(self):
        by_slug = {e["slug"]: e for e in installer.catalog()}
        for entry in by_slug.values():
            description = entry["description"]
            # a family, a contrast level and a #rrggbb or a named signatage colour
            self.assertIn(entry["skin"].split()[0], description)
            self.assertRegex(description, r"(medium|hard|soft) contrast")
            self.assertRegex(description, r"#[0-9a-f]{6}|yellow|orange", description)
        self.assertIn("#282828", by_slug["dark-medium"]["description"])
        self.assertIn("yellow", by_slug["dark-medium"]["description"])
        self.assertEqual(by_slug["dark-medium"]["label"], "Gruvbox Dark Medium")

    def test_install_copies_every_skin_and_records_a_receipt(self):
        changed, skipped = installer.install(self.home)
        self.assertEqual(skipped, [])
        self.assertEqual(sorted(changed), sorted(e["skin"] for e in installer.catalog()))
        for entry in installer.catalog():
            self.assertTrue(self.skin_file(entry["skin"]).is_file(), entry["skin"])
        self.assertEqual(len(self.receipt()["skins"]), COUNT)
        # only skins and the receipt are written: never config.yaml
        self.assertFalse((self.home / "config.yaml").exists())

    def test_install_is_idempotent(self):
        installer.install(self.home)
        changed, skipped = installer.install(self.home)
        self.assertEqual((changed, skipped), ([], []))
        self.assertEqual(installer.installed(self.home), [e["skin"] for e in installer.catalog()])

    def test_edited_skin_is_never_clobbered(self):
        installer.install(self.home)
        mine = self.skin_file(FIRST)
        mine.write_text("name: mine\ndescription: mine\ncolors: {}\n", encoding="utf-8")
        changed, skipped = installer.install(self.home)
        self.assertEqual(skipped, [FIRST])
        self.assertIn("mine", mine.read_text(encoding="utf-8"))
        self.assertNotIn(FIRST, installer.uninstall(self.home)[0])

    def test_foreign_skin_of_the_same_name_is_kept(self):
        theirs = self.write(FIRST, "theirs")
        _, skipped = installer.install(self.home)
        self.assertEqual(skipped, [FIRST])
        self.assertIn("theirs", theirs.read_text(encoding="utf-8"))

    def test_install_with_replace_backs_up_and_restores(self):
        theirs = self.write(FIRST, "theirs")
        installer.install(self.home, names=[FIRST], replace=True)
        self.assertIn("#282828", theirs.read_text(encoding="utf-8"))
        removed, kept = installer.uninstall(self.home)
        self.assertEqual((removed, kept), ([FIRST], []))
        self.assertIn("theirs", theirs.read_text(encoding="utf-8"))

    def test_uninstall_removes_only_managed_skins(self):
        installer.install(self.home)
        keep = self.write(LAST, "edited")
        removed, kept = installer.uninstall(self.home)
        self.assertEqual(kept, [LAST])
        self.assertEqual(len(removed), COUNT - 1)
        self.assertFalse(self.skin_file(FIRST).exists())
        self.assertTrue(keep.exists())
        self.assertEqual(installer.installed(self.home), [LAST])

    def test_uninstall_is_remembered(self):
        installer.install(self.home)
        installer.uninstall(self.home)
        changed, skipped = installer.install(self.home)  # what register() does on load
        self.assertEqual(changed, [])
        self.assertEqual(len(skipped), COUNT)
        self.assertFalse(self.skin_file(FIRST).exists())
        installer.set_disabled(self.home, False)
        changed, _ = installer.install(self.home)
        self.assertEqual(len(changed), COUNT)

    def test_rename_retires_the_previous_names(self):
        """A skin this version no longer ships is removed, once, without a stale file."""
        installer.install(self.home)
        state = installer.load_receipt(self.home)
        legacy = self.write("gruvbox-dark", "installed by the previous version")
        state["skins"]["gruvbox-dark"] = {
            "sha256": installer.digest(legacy.read_bytes()), "previous": None}
        installer.save_receipt(self.home, state)

        installer.install(self.home)  # what register() does on the next load
        self.assertFalse(legacy.exists())
        self.assertNotIn("gruvbox-dark", installer.load_receipt(self.home)["skins"])
        self.assertEqual(len(installer.installed(self.home)), COUNT)
        # idempotent: nothing left to retire
        self.assertEqual(installer.retire(self.home, installer.load_receipt(self.home)), [])

    def test_rename_retires_only_files_it_still_owns(self):
        installer.install(self.home)
        state = installer.load_receipt(self.home)
        legacy = self.write("gruvbox-dark", "edited by the user")
        state["skins"]["gruvbox-dark"] = {"sha256": "not-the-current-digest", "previous": None}
        installer.save_receipt(self.home, state)

        installer.install(self.home)
        self.assertTrue(legacy.exists())
        self.assertIn("edited by the user", legacy.read_text(encoding="utf-8"))
        self.assertNotIn("gruvbox-dark", installer.load_receipt(self.home)["skins"])

    def test_receipt_never_escapes_a_users_own_unrelated_file(self):
        installer.install(self.home)
        state = installer.load_receipt(self.home)
        state["skins"]["../escaped"] = {"sha256": "x", "previous": None}
        installer.save_receipt(self.home, state)
        installer.install(self.home)  # retire path must not touch it either
        removed, kept = installer.uninstall(self.home)
        self.assertNotIn("../escaped", removed + kept)
        self.assertNotIn("../escaped", installer.load_receipt(self.home)["skins"])
        self.assertFalse((self.home.parent / "escaped").exists())
        self.assertEqual(len(removed), COUNT)


if __name__ == "__main__":
    unittest.main()
