from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
from ui.dialogs.properties._utils import BTN_CANCEL_STYLE, BTN_SAVE_STYLE
from theme import (
    apply_dark_titlebar,
    COLOR_WHITE,
    META_APPLY_THUMB_BG,
    META_APPLY_THUMB_BORDER,
    META_APPLY_TEXT_DIM,
    META_APPLY_TEXT_SUB,
    META_APPLY_RADIO_TEXT,
    META_APPLY_RADIO_BORDER,
    META_APPLY_TOGGLE_TEXT,
    META_APPLY_TOGGLE_DIM_TEXT,
)


class MetaApplyDialog(QDialog):
    """メタデータ取捨選択ダイアログ"""

    def __init__(self, current: dict, fetched: dict, parent=None, book_path: str = ""):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self._result: dict | None = None
        self._current_vals: dict[str, str] = {}
        self._fetched_vals: dict[str, str] = {}
        self._current_edits: dict[str, QLineEdit | QTextEdit] = {}
        self._fetched_edits: dict[str, QLineEdit | QTextEdit] = {}
        self._book_path = book_path or ""
        self._current_cover = (current.get("cover") or "").strip()
        self._fetched_image_url = (fetched.get("image_url") or "").strip()
        self._cover_choice = "current"  # "current" | "fetched" | "cropped"
        self._chosen_cover_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.META_APPLY_LAYOUT_MARGINS)
        layout.setSpacing(config.META_APPLY_LAYOUT_SPACING)

        # ヘッダー行
        header = QHBoxLayout()
        lbl_field = QLabel("項目")
        lbl_field.setFixedWidth(config.META_APPLY_FIELD_COL_WIDTH)
        lbl_cur = QLabel("現在値")
        lbl_cur.setFixedWidth(config.META_APPLY_VALUE_COL_WIDTH)
        spacer = QLabel("")
        spacer.setFixedWidth(config.META_APPLY_ARROW_COL_WIDTH)
        lbl_new = QLabel("取得値")
        lbl_new.setFixedWidth(config.META_APPLY_VALUE_COL_WIDTH)
        header.addWidget(lbl_field)
        header.addWidget(lbl_cur)
        header.addWidget(spacer)
        header.addWidget(lbl_new)
        layout.addLayout(header)

        # サムネイル行（取得画像がある場合のみ）
        self._cover_current_label: QLabel | None = None
        self._cover_fetched_label: QLabel | None = None
        self._cover_radio_current = None
        self._cover_radio_fetched = None
        if self._current_cover or self._fetched_image_url:
            row_cover = QHBoxLayout()
            chk_cover = QLabel("サムネイル")
            chk_cover.setFixedWidth(config.META_APPLY_FIELD_COL_WIDTH)
            row_cover.addWidget(chk_cover)
            # 現在のサムネ表示
            self._cover_current_label = QLabel()
            self._cover_current_label.setFixedSize(*config.META_APPLY_THUMB_SIZE)
            self._cover_current_label.setStyleSheet(
                f"background: {META_APPLY_THUMB_BG}; border: 1px solid {META_APPLY_THUMB_BORDER}; "
                f"border-radius: {config.PROP_ACTION_BTN_RADIUS}px;"
            )
            self._cover_current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._current_cover and os.path.exists(self._current_cover):
                pix = QPixmap(self._current_cover).scaled(
                    config.META_APPLY_THUMB_PIX_SIZE[0],
                    config.META_APPLY_THUMB_PIX_SIZE[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._cover_current_label.setPixmap(pix)
            else:
                self._cover_current_label.setText("なし")
                self._cover_current_label.setStyleSheet(
                    f"background: {META_APPLY_THUMB_BG}; color: {META_APPLY_TEXT_DIM}; "
                    f"border: 1px solid {META_APPLY_THUMB_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;"
                )
            row_cover.addWidget(self._cover_current_label)
            row_cover.addWidget(QLabel("→"))
            # 取得サムネ表示（URLから非同期で読む場合は後で更新するためプレースホルダー）
            self._cover_fetched_label = QLabel()
            self._cover_fetched_label.setFixedSize(*config.META_APPLY_THUMB_SIZE)
            self._cover_fetched_label.setStyleSheet(
                f"background: {META_APPLY_THUMB_BG}; border: 1px solid {META_APPLY_THUMB_BORDER}; "
                f"border-radius: {config.PROP_ACTION_BTN_RADIUS}px;"
            )
            self._cover_fetched_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self._fetched_image_url:
                self._cover_fetched_label.setText("読込中…")
                self._cover_fetched_label.setStyleSheet(
                    f"background: {META_APPLY_THUMB_BG}; color: {META_APPLY_TEXT_SUB}; "
                    f"border: 1px solid {META_APPLY_THUMB_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;"
                )
                self._load_fetched_cover_async()
            else:
                self._cover_fetched_label.setText("なし")
                self._cover_fetched_label.setStyleSheet(
                    f"background: {META_APPLY_THUMB_BG}; color: {META_APPLY_TEXT_DIM}; "
                    f"border: 1px solid {META_APPLY_THUMB_BORDER}; border-radius: {config.PROP_ACTION_BTN_RADIUS}px;"
                )
            row_cover.addWidget(self._cover_fetched_label)
            # ラジオ＋切り抜きボタン
            from PySide6.QtWidgets import QRadioButton

            cover_grp = QWidget()
            cover_grp_layout = QVBoxLayout(cover_grp)
            cover_grp_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
            self._cover_radio_current = QRadioButton("現在のサムネ")
            self._cover_radio_fetched = QRadioButton("取得したサムネ")
            _radio_style = (
                f"QRadioButton {{ color: {META_APPLY_RADIO_TEXT}; }}"
                f" QRadioButton::indicator:checked {{ background-color: {COLOR_WHITE}; border: 1px solid {META_APPLY_RADIO_BORDER}; }}"
                f" QRadioButton:checked {{ color: {COLOR_WHITE}; }}"
            )
            self._cover_radio_current.setStyleSheet(_radio_style)
            self._cover_radio_fetched.setStyleSheet(_radio_style)
            cover_grp_layout.addWidget(self._cover_radio_current)
            cover_grp_layout.addWidget(self._cover_radio_fetched)
            btn_crop = QPushButton("切り抜きで選択")
            btn_crop.setStyleSheet(f"font-size: {config.FONT_SIZE_PROP_HINT}px;")
            btn_crop.clicked.connect(self._on_cover_crop)
            cover_grp_layout.addWidget(btn_crop)
            row_cover.addWidget(cover_grp)
            layout.addLayout(row_cover)
            # 初期選択: すでにサムネがある場合は現在値、ない場合は取得値
            if self._current_cover and os.path.exists(self._current_cover):
                self._cover_radio_current.setChecked(True)
            elif self._fetched_image_url:
                self._cover_radio_fetched.setChecked(True)
                self._cover_choice = "fetched"
            else:
                self._cover_radio_current.setChecked(True)

            def _set_cover_current(v):
                if v:
                    self._cover_choice = "current"

            def _set_cover_fetched(v):
                if v:
                    self._cover_choice = "fetched"

            self._cover_radio_current.toggled.connect(_set_cover_current)
            self._cover_radio_fetched.toggled.connect(_set_cover_fetched)

        # 各フィールド定義
        FIELDS = [
            ("title", "タイトル"),
            ("circle", "サークル"),
            ("author", "作者"),
            ("series", "シリーズ"),
            ("tags", "タグ"),
            ("characters", "キャラクター"),
            ("pages", "ページ数"),
            ("release_date", "発売日"),
            ("price", "金額"),
            ("dlsite_id", "作品ID"),
            ("store_url", "商品URL"),
        ]

        def _make_toggle(chk, lbl_c, edit_n):
            def _toggle(checked):
                if checked:
                    lbl_c.setStyleSheet(
                        f"border: 1px solid {META_APPLY_THUMB_BORDER}; border-radius: {config.META_APPLY_TOGGLE_RADIUS}px; "
                        f"padding: {config.META_APPLY_TOGGLE_PADDING_Y}px {config.META_APPLY_TOGGLE_PADDING_X}px; color: {META_APPLY_TOGGLE_TEXT};"
                    )
                    edit_n.setStyleSheet(
                        f"border: 1px solid {COLOR_WHITE}; border-radius: {config.META_APPLY_TOGGLE_RADIUS}px; "
                        f"padding: {config.META_APPLY_TOGGLE_PADDING_Y}px {config.META_APPLY_TOGGLE_PADDING_X}px;"
                    )
                else:
                    lbl_c.setStyleSheet(
                        f"border: 1px solid {COLOR_WHITE}; border-radius: {config.META_APPLY_TOGGLE_RADIUS}px; "
                        f"padding: {config.META_APPLY_TOGGLE_PADDING_Y}px {config.META_APPLY_TOGGLE_PADDING_X}px; color: {META_APPLY_TOGGLE_TEXT};"
                    )
                    edit_n.setStyleSheet(
                        f"border: 1px solid {META_APPLY_THUMB_BORDER}; border-radius: {config.META_APPLY_TOGGLE_RADIUS}px; "
                        f"padding: {config.META_APPLY_TOGGLE_PADDING_Y}px {config.META_APPLY_TOGGLE_PADDING_X}px; color: {META_APPLY_TOGGLE_DIM_TEXT};"
                    )

            chk.toggled.connect(_toggle)
            _toggle(chk.isChecked())

        self._checks: dict[str, QCheckBox] = {}

        for key, label in FIELDS:
            cur_val = current.get(key, "")
            new_val = fetched.get(key, "")

            # リストは文字列に変換
            if isinstance(cur_val, list):
                cur_val = ", ".join(cur_val)
            if isinstance(new_val, list):
                new_val = ", ".join(new_val)

            cur_str = str(cur_val) if cur_val else ""
            new_str = str(new_val) if new_val else ""
            self._current_vals[key] = cur_str
            self._fetched_vals[key] = new_str

            row = QHBoxLayout()

            chk = QCheckBox(label)
            chk.setFixedWidth(config.META_APPLY_FIELD_COL_WIDTH)
            chk.setStyleSheet(
                f"""
                QCheckBox {{ color: {COLOR_WHITE}; }}
                QCheckBox::indicator {{
                    width: {config.META_APPLY_CHECKBOX_INDICATOR_SIZE}px;
                    height: {config.META_APPLY_CHECKBOX_INDICATOR_SIZE}px;
                    border: 1px solid {COLOR_WHITE};
                    border-radius: {config.META_APPLY_CHECKBOX_INDICATOR_RADIUS}px;
                    background: transparent;
                }}
                QCheckBox::indicator:checked {{
                    background: {COLOR_WHITE};
                }}
                """
            )
            has_new = bool(new_str.strip())
            same = cur_str.strip() == new_str.strip()
            chk.setChecked(has_new and not same)
            self._checks[key] = chk
            row.addWidget(chk)

            if key in ("tags", "characters"):
                lbl_c = QTextEdit()
                lbl_c.setPlainText(cur_str)
                lbl_c.setFixedSize(*config.META_APPLY_TEXTEDIT_SIZE)
            else:
                lbl_c = QLineEdit(cur_str)
                lbl_c.setFixedWidth(config.META_APPLY_LINEEDIT_WIDTH)
            self._current_edits[key] = lbl_c
            row.addWidget(lbl_c)

            arrow = QLabel("→")
            arrow.setFixedWidth(config.META_APPLY_ARROW_COL_WIDTH)
            arrow.setAlignment(Qt.AlignCenter)
            arrow.setStyleSheet(f"color: {META_APPLY_TEXT_SUB};")
            row.addWidget(arrow)

            if key in ("tags", "characters"):
                edit_n = QTextEdit()
                edit_n.setPlainText(new_str)
                edit_n.setFixedSize(*config.META_APPLY_TEXTEDIT_SIZE)
            else:
                edit_n = QLineEdit(new_str)
                edit_n.setFixedWidth(config.META_APPLY_LINEEDIT_WIDTH)
            self._fetched_edits[key] = edit_n
            row.addWidget(edit_n)

            _make_toggle(chk, lbl_c, edit_n)
            layout.addLayout(row)

        # ボタン
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_apply = QPushButton("適用")
        btn_apply.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def _load_fetched_cover_async(self):
        """取得サムネURLをバックグラウンドでダウンロードしてラベルに表示"""
        url = self._fetched_image_url
        if not url:
            return

        class _CoverWorker(QThread):
            done = Signal(object)

            def __init__(self, u):
                super().__init__()
                self._url = u

            def run(self):
                from ui.dialogs.thumbnail_crop_dialog import _download_image

                self.done.emit(_download_image(self._url))

        w = _CoverWorker(url)

        def _on_done(pix):
            if pix is not None and not pix.isNull() and getattr(self, "_cover_fetched_label", None):
                scaled = pix.scaled(
                    config.META_APPLY_THUMB_PIX_SIZE[0],
                    config.META_APPLY_THUMB_PIX_SIZE[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._cover_fetched_label.setPixmap(scaled)
                self._cover_fetched_label.setStyleSheet(
                    f"background: {META_APPLY_THUMB_BG}; border: 1px solid {META_APPLY_THUMB_BORDER}; "
                    f"border-radius: {config.PROP_ACTION_BTN_RADIUS}px;"
                )

        w.done.connect(_on_done)
        w.finished.connect(w.deleteLater)
        w.start()
        setattr(self, "_cover_worker", w)

    def _on_cover_crop(self):
        """切り抜きダイアログを開き、確定時にサムネイルパスを保存"""
        from ui.dialogs.thumbnail_crop_dialog import ThumbnailCropDialog

        if not self._fetched_image_url:
            QMessageBox.information(self, "サムネイル", "取得した画像がありません。")
            return
        dlg = ThumbnailCropDialog(self._fetched_image_url, self._book_path, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_path:
            self._chosen_cover_path = dlg.result_path
            self._cover_choice = "cropped"
            if self._cover_radio_fetched:
                self._cover_radio_fetched.setChecked(False)
            if self._cover_radio_current:
                self._cover_radio_current.setChecked(False)
            QMessageBox.information(self, "サムネイル", "切り抜きを適用しました。「適用」で確定してください。")

    def _on_apply(self):
        result = {}
        for key, chk in self._checks.items():
            cur_edit = self._current_edits[key]
            cur_val = cur_edit.toPlainText() if isinstance(cur_edit, QTextEdit) else cur_edit.text()
            edit = self._fetched_edits[key]
            new_val = edit.toPlainText() if isinstance(edit, QTextEdit) else edit.text()
            result[key] = new_val if chk.isChecked() else cur_val
        # サムネイル: 現在 / 取得 / 切り抜き
        if getattr(self, "_cover_radio_current", None) is not None:
            if self._chosen_cover_path:
                result["cover_path"] = self._chosen_cover_path
            elif self._cover_choice == "fetched" and self._fetched_image_url:
                result["cover_path"] = self._download_and_save_cover()
            else:
                result["cover_path"] = None
        self._result = result
        self.accept()

    def _download_and_save_cover(self) -> str | None:
        """取得画像URLをダウンロードしてcover_cacheに保存しパスを返す"""
        import hashlib

        from ui.dialogs.thumbnail_crop_dialog import _download_image

        pix = _download_image(self._fetched_image_url)
        if pix is None or pix.isNull():
            return None
        cover_dir = config.COVER_CACHE_DIR
        os.makedirs(cover_dir, exist_ok=True)
        key = hashlib.md5(self._book_path.encode()).hexdigest()
        out_path = os.path.join(cover_dir, f"{key}_fetched.jpg")
        saved = pix.save(out_path, "JPEG", quality=90)
        return out_path if saved else None

    def selected_keys(self) -> dict:
        return self._result or {}

