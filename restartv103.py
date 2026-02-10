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
import json # Needed for parsing the new IP source response

# --- Constants ---
APP_NAME = "Modem Reset Tool"
APP_VERSION = "1.3.0" # Incremented version for IP source change
CONFIG_FILE = 'config.ini'
MODEM_IP = 'http://192.168.0.1'
LOGIN_URL = f'{MODEM_IP}/reqproc/proc_post'
# IP_CHECK_URL = "https://api.ipify.org" # Old IP source
IP_CHECK_URL = "https://geo.myip.link/" # New IP source (returns JSON)
IP_CHECK_INTERVAL_SECONDS = 10
LOG_UPDATE_INTERVAL_SECONDS = 5
DEFAULT_LOG_INTERVAL = 0
DEFAULT_AUTO_RESET_INTERVAL = 0
ICON_PATH = r"C:\Projects\ResetModem\icons\app_icon.ico" # Adjust if needed

# Network Timeouts & Delays
REQUESTS_TIMEOUT_S = 10
IP_FETCH_TIMEOUT_S = 5 # Timeout for fetching public IP
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
STATUS_IP_PARSE_ERROR = "Lỗi phân tích IP" # New status for JSON parse error
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
    window.update_idletasks() # Ensure winfo methods work correctly
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    parent_x, parent_y = 0, 0

    if parent and parent.winfo_exists():
        parent_geo = parent.winfo_geometry()
        try:
            # Regex to parse geometry string like "WxH+X+Y"
            match = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", parent_geo) # Allow negative coords
            if match:
                parent_w, parent_h, parent_x, parent_y = map(int, match.groups())
                x = parent_x + (parent_w // 2) - (width // 2)
                y = parent_y + (parent_h // 2) - (height // 2)
            else:
                logging.warning(f"Could not parse parent geometry: {parent_geo}. Centering on screen.")
                # Fallback to screen centering if parsing fails
                x = (screen_width // 2) - (width // 2)
                y = (screen_height // 2) - (height // 2)
        except Exception as e:
             logging.error(f"Error calculating relative center: {e}. Centering on screen.")
             x = (screen_width // 2) - (width // 2)
             y = (screen_height // 2) - (height // 2)
    else:
        # Center on screen if no parent or parent doesn't exist
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)

    # Ensure the window is not positioned completely off-screen
    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))
    window.geometry(f'{width}x{height}+{x}+{y}')


# --- Settings Window ---
class SettingsWindow(tk.Toplevel):
    """A Toplevel window for configuring log file export settings."""
    def __init__(self, parent_app: 'ModemResetApp'):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.transient(parent_app.root) # Keep on top of parent
        self.title("Cài đặt Lưu Log")
        self.resizable(False, False)
        self.grab_set() # Modal behavior
        settings_width = 450
        settings_height = 200

        # Initialize variables with current app settings
        initial_dir = parent_app.log_directory or "Chưa chọn thư mục"
        initial_interval = str(parent_app.log_interval)
        self.log_dir_var = tk.StringVar(value=initial_dir)
        self.log_interval_var = tk.StringVar(value=initial_interval)

        # --- Widgets ---
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
        # Allow saving by pressing Enter in the interval entry
        interval_entry.bind("<Return>", lambda event: self._save_settings())

        # Frame for buttons at the bottom right
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=15, sticky="e")
        save_button = ttk.Button(button_frame, text="Lưu", command=self._save_settings)
        save_button.pack(side="left", padx=5)
        cancel_button = ttk.Button(button_frame, text="Hủy", command=self.destroy)
        cancel_button.pack(side="left", padx=5)

        # Configure column weights for resizing (though window is fixed size)
        main_frame.columnconfigure(0, weight=1)

        interval_entry.focus() # Set focus to interval entry
        center_window(self, settings_width, settings_height, parent=parent_app.root)
        self.wait_window() # Make it modal - wait until destroyed

    def _select_directory(self):
        """Opens a dialog to choose a log directory."""
        # Use the current setting or the script's directory as starting point
        initial_dir = self.parent_app.log_directory or os.getcwd()
        directory = filedialog.askdirectory(parent=self, title="Chọn thư mục để lưu file log", initialdir=initial_dir)
        if directory: # Only update if a directory was selected
            self.log_dir_var.set(directory)

    def _save_settings(self):
        """Validates and saves the log settings to the main app."""
        try:
            interval = int(self.log_interval_var.get())
            if interval < 0:
                raise ValueError("Interval cannot be negative")
        except ValueError:
            messagebox.showerror("Lỗi Đầu vào", "Thời gian tự động lưu phải là số nguyên không âm.", parent=self)
            return # Keep settings window open

        directory = self.log_dir_var.get()
        # Treat the placeholder text as None
        if directory == "Chưa chọn thư mục":
            directory = None

        # Require directory if auto-save interval is positive
        if directory is None and interval > 0:
            messagebox.showerror("Thiếu Thông tin", "Vui lòng chọn thư mục nếu bật tự động lưu.", parent=self)
            return # Keep settings window open

        # Pass validated settings back to the main application
        self.parent_app.update_log_settings(directory, interval)
        self.destroy() # Close the settings window


# --- Main Application ---
class ModemResetApp:
    """Main application class for the Modem Reset Tool."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.app_width = 450
        self.app_height = 350
        self.root.resizable(True, True) # Allow resizing
        self.root.geometry(f"{self.app_width}x{self.app_height}")
        # Set minimum size to prevent widgets overlapping too much
        self.root.minsize(400, 300)

        self.config = configparser.ConfigParser()
        self.last_pos_x: int | None = None
        self.last_pos_y: int | None = None

        # --- Tkinter Variables ---
        self.password_var = tk.StringVar()
        self.save_password_var = tk.BooleanVar()
        self.auto_reset_interval_var = tk.StringVar(value=str(DEFAULT_AUTO_RESET_INTERVAL))
        self.auto_reset_enabled_var = tk.BooleanVar(value=False)

        # --- Application State ---
        self.public_ip: str = STATUS_GETTING_IP # Current public IP or status
        self.is_connected: bool | None = None # None = initial state, True = connected, False = disconnected
        self.last_action: str | None = None # Stores current action (like resetting, logging in)
        self.log_directory: str | None = None # Directory for auto log export
        self.log_interval: int = DEFAULT_LOG_INTERVAL # Interval in seconds for auto log export

        self.is_resetting: bool = False # Flag to prevent concurrent resets
        self.lock = threading.Lock() # Lock for thread-safe access to shared state

        # --- Timer IDs ---
        self.auto_export_timer: str | None = None # Tkinter timer ID for log export
        self.auto_reset_timer: str | None = None # Tkinter timer ID for auto reset
        self.status_reset_timer: str | None = None # Tkinter timer ID to reset status message

        # --- Network Session ---
        self.session = requests.Session()
        # Set common headers for modem communication
        self.session.headers.update({
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': MODEM_IP + '/index.html',
            'X-Requested-With': 'XMLHttpRequest',
            # 'X-Ki-Saas-Ajax-Request': 'Ajax_Request', # Commented out - may not be necessary for all models
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36' # More standard UA
        })

        # --- GUI Widget References ---
        self.tree: ttk.Treeview | None = None
        self.ip_label: ttk.Label | None = None
        self.restart_btn: ttk.Button | None = None
        self.auto_reset_interval_entry: ttk.Entry | None = None
        self.auto_reset_enabled_chk: ttk.Checkbutton | None = None
        self.password_entry: ttk.Entry | None = None
        self.save_password_chk: ttk.Checkbutton | None = None

        # --- Initialization Steps ---
        self._set_icon()
        self._create_menu()
        self._create_widgets()
        self._load_config()
        self._position_window() # Position after loading config
        self._start_background_tasks()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing) # Handle window close button

    # --- Initialization & UI Creation Methods ---
    def _set_icon(self):
        """Sets the application window icon."""
        try:
            if os.path.exists(ICON_PATH):
                self.root.iconbitmap(ICON_PATH)
            else:
                logging.warning(f"Icon file not found: {ICON_PATH}")
        except tk.TclError as e: # Catch specific Tkinter errors related to icons
            logging.warning(f"Could not set icon (TclError): {e}")
        except Exception as e: # Catch any other potential errors
            logging.warning(f"Could not set icon (General Error): {e}")

    def _create_menu(self):
        """Creates the main application menu bar."""
        menubar = tk.Menu(self.root)
        options_menu = tk.Menu(menubar, tearoff=0) # Create "Tùy chọn" menu
        options_menu.add_command(label="Cài đặt Log...", command=self._open_settings_window)
        options_menu.add_command(label="Thông tin...", command=self._show_about_info)
        options_menu.add_separator()
        options_menu.add_command(label="Thoát", command=self._on_closing)
        menubar.add_cascade(label="Tùy chọn", menu=options_menu) # Add the menu to the menubar
        self.root.config(menu=menubar) # Attach menubar to the root window

    def _create_widgets(self):
        """Creates all the GUI widgets for the main window."""
        # --- Top Frame for Controls ---
        top_frame = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        top_frame.pack(fill='x', side='top') # Pack at the top, fill horizontally
        top_frame.columnconfigure(1, weight=1) # Allow the second column (entries/buttons) to expand

        # Password Input
        ttk.Label(top_frame, text="Mật khẩu modem:").grid(row=0, column=0, sticky='w', padx=(0, 5), pady=3)
        pw_frame = ttk.Frame(top_frame) # Frame to hold password entry and checkbox together
        pw_frame.grid(row=0, column=1, columnspan=2, sticky='w') # Span 2 cols, align left
        self.password_entry = ttk.Entry(pw_frame, textvariable=self.password_var, show="*", width=15)
        self.password_entry.pack(side='left', padx=(0, 5))
        self.save_password_chk = ttk.Checkbutton(pw_frame, text="Lưu", variable=self.save_password_var)
        self.save_password_chk.pack(side='left')

        # Auto Reset Input
        ttk.Label(top_frame, text="Tự động reset (giây):").grid(row=1, column=0, sticky='w', padx=(0, 5), pady=3)
        reset_frame = ttk.Frame(top_frame) # Frame for auto-reset controls
        reset_frame.grid(row=1, column=1, columnspan=2, sticky='w')
        self.auto_reset_interval_entry = ttk.Entry(reset_frame, textvariable=self.auto_reset_interval_var, width=15)
        self.auto_reset_interval_entry.pack(side='left', padx=(0, 5))
        self.auto_reset_enabled_chk = ttk.Checkbutton(reset_frame, text="Bật", variable=self.auto_reset_enabled_var, command=self._schedule_auto_reset)
        self.auto_reset_enabled_chk.pack(side='left')
        # Schedule auto-reset when Enter is pressed or focus leaves the interval entry
        self.auto_reset_interval_entry.bind("<Return>", lambda e: self._schedule_auto_reset())
        self.auto_reset_interval_entry.bind("<FocusOut>", lambda e: self._schedule_auto_reset())

        # Manual Reset Button
        self.restart_btn = ttk.Button(top_frame, text="Reset Modem Thủ Công", command=self._manual_reset_request, width=25)
        self.restart_btn.grid(row=2, column=1, pady=10, ipady=3, sticky='w', padx=(0, 5)) # Internal padding, align left

        # IP Address Label
        self.ip_label = ttk.Label(top_frame, text=f"IP Public: {self.public_ip}", width=40, anchor='w') # Align text left
        self.ip_label.grid(row=3, column=0, columnspan=3, pady=5, sticky='w') # Span all columns

        # Separator Line
        ttk.Separator(self.root).pack(fill='x', pady=5, padx=10)

        # --- Log Frame ---
        log_frame = ttk.LabelFrame(self.root, text="Lịch sử hoạt động", padding=5)
        # Pack below separator, fill remaining space, allow expansion
        log_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10), side='bottom')

        # Log Treeview
        columns = ("time", "ip", "status")
        self.tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=10)
        self.tree.heading("time", text="Thời gian", anchor='w')
        self.tree.column("time", width=140, anchor='w', stretch=tk.NO) # Fixed width
        self.tree.heading("ip", text="IP", anchor='w')
        self.tree.column("ip", width=120, anchor='w', stretch=tk.NO) # Fixed width
        self.tree.heading("status", text="Trạng thái", anchor='w')
        self.tree.column("status", width=250, anchor='w') # Allow status column to stretch

        # Scrollbar for Treeview
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Grid layout for Treeview and Scrollbar within the log_frame
        log_frame.rowconfigure(0, weight=1) # Allow Treeview row to expand vertically
        log_frame.columnconfigure(0, weight=1) # Allow Treeview column to expand horizontally
        self.tree.grid(row=0, column=0, sticky='nsew') # Expand in all directions
        scrollbar.grid(row=0, column=1, sticky='ns') # Stick to North/South edges

    def _position_window(self):
        """Positions the window based on saved config or centers it."""
        if self.last_pos_x is not None and self.last_pos_y is not None:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            # Check if the saved position is reasonably on-screen
            if 0 <= self.last_pos_x < (screen_w - 50) and 0 <= self.last_pos_y < (screen_h - 50):
                 logging.info(f"Restoring window position to +{self.last_pos_x}+{self.last_pos_y}")
                 self.root.geometry(f"+{self.last_pos_x}+{self.last_pos_y}")
            else:
                 logging.warning("Saved window position is off-screen or invalid, centering.")
                 center_window(self.root, self.app_width, self.app_height)
        else:
            logging.info("No saved window position found, centering.")
            center_window(self.root, self.app_width, self.app_height)

    def _start_background_tasks(self):
        """Starts the recurring background threads and initial tasks."""
        self._schedule_auto_export() # Schedule log export based on loaded config
        self._schedule_auto_reset() # Schedule auto reset based on loaded config
        # Fetch IP immediately once on startup in a separate thread
        threading.Thread(target=self._update_ip_now_task, daemon=True, name="InitialIPFetch").start()
        # Start the continuous IP update loop
        threading.Thread(target=self._ip_update_loop, daemon=True, name="IPUpdateLoop").start()
        # Start the continuous GUI log update loop
        threading.Thread(target=self._log_update_loop, daemon=True, name="LogUpdateLoop").start()

    # --- Configuration Methods ---
    def _load_config(self):
        """Loads settings from the CONFIG_FILE."""
        if not os.path.exists(CONFIG_FILE):
            logging.info(f"Config file '{CONFIG_FILE}' not found. Using defaults.")
            return # Use default values if file doesn't exist

        try:
            self.config.read(CONFIG_FILE, encoding='utf-8') # Specify encoding

            # Load Credentials
            if self.config.has_section(CONFIG_SECTION_CREDS):
                saved_pw = self.config.get(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, fallback='')
                if saved_pw:
                    self.password_var.set(saved_pw)
                    self.save_password_var.set(True) # Check the "Save" box if loaded

            # Load Logging Settings
            if self.config.has_section(CONFIG_SECTION_LOGGING):
                # Handle empty string fallback for directory correctly
                self.log_directory = self.config.get(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, fallback=None)
                if self.log_directory == '': self.log_directory = None # Treat empty string as None

                self.log_interval = self.config.getint(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, fallback=DEFAULT_LOG_INTERVAL)
                self.log_interval = max(0, self.log_interval) # Ensure non-negative

            # Load Auto Reset Settings
            if self.config.has_section(CONFIG_SECTION_AUTO_RESET):
                 enabled = self.config.getboolean(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_ENABLED, fallback=False)
                 interval = self.config.getint(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, fallback=DEFAULT_AUTO_RESET_INTERVAL)
                 interval = max(0, interval) # Ensure non-negative
                 self.auto_reset_enabled_var.set(enabled)
                 self.auto_reset_interval_var.set(str(interval))

            # Load Window Position
            if self.config.has_section(CONFIG_SECTION_WINDOW):
                self.last_pos_x = self.config.getint(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, fallback=None)
                self.last_pos_y = self.config.getint(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, fallback=None)

        except (configparser.Error, ValueError, TypeError) as e:
            logging.error(f"Error reading config file '{CONFIG_FILE}': {e}")
            messagebox.showwarning("Lỗi Config", f"Lỗi đọc file cấu hình '{CONFIG_FILE}'.\nSử dụng cài đặt mặc định.", parent=self.root)
            self._reset_to_default_config_values() # Reset state if config is corrupt

    def _reset_to_default_config_values(self):
        """Resets all configurable settings to their default state."""
        logging.warning("Resetting configuration variables to defaults.")
        self.password_var.set("")
        self.save_password_var.set(False)
        self.log_directory = None
        self.log_interval = DEFAULT_LOG_INTERVAL
        self.auto_reset_enabled_var.set(False)
        self.auto_reset_interval_var.set(str(DEFAULT_AUTO_RESET_INTERVAL))
        self.last_pos_x = None
        self.last_pos_y = None
        # Ensure config object is cleared if it was partially read
        self.config = configparser.ConfigParser()

    def _save_config(self):
        """Saves the current settings to the CONFIG_FILE."""
        logging.info("Saving configuration...")
        try:
            # Ensure sections exist
            for section in [CONFIG_SECTION_CREDS, CONFIG_SECTION_LOGGING, CONFIG_SECTION_WINDOW, CONFIG_SECTION_AUTO_RESET]:
                if not self.config.has_section(section):
                    self.config.add_section(section)

            # Save Credentials
            if self.save_password_var.get():
                self.config.set(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, self.password_var.get())
            elif self.config.has_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD):
                # Remove password if "Save" is unchecked
                self.config.remove_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD)

            # Save Logging Settings
            self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, str(self.log_interval))
            self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, self.log_directory or '') # Save empty string if None

            # Save Auto Reset Settings
            self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_ENABLED, str(self.auto_reset_enabled_var.get()))
            try:
                # Validate and save interval, default to 0 if invalid
                interval_to_save = int(self.auto_reset_interval_var.get())
                interval_to_save = max(0, interval_to_save)
            except ValueError:
                interval_to_save = DEFAULT_AUTO_RESET_INTERVAL # Save default if current value is invalid
                logging.warning(f"Invalid auto reset interval '{self.auto_reset_interval_var.get()}' during save. Saving default ({DEFAULT_AUTO_RESET_INTERVAL}).")
            self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, str(interval_to_save))

            # Save Window Position
            current_x, current_y = self._get_current_window_position()
            if current_x is not None and current_y is not None:
                self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, str(current_x))
                self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, str(current_y))
            else: # If position invalid, remove from config
                if self.config.has_option(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X):
                    self.config.remove_option(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X)
                if self.config.has_option(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y):
                    self.config.remove_option(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y)


            # Write to file
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            logging.info("Configuration saved successfully.")

        except (configparser.Error, IOError, OSError) as e:
            logging.error(f"Error writing configuration file '{CONFIG_FILE}': {e}")
            # Optionally show a message box, but might be annoying on close
            # messagebox.showerror("Lỗi Lưu Config", f"Không thể lưu file cấu hình:\n{e}", parent=self.root)

    def _get_current_window_position(self) -> tuple[int | None, int | None]:
        """Gets the current X, Y coordinates of the main window."""
        try:
            # Check if root window exists and hasn't been destroyed
            if self.root and self.root.winfo_exists():
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                # Basic check to avoid saving completely off-screen positions
                # (Allows negative coordinates which are valid in multi-monitor setups)
                screen_w = self.root.winfo_screenwidth()
                screen_h = self.root.winfo_screenheight()
                # Check if at least a small part of the window is visible
                if (x + self.root.winfo_width() > 50) and (x < screen_w - 50) and \
                   (y + self.root.winfo_height() > 50) and (y < screen_h - 50):
                    return x, y
                else:
                    logging.warning(f"Window position {x},{y} seems off-screen. Not saving.")
                    return None, None
            return None, None # Window doesn't exist
        except tk.TclError as e: # Catch errors if window is in a weird state
             logging.error(f"Error getting window position (TclError): {e}")
             return None, None
        except Exception as e: # Catch any other error
             logging.error(f"Unexpected error getting window position: {e}")
             return None, None

    # --- Action Methods & Event Handlers ---
    def _on_closing(self):
        """Handles the window close event (clicking the X button)."""
        # Ask for confirmation before closing
        if messagebox.askyesno("Xác nhận thoát", f"Bạn có chắc muốn thoát {APP_NAME}?", parent=self.root):
            logging.info("Close requested by user. Shutting down...")
            self._cancel_all_timers() # Stop any pending actions
            self._save_config() # Save settings before exiting
            if self.root and self.root.winfo_exists():
                try:
                    self.root.destroy() # Close the Tkinter window
                except tk.TclError as e:
                    # This can happen if threads are still trying to interact with the GUI
                    logging.warning(f"TclError during window destruction (likely safe to ignore): {e}")
        else:
            logging.info("User cancelled close request.")

    def _show_about_info(self):
        """Displays the About information dialog."""
        info = f"{APP_NAME}\nPhiên bản: {APP_VERSION}\n\nChức năng:\n- Theo dõi IP Public.\n- Reset modem Viettel (HG8045A5, F670Y, etc.).\n- Lưu log hoạt động ra file.\n- Tự động reset khi mất kết nối (tùy chọn).\n- Lưu cài đặt và vị trí cửa sổ."
        messagebox.showinfo("Thông tin", info, parent=self.root)

    def _open_settings_window(self):
        """Opens the modal Settings window."""
        # Creates an instance of the SettingsWindow class, passing self (ModemResetApp)
        # The SettingsWindow handles its own logic and calls back to update_log_settings
        SettingsWindow(self)

    def update_log_settings(self, directory: str | None, interval: int):
        """Callback method for SettingsWindow to update log config."""
        self.log_directory = directory
        self.log_interval = interval
        logging.info(f"Log settings updated: Directory='{self.log_directory}', Interval={self.log_interval}s")
        self._save_config() # Save changes immediately
        self._schedule_auto_export() # Reschedule export timer with new settings

    def _manual_reset_request(self):
        """Initiates a manual modem reset."""
        # Simply call the core reset logic, marking it as non-automatic
        self._perform_reset(is_auto=False)

    # --- Background Task Scheduling & Execution ---
    def _schedule_auto_export(self):
        """Schedules or cancels the automatic log file export timer."""
        self._cancel_timer(self.auto_export_timer) # Cancel previous timer if exists
        self.auto_export_timer = None # Clear timer ID

        # Only schedule if interval is positive AND a valid directory is set
        if self.log_interval > 0 and self.log_directory and os.path.isdir(self.log_directory):
            logging.info(f"Scheduling auto log export every {self.log_interval} seconds to '{self.log_directory}'.")
            delay_ms = self.log_interval * 1000
            # Schedule _perform_auto_export to run after the delay
            self.auto_export_timer = self._safe_after(delay_ms, self._perform_auto_export)
        elif self.log_interval <= 0:
            logging.info("Auto log export disabled (interval is zero or negative).")
        elif not self.log_directory:
             logging.info("Auto log export disabled (no directory selected).")
        elif self.log_directory and not os.path.isdir(self.log_directory):
             # Log error if directory is set but invalid
             logging.error(f"Auto log export disabled (directory '{self.log_directory}' is invalid or inaccessible).")

    def _perform_auto_export(self):
        """Exports the current log entries from the Treeview to a file."""
        self.auto_export_timer = None # Mark timer as fired
        log_items = []

        # --- Safely get log items from Treeview ---
        try:
            # Check if GUI elements still exist before accessing them
            if self.root and self.root.winfo_exists() and self.tree and self.tree.winfo_exists():
                log_items = self.tree.get_children('') # Get IDs of all top-level items
            else:
                logging.warning("Auto export cancelled: GUI elements no longer exist.")
                return # Don't reschedule if GUI is gone
        except tk.TclError:
            logging.warning("Auto export cancelled: TclError accessing Treeview children (likely GUI closing).")
            return # Don't reschedule if GUI is gone

        if not log_items:
            logging.info("No log entries in the GUI to auto-export.")
            self._schedule_auto_export() # Reschedule for the next interval
            return

        # --- Validate directory again just before writing ---
        if not self.log_directory or not os.path.isdir(self.log_directory):
             # Show error message only once per invalid directory detection
             if not hasattr(self, "_log_dir_error_shown") or not self._log_dir_error_shown:
                 if self.root and self.root.winfo_exists(): # Check if parent window exists
                    messagebox.showerror("Lỗi Xuất Log", f"Thư mục lưu log tự động '{self.log_directory or ''}' không hợp lệ hoặc không thể truy cập.\nVui lòng kiểm tra lại trong Cài đặt Log.", parent=self.root)
                 self._log_dir_error_shown = True # Flag to prevent repeated popups
             logging.error(f"Auto log export failed: Directory '{self.log_directory or ''}' is invalid or inaccessible.")
             self.log_interval = 0 # Temporarily disable auto-export until settings are fixed
             # Do NOT reschedule here
             return
        # Reset error flag if directory is valid now
        self._log_dir_error_shown = False

        # --- Prepare log data ---
        log_data = []
        try:
             if self.tree and self.tree.winfo_exists(): # Check again before iterating
                  for item_id in log_items:
                      try:
                          values = self.tree.item(item_id, 'values')
                          # Ensure values is a tuple/list and not empty
                          if isinstance(values, (list, tuple)) and len(values) == 3:
                              # Format as tab-separated string
                              log_data.append("\t".join(map(str, values)))
                      except tk.TclError:
                          logging.warning(f"TclError reading item {item_id} during auto-export, skipping.")
                          continue # Skip item if it causes an error
        except tk.TclError:
             logging.error("Auto export: TclError accessing Treeview items during data extraction.")
             # Reschedule even if there was an error getting data, maybe it's temporary
             self._schedule_auto_export()
             return

        if not log_data:
            logging.info("No valid log data retrieved for auto export.")
            self._schedule_auto_export() # Reschedule
            return

        # --- Write to file ---
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"modem_log_{timestamp}.txt" # More descriptive filename
        full_path = os.path.join(self.log_directory, filename)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write("Thời gian\tIP\tTrạng thái\n")
                f.write("="*60 + "\n") # Separator line
                # Write data
                f.write("\n".join(log_data))
            logging.info(f"Auto-exported {len(log_data)} log entries to: {full_path}")

            # --- Clear Treeview after successful export ---
            if self.tree and self.tree.winfo_exists():
                try:
                    self.tree.delete(*log_items) # Delete exported items
                except tk.TclError:
                    logging.warning("Could not clear Treeview after auto-export (TclError).")
        except (IOError, OSError) as e:
            logging.error(f"Auto log export failed: Error writing file '{full_path}': {e}")
            if self.root and self.root.winfo_exists():
                messagebox.showerror("Lỗi Xuất Log", f"Không thể ghi file log:\n{full_path}\n\nLỗi: {e}", parent=self.root)
        except Exception as e: # Catch any other unexpected error during file write/clear
            logging.exception("Unexpected error during auto log export file operation:")
            if self.root and self.root.winfo_exists():
                messagebox.showerror("Lỗi Xuất Log", f"Lỗi không xác định khi xuất log:\n{e}", parent=self.root)
        finally:
            # --- Reschedule for the next interval ---
            # Check conditions again in case they changed during export (e.g., user changed settings)
            if self.log_interval > 0 and self.log_directory and os.path.isdir(self.log_directory):
                 self._schedule_auto_export()

    def _schedule_auto_reset(self):
        """Schedules or cancels the automatic modem reset timer."""
        self._cancel_timer(self.auto_reset_timer) # Cancel previous timer
        self.auto_reset_timer = None

        is_enabled = self.auto_reset_enabled_var.get()
        interval_str = self.auto_reset_interval_var.get()

        if is_enabled:
            try:
                interval_sec = int(interval_str)
                if interval_sec <= 0:
                    # Don't schedule if interval is not positive
                    logging.warning("Auto reset interval must be a positive number of seconds. Auto-reset disabled.")
                    # Optionally uncheck the box if interval is invalid? Or just silently disable.
                    # self.auto_reset_enabled_var.set(False) # <-- Maybe too intrusive
                    return
            except ValueError:
                # Don't schedule if interval is not a valid integer
                logging.warning(f"Invalid auto reset interval '{interval_str}'. Must be an integer. Auto-reset disabled.")
                # self.auto_reset_enabled_var.set(False) # <-- Maybe too intrusive
                return

            # Schedule the reset trigger if enabled and interval is valid
            logging.info(f"Scheduling automatic reset check every {interval_sec} seconds.")
            self.auto_reset_timer = self._safe_after(interval_sec * 1000, self._auto_reset_trigger)
        else:
            logging.info("Automatic reset is disabled.")

    def _auto_reset_trigger(self):
        """Checks connection and performs auto-reset if needed, then reschedules."""
        self.auto_reset_timer = None # Mark timer as fired

        # --- Pre-checks before executing ---
        if not self.root or not self.root.winfo_exists():
            logging.info("Auto reset trigger cancelled: GUI no longer exists.")
            return

        # Re-validate settings right before potentially resetting
        is_enabled = self.auto_reset_enabled_var.get()
        interval_sec = 0
        try:
            interval_sec = int(self.auto_reset_interval_var.get())
            is_enabled = is_enabled and (interval_sec > 0) # Must still be enabled and have positive interval
        except ValueError:
            is_enabled = False # Disable if interval became invalid

        if not is_enabled:
            logging.info("Auto reset trigger cancelled: Conditions changed (disabled or invalid interval).")
            self._schedule_auto_reset() # Try to reschedule based on current (likely disabled) state
            return

        # --- Check connection status ---
        # Use the latest known connection status from the background thread
        with self.lock:
            currently_connected = self.is_connected

        if currently_connected is None:
            logging.info("Auto reset trigger: Connection status unknown, skipping reset check.")
        elif currently_connected is True:
            logging.info(f"Auto reset trigger: Connection OK (IP: {self.public_ip}). No reset needed.")
        else: # currently_connected is False
            logging.warning(f"Auto reset trigger: Connection appears down (Status: {self.public_ip}). Initiating auto-reset.")
            self._perform_reset(is_auto=True) # Perform the reset

        # --- Reschedule the next check ---
        # This happens regardless of whether a reset was performed, to keep the cycle going
        self._schedule_auto_reset()


    # --- Core Logic: IP Fetching, Logging, Modem Reset ---
    def _get_public_ip(self) -> str:
        """Fetches the public IP address using the configured URL."""
        try:
            # Use a separate timeout for IP fetching
            # Provide headers to look like a browser request
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36'}
            # Use a standard requests.get, not the session, to avoid modem-specific headers
            response = requests.get(IP_CHECK_URL, timeout=IP_FETCH_TIMEOUT_S, headers=headers)
            response.raise_for_status() # Check for HTTP errors (4xx, 5xx)

            # --- Parse JSON response ---
            try:
                data = response.json()
                ip_address = data.get('ip') # Safely get 'ip' key
                if ip_address and isinstance(ip_address, str):
                     return ip_address.strip()
                else:
                     logging.error(f"Could not find valid 'ip' key in JSON response from {IP_CHECK_URL}. Data: {data}")
                     return STATUS_IP_PARSE_ERROR # Indicate parsing issue
            except json.JSONDecodeError as json_err:
                 logging.error(f"Error decoding JSON response from {IP_CHECK_URL}: {json_err}")
                 logging.debug(f"Response text (first 200 chars): {response.text[:200]}")
                 return STATUS_IP_PARSE_ERROR # Indicate parsing issue
            except Exception as parse_e: # Catch other potential issues during parsing
                 logging.exception(f"Unexpected error parsing IP response from {IP_CHECK_URL}:")
                 return STATUS_IP_UNKNOWN

        except requests.exceptions.Timeout:
            logging.warning(f"Timeout getting public IP from {IP_CHECK_URL}.")
            return STATUS_IP_TIMEOUT
        except requests.exceptions.RequestException as e:
            # Log specific request errors (like connection refused, DNS error, etc.)
            logging.error(f"Error getting public IP from {IP_CHECK_URL}: {e}")
            return STATUS_IP_UNKNOWN
        except Exception as e: # Catch any other unexpected error
             logging.exception(f"Unexpected error getting public IP from {IP_CHECK_URL}:")
             return STATUS_IP_UNKNOWN

    def _update_ip_now_task(self):
        """Fetches IP and updates state and GUI if necessary. Runs in a thread."""
        if not self.root or not self.root.winfo_exists(): return # Exit if GUI is gone

        new_ip = self._get_public_ip()
        ip_changed, conn_changed = False, False

        with self.lock: # --- Thread safety ---
            # Check if IP address itself changed
            if new_ip != self.public_ip:
                ip_changed = True
                self.public_ip = new_ip # Update stored IP

            # Determine new connection state based on IP result
            # Considered connected if IP is valid and not an error/status message
            newly_connected = (new_ip not in [STATUS_IP_UNKNOWN, STATUS_IP_TIMEOUT, STATUS_GETTING_IP, STATUS_IP_PARSE_ERROR])

            # Check if connection state changed (e.g., None->True, True->False)
            if self.is_connected is None or self.is_connected != newly_connected:
                conn_changed = True
                self.is_connected = newly_connected # Update stored connection state
            # --- End thread safety ---

        # --- Schedule GUI updates on main thread ---
        if ip_changed or conn_changed: # Update IP label if IP or connection changed
            self._safe_schedule(self._update_ip_label)
        # Update log on first run (last_action is None) or if connection state changed
        if conn_changed or (self.last_action is None and not self.is_resetting):
            self._safe_schedule(self._update_log_treeview)

    def _update_ip_label(self):
        """Updates the IP address label in the GUI (runs on main thread)."""
        try:
             if self.ip_label and self.ip_label.winfo_exists():
                 with self.lock: # Read shared variable safely
                     ip_to_display = self.public_ip
                 self.ip_label.config(text=f"IP Public: {ip_to_display}")
        except tk.TclError:
            pass # Widget might have been destroyed between check and config

    def _ip_update_loop(self):
        """Periodically calls the IP update task in a loop."""
        while True:
            if not self.root or not self.root.winfo_exists():
                logging.info("IP update loop exiting: GUI closed.")
                break # Exit loop if GUI is closed
            try:
                self._update_ip_now_task()
            except Exception as e:
                # Log unexpected errors in the loop itself
                logging.exception("Error in IP update loop:")
            # Wait for the specified interval, or shorter if GUI closed
            sleep_time = IP_CHECK_INTERVAL_SECONDS if self.root and self.root.winfo_exists() else 0.5
            time.sleep(sleep_time)
        logging.info("IP update thread finished.")

    def _update_log_treeview(self):
        """Adds a new entry to the log Treeview (runs on main thread)."""
        # Check if GUI elements are valid before proceeding
        if not self.root or not self.root.winfo_exists() or not self.tree or not self.tree.winfo_exists():
            return

        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        log_ip = "N/A"
        log_status = "..."

        with self.lock: # Read shared state safely
            log_ip = self.public_ip
            action = self.last_action
            connected = self.is_connected
            resetting = self.is_resetting

        # Determine the status message to display in the log
        if action and action != STATUS_NORMAL: # Show specific action if one is in progress
            log_status = action
        elif connected is None and not resetting: # Initial state or checking
             log_status = STATUS_CHECKING
        elif connected:
            log_status = STATUS_NORMAL # Normal operation
        elif not connected and not resetting: # Connected is False, not currently resetting
            # Display appropriate disconnected status based on IP value
            if log_ip == STATUS_IP_TIMEOUT:
                 log_status = STATUS_IP_TIMEOUT
            elif log_ip == STATUS_IP_UNKNOWN:
                 log_status = STATUS_IP_UNKNOWN
            elif log_ip == STATUS_IP_PARSE_ERROR:
                 log_status = STATUS_IP_PARSE_ERROR
            else:
                 log_status = STATUS_DISCONNECTED # Generic disconnected
        # If resetting, the status is likely already set by _update_status

        # Only add log entry if status is determined
        if log_status != "...":
            try:
                # Insert new log entry at the top (index 0)
                self.tree.insert('', 0, values=(now, log_ip, log_status))

                # --- Optional: Limit visible log lines if auto-export is OFF ---
                # This prevents the GUI log from growing indefinitely if not exported
                # if self.log_interval <= 0 or not self.log_directory:
                #      children = self.tree.get_children('')
                #      MAX_GUI_LOG_LINES = 200 # Adjust as needed
                #      if len(children) > MAX_GUI_LOG_LINES:
                #          # Delete the oldest entries
                #          items_to_delete = children[MAX_GUI_LOG_LINES:]
                #          self.tree.delete(*items_to_delete)

            except tk.TclError:
                pass # Widget might have been destroyed between check and insert
            except Exception as e:
                logging.error(f"Error updating log treeview: {e}")

    def _log_update_loop(self):
        """Periodically schedules the GUI log update."""
        while True:
            if not self.root or not self.root.winfo_exists():
                logging.info("Log update loop exiting: GUI closed.")
                break # Exit loop if GUI is closed
            try:
                # Schedule the update on the main thread
                self._safe_schedule(self._update_log_treeview)
            except Exception as e:
                logging.exception("Error in Log update loop:")
            # Wait for interval, or shorter if GUI closed
            sleep_time = LOG_UPDATE_INTERVAL_SECONDS if self.root and self.root.winfo_exists() else 0.5
            time.sleep(sleep_time)
        logging.info("Log update thread finished.")

    def _update_status(self, message: str, update_log: bool = True, reset_after_ms: int | None = None):
        """ Updates the internal action status, optionally logs it, and optionally schedules a reset to normal status. """
        logging.debug(f"Updating action status: '{message}' (Reset delay: {reset_after_ms}ms)")
        with self.lock:
            self.last_action = message # Set the current action message

        # Cancel any pending status reset timer
        self._cancel_timer(self.status_reset_timer)
        self.status_reset_timer = None

        # Immediately update the log view if requested
        if update_log:
            self._safe_schedule(self._update_log_treeview)

        # Schedule the status message to automatically clear after a delay
        if reset_after_ms is not None and reset_after_ms > 0:
            self.status_reset_timer = self._safe_after(reset_after_ms, self._reset_action_status_to_normal)
        elif reset_after_ms == 0: # Allow immediate reset if 0 is passed
             self._reset_action_status_to_normal()


    def _reset_action_status_to_normal(self):
        """ Resets the action status (last_action) to None, allowing the log updater to show connection status. """
        self.status_reset_timer = None # Mark timer as fired/cancelled
        logging.debug("Resetting action status message.")
        with self.lock:
            # Clear the specific action message
            # The log updater will now determine status based on self.is_connected
            self.last_action = None
        # Update the log display to reflect the change
        self._safe_schedule(self._update_log_treeview)
        # Ensure the reset button is enabled after the action completes
        # (This might be called slightly later via _finalize_reset_state too, which is fine)
        self._enable_reset_button()

    def _perform_reset(self, is_auto: bool = False):
        """ Handles the entire modem reset process in a separate thread. """
        password = self.password_var.get()
        if not password:
            # Show error only for manual attempts
            if not is_auto and self.root and self.root.winfo_exists():
                messagebox.showerror("Thiếu Mật khẩu", "Vui lòng nhập mật khẩu modem.", parent=self.root)
            else:
                logging.warning("Reset skipped: Modem password not provided.")
            return

        # Prevent concurrent resets using the flag
        if self.is_resetting:
            action_type = "Tự động" if is_auto else "Thủ công"
            logging.warning(f"{action_type} reset request ignored: Another reset is already in progress.")
            # Show message only for manual attempts
            if not is_auto and self.root and self.root.winfo_exists():
                messagebox.showinfo("Đang thực hiện", "Modem đang trong quá trình reset.\nVui lòng đợi.", parent=self.root)
            return

        # --- Start Reset Process ---
        self.is_resetting = True
        self._disable_reset_button() # Disable button immediately

        interval_sec = 0
        if is_auto: # Get interval for logging message
            try: interval_sec = int(self.auto_reset_interval_var.get())
            except ValueError: interval_sec = 0 # Default if invalid
        start_message = STATUS_RESET_AUTO_START.format(interval_sec) if is_auto else STATUS_RESET_MANUAL_START

        # Update status immediately to show reset start, don't schedule auto-reset for this message
        self._update_status(start_message, update_log=True, reset_after_ms=None)

        # --- Run blocking network operations in a background thread ---
        def reset_task():
            final_status_message = STATUS_RESET_END_UNKNOWN # Default final status
            final_status_reset_delay = STATUS_RESET_DELAY_MS # Default delay to clear final status message
            reboot_initiated = False # Flag if reboot command was likely successful

            try:
                # Encode password in Base64 as required by modem API
                encoded_password = base64.b64encode(password.encode('utf-8')).decode('utf-8')
                login_payload = {'goformId': MODEM_LOGIN_COMMAND_ID, 'password': encoded_password}

                # --- 1. Attempt Login ---
                logging.info("Attempting modem login...")
                self._update_status(STATUS_LOGIN_ATTEMPT, update_log=True, reset_after_ms=None) # Update GUI log
                try:
                    login_response = self.session.post(LOGIN_URL, data=login_payload, timeout=REQUESTS_TIMEOUT_S)
                    login_response.raise_for_status() # Check for HTTP errors
                    login_text = login_response.text
                    logging.debug(f"Login response text: {login_text[:150]}") # Log part of response

                    # --- 2. Check Login Result ---
                    if MODEM_LOGIN_SUCCESS_STR in login_text:
                        logging.info("Modem login successful.")
                        # --- 3. Send Reboot Command ---
                        logging.info("Sending reboot command...")
                        self._update_status(STATUS_REBOOT_COMMAND_SENT, update_log=True, reset_after_ms=None)
                        try:
                            reboot_response = self.session.post(LOGIN_URL, data=MODEM_REBOOT_COMMAND, timeout=REQUESTS_TIMEOUT_S)
                            reboot_response.raise_for_status()
                            # Assuming command sent successfully if no exception
                            logging.info("Reboot command sent successfully (based on HTTP status).")
                            final_status_message = STATUS_REBOOTING # Set status to "Rebooting"
                            # Use a longer delay before clearing "Rebooting" status
                            final_status_reset_delay = REBOOT_STATUS_RESET_DELAY_MS
                            reboot_initiated = True
                        except requests.exceptions.Timeout:
                            logging.error("Timeout occurred while sending reboot command.")
                            final_status_message = STATUS_MODEM_TIMEOUT
                        except requests.exceptions.RequestException as e_reboot:
                            error_msg = self._format_request_error(e_reboot, "reboot command")
                            logging.error(f"Error sending reboot command: {error_msg} (Details: {e_reboot})")
                            final_status_message = STATUS_REBOOT_CMD_ERROR.format(error_msg)

                    elif MODEM_LOGIN_FAILURE_STR in login_text or 'login_fail' in login_text:
                        logging.warning("Modem login failed (incorrect password or other login issue).")
                        final_status_message = STATUS_LOGIN_FAILED
                    else:
                        # Handle unexpected login responses
                        logging.warning(f"Unknown login response received: {login_text[:100]}...")
                        final_status_message = STATUS_LOGIN_UNKNOWN_ERROR

                # --- Handle Login Errors ---
                except requests.exceptions.Timeout:
                     logging.error("Timeout occurred during modem login attempt.")
                     final_status_message = STATUS_MODEM_TIMEOUT
                except requests.exceptions.ConnectionError as e_conn:
                     # More specific handling for connection errors
                     error_msg = self._format_request_error(e_conn, "login connection")
                     logging.error(f"Connection error during login: {error_msg} (Details: {e_conn})")
                     final_status_message = STATUS_MODEM_CONNECTION_ERROR # Specific status
                except requests.exceptions.RequestException as e_login:
                     # Handle other request errors (e.g., HTTP errors caught by raise_for_status)
                     error_msg = self._format_request_error(e_login, "login request")
                     logging.error(f"Request error during login: {error_msg} (Details: {e_login})")
                     final_status_message = STATUS_REQUEST_ERROR.format(error_msg)

            except Exception as e_outer:
                 # Catch any unexpected errors in the main reset logic
                 error_msg = str(e_outer).splitlines()[0][:70] # Get first line, limit length
                 logging.exception("Unexpected error during modem reset process:")
                 final_status_message = STATUS_UNKNOWN_ERROR.format(error_msg)

            finally:
                 # --- Finalize ---
                 logging.info(f"Reset task finished. Final status: '{final_status_message}'")
                 # Update the GUI log with the final result of the reset attempt
                 self._update_status(final_status_message, update_log=True, reset_after_ms=None)
                 # Schedule the cleanup tasks (reset flag, enable button, schedule status clear)
                 # Pass the appropriate delay for clearing the final status message
                 self._safe_schedule(lambda: self._finalize_reset_state(final_status_reset_delay))

        # Start the reset task in a daemon thread
        threading.Thread(target=reset_task, daemon=True, name="ModemResetTask").start()

    def _format_request_error(self, e: requests.exceptions.RequestException, context: str = "request") -> str:
        """ Formats RequestException messages concisely for GUI/log display. """
        error_detail = str(e)
        original_exception_type = type(e).__name__
        inner_reason_str = None

        # Try to extract a more specific reason, especially for ConnectionError
        if isinstance(e, requests.exceptions.ConnectionError) and e.args:
            inner_exception = e.args[0]
            # Check specific nested exceptions from requests/urllib3 if available
            # Note: Accessing deeply nested exceptions can be fragile.
            # Stick to direct attributes or args if possible.
            inner_reason = getattr(inner_exception, 'reason', None)
            if inner_reason:
                 inner_reason_str = str(inner_reason).splitlines()[0] # Get first line of reason
            else:
                 inner_reason_str = str(inner_exception).splitlines()[0] # Fallback to string of inner exception

        # Choose the most relevant error string
        if inner_reason_str:
            error_msg = inner_reason_str
        else:
            error_msg = error_detail.splitlines()[0] # First line of the main exception string

        # Simplify common Winsock/network error messages
        if '[Errno 10054]' in error_msg or 'forcibly closed by the remote host' in error_msg.lower() or 'Connection aborted' in error_msg:
            return LOG_ERR_CONN_ABORTED
        if '[Errno 10061]' in error_msg or 'No connection could be made because the target machine actively refused it' in error_msg or 'Connection refused' in error_msg:
            return LOG_ERR_CONN_REFUSED
        if 'timed out' in error_msg.lower():
             # Distinguish between modem timeout and general network timeout if possible
             if context == "login connection" or context == "reboot command":
                 return STATUS_MODEM_TIMEOUT # More specific if during modem communication
             else:
                 return LOG_ERR_CONN_TIMEOUT # Generic timeout otherwise

        # Limit length for display purposes
        MAX_LEN = 70
        if len(error_msg) > MAX_LEN:
            error_msg = error_msg[:MAX_LEN-3] + "..."

        logging.debug(f"Formatted error (Context: {context}, Type: {original_exception_type}, Original: {error_detail[:100]}...) -> '{error_msg}'")
        return error_msg

    def _finalize_reset_state(self, status_reset_delay_ms: int):
        """ Cleans up after a reset attempt: resets flag, enables button, schedules status message clear. """
        logging.debug(f"Finalizing reset state. Scheduling status message reset in {status_reset_delay_ms}ms")

        # --- Critical: Clear the resetting flag FIRST ---
        # This allows new resets to be initiated even if the status message is still showing "Rebooting"
        self.is_resetting = False

        # --- Re-enable the reset button ---
        # Do this after clearing the flag
        self._enable_reset_button()

        # --- Schedule the final status message to clear ---
        # This uses the delay passed in (e.g., longer for "Rebooting")
        self._cancel_timer(self.status_reset_timer) # Cancel any leftover timer
        if status_reset_delay_ms > 0:
            self.status_reset_timer = self._safe_after(status_reset_delay_ms, self._reset_action_status_to_normal)
        else: # If delay is 0 or less, clear status immediately
             self._reset_action_status_to_normal()


    def _disable_reset_button(self):
        """Safely disables the manual reset button (runs on main thread)."""
        # Schedule the GUI update using lambda to avoid issues if restart_btn is None yet
        self._safe_schedule(lambda: self.restart_btn.config(state=tk.DISABLED) if self.restart_btn and self.restart_btn.winfo_exists() else None)

    def _enable_reset_button(self):
        """Safely enables the manual reset button IF no reset is currently in progress (runs on main thread)."""
        # Check the flag *before* scheduling the GUI update
        if not self.is_resetting:
            # Schedule the GUI update
            self._safe_schedule(lambda: self.restart_btn.config(state=tk.NORMAL) if self.restart_btn and self.restart_btn.winfo_exists() else None)
        else:
             logging.debug("Skipped enabling reset button because a reset is still marked as in progress.")


    # --- Thread-Safe GUI Update Helpers ---
    def _safe_schedule(self, callback_func, *args):
        """ Schedules a function to run as soon as possible on the main Tkinter thread. """
        try:
            # Check if root window exists before scheduling
            if self.root and self.root.winfo_exists():
                self.root.after(0, callback_func, *args) # Use after(0, ...) for immediate scheduling
        except (tk.TclError, RuntimeError) as e:
            # Catch errors if the window is destroyed between the check and `after` call
            # or if the Tkinter loop is not running.
            logging.warning(f"Could not schedule callback '{getattr(callback_func, '__name__', 'unknown')}': {e}")
        except Exception as e:
            logging.exception(f"Unexpected error scheduling callback '{getattr(callback_func, '__name__', 'unknown')}':")


    def _safe_after(self, delay_ms: int, callback_func, *args) -> str | None:
         """ Schedules a function to run after a delay on the main Tkinter thread. Returns timer ID or None. """
         try:
              if self.root and self.root.winfo_exists():
                   # Schedule the callback and return the timer ID
                   timer_id = self.root.after(delay_ms, callback_func, *args)
                   return timer_id
         except (tk.TclError, RuntimeError) as e:
              logging.warning(f"Could not schedule 'after' callback '{getattr(callback_func, '__name__', 'unknown')}': {e}")
         except Exception as e:
              logging.exception(f"Unexpected error scheduling 'after' callback '{getattr(callback_func, '__name__', 'unknown')}':")
         return None # Return None if scheduling failed


    def _cancel_timer(self, timer_id: str | None):
        """ Safely cancels a timer created with `root.after`. """
        if timer_id: # Proceed only if timer_id is not None or empty
            try:
                # Check if root exists before cancelling
                if self.root and self.root.winfo_exists():
                    self.root.after_cancel(timer_id)
                    logging.debug(f"Cancelled Tkinter timer: {timer_id}")
            except tk.TclError as e:
                # This often happens if the timer already fired or the ID is invalid
                logging.warning(f"Could not cancel timer {timer_id} (TclError, likely already fired/invalid): {e}")
            except ValueError as e: # Can also raise ValueError for invalid IDs
                logging.warning(f"Could not cancel timer {timer_id} (ValueError, likely invalid): {e}")
            except Exception as e: # Catch any other unexpected error
                logging.error(f"Unexpected error cancelling timer {timer_id}: {e}")


    def _cancel_all_timers(self):
        """ Cancels all known scheduled Tkinter timers. """
        logging.debug("Cancelling all known application timers...")
        self._cancel_timer(self.auto_export_timer)
        self.auto_export_timer = None
        self._cancel_timer(self.auto_reset_timer)
        self.auto_reset_timer = None
        self._cancel_timer(self.status_reset_timer)
        self.status_reset_timer = None
        logging.debug("All known timers cancelled.")


# --- Main Execution ---
if __name__ == '__main__':
    # Configure basic logging
    log_format = '%(asctime)s - %(levelname)-8s - %(threadName)-16s - %(filename)s:%(lineno)d - %(message)s'
    logging.basicConfig(
        level=logging.INFO, # Change to DEBUG for more detailed logs
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # --- Optional: Add file logging handler ---
    log_filename = "modem_reset_tool.log"
    try:
        # Use RotatingFileHandler for log rotation (optional but recommended)
        from logging.handlers import RotatingFileHandler
        # Rotate log file when it reaches 5MB, keep 3 backup files
        file_handler = RotatingFileHandler(log_filename, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)
        logging.info(f"File logging configured to '{log_filename}'.")
    except ImportError:
         logging.warning("RotatingFileHandler not available. Using basic FileHandler.")
         try:
             log_file_handler = logging.FileHandler(log_filename, encoding='utf-8')
             log_file_handler.setFormatter(logging.Formatter(log_format))
             logging.getLogger().addHandler(log_file_handler)
             logging.info(f"Basic file logging configured to '{log_filename}'.")
         except Exception as log_e:
              logging.error(f"Failed to configure file logging: {log_e}")
    except Exception as log_e:
         logging.error(f"Failed to configure file logging: {log_e}")
    # --- End Optional File Logging ---

    logging.info(f"Starting {APP_NAME} v{APP_VERSION}")

    try:
        root = tk.Tk()
        app = ModemResetApp(root)
        root.mainloop() # Start the Tkinter event loop
        logging.info(f"{APP_NAME} exited normally.")
    except Exception as e:
         # Log fatal errors during startup or runtime
         logging.exception("Fatal error encountered:")
         # Attempt to show a final error message if Tkinter might still be usable
         try:
              # Check if a root window was ever created
              if 'root' in locals() and isinstance(root, tk.Tk):
                   parent = root
              else: # If root wasn't even created, can't show messagebox relative to it
                   parent = None
              messagebox.showerror("Lỗi Nghiêm Trọng", f"Ứng dụng gặp lỗi nghiêm trọng và phải đóng:\n\n{type(e).__name__}: {e}\n\nVui lòng kiểm tra file log '{log_filename}' để biết chi tiết.", parent=parent)
         except Exception as final_e:
              logging.error(f"Could not display final error messagebox: {final_e}")