"""Tiny logging setup: logs to both stderr and a dated file under data/logs/."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path


def setup_logging(data_dir: Path, level: int = logging.INFO) -> logging.Logger:
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / f"run-{date.today().isoformat()}.log"

    logger = logging.getLogger("jobdigest")
    logger.setLevel(level)
    logger.handlers.clear()  # idempotent if called twice in one process

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    fileh = logging.FileHandler(logfile, encoding="utf-8")
    fileh.setFormatter(fmt)
    logger.addHandler(fileh)

    logger.propagate = False
    return logger
