"""tab_shortcut.py - 設定ダイアログ「ショートカット」タブ"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFormLayout,
    QScrollArea,
    QApplication,
    QFrame,
)
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtCore import Qt, QEvent, QTimer

import db
import config
from theme import (
    SETTINGS_SHORTCUT_HINT_STYLE,
    SETTINGS_SHORTCUT_DISPLAY_STYLE_NORMAL,
    SETTINGS_SHORTCUT_DISPLAY_STYLE_CAPTURE,
    SETTINGS_SHORTCUT_DISPLAY_STYLE_CONFIRMED,
)

_SHORTCUT_KEYS = [
    ("file_open", "開く"),
    ("file_recent", "最近開いたブック"),
    ("file_close_all", "すべて閉じる"),
    ("file_open_library", "ライブラリを開く"),
    ("file_copy", "コピー"),
    ("file_paste", "貼り付け"),
    ("file_print", "印刷"),
    ("file_rescan", "ライブラリの再スキャン"),
    ("file_quit", "終了"),
]


class TabShortcut(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shortcut_displays: dict = {}
        self._active_shortcut_id = None
        self._shortcut_capture_display = None
        self._shortcut_capture_btn = None
        self._shortcut_capture_row = None
        self._shortcut_capture_original_value = ""
        self._shortcut_normal_style = SETTINGS_SHORTCUT_DISPLAY_STYLE_NORMAL
        self._shortcut_capture_style = SETTINGS_SHORTCUT_DISPLAY_STYLE_CAPTURE
        self._shortcut_confirmed_style = SETTINGS_SHORTCUT_DISPLAY_STYLE_CONFIRMED
        self._shortcut_ok_button = None
        self._setup_ui()

    def set_ok_button(self, btn) -> None:
        """設定ダイアログの OK ボタン（検知終了後にフォーカスを戻す）。"""
        self._shortcut_ok_button = btn

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        hint = QLabel("「検知」を押してから割り当てたいキーを押してください。直接入力はできません。×でクリア。")
        hint.setWordWrap(True)
        hint.setStyleSheet(SETTINGS_SHORTCUT_HINT_STYLE)
        layout.addWidget(hint)

        form = QFormLayout()
        for key, label in _SHORTCUT_KEYS:
            key_display = QLabel("")
            key_display.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
            key_display.setStyleSheet(self._shortcut_normal_style)
            key_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_display.setToolTip("検知ボタンで割り当て")
            btn_capture = QPushButton("検知")
            btn_capture.setFixedWidth(config.SETTINGS_SHORTCUT_CAPTURE_BTN_WIDTH)
            btn_capture.setToolTip("クリック後、割り当てたいキーを1回押してください（Escでキャンセル）")
            btn_clear = QPushButton("×")
            btn_clear.setFixedWidth(config.SETTINGS_SHORTCUT_CLEAR_BTN_WIDTH)
            btn_clear.setToolTip("ショートカットをクリア")
            row_w = QWidget()
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
            row_layout.setSpacing(config.SETTINGS_SHORTCUT_ROW_SPACING)
            row_layout.addWidget(key_display)
            row_layout.addWidget(btn_capture)
            row_layout.addWidget(btn_clear)
            form.addRow(label, row_w)
            self._shortcut_displays[key] = key_display
            btn_capture.clicked.connect(
                lambda checked=False, k=key, d=key_display, b=btn_capture, r=row_w: self._start_shortcut_capture(
                    k, d, b, r
                )
            )
            btn_clear.clicked.connect(lambda checked=False, k=key: self._clear_shortcut(k))

        layout.addLayout(form)
        layout.addStretch()
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

    def load(self) -> None:
        for key, disp in self._shortcut_displays.items():
            val = db.get_setting(f"shortcut_{key}")
            if val is None:
                val = config.DEFAULT_SHORTCUTS.get(key, "")
            disp.setText((val or "").strip())

    def save(self) -> None:
        for key, disp in self._shortcut_displays.items():
            val = (disp.text() or "").strip()
            db.set_setting(f"shortcut_{key}", val if val else "")

    def _start_shortcut_capture(self, shortcut_id: str, display: QLabel, btn: QPushButton, row_widget: QWidget):
        """検知開始: 表示枠をハイライトし、次の1キーをグローバルで待つ。"""
        if self._active_shortcut_id is not None:
            if self._active_shortcut_id == shortcut_id:
                self._end_shortcut_capture(cancel=True)
                return
            self._end_shortcut_capture(cancel=True)
        self._active_shortcut_id = shortcut_id
        self._shortcut_capture_display = display
        self._shortcut_capture_btn = btn
        self._shortcut_capture_row = row_widget
        self._shortcut_capture_original_value = (display.text() or "").strip()
        display.setText("● キーを入力してください...")
        display.setStyleSheet(self._shortcut_capture_style)
        btn.setText("再クリックで戻す")
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        self.grabKeyboard()

    def _end_shortcut_capture(self, cancel: bool = False):
        self.releaseKeyboard()
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        display = self._shortcut_capture_display
        if display:
            if cancel:
                display.setText(self._shortcut_capture_original_value)
            display.setStyleSheet(self._shortcut_normal_style)
        if self._shortcut_capture_btn:
            self._shortcut_capture_btn.setText("検知")
        if self._shortcut_ok_button:
            self._shortcut_ok_button.setFocus()
            if app:
                app.processEvents()
        self._active_shortcut_id = None
        self._shortcut_capture_display = None
        self._shortcut_capture_btn = None
        self._shortcut_capture_row = None
        self._shortcut_capture_original_value = ""

    def _clear_shortcut(self, shortcut_id: str):
        """指定ショートカットを空にする。検知中でなければ即反映。"""
        if shortcut_id not in self._shortcut_displays:
            return
        if self._active_shortcut_id == shortcut_id:
            self._end_shortcut_capture(cancel=True)
        self._shortcut_displays[shortcut_id].setText("")

    def eventFilter(self, obj, event):
        """キー検知を最優先。検知中は KeyPress を先に処理し、修飾キー単体は消費して組み合わせ待ち。マウスは後回し。"""
        if self._active_shortcut_id is None:
            return False

        if event.type() == QEvent.Type.KeyPress:
            ev = event
            key = ev.key()
            mods = ev.modifiers()
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return True
            if key == Qt.Key.Key_Escape:
                self._end_shortcut_capture(cancel=True)
                return True
            try:
                mod_int = int(mods)
            except TypeError:
                mod_int = getattr(mods, "value", 0)
            seq = QKeySequence(int(key) | mod_int)
            text = (seq.toString() or "").strip()
            if not text:
                self._end_shortcut_capture(cancel=True)
                return True
            display = self._shortcut_capture_display
            display.setText(text)
            display.setStyleSheet(self._shortcut_confirmed_style)
            QApplication.processEvents()
            display.repaint()
            QTimer.singleShot(config.SETTINGS_SHORTCUT_CAPTURE_END_DELAY_MS, self._end_shortcut_capture)
            return True

        if event.type() == QEvent.Type.MouseButtonPress:
            w = obj
            while w:
                if w is self._shortcut_capture_row:
                    break
                w = w.parentWidget() if hasattr(w, "parentWidget") else None
            else:
                self._end_shortcut_capture(cancel=True)
            return False
        return False
