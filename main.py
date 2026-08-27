import ctypes
import logging
import sys
import tkinter as tk
from logging.handlers import RotatingFileHandler
from tkinter import messagebox

from modem_reset import APP_NAME, APP_VERSION
from modem_reset.constants import APP_USER_MODEL_ID, DEFAULT_LANGUAGE, LOG_PATH
from modem_reset.i18n import Translator
from modem_reset.ui.main_window import MainWindow


def configure_logging() -> None:
    log_format = (
        "%(asctime)s - %(levelname)-8s - %(threadName)-16s - "
        "%(filename)s:%(lineno)d - %(message)s"
    )
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)

def configure_windows_app_identity() -> None:
    """Gives the process its own taskbar identity before Tk creates a window."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        logging.exception("Could not configure the Windows taskbar identity")


def main() -> None:
    configure_logging()
    logging.info("Starting %s v%s", APP_NAME, APP_VERSION)
    configure_windows_app_identity()
    root: tk.Tk | None = None
    app: MainWindow | None = None
    try:
        root = tk.Tk()
        app = MainWindow(root)
        root.mainloop()
        logging.info("%s exited normally", APP_NAME)
    except Exception as error:
        logging.exception("Fatal application error")
        translator = app.translator if app else Translator(DEFAULT_LANGUAGE)
        try:
            messagebox.showerror(
                translator.text("fatal_error_title"),
                translator.text(
                    "fatal_error",
                    error_type=type(error).__name__,
                    error=error,
                    log_filename=LOG_PATH.name,
                ),
                parent=root,
            )
        except Exception:
            logging.exception("Could not display fatal error dialog")
        raise


if __name__ == "__main__":
    main()
