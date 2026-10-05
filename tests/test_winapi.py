import unittest

from centercross.winapi import WindowInfo, match_window


class WindowMatchingTests(unittest.TestCase):
    def test_public_label_does_not_contain_window_title(self):
        item = WindowInfo(1, 2, "private@example.com - Confidential", "msedge.exe")
        self.assertEqual(item.label, "msedge")

    def test_foreground_instance_is_preferred_for_same_application(self):
        first = WindowInfo(10, 2, "First", "example.exe")
        foreground = WindowInfo(20, 2, "Private title", "example.exe")
        self.assertEqual(match_window([first, foreground], "example.exe", preferred_hwnd=20), foreground)


if __name__ == "__main__":
    unittest.main()
