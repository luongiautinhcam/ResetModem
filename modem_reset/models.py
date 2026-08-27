from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class IpCheckResult:
    value: str
    connected: bool


@dataclass(frozen=True)
class ResetOutcome:
    status: str
    clear_status_after_ms: int


@dataclass(frozen=True)
class LogEntry:
    entry_id: int
    timestamp: datetime
    public_ip: str
    status: str


class ResetRequestResult(Enum):
    STARTED = "started"
    MISSING_PASSWORD = "missing_password"
    ALREADY_RUNNING = "already_running"
