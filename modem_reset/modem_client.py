import base64
import logging
from collections.abc import Callable

import requests

from .constants import (
    LOG_ERR_CONN_ABORTED,
    LOG_ERR_CONN_REFUSED,
    LOG_ERR_CONN_TIMEOUT,
    MODEM_API_URL,
    MODEM_IP,
    MODEM_LOGIN_COMMAND_ID,
    MODEM_LOGIN_FAILURE,
    MODEM_LOGIN_SUCCESS,
    MODEM_REBOOT_COMMAND,
    REBOOT_STATUS_RESET_DELAY_MS,
    REQUESTS_TIMEOUT_SECONDS,
    STATUS_LOGIN_ATTEMPT,
    STATUS_LOGIN_FAILED,
    STATUS_LOGIN_UNKNOWN_ERROR,
    STATUS_MODEM_CONNECTION_ERROR,
    STATUS_MODEM_TIMEOUT,
    STATUS_REBOOT_COMMAND_SENT,
    STATUS_REBOOT_CMD_ERROR,
    STATUS_REBOOTING,
    STATUS_REQUEST_ERROR,
    STATUS_RESET_DELAY_MS,
    STATUS_RESET_END_UNKNOWN,
    STATUS_UNKNOWN_ERROR,
)
from .models import ResetOutcome

StatusCallback = Callable[[str], None]


class ModemClient:
    def __init__(
        self,
        api_url: str = MODEM_API_URL,
        timeout: int = REQUESTS_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ):
        self.api_url = api_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": MODEM_IP + "/index.html",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
                ),
            }
        )

    def reboot(self, password: str, on_status: StatusCallback) -> ResetOutcome:
        final_status = STATUS_RESET_END_UNKNOWN
        clear_after_ms = STATUS_RESET_DELAY_MS
        try:
            encoded_password = base64.b64encode(password.encode("utf-8")).decode("utf-8")
            login_payload = {"goformId": MODEM_LOGIN_COMMAND_ID, "password": encoded_password}
            on_status(STATUS_LOGIN_ATTEMPT)
            try:
                login_response = self.session.post(
                    self.api_url,
                    data=login_payload,
                    timeout=self.timeout,
                )
                login_response.raise_for_status()
                login_text = login_response.text

                if MODEM_LOGIN_SUCCESS in login_text:
                    on_status(STATUS_REBOOT_COMMAND_SENT)
                    try:
                        reboot_response = self.session.post(
                            self.api_url,
                            data=MODEM_REBOOT_COMMAND,
                            timeout=self.timeout,
                        )
                        reboot_response.raise_for_status()
                        final_status = STATUS_REBOOTING
                        clear_after_ms = REBOOT_STATUS_RESET_DELAY_MS
                    except requests.exceptions.Timeout:
                        final_status = STATUS_MODEM_TIMEOUT
                    except requests.exceptions.RequestException as error:
                        final_status = STATUS_REBOOT_CMD_ERROR.format(
                            self.format_request_error(error, "reboot command")
                        )
                elif MODEM_LOGIN_FAILURE in login_text or "login_fail" in login_text:
                    final_status = STATUS_LOGIN_FAILED
                else:
                    final_status = STATUS_LOGIN_UNKNOWN_ERROR
            except requests.exceptions.Timeout:
                final_status = STATUS_MODEM_TIMEOUT
            except requests.exceptions.ConnectionError as error:
                logging.error("Modem login connection failed: %s", error)
                final_status = STATUS_MODEM_CONNECTION_ERROR
            except requests.exceptions.RequestException as error:
                final_status = STATUS_REQUEST_ERROR.format(
                    self.format_request_error(error, "login request")
                )
        except Exception as error:
            logging.exception("Unexpected modem reset failure")
            detail = str(error).splitlines()[0][:70]
            final_status = STATUS_UNKNOWN_ERROR.format(detail)

        return ResetOutcome(final_status, clear_after_ms)

    @staticmethod
    def format_request_error(
        error: requests.exceptions.RequestException,
        context: str = "request",
    ) -> str:
        error_detail = str(error)
        error_message = error_detail.splitlines()[0]
        if isinstance(error, requests.exceptions.ConnectionError) and error.args:
            inner_exception = error.args[0]
            reason = getattr(inner_exception, "reason", None)
            error_message = str(reason or inner_exception).splitlines()[0]

        lower_message = error_message.lower()
        if (
            "[errno 10054]" in lower_message
            or "forcibly closed by the remote host" in lower_message
            or "connection aborted" in lower_message
        ):
            return LOG_ERR_CONN_ABORTED
        if (
            "[errno 10061]" in lower_message
            or "actively refused" in lower_message
            or "connection refused" in lower_message
        ):
            return LOG_ERR_CONN_REFUSED
        if "timed out" in lower_message:
            if context in {"login connection", "reboot command"}:
                return STATUS_MODEM_TIMEOUT
            return LOG_ERR_CONN_TIMEOUT
        return error_message if len(error_message) <= 70 else error_message[:67] + "..."
