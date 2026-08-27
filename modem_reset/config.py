import configparser
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    CONFIG_PATH,
    DEFAULT_AUTO_RESET_INTERVAL,
    DEFAULT_LANGUAGE,
    DEFAULT_LOG_INTERVAL,
    SUPPORTED_LANGUAGES,
)


class ConfigLoadError(Exception):
    pass


@dataclass
class AppConfig:
    language: str = DEFAULT_LANGUAGE
    password: str = ""
    save_password: bool = False
    log_directory: str | None = None
    log_interval: int = DEFAULT_LOG_INTERVAL
    auto_reset_enabled: bool = False
    auto_reset_interval: int = DEFAULT_AUTO_RESET_INTERVAL
    window_x: int | None = None
    window_y: int | None = None
    window_width: int = 450
    window_height: int = 350


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()

        parser = configparser.ConfigParser()
        try:
            parser.read(self.path, encoding="utf-8")
            language = parser.get("GENERAL", "language", fallback=DEFAULT_LANGUAGE)
            if language not in SUPPORTED_LANGUAGES:
                language = DEFAULT_LANGUAGE

            password = parser.get("CREDENTIALS", "password", fallback="")
            log_directory = parser.get("LOGGING", "log_directory", fallback="").strip() or None

            return AppConfig(
                language=language,
                password=password,
                save_password=bool(password),
                log_directory=log_directory,
                log_interval=max(0, parser.getint("LOGGING", "log_interval", fallback=DEFAULT_LOG_INTERVAL)),
                auto_reset_enabled=parser.getboolean("AUTO_RESET", "enabled", fallback=False),
                auto_reset_interval=max(
                    0,
                    parser.getint(
                        "AUTO_RESET",
                        "interval_seconds",
                        fallback=DEFAULT_AUTO_RESET_INTERVAL,
                    ),
                ),
                window_x=parser.getint("WINDOW", "pos_x", fallback=None),
                window_y=parser.getint("WINDOW", "pos_y", fallback=None),
                window_width=max(400, parser.getint("WINDOW", "width", fallback=450)),
                window_height=max(300, parser.getint("WINDOW", "height", fallback=350)),
            )
        except (configparser.Error, OSError, TypeError, ValueError) as error:
            raise ConfigLoadError(str(error)) from error

    def save(self, config: AppConfig) -> None:
        parser = configparser.ConfigParser()
        parser["GENERAL"] = {"language": config.language}
        parser["CREDENTIALS"] = {}
        if config.save_password:
            parser["CREDENTIALS"]["password"] = config.password
        parser["LOGGING"] = {
            "log_interval": str(max(0, config.log_interval)),
            "log_directory": config.log_directory or "",
        }
        parser["WINDOW"] = {
            "width": str(max(400, config.window_width)),
            "height": str(max(300, config.window_height)),
        }
        if config.window_x is not None and config.window_y is not None:
            parser["WINDOW"]["pos_x"] = str(config.window_x)
            parser["WINDOW"]["pos_y"] = str(config.window_y)
        parser["AUTO_RESET"] = {
            "enabled": str(config.auto_reset_enabled),
            "interval_seconds": str(max(0, config.auto_reset_interval)),
        }

        with self.path.open("w", encoding="utf-8") as config_file:
            parser.write(config_file)
