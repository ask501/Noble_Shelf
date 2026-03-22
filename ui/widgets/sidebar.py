"""
sidebar.py - サイドバー
モード切替（作品名/サークル/作者/シリーズ/キャラ/タグ/追加順/履歴）+
リスト表示 → クリックでグリッドフィルタリング
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QLabel,
    QSizePolicy, QStyledItemDelegate, QStyleOptionViewItem, QStyle,
    QStackedWidget, QMenu, QApplication,
)
from PySide6.QtCore import Qt, Signal, QRect, QSize, QEvent
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QFontMetrics
from ui.utils.auto_scroll_mixin import AutoScrollListWidget

import db
import config
from theme import THEME_COLORS, COLOR_BORDER, COLOR_WHITE, COLOR_BADGE_BG

# ── モード定義 ────────────────────────────────────────
def _build_sidebar_modes():
    from plugin_loader import has_enabled_plugins
    modes = [
        ("added_date", "追加順"),
        ("title", "作品名"),
        ("circle", "サークル"),
        ("author", "作者"),
        ("series", "シリーズ"),
        ("character", "キャラクター"),
        ("tag", "タグ"),
    ]
    if has_enabled_plugins():
        modes.append(("metadata", "メタデータ"))
    modes.extend([
        ("favorite", "お気に入り"),
        ("history", "履歴"),
    ])
    return modes


SIDEBAR_MODES = _build_sidebar_modes()


class SidebarItemDelegate(QStyledItemDelegate):
    """サイドバーのリスト項目に件数バッジを描画するデリゲート"""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()

        rect = option.rect
        text = index.data(Qt.DisplayRole) or ""
        value = index.data(Qt.UserRole)
        count = index.data(Qt.UserRole + 1) or 0

        # 背景（選択のみ。ホバー時は色を変えない）
        if option.state & QStyle.State_Selected:
            bg = QColor(THEME_COLORS["accent"])
        else:
            bg = QColor(0, 0, 0, 0)
        if bg.alpha() > 0:
            painter.setBrush(bg)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                rect.adjusted(
                    config.SIDEBAR_DELEGATE_BG_INSET,
                    config.SIDEBAR_DELEGATE_BG_INSET,
                    -config.SIDEBAR_DELEGATE_BG_INSET,
                    -config.SIDEBAR_DELEGATE_BG_INSET,
                ),
                config.SIDEBAR_ITEM_RADIUS,
                config.SIDEBAR_ITEM_RADIUS,
            )

        # バッジのサイズ計算
        badge_margin = config.SIDEBAR_BADGE_MARGIN
        show_badge = isinstance(count, int) and count > 0 and value is not None
        badge_text = str(count) if show_badge else ""

        fm_badge = QFontMetrics(QFont(config.FONT_FAMILY, config.FONT_SIZE_SIDEBAR_BADGE))
        badge_h = config.SIDEBAR_BADGE_HEIGHT
        badge_w = (
            max(badge_h, fm_badge.horizontalAdvance(badge_text) + config.SIDEBAR_BADGE_TEXT_PAD)
            if show_badge
            else 0
        )

        # テキスト描画領域（右端にバッジスペースを確保）
        text_right = rect.right() - (
            badge_w + badge_margin if show_badge else config.SIDEBAR_TEXT_RIGHT_INSET_NO_BADGE
        )
        text_left = rect.left() + config.SIDEBAR_ITEM_PADDING_X
        text_rect = QRect(text_left, rect.top(), max(0, text_right - text_left), rect.height())

        # テキスト色
        if option.state & QStyle.State_Selected:
            text_color = QColor(COLOR_WHITE)
        else:
            text_color = QColor(THEME_COLORS["text_main"])

        painter.setPen(QPen(text_color))
        fm_text = QFontMetrics(painter.font())
        elided = fm_text.elidedText(text, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        # 件数バッジ
        if show_badge:
            widget = option.widget
            view_width = (
                widget.viewport().width()
                if widget and hasattr(widget, "viewport")
                else config.SIDEBAR_VIEWPORT_FALLBACK_WIDTH
            )
            bx = view_width - badge_w - config.SIDEBAR_BADGE_MARGIN_RIGHT
            by = rect.center().y() - badge_h // 2
            badge_rect = QRect(bx, by, badge_w, badge_h)

            painter.setClipping(False)
            painter.setBrush(QColor(COLOR_BADGE_BG))
            painter.setPen(Qt.NoPen)
            radius = badge_h / 2
            painter.drawRoundedRect(badge_rect, radius, radius)

            painter.setPen(QPen(QColor(COLOR_WHITE)))
            painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        painter.restore()


class SidebarWidget(QWidget):
    """サイドバー本体"""

    # シグナル: フィルタ変更 → app.pyがgridに渡す
    filterChanged = Signal(str, str)   # mode, value  ("circle", "島田流")
    filterCleared = Signal()           # "すべて" 選択時
    # ソートモード変更（コンボボックスのモード変更時）
    sortModeChanged = Signal(str)      # mode ("title", "circle", ...)
    titleSelected = Signal(str)       # path
    # サイドバー右クリックで選択項目のコンテキストメニューを表示したいとき（path が有効な場合のみ）
    contextMenuRequested = Signal(str, object)  # path, global_pos (QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(config.SIDEBAR_WIDTH)
        self.setObjectName("Sidebar")
        self.setStyleSheet(f"""
            QWidget#Sidebar {{
                background: {THEME_COLORS['bg_panel']};
            }}
        """)

        # 初期モード（コンボの選択は _setup_ui で同期）
        self._mode = "title"
        self._title_books: list[dict] = []
        self._showing_filter_result = False
        self._filter_result_books: list[dict] = []
        self._setup_ui()
        self.refresh()

    # ── UI構築 ────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        ml, mt, mr, mb = config.SIDEBAR_MARGINS
        layout.setContentsMargins(ml, mt, mr, mb)
        layout.setSpacing(config.SIDEBAR_SPACING)

        # ヘッダー（コンボ＋下線）コンテナ: ゴーストバーと高さを揃える
        header_container = QWidget()
        header_container.setFixedHeight(config.GHOSTBAR_HEIGHT)
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(*config.LAYOUT_MARGINS_ZERO)
        header_layout.setSpacing(config.LAYOUT_SPACING_ZERO)

        # モード選択コンボ or フィルター結果時の固定ラベル（同じ枠で切替）
        self._combo = QComboBox()
        self._combo.setFixedHeight(config.SIDEBAR_HEADER_CONTROL_HEIGHT)
        for key, label in SIDEBAR_MODES:
            self._combo.addItem(label, key)
        self._combo.setCurrentIndex(0)
        self._mode = "title"
        self._combo.currentIndexChanged.connect(self._on_mode_changed)

        self._filter_result_label = QLabel("フィルター")
        self._filter_result_label.setFixedHeight(config.SIDEBAR_HEADER_CONTROL_HEIGHT)
        self._filter_result_label.setAlignment(Qt.AlignCenter)
        self._filter_result_label.setStyleSheet(
            f"background: {THEME_COLORS['bg_widget']}; color: {THEME_COLORS['text_main']}; "
            f"border: 1px solid {THEME_COLORS['border']}; border-radius: {config.SIDEBAR_ITEM_RADIUS}px; "
            f"font-size: {config.FONT_SIZE_BTN_ACTION}px;"
        )

        self._header_stack = QStackedWidget()
        # コンボが右端で切れないよう、サイドバー内容幅いっぱいを確保
        content_w = config.SIDEBAR_WIDTH - ml - mr
        self._header_stack.setMinimumWidth(content_w)
        self._header_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._header_stack.addWidget(self._combo)
        self._header_stack.addWidget(self._filter_result_label)
        header_layout.addWidget(self._header_stack)

        # セパレーター（メインのゴーストバー下・グリッド上と同じフラット1px線）
        sep = QWidget()
        sep.setFixedHeight(config.SEPARATOR_LINE_HEIGHT)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER};")
        header_layout.addWidget(sep)

        layout.addWidget(header_container)

        # リスト
        self._list = AutoScrollListWidget()
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                color: {THEME_COLORS['text_main']};
                padding: {config.SIDEBAR_ITEM_PADDING_Y}px {config.SIDEBAR_ITEM_PADDING_X}px;
                border-radius: {config.SIDEBAR_ITEM_RADIUS}px;
                font-size: {config.FONT_SIZE_SIDEBAR_ITEM}px;
            }}
            QListWidget::item:selected {{
                background: {THEME_COLORS['accent']};
                color: {COLOR_WHITE};
            }}
            QListWidget::item:hover:!selected {{
                background: transparent;
            }}
        """)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.installEventFilter(self)
        # 件数バッジ付きのカスタム描画を適用
        self._list.setItemDelegate(SidebarItemDelegate(self._list))
        layout.addWidget(self._list)

    # ── モード切替 ────────────────────────────────────
    def _on_mode_changed(self, index: int):
        self._mode = self._combo.itemData(index)
        # モード変更時はいったん選択状態をクリアしてからリストを再構築する
        self._list.clearSelection()
        self._list.setCurrentRow(-1)
        self.refresh()
        # ソートモードとしても扱う
        self.sortModeChanged.emit(self._mode)

    def set_mode_and_select(self, mode: str, value: str):
        """指定モードに切り替えて該当値を選択状態にする（シグナルは手動制御）"""
        # コンボボックスをモード切替（シグナルをブロックして二重発火防止）
        self._combo.blockSignals(True)
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == mode:
                self._combo.setCurrentIndex(i)
                self._mode = mode
                break
        self._combo.blockSignals(False)

        # リスト再構築
        self.refresh()

        # 該当valueを選択状態にしてシグナル発火
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.UserRole) == value:
                self._list.setCurrentItem(item)
                # filterChangedは呼び出し元(app.py)が処理するので直接emitしない
                self.filterChanged.emit(mode, value)
                break

    def set_filter_result_mode(self, active: bool, books: list[dict] | None = None):
        """複合フィルター適用中はプルダウンを隠し「フィルター」表示＋結果一覧にする"""
        self._showing_filter_result = active
        self._filter_result_books = list(books or [])
        if active:
            # フィルタ結果モードに入るときも選択をクリアしておく
            self._list.clearSelection()
            self._list.setCurrentRow(-1)
            self._header_stack.setCurrentWidget(self._filter_result_label)
        else:
            self._header_stack.setCurrentWidget(self._combo)
        self.refresh()

    # ── リスト更新 ────────────────────────────────────
    def refresh(self):
        """現在のモードに合わせてリストを再構築"""
        # スクロール位置と現在選択値を保存
        scroll_pos = self._list.verticalScrollBar().value()
        current_value = (
            self._list.currentItem().data(Qt.UserRole)
            if self._list.currentItem() is not None
            else None
        )

        self._list.clear()

        # フィルター結果表示モード: フィルター結果の一覧のみ
        if self._showing_filter_result:
            for b in self._filter_result_books:
                path = b.get("path") or ""
                if not path:
                    continue
                title = b.get("title") or b.get("name") or path
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, path)
                item.setData(Qt.UserRole + 1, 0)
                self._list.addItem(item)
            self._list.verticalScrollBar().setValue(scroll_pos)
            return

        # 先頭アイテム: 作品名・追加順は「すべて」、それ以外は「不明」。メタデータ・お気に入り・履歴は先頭なし
        if self._mode not in ("metadata", "favorite", "history"):
            if self._mode in ("title", "added_date"):
                first_label = "すべて"
                first_value = None
            else:
                first_label = "不明"
                first_value = "__unknown__"
            all_item = QListWidgetItem(first_label)
            all_item.setData(Qt.UserRole, first_value)
            all_item.setData(Qt.UserRole + 1, 0)
            self._list.addItem(all_item)

        items = self._get_items()
        for label, value, count in items:
            # 表示テキストはラベルのみ。件数は別ロールに保持し、デリゲート側でバッジとして描画。
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, value)
            # count は SQLite Row などの場合があるので、明示的に int に変換
            item.setData(Qt.UserRole + 1, int(count) if count else 0)
            self._list.addItem(item)

        # 可能なら元の選択を復元、それ以外は先頭（「すべて」）
        if current_value is not None:
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item and item.data(Qt.UserRole) == current_value:
                    self._list.setCurrentRow(i)
                    break
        else:
            self._list.setCurrentRow(0)

        # スクロール位置を復元
        self._list.verticalScrollBar().setValue(scroll_pos)

    def _get_items(self) -> list[tuple[str, str, int]]:
        """モードに応じたDBデータを返す (label, value, count)"""
        mode = self._mode
        try:
            if mode == "circle":
                rows = db.get_all_circles_with_count()
                return [(r[0], r[0], r[1]) for r in rows if r[0]]

            elif mode == "title":
                books = getattr(self, "_title_books", []) or []
                return [
                    (b.get("title") or b.get("name", ""), b.get("path", ""), 0)
                    for b in books
                    if b.get("path")
                ]

            elif mode == "author":
                rows = db.get_all_authors_with_count()
                return [(r[0], r[0], r[1]) for r in rows if r[0]]  # (label, value, count)

            elif mode == "series":
                # series は book_meta にあるので、全件メタを一括取得して集計
                from collections import Counter
                all_metas = db.get_all_book_metas()  # {path: meta_dict}
                series_list = [
                    meta["series"]
                    for meta in all_metas.values()
                    if meta.get("series")
                ]
                counts = Counter(series_list)
                return [(s, s, n) for s, n in sorted(counts.items())]

            elif mode == "character":
                rows = db.get_all_characters_with_count()
                return [(r[0], r[0], r[1]) for r in rows if r[0]]

            elif mode == "tag":
                rows = db.get_all_tags_with_count()
                return [(r[0], r[0], r[1]) for r in rows if r[0]]

            elif mode == "added_date":
                # 作品名を追加順（updated_at 降順）で一覧
                rows = db.get_all_books_order_by_added_desc()
                return [
                    (row[2] or row[0] or row[3], row[3], 0)  # title or name, path, count
                    for row in rows
                    if row[3]
                ]

            elif mode == "history":
                rows = db.get_recent_books(limit=config.SIDEBAR_HISTORY_RECENT_LIMIT)
                return [(r[0], r[1], 0) for r in rows if r[0]]

            elif mode == "metadata":
                rows = db.get_meta_source_counts()
                return [(label, key, count) for key, label, count in rows]

            elif mode == "favorite":
                from collections import Counter
                bm = db.get_all_bookmarks()  # {path: rating}
                counts = Counter(bm.values())
                items = [("不明", "0", len(db.get_all_books()) - len(bm))]
                for r in range(1, 6):
                    star = "★" * r
                    items.append((star, str(r), counts.get(r, 0)))
                return items

        except Exception:
            pass
        return []

    def set_title_items(self, books: list[dict]):
        """グリッドのソート済みリストをそのまま作品名一覧に使う"""
        # 現在の選択値を保持しておき、リフレッシュ後に復元する
        current_value = None
        if self._mode == "title" and self._list.currentItem() is not None:
            current_value = self._list.currentItem().data(Qt.UserRole)

        self._title_books = books
        if self._mode == "title":
            self.refresh()
            if current_value is not None:
                for i in range(self._list.count()):
                    item = self._list.item(i)
                    if item and item.data(Qt.UserRole) == current_value:
                        self._list.setCurrentRow(i)
                        break

    # ── クリック処理 ──────────────────────────────────
    def _on_item_clicked(self, item: QListWidgetItem):
        value = item.data(Qt.UserRole)
        if self._showing_filter_result:
            if value:
                self.titleSelected.emit(value)
            return
        if value is None:
            self.filterCleared.emit()
        else:
            self.filterChanged.emit(self._mode, value)

    # ── コンテキストメニュー（右クリック）────────────────
    def eventFilter(self, obj, event):
        if obj == self._list and event.type() == QEvent.Type.ContextMenu:
            pos = self._list.mapFromGlobal(event.globalPos())
            item = self._list.itemAt(pos)
            if item is not None:
                value = item.data(Qt.UserRole)
                label = (item.data(Qt.DisplayRole) or "") if item.data(Qt.DisplayRole) else ""
                # 作品名・追加順・履歴・フィルター結果では value が path
                is_path = (
                    isinstance(value, str)
                    and value
                    and (self._showing_filter_result or self._mode in ("title", "added_date", "history"))
                )
                if is_path:
                    self.contextMenuRequested.emit(value, event.globalPos())
                    return True
                # それ以外（サークル・作者など）は簡易メニュー：コピーのみ
                menu = QMenu(self)
                menu.setStyleSheet(
                    f"""
                    QMenu {{ background-color: {THEME_COLORS["bg_panel"]}; color: {THEME_COLORS["text_main"]}; }}
                    QMenu::item:selected {{ background-color: {THEME_COLORS["hover"]}; }}
                    """
                )
                act_copy = menu.addAction("コピー")
                act_copy.triggered.connect(lambda _=None, t=label: QApplication.clipboard().setText(t or ""))
                menu.exec(event.globalPos())
                return True
        return super().eventFilter(obj, event)
