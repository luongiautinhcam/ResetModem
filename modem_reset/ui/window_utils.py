import logging
import tkinter as tk


def center_window(
    window: tk.Misc,
    width: int,
    height: int,
    parent: tk.Misc | None = None,
) -> None:
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    if parent and parent.winfo_exists():
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    else:
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2

    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))
    try:
        window.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError as error:
        logging.warning("Could not position window: %s", error)
