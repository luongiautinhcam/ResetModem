import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import base64
import threading
import time
import os
import configparser
from datetime import datetime
import logging
import re # Import regex for parsing geometry

# --- Constants ---
APP_NAME = "Modem Reset Tool v1.0.1"
APP_VERSION = "1.1.0"
CONFIG_FILE = 'config.ini'
MODEM_IP = 'http://192.168.0.1'
LOGIN_URL = f'{MODEM_IP}/reqproc/proc_post'
IP_CHECK_INTERVAL_SECONDS = 10
LOG_UPDATE_INTERVAL_SECONDS = 5
DEFAULT_LOG_INTERVAL = 0
DEFAULT_AUTO_RESET_INTERVAL = 0 # Default: disabled
ICON_PATH = r"C:\Projects\ResetModem\icons\app_icon.ico" # Giữ nguyên hoặc thay đổi nếu cần

# Configuration Sections/Keys
CONFIG_SECTION_WINDOW = 'WINDOW'
CONFIG_KEY_POS_X = 'pos_x'
CONFIG_KEY_POS_Y = 'pos_y'
CONFIG_SECTION_CREDS = 'CREDENTIALS'
CONFIG_KEY_PASSWORD = 'password'
CONFIG_SECTION_LOGGING = 'LOGGING'
CONFIG_KEY_LOG_DIR = 'log_directory'
CONFIG_KEY_LOG_INTERVAL = 'log_interval'
# --- NEW Config Keys ---
CONFIG_SECTION_AUTO_RESET = 'AUTO_RESET'
CONFIG_KEY_AUTO_RESET_ENABLED = 'enabled'
CONFIG_KEY_AUTO_RESET_INTERVAL = 'interval_seconds'
# -----------------------


# --- Helper Function for Centering Windows (Unchanged) ---
def center_window(window, width, height, parent=None):
    """Centers a Tkinter window on the screen or relative to a parent."""
    window.update_idletasks() # Ensure window dimensions are calculated
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    if parent:
        parent_geo = parent.winfo_geometry()
        try: # Robust parsing
            match = re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", parent_geo)
            if match:
                parent_w, parent_h, parent_x, parent_y = map(int, match.groups())
                x = parent_x + (parent_w // 2) - (width // 2)
                y = parent_y + (parent_h // 2) - (height // 2)
            else: # Fallback if parsing fails
                x = (screen_width // 2) - (width // 2)
                y = (screen_height // 2) - (height // 2)
        except Exception: # Broad exception for parsing safety
             x = (screen_width // 2) - (width // 2)
             y = (screen_height // 2) - (height // 2)
    else:
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')


# --- Settings Window (Unchanged) ---
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.transient(parent_app.root)
        self.title("Cài đặt Lưu Log")
        self.resizable(False, False)
        self.grab_set()
        settings_width = 450
        settings_height = 200
        # self.geometry(f"{settings_width}x{settings_height}") # Centering handles this
        self.log_dir_var = tk.StringVar(value=parent_app.log_directory or "Chưa chọn thư mục")
        self.log_interval_var = tk.StringVar(value=str(parent_app.log_interval))
        frm = ttk.Frame(self, padding="10"); frm.pack(expand=True, fill="both")
        ttk.Label(frm, text="Thư mục lưu log:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        dir_entry = ttk.Entry(frm, textvariable=self.log_dir_var, state="readonly", width=40)
        dir_entry.grid(row=1, column=0, padx=5, pady=2, sticky="ew")
        dir_button = ttk.Button(frm, text="Chọn...", command=self.select_directory)
        dir_button.grid(row=1, column=1, padx=5, pady=2)
        ttk.Label(frm, text="Tự động lưu mỗi (giây, 0 = tắt):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        interval_entry = ttk.Entry(frm, textvariable=self.log_interval_var, width=10)
        interval_entry.grid(row=3, column=0, padx=5, pady=2, sticky="w")
        btn_frm = ttk.Frame(frm); btn_frm.grid(row=4, column=0, columnspan=2, pady=15, sticky="e")
        save_btn = ttk.Button(btn_frm, text="Lưu", command=self.save_settings); save_btn.pack(side="left", padx=5)
        cancel_btn = ttk.Button(btn_frm, text="Hủy", command=self.destroy); cancel_btn.pack(side="left", padx=5)
        interval_entry.focus(); interval_entry.bind("<Return>", lambda event: self.save_settings())
        center_window(self, settings_width, settings_height, parent=parent_app.root)

    def select_directory(self):
        initial_dir = self.parent_app.log_directory or os.getcwd()
        directory = filedialog.askdirectory(parent=self,title="Chọn thư mục để lưu file log",initialdir=initial_dir)
        if directory: self.log_dir_var.set(directory)

    def save_settings(self):
        try:
            interval = int(self.log_interval_var.get())
            if interval < 0: raise ValueError
        except ValueError: messagebox.showerror("Lỗi", "Thời gian tự động lưu phải là một số nguyên không âm (giây).", parent=self); return
        directory = self.log_dir_var.get()
        if (not directory or directory == "Chưa chọn thư mục") and interval > 0:
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục lưu log nếu bật tự động lưu.", parent=self); return
        elif (not directory or directory == "Chưa chọn thư mục"): directory = None
        self.parent_app.update_log_settings(directory, interval); self.destroy()


# --- Main Application ---
class ModemResetApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.app_width = 550 # Store dimensions for later use
        self.app_height = 450 # Increased height for new controls
        self.root.resizable(False, False)
        # Set base size - position will be set later
        self.root.geometry(f"{self.app_width}x{self.app_height}")

        # --- Configuration object ---
        self.config = configparser.ConfigParser()
        self.last_pos_x = None # Store loaded position
        self.last_pos_y = None

        # --- Set Application Icon ---
        try:
            if os.path.exists(ICON_PATH): self.root.iconbitmap(ICON_PATH)
            else: print(f"Warning: Icon file not found at {ICON_PATH}")
        except Exception as e: print(f"Warning: Could not set icon: {e}")

        # --- App state ---
        self.password_var = tk.StringVar()
        self.save_password_var = tk.BooleanVar()
        # --- NEW Auto Reset State ---
        self.auto_reset_interval_var = tk.StringVar(value=str(DEFAULT_AUTO_RESET_INTERVAL))
        self.auto_reset_enabled_var = tk.BooleanVar(value=False)
        self.auto_reset_timer = None
        self.is_resetting = False # Flag to prevent concurrent resets
        # ----------------------------
        self.public_ip = "Đang lấy IP..."
        self.is_connected = None
        self.lock = threading.Lock() # For thread-safe access to shared state
        self.last_action = None
        self.log_directory = None
        self.log_interval = DEFAULT_LOG_INTERVAL
        self.auto_export_timer = None

        # Create UI Elements
        self.create_menu()
        self.create_widgets()

        # Load config FIRST
        self.load_config()

        # --- Restore Position or Center ---
        if self.last_pos_x is not None and self.last_pos_y is not None:
            print(f"Restoring window position to +{self.last_pos_x}+{self.last_pos_y}")
            self.root.geometry(f"+{self.last_pos_x}+{self.last_pos_y}")
        else:
            print("No saved position found, centering window.")
            center_window(self.root, self.app_width, self.app_height)

        # Schedule tasks AFTER UI is mostly set up and config loaded
        self.schedule_auto_export()
        self.schedule_auto_reset() # <-- Schedule auto reset based on loaded config
        self.update_ip_periodically()
        self.update_log_periodically()
        threading.Thread(target=self.update_ip_now, daemon=True).start() # Initial IP fetch

        # --- Intercept Close Event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Handle X button


    def create_menu(self):
        menubar = tk.Menu(self.root)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Cài đặt Log...", command=self.open_settings_window)
        options_menu.add_command(label="Thông tin...", command=self.show_about_info) # <-- NEW
        options_menu.add_separator()
        options_menu.add_command(label="Thoát", command=self.on_closing) # Use same closing logic
        menubar.add_cascade(label="Tùy chọn", menu=options_menu)
        self.root.config(menu=menubar)

    def create_widgets(self):
        # --- Top Frame for Controls ---
        frm_top = ttk.Frame(self.root, padding=(10, 10, 10, 5))
        frm_top.pack(fill='x')
        frm_top.columnconfigure(1, weight=1) # Allow entry fields to expand slightly if needed

        # --- Password Row ---
        ttk.Label(frm_top, text="Mật khẩu modem:").grid(row=0, column=0, sticky='w', padx=(0,5), pady=3)
        pw_frame = ttk.Frame(frm_top)
        pw_frame.grid(row=0, column=1, columnspan=2, sticky='w')
        self.password_entry = ttk.Entry(pw_frame, textvariable=self.password_var, show="*", width=15)
        self.password_entry.pack(side='left', padx=(0,5))
        self.save_password_chk = ttk.Checkbutton(pw_frame, text="Lưu", variable=self.save_password_var)
        self.save_password_chk.pack(side='left')

        # --- Auto Reset Row --- NEW ---
        ttk.Label(frm_top, text="Tự động reset (giây):").grid(row=1, column=0, sticky='w', padx=(0,5), pady=3)
        reset_frame = ttk.Frame(frm_top)
        reset_frame.grid(row=1, column=1, columnspan=2, sticky='w')
        self.auto_reset_interval_entry = ttk.Entry(reset_frame, textvariable=self.auto_reset_interval_var, width=15)
        self.auto_reset_interval_entry.pack(side='left', padx=(0,5))
        self.auto_reset_enabled_chk = ttk.Checkbutton(
            reset_frame,
            text="Bật",
            variable=self.auto_reset_enabled_var,
            command=self.schedule_auto_reset
        )
        self.auto_reset_enabled_chk.pack(side='left')
        self.auto_reset_interval_entry.bind("<Return>", lambda event: self.schedule_auto_reset())
        self.auto_reset_interval_entry.bind("<FocusOut>", lambda event: self.schedule_auto_reset())
        # -----------------------------

        # --- Manual Reset Button ---
        self.restart_btn = ttk.Button(frm_top, text="Reset Modem Thủ Công", command=self.restart_modem, width=25)
        # Note: Row index increased due to new auto-reset row
        self.restart_btn.grid(row=2, column=1, pady=10, ipady=3, sticky='w', padx=(0,5))

        # --- IP Label ---
        self.ip_label = ttk.Label(frm_top, text=f"IP Public: {self.public_ip}", width=40, anchor='w')
         # Note: Row index increased
        self.ip_label.grid(row=3, column=0, columnspan=3, pady=5, sticky='w')

        # --- Separator and Log Tree ---
        ttk.Separator(self.root).pack(fill='x', pady=5, padx=10)
        log_frame = ttk.LabelFrame(self.root, text="Lịch sử hoạt động", padding=5) # Use LabelFrame
        log_frame.pack(fill='both', expand=True, padx=10, pady=(0,10))

        columns = ("time", "ip", "status")
        self.tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=10) # Slightly reduce height
        self.tree.heading("time", text="Thời gian", anchor='w')
        self.tree.heading("ip", text="IP", anchor='w')
        self.tree.heading("status", text="Trạng thái", anchor='w')
        self.tree.column("time", width=140, anchor='w', stretch=tk.NO)
        self.tree.column("ip", width=120, anchor='w', stretch=tk.NO)
        self.tree.column("status", width=250, anchor='w') # Auto-adjust width

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Use grid within log_frame for easier expansion control
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')


    def load_config(self):
        """Loads configuration from file into self.config and sets app state."""
        if not os.path.exists(CONFIG_FILE):
            print("Config file not found.")
            return # Keep defaults

        try:
            self.config.read(CONFIG_FILE)

            # --- Load Password ---
            if self.config.has_section(CONFIG_SECTION_CREDS):
                saved_pw = self.config.get(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, fallback='')
                if saved_pw:
                    self.password_var.set(saved_pw)
                    self.save_password_var.set(True)

            # --- Load Log Settings ---
            if self.config.has_section(CONFIG_SECTION_LOGGING):
                self.log_directory = self.config.get(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, fallback=None)
                if not self.log_directory: self.log_directory = None # Ensure empty string becomes None
                self.log_interval = self.config.getint(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, fallback=DEFAULT_LOG_INTERVAL)
                if self.log_interval < 0: self.log_interval = DEFAULT_LOG_INTERVAL

            # --- Load Auto Reset Settings --- NEW ---
            if self.config.has_section(CONFIG_SECTION_AUTO_RESET):
                 enabled = self.config.getboolean(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_ENABLED, fallback=False)
                 interval = self.config.getint(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, fallback=DEFAULT_AUTO_RESET_INTERVAL)
                 if interval < 0: interval = DEFAULT_AUTO_RESET_INTERVAL # Ensure non-negative

                 self.auto_reset_enabled_var.set(enabled)
                 self.auto_reset_interval_var.set(str(interval))
            # ------------------------------------

            # --- Load Window Position ---
            if self.config.has_section(CONFIG_SECTION_WINDOW):
                self.last_pos_x = self.config.getint(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, fallback=None)
                self.last_pos_y = self.config.getint(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, fallback=None)

        except (configparser.Error, ValueError, TypeError) as e: # Catch potential errors during conversion
            print(f"Error reading config file or invalid value: {e}")
            # Don't show messagebox here, just use defaults or whatever was loaded before error
            # Reset potentially corrupted values to defaults
            self.log_directory = self.log_directory or None
            self.log_interval = self.log_interval if isinstance(self.log_interval, int) and self.log_interval >= 0 else DEFAULT_LOG_INTERVAL
            self.last_pos_x = self.last_pos_x if isinstance(self.last_pos_x, int) else None
            self.last_pos_y = self.last_pos_y if isinstance(self.last_pos_y, int) else None
            # Reset new settings as well
            is_enabled = self.auto_reset_enabled_var.get() if isinstance(self.auto_reset_enabled_var.get(), bool) else False
            try: interval_val = int(self.auto_reset_interval_var.get())
            except: interval_val = DEFAULT_AUTO_RESET_INTERVAL
            if interval_val < 0: interval_val = DEFAULT_AUTO_RESET_INTERVAL
            self.auto_reset_enabled_var.set(is_enabled)
            self.auto_reset_interval_var.set(str(interval_val))


    def save_config(self):
        """Saves current app state into self.config and writes to file."""
        print("Saving configuration...")
        # --- Ensure sections exist ---
        if not self.config.has_section(CONFIG_SECTION_CREDS): self.config.add_section(CONFIG_SECTION_CREDS)
        if not self.config.has_section(CONFIG_SECTION_LOGGING): self.config.add_section(CONFIG_SECTION_LOGGING)
        if not self.config.has_section(CONFIG_SECTION_WINDOW): self.config.add_section(CONFIG_SECTION_WINDOW)
        if not self.config.has_section(CONFIG_SECTION_AUTO_RESET): self.config.add_section(CONFIG_SECTION_AUTO_RESET) # <-- NEW

        # --- Save Password ---
        if self.save_password_var.get():
            self.config.set(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, self.password_var.get())
        elif self.config.has_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD):
            self.config.remove_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD)

        # --- Save Log Settings ---
        self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, str(self.log_interval))
        self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, self.log_directory or '') # Save empty if None

        # --- Save Auto Reset Settings --- NEW ---
        self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_ENABLED, str(self.auto_reset_enabled_var.get()))
        try:
            interval_to_save = int(self.auto_reset_interval_var.get())
            if interval_to_save < 0: interval_to_save = DEFAULT_AUTO_RESET_INTERVAL
            self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, str(interval_to_save))
        except ValueError:
            # Save default if current value is invalid somehow
             self.config.set(CONFIG_SECTION_AUTO_RESET, CONFIG_KEY_AUTO_RESET_INTERVAL, str(DEFAULT_AUTO_RESET_INTERVAL))
        # ------------------------------------

        # --- Save Window Position (Get latest valid position) ---
        current_x, current_y = self.get_current_window_position()
        if current_x is not None and current_y is not None:
             self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, str(current_x))
             self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, str(current_y))
        elif self.last_pos_x is not None and self.last_pos_y is not None:
            # Fallback to last loaded position if current couldn't be read
             self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, str(self.last_pos_x))
             self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, str(self.last_pos_y))

        # --- Write to file ---
        try:
            with open(CONFIG_FILE, 'w') as configfile:
                self.config.write(configfile)
            print("Configuration saved successfully.")
        except IOError as e:
             print(f"Error writing config file: {e}")
             # Avoid showing messagebox during shutdown if possible
             # messagebox.showerror("Lỗi Lưu Config", f"Không thể ghi vào tệp {CONFIG_FILE}.", parent=self.root)


    def get_current_window_position(self):
        """Safely gets the current window's top-left corner coordinates."""
        try:
            # Ensure window exists before getting geometry
            if self.root and self.root.winfo_exists():
                geometry = self.root.winfo_geometry()
                match = re.search(r"\+(\d+)\+(\d+)$", geometry) # Find +X+Y at the end
                if match:
                    x = int(match.group(1))
                    y = int(match.group(2))
                    # Basic screen bounds check (optional but good)
                    screen_w = self.root.winfo_screenwidth()
                    screen_h = self.root.winfo_screenheight()
                    if 0 <= x < screen_w and 0 <= y < screen_h:
                        return x, y
                    else:
                        print("Warning: Window position seems off-screen, not saving.")
                        return None, None
                else:
                    print("Could not parse window geometry to get position.")
                    return None, None
        except Exception as e:
            print(f"Error getting window geometry: {e}")
        return None, None


    def on_closing(self):
        """Called when the window is closed via X button or Exit menu."""
        # --- NEW: Ask for confirmation ---
        if messagebox.askyesno("Xác nhận thoát", f"Bạn có chắc chắn thoát {APP_NAME}?", parent=self.root):
            print("Closing application...")
            # Stop timers to prevent issues during shutdown
            if self.auto_export_timer: self.root.after_cancel(self.auto_export_timer)
            if self.auto_reset_timer: self.root.after_cancel(self.auto_reset_timer)

            # Save all settings
            self.save_config()

            # Cleanly destroy the window
            if self.root.winfo_exists():
                self.root.destroy()
        else:
            print("Close cancelled by user.")


    def show_about_info(self):
        """Displays application information in a messagebox."""
        # --- NEW ---
        info_text = f"""{APP_NAME}
Phiên bản: {APP_VERSION}

Chức năng:
- Theo dõi địa chỉ IP public.
- Reset modem Viettel H646EW qua giao diện web.
- Lưu lịch sử hoạt động và IP.
- Tùy chọn tự động reset modem định kỳ.
- Lưu/khôi phục cài đặt và vị trí cửa sổ."""
        messagebox.showinfo("Thông tin", info_text, parent=self.root)


    def open_settings_window(self):
        SettingsWindow(self)

    def update_log_settings(self, directory, interval):
        self.log_directory = directory
        self.log_interval = interval
        print(f"Updated log settings: Dir='{self.log_directory}', Interval={self.log_interval}s")
        self.schedule_auto_export() # Reschedule timer with new settings


    def schedule_auto_export(self):
        """Schedules or cancels the automatic log export timer."""
        if self.auto_export_timer:
             try: self.root.after_cancel(self.auto_export_timer)
             except ValueError: pass # Timer might already be invalid
             self.auto_export_timer = None

        if self.log_interval > 0 and self.log_directory:
            # Check directory validity *before* scheduling
            if not os.path.isdir(self.log_directory):
                 print(f"Log directory '{self.log_directory}' not found. Disabling auto-export.")
                 # Optionally notify user or reset interval? For now, just disable.
                 return # Don't schedule if dir is bad

            print(f"Scheduling auto log export every {self.log_interval} seconds.")
            delay_ms = self.log_interval * 1000
            # Ensure root still exists before scheduling
            if self.root and self.root.winfo_exists():
                 self.auto_export_timer = self.root.after(delay_ms, self.perform_auto_export)


    def perform_auto_export(self):
        """Exports current log entries to a file and reschedules the timer."""
        # Check if root window still exists before proceeding
        if not self.root or not self.root.winfo_exists():
            print("Auto export cancelled: Root window destroyed.")
            return

        log_items = []
        try: # Protect against Treeview being destroyed mid-operation
             if self.tree.winfo_exists():
                 log_items = self.tree.get_children('')
        except tk.TclError:
             print("Auto export cancelled: Treeview widget destroyed.")
             return # Stop if treeview gone

        if not log_items:
            print("No logs to export automatically.")
            self.schedule_auto_export() # Reschedule for next time
            return

        # Ensure log directory is still valid
        if not self.log_directory or not os.path.isdir(self.log_directory):
             messagebox.showerror("Lỗi Xuất Log", f"Thư mục log '{self.log_directory or ''}' không hợp lệ hoặc không tồn tại.\nTự động xuất log bị tạm dừng.", parent=self.root if self.root.winfo_exists() else None)
             print(f"Auto log export failed: Directory '{self.log_directory or ''}' invalid.")
             # Don't reschedule until settings are fixed by user
             if self.auto_export_timer: self.root.after_cancel(self.auto_export_timer); self.auto_export_timer = None
             return

        # Proceed with export
        log_data = []
        try:
             if self.tree.winfo_exists():
                  log_data = ["\t".join(map(str, self.tree.item(item_id, 'values'))) for item_id in log_items if self.tree.item(item_id, 'values')] # Safer check
        except tk.TclError:
             print("Auto export failed: Error accessing Treeview items.")
             self.schedule_auto_export() # Try again later
             return

        if not log_data: # Check if list is empty after trying to read
            print("No valid log data retrieved for auto export.")
            self.schedule_auto_export()
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"logs-{timestamp}.txt"
        full_path = os.path.join(self.log_directory, filename)

        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write("Thời gian\tIP\tTrạng thái\n")
                f.write("="*40 + "\n")
                f.write("\n".join(log_data))
            print(f"Successfully auto-exported logs to: {full_path}")
            # Safely delete items from treeview
            if self.tree.winfo_exists():
                self.tree.delete(*log_items)
        except (IOError, OSError, tk.TclError) as e: # Catch file errors and potential Tcl errors
            messagebox.showerror("Lỗi Xuất Log", f"Không thể ghi vào file log:\n{full_path}\nLỗi: {e}", parent=self.root if self.root.winfo_exists() else None)
            print(f"Auto log export failed: {type(e).__name__} - {e}")
        except Exception as e:
            messagebox.showerror("Lỗi Xuất Log", f"Lỗi không xác định khi ghi file log:\n{e}", parent=self.root if self.root.winfo_exists() else None)
            print(f"Auto log export failed: Unexpected error - {e}")
        finally:
             # ALWAYS reschedule, even if export failed, unless dir was invalid
             if self.log_directory and os.path.isdir(self.log_directory):
                  self.schedule_auto_export()


    # --- NEW Auto Reset Methods ---
    def schedule_auto_reset(self):
        """Schedules or cancels the automatic modem reset timer based on GUI controls."""
        if self.auto_reset_timer:
            try: self.root.after_cancel(self.auto_reset_timer)
            except ValueError: pass
            self.auto_reset_timer = None

        is_enabled = self.auto_reset_enabled_var.get()
        interval_str = self.auto_reset_interval_var.get()

        if is_enabled:
            try:
                interval_sec = int(interval_str)
                if interval_sec <= 0:
                    # print("Auto reset interval must be positive. Disabling.")
                    # self.auto_reset_enabled_var.set(False) # Optionally uncheck box if invalid
                    return # Don't schedule
            except ValueError:
                # print("Invalid auto reset interval. Disabling.")
                # self.auto_reset_enabled_var.set(False) # Optionally uncheck box if invalid
                return # Don't schedule

            print(f"Scheduling auto modem reset every {interval_sec} seconds.")
            delay_ms = interval_sec * 1000
            # Ensure root still exists before scheduling
            if self.root and self.root.winfo_exists():
                self.auto_reset_timer = self.root.after(delay_ms, self.perform_auto_reset)
        else:
             print("Auto reset disabled.")


    def perform_auto_reset(self):
        """Initiates an automatic modem reset if conditions met and reschedules."""
         # Check if root window still exists
        if not self.root or not self.root.winfo_exists():
            print("Auto reset cancelled: Root window destroyed.")
            return

        # Check if a reset (manual or auto) is already in progress
        if self.is_resetting:
            print("Auto reset skipped: Another reset is already in progress.")
            # Reschedule for the next interval
            self.schedule_auto_reset()
            return

        # Check if enabled and interval is still valid *just before* resetting
        is_enabled = self.auto_reset_enabled_var.get()
        try:
            interval_sec = int(self.auto_reset_interval_var.get())
            if interval_sec <= 0: is_enabled = False # Treat invalid interval as disabled
        except ValueError:
            is_enabled = False

        if not is_enabled:
            print("Auto reset cancelled: Feature disabled or interval invalid.")
            # Ensure timer is cancelled if it somehow got here while disabled
            if self.auto_reset_timer: self.root.after_cancel(self.auto_reset_timer); self.auto_reset_timer = None
            return

        print(f"Performing scheduled auto reset (interval: {interval_sec}s)...")
        self.set_last_action(f"Tự động reset (chu kỳ {interval_sec}s)")
        self.safe_update_log()
        # Call the main reset function (which runs in a thread)
        self.restart_modem(is_auto=True)

        # restart_modem will eventually call reset_action_status which clears is_resetting.
        # We need to reschedule the *next* auto reset check here.
        self.schedule_auto_reset()


    # --- IP and Log Update Methods (Mostly Unchanged, added safety checks) ---
    def get_public_ip(self):
        try:
            response = requests.get("https://api.ipify.org", timeout=5)
            response.raise_for_status()
            return response.text.strip()
        except requests.exceptions.RequestException as e:
            print(f"Error getting public IP: {e}")
            return "Không xác định"

    def update_ip_now(self):
        # Check if window still exists
        if not self.root or not self.root.winfo_exists(): return
        ip = self.get_public_ip()
        ip_changed = False
        connection_status_changed = False
        with self.lock:
            if ip != self.public_ip: ip_changed = True; self.public_ip = ip
            newly_connected = (ip != "Không xác định")
            if self.is_connected is None or self.is_connected != newly_connected: connection_status_changed = True; self.is_connected = newly_connected

        # Update label safely
        try:
             if self.ip_label and self.ip_label.winfo_exists() and ip_changed:
                  self.ip_label.config(text=f"IP Public: {ip}")
        except tk.TclError: pass # Widget might be destroyed

    def update_ip_periodically(self):
        def update():
            while True:
                # Check root window existence at the start of each loop iteration
                if not self.root or not self.root.winfo_exists(): break
                try:
                    self.update_ip_now()
                except Exception as e: # Catch unexpected errors in the loop
                    print(f"Error in IP update thread: {e}")
                # Use a shorter sleep if window is gone to exit thread sooner
                sleep_time = IP_CHECK_INTERVAL_SECONDS if self.root and self.root.winfo_exists() else 0.5
                time.sleep(sleep_time)
            print("IP update thread finished.") # Indicate thread exit
        threading.Thread(target=update, daemon=True).start()

    def update_log_periodically(self):
        def update():
            while True:
                 # Check root window existence
                if not self.root or not self.root.winfo_exists(): break
                try:
                    self.update_log_now()
                except Exception as e: # Catch unexpected errors
                    print(f"Error in Log update thread: {e}")
                # Use a shorter sleep if window is gone
                sleep_time = LOG_UPDATE_INTERVAL_SECONDS if self.root and self.root.winfo_exists() else 0.5
                time.sleep(sleep_time)
            print("Log update thread finished.") # Indicate thread exit
        threading.Thread(target=update, daemon=True).start()

    def update_log_now(self):
        # Check if window and tree exist
        if not self.root or not self.root.winfo_exists() or not self.tree or not self.tree.winfo_exists(): return

        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        log_status = "Đang kiểm tra..."
        with self.lock:
            ip = self.public_ip
            action = self.last_action
            connected = self.is_connected

            # Determine status based on state
            if action and action != "Bình thường":
                log_status = action
            elif connected is None:
                log_status = "Đang kiểm tra kết nối..."
            elif connected:
                log_status = "Hoạt động bình thường"
            else:
                log_status = "Mất kết nối Internet"

        # Insert into treeview safely
        try:
            self.tree.insert('', 0, values=(now, ip, log_status))
            # Limit log entries (optional, keeps GUI responsive)
            # children = self.tree.get_children('')
            # if len(children) > 100: # Keep last 100 entries
            #     self.tree.delete(children[100:])
        except tk.TclError: pass # Widget might be destroyed between check and insert
        except Exception as e: print(f"Error updating log tree: {e}")


    def set_last_action(self, action_message):
        with self.lock:
            self.last_action = action_message

    # --- Modified restart_modem to handle is_auto flag and is_resetting flag ---
    def restart_modem(self, is_auto=False): # Added is_auto flag
        password = self.password_var.get()
        if not password:
            messagebox.showerror("Lỗi", "Vui lòng nhập mật khẩu modem", parent=self.root)
            return

        # Prevent concurrent resets
        if self.is_resetting:
            action_type = "Tự động" if is_auto else "Thủ công"
            print(f"{action_type} reset skipped: Reset already in progress.")
            # Optionally show a message to the user for manual clicks?
            if not is_auto:
                messagebox.showinfo("Thông báo", "Modem đang trong quá trình reset.", parent=self.root)
            return

        # --- Start Reset Process ---
        self.is_resetting = True # Set flag
        if self.restart_btn.winfo_exists():
            self.restart_btn.config(state=tk.DISABLED) # Disable manual button

        def task():
            encoded_password = base64.b64encode(password.encode()).decode()
            session = requests.Session()
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': MODEM_IP + '/index.html',
                'X-Requested-With': 'XMLHttpRequest',
                'X-Ki-Saas-Ajax-Request': 'Ajax_Request', # Specific header for Viettel modem?
                'User-Agent': 'Mozilla/5.0'
            }
            login_payload = {'goformId': 'LOGIN', 'password': encoded_password}
            action_reset_timer_id = None # Store timer ID

            def reset_action_status():
                self.set_last_action("Bình thường")
                # Safely re-enable button and clear flag
                self.is_resetting = False # Clear flag *before* potentially triggering new resets
                try:
                    if self.root and self.root.winfo_exists():
                        if self.restart_btn.winfo_exists():
                             self.restart_btn.config(state=tk.NORMAL)
                        self.update_log_now() # Update log one last time
                except tk.TclError: pass # Window/widget might be gone

            try:
                action_msg = "Đang đăng nhập modem..."
                self.set_last_action(action_msg)
                self.safe_update_log()

                login_response = session.post(LOGIN_URL, data=login_payload, headers=headers, timeout=10)
                login_response.raise_for_status() # Check for HTTP errors

                # Check login result (adjust based on actual modem response)
                if '"result":"0"' in login_response.text: # Successful login
                    reboot_payload = {'goformId': 'REBOOT_DEVICE'}
                    try:
                        action_msg = "Đang gửi lệnh reset..."
                        self.set_last_action(action_msg)
                        self.safe_update_log()

                        reboot_response = session.post(LOGIN_URL, data=reboot_payload, headers=headers, timeout=10)
                        reboot_response.raise_for_status()

                        # Check reboot command result (if modem provides one, otherwise assume OK)
                        # if '"result":"0"' in reboot_response.text: # Example check
                        action_msg = "Reset modem (đang khởi động lại)"
                        self.set_last_action(action_msg)
                        self.safe_update_log()
                        action_reset_timer_id = self.safe_after(15000, reset_action_status) # Reset status after 15s

                    except requests.exceptions.RequestException as e:
                        error_msg = str(e).splitlines()[0][:50] # Get first line, limit length
                        action_msg = f"Lỗi gửi lệnh reset: {error_msg}"
                        self.set_last_action(action_msg)
                        self.safe_update_log()
                        action_reset_timer_id = self.safe_after(5000, reset_action_status)

                elif '"result":"1"' in login_response.text or 'login_fail' in login_response.text: # Login failed
                    action_msg = "Sai mật khẩu modem"
                    self.set_last_action(action_msg)
                    self.safe_update_log()
                    action_reset_timer_id = self.safe_after(5000, reset_action_status)
                else: # Unknown login response
                    action_msg = "Lỗi đăng nhập không xác định"
                    self.set_last_action(action_msg)
                    self.safe_update_log()
                    action_reset_timer_id = self.safe_after(5000, reset_action_status)

            except requests.exceptions.Timeout:
                 action_msg = "Lỗi: Modem không phản hồi (timeout)"
                 self.set_last_action(action_msg); self.safe_update_log()
                 action_reset_timer_id = self.safe_after(5000, reset_action_status)
            except requests.exceptions.ConnectionError:
                 action_msg = "Lỗi: Không kết nối được tới modem"
                 self.set_last_action(action_msg); self.safe_update_log()
                 action_reset_timer_id = self.safe_after(5000, reset_action_status)
            except requests.exceptions.RequestException as e:
                 error_msg = str(e).splitlines()[0][:50]
                 action_msg = f"Lỗi kết nối: {error_msg}"
                 self.set_last_action(action_msg); self.safe_update_log()
                 action_reset_timer_id = self.safe_after(5000, reset_action_status)
            except Exception as e: # Catch any other unexpected error in the task
                 action_msg = f"Lỗi không xác định: {str(e)[:50]}"
                 self.set_last_action(action_msg); self.safe_update_log()
                 action_reset_timer_id = self.safe_after(5000, reset_action_status) # Still try to reset status
            finally:
                 # Ensure the flag is cleared if the timer wasn't set or failed
                 if not action_reset_timer_id:
                      print("Reset task finished unexpectedly, ensuring status reset.")
                      reset_action_status() # Directly call if timer failed


        # Start the reset task in a separate thread
        threading.Thread(target=task, daemon=True).start()


    # Helper methods for thread-safe GUI updates (Unchanged but critical)
    def safe_update_log(self):
        """Schedules update_log_now to run in the main Tkinter thread."""
        try:
            if self.root and self.root.winfo_exists():
                self.root.after(0, self.update_log_now)
        except tk.TclError: pass # Root might be destroyed

    def safe_after(self, delay_ms, callback_func):
         """Schedules a callback using root.after, checking if root exists."""
         try:
              if self.root and self.root.winfo_exists():
                   return self.root.after(delay_ms, callback_func)
         except tk.TclError: pass # Root might be destroyed
         return None


if __name__ == '__main__':
    # Setup basic logging to console (optional but helpful for debugging)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    root = tk.Tk()
    app = ModemResetApp(root)
    root.mainloop()