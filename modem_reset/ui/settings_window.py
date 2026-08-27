import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from .window_utils import center_window

if TYPE_CHECKING:
    from .main_window import MainWindow


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent.root)
        self.parent_app = parent
        self.transient(parent.root)
        self.title(parent.text("settings_title"))
        self.resizable(False, False)
        self.grab_set()

        initial_directory = parent.log_directory or parent.text("directory_not_selected")
        self.log_directory_var = tk.StringVar(value=initial_directory)
        self.log_interval_var = tk.StringVar(value=str(parent.log_interval))

        frame = ttk.Frame(self, padding=10)
        frame.pack(expand=True, fill="both")
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text=parent.text("log_directory")).grid(
            row=0,
            column=0,
            padx=5,
            pady=5,
            sticky="w",
        )
        ttk.Entry(
            frame,
            textvariable=self.log_directory_var,
            state="readonly",
            width=40,
        ).grid(row=1, column=0, padx=5, pady=2, sticky="ew")
        ttk.Button(
            frame,
            text=parent.text("choose"),
            command=self._select_directory,
        ).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(frame, text=parent.text("auto_save_interval")).grid(
            row=2,
            column=0,
            padx=5,
            pady=5,
            sticky="w",
        )
        interval_entry = ttk.Entry(frame, textvariable=self.log_interval_var, width=10)
        interval_entry.grid(row=3, column=0, padx=5, pady=2, sticky="w")
        interval_entry.bind("<Return>", lambda _event: self._save())

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, pady=15, sticky="e")
        ttk.Button(buttons, text=parent.text("save"), command=self._save).pack(
            side="left",
            padx=5,
        )
        ttk.Button(buttons, text=parent.text("cancel"), command=self.destroy).pack(
            side="left",
            padx=5,
        )

        interval_entry.focus()
        center_window(self, 450, 200, parent=parent.root)
        self.wait_window()

    def _select_directory(self) -> None:
        directory = filedialog.askdirectory(
            parent=self,
            title=self.parent_app.text("choose_log_directory"),
            initialdir=self.parent_app.log_directory or os.getcwd(),
        )
        if directory:
            self.log_directory_var.set(directory)

    def _save(self) -> None:
        try:
            interval = int(self.log_interval_var.get())
            if interval < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                self.parent_app.text("input_error_title"),
                self.parent_app.text("invalid_log_interval"),
                parent=self,
            )
            return

        directory = self.log_directory_var.get()
        if directory == self.parent_app.text("directory_not_selected"):
            directory = ""
        if not directory and interval > 0:
            messagebox.showerror(
                self.parent_app.text("missing_info_title"),
                self.parent_app.text("missing_log_directory"),
                parent=self,
            )
            return

        self.parent_app.update_log_settings(directory or None, interval)
        self.destroy()
