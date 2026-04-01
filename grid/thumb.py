from __future__ import annotations

import hashlib
import os
from typing import Callable, Optional

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QPixmap

import config


def _cache_path(cover: str) -> str:
    h = hashlib.md5(cover.encode()).hexdigest()
    return os.path.join(config.CACHE_DIR, f"{h}.png")


def _load_thumb_sync(cover: str) -> Optional[QPixmap]:
    try:
        cp = _cache_path(cover)
        tw, th = config.THUMB_CACHE_WIDTH, config.THUMB_CACHE_HEIGHT
        if os.path.exists(cp):
            pix = QPixmap(cp)
            if not pix.isNull():
                return pix
        if not os.path.exists(cover):
            return None
        with Image.open(cover) as im:
            im = im.convert("RGB")
            im.thumbnail((tw, th), Image.BILINEAR)
            os.makedirs(config.CACHE_DIR, exist_ok=True)
            im.save(cp, "PNG", optimize=False)
        pix = QPixmap(cp)
        return pix if not pix.isNull() else None
    except Exception:
        return None


class ThumbSignals(QObject):
    done = Signal(str, QPixmap)
    finished = Signal(str)


class ThumbWorker(QRunnable):
    def __init__(
        self,
        cover: str,
        serial: int,
        serial_getter: Callable[[], int],
    ) -> None:
        super().__init__()
        self.cover = cover
        self._serial = serial
        self._serial_getter = serial_getter
        self.signals = ThumbSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            pix = _load_thumb_sync(self.cover)
            if pix and self._serial_getter() == self._serial:
                self.signals.done.emit(self.cover, pix)
        finally:
            self.signals.finished.emit(self.cover)

