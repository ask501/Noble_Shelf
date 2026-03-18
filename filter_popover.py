from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

import config
import db
from theme import (
    THEME_COLORS,
    COLOR_WHITE,
    COLOR_BTN_SAVE,
    COLOR_BTN_SAVE_BORDER,
    COLOR_BTN_CANCEL,
    COLOR_BTN_CANCEL_BORDER,
)


class FilterPopover(QDialog):
    """ゴーストバーのフィルター設定用ポップオーバー"""

    def __init__(
        self,
        parent,
        on_apply: Callable[[list[dict], str], None],
        on_clear: Callable[[], None],
        on_remove: Callable[[int], None] | None = None,
    ):
        super().__init__(parent)
        # Popup: ウィンドウ外をクリック or フォーカスが外れると自動で閉じる
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("FilterPopover")
        self.setFixedWidth(config.FILTER_POPOVER_WIDTH)

        self._on_apply = on_apply
        self._on_clear = on_clear
        self._on_remove = on_remove
        self._conditions: list[dict] = []

        self._build_ui()

    def _build_ui(self):
        # 【高さの洗い出し】高さを決めている箇所は以下のみ。個別に別の値を入れないこと。
        # - row_h = config.FILTER_POPOVER_ROW_HEIGHT（コンボ・ボタン共通の基準）
        # - _field_combo / _value_combo : setFixedHeight(row_h)
        # - _btn_add : setFixedSize(row_h, row_h) → 表示後 _sync_button_height_to_combo で左コンボ高さに統一
        # - _list : setFixedHeight(config.FILTER_POPOVER_LIST_HEIGHT)
        # - _btn_apply / _btn_clear : setFixedHeight(row_h) → 表示後 _sync で左コンボ高さに統一
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            config.FILTER_POPOVER_MARGINS,
            config.FILTER_POPOVER_MARGINS,
            config.FILTER_POPOVER_MARGINS,
            config.FILTER_POPOVER_MARGINS,
        )
        layout.setSpacing(config.FILTER_POPOVER_SPACING)

        row_h = config.FILTER_POPOVER_ROW_HEIGHT

        # 条件追加行
        row = QHBoxLayout()
        row.setSpacing(config.FILTER_POPOVER_ROW_SPACING)

        self._field_combo = QComboBox()
        self._field_combo.setFixedHeight(row_h)
        self._field_combo.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        self._field_combo.addItem("作者", "author")
        self._field_combo.addItem("サークル", "circle")
        self._field_combo.addItem("シリーズ", "series")
        self._field_combo.addItem("キャラクター", "character")
        self._field_combo.addItem("タグ", "tag")
        row.addWidget(self._field_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        # 入力フィールド兼プルダウン（editable QComboBox）
        self._value_combo = QComboBox()
        self._value_combo.setFixedHeight(row_h)
        self._value_combo.setEditable(True)
        row.addWidget(self._value_combo, 1, Qt.AlignmentFlag.AlignVCenter)

        # 入力欄のIMEやプレースホルダ設定
        line_edit = self._value_combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("値を入力")
            line_edit.setInputMethodHints(Qt.ImhNone)

        # 上段の「+」ボタン（コンボ2つの右隣）。テーマの決定ボタン色・縦中央でコンボと揃える
        self._btn_add = QPushButton("+")
        self._btn_add.setFixedSize(row_h, row_h)
        self._btn_add.setStyleSheet(
            f"""
            QPushButton {{
                background: {COLOR_BTN_SAVE}; color: {COLOR_WHITE};
                border: 1px solid {COLOR_BTN_SAVE_BORDER}; border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
                padding: 0;
            }}
            QPushButton:hover {{ background: {COLOR_BTN_SAVE_BORDER}; }}
            """
        )
        self._btn_add.clicked.connect(self._on_add_condition)
        row.addWidget(self._btn_add, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(row)

        # 項目変更でプルダウンを更新
        self._field_combo.currentIndexChanged.connect(self._on_field_changed)

        # 一致条件（ラジオボタン）
        radio_row = QHBoxLayout()
        radio_row.setSpacing(config.FILTER_POPOVER_ROW_SPACING * 2)
        lbl = QLabel("一致条件:")
        radio_row.addWidget(lbl)
        self._radio_all = QRadioButton("すべて一致")
        self._radio_any = QRadioButton("どれか一致")
        self._radio_all.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self._radio_all)
        group.addButton(self._radio_any)
        radio_row.addWidget(self._radio_all)
        radio_row.addWidget(self._radio_any)
        radio_row.addStretch()
        layout.addLayout(radio_row)

        # 条件リスト
        self._list = QListWidget()
        self._list.setFixedHeight(config.FILTER_POPOVER_LIST_HEIGHT)
        layout.addWidget(self._list)

        # 下部ボタン（上段のコンボ・入力欄と同じ高さに揃える）
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_apply = QPushButton("適用")
        self._btn_apply.setFixedSize(config.FILTER_POPOVER_APPLY_BTN_WIDTH, row_h)
        self._btn_apply.setStyleSheet(
            f"""
            QPushButton {{
                background: {COLOR_BTN_SAVE}; color: {COLOR_WHITE};
                border: 1px solid {COLOR_BTN_SAVE_BORDER}; border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
                padding: {config.FILTER_POPOVER_ACTION_BTN_PADDING_Y}px {config.FILTER_POPOVER_ACTION_BTN_PADDING_X}px;
            }}
            QPushButton:hover {{ background: {COLOR_BTN_SAVE_BORDER}; }}
            """
        )
        self._btn_apply.clicked.connect(self._on_apply_clicked)
        btn_row.addWidget(self._btn_apply)

        self._btn_clear = QPushButton("クリア")
        self._btn_clear.setFixedSize(config.FILTER_POPOVER_CLEAR_BTN_WIDTH, row_h)
        self._btn_clear.setStyleSheet(
            f"""
            QPushButton {{
                background: {COLOR_BTN_CANCEL}; color: {COLOR_WHITE};
                border: 1px solid {COLOR_BTN_CANCEL_BORDER}; border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
                padding: {config.FILTER_POPOVER_ACTION_BTN_PADDING_Y}px {config.FILTER_POPOVER_ACTION_BTN_PADDING_X}px;
            }}
            QPushButton:hover {{ background: {COLOR_BTN_CANCEL_BORDER}; }}
            """
        )
        self._btn_clear.clicked.connect(self._on_clear_clicked)
        btn_row.addWidget(self._btn_clear)

        layout.addLayout(btn_row)

        # 条件リストクリックで個別削除
        self._list.itemClicked.connect(self._on_list_item_clicked)

        # スタイル（QPushButton の高さはコードで統一。上段「+」は padding を詰めてコンボと視覚的に揃える）
        self.setStyleSheet(
            f"""
            QDialog#FilterPopover {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
            }}
            QDialog#FilterPopover QPushButton {{
                padding: 0;
            }}
            QListWidget {{
                background-color: {THEME_COLORS["bg_widget"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.FILTER_POPOVER_LIST_RADIUS}px;
            }}
            QRadioButton {{
                background-color: transparent;
            }}
            QRadioButton::indicator {{
                width: {config.FILTER_POPOVER_RADIO_INDICATOR}px;
                height: {config.FILTER_POPOVER_RADIO_INDICATOR}px;
                border-radius: {config.FILTER_POPOVER_RADIO_INDICATOR // 2}px;
                border: 1px solid {THEME_COLORS["text_main"]};
                background-color: transparent;
            }}
            QRadioButton::indicator:checked {{
                background-color: {THEME_COLORS["text_main"]};
            }}
            """
        )

        # 初期のプルダウン内容をロード
        self._reload_value_combo()

    def focusOutEvent(self, event):
        """フォーカスが外れたら閉じる（他ウィジェットへ移ったか、ウィンドウ外クリック）"""
        super().focusOutEvent(event)
        # イベント処理後にフォーカスがまだポップオーバー内かどうかで判定
        QTimer.singleShot(config.FILTER_POPOVER_FOCUS_CHECK_DELAY_MS, self._check_focus_and_close)

    def _check_focus_and_close(self):
        if not self.isVisible():
            return
        fw = QApplication.focusWidget()
        if fw is None:
            self.hide()
            return
        # フォーカスがこのダイアログまたはその子でないなら閉じる
        if not self.isAncestorOf(fw) and fw != self:
            self.hide()

    def showEvent(self, event):
        """表示時に値入力欄を空にする。左コンボの高さを参照して下部ボタン高さを同期する。"""
        super().showEvent(event)
        if hasattr(self, "_value_combo"):
            self._value_combo.setCurrentIndex(-1)
            self._value_combo.setCurrentText("")
        # 左コンボの実際の高さに「+」「追加」「クリア」を揃える（レイアウト適用後に実行）
        QTimer.singleShot(config.FILTER_POPOVER_SHOW_SYNC_DELAY_MS, self._sync_button_height_to_combo)

    def _sync_button_height_to_combo(self):
        """左コンボの高さを参照し、上段の「+」ボタンと下部の追加・クリアボタンの高さを同じにする。
        高さはここで一元で設定（個別に setFixedHeight している箇所と表示時ここで揃える）。
        """
        if not hasattr(self, "_field_combo"):
            return
        h = self._field_combo.height()
        if h <= 0:
            h = self._field_combo.sizeHint().height()
        if h <= 0:
            h = config.FILTER_POPOVER_ROW_HEIGHT
        # 上段：コンボ2つの右隣の「+」ボタン（挿入ボタン）
        if hasattr(self, "_btn_add"):
            self._btn_add.setFixedSize(h, h)
        # 下部：追加・クリアボタン
        if hasattr(self, "_btn_apply"):
            self._btn_apply.setFixedHeight(h)
        if hasattr(self, "_btn_clear"):
            self._btn_clear.setFixedHeight(h)

    def _on_add_condition(self):
        field = self._field_combo.currentData() or ""
        value = self._value_combo.currentText().strip()
        if not field or not value:
            return
        self._conditions.append({"field": field, "value": value})
        self._value_combo.setCurrentText("")
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        label_map = {
            "author": "作者",
            "circle": "サークル",
            "series": "シリーズ",
            "character": "キャラクター",
            "tag": "タグ",
        }
        for cond in self._conditions:
            field = cond.get("field")
            value = cond.get("value")
            label = label_map.get(field, field)
            item = QListWidgetItem(f"{label}: {value}  [×]")
            self._list.addItem(item)

    def _on_apply_clicked(self):
        logic = "and" if self._radio_all.isChecked() else "or"
        if self._on_apply:
            self._on_apply(self._conditions, logic)
        self.hide()

    def _on_clear_clicked(self):
        self._conditions.clear()
        self._refresh_list()
        if self._on_clear:
            self._on_clear()
        self.hide()

    # ── プルダウン連携 ──────────────────────────────────
    def _on_field_changed(self, index: int):
        self._reload_value_combo()

    def _reload_value_combo(self):
        """左側の項目に応じて既存値プルダウンを切り替える"""
        if not hasattr(self, "_value_combo"):
            return
        field = self._field_combo.currentData() or ""
        self._value_combo.blockSignals(True)
        self._value_combo.clear()
        try:
            items: list[str] = []
            if field == "author":
                items = [name for name, _cnt in db.get_all_authors_with_count()]
            elif field == "circle":
                rows = db.get_all_circles_with_count()
                items = [name for name, _cnt in rows]
            elif field == "series":
                rows = db.get_all_series_with_count()
                items = [name for name, _cnt in rows]
            elif field == "character":
                rows = db.get_all_characters_with_count()
                items = [name for name, _cnt in rows]
            elif field == "tag":
                rows = db.get_all_tags_with_count()
                items = [name for name, _cnt in rows]

            for name in items:
                if name:
                    self._value_combo.addItem(name)
        except Exception:
            pass
        finally:
            self._value_combo.blockSignals(False)
            # 初期値は入れない。選択または入力したときだけ値が入る
            self._value_combo.setCurrentIndex(-1)
            self._value_combo.setCurrentText("")

    def reset(self):
        """条件リストと選択項目をすべてクリア"""
        self._conditions = []
        self._refresh_list()
        # 入力フィールド（editable combo）のテキストもクリア
        self._value_combo.setCurrentText("")

    def _on_list_item_clicked(self, item: QListWidgetItem):
        """条件リスト内の項目クリックでその条件を削除"""
        row = self._list.row(item)
        if 0 <= row < len(self._conditions):
            self._conditions.pop(row)
            self._refresh_list()
            if self._on_remove:
                self._on_remove(row)

