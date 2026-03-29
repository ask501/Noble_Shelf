from __future__ import annotations

import os

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from PIL import Image

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


# ══════════════════════════════════════════════════════════
#  BookReader アダプター
# ══════════════════════════════════════════════════════════

class BookReader:
    """形式ごとの読み込みを統一するアダプター基底クラス"""

    def page_count(self) -> int:
        raise NotImplementedError

    def read_page(self, idx: int) -> Image.Image:
        raise NotImplementedError

    def close(self):
        pass

    @staticmethod
    def open(path: str) -> "BookReader":
        ext = os.path.splitext(path)[1].lower()
        if os.path.isdir(path):
            return FolderReader(path)
        elif ext == ".pdf":
            return PdfReader(path)
        else:
            raise ValueError(f"非対応形式: {ext}")


class FolderReader(BookReader):
    def __init__(self, path: str):
        self._path = path
        self._files = sorted(
            f for f in os.listdir(path)
            if f.lower().endswith(IMAGE_EXTS)
        )

    def page_count(self):
        return len(self._files)

    def read_page(self, idx: int) -> Image.Image:
        return Image.open(os.path.join(self._path, self._files[idx])).convert("RGB")


class PdfReader(BookReader):
    def __init__(self, path: str):
        if not HAS_PYMUPDF:
            raise ImportError("PyMuPDF が必要です: pip install pymupdf")
        self._doc = fitz.open(path)

    def page_count(self):
        return len(self._doc)

    def read_page(self, idx: int) -> Image.Image:
        page = self._doc[idx]
        mat  = fitz.Matrix(2.0, 2.0)
        pix  = page.get_pixmap(matrix=mat)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def close(self):
        self._doc.close()
