"""BookReader のページ読み込み（スレッド並列時のロック方針を一元化）。"""
from __future__ import annotations

import os
import threading

from PIL import Image

import config

from ui.dialogs.viewer._reader import BookReader, FolderReader


def read_page_concurrent(
    reader: BookReader,
    lock: threading.Lock,
    idx: int,
) -> Image.Image:
    """フォルダ形式はパス指定の Image.open がスレッドセーフなためロック不要。

    PdfReader 等はドキュメントが非スレッドセーフのため、呼び出し側で ``lock`` を
    掴んだ状態で本関数を呼ぶこと（本関数内ではロックを取らない。二重取得を防ぐため）。

    戻り値は常に ``config.VIEWER_READ_PAGE_PIL_MODE_RGB`` へ変換済み。
    """
    mode = config.VIEWER_READ_PAGE_PIL_MODE_RGB
    if isinstance(reader, FolderReader):
        full_path = os.path.join(reader._path, reader._files[idx])
        return Image.open(full_path).convert(mode)
    if not lock.locked():
        raise RuntimeError(
            "read_page_concurrent: non-FolderReader では呼び出し側が lock を掴んだ状態で呼ぶこと"
        )
    return reader.read_page(idx).convert(mode)
