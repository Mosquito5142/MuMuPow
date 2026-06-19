import unittest

from mumu_controller import escape_adb_text


class EscapeAdbTextTests(unittest.TestCase):
    def test_plain_text_is_unchanged(self):
        self.assertEqual(escape_adb_text("player@example.com"), "player@example.com")

    def test_space_becomes_percent_s_token(self):
        self.assertEqual(escape_adb_text("hello world"), "hello%sworld")

    def test_shell_metacharacters_are_backslash_escaped(self):
        self.assertEqual(escape_adb_text("P@ss&w(rd)!"), "P@ss\\&w\\(rd\\)\\!")

    def test_quotes_and_dollar_and_backtick_are_escaped(self):
        self.assertEqual(escape_adb_text("a\"b'c$d`e"), "a\\\"b\\'c\\$d\\`e")

    def test_pipe_semicolon_redirect_are_escaped(self):
        self.assertEqual(escape_adb_text("a|b;c<d>e"), "a\\|b\\;c\\<d\\>e")

    def test_backslash_itself_is_escaped(self):
        self.assertEqual(escape_adb_text("a\\b"), "a\\\\b")

    def test_non_string_input_is_coerced(self):
        self.assertEqual(escape_adb_text(12345), "12345")


if __name__ == "__main__":
    unittest.main()
