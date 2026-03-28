from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

import config
import paths
from theme import THEME_COLORS, apply_dark_titlebar

# ページ定義（タイトル, 本文行のリスト, 画像パス or None）— 文言はここで一元管理
_BOOKMARKLET_HELP_PAGES: list[tuple[str, list[str], str | None]] = [
    (
        "ブックマークレットとは",
        [
            "ブックマークレットは、DLsiteやFANZAなどの作品ページを開いた状態でクリックするだけで、"
            "メタデータを自動取得してNoble Shelfに送信できる機能です。",
            "一度登録すれば、作品ページから1クリックでタイトル・サークル・タグ・カバー画像などを取得できます。",
            "※ Noble Shelfが起動していないと動作しません。",
        ],
        None,
    ),
    (
        "ブックマークレットのコピー",
        [
            "ブックマークレットキュー画面の「ブックマークレットをコピー」ボタンを押し、"
            "クリップボードにコピーされた JavaScript（URL）をそのまま使います。",
            "（下の図の赤枠のボタンをクリックすると、自動でコピーされます。）",
        ],
        paths.BOOKMARKLET_HELP_COPY_SCREENSHOT,
    ),
    (
        "ブラウザへの登録方法",
        [
            "Chrome / Microsoft Edge を例にします。",
            "ブックマークバーを表示します（ショートカットキー：Ctrl+Shift+B）。",
            "ブックマークバー上で右クリックし「新しいブックマーク」などから追加します。",
            "名前は任意（例：Noble Shelf）。URL欄にコピーしたブックマークレットを貼り付け、「保存」で確定します。",
            "（下の図：①名前 ②貼り付け ③保存の順です。）",
        ],
        paths.BOOKMARKLET_HELP_BROWSER_SCREENSHOT,
    ),
    (
        "サイトごとの使い方",
        [
            "DLsite：対象の作品ページを開き、登録したブックマークレットをクリックします。",
            "FANZA：対象の作品ページを開き、登録したブックマークレットをクリックします。",
            "「Noble Shelfに送信しました！」と表示されれば成功です。",
        ],
        None,
    ),
    (
        "ランプ（ステータス）の見方",
        [
            "🟢 自動適用済み：ライブラリと完全一致し、メタデータを自動で適用しました。",
            "🟡 手動適用待ち：ライブラリと一致しました。キューで選択し「メタデータを適用」で反映してください。",
            "🔴 未一致：ライブラリに一致する作品が見つかりませんでした。",
        ],
        None,
    ),
    (
        "全体的な使い方",
        [
            "キューに溜まった作品は一覧で選択し、「メタデータを適用」でライブラリに反映できます。",
            "適用済み・不要なキューは削除ボタンで整理できます。",
            "「完全一致時に自動適用」にチェックを入れると、一致時の自動適用が有効になります（オフで無効）。",
        ],
        None,
    ),
]


class BookmarkletHelpDialog(QDialog):
    """ブックマークレットのページ送り式ヘルプダイアログ。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        apply_dark_titlebar(self)
        # 非モーダル表示時も他ウィンドウより手前に維持する
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        self.setWindowTitle("ブックマークレット ヘルプ")
        self.setMinimumSize(*config.BOOKMARKLET_HELP_DIALOG_MIN_SIZE)
        self.resize(*config.BOOKMARKLET_HELP_DIALOG_SIZE)

        self._pages = _BOOKMARKLET_HELP_PAGES
        self._page_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(*config.THUMB_CROP_LAYOUT_MARGINS)
        root.setSpacing(config.THUMB_CROP_LAYOUT_SPACING)

        self._lbl_page_title = QLabel()
        title_font = QFont(config.FONT_FAMILY, config.FONT_SIZE_BOOKMARKLET_HELP_TITLE)
        title_font.setBold(True)
        self._lbl_page_title.setFont(title_font)
        self._lbl_page_title.setStyleSheet(f"color: {THEME_COLORS['text_main']};")
        root.addWidget(self._lbl_page_title)

        self._lbl_body = QLabel()
        self._lbl_body.setWordWrap(True)
        self._lbl_body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._lbl_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lbl_body.setStyleSheet(
            f"color: {THEME_COLORS['text_main']}; font-size: {config.FONT_SIZE_BOOKMARKLET_HELP_BODY}px;"
        )
        root.addWidget(self._lbl_body, stretch=1)

        self._lbl_screenshot = QLabel()
        self._lbl_screenshot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_screenshot.setVisible(False)
        root.addWidget(self._lbl_screenshot)

        footer = QHBoxLayout()
        footer.setSpacing(config.BOOKMARKLET_HELP_FOOTER_SPACING)

        self._btn_prev = QPushButton("前へ")
        self._btn_prev.clicked.connect(self._go_prev)
        footer.addWidget(self._btn_prev)

        self._lbl_counter = QLabel()
        self._lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_counter.setStyleSheet(
            f"color: {THEME_COLORS['text_sub']}; font-size: {config.FONT_SIZE_BOOKMARKLET_HELP_BODY}px;"
        )
        footer.addWidget(self._lbl_counter, stretch=1)

        self._btn_next = QPushButton("次へ")
        self._btn_next.clicked.connect(self._go_next)
        footer.addWidget(self._btn_next)

        root.addLayout(footer)

        self._refresh_page()

    def _go_prev(self) -> None:
        if self._page_index > 0:
            self._page_index -= 1
            self._refresh_page()

    def _go_next(self) -> None:
        if self._page_index < len(self._pages) - 1:
            self._page_index += 1
            self._refresh_page()

    def _refresh_page(self) -> None:
        title, lines, image_path = self._pages[self._page_index]
        self._lbl_page_title.setText(title)
        self._lbl_body.setText("\n\n".join(lines))

        if image_path and os.path.isfile(image_path):
            pix = QPixmap(image_path)
            if not pix.isNull():
                mw = config.BOOKMARKLET_HELP_SCREENSHOT_MAX_WIDTH
                if pix.width() > mw:
                    pix = pix.scaledToWidth(
                        mw,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                self._lbl_screenshot.setPixmap(pix)
                self._lbl_screenshot.setVisible(True)
            else:
                self._lbl_screenshot.clear()
                self._lbl_screenshot.setVisible(False)
        else:
            self._lbl_screenshot.clear()
            self._lbl_screenshot.setVisible(False)
        n = len(self._pages)
        self._lbl_counter.setText(f"{self._page_index + 1} / {n}")
        self._btn_prev.setEnabled(self._page_index > 0)
        self._btn_next.setEnabled(self._page_index < n - 1)
