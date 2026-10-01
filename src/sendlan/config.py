"""Application settings, validation, and atomic JSON persistence."""

from __future__ import annotations

import getpass
import json
import math
import os
import socket
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """Raised when application settings cannot be stored safely."""


def default_device_name() -> str:
    """Return the operating system's device name with a portable fallback."""
    try:
        hostname = socket.gethostname().strip()
    except OSError:
        hostname = ""
    return hostname[:128] or "SendLan device"


@dataclass(slots=True)
class AppConfig:
    """Validated user preferences and network defaults for SendLan."""

    username: str = field(default_factory=default_device_name)
    username_customized: bool = False
    device_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tcp_port: int = 50001
    discovery_port: int = 50000
    heartbeat_interval: float = 3.0
    peer_timeout: float = 10.0
    downloads_dir: str = "downloads"
    appearance_mode: str = "system"

    def validate(self) -> None:
        """Raise ``ValueError`` if any setting is outside its supported range."""
        if not isinstance(self.username, str) or not self.username.strip():
            raise ValueError("username cannot be empty")
        if len(self.username) > 128:
            raise ValueError("username must not exceed 128 characters")
        if not isinstance(self.username_customized, bool):
            raise ValueError("username_customized must be a boolean")
        if not isinstance(self.device_id, str) or not self.device_id.strip():
            raise ValueError("device_id cannot be empty")
        if len(self.device_id) > 64:
            raise ValueError("device_id must not exceed 64 characters")
        for name, port in (
            ("tcp_port", self.tcp_port),
            ("discovery_port", self.discovery_port),
        ):
            if (
                isinstance(port, bool)
                or not isinstance(port, int)
                or not 1 <= port <= 65535
            ):
                raise ValueError(f"{name} must be between 1 and 65535")
        if (
            isinstance(self.heartbeat_interval, bool)
            or not isinstance(self.heartbeat_interval, (int, float))
            or not math.isfinite(self.heartbeat_interval)
        ):
            raise ValueError("heartbeat_interval must be a finite number")
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")
        if (
            isinstance(self.peer_timeout, bool)
            or not isinstance(self.peer_timeout, (int, float))
            or not math.isfinite(self.peer_timeout)
        ):
            raise ValueError("peer_timeout must be a finite number")
        if self.peer_timeout <= self.heartbeat_interval:
            raise ValueError("peer_timeout must exceed heartbeat_interval")
        if not isinstance(self.downloads_dir, str) or not self.downloads_dir.strip():
            raise ValueError("downloads_dir cannot be empty")
        if (
            not isinstance(self.appearance_mode, str)
            or self.appearance_mode not in {"system", "light", "dark"}
        ):
            raise ValueError("appearance_mode must be system, light, or dark")


class ConfigStore:
    """Load and atomically save an ``AppConfig`` JSON file."""

    def __init__(self, path: str | Path, defaults: AppConfig | None = None) -> None:
        """Create a settings store at ``path`` with optional default values."""
        self.path = Path(path)
        self.defaults = defaults or AppConfig()

    def load(self) -> AppConfig:
        """Load validated settings, creating defaults when the file is absent."""
        try:
            with self.path.open("r", encoding="utf-8") as config_file:
                raw_config = json.load(config_file)
            if not isinstance(raw_config, dict):
                raise ValueError("configuration root must be a JSON object")
            allowed = {field_name for field_name in asdict(self.defaults)}
            config = AppConfig(
                **{key: value for key, value in raw_config.items() if key in allowed}
            )
            needs_save = "device_id" not in raw_config
            if "username_customized" not in raw_config:
                stored_username = raw_config.get("username")
                if (
                    not isinstance(stored_username, str)
                    or not stored_username.strip()
                    or stored_username == getpass.getuser()
                ):
                    config.username = default_device_name()
                    config.username_customized = False
                else:
                    config.username_customized = True
                needs_save = True
            config.validate()
            if needs_save:
                try:
                    self.save(config)
                except ConfigError:
                    pass
            return config
        except FileNotFoundError:
            self._save_defaults()
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._save_defaults()
        return AppConfig(**asdict(self.defaults))

    def save(self, config: AppConfig) -> None:
        """Validate and atomically replace the JSON settings file."""
        config.validate()
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(asdict(config), temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ConfigError(f"could not save settings to {self.path}: {exc}") from exc

    def _save_defaults(self) -> None:
        """Persist defaults when possible without blocking application startup."""
        try:
            self.save(self.defaults)
        except ConfigError:
            return