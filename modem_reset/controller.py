import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import count

from .constants import (
    FINAL_STATUSES,
    IP_CHECK_INTERVAL_SECONDS,
    LOG_UPDATE_INTERVAL_SECONDS,
    STATUS_CHECKING,
    STATUS_DISCONNECTED,
    STATUS_GETTING_IP,
    STATUS_IP_PARSE_ERROR,
    STATUS_IP_TIMEOUT,
    STATUS_IP_UNKNOWN,
    STATUS_NORMAL,
    STATUS_RESET_AUTO_START,
    STATUS_RESET_MANUAL_START,
)
from .ip_checker import PublicIpChecker
from .models import LogEntry, ResetRequestResult
from .modem_client import ModemClient


@dataclass(frozen=True)
class ControllerEvent:
    kind: str
    payload: object = None


class AppController:
    """Owns application state and all background network work."""

    def __init__(
        self,
        ip_checker: PublicIpChecker | None = None,
        modem_client: ModemClient | None = None,
    ):
        self.ip_checker = ip_checker or PublicIpChecker()
        self.modem_client = modem_client or ModemClient()
        self._lock = threading.RLock()
        self._events: queue.Queue[ControllerEvent] = queue.Queue()
        self._stop_event = threading.Event()
        self._status_timer: threading.Timer | None = None
        self._threads: list[threading.Thread] = []
        self._started = False

        self._public_ip = STATUS_GETTING_IP
        self._is_connected: bool | None = None
        self._last_action: str | None = None
        self._is_resetting = False
        self._logs: list[LogEntry] = []
        self._entry_ids = count(1)

        self._password = ""
        self._auto_reset_enabled = False
        self._auto_reset_interval = 0
        self._auto_reset_due = float("inf")

    @property
    def public_ip(self) -> str:
        with self._lock:
            return self._public_ip

    @property
    def is_connected(self) -> bool | None:
        with self._lock:
            return self._is_connected

    @property
    def is_resetting(self) -> bool:
        with self._lock:
            return self._is_resetting

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        self._threads = [
            threading.Thread(target=self._ip_loop, daemon=True, name="IPMonitor"),
            threading.Thread(target=self._scheduler_loop, daemon=True, name="AppScheduler"),
        ]
        for thread in self._threads:
            thread.start()

    def close(self) -> None:
        self._stop_event.set()
        self._cancel_status_timer()

    def drain_events(self) -> list[ControllerEvent]:
        events: list[ControllerEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def logs_snapshot(self) -> tuple[LogEntry, ...]:
        with self._lock:
            return tuple(self._logs)

    def remove_logs(self, entry_ids: set[int]) -> None:
        with self._lock:
            self._logs = [entry for entry in self._logs if entry.entry_id not in entry_ids]
            snapshot = tuple(self._logs)
        self._events.put(ControllerEvent("logs_changed", snapshot))

    def set_password(self, password: str) -> None:
        with self._lock:
            self._password = password

    def configure_auto_reset(self, enabled: bool, interval_seconds: int) -> None:
        interval = max(0, interval_seconds)
        with self._lock:
            self._auto_reset_enabled = enabled and interval > 0
            self._auto_reset_interval = interval
            self._auto_reset_due = (
                time.monotonic() + interval if self._auto_reset_enabled else float("inf")
            )

    def request_reset(
        self,
        password: str,
        *,
        is_auto: bool = False,
        interval_seconds: int = 0,
    ) -> ResetRequestResult:
        if not password:
            return ResetRequestResult.MISSING_PASSWORD

        with self._lock:
            if self._is_resetting:
                return ResetRequestResult.ALREADY_RUNNING
            self._is_resetting = True
            self._last_action = (
                STATUS_RESET_AUTO_START.format(interval_seconds)
                if is_auto
                else STATUS_RESET_MANUAL_START
            )

        self._cancel_status_timer()
        self._record_current_status()
        self._events.put(ControllerEvent("reset_state", True))
        threading.Thread(
            target=self._run_reset,
            args=(password,),
            daemon=True,
            name="ModemReset",
        ).start()
        return ResetRequestResult.STARTED

    def _run_reset(self, password: str) -> None:
        outcome = self.modem_client.reboot(password, self._set_action)
        self._set_action(outcome.status)
        with self._lock:
            self._is_resetting = False
        self._events.put(ControllerEvent("reset_state", False))
        self._schedule_status_clear(outcome.clear_status_after_ms)

    def _set_action(self, status: str) -> None:
        self._cancel_status_timer()
        with self._lock:
            self._last_action = status
        self._record_current_status()

    def _schedule_status_clear(self, delay_ms: int) -> None:
        if delay_ms <= 0:
            self._clear_action()
            return
        timer = threading.Timer(delay_ms / 1000, self._clear_action)
        timer.daemon = True
        with self._lock:
            self._status_timer = timer
        timer.start()

    def _cancel_status_timer(self) -> None:
        with self._lock:
            timer = self._status_timer
            self._status_timer = None
        if timer:
            timer.cancel()

    def _clear_action(self) -> None:
        if self._stop_event.is_set():
            return
        with self._lock:
            self._last_action = None
            self._status_timer = None
        self._record_current_status()

    def _ip_loop(self) -> None:
        while not self._stop_event.is_set():
            result = self.ip_checker.check()
            with self._lock:
                ip_changed = result.value != self._public_ip
                connection_changed = (
                    self._is_connected is None or result.connected != self._is_connected
                )
                self._public_ip = result.value
                self._is_connected = result.connected
                should_log = connection_changed or not self._logs
            if ip_changed or connection_changed:
                self._events.put(ControllerEvent("ip_changed", result))
            if should_log:
                self._record_current_status()
            if self._stop_event.wait(IP_CHECK_INTERVAL_SECONDS):
                return

    def _scheduler_loop(self) -> None:
        next_log = time.monotonic() + LOG_UPDATE_INTERVAL_SECONDS
        while not self._stop_event.wait(0.2):
            now = time.monotonic()
            if now >= next_log:
                self._record_current_status()
                next_log = now + LOG_UPDATE_INTERVAL_SECONDS

            with self._lock:
                auto_due = self._auto_reset_enabled and now >= self._auto_reset_due
                if auto_due:
                    interval = self._auto_reset_interval
                    password = self._password
                    disconnected = self._is_connected is False
                    self._auto_reset_due = now + interval
                else:
                    interval = 0
                    password = ""
                    disconnected = False
            if auto_due and disconnected:
                self.request_reset(
                    password,
                    is_auto=True,
                    interval_seconds=interval,
                )

    def _record_current_status(self) -> None:
        now = datetime.now().replace(microsecond=0)
        with self._lock:
            status = self._current_status_locked()
            if status is None:
                return

            same_second = [entry for entry in self._logs if entry.timestamp == now]
            if any(entry.status == status for entry in same_second):
                return

            new_is_final = self._is_final_status(status)
            if any(self._is_final_status(entry.status) for entry in same_second):
                return
            if new_is_final and same_second:
                same_ids = {entry.entry_id for entry in same_second}
                self._logs = [entry for entry in self._logs if entry.entry_id not in same_ids]

            self._logs.insert(
                0,
                LogEntry(next(self._entry_ids), now, self._public_ip, status),
            )
            snapshot = tuple(self._logs)
        self._events.put(ControllerEvent("logs_changed", snapshot))

    def _current_status_locked(self) -> str | None:
        if self._last_action and self._last_action != STATUS_NORMAL:
            return self._last_action
        if self._is_connected is None and not self._is_resetting:
            return STATUS_CHECKING
        if self._is_connected:
            return STATUS_NORMAL
        if self._is_connected is False and not self._is_resetting:
            if self._public_ip in {
                STATUS_IP_TIMEOUT,
                STATUS_IP_UNKNOWN,
                STATUS_IP_PARSE_ERROR,
            }:
                return self._public_ip
            return STATUS_DISCONNECTED
        return None

    @staticmethod
    def _is_final_status(status: str) -> bool:
        return any(status == final or status.startswith(final) for final in FINAL_STATUSES)
