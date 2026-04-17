from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "AlmancaTurkceSozluk"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def install_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def user_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        root = Path(base) / APP_DIR_NAME
    else:
        root = Path.home() / "AppData" / "Local" / APP_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def resolve_user_path(*parts: str) -> Path:
    path = user_data_root().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_user_subdirs() -> None:
    for relative in (
        ("data", "manual"),
        ("output",),
        ("logs",),
    ):
        user_data_root().joinpath(*relative).mkdir(parents=True, exist_ok=True)
