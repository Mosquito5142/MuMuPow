import tempfile
import unittest
from pathlib import Path

from script_sets import (
    build_run_set_step,
    expand_steps_with_sets,
    load_script_set,
    safe_set_slug,
    save_script_set,
)


class ScriptSetTests(unittest.TestCase):
    def test_build_run_set_step_uses_named_set(self):
        step = build_run_set_step("login")

        self.assertEqual(step["type"], "run_set")
        self.assertEqual(step["set"], "login")
        self.assertEqual(step["desc"], "Use set: login")

    def test_expand_steps_with_sets_inlines_sets_in_order(self):
        sets = {
            "login": [{"type": "text", "text": "{EMAIL}", "desc": "email"}],
            "ads": [{"type": "sleep", "seconds": 10, "desc": "wait"}],
        }

        expanded = expand_steps_with_sets(
            [
                {"type": "run_set", "set": "login"},
                {"type": "tap", "x": "1", "y": "2", "desc": "middle"},
                {"type": "run_set", "set": "ads"},
            ],
            lambda name: sets[name],
        )

        self.assertEqual([step["type"] for step in expanded], ["text", "tap", "sleep"])
        self.assertEqual(expanded[0]["text"], "{EMAIL}")
        self.assertEqual(expanded[2]["seconds"], 10)

    def test_expand_steps_with_sets_supports_nested_sets(self):
        sets = {
            "login_then_ads": [
                {"type": "run_set", "set": "login"},
                {"type": "run_set", "set": "ads"},
            ],
            "login": [{"type": "text", "text": "{PASSWORD}"}],
            "ads": [{"type": "keyevent", "code": "4"}],
        }

        expanded = expand_steps_with_sets(
            [{"type": "run_set", "set": "login_then_ads"}],
            lambda name: sets[name],
        )

        self.assertEqual([step["type"] for step in expanded], ["text", "keyevent"])

    def test_expand_steps_with_sets_rejects_cycles(self):
        sets = {
            "a": [{"type": "run_set", "set": "b"}],
            "b": [{"type": "run_set", "set": "a"}],
        }

        with self.assertRaisesRegex(ValueError, "cycle"):
            expand_steps_with_sets([{"type": "run_set", "set": "a"}], lambda name: sets[name])

    def test_safe_set_slug_removes_path_separators(self):
        self.assertEqual(safe_set_slug("../login set"), "login_set")
        self.assertEqual(safe_set_slug(""), "set")

    def test_save_and_load_script_set_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "login.json"
            steps = [{"type": "sleep", "seconds": 10, "desc": "wait login"}]

            save_script_set(path, "login", steps)
            data = load_script_set(path)

        self.assertEqual(data["name"], "login")
        self.assertEqual(data["steps"], steps)


if __name__ == "__main__":
    unittest.main()
