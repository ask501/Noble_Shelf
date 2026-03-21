from __future__ import annotations

from collections import defaultdict
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QButtonGroup,
    QSizePolicy,
    QScrollArea,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QWheelEvent

import config
import db
from theme import THEME_COLORS

# フィールドキー → パネル上の見出しラベル（文言のみ）
_FIELD_LABELS: dict[str, str] = {
    "author": "作者",
    "circle": "サークル",
    "series": "シリーズ",
    "character": "キャラクター",
    "tag": "タグ",
}

_FIELD_ORDER: tuple[str, ...] = (
    "author",
    "circle",
    "series",
    "character",
    "tag",
)


class _NoWheelComboBox(QComboBox):
    """ホイールで選択が変わらないようにし、スクロールは親へ任せる。"""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class FilterPopover(QWidget):
    """メインウィンドウ右側の即時反映フィルターパネル（項目ごと動的ドロップダウン）。"""

    def __init__(
        self,
        parent,
        on_apply: Callable[[list[dict], str], None],
        on_clear: Callable[[], None],
        on_clear_only: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.setObjectName("FilterPopover")
        self.setFixedWidth(config.FILTER_POPOVER_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )

        self._on_apply = on_apply
        self._on_clear = on_clear
        self._on_clear_only = on_clear_only
        # 項目別：コンボを上から順に保持
        self._section_layouts: dict[str, QVBoxLayout] = {}
        self._combo_rows: dict[str, list[QComboBox]] = {
            k: [] for k in _FIELD_ORDER
        }
        # フィルタ結合: 項目間 and / or（_emit_apply で on_apply に渡す）
        self._logic: str = "and"

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            config.FILTER_POPOVER_MARGINS,
            config.FILTER_POPOVER_MARGINS,
            config.FILTER_POPOVER_MARGINS,
            config.FILTER_POPOVER_MARGINS,
        )
        layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        # 上部: AND / OR 切り替え
        header = QWidget()
        header_lo = QHBoxLayout(header)
        header_lo.setContentsMargins(
            0,
            0,
            0,
            config.FILTER_POPOVER_SECTION_SPACING,
        )
        header_lo.setSpacing(config.FILTER_POPOVER_ROW_SPACING)
        self._btn_logic_and = QPushButton(config.FILTER_POPOVER_LOGIC_AND_LABEL)
        self._btn_logic_or = QPushButton(config.FILTER_POPOVER_LOGIC_OR_LABEL)
        self._btn_logic_and.setObjectName("FilterLogicToggleButton")
        self._btn_logic_or.setObjectName("FilterLogicToggleButton")
        self._btn_logic_and.setCheckable(True)
        self._btn_logic_or.setCheckable(True)
        self._btn_logic_and.setChecked(True)
        self._btn_logic_and.setFixedHeight(config.FILTER_POPOVER_LOGIC_TOGGLE_HEIGHT)
        self._btn_logic_or.setFixedHeight(config.FILTER_POPOVER_LOGIC_TOGGLE_HEIGHT)
        self._btn_logic_and.setFont(
            QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_ACTION)
        )
        self._btn_logic_or.setFont(
            QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_ACTION)
        )
        self._logic_button_group = QButtonGroup(self)
        self._logic_button_group.setExclusive(True)
        self._logic_button_group.addButton(self._btn_logic_and, 0)
        self._logic_button_group.addButton(self._btn_logic_or, 1)
        self._logic_button_group.idClicked.connect(self._on_logic_id_clicked)
        header_lo.addWidget(self._btn_logic_and, stretch=1)
        header_lo.addWidget(self._btn_logic_or, stretch=1)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setObjectName("FilterPanelScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        inner = QWidget()
        inner.setObjectName("FilterPanelScrollContents")
        inner.setMinimumWidth(0)
        inner_lo = QVBoxLayout(inner)
        inner_lo.setContentsMargins(0, 0, 0, 0)
        inner_lo.setSpacing(config.FILTER_POPOVER_SPACING)

        title = QLabel(config.FILTER_PANEL_TITLE)
        title.setFont(
            QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL)
        )
        inner_lo.addWidget(title)

        for i, field_key in enumerate(_FIELD_ORDER):
            if i > 0:
                inner_lo.addSpacing(config.FILTER_POPOVER_SECTION_SPACING)
            lbl = QLabel(_FIELD_LABELS.get(field_key, field_key))
            lbl.setFont(
                QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL)
            )
            inner_lo.addWidget(lbl)

            section = QWidget()
            sec_lo = QVBoxLayout(section)
            sec_lo.setContentsMargins(0, 0, 0, 0)
            sec_lo.setSpacing(config.FILTER_POPOVER_ROW_SPACING)
            self._section_layouts[field_key] = sec_lo
            inner_lo.addWidget(section)
            self._append_empty_combo(field_key)

        inner_lo.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        # 下部: 条件一括クリア
        footer = QWidget()
        footer_lo = QHBoxLayout(footer)
        footer_lo.setContentsMargins(
            0,
            config.FILTER_POPOVER_SECTION_SPACING,
            0,
            0,
        )
        footer_lo.setSpacing(config.FILTER_POPOVER_ROW_SPACING)
        self._btn_clear = QPushButton(config.FILTER_POPOVER_CLEAR_LABEL)
        self._btn_clear.setObjectName("FilterClearButton")
        self._btn_clear.setFixedHeight(config.FILTER_POPOVER_LOGIC_TOGGLE_HEIGHT)
        self._btn_clear.setFont(
            QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_ACTION)
        )
        self._btn_clear.clicked.connect(self._on_clear_clicked)
        footer_lo.addWidget(self._btn_clear, stretch=1)
        layout.addWidget(footer)

        self.setStyleSheet(
            f"""
            QWidget#FilterPopover {{
                background-color: {THEME_COLORS["bg_panel"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
            }}
            QScrollArea#FilterPanelScroll {{
                background-color: transparent;
                border: none;
            }}
            QWidget#FilterPanelScrollContents {{
                background-color: transparent;
            }}
            QWidget#FilterPopover QComboBox {{
                background-color: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.FILTER_POPOVER_LIST_RADIUS}px;
                padding-top: {config.FILTER_POPOVER_COMBO_PADDING_Y}px;
                padding-bottom: {config.FILTER_POPOVER_COMBO_PADDING_Y}px;
                padding-left: {config.FILTER_POPOVER_COMBO_PADDING_LEFT}px;
                padding-right: {config.FILTER_POPOVER_COMBO_PADDING_RIGHT}px;
                min-width: 0;
                min-height: {config.FILTER_POPOVER_COMBO_OUTER_HEIGHT}px;
            }}
            QWidget#FilterPopover QComboBox:hover {{
                border-color: {THEME_COLORS["accent"]};
            }}
            QWidget#FilterPopover QComboBox::drop-down {{
                border: none;
                width: {config.FILTER_POPOVER_COMBO_DROPDOWN_WIDTH}px;
            }}
            QWidget#FilterPopover QPushButton#FilterComboClearButton {{
                background: {THEME_COLORS["btn_cancel"]};
                color: {THEME_COLORS["btn_cancel_fg"]};
                border: 1px solid {THEME_COLORS["btn_cancel_border"]};
                border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
                padding: 0;
            }}
            QWidget#FilterPopover QPushButton#FilterComboClearButton:hover {{
                background: {THEME_COLORS["btn_cancel_border"]};
                color: {THEME_COLORS["btn_cancel_fg"]};
            }}
            QWidget#FilterPopover QPushButton#FilterLogicToggleButton {{
                background-color: {THEME_COLORS["bg_widget"]};
                color: {THEME_COLORS["text_main"]};
                border: 1px solid {THEME_COLORS["border"]};
                border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
                padding: {config.FILTER_POPOVER_ACTION_BTN_PADDING_Y}px
                    {config.FILTER_POPOVER_ACTION_BTN_PADDING_X}px;
            }}
            QWidget#FilterPopover QPushButton#FilterLogicToggleButton:checked {{
                background-color: {THEME_COLORS["accent"]};
                border-color: {THEME_COLORS["accent"]};
                color: {THEME_COLORS["fg_on_accent"]};
            }}
            QWidget#FilterPopover QPushButton#FilterClearButton {{
                background: {THEME_COLORS["btn_cancel"]};
                color: {THEME_COLORS["btn_cancel_fg"]};
                border: 1px solid {THEME_COLORS["btn_cancel_border"]};
                border-radius: {config.FILTER_POPOVER_BORDER_RADIUS}px;
                padding: {config.FILTER_POPOVER_ACTION_BTN_PADDING_Y}px
                    {config.FILTER_POPOVER_ACTION_BTN_PADDING_X}px;
            }}
            QWidget#FilterPopover QPushButton#FilterClearButton:hover {{
                background: {THEME_COLORS["btn_cancel_border"]};
                color: {THEME_COLORS["btn_cancel_fg"]};
            }}
            """
        )

    def _fetch_items(self, field: str) -> list[str]:
        items: list[str] = []
        try:
            if field == "author":
                items = [n for n, _c in db.get_all_authors_with_count() if n]
            elif field == "circle":
                items = [n for n, _c in db.get_all_circles_with_count() if n]
            elif field == "series":
                items = [n for n, _c in db.get_all_series_with_count() if n]
            elif field == "character":
                items = [n for n, _c in db.get_all_characters_with_count() if n]
            elif field == "tag":
                items = [n for n, _c in db.get_all_tags_with_count() if n]
        except Exception:
            pass
        return items

    def _populate_combo(self, combo: QComboBox, field: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(config.FILTER_PANEL_NONE_LABEL, None)
        for name in self._fetch_items(field):
            combo.addItem(name, name)
        combo.blockSignals(False)

    def _create_combo(self, field: str) -> QComboBox:
        cb = _NoWheelComboBox()
        cb.setMinimumHeight(config.FILTER_POPOVER_COMBO_OUTER_HEIGHT)
        cb.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        cb.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        cb.setMinimumContentsLength(
            config.FILTER_POPOVER_COMBO_MIN_VISIBLE_CHARS
        )
        cb.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        cb.setEditable(False)
        cb.view().setAutoScroll(False)
        self._populate_combo(cb, field)
        cb.currentIndexChanged.connect(
            lambda _i, fk=field: self._on_field_combo_changed(fk)
        )
        return cb

    def _wrap_combo_with_clear(self, field: str, combo: QComboBox) -> QWidget:
        """コンボと×（1行削除）を横並びにした行ウィジェット。"""
        row = QWidget()
        row_lo = QHBoxLayout(row)
        row_lo.setContentsMargins(0, 0, 0, 0)
        row_lo.setSpacing(config.FILTER_POPOVER_ROW_SPACING)
        row_lo.addWidget(combo, stretch=1)
        btn_clear = QPushButton(config.FILTER_PANEL_CLOSE_SYMBOL)
        btn_clear.setObjectName("FilterComboClearButton")
        btn_clear.setFixedSize(
            config.FILTER_POPOVER_COMBO_OUTER_HEIGHT,
            config.FILTER_POPOVER_COMBO_OUTER_HEIGHT,
        )
        btn_clear.setToolTip(config.FILTER_POPOVER_COMBO_CLEAR_TOOLTIP)
        btn_clear.setVisible(combo.currentIndex() > 0)
        row_lo.addWidget(btn_clear, 0, Qt.AlignmentFlag.AlignVCenter)
        btn_clear.clicked.connect(
            lambda _checked=False, fk=field, c=combo: self._on_combo_clear_clicked(
                fk, c
            )
        )
        return row

    def _clear_button_for_combo_row(self, combo: QComboBox) -> QPushButton | None:
        """コンボ行レイアウト内の×ボタンを取得（[コンボ][×] の順で配置している前提）。"""
        row = combo.parentWidget()
        if row is None:
            return None
        lay = row.layout()
        if lay is None or lay.count() < 2:
            return None
        item = lay.itemAt(1)
        if item is None:
            return None
        w = item.widget()
        return w if isinstance(w, QPushButton) else None

    def _refresh_clear_buttons(self, field: str) -> None:
        """選択済み（currentIndex > 0）の行だけ×を表示する。"""
        for c in self._combo_rows[field]:
            btn = self._clear_button_for_combo_row(c)
            if btn is not None:
                btn.setVisible(c.currentIndex() > 0)

    def _on_combo_clear_clicked(self, field: str, combo: QComboBox) -> None:
        if combo not in self._combo_rows[field]:
            return
        self._block_field_signals(field, True)
        try:
            self._remove_combo(field, combo)
            self._normalize_field(field)
            self._refresh_clear_buttons(field)
        finally:
            self._block_field_signals(field, False)
        self._emit_apply()

    def _append_empty_combo(self, field: str) -> QComboBox:
        lo = self._section_layouts[field]
        cb = self._create_combo(field)
        cb.blockSignals(True)
        cb.setCurrentIndex(0)
        cb.blockSignals(False)
        row = self._wrap_combo_with_clear(field, cb)
        lo.addWidget(row)
        self._combo_rows[field].append(cb)
        return cb

    def _remove_combo(self, field: str, combo: QComboBox) -> None:
        if combo not in self._combo_rows[field]:
            return
        self._combo_rows[field].remove(combo)
        row = combo.parentWidget()
        if row is not None:
            self._section_layouts[field].removeWidget(row)
            row.deleteLater()
        else:
            self._section_layouts[field].removeWidget(combo)
            combo.deleteLater()

    def _block_field_signals(self, field: str, block: bool) -> None:
        for c in self._combo_rows[field]:
            c.blockSignals(block)

    def _on_field_combo_changed(self, field: str) -> None:
        self._block_field_signals(field, True)
        try:
            self._normalize_field(field)
            self._refresh_clear_buttons(field)
        finally:
            self._block_field_signals(field, False)
        self._emit_apply()

    def _normalize_field(self, field: str) -> None:
        """末尾の重複「指定なし」を削除し、値があるときは末尾に空枠1つを保証する。"""
        rows = self._combo_rows[field]
        if not rows:
            self._append_empty_combo(field)
            return

        # 末尾が「指定なし」が2つ以上続く場合は1つまで削る
        while (
            len(rows) >= 2
            and rows[-1].currentIndex() == 0
            and rows[-2].currentIndex() == 0
        ):
            self._remove_combo(field, rows[-1])
            rows = self._combo_rows[field]

        has_value = any(c.currentIndex() > 0 for c in rows)

        if has_value:
            if rows[-1].currentIndex() != 0:
                self._append_empty_combo(field)
        else:
            while len(rows) > 1:
                self._remove_combo(field, rows[-1])
                rows = self._combo_rows[field]

    def _emit_apply(self) -> None:
        conditions: list[dict] = []
        for field in _FIELD_ORDER:
            seen: set[str] = set()
            for cb in self._combo_rows[field]:
                if cb.currentIndex() <= 0:
                    continue
                value = (cb.currentText() or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                conditions.append({"field": field, "value": value})
        if self._on_apply:
            self._on_apply(conditions, self._logic)

    def _on_logic_id_clicked(self, button_id: int) -> None:
        """AND/OR トグル。変更時のみ即時フィルタを反映する。"""
        new_logic = "and" if button_id == 0 else "or"
        if new_logic == self._logic:
            return
        self._logic = new_logic
        self._emit_apply()

    def _on_clear_clicked(self) -> None:
        """パネル下部クリア: UI リセット後に親へ反映（on_clear_only 優先）。"""
        self.reset()
        if self._on_clear_only:
            self._on_clear_only()
        elif self._on_clear:
            self._on_clear()

    def reset(self) -> None:
        self._btn_logic_and.blockSignals(True)
        self._btn_logic_or.blockSignals(True)
        try:
            self._logic = "and"
            self._btn_logic_and.setChecked(True)
            self._btn_logic_or.setChecked(False)
        finally:
            self._btn_logic_and.blockSignals(False)
            self._btn_logic_or.blockSignals(False)
        for field in _FIELD_ORDER:
            self._block_field_signals(field, True)
            try:
                while len(self._combo_rows[field]) > 1:
                    self._remove_combo(field, self._combo_rows[field][-1])
                if self._combo_rows[field]:
                    self._combo_rows[field][0].setCurrentIndex(0)
                self._refresh_clear_buttons(field)
            finally:
                self._block_field_signals(field, False)

    def _repopulate_combo_preserve(self, combo: QComboBox, field: str) -> None:
        prev = ""
        if combo.currentIndex() > 0:
            prev = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(config.FILTER_PANEL_NONE_LABEL, None)
        for name in self._fetch_items(field):
            combo.addItem(name, name)
        if prev:
            idx = combo.findText(prev, Qt.MatchFlag.MatchExactly)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(prev, prev)
                combo.setCurrentIndex(combo.count() - 1)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def repopulate_all_combos(self) -> None:
        """全フィールドのコンボ候補を DB 最新で再構築し、親へフィルタを再適用する。"""
        for field in _FIELD_ORDER:
            self._block_field_signals(field, True)
            try:
                for cb in list(self._combo_rows[field]):
                    self._repopulate_combo_preserve(cb, field)
                self._normalize_field(field)
                self._refresh_clear_buttons(field)
            finally:
                self._block_field_signals(field, False)
        self._emit_apply()

    def showEvent(self, event):
        super().showEvent(event)
        self._emit_apply()

    def sync_from_parent(self, active: list[dict], logic: str = "and") -> None:
        logic_norm = (logic or "and").strip().lower()
        if logic_norm not in ("and", "or"):
            logic_norm = "and"
        self._btn_logic_and.blockSignals(True)
        self._btn_logic_or.blockSignals(True)
        try:
            self._logic = logic_norm
            self._btn_logic_and.setChecked(logic_norm == "and")
            self._btn_logic_or.setChecked(logic_norm == "or")
        finally:
            self._btn_logic_and.blockSignals(False)
            self._btn_logic_or.blockSignals(False)

        grouped: dict[str, list[str]] = defaultdict(list)
        seen_pair: set[tuple[str, str]] = set()
        for c in active:
            f = (c.get("field") or "").strip()
            v = (c.get("value") or "").strip()
            if not f or not v or f not in self._combo_rows:
                continue
            key = (f, v)
            if key in seen_pair:
                continue
            seen_pair.add(key)
            grouped[f].append(v)

        for field in _FIELD_ORDER:
            self._block_field_signals(field, True)
            try:
                while self._combo_rows[field]:
                    self._remove_combo(field, self._combo_rows[field][-1])
                lo = self._section_layouts[field]
                vals = grouped.get(field, [])
                for v in vals:
                    cb = self._create_combo(field)
                    row = self._wrap_combo_with_clear(field, cb)
                    lo.addWidget(row)
                    self._combo_rows[field].append(cb)
                    cb.blockSignals(True)
                    idx = cb.findText(v, Qt.MatchFlag.MatchExactly)
                    if idx < 0:
                        cb.addItem(v, v)
                        idx = cb.count() - 1
                    cb.setCurrentIndex(idx)
                    cb.blockSignals(False)
                self._append_empty_combo(field)
                self._normalize_field(field)
                self._refresh_clear_buttons(field)
            finally:
                self._block_field_signals(field, False)
