"""Configurable data-folder location for the HPA Cervix Manager.

The Git repository holds only code. All downloaded images, the SQLite
database, logs and exports live in a user-chosen data directory (e.g. an
iCloud Drive folder) that is *not* part of the repository. The chosen path
is persisted in a small local config file so it only has to be selected
once per Mac.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

APP_CONFIG_DIR = Path.home() / "Library" / "Application Support" / "HPA Cervix Manager"
APP_CONFIG_FILE = APP_CONFIG_DIR / "config.json"

DEFAULT_DATA_DIR_NAME = "HPA_Cervix"


@dataclass(frozen=True)
class DataPaths:
    """Resolved subdirectories inside the user-chosen data folder."""

    root: Path

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def metadata(self) -> Path:
        return self.root / "metadata"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def database_path(self) -> Path:
        return self.metadata / "hpa_cervix.sqlite"

    def ensure_exists(self) -> None:
        for path in (self.images, self.metadata, self.exports, self.logs):
            path.mkdir(parents=True, exist_ok=True)


def _read_config() -> dict:
    if APP_CONFIG_FILE.exists():
        return json.loads(APP_CONFIG_FILE.read_text())
    return {}


def _write_config(config: dict) -> None:
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    APP_CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_configured_data_dir() -> Path | None:
    """Return the previously chosen data directory, if any.

    Checks the HPA_CERVIX_DATA_DIR environment variable first (useful for
    tests and scripting), then the persisted config file.
    """
    env_override = os.environ.get("HPA_CERVIX_DATA_DIR")
    if env_override:
        return Path(env_override).expanduser()

    config = _read_config()
    stored = config.get("data_dir")
    return Path(stored).expanduser() if stored else None


def set_configured_data_dir(path: Path) -> None:
    config = _read_config()
    config["data_dir"] = str(Path(path).expanduser().resolve())
    _write_config(config)


def get_data_paths() -> DataPaths:
    """Resolve the active data directory into a DataPaths object.

    Raises RuntimeError if no data directory has been configured yet. The
    GUI is responsible for prompting the user to pick one on first launch
    (see ui/main_window.py, not yet implemented in this phase).
    """
    data_dir = get_configured_data_dir()
    if data_dir is None:
        raise RuntimeError(
            "No data directory configured. Set HPA_CERVIX_DATA_DIR or call "
            "set_configured_data_dir() first."
        )
    paths = DataPaths(root=data_dir)
    paths.ensure_exists()
    return paths
