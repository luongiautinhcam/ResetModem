import tempfile
import unittest
from pathlib import Path

from modem_reset.config import AppConfig, ConfigStore


class ConfigStoreTests(unittest.TestCase):
    def test_configuration_round_trip(self) -> None:
        expected = AppConfig(
            language="en",
            password="secret",
            save_password=True,
            log_directory="C:/logs",
            log_interval=60,
            auto_reset_enabled=True,
            auto_reset_interval=120,
            window_x=100,
            window_y=200,
            window_width=640,
            window_height=480,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(Path(directory) / "config.ini")
            store.save(expected)
            actual = store.load()

        self.assertEqual(expected, actual)

    def test_password_is_omitted_when_save_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.ini"
            store = ConfigStore(path)
            store.save(AppConfig(password="secret", save_password=False))
            content = path.read_text(encoding="utf-8")
            actual = store.load()

        self.assertNotIn("secret", content)
        self.assertEqual("", actual.password)
        self.assertFalse(actual.save_password)


if __name__ == "__main__":
    unittest.main()
