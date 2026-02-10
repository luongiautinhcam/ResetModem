import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
# import requests.packages.urllib3.exceptions # Removed - Not needed, use requests.exceptions
import base64
import threading
import time
import os
import configparser
from datetime import datetime
import logging
import re # For parsing geometry

# --- Constants ---
APP_NAME = "Modem Reset Tool"
APP_VERSION = "1.2.3" # Incremented version for syntax fix
CONFIG_FILE = 'config.ini'
MODEM_IP = 'http://192.168.0.1'
LOGIN_URL = f'{MODEM_IP}/reqproc/proc_post'
IP_CHECK_INTERVAL_SECONDS = 10
LOG_UPDATE_INTERVAL_SECONDS = 5
DEFAULT_LOG_INTERVAL = 0
DEFAULT_AUTO_RESET_INTERVAL = 0
ICON_PATH = r"C:\Projects\ResetModem\icons\app_icon.ico" # Adjust if needed

# Network Timeouts & Delays
REQUESTS_TIMEOUT_S = 10
IP_FETCH_TIMEOUT_S = 5
STATUS_RESET_DELAY_MS = 5000
REBOOT_STATUS_RESET_DELAY_MS = 15000

# Modem API Constants
MODEM_LOGIN_SUCCESS_STR = '"result":"0"'
MODEM_LOGIN_FAILURE_STR = '"result":"1"'
MODEM_REBOOT_COMMAND = {'goformId': 'REBOOT_DEVICE'}
MODEM_LOGIN_COMMAND_ID = 'LOGIN'

# Configuration Sections/Keys
CONFIG_SECTION_WINDOW = 'WINDOW'
CONFIG_KEY_POS_X = 'pos_x'
CONFIG_KEY_POS_Y = 'pos_y'
CONFIG_SECTION_CREDS = 'CREDENTIALS'
CONFIG_KEY_PASSWORD = 'password'
CONFIG_SECTION_LOGGING = 'LOGGING'
CONFIG_KEY_LOG_DIR = 'log_directory'
CONFIG_KEY_LOG_INTERVAL = 'log_interval'
CONFIG_SECTION_AUTO_RESET = 'AUTO_RESET'
CONFIG_KEY_AUTO_RESET_ENABLED = 'enabled'
CONFIG_KEY_AUTO_RESET_INTERVAL = 'interval_seconds'

# Status Messages
STATUS_NORMAL = "Hoạt động bình thường"
STATUS_CHECKING = "Đang kiểm tra kết nối..."
STATUS_DISCONNECTED = "Mất kết nối Internet"
STATUS_GETTING_IP = "Đang lấy IP..."
STATUS_IP_TIMEOUT = "Lỗi Timeout (IP)"
STATUS_IP_UNKNOWN = "Không xác định (IP)"
STATUS_RESET_MANUAL_START = "Reset Thủ công Bắt đầu"
STATUS_RESET_AUTO_START = "Reset Tự động Bắt đầu (chu kỳ {}s)"
STATUS_RESET_END_UNKNOWN = "Reset Kết thúc (Không rõ KQ)"
STATUS_LOGIN_ATTEMPT = "Đang đăng nhập modem..."
STATUS_LOGIN_FAILED = "Sai mật khẩu modem"
STATUS_LOGIN_UNKNOWN_ERROR = "Lỗi đăng nhập không xác định"
STATUS_REBOOT_COMMAND_SENT = "Đang gửi lệnh reset..."
STATUS_REBOOTING = "Reset modem (đang khởi động lại)"
STATUS_REBOOT_CMD_ERROR = "Lỗi gửi lệnh reset: {}"
STATUS_MODEM_TIMEOUT = "Lỗi: Modem không phản hồi (timeout)"
STATUS_MODEM_CONNECTION_ERROR = "Lỗi: Không kết nối được tới modem"
STATUS_REQUEST_ERROR = "Lỗi kết nối mạng: {}"
STATUS_UNKNOWN_ERROR = "Lỗi không xác định: {}"

# GUI Log Messages
LOG_ERR_CONN_ABORTED = "Connection aborted by remote host"
LOG_ERR_CONN_REFUSED = "Connection refused by modem"
LOG_ERR_CONN_TIMEOUT = "Connection timed out"
LOG_ERR_GENERIC_NETWORK = "Lỗi mạng chung"

# --- Helper Function for Centering Windows ---
def center_window(window: tk.Misc, width: int, height: int, parent: tk.Misc = None):
    """Centers a Tkinter window on the screen or relative to a parent."""
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    parent_x, parent_y = 0, 0

    if parent and parent.winfo_exists():
        parent_geo = parent.winfo_geometry()
        try:
            match = re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", parent_geo)
            if match:
                parent_w, parent_h, parent_x, parent_y = map(int, match.groups())
                x = parent_x + (parent_w // 2) - (width // 2)
                y = parent_y + (parent_h // 2) - (height // 2)
            else:
                logging.warning(f"Could not parse parent geometry: {parent_geo}. Centering on screen.")
                x = (screen_width // 2) - (width // 2)
                y = (screen_height // 2) - (height // 2)
        except Exception as e:
             logging.error(f"Error calculating relative center: {e}. Centering on screen.")
             x = (screen_width // 2) - (width // 2)
             y = (screen_height // 2) - (height // 2)
    else:
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)

    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))
    window.geometry(f'{width}x{height}+{x}+{y}')


# --- Settings Window ---
class SettingsWindow(tk.Toplevel):
    """A Toplevel window for configuring log file export settings."""
    def __init__(self, parent_app: 'ModemResetApp'):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.transient(parent_app.root)
        self.title("Cài đặt Lưu Log")
        self.resizable(False, False)
        self.grab_set()
        settings_width = 450
        settings_height = 200

        initial_dir = parent_app.log_directory or "Chưa chọn thư mục"
        initial_interval = str(parent_app.log_interval)
        self.log_dir_var = tk.StringVar(value=initial_dir)
        self.log_interval_var = tk.StringVar(value=initial_interval)

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        ttk.Label(main_frame, text="Thư mục lưu log:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        dir_entry = ttk.Entry(main_frame, textvariable=self.log_dir_var, state="readonly", width=40)
        dir_entry.grid(row=1, column=0, padx=5, pady=2, sticky="ew")
        dir_button = ttk.Button(main_frame, text="Chọn...", command=self._select_directory)
        dir_button.grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(main_frame, text="Tự động lưu file mỗi (giây, 0 = tắt):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        interval_entry = ttk.Entry(main_frame, textvariable=self.log_interval_var, width=10)
        interval_entry.grid(row=3, column=0, padx=5, pady=2, sticky="w")
        interval_entry.bind("<Return>", lambda event: self._save_settings())

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=15, sticky="e")
        save_button = ttk.Button(button_frame, text="Lưu", command=self._save_settings)
        save_button.pack(side="left", padx=5)
        cancel_button = ttk.Button(button_frame, text="Hủy", command=self.destroy)
        cancel_button.pack(side="left", padx=5)

        interval_entry.focus()
        center_window(self, settings_width, settings_height, parent=parent_app.root)
        self.wait_window()

    def _select_directory(self):
        initial_dir = self.parent_app.log_directory or os.getcwd()
        directory = filedialog.askdirectory(parent=self, title="Chọn thư mục để lưu file log", initialdir=initial_dir)
        if directory:
            self.log_dir_var.set(directory)

    def _save_settings(self):
        try:
            interval = int(self.log_interval_var.get())
            if interval < 0:
                raise ValueError("Interval cannot be negative")
        except ValueError:
            messagebox.showerror("Lỗi Đầu vào", "Thời gian tự động lưu phải là số nguyên không âm.", parent=self)
            return
        directory = self.log_dir_var.get()
        if directory == "Chưa chọn thư mục":
            directory = None
        if directory is None and interval > 0:
            messagebox.showerror("Thiếu Thông tin", "Vui lòng chọn thư mục nếu bật tự động lưu.", parent=self)
            return
        self.parent_app.update_log_settings(directory, interval)
        self.destroy()


# --- Main Application ---
class ModemResetApp:
    """Main application class for the Modem Reset Tool."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.app_width = 450
        self.app_height = 350
        self.root.resizable(True, True)
        self.root.geometry(f"{self.app_width}x{self.app_height}")

        self.config = configparser.ConfigParser()
        self.last_pos_x: int | None = None
        self.last_pos_y: int | None = None

        self.password_var = tk.StringVar()
        self.save_password_var = tk.BooleanVar()
        self.auto_reset_interval_var = tk.StringVar(value=str(DEFAULT_AUTO_RESET_INTERVAL))
        self.auto_reset_enabled_var = tk.BooleanVar(value=False)

        self.public_ip: str = STATUS_GETTING_IP
        self.is_connected: bool | None = None
        self.last_action: str | None = None
        self.log_directory: str | None = None
        self.log_interval: int = DEFAULT_LOG_INTERVAL

        self.is_resetting: bool = False
        self.lock = threading.Lock()

        self.auto_export_timer: str | None = None
        self.auto_reset_timer: str | None = None
        self.status_reset_timer: str | None = None

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': MODEM_IP + '/index.html',
            'X-Requested-With': 'XMLHttpRequest',
            'X-Ki-Saas-Ajax-Request': 'Ajax_Request', # Specific header?
            'User-Agent': 'Mozilla/5.0'
        })

        self.tree: ttk.Treeview | None = None
        self.ip_label: ttk.Label | None = None
        self.restart_btn: ttk.Button | None = None
        self.auto_reset_interval_entry: ttk.Entry | None = None
        self.auto_reset_enabled_chk: ttk.Checkbutton | None = None
        self.password_entry: ttk.Entry | None = None
        self.save_password_chk: ttk.Checkbutton | None = None

        self._set_icon()
        self._create_menu()
        self._create_widgets()
        self._load_config()
        self._position_window()
        self._start_background_tasks()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # --- Initialization & UI Creation Methods ---
    def _set_icon(self):
        try:
            if os.path.exists(ICON_PATH):
                self.root.iconbitmap(ICON_PATH)
            else:
                logging.warning(f"Icon file not found: {ICON_PATH}")
        except Exception as e: # Catch potential errors during icon setting
            logging.warning(f"Could not set icon: {e}")

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Cài đặt Log...", command=self._open_settings_window)
        options_menu.add_command(label="Thông tin...", command=self._show_about_info)
        options_menu.add_separator()
        options_menu.add_command(label="Thoát", command=self._on_closing)
        menubar.add_cascade(label="Tùy chọn", menu=options_menu)
        self.root.config(menu=menubar)

    def _create_widgets(self):
        top_frame = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        top_frame.pack(fill='x')
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="Mật khẩu modem:").grid(row=0, column=0, sticky='w', padx=(0, 5), pady=3)
        pw_frame = ttk.Frame(top_frame)
        pw_frame.grid(row=0, column=1, columnspan=2, sticky='w')
        self.password_entry = ttk.Entry(pw_frame, textvariable=self.password_var, show="*", width=15)
        self.password_entry.pack(side='left', padx=(0, 5))
        self.save_password_chk = ttk.Checkbutton(pw_frame, text="Lưu", variable=self.save_password_var)
        self.save_password_chk.pack(side='left')

        ttk.Label(top_frame, text="Tự động reset (giây):").grid(row=1, column=0, sticky='w', padx=(0, 5), pady=3)
        reset_frame = ttk.Frame(top_frame)
        reset_frame.grid(row=1, column=1, columnspan=2, sticky='w')
        self.auto_reset_interval_entry = ttk.Entry(reset_frame, textvariable=self.auto_reset_interval_var, width=15)
        self.auto_reset_interval_entry.pack(side='left', padx=(0, 5))
        self.auto_reset_enabled_chk = ttk.Checkbutton(reset_frame, text="Bật", variable=self.auto_reset_enabled_var, command=self._schedule_auto_reset)
        self.auto_reset_enabled_chk.pack(side='left')
        self.auto_reset_interval_entry.bind("<Return>", lambda e: self._schedule_auto_reset())
        self.auto_reset_interval_entry.bind("<FocusOut>", lambda e: self._schedule_auto_reset())

        self.restart_btn = ttk.Button(top_frame, text="Reset Modem Thủ Công", command=self._manual_reset_request, width=25)
        self.restart_btn.grid(row=2, column=1, pady=10, ipady=3, sticky='w', padx=(0, 5))

        self.ip_label = ttk.Label(top_frame, text=f"IP Public: {self.public_ip}", width=40, anchor='w')
        self.ip_label.grid(row=3, column=0, columnspan=3, pady=5, sticky='w')

        ttk.Separator(self.root).pack(fill='x', pady=5, padx=10)

        log_frame = ttk.LabelFrame(self.root, text="Lịch sử hoạt động", padding=5)
        log_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        columns = ("time", "ip", "status")
        self.tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=10)
        self.tree.heading("time", text="Thời gian", anchor='w')
        self.tree.column("time", width=140, anchor='w', stretch=tk.NO)
        self.tree.heading("ip", text="IP", anchor='w')
        self.tree.column("ip", width=120, anchor='w', stretch=tk.NO)
        self.tree.heading("status", text="Trạng thái", anchor='w')
        self.tree.column("status", width=250, anchor='w') # Let status width adjust

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

    def _position_window(self):
        if self.last_pos_x is not None and self.last_pos_y is not None:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            if 0 <= self.last_pos_x < (screen_w - 50) and 0 <= self.last_pos_y < (screen_h - 50):
                 logging.info(f"Restoring window position to +{self.last_pos_x}+{self.last_pos_y}")
                 self.root.geometry(f"+{self.last_pos_x}+{self.last_pos_y}")
            else:
                 logging.warning("Saved position off-screen, centering.")
                 center_window(self.root, self.app_width, self.app_height)
        else:
            logging.info("No saved position, centering.")
            center_window(self.root, self.app_width, self.app_height)

    def _start_background_tasks(self):
        self._schedule_auto_export()
        self._schedule_auto_reset()
        threading.Thread(target=self._update_ip_now_task, daemon=True, name="InitialIPFetch").start()
        threading.Thread(target=self._ip_update_loop, daemon=True, name="IPUpdateLoop").start()
        threading.Thread(target=self._log_update_loop, daemon=True, name="LogUpdateLoop").start()

    # --- Configuration Methods ---
    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            logging.info(f"Config file '{CONFIG_FILE}' not found.")
            return
        try:
            self.config.read(CONFIG_FILE)
            if self.config.has_section(CONFIG_SECTION_CREDS):
                saved_pw = self.config.get(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, fallback='')
                if saved_pw:
                    self.password_var.set(saved_pw)
                    self.save_password_var.set(True)
            if self.config.has_section(CONFIG_SECTION_LOGGING):
                self.log_directory = self.config.get(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, fallback=None) or None
                self.log_interval = self.config.getint(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, fallback=DEFAULT_LOG_INTERVAL)
                self.log_interval = max(0, self.log_interval) # Ensure non-negative
            if self.config.has_section(CONFIG_SECTION_AUTO_RESET):
                 enabled = self.config.getboolean(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_ENABLED, fallback=False)
                 interval = self.config.getint(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, fallback=DEFAULT_AUTO_RESET_INTERVAL)
                 interval = max(0, interval) # Ensure non-negative
                 self.auto_reset_enabled_var.set(enabled)
                 self.auto_reset_interval_var.set(str(interval))
            if self.config.has_section(CONFIG_SECTION_WINDOW):
                self.last_pos_x = self.config.getint(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, fallback=None)
                self.last_pos_y = self.config.getint(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, fallback=None)
        except (configparser.Error, ValueError, TypeError) as e:
            logging.error(f"Error reading config: {e}")
            messagebox.showwarning("Lỗi Config", f"Lỗi đọc '{CONFIG_FILE}'.", parent=self.root)
            self._reset_to_default_config_values()

    def _reset_to_default_config_values(self):
        self.password_var.set("")
        self.save_password_var.set(False)
        self.log_directory = None
        self.log_interval = DEFAULT_LOG_INTERVAL
        self.auto_reset_enabled_var.set(False)
        self.auto_reset_interval_var.set(str(DEFAULT_AUTO_RESET_INTERVAL))
        self.last_pos_x = None
        self.last_pos_y = None

    def _save_config(self):
        logging.info("Saving configuration...")
        try:
            for section in [CONFIG_SECTION_CREDS, CONFIG_SECTION_LOGGING, CONFIG_SECTION_WINDOW, CONFIG_SECTION_AUTO_RESET]:
                if not self.config.has_section(section):
                    self.config.add_section(section)
            if self.save_password_var.get():
                self.config.set(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, self.password_var.get())
            elif self.config.has_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD):
                self.config.remove_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD)
            self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, str(self.log_interval))
            self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, self.log_directory or '')
            self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_ENABLED, str(self.auto_reset_enabled_var.get()))
            try:
                interval_to_save = int(self.auto_reset_interval_var.get())
                interval_to_save = max(0, interval_to_save)
            except ValueError:
                interval_to_save = DEFAULT_AUTO_RESET_INTERVAL
            self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, str(interval_to_save))
            current_x, current_y = self._get_current_window_position()
            if current_x is not None and current_y is not None:
                self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, str(current_x))
                self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, str(current_y))
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            logging.info("Configuration saved.")
        except (configparser.Error, IOError, OSError) as e:
            logging.error(f"Error writing config: {e}")

    def _get_current_window_position(self) -> tuple[int | None, int | None]:
        try:
            if self.root and self.root.winfo_exists():
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                screen_w = self.root.winfo_screenwidth()
                screen_h = self.root.winfo_screenheight()
                if (-50 < x < screen_w) and (-50 < y < screen_h): # Allow slightly off-screen
                    return x, y
                else:
                    logging.warning(f"Window pos {x},{y} off-screen.")
                    return None, None
            return None, None
        except Exception as e:
            logging.error(f"Error getting window pos: {e}")
            return None, None

    # --- Action Methods & Event Handlers ---
    def _on_closing(self):
        if messagebox.askyesno("Xác nhận thoát", f"Thoát {APP_NAME}?", parent=self.root):
            logging.info("Closing application...")
            self._cancel_all_timers()
            self._save_config()
            if self.root and self.root.winfo_exists():
                try:
                    self.root.destroy()
                except tk.TclError as e:
                    logging.warning(f"Error during destroy: {e}")
        else:
            logging.info("Close cancelled.")

    def _show_about_info(self):
        info = f"{APP_NAME}\nPhiên bản: {APP_VERSION}\n\nChức năng:\n- Theo dõi IP.\n- Reset modem Viettel.\n- Lưu log.\n- Tự động reset.\n- Lưu cài đặt."
        messagebox.showinfo("Thông tin", info, parent=self.root)

    def _open_settings_window(self):
        SettingsWindow(self)

    def update_log_settings(self, directory: str | None, interval: int):
        self.log_directory = directory
        self.log_interval = interval
        logging.info(f"Log settings: Dir='{self.log_directory}', Interval={self.log_interval}s")
        self._schedule_auto_export()

    def _manual_reset_request(self):
        self._perform_reset(is_auto=False)

    # --- Background Task Scheduling & Execution ---
    def _schedule_auto_export(self):
        self._cancel_timer(self.auto_export_timer)
        self.auto_export_timer = None
        if self.log_interval > 0 and self.log_directory:
            if not os.path.isdir(self.log_directory):
                logging.warning(f"Log directory invalid. Disabling auto-export.")
                return
            logging.info(f"Scheduling auto log export every {self.log_interval} seconds.")
            delay_ms = self.log_interval * 1000
            self.auto_export_timer = self._safe_after(delay_ms, self._perform_auto_export)
        elif self.log_interval <= 0:
            logging.info("Auto log export disabled (interval <= 0).")
        elif not self.log_directory:
            logging.info("Auto log export disabled (no directory).")

    def _perform_auto_export(self):
        self.auto_export_timer = None
        log_items = []
        try:
            if self.root and self.root.winfo_exists() and self.tree and self.tree.winfo_exists():
                log_items = self.tree.get_children('')
            else:
                logging.warning("Auto export cancelled: GUI gone.")
                return
        except tk.TclError:
            logging.warning("Auto export cancelled: Treeview access error.")
            return

        if not log_items:
            logging.info("No logs to export.")
            self._schedule_auto_export() # Reschedule even if empty
            return

        if not self.log_directory or not os.path.isdir(self.log_directory):
             # Show error once logic
             if not hasattr(self, "_log_dir_error_shown") or not self._log_dir_error_shown:
                 messagebox.showerror("Lỗi Xuất Log", f"Thư mục log '{self.log_directory or ''}' không hợp lệ.", parent=self.root if self.root.winfo_exists() else None)
                 self._log_dir_error_shown = True
             logging.error(f"Auto log export failed: Directory invalid.")
             self.log_interval = 0 # Disable until fixed
             return
        self._log_dir_error_shown = False # Reset flag if dir valid now

        log_data = []
        try:
             if self.tree and self.tree.winfo_exists():
                  for item_id in log_items:
                      try:
                          values = self.tree.item(item_id, 'values')
                          if values: # Ensure values exist before joining
                              log_data.append("\t".join(map(str, values)))
                      except tk.TclError:
                          continue # Skip item if error
        except tk.TclError:
             logging.error("Auto export: Error accessing Treeview items.")
             self._schedule_auto_export() # Try again later
             return

        if not log_data:
            logging.info("No valid log data for auto export.")
            self._schedule_auto_export()
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"logs-{timestamp}.txt"
        full_path = os.path.join(self.log_directory, filename)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write("Thời gian\tIP\tTrạng thái\n")
                f.write("="*50 + "\n")
                f.write("\n".join(log_data))
            logging.info(f"Auto-exported logs to: {full_path}")
            if self.tree and self.tree.winfo_exists():
                try:
                    self.tree.delete(*log_items)
                except tk.TclError:
                    logging.warning("Could not clear Treeview after export.")
        except (IOError, OSError, tk.TclError) as e:
            messagebox.showerror("Lỗi Xuất Log", f"Không thể ghi file:\n{full_path}\nLỗi: {e}", parent=self.root if self.root.winfo_exists() else None)
            logging.error(f"Auto log export failed: {e}")
        except Exception as e:
            messagebox.showerror("Lỗi Xuất Log", f"Lỗi không xác định:\n{e}", parent=self.root if self.root.winfo_exists() else None)
            logging.exception("Unexpected error during auto log export:")
        finally:
            if self.log_interval > 0 and self.log_directory and os.path.isdir(self.log_directory):
                 self._schedule_auto_export()

    def _schedule_auto_reset(self):
        self._cancel_timer(self.auto_reset_timer)
        self.auto_reset_timer = None
        is_enabled = self.auto_reset_enabled_var.get()
        interval_str = self.auto_reset_interval_var.get()
        if is_enabled:
            try:
                interval_sec = int(interval_str)
                if interval_sec <= 0:
                    logging.warning("Auto reset interval must be positive.")
                    return
            except ValueError:
                logging.warning(f"Invalid auto reset interval '{interval_str}'.")
                return
            logging.info(f"Scheduling auto reset every {interval_sec} seconds.")
            self.auto_reset_timer = self._safe_after(interval_sec * 1000, self._auto_reset_trigger)
        else:
            logging.info("Auto reset disabled.")

    def _auto_reset_trigger(self):
        self.auto_reset_timer = None # Timer fired
        if not self.root or not self.root.winfo_exists():
            logging.info("Auto reset cancelled: GUI gone.")
            return
        # Re-check conditions before executing
        is_enabled = self.auto_reset_enabled_var.get()
        interval_sec = 0
        try:
            interval_sec = int(self.auto_reset_interval_var.get())
            is_enabled = is_enabled and (interval_sec > 0)
        except ValueError:
            is_enabled = False
        if not is_enabled:
            logging.info("Auto reset cancelled: Disabled or invalid interval before exec.")
            return
        logging.info(f"Performing scheduled auto reset (interval: {interval_sec}s)...")
        self._perform_reset(is_auto=True)
        # Reschedule the next auto reset check
        self._schedule_auto_reset()

    # --- Core Logic: IP Fetching, Logging, Modem Reset ---
    def _get_public_ip(self) -> str:
        try:
            response = self.session.get("https://api.ipify.org", timeout=IP_FETCH_TIMEOUT_S)
            response.raise_for_status()
            return response.text.strip()
        except requests.exceptions.Timeout:
            logging.warning("Timeout getting public IP.")
            return STATUS_IP_TIMEOUT
        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting public IP: {e}")
            return STATUS_IP_UNKNOWN

    def _update_ip_now_task(self):
        if not self.root or not self.root.winfo_exists(): return
        new_ip = self._get_public_ip()
        ip_changed, conn_changed = False, False
        with self.lock:
            if new_ip != self.public_ip: ip_changed = True; self.public_ip = new_ip
            newly_connected = (new_ip not in [STATUS_IP_UNKNOWN, STATUS_IP_TIMEOUT, STATUS_GETTING_IP])
            if self.is_connected is None or self.is_connected != newly_connected: conn_changed = True; self.is_connected = newly_connected
        if ip_changed or conn_changed:
            self._safe_schedule(self._update_ip_label)
        if conn_changed or self.last_action is None: # Update log on first run or connection change
            self._safe_schedule(self._update_log_treeview)

    def _update_ip_label(self):
        try:
             if self.ip_label and self.ip_label.winfo_exists():
                 with self.lock:
                     ip_to_display = self.public_ip
                 self.ip_label.config(text=f"IP Public: {ip_to_display}")
        except tk.TclError:
            pass # Widget gone

    def _ip_update_loop(self):
        while True:
            if not self.root or not self.root.winfo_exists():
                break
            try:
                self._update_ip_now_task()
            except Exception as e:
                logging.exception("Error in IP update loop:")
            sleep_time = IP_CHECK_INTERVAL_SECONDS if self.root and self.root.winfo_exists() else 0.5
            time.sleep(sleep_time)
        logging.info("IP update thread finished.")

    def _update_log_treeview(self):
        if not self.root or not self.root.winfo_exists() or not self.tree or not self.tree.winfo_exists():
            return
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        log_ip = "N/A"
        log_status = "..."
        with self.lock:
            log_ip = self.public_ip
            action = self.last_action
            connected = self.is_connected

        if action and action != STATUS_NORMAL: # Show specific action if in progress
            log_status = action
        elif connected is None:
            log_status = STATUS_CHECKING
        elif connected:
            log_status = STATUS_NORMAL
        else: # connected is False
            log_status = STATUS_DISCONNECTED

        try:
            self.tree.insert('', 0, values=(now, log_ip, log_status))
            # Optional: Limit GUI log lines if auto-export is off
            # if self.log_interval == 0:
            #     children = self.tree.get_children('')
            #     MAX_GUI_LOG_LINES = 200
            #     if len(children) > MAX_GUI_LOG_LINES:
            #         self.tree.delete(*children[MAX_GUI_LOG_LINES:])
        except tk.TclError:
            pass # Widget gone between check and insert
        except Exception as e:
            logging.error(f"Error updating log tree: {e}")

    def _log_update_loop(self):
        while True:
            if not self.root or not self.root.winfo_exists():
                break
            try:
                self._safe_schedule(self._update_log_treeview)
            except Exception as e:
                logging.exception("Error in Log update loop:")
            sleep_time = LOG_UPDATE_INTERVAL_SECONDS if self.root and self.root.winfo_exists() else 0.5
            time.sleep(sleep_time)
        logging.info("Log update thread finished.")

    def _update_status(self, message: str, update_log: bool = True, reset_after_ms: int | None = None):
        """ Updates status, logs (conditionally), schedules reset. """
        # Assign default delay if None was passed
        if reset_after_ms is None:
            reset_after_ms = STATUS_RESET_DELAY_MS # Use constant here

        logging.debug(f"Status -> {message} (Reset in: {reset_after_ms}ms)")
        with self.lock:
            self.last_action = message
        self._cancel_timer(self.status_reset_timer) # Cancel any pending reset
        self.status_reset_timer = None
        if update_log:
            self._safe_schedule(self._update_log_treeview) # Add this message explicitly to GUI log
        if reset_after_ms and reset_after_ms > 0:
            self.status_reset_timer = self._safe_after(reset_after_ms, self._reset_action_status_to_normal)

    def _reset_action_status_to_normal(self):
        """ Resets status message to normal/connection based. """
        self.status_reset_timer = None
        logging.debug("Resetting action status.")
        with self.lock:
            self.last_action = None # Let log updater determine based on connection
        self._safe_schedule(self._update_log_treeview) # Update display
        self._enable_reset_button() # Ensure button is usable

    def _perform_reset(self, is_auto: bool = False):
        """ Core logic for modem reset (less verbose GUI logging). """
        password = self.password_var.get()
        if not password:
            messagebox.showerror("Thiếu Mật khẩu", "Vui lòng nhập mật khẩu modem.", parent=self.root)
            return
        if self.is_resetting:
            action_type = "Tự động" if is_auto else "Thủ công"
            logging.warning(f"{action_type} reset skipped: Reset in progress.")
            if not is_auto:
                messagebox.showinfo("Đang thực hiện", "Modem đang trong quá trình reset.", parent=self.root)
            return

        self.is_resetting = True
        self._disable_reset_button()

        interval_sec = 0
        if is_auto:
            try:
                interval_sec = int(self.auto_reset_interval_var.get())
            except ValueError:
                pass # Keep 0
        start_message = STATUS_RESET_AUTO_START.format(interval_sec) if is_auto else STATUS_RESET_MANUAL_START
        self._update_status(start_message, update_log=True, reset_after_ms=None) # Log start

        def reset_task():
            final_status_message = None
            final_status_reset_delay = STATUS_RESET_DELAY_MS
            reboot_initiated = False
            try:
                encoded_password = base64.b64encode(password.encode()).decode()
                login_payload = {'goformId': MODEM_LOGIN_COMMAND_ID, 'password': encoded_password}

                logging.info("Attempting modem login...")
                with self.lock: self.last_action = STATUS_LOGIN_ATTEMPT # Internal state
                try:
                    login_response = self.session.post(LOGIN_URL, data=login_payload, timeout=REQUESTS_TIMEOUT_S)
                    login_response.raise_for_status()
                    login_text = login_response.text

                    if MODEM_LOGIN_SUCCESS_STR in login_text:
                        logging.info("Login successful.")
                        logging.info("Sending reboot command...")
                        with self.lock: self.last_action = STATUS_REBOOT_COMMAND_SENT # Internal state
                        try:
                            reboot_response = self.session.post(LOGIN_URL, data=MODEM_REBOOT_COMMAND, timeout=REQUESTS_TIMEOUT_S)
                            reboot_response.raise_for_status()
                            logging.info("Reboot command sent.")
                            final_status_message = STATUS_REBOOTING
                            final_status_reset_delay = REBOOT_STATUS_RESET_DELAY_MS
                            reboot_initiated = True
                        except requests.exceptions.Timeout:
                            logging.error("Timeout sending reboot.")
                            final_status_message = STATUS_MODEM_TIMEOUT
                        except requests.exceptions.RequestException as e:
                            error_msg = self._format_request_error(e, "reboot")
                            logging.error(f"Reboot error: {error_msg}")
                            final_status_message = STATUS_REBOOT_CMD_ERROR.format(error_msg)
                    elif MODEM_LOGIN_FAILURE_STR in login_text or 'login_fail' in login_text:
                        logging.warning("Login failed.")
                        final_status_message = STATUS_LOGIN_FAILED
                    else:
                        logging.warning(f"Unknown login response: {login_text[:100]}")
                        final_status_message = STATUS_LOGIN_UNKNOWN_ERROR
                except requests.exceptions.Timeout:
                     logging.error("Login timeout.")
                     final_status_message = STATUS_MODEM_TIMEOUT
                except requests.exceptions.ConnectionError as e:
                     error_msg = self._format_request_error(e, "login")
                     logging.error(f"Login connection error: {error_msg}")
                     final_status_message = STATUS_REQUEST_ERROR.format(error_msg)
                except requests.exceptions.RequestException as e:
                     error_msg = self._format_request_error(e, "login/reboot")
                     logging.error(f"Login/reboot request error: {error_msg}")
                     final_status_message = STATUS_REQUEST_ERROR.format(error_msg)
            except Exception as e:
                 error_msg = str(e).splitlines()[0][:70]
                 logging.exception("Unexpected reset error:")
                 final_status_message = STATUS_UNKNOWN_ERROR.format(error_msg)
            finally:
                 if not final_status_message:
                      final_status_message = STATUS_RESET_END_UNKNOWN
                      logging.warning("Reset task finished: Unknown final status.")
                 # Log the final result to GUI
                 self._update_status(final_status_message, update_log=True, reset_after_ms=None)
                 # Schedule cleanup (flag, button, and reset status message)
                 self._safe_schedule(lambda: self._finalize_reset_state(final_status_reset_delay))
        threading.Thread(target=reset_task, daemon=True, name="ModemResetTask").start()

    def _format_request_error(self, e: requests.exceptions.RequestException, context: str = "") -> str:
        """ Helper to format RequestException messages for the GUI log. """
        error_detail = str(e)
        original_exception_type = type(e).__name__
        inner_reason_str = None
        # Check nested exceptions for ConnectionError
        if isinstance(e, requests.exceptions.ConnectionError) and e.args:
            inner_exception = e.args[0]
            # Use exceptions directly from requests library
            if isinstance(inner_exception, (requests.exceptions.MaxRetryError, requests.exceptions.NewConnectionError)):
                 inner_reason = getattr(inner_exception, 'reason', inner_exception)
                 inner_reason_str = str(inner_reason)
            else:
                 inner_reason_str = str(inner_exception) # Fallback to string of inner arg

        if inner_reason_str:
            error_msg = inner_reason_str.splitlines()[0]
        else:
            error_msg = error_detail.splitlines()[0]

        # Simplify common error messages
        if '[Errno 10054]' in error_msg or 'Connection aborted' in error_msg:
            return LOG_ERR_CONN_ABORTED
        if '[Errno 10061]' in error_msg or 'Connection refused' in error_msg:
            return LOG_ERR_CONN_REFUSED
        if 'timed out' in error_msg.lower():
            return LOG_ERR_CONN_TIMEOUT

        logging.debug(f"Formatted error (Context: {context}, Type: {original_exception_type}): {error_msg}")
        return error_msg[:70] # Limit length

    def _finalize_reset_state(self, status_reset_delay_ms: int):
        """ Cleans up reset state (flag, button) and schedules status msg reset. """
        logging.debug(f"Finalizing reset state. Resetting status msg in {status_reset_delay_ms}ms")
        self.is_resetting = False # Clear flag FIRST
        self._enable_reset_button() # Re-enable button

        # Schedule the reset of the STATUS MESSAGE back to normal
        self._cancel_timer(self.status_reset_timer)
        self.status_reset_timer = self._safe_after(status_reset_delay_ms, self._reset_action_status_to_normal)

    def _disable_reset_button(self):
        self._safe_schedule(lambda: self.restart_btn.config(state=tk.DISABLED) if self.restart_btn else None)

    def _enable_reset_button(self):
        # Only enable if not currently resetting (extra safety)
        if not self.is_resetting:
            self._safe_schedule(lambda: self.restart_btn.config(state=tk.NORMAL) if self.restart_btn else None)

    # --- Thread-Safe GUI Update Helpers ---
    def _safe_schedule(self, callback_func, *args):
        """ Schedules a function for the main Tkinter thread using `after(0, ...)`. """
        try:
            if self.root and self.root.winfo_exists():
                self.root.after(0, callback_func, *args)
        except (tk.TclError, RuntimeError) as e:
            logging.warning(f"Could not schedule {callback_func.__name__}: {e}")

    def _safe_after(self, delay_ms: int, callback_func, *args) -> str | None:
         """ Schedules a function after a delay in the main Tkinter thread. """
         try:
              if self.root and self.root.winfo_exists():
                   return self.root.after(delay_ms, callback_func, *args)
         except (tk.TclError, RuntimeError) as e:
              logging.warning(f"Could not schedule 'after' {callback_func.__name__}: {e}")
         return None

    def _cancel_timer(self, timer_id: str | None):
        """ Safely cancels a timer created with `root.after`. """
        if timer_id:
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after_cancel(timer_id)
                    logging.debug(f"Cancelled timer: {timer_id}")
            except (tk.TclError, ValueError) as e: # ValueError if ID invalid/already cancelled
                logging.warning(f"Could not cancel timer {timer_id}: {e}")
            except Exception as e: # Catch any other unexpected error
                logging.error(f"Unexpected error cancelling timer {timer_id}: {e}")

    def _cancel_all_timers(self):
        """ Cancels all known scheduled timers. """
        logging.debug("Cancelling all timers...")
        self._cancel_timer(self.auto_export_timer)
        self.auto_export_timer = None
        self._cancel_timer(self.auto_reset_timer)
        self.auto_reset_timer = None
        self._cancel_timer(self.status_reset_timer)
        self.status_reset_timer = None

# --- Main Execution ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, # Change to DEBUG for more verbose logs
        format='%(asctime)s - %(levelname)-8s - %(threadName)-15s - %(message)s'
    )
    # Optional: Add file logging handler
    # try:
    #     log_file_handler = logging.FileHandler("modem_reset_tool.log", encoding='utf-8')
    #     log_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s'))
    #     logging.getLogger().addHandler(log_file_handler)
    # except Exception as log_e:
    #      logging.error(f"Failed to configure file logging: {log_e}")

    try:
        root = tk.Tk()
        app = ModemResetApp(root)
        root.mainloop()
    except Exception as e:
         logging.exception("Fatal error starting or running application:")
         # Attempt to show final error message if GUI setup failed partially
         try:
              messagebox.showerror("Lỗi Nghiêm Trọng", f"Ứng dụng gặp lỗi:\n\n{e}\n\nVui lòng kiểm tra file log.")
         except Exception:
              pass # Ignore if Tkinter itself is broken