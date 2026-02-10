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
CONFIG_FILE = 'config.ini'
MODEM_IP = 'http://192.168.0.1'
LOGIN_URL = f'{MODEM_IP}/reqproc/proc_post'
IP_CHECK_INTERVAL_SECONDS = 10
LOG_UPDATE_INTERVAL_SECONDS = 5
DEFAULT_LOG_INTERVAL = 0
ICON_PATH = r"C:\Projects\ResetModem\icons\app_icon.ico"

# Configuration Sections/Keys
CONFIG_SECTION_WINDOW = 'WINDOW'
CONFIG_KEY_POS_X = 'pos_x'
CONFIG_KEY_POS_Y = 'pos_y'
CONFIG_SECTION_CREDS = 'CREDENTIALS'
CONFIG_KEY_PASSWORD = 'password'
CONFIG_SECTION_LOGGING = 'LOGGING'
CONFIG_KEY_LOG_DIR = 'log_directory'
CONFIG_KEY_LOG_INTERVAL = 'log_interval'


# --- Helper Function for Centering Windows ---
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
        self.geometry(f"{settings_width}x{settings_height}")
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
        self.root.title("Modem Reset Tool")
        self.app_width = 550 # Store dimensions for later use
        self.app_height = 400
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

        # App state
        self.password_var = tk.StringVar()
        self.save_password_var = tk.BooleanVar()
        self.public_ip = "Đang lấy IP..."
        self.is_connected = None
        self.lock = threading.Lock()
        self.last_action = None
        self.log_directory = None
        self.log_interval = DEFAULT_LOG_INTERVAL
        self.auto_export_timer = None

        # Create UI Elements
        self.create_menu()
        self.create_widgets()

        # Load config FIRST
        self.load_config()

        # --- Restore Position or Center --- ADDED ---
        if self.last_pos_x is not None and self.last_pos_y is not None:
            print(f"Restoring window position to +{self.last_pos_x}+{self.last_pos_y}")
            self.root.geometry(f"+{self.last_pos_x}+{self.last_pos_y}")
        else:
            print("No saved position found, centering window.")
            center_window(self.root, self.app_width, self.app_height)
        # --------------------------------------

        # Schedule tasks AFTER UI is mostly set up
        self.schedule_auto_export()
        self.update_ip_periodically()
        self.update_log_periodically()
        threading.Thread(target=self.update_ip_now, daemon=True).start()

        # --- Intercept Close Event --- ADDED ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # ---------------------------------------


    def create_menu(self):
        menubar = tk.Menu(self.root)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Cài đặt Log...", command=self.open_settings_window)
        options_menu.add_separator()
        # --- MODIFIED: Call on_closing for save ---
        options_menu.add_command(label="Thoát", command=self.on_closing)
        menubar.add_cascade(label="Tùy chọn", menu=options_menu)
        self.root.config(menu=menubar)

    def create_widgets(self):
        # (create_widgets implementation remains unchanged)
        frm_top = ttk.Frame(self.root, padding=(10, 10, 10, 5)); frm_top.pack(fill='x')
        frm_top.columnconfigure(1, weight=1)
        ttk.Label(frm_top, text="Mật khẩu modem:").grid(row=0, column=0, sticky='w', padx=(0,5), pady=2)
        self.password_entry = ttk.Entry(frm_top, textvariable=self.password_var, show="*", width=20)
        self.password_entry.grid(row=0, column=1, sticky='w', padx=5, pady=2)
        self.save_password_chk = ttk.Checkbutton(frm_top, text="Lưu mật khẩu", variable=self.save_password_var)
        self.save_password_chk.grid(row=0, column=2, sticky='e', padx=(10,0), pady=2)
        self.restart_btn = ttk.Button(frm_top, text="Reset Modem", command=self.restart_modem, width=15)
        self.restart_btn.grid(row=1, column=1, pady=8, ipady=3, sticky='w', padx=5)
        self.ip_label = ttk.Label(frm_top, text=f"IP Public: {self.public_ip}", width=40, anchor='w')
        self.ip_label.grid(row=2, column=0, columnspan=3, pady=5, sticky='w')
        ttk.Separator(self.root).pack(fill='x', pady=5, padx=10)
        log_frame = ttk.Frame(self.root); log_frame.pack(fill='both', expand=True, padx=10, pady=(0,10))
        columns = ("time", "ip", "status"); self.tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=11)
        self.tree.heading("time", text="Thời gian", anchor='w'); self.tree.heading("ip", text="IP", anchor='w'); self.tree.heading("status", text="Trạng thái", anchor='w')
        self.tree.column("time", width=140, anchor='w', stretch=tk.NO); self.tree.column("ip", width=120, anchor='w', stretch=tk.NO); self.tree.column("status", width=250, anchor='w')
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")


    def load_config(self):
        """Loads configuration from file into self.config and sets app state."""
        if not os.path.exists(CONFIG_FILE):
            print("Config file not found.")
            return

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

                try:
                    interval_str = self.config.get(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, fallback=str(DEFAULT_LOG_INTERVAL))
                    self.log_interval = int(interval_str)
                    if self.log_interval < 0: self.log_interval = DEFAULT_LOG_INTERVAL
                except ValueError:
                    print(f"Warning: Invalid log interval found in config, using default.")
                    self.log_interval = DEFAULT_LOG_INTERVAL

            # --- Load Window Position --- ADDED ---
            if self.config.has_section(CONFIG_SECTION_WINDOW):
                try:
                    pos_x_str = self.config.get(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, fallback=None)
                    pos_y_str = self.config.get(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, fallback=None)
                    if pos_x_str is not None and pos_y_str is not None:
                        self.last_pos_x = int(pos_x_str)
                        self.last_pos_y = int(pos_y_str)
                        # Basic validation: Ensure not wildly off-screen (optional)
                        # screen_w = self.root.winfo_screenwidth()
                        # screen_h = self.root.winfo_screenheight()
                        # if not (0 <= self.last_pos_x < screen_w and 0 <= self.last_pos_y < screen_h):
                        #     print("Warning: Saved position seems invalid, ignoring.")
                        #     self.last_pos_x = None
                        #     self.last_pos_y = None

                except ValueError:
                    print(f"Warning: Invalid window position found in config, ignoring.")
                    self.last_pos_x = None
                    self.last_pos_y = None
            # --------------------------------

        except configparser.Error as e:
            print(f"Error reading config file: {e}")
            messagebox.showwarning("Lỗi Config", f"Không thể đọc tệp {CONFIG_FILE}. Sử dụng cài đặt mặc định.", parent=self.root)
            # Reset relevant state to defaults if read fails badly
            self.log_directory = None
            self.log_interval = DEFAULT_LOG_INTERVAL
            self.last_pos_x = None
            self.last_pos_y = None


    def save_config(self):
        """Saves current app state (from variables/controls) into self.config and writes to file."""
        print("Saving configuration...")
        # --- Ensure sections exist ---
        if not self.config.has_section(CONFIG_SECTION_CREDS): self.config.add_section(CONFIG_SECTION_CREDS)
        if not self.config.has_section(CONFIG_SECTION_LOGGING): self.config.add_section(CONFIG_SECTION_LOGGING)
        if not self.config.has_section(CONFIG_SECTION_WINDOW): self.config.add_section(CONFIG_SECTION_WINDOW)

        # --- Save Password ---
        if self.save_password_var.get():
            self.config.set(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD, self.password_var.get())
        elif self.config.has_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD):
             # Remove password if checkbox is unchecked but it exists in config
            self.config.remove_option(CONFIG_SECTION_CREDS, CONFIG_KEY_PASSWORD)

        # --- Save Log Settings ---
        self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_INTERVAL, str(self.log_interval))
        self.config.set(CONFIG_SECTION_LOGGING, CONFIG_KEY_LOG_DIR, self.log_directory or '') # Save empty if None

        # --- Save Window Position (if available from on_closing) --- ADDED ---
        if self.last_pos_x is not None and self.last_pos_y is not None:
             self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_X, str(self.last_pos_x))
             self.config.set(CONFIG_SECTION_WINDOW, CONFIG_KEY_POS_Y, str(self.last_pos_y))
        # --------------------------------------------------------

        # --- Write to file ---
        try:
            with open(CONFIG_FILE, 'w') as configfile:
                self.config.write(configfile)
            print("Configuration saved successfully.")
        except IOError as e:
             print(f"Error writing config file: {e}")
             messagebox.showerror("Lỗi Lưu Config", f"Không thể ghi vào tệp {CONFIG_FILE}.", parent=self.root)


    # --- ADDED: Handle application closing ---
    def on_closing(self):
        """Called when the window is closed via X button or Exit menu."""
        print("Closing application...")
        # --- Get current position ---
        try:
            # Ensure window exists before getting geometry
            if self.root.winfo_exists():
                geometry = self.root.winfo_geometry()
                match = re.search(r"\+(\d+)\+(\d+)$", geometry) # Find +X+Y at the end
                if match:
                    self.last_pos_x = int(match.group(1))
                    self.last_pos_y = int(match.group(2))
                    print(f"Saving last position: +{self.last_pos_x}+{self.last_pos_y}")
                else:
                    print("Could not parse window geometry to save position.")
                    # Keep previous values or reset? Let's keep previous if parsing fails.
                    # self.last_pos_x = None
                    # self.last_pos_y = None
        except Exception as e:
            print(f"Error getting window geometry on close: {e}")
            # Keep previous values or reset?
            # self.last_pos_x = None
            # self.last_pos_y = None

        # --- Save all settings ---
        self.save_config()

        # --- Cleanly destroy the window ---
        if self.root.winfo_exists():
            self.root.destroy()
    # --------------------------------------


    def open_settings_window(self):
        SettingsWindow(self)

    def update_log_settings(self, directory, interval):
        self.log_directory = directory
        self.log_interval = interval
        print(f"Updated log settings: Dir='{self.log_directory}', Interval={self.log_interval}s")
        # Don't save config immediately here, let on_closing handle the final save
        # self.save_config()
        self.schedule_auto_export() # Reschedule timer


    def schedule_auto_export(self):
        # (schedule_auto_export implementation remains unchanged)
        if self.auto_export_timer: self.root.after_cancel(self.auto_export_timer); self.auto_export_timer = None
        if self.log_interval > 0 and self.log_directory:
            if not os.path.isdir(self.log_directory):
                 print(f"Log directory '{self.log_directory}' not found. Disabling auto-export.")
                 self.log_interval = 0 # Temporarily disable until fixed
                 # Maybe update config here? Or rely on on_closing? Let's rely on on_closing.
                 return
            delay_ms = self.log_interval * 1000
            self.auto_export_timer = self.root.after(delay_ms, self.perform_auto_export)

    def perform_auto_export(self):
        # (perform_auto_export implementation remains unchanged)
        log_items = self.tree.get_children('');
        if not log_items: self.schedule_auto_export(); return
        log_data = ["\t".join(map(str, self.tree.item(item_id, 'values'))) for item_id in log_items if self.tree.item(item_id, 'values')]
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S"); filename = f"logs-{timestamp}.txt"
        try:
            if not self.log_directory or not os.path.isdir(self.log_directory):
                 messagebox.showerror("Lỗi Xuất Log", f"Thư mục log '{self.log_directory or ''}' không hợp lệ hoặc không tồn tại.", parent=self.root if self.root.winfo_exists() else None)
                 print(f"Log export failed: Directory '{self.log_directory or ''}' invalid."); self.schedule_auto_export(); return
            full_path = os.path.join(self.log_directory, filename)
        except Exception as e:
             messagebox.showerror("Lỗi Đường Dẫn", f"Không thể tạo đường dẫn file log:\n{e}", parent=self.root if self.root.winfo_exists() else None)
             print(f"Log export failed: Path creation error - {e}"); self.schedule_auto_export(); return
        try:
            with open(full_path, 'w', encoding='utf-8') as f: f.write("Thời gian\tIP\tTrạng thái\n"); f.write("="*40 + "\n"); f.write("\n".join(log_data))
            print(f"Successfully exported logs to: {full_path}")
            if self.tree.winfo_exists(): self.tree.delete(*log_items)
        except IOError as e: messagebox.showerror("Lỗi Xuất Log", f"Không thể ghi vào file log:\n{full_path}\nLỗi: {e}", parent=self.root if self.root.winfo_exists() else None); print(f"Log export failed: IOError - {e}")
        except Exception as e: messagebox.showerror("Lỗi Xuất Log", f"Lỗi không xác định khi ghi file log:\n{e}", parent=self.root if self.root.winfo_exists() else None); print(f"Log export failed: Unexpected error - {e}")
        self.schedule_auto_export()


    # --- IP and Log Update Methods (Unchanged) ---
    def get_public_ip(self):
        try: response = requests.get("https://api.ipify.org", timeout=5); response.raise_for_status(); return response.text.strip()
        except requests.exceptions.RequestException: return "Không xác định"

    def update_ip_now(self):
        if not self.root.winfo_exists(): return # Check if window still exists
        ip = self.get_public_ip(); ip_changed = False; connection_status_changed = False
        with self.lock:
            if ip != self.public_ip: ip_changed = True; self.public_ip = ip
            newly_connected = (ip != "Không xác định")
            if self.is_connected is None or self.is_connected != newly_connected: connection_status_changed = True; self.is_connected = newly_connected
        if self.ip_label.winfo_exists() and ip_changed: self.ip_label.config(text=f"IP Public: {ip}")

    def update_ip_periodically(self):
        def update():
            while True:
                if not self.root.winfo_exists(): break
                try: self.update_ip_now()
                except Exception as e: print(f"Error in update_ip_now: {e}") # Add error handling
                time.sleep(IP_CHECK_INTERVAL_SECONDS)
        threading.Thread(target=update, daemon=True).start()

    def update_log_periodically(self):
        def update():
            while True:
                if not self.root.winfo_exists(): break
                try: self.update_log_now()
                except Exception as e: print(f"Error in update_log_now: {e}") # Add error handling
                time.sleep(LOG_UPDATE_INTERVAL_SECONDS)
        threading.Thread(target=update, daemon=True).start()

    def update_log_now(self):
        if not self.root.winfo_exists(): return # Check if window still exists
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S"); log_status = "Đang kiểm tra..."
        with self.lock:
            ip = self.public_ip; action = self.last_action; connected = self.is_connected
            if action and action != "Bình thường": log_status = action
            elif connected is None: log_status = "Đang kiểm tra kết nối..."
            elif connected: log_status = "Hoạt động bình thường"
            else: log_status = "Mất kết nối Internet"
        if self.tree.winfo_exists():
            try: self.tree.insert('', 0, values=(now, ip, log_status))
            except tk.TclError: pass # Widget might be destroyed between check and insert

    def set_last_action(self, action_message):
        with self.lock: self.last_action = action_message

    def restart_modem(self):
        # (restart_modem implementation remains unchanged)
        password = self.password_var.get()
        if not password: messagebox.showerror("Lỗi", "Vui lòng nhập mật khẩu modem", parent=self.root); return
        self.restart_btn.config(state=tk.DISABLED)
        # Don't save config here, wait for on_closing
        # self.save_config()
        def task():
            encoded_password = base64.b64encode(password.encode()).decode(); session = requests.Session()
            headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Referer': MODEM_IP + '/index.html', 'X-Requested-With': 'XMLHttpRequest', 'X-Ki-Saas-Ajax-Request': 'Ajax_Request', 'User-Agent': 'Mozilla/5.0'}
            login_payload = {'goformId': 'LOGIN', 'password': encoded_password}; action_reset_timer = None
            def reset_action_status():
                self.set_last_action("Bình thường")
                if self.root.winfo_exists(): self.restart_btn.config(state=tk.NORMAL); self.update_log_now()
            try:
                self.set_last_action("Đang đăng nhập modem..."); self.safe_update_log()
                login_response = session.post(LOGIN_URL, data=login_payload, headers=headers, timeout=10); login_response.raise_for_status()
                if '"result":"0"' in login_response.text:
                    reboot_payload = {'goformId': 'REBOOT_DEVICE'}
                    try:
                        self.set_last_action("Đang gửi lệnh reset..."); self.safe_update_log()
                        reboot_response = session.post(LOGIN_URL, data=reboot_payload, headers=headers, timeout=10); reboot_response.raise_for_status()
                        self.set_last_action("Reset modem (đang khởi động lại)"); self.safe_update_log()
                        self.safe_after(15000, reset_action_status)
                    except requests.exceptions.RequestException as e:
                        error_msg = str(e).splitlines()[0][:50]; self.set_last_action(f"Lỗi gửi lệnh reset: {error_msg}"); self.safe_update_log()
                        self.safe_after(5000, reset_action_status)
                elif '"result":"1"' in login_response.text or 'login_fail' in login_response.text:
                    self.set_last_action("Sai mật khẩu modem"); self.safe_update_log()
                    self.safe_after(5000, reset_action_status)
                else:
                    self.set_last_action("Lỗi đăng nhập không xác định"); self.safe_update_log()
                    self.safe_after(5000, reset_action_status)
            except requests.exceptions.Timeout:
                 self.set_last_action("Lỗi: Modem không phản hồi (timeout)"); self.safe_update_log()
                 self.safe_after(5000, reset_action_status)
            except requests.exceptions.ConnectionError:
                 self.set_last_action("Lỗi: Không kết nối được tới modem"); self.safe_update_log()
                 self.safe_after(5000, reset_action_status)
            except requests.exceptions.RequestException as e:
                 error_msg = str(e).splitlines()[0][:50]; self.set_last_action(f"Lỗi kết nối: {error_msg}"); self.safe_update_log()
                 self.safe_after(5000, reset_action_status)
        threading.Thread(target=task, daemon=True).start()

    # Helper methods for thread-safe GUI updates from restart_modem thread
    def safe_update_log(self):
        if self.root.winfo_exists():
            self.root.after(0, self.update_log_now)

    def safe_after(self, delay_ms, callback_func):
         if self.root.winfo_exists():
              return self.root.after(delay_ms, callback_func)
         return None


if __name__ == '__main__':
    root = tk.Tk()
    app = ModemResetApp(root)
    root.mainloop()