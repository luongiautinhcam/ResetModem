from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from .models import LogEntry


class LogExportError(Exception):
    pass


class LogExporter:
    def export(
        self,
        entries: Sequence[LogEntry],
        directory: str,
        translate: Callable[..., str],
        status_text: Callable[[str], str],
    ) -> Path:
        target_directory = Path(directory)
        if not target_directory.is_dir():
            raise LogExportError(f"Invalid log directory: {directory}")

        filename = f"modem_log_{datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
        target = target_directory / filename
        try:
            with target.open("w", encoding="utf-8") as log_file:
                log_file.write(
                    f"{translate('time')}\t{translate('ip')}\t{translate('status')}\n"
                )
                log_file.write("=" * 60 + "\n")
                for entry in entries:
                    log_file.write(
                        f"{entry.timestamp:%d/%m/%Y %H:%M:%S}\t"
                        f"{status_text(entry.public_ip)}\t{status_text(entry.status)}\n"
                    )
        except OSError as error:
            raise LogExportError(str(error)) from error
        return target
