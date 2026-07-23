"""tests/test_icons.py — icon-pack presence and reference-rewrite audit."""
import importlib.util
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "display"))

GAME_ICONS = [
    "attack", "chat", "crystal_ball", "treasure", "location", "heal",
    "scroll", "faction", "dragon", "spellbook", "potion", "shield",
    "dagger", "timer", "enemy", "ability", "focus", "helmet", "pack",
    "health", "class_barbarian", "class_bard", "class_cleric",
    "class_druid", "class_fighter", "class_monk", "class_paladin",
    "class_ranger", "class_rogue", "class_sorcerer", "class_warlock",
    "class_wizard", "class_artificer",
]
BRANDING_ICONS = [
    "logo_primary_fullcolor", "app_icon_32", "app_icon_180", "app_icon_192",
]
EXPECTED = GAME_ICONS + BRANDING_ICONS


def _import_app():
    spec = importlib.util.spec_from_file_location(
        "gm_display_app", str(REPO / "display" / "gm-display-app.py"))
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so Flask's get_root_path() finds mod.__file__ via
    # sys.modules instead of falling back to cwd (which breaks template
    # resolution for render_template calls, e.g. GET /).
    sys.modules["gm_display_app"] = mod
    spec.loader.exec_module(mod)
    return mod


class IconStaticServingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _import_app()
        cls.client = cls.mod.app.test_client()

    def test_all_icons_served(self):
        for basename in EXPECTED:
            with self.subTest(basename=basename):
                response = self.client.get(f"/static/icons/{basename}.svg")
                self.assertEqual(response.status_code, 200)
                self.assertIn("image/svg+xml", response.content_type)


class IconReferenceAuditTests(unittest.TestCase):
    FILES = [
        REPO / "display" / "templates" / "index.html",
        REPO / "systems" / "dnd5e" / "ui.json",
        REPO / "systems" / "pf2e" / "ui.json",
        REPO / "systems" / "sf2e" / "ui.json",
    ]

    def test_no_old_icons_prefix(self):
        import re
        for path in self.FILES:
            with self.subTest(path=str(path)):
                content = path.read_text()
                # The old bare prefix "/icons/" must be gone; only the new
                # "/static/icons/" form is allowed.
                self.assertIsNone(re.search(r"(?<!static)/icons/", content))

    def test_no_png_icons(self):
        import re
        for path in self.FILES:
            with self.subTest(path=str(path)):
                content = path.read_text()
                self.assertIsNone(
                    re.search(r"/static/icons/[^\"'` )]*\.png", content))


if __name__ == "__main__":
    unittest.main()
