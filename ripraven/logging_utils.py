"""
Utility helpers for consistent logging across RipRaven modules.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

_LOGGING_INITIALIZED = False


def _determine_log_path(log_file: Optional[str]) -> Path:
    if log_file:
        return Path(log_file).expanduser().resolve()

    env_log_file = os.getenv("RIPRAVEN_LOG_FILE")
    if env_log_file:
        return Path(env_log_file).expanduser().resolve()

    project_root = Path(__file__).resolve().parent.parent
    default_dir = project_root / "logs"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir / "ripraven.log"


def setup_logging(log_file: Optional[str] = None, level: Optional[str] = None) -> None:
    """
    Configure the root logger with file and console handlers.
    """
    global _LOGGING_INITIALIZED

    if _LOGGING_INITIALIZED and logging.getLogger().handlers:
        return

    log_path = _determine_log_path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level_name = level or os.getenv("RIPRAVEN_LOG_LEVEL", "INFO")
    log_level = getattr(logging, level_name.upper(), logging.INFO)

    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    console_formatter = logging.Formatter("%(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    existing_files = {
        Path(handler.baseFilename)
        for handler in root_logger.handlers
        if hasattr(handler, "baseFilename")
    }

    if log_path not in existing_files:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    if not any(
        isinstance(handler, logging.StreamHandler) and not hasattr(handler, "baseFilename")
        for handler in root_logger.handlers
    ):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    _LOGGING_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a module-specific logger, ensuring logging is configured first.
    """
    setup_logging()
    return logging.getLogger(name)
