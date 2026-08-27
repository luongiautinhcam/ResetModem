from pathlib import Path

APP_NAME = "Modem Reset Tool"
APP_VERSION = "1.0.6"
APP_USER_MODEL_ID = "ResetModem.ModemResetTool"
CONFIG_PATH = Path("config.ini")
LOG_PATH = Path("modem_reset_tool.log")
ICON_PATH = Path(__file__).resolve().parent.parent / "icons" / "app_icon.ico"
ICON_PNG_PATH = Path(__file__).resolve().parent.parent / "icons" / "app_icon.png"

MODEM_IP = "http://192.168.0.1"
MODEM_API_URL = f"{MODEM_IP}/reqproc/proc_post"
IP_CHECK_URL = "https://geo.myip.link/"

IP_CHECK_INTERVAL_SECONDS = 10
LOG_UPDATE_INTERVAL_SECONDS = 5
POLL_INTERVAL_MS = 100
DEFAULT_LOG_INTERVAL = 0
DEFAULT_AUTO_RESET_INTERVAL = 0
REQUESTS_TIMEOUT_SECONDS = 10
IP_FETCH_TIMEOUT_SECONDS = 5
STATUS_RESET_DELAY_MS = 5_000
REBOOT_STATUS_RESET_DELAY_MS = 15_000

MODEM_LOGIN_SUCCESS = '"result":"0"'
MODEM_LOGIN_FAILURE = '"result":"1"'
MODEM_LOGIN_COMMAND_ID = "LOGIN"
MODEM_REBOOT_COMMAND = {"goformId": "REBOOT_DEVICE"}

DEFAULT_LANGUAGE = "vi"
SUPPORTED_LANGUAGES = ("vi", "en")

STATUS_NORMAL = "status_normal"
STATUS_CHECKING = "status_checking"
STATUS_DISCONNECTED = "status_disconnected"
STATUS_GETTING_IP = "status_getting_ip"
STATUS_IP_TIMEOUT = "status_ip_timeout"
STATUS_IP_UNKNOWN = "status_ip_unknown"
STATUS_IP_PARSE_ERROR = "status_ip_parse_error"
STATUS_RESET_MANUAL_START = "status_reset_manual_start"
STATUS_RESET_AUTO_START = "status_reset_auto_start:{}"
STATUS_RESET_END_UNKNOWN = "status_reset_end_unknown"
STATUS_LOGIN_ATTEMPT = "status_login_attempt"
STATUS_LOGIN_FAILED = "status_login_failed"
STATUS_LOGIN_UNKNOWN_ERROR = "status_login_unknown_error"
STATUS_REBOOT_COMMAND_SENT = "status_reboot_command_sent"
STATUS_REBOOTING = "status_rebooting"
STATUS_REBOOT_CMD_ERROR = "status_reboot_cmd_error:{}"
STATUS_MODEM_TIMEOUT = "status_modem_timeout"
STATUS_MODEM_CONNECTION_ERROR = "status_modem_connection_error"
STATUS_REQUEST_ERROR = "status_request_error:{}"
STATUS_UNKNOWN_ERROR = "status_unknown_error:{}"

LOG_ERR_CONN_ABORTED = "log_err_conn_aborted"
LOG_ERR_CONN_REFUSED = "log_err_conn_refused"
LOG_ERR_CONN_TIMEOUT = "log_err_conn_timeout"

FINAL_STATUSES = (
    STATUS_NORMAL,
    STATUS_LOGIN_FAILED,
    STATUS_REBOOT_CMD_ERROR.partition("{")[0],
    STATUS_RESET_END_UNKNOWN,
)
