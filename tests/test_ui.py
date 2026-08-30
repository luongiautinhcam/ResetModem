import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from modem_reset.config import ConfigStore
from modem_reset.constants import APP_USER_MODEL_ID, STATUS_GETTING_IP
from modem_reset.models import ResetRequestResult
from modem_reset.ui.main_window import MainWindow
from main import configure_windows_app_identity


class MainWindowTests(unittest.TestCase):
    def test_main_window_constructs_and_switches_language(self) -> None:
        controller = Mock()
        controller.public_ip = STATUS_GETTING_IP
        controller.drain_events.return_value = []
        controller.logs_snapshot.return_value = ()
        controller.request_reset.return_value = ResetRequestResult.STARTED

        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            try:
                app = MainWindow(
                    root,
                    config_store=ConfigStore(Path(directory) / "config.ini"),
                    controller=controller,
                )
                root.update_idletasks()

                self.assertEqual("Modem Reset Tool v1.0.6", root.title())
                self.assertEqual("Mật khẩu modem:", app.password_label.cget("text"))
                self.assertEqual("Reset Modem", app.restart_button.cget("text"))
                self.assertGreaterEqual(root.winfo_width(), 400)
                self.assertGreaterEqual(root.winfo_height(), 300)

                app.language_var.set("en")
                app._change_language()
                root.update_idletasks()

                self.assertEqual("Modem password:", app.password_label.cget("text"))
                self.assertEqual("Activity history", app.log_frame.cget("text"))
            finally:
                controller.close()
                root.destroy()

    @patch("main.sys.platform", "win32")
    @patch("main.ctypes.windll", create=True)
    def test_windows_app_identity_is_set_before_window_creation(self, windll: Mock) -> None:
        configure_windows_app_identity()

        windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            APP_USER_MODEL_ID
        )


if __name__ == "__main__":
    unittest.main()
