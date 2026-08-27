import logging
import os
import tkinter as tk
from tkinter import messagebox, ttk

from ..config import AppConfig, ConfigLoadError, ConfigStore
from ..constants import (
    APP_NAME,
    APP_VERSION,
    CONFIG_PATH,
    ICON_PATH,
    ICON_PNG_PATH,
    POLL_INTERVAL_MS,
)
from ..controller import AppController, ControllerEvent
from ..i18n import Translator
from ..log_exporter import LogExporter, LogExportError
from ..models import LogEntry, ResetRequestResult
from .settings_window import SettingsWindow
from .window_utils import center_window


class MainWindow:
    def __init__(
        self,
        root: tk.Tk,
        *,
        config_store: ConfigStore | None = None,
        controller: AppController | None = None,
        log_exporter: LogExporter | None = None,
    ):
        self.root = root
        self.config_store = config_store or ConfigStore()
        self.controller = controller or AppController()
        self.log_exporter = log_exporter or LogExporter()
        self._closed = False
        self._event_timer: str | None = None
        self._auto_export_timer: str | None = None
        self._log_directory_error_shown = False
        self._window_icon: tk.PhotoImage | None = None

        config_error: str | None = None
        try:
            self.config = self.config_store.load()
        except ConfigLoadError as error:
            logging.error("Could not load %s: %s", CONFIG_PATH, error)
            self.config = AppConfig()
            config_error = str(error)

        self.translator = Translator(self.config.language)
        self.language_var = tk.StringVar(value=self.config.language)
        self.password_var = tk.StringVar(value=self.config.password)
        self.save_password_var = tk.BooleanVar(value=self.config.save_password)
        self.auto_reset_interval_var = tk.StringVar(value=str(self.config.auto_reset_interval))
        self.auto_reset_enabled_var = tk.BooleanVar(value=self.config.auto_reset_enabled)
        self.log_directory = self.config.log_directory
        self.log_interval = self.config.log_interval

        self.password_label: ttk.Label
        self.password_entry: ttk.Entry
        self.save_password_check: ttk.Checkbutton
        self.auto_reset_label: ttk.Label
        self.auto_reset_interval_entry: ttk.Entry
        self.auto_reset_enabled_check: ttk.Checkbutton
        self.restart_button: ttk.Button
        self.ip_label: ttk.Label
        self.log_frame: ttk.LabelFrame
        self.tree: ttk.Treeview

        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.resizable(True, True)
        self.root.minsize(400, 300)
        self.root.geometry("450x350")
        self._set_icon()
        self._create_menu()
        self._create_widgets()
        self._position_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.password_var.trace_add("write", self._password_changed)
        self.controller.set_password(self.password_var.get())
        self._configure_auto_reset()
        self.controller.start()
        self._poll_controller()
        self._schedule_auto_export()

        if config_error:
            self.root.after(
                0,
                lambda: messagebox.showwarning(
                    self.text("config_error_title"),
                    self.text("config_error", filename=CONFIG_PATH.name),
                    parent=self.root,
                ),
            )

    def text(self, key: str, **values: object) -> str:
        return self.translator.text(key, **values)

    def update_log_settings(self, directory: str | None, interval: int) -> None:
        self.log_directory = directory
        self.log_interval = max(0, interval)
        self._log_directory_error_shown = False
        self._save_config()
        self._schedule_auto_export()

    def _set_icon(self) -> None:
        try:
            if ICON_PNG_PATH.exists():
                self._window_icon = tk.PhotoImage(file=str(ICON_PNG_PATH))
                self.root.iconphoto(True, self._window_icon)
            else:
                logging.warning("PNG icon file not found: %s", ICON_PNG_PATH)

            if os.name == "nt" and ICON_PATH.exists():
                self.root.iconbitmap(str(ICON_PATH))
            elif os.name == "nt":
                logging.warning("Windows icon file not found: %s", ICON_PATH)
        except (OSError, tk.TclError) as error:
            logging.warning("Could not set application icon: %s", error)

    def _create_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        options_menu = tk.Menu(menu_bar, tearoff=0)
        options_menu.add_command(
            label=self.text("menu_log_settings"),
            command=self._open_settings_window,
        )
        options_menu.add_command(
            label=self.text("menu_about"),
            command=self._show_about,
        )
        language_menu = tk.Menu(options_menu, tearoff=0)
        language_menu.add_radiobutton(
            label=self.text("language_vi"),
            variable=self.language_var,
            value="vi",
            command=self._change_language,
        )
        language_menu.add_radiobutton(
            label=self.text("language_en"),
            variable=self.language_var,
            value="en",
            command=self._change_language,
        )
        options_menu.add_cascade(label=self.text("menu_language"), menu=language_menu)
        options_menu.add_separator()
        options_menu.add_command(label=self.text("menu_exit"), command=self._on_closing)
        menu_bar.add_cascade(label=self.text("menu_options"), menu=options_menu)
        self.root.config(menu=menu_bar)

    def _create_widgets(self) -> None:
        top_frame = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        top_frame.pack(fill="x", side="top")
        top_frame.columnconfigure(3, weight=1)

        self.restart_button = ttk.Button(
            top_frame,
            text=self.text("reset_modem"),
            command=self._manual_reset,
            width=15,
        )
        self.restart_button.grid(
            row=0,
            column=2,
            rowspan=2,
            padx=(10, 0),
            pady=3,
            sticky="w",
            ipady=3,
        )

        self.password_label = ttk.Label(top_frame, text=self.text("password_label"))
        self.password_label.grid(row=0, column=0, sticky="w", padx=(0, 5), pady=3)
        password_frame = ttk.Frame(top_frame)
        password_frame.grid(row=0, column=1, sticky="w")
        self.password_entry = ttk.Entry(
            password_frame,
            textvariable=self.password_var,
            show="*",
            width=15,
        )
        self.password_entry.pack(side="left", padx=(0, 5))
        self.save_password_check = ttk.Checkbutton(
            password_frame,
            text=self.text("save"),
            variable=self.save_password_var,
        )
        self.save_password_check.pack(side="left")

        self.auto_reset_label = ttk.Label(top_frame, text=self.text("auto_reset_label"))
        self.auto_reset_label.grid(row=1, column=0, sticky="w", padx=(0, 5), pady=3)
        reset_frame = ttk.Frame(top_frame)
        reset_frame.grid(row=1, column=1, sticky="w")
        self.auto_reset_interval_entry = ttk.Entry(
            reset_frame,
            textvariable=self.auto_reset_interval_var,
            width=15,
        )
        self.auto_reset_interval_entry.pack(side="left", padx=(0, 5))
        self.auto_reset_enabled_check = ttk.Checkbutton(
            reset_frame,
            text=self.text("enable"),
            variable=self.auto_reset_enabled_var,
            command=self._configure_auto_reset,
        )
        self.auto_reset_enabled_check.pack(side="left")
        self.auto_reset_interval_entry.bind(
            "<Return>",
            lambda _event: self._configure_auto_reset(),
        )
        self.auto_reset_interval_entry.bind(
            "<FocusOut>",
            lambda _event: self._configure_auto_reset(),
        )

        self.ip_label = ttk.Label(top_frame, width=40, anchor="w")
        self.ip_label.grid(row=2, column=0, columnspan=4, pady=5, sticky="w")
        self._update_ip_label()
        ttk.Separator(self.root).pack(fill="x", pady=5, padx=10)

        self.log_frame = ttk.LabelFrame(
            self.root,
            text=self.text("activity_history"),
            padding=5,
        )
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10), side="bottom")
        columns = ("time", "ip", "status")
        self.tree = ttk.Treeview(self.log_frame, columns=columns, show="headings", height=10)
        self.tree.heading("time", text=self.text("time"), anchor="w")
        self.tree.column("time", width=140, anchor="w", stretch=tk.NO)
        self.tree.heading("ip", text=self.text("ip"), anchor="w")
        self.tree.column("ip", width=120, anchor="w", stretch=tk.NO)
        self.tree.heading("status", text=self.text("status"), anchor="w")
        self.tree.column("status", width=250, anchor="w")
        scrollbar = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _position_window(self) -> None:
        width = max(400, self.config.window_width)
        height = max(300, self.config.window_height)
        x = self.config.window_x
        y = self.config.window_y
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        if x is not None and y is not None and 0 <= x < screen_width - 50 and 0 <= y < screen_height - 50:
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        else:
            center_window(self.root, width, height)

    def _password_changed(self, *_args: object) -> None:
        self.controller.set_password(self.password_var.get())

    def _configure_auto_reset(self) -> None:
        try:
            interval = int(self.auto_reset_interval_var.get())
        except ValueError:
            interval = 0
        self.controller.configure_auto_reset(
            self.auto_reset_enabled_var.get(),
            interval,
        )

    def _manual_reset(self) -> None:
        result = self.controller.request_reset(self.password_var.get())
        if result is ResetRequestResult.MISSING_PASSWORD:
            messagebox.showerror(
                self.text("missing_password_title"),
                self.text("missing_password"),
                parent=self.root,
            )
        elif result is ResetRequestResult.ALREADY_RUNNING:
            messagebox.showinfo(
                self.text("reset_in_progress_title"),
                self.text("reset_in_progress"),
                parent=self.root,
            )

    def _poll_controller(self) -> None:
        if self._closed:
            return
        for event in self.controller.drain_events():
            self._handle_controller_event(event)
        self._event_timer = self.root.after(POLL_INTERVAL_MS, self._poll_controller)

    def _handle_controller_event(self, event: ControllerEvent) -> None:
        if event.kind == "ip_changed":
            self._update_ip_label()
        elif event.kind == "logs_changed":
            self._render_logs(event.payload)
        elif event.kind == "reset_state":
            state = tk.DISABLED if event.payload else tk.NORMAL
            self.restart_button.config(state=state)

    def _update_ip_label(self) -> None:
        self.ip_label.config(
            text=self.text(
                "public_ip",
                value=self.translator.status_text(self.controller.public_ip),
            )
        )

    def _render_logs(self, entries: object = None) -> None:
        log_entries = entries if isinstance(entries, tuple) else self.controller.logs_snapshot()
        self.tree.delete(*self.tree.get_children(""))
        for entry in log_entries:
            if not isinstance(entry, LogEntry):
                continue
            self.tree.insert(
                "",
                "end",
                iid=str(entry.entry_id),
                values=(
                    entry.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
                    self.translator.status_text(entry.public_ip),
                    self.translator.status_text(entry.status),
                ),
            )

    def _change_language(self) -> None:
        self.translator.set_language(self.language_var.get())
        self.language_var.set(self.translator.language)
        self._create_menu()
        self.password_label.config(text=self.text("password_label"))
        self.save_password_check.config(text=self.text("save"))
        self.auto_reset_label.config(text=self.text("auto_reset_label"))
        self.auto_reset_enabled_check.config(text=self.text("enable"))
        self.restart_button.config(text=self.text("reset_modem"))
        self.log_frame.config(text=self.text("activity_history"))
        self.tree.heading("time", text=self.text("time"), anchor="w")
        self.tree.heading("ip", text=self.text("ip"), anchor="w")
        self.tree.heading("status", text=self.text("status"), anchor="w")
        self._update_ip_label()
        self._render_logs()
        self._save_config()

    def _open_settings_window(self) -> None:
        SettingsWindow(self)

    def _show_about(self) -> None:
        messagebox.showinfo(
            self.text("about_title"),
            self.text("about_body", app_name=APP_NAME, version=APP_VERSION),
            parent=self.root,
        )

    def _schedule_auto_export(self) -> None:
        if self._auto_export_timer:
            try:
                self.root.after_cancel(self._auto_export_timer)
            except tk.TclError:
                pass
            self._auto_export_timer = None
        if self.log_interval > 0 and self.log_directory and os.path.isdir(self.log_directory):
            self._auto_export_timer = self.root.after(
                self.log_interval * 1000,
                self._perform_auto_export,
            )

    def _perform_auto_export(self) -> None:
        self._auto_export_timer = None
        entries = self.controller.logs_snapshot()
        if not entries:
            self._schedule_auto_export()
            return
        if not self.log_directory or not os.path.isdir(self.log_directory):
            if not self._log_directory_error_shown:
                messagebox.showerror(
                    self.text("export_error_title"),
                    self.text(
                        "invalid_export_directory",
                        directory=self.log_directory or "",
                    ),
                    parent=self.root,
                )
                self._log_directory_error_shown = True
            return

        try:
            target = self.log_exporter.export(
                entries,
                self.log_directory,
                self.text,
                self.translator.status_text,
            )
            logging.info("Exported %d log entries to %s", len(entries), target)
            self.controller.remove_logs({entry.entry_id for entry in entries})
        except LogExportError as error:
            logging.error("Could not export logs: %s", error)
            messagebox.showerror(
                self.text("export_error_title"),
                self.text("write_log_error", path=self.log_directory, error=error),
                parent=self.root,
            )
        finally:
            self._schedule_auto_export()

    def _capture_config(self) -> AppConfig:
        try:
            auto_reset_interval = max(0, int(self.auto_reset_interval_var.get()))
        except ValueError:
            auto_reset_interval = 0

        window_x: int | None = None
        window_y: int | None = None
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            if (
                x + self.root.winfo_width() > 50
                and x < self.root.winfo_screenwidth() - 50
                and y + self.root.winfo_height() > 50
                and y < self.root.winfo_screenheight() - 50
            ):
                window_x, window_y = x, y
        except tk.TclError:
            pass

        return AppConfig(
            language=self.translator.language,
            password=self.password_var.get(),
            save_password=self.save_password_var.get(),
            log_directory=self.log_directory,
            log_interval=self.log_interval,
            auto_reset_enabled=self.auto_reset_enabled_var.get(),
            auto_reset_interval=auto_reset_interval,
            window_x=window_x,
            window_y=window_y,
            window_width=max(400, self.root.winfo_width()),
            window_height=max(300, self.root.winfo_height()),
        )

    def _save_config(self) -> None:
        try:
            self.config_store.save(self._capture_config())
        except OSError as error:
            logging.error("Could not save configuration: %s", error)

    def _on_closing(self) -> None:
        if not messagebox.askyesno(
            self.text("confirm_exit_title"),
            self.text("confirm_exit", app_name=APP_NAME),
            parent=self.root,
        ):
            return
        self._save_config()
        self._closed = True
        self.controller.close()
        if self._event_timer:
            try:
                self.root.after_cancel(self._event_timer)
            except tk.TclError:
                pass
        if self._auto_export_timer:
            try:
                self.root.after_cancel(self._auto_export_timer)
            except tk.TclError:
                pass
        self.root.destroy()
