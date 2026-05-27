import unittest

from autostart import has_stickynotes_signature


class AutoStartTests(unittest.TestCase):
    def test_signature_detects_tagged_launcher(self):
        content = "@echo off\n# StickyNotes_AutoStart\nstart \"\" \"C:/x/StickyNotes_noteonly_fix37.exe\" --autostart\n"
        self.assertTrue(has_stickynotes_signature(content))


if __name__ == "__main__":
    unittest.main()
