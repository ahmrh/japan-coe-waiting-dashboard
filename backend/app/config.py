from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = ROOT_DIR / "data" / "coe_dashboard.sqlite3"
load_dotenv(ROOT_DIR / ".env")


def database_path() -> Path:
    configured = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE}")
    if not configured.startswith("sqlite:///"):
        raise ValueError("This local release supports SQLite DATABASE_URL values only.")
    path = Path(configured.removeprefix("sqlite:///"))
    return path if path.is_absolute() else ROOT_DIR / path


def refresh_interval_seconds() -> int:
    hours = int(os.getenv("ESTAT_REFRESH_INTERVAL_HOURS", "24"))
    if hours < 1:
        raise ValueError("ESTAT_REFRESH_INTERVAL_HOURS must be at least one.")
    return hours * 60 * 60


def request_timeout_seconds() -> float:
    timeout = float(os.getenv("ESTAT_REQUEST_TIMEOUT_SECONDS", "20"))
    if not 1 <= timeout <= 120:
        raise ValueError("ESTAT_REQUEST_TIMEOUT_SECONDS must be between 1 and 120.")
    return timeout


ESTAT_TABLE_ID = "0004049310"
ESTAT_URL = f"https://www.e-stat.go.jp/dbview?sid={ESTAT_TABLE_ID}"
ESTAT_TITLE = "地方出入国在留管理局管内別 在留資格認定証明書交付申請の受理及び処理人員"
