import unittest

from centercross.hotkeys import MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, parse_hotkey


class HotkeyTests(unittest.TestCase):
    def test_keyboard_hotkey_can_have_no_modifier(self):
        parsed = parse_hotkey("F8")
        self.assertEqual(parsed.key, 0x77)
        self.assertEqual(parsed.modifiers, MOD_NOREPEAT)

    def test_mouse_hotkeys_keep_optional_modifiers(self):
        plain = parse_hotkey("Mouse4")
        modified = parse_hotkey("Ctrl+Alt+Mouse5")
        self.assertEqual((plain.mouse_button, plain.modifiers), (4, MOD_NOREPEAT))
        self.assertEqual(modified.mouse_button, 5)
        self.assertEqual(modified.modifiers & (MOD_CONTROL | MOD_ALT), MOD_CONTROL | MOD_ALT)


if __name__ == "__main__":
    unittest.main()
