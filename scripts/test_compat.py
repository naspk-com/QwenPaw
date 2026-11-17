"""Regression tests for the fnOS compatibility launcher."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "app/qwenpaw/compat.py"
spec = importlib.util.spec_from_file_location("qwenpaw_fnos_compat", MODULE)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class LegacyEnvironmentTests(unittest.TestCase):
    def test_maps_supported_legacy_values(self):
        env = {"COPAW_LLM_MAX_QPM": "123", "COPAW_UNKNOWN": "value"}
        compat.apply_legacy_environment(env)
        self.assertEqual(env["QWENPAW_LLM_MAX_QPM"], "123")
        self.assertNotIn("QWENPAW_UNKNOWN", env)

    def test_explicit_modern_value_including_empty_wins(self):
        env = {"COPAW_CONFIG_FILE": "old", "QWENPAW_CONFIG_FILE": ""}
        compat.apply_legacy_environment(env)
        self.assertEqual(env["QWENPAW_CONFIG_FILE"], "")

    def test_dotenv_is_data_and_respects_file_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.env"
            second = root / "second.env"
            marker = root / "should-not-exist"
            first.write_text(
                f"COPAW_JOBS_FILE='$(touch {marker})'\n"
                "COPAW_CHATS_FILE=first.json\n",
                encoding="utf-8",
            )
            second.write_text("COPAW_CHATS_FILE=second.json\n", encoding="utf-8")
            env = {}
            compat.apply_legacy_environment(env, (first, second))
            self.assertEqual(env["QWENPAW_CHATS_FILE"], "first.json")
            self.assertIn("$(touch ", env["QWENPAW_JOBS_FILE"])
            self.assertFalse(marker.exists())

    def test_dotenv_modern_value_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("QWENPAW_JOBS_FILE=new.json\n", encoding="utf-8")
            env = {"COPAW_JOBS_FILE": "old.json"}
            compat.apply_legacy_environment(env, (path,))
            self.assertNotIn("QWENPAW_JOBS_FILE", env)


if __name__ == "__main__":
    unittest.main()
