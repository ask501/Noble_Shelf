"""settings_dialog.py - 設定ダイアログ"""
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QDialogButtonBox,
    QFontComboBox,
    QComboBox,
    QApplication,
    QMessageBox,
    QProgressDialog,
    QTabWidget,
    QWidget,
    QFormLayout,
    QScrollArea,
    QSpinBox,
    QCheckBox,
)
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QKeyEvent
import os

import db
import config
from theme import (
    apply_dark_titlebar,
    SETTINGS_SHORTCUT_HINT_STYLE,
    SETTINGS_SHORTCUT_DISPLAY_STYLE_NORMAL,
    SETTINGS_SHORTCUT_DISPLAY_STYLE_CAPTURE,
    SETTINGS_SHORTCUT_DISPLAY_STYLE_CONFIRMED,
    SETTINGS_CARD_PREVIEW_THUMB_BG,
    SETTINGS_CARD_PREVIEW_META_OK_BG,
    COLOR_BG_WIDGET,
    COLOR_BORDER,
    COLOR_STAR_ACTIVE,
    COLOR_CARD_TITLE_FG,
    COLOR_CARD_SUB_FG,
    CARD_BADGE_OVERLAY_ALPHA,
    CARD_RATING_BG_ALPHA,
)
from context_menu import resolve_shortcut, is_valid_store_viewer_path
from properties._utils import BTN_CANCEL_STYLE, BTN_SAVE_STYLE

# ビュアー選択のファイル種類（.exe と .lnk を同じ一覧で参照）
VIEWER_FILE_FILTER = "ビュアー (*.exe *.lnk);;実行ファイル (*.exe);;ショートカット (*.lnk);;すべてのファイル (*.*)"


def _find_viewer_dir_on_any_drive(relative_paths: list[str]) -> str:
    """
    C: から Z: までスキャンし、いずれかのドライブに存在する
    相対パス（例: Program Files\\DMM\\DMMbookviewer）を返す。
    見つからなければ空文字。
    """
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = letter + ":\\"
        try:
            if not os.path.exists(drive):
                continue
        except OSError:
            continue
        for rel in relative_paths:
            p = os.path.join(drive, rel)
            if os.path.isdir(p):
                return p
    return ""


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_dark_titlebar(self)
        self.setWindowTitle(config.APP_TITLE)
        self.setModal(True)
        self.setMinimumSize(*config.SETTINGS_DIALOG_MIN_SIZE)
        self.resize(*config.SETTINGS_DIALOG_DEFAULT_SIZE)
        self._setup_ui()
        self._load()

    def closeEvent(self, event):
        if getattr(self, "_active_shortcut_id", None) is not None:
            self._end_shortcut_capture(cancel=True)
        super().closeEvent(event)

    def reject(self):
        if getattr(self, "_active_shortcut_id", None) is not None:
            self._end_shortcut_capture(cancel=True)
        super().reject()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*config.SETTINGS_DIALOG_MARGINS)
        layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        tabs = QTabWidget()
        # ── タブ1: 一般 ──
        general = QWidget()
        general_layout = QVBoxLayout(general)
        general_layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        # 綴じ方向
        direction_row = QHBoxLayout()
        direction_label = QLabel("ビューアー綴じ方向")
        direction_label.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        direction_row.addWidget(direction_label)
        self._direction_combo = QComboBox()
        self._direction_combo.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        self._direction_combo.addItem("右綴じで表示する", config.VIEWER_DIRECTION_DATA_RTL)
        self._direction_combo.addItem("左綴じで表示する", config.VIEWER_DIRECTION_DATA_LTR)
        direction_row.addWidget(self._direction_combo)
        general_layout.addLayout(direction_row)

        # 外部ビュアー
        lbl = QLabel("外部ビュアー (未設定なら既定のアプリで開く)")
        lbl.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        general_layout.addWidget(lbl)

        row = QHBoxLayout()
        self._viewer_edit = QLineEdit()
        self._viewer_edit.setPlaceholderText(
            r"例: C:\Program Files\Honeyview\Honeyview.exe"
        )
        self._viewer_edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row.addWidget(self._viewer_edit)

        btn_browse = QPushButton("参照...")
        btn_browse.setFixedWidth(config.SETTINGS_BROWSE_BTN_WIDTH)
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        general_layout.addLayout(row)

        # DMMビュアー
        lbl_dmm = QLabel("DMMビュアー (dmmb/dmme/dmmr用)")
        lbl_dmm.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        general_layout.addWidget(lbl_dmm)

        row_dmm = QHBoxLayout()
        self._dmm_viewer_edit = QLineEdit()
        self._dmm_viewer_edit.setPlaceholderText(r"例: C:\Program Files\DMMブックス\DMMBooks.exe")
        self._dmm_viewer_edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_dmm.addWidget(self._dmm_viewer_edit)
        btn_dmm = QPushButton("参照...")
        btn_dmm.setFixedWidth(config.SETTINGS_BROWSE_BTN_WIDTH)
        btn_dmm.clicked.connect(self._browse_dmm)
        row_dmm.addWidget(btn_dmm)
        general_layout.addLayout(row_dmm)

        # DLSiteビュアー
        lbl_dlsite = QLabel("DLSiteビュアー (dlst用)")
        lbl_dlsite.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        general_layout.addWidget(lbl_dlsite)

        row_dlsite = QHBoxLayout()
        self._dlsite_viewer_edit = QLineEdit()
        self._dlsite_viewer_edit.setPlaceholderText(r"例: C:\Program Files\DLSite\DLSitePlay.exe")
        self._dlsite_viewer_edit.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_INPUT))
        row_dlsite.addWidget(self._dlsite_viewer_edit)
        btn_dlsite = QPushButton("参照...")
        btn_dlsite.setFixedWidth(config.SETTINGS_BROWSE_BTN_WIDTH)
        btn_dlsite.clicked.connect(self._browse_dlsite)
        row_dlsite.addWidget(btn_dlsite)
        general_layout.addLayout(row_dlsite)

        # フォントファミリー
        font_row = QHBoxLayout()
        font_label = QLabel("フォント")
        font_label.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        font_row.addWidget(font_label)

        self._font_combo = QFontComboBox()
        # 日本語フォントのみを対象にする
        self._font_combo.setWritingSystem(QFontDatabase.WritingSystem.Japanese)
        current_family = db.get_setting("font_family") or config.FONT_FAMILY
        raw_size = db.get_setting("font_size")
        try:
            pt = int(raw_size) if raw_size is not None else config.FONT_SIZE_DEFAULT
        except (TypeError, ValueError):
            pt = config.FONT_SIZE_DEFAULT
        if pt <= 0:
            pt = config.FONT_SIZE_DEFAULT
        self._font_combo.setCurrentFont(QFont(current_family, pt))
        self._font_combo.currentFontChanged.connect(
            lambda f: self._apply_font(f.family())
        )
        font_row.addWidget(self._font_combo)
        # 綴じ方向コンボをフォントコンボと同じサイズポリシーに揃える（フォント行の QFontComboBox 基準）
        self._direction_combo.setSizePolicy(self._font_combo.sizePolicy())

        general_layout.addLayout(font_row)

        # [サークル名]作品名 に一括リネーム
        bulk_rename_btn = QPushButton("[サークル名]作品名に一括リネーム")
        bulk_rename_btn.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_DEFAULT))
        bulk_rename_btn.clicked.connect(self._on_bulk_rename)
        general_layout.addWidget(bulk_rename_btn)

        # 誤って登録されたパス（フォルダ名だけなど）を修復
        repair_paths_btn = QPushButton("誤ったパスを修復")
        repair_paths_btn.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_BTN_DEFAULT))
        repair_paths_btn.clicked.connect(self._on_repair_paths)
        general_layout.addWidget(repair_paths_btn)

        general_layout.addStretch()
        tabs.addTab(general, "一般")

        # ── タブ2: ショートカット（HotKey形式・検知専用）──
        shortcut_widget = QWidget()
        shortcut_layout = QVBoxLayout(shortcut_widget)
        hint = QLabel("「検知」を押してから割り当てたいキーを押してください。直接入力はできません。×でクリア。")
        hint.setWordWrap(True)
        hint.setStyleSheet(SETTINGS_SHORTCUT_HINT_STYLE)
        shortcut_layout.addWidget(hint)
        form = QFormLayout()
        self._shortcut_displays = {}
        self._active_shortcut_id = None
        self._shortcut_capture_display = None
        self._shortcut_capture_btn = None
        self._shortcut_capture_row = None
        self._shortcut_capture_original_value = ""
        self._shortcut_normal_style = SETTINGS_SHORTCUT_DISPLAY_STYLE_NORMAL
        self._shortcut_capture_style = SETTINGS_SHORTCUT_DISPLAY_STYLE_CAPTURE
        self._shortcut_confirmed_style = SETTINGS_SHORTCUT_DISPLAY_STYLE_CONFIRMED
        for key, label in (
            ("file_open", "開く"),
            ("file_recent", "最近開いたブック"),
            ("file_close_all", "すべて閉じる"),
            ("file_open_library", "ライブラリを開く"),
            ("file_copy", "コピー"),
            ("file_paste", "貼り付け"),
            ("file_print", "印刷"),
            ("file_rescan", "ライブラリの再スキャン"),
            ("file_quit", "終了"),
        ):
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
                lambda checked=False, k=key, d=key_display, b=btn_capture, r=row_w: self._start_shortcut_capture(k, d, b, r)
            )
            btn_clear.clicked.connect(lambda checked=False, k=key: self._clear_shortcut(k))
        shortcut_layout.addLayout(form)
        shortcut_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(shortcut_widget)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs.addTab(scroll, "ショートカット")
        tabs.addTab(self._build_card_display_tab(), "カード表示")
        tabs.addTab(self._build_backup_tab(), "バックアップ")

        layout.addWidget(tabs)

        # 保存 / キャンセル（プロパティ系ダイアログと同じ BTN_SAVE_STYLE / BTN_CANCEL_STYLE）
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        btn_ok = btn_box.button(QDialogButtonBox.Ok)
        btn_cancel = btn_box.button(QDialogButtonBox.Cancel)
        btn_ok.setText(config.SETTINGS_DIALOG_BTN_SAVE_TEXT)
        btn_cancel.setText(config.SETTINGS_DIALOG_BTN_CANCEL_TEXT)
        btn_ok.setStyleSheet(BTN_SAVE_STYLE)
        btn_cancel.setStyleSheet(BTN_CANCEL_STYLE)
        layout.addWidget(btn_box)
        self._shortcut_ok_button = btn_ok

    def _build_card_display_tab(self) -> QWidget:
        import db
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel,
            QCheckBox, QComboBox, QFrame, QSizePolicy
        )
        from PySide6.QtGui import (
            QPainter, QColor, QBrush, QPen, QFont, QFontMetrics, QLinearGradient
        )
        from PySide6.QtCore import Qt, QRect, QSize

        CARD_W, CARD_H = config.THUMB_WIDTH_BASE, config.THUMB_HEIGHT_BASE
        THUMB_H = int(CARD_H * 0.80)
        TEXT_H = CARD_H - THUMB_H

        class _CardPreview(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setFixedSize(
                    CARD_W + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
                    CARD_H + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
                )
                self.show_meta       = True
                self.show_pages      = True
                self.show_star       = True
                self.show_store_icon = True
                self.sub_info        = "circle"
                self.sub_text    = "サークル名サンプル"

            def sizeHint(self):
                return QSize(
                    CARD_W + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
                    CARD_H + config.SETTINGS_CARD_PREVIEW_OUTER_PAD * 2,
                )

            def paintEvent(self, event):
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

                cx, cy = config.SETTINGS_CARD_PREVIEW_OUTER_PAD, config.SETTINGS_CARD_PREVIEW_OUTER_PAD

                # カード背景
                p.setBrush(QBrush(QColor(COLOR_BG_WIDGET)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRect(cx, cy, CARD_W, CARD_H), config.BORDER_RADIUS, config.BORDER_RADIUS)

                # サムネプレースホルダー
                p.setBrush(QBrush(QColor(SETTINGS_CARD_PREVIEW_THUMB_BG)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(QRect(cx, cy, CARD_W, THUMB_H))

                # サムネ下グラデーション
                grad = QLinearGradient(
                    0,
                    cy + THUMB_H - config.CARD_GRADIENT_HEIGHT,
                    0,
                    cy + THUMB_H,
                )
                grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                grad.setColorAt(1.0, QColor(COLOR_BG_WIDGET))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(QRect(cx, cy + THUMB_H - config.CARD_GRADIENT_HEIGHT, CARD_W, config.CARD_GRADIENT_HEIGHT))

                # 左上メタバッジ（✓）
                if self.show_meta:
                    p.setBrush(QBrush(QColor(SETTINGS_CARD_PREVIEW_META_OK_BG)))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(
                        QRect(
                            cx + config.CARD_INSET,
                            cy + config.CARD_INSET,
                            config.CARD_META_BADGE_SIZE,
                            config.CARD_META_BADGE_SIZE,
                        ),
                        config.CARD_META_BADGE_RADIUS,
                        config.CARD_META_BADGE_RADIUS,
                    )
                    p.setPen(QPen(Qt.GlobalColor.white))
                    f = QFont(config.FONT_FAMILY)
                    f.setPointSize(config.FONT_SIZE_CARD_BADGE)
                    f.setBold(True)
                    p.setFont(f)
                    p.drawText(
                        QRect(
                            cx + config.CARD_INSET,
                            cy + config.CARD_INSET,
                            config.CARD_META_BADGE_SIZE,
                            config.CARD_META_BADGE_SIZE,
                        ),
                        Qt.AlignmentFlag.AlignCenter,
                        "✓",
                    )

                # 右上ページ数バッジ
                if self.show_pages:
                    f = QFont(config.FONT_FAMILY)
                    f.setPointSize(config.FONT_SIZE_CARD_BADGE)
                    p.setFont(f)
                    fm = QFontMetrics(f)
                    badge_text = "148P"
                    bw = fm.horizontalAdvance(badge_text) + (config.PAGE_BADGE_PAD * 2)
                    p.setBrush(QBrush(QColor(0, 0, 0, CARD_BADGE_OVERLAY_ALPHA)))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(
                        QRect(
                            cx + CARD_W - bw - config.CARD_INSET,
                            cy + config.CARD_INSET,
                            bw,
                            config.BADGE_HEIGHT,
                        ),
                        config.CARD_BADGE_RADIUS,
                        config.CARD_BADGE_RADIUS,
                    )
                    p.setPen(QPen(Qt.GlobalColor.white))
                    p.drawText(
                        QRect(
                            cx + CARD_W - bw - config.CARD_INSET,
                            cy + config.CARD_INSET,
                            bw,
                            config.BADGE_HEIGHT,
                        ),
                        Qt.AlignmentFlag.AlignCenter,
                        badge_text,
                    )

                # 左下星レーティング
                if self.show_star:
                    f = QFont(config.FONT_FAMILY)
                    f.setPointSize(config.FONT_SIZE_CARD_BADGE)
                    p.setFont(f)
                    fm = QFontMetrics(f)
                    stars = "★★★"
                    sw = fm.horizontalAdvance(stars) + (config.PAGE_BADGE_PAD * 2)
                    p.setBrush(QBrush(QColor(0, 0, 0, CARD_RATING_BG_ALPHA)))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(
                        QRect(
                            cx + config.CARD_INSET,
                            cy + THUMB_H - config.CARD_GRADIENT_HEIGHT,
                            sw,
                            config.BADGE_HEIGHT,
                        ),
                        config.CARD_BADGE_RADIUS,
                        config.CARD_BADGE_RADIUS,
                    )
                    p.setPen(QPen(QColor(COLOR_STAR_ACTIVE)))
                    p.drawText(
                        QRect(
                            cx + config.CARD_INSET,
                            cy + THUMB_H - config.CARD_GRADIENT_HEIGHT,
                            sw,
                            config.BADGE_HEIGHT,
                        ),
                        Qt.AlignmentFlag.AlignCenter,
                        stars,
                    )

                # テキスト行
                line_h = (TEXT_H - 2) // 2

                # タイトル（1行目）
                f = QFont(config.FONT_FAMILY)
                f.setPointSize(config.FONT_SIZE_CARD_TITLE)
                p.setFont(f)
                fm = QFontMetrics(f)
                title = config.APP_TITLE
                elided = fm.elidedText(title, Qt.TextElideMode.ElideRight, CARD_W - 8)
                p.setPen(QPen(QColor(COLOR_CARD_TITLE_FG)))
                p.drawText(QRect(cx + 4, cy + THUMB_H + 2, CARD_W - 8, line_h),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

                # サブ情報（2行目）
                if self.sub_info != "none" and self.sub_text:
                    f2 = QFont(config.FONT_FAMILY)
                    f2.setPointSize(config.FONT_SIZE_CARD_BADGE)
                    p.setFont(f2)
                    fm2 = QFontMetrics(f2)
                    elided_sub = fm2.elidedText(self.sub_text, Qt.TextElideMode.ElideRight, CARD_W - 8)
                    p.setPen(QPen(QColor(COLOR_CARD_SUB_FG)))
                    p.drawText(QRect(cx + 4, cy + THUMB_H + 2 + line_h, CARD_W - 8, line_h),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_sub)

                p.end()

        # ── メインレイアウト（左: 設定 / 右: プレビュー）──────────
        page = QWidget()
        root = QHBoxLayout(page)
        root.setContentsMargins(*config.SETTINGS_DIALOG_MARGINS)
        root.setSpacing(config.SETTINGS_CARD_TAB_ROOT_SPACING)

        # 左カラム（設定項目）
        left = QVBoxLayout()
        left.setSpacing(config.SETTINGS_CARD_TAB_LEFT_SPACING)

        section_badge = QLabel("バッジ・レーティング")
        section_badge.setStyleSheet(
            f"font-weight: bold; color: {COLOR_CARD_SUB_FG}; font-size: {config.SETTINGS_SECTION_LABEL_FONT_SIZE_PX}px;"
        )
        left.addWidget(section_badge)

        self._chk_meta_badge  = QCheckBox("メタデータバッジ（✓）を表示")
        self._chk_pages_badge = QCheckBox("ページ数バッジを表示")
        self._chk_star        = QCheckBox("星レーティング（★）を表示")
        self._chk_store_icon  = QCheckBox("ストアアイコンを表示（DLSite / DMM）")
        for chk in (self._chk_meta_badge, self._chk_pages_badge, self._chk_star, self._chk_store_icon):
            left.addWidget(chk)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        left.addWidget(sep)

        section_sub = QLabel("カード下部のサブ情報")
        section_sub.setStyleSheet(
            f"font-weight: bold; color: {COLOR_CARD_SUB_FG}; font-size: {config.SETTINGS_SECTION_LABEL_FONT_SIZE_PX}px;"
        )
        left.addWidget(section_sub)

        sub_row = QHBoxLayout()
        sub_label = QLabel("表示する情報：")
        self._combo_sub_info = QComboBox()
        SUB_INFO_OPTIONS = [
            ("none",      "なし"),
            ("circle",    "サークル"),
            ("author",    "作者"),
            ("series",    "シリーズ"),
            ("character", "キャラクター"),
            ("tag",       "タグ"),
        ]
        SUB_SAMPLE_TEXT = {
            "none":      "",
            "circle":    "サークル名サンプル",
            "author":    "作者名サンプル",
            "series":    "シリーズ名サンプル",
            "character": "キャラクター名",
            "tag":       "タグA・タグB・タグC…",
        }
        for key, label in SUB_INFO_OPTIONS:
            self._combo_sub_info.addItem(label, key)
        sub_row.addWidget(sub_label)
        sub_row.addWidget(self._combo_sub_info)
        sub_row.addStretch()
        left.addLayout(sub_row)
        left.addStretch()

        # 右カラム（プレビュー）
        right = QVBoxLayout()
        right.setSpacing(config.SETTINGS_CARD_TAB_RIGHT_SPACING)
        preview_label = QLabel("プレビュー")
        preview_label.setStyleSheet(
            f"color: {COLOR_CARD_SUB_FG}; font-size: {config.SETTINGS_SECTION_LABEL_FONT_SIZE_PX}px;"
        )
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        preview = _CardPreview()
        right.addStretch()
        right.addWidget(preview_label, 0, Qt.AlignmentFlag.AlignHCenter)
        right.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)
        right.addStretch()

        root.addLayout(left, 1)
        root.addLayout(right, 0)

        # ── DBから現在値を読み込んで反映 ──────────────────────────
        def _b(key, default="1"):
            v = db.get_setting(key)
            return v != "0" if v is not None else (default == "1")

        self._chk_meta_badge.setChecked(_b(config.CARD_SETTING_META_BADGE))
        self._chk_pages_badge.setChecked(_b(config.CARD_SETTING_PAGES_BADGE))
        self._chk_star.setChecked(_b(config.CARD_SETTING_STAR))
        self._chk_store_icon.setChecked(_b(config.CARD_SETTING_STORE_ICON))

        saved_sub = db.get_setting(config.CARD_SETTING_SUB_INFO) or config.CARD_SETTING_SUB_INFO_DEFAULT
        for i in range(self._combo_sub_info.count()):
            if self._combo_sub_info.itemData(i) == saved_sub:
                self._combo_sub_info.setCurrentIndex(i)
                break

        # ── プレビューをDBの現在値で初期化 ────────────────────────
        preview.show_meta       = self._chk_meta_badge.isChecked()
        preview.show_pages      = self._chk_pages_badge.isChecked()
        preview.show_star       = self._chk_star.isChecked()
        preview.show_store_icon = self._chk_store_icon.isChecked()
        preview.sub_info   = self._combo_sub_info.currentData()
        preview.sub_text   = SUB_SAMPLE_TEXT.get(preview.sub_info, "")

        # ── トグル変更 → リアルタイムプレビュー更新 ──────────────
        def _update_preview():
            preview.show_meta       = self._chk_meta_badge.isChecked()
            preview.show_pages     = self._chk_pages_badge.isChecked()
            preview.show_star      = self._chk_star.isChecked()
            preview.show_store_icon = self._chk_store_icon.isChecked()
            key = self._combo_sub_info.currentData()
            preview.sub_info = key
            preview.sub_text = SUB_SAMPLE_TEXT.get(key, "")
            preview.update()

        self._chk_meta_badge.stateChanged.connect(_update_preview)
        self._chk_pages_badge.stateChanged.connect(_update_preview)
        self._chk_star.stateChanged.connect(_update_preview)
        self._chk_store_icon.stateChanged.connect(_update_preview)
        self._combo_sub_info.currentIndexChanged.connect(_update_preview)

        return page

    def _build_backup_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(config.SETTINGS_DIALOG_SPACING)

        row = QHBoxLayout()
        lbl = QLabel("バックアップ保持件数")
        lbl.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        row.addWidget(lbl)

        self._backup_count_spin = QSpinBox()
        self._backup_count_spin.setRange(config.SETTINGS_BACKUP_COUNT_MIN, config.SETTINGS_BACKUP_COUNT_MAX)
        try:
            val = int(db.get_setting("backup_max_count") or config.SETTINGS_BACKUP_COUNT_DEFAULT)
        except (TypeError, ValueError):
            val = config.SETTINGS_BACKUP_COUNT_DEFAULT
        self._backup_count_spin.setValue(val)
        self._backup_count_spin.setFixedWidth(config.SETTINGS_BACKUP_SPIN_WIDTH)
        row.addWidget(self._backup_count_spin)
        row.addStretch()
        layout.addLayout(row)

        # 自動アップデート
        update_row = QHBoxLayout()
        self._disable_update_check = QCheckBox("自動アップデートを無効にする")
        self._disable_update_check.setFont(QFont(config.FONT_FAMILY, config.FONT_SIZE_DIALOG_LABEL))
        self._disable_update_check.setChecked(db.get_setting("disable_auto_update") == "1")
        update_row.addWidget(self._disable_update_check)
        update_row.addStretch()
        layout.addLayout(update_row)

        layout.addStretch()
        return widget

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

        # 1. キーイベントを最優先で判定（空振り防止は grabKeyboard に依存）
        if event.type() == QEvent.Type.KeyPress:
            ev = event
            key = ev.key()
            mods = ev.modifiers()
            # 修飾キー単体: 消費して次のキー（修飾＋キー）を待つ
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

        # 2. マウス等は後回し: 検知行外クリックでキャンセル
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

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "ビュアーを選択", "", VIEWER_FILE_FILTER
        )
        if path:
            self._viewer_edit.setText(path)

    def _browse_dmm(self):
        start = _find_viewer_dir_on_any_drive([
            os.path.join("Program Files", "DMM", "DMMbookviewer"),
        ])
        path, _ = QFileDialog.getOpenFileName(
            self, "DMMビュアーを選択", start, VIEWER_FILE_FILTER,
        )
        if path:
            self._dmm_viewer_edit.setText(path)

    def _browse_dlsite(self):
        start = _find_viewer_dir_on_any_drive([
            os.path.join("Program Files (x86)", "DLsiteViewer"),
            os.path.join("Program Files", "DLsiteViewer"),
        ])
        path, _ = QFileDialog.getOpenFileName(
            self, "DLSiteビュアーを選択", start, VIEWER_FILE_FILTER,
        )
        if path:
            self._dlsite_viewer_edit.setText(path)

    def _load(self):
        direction = db.get_setting(config.VIEWER_DIRECTION_SETTING_KEY) or config.VIEWER_DIRECTION_DEFAULT
        idx = self._direction_combo.findData(direction)
        if idx >= 0:
            self._direction_combo.setCurrentIndex(idx)
        self._viewer_edit.setText(db.get_setting("external_viewer") or "")
        self._dmm_viewer_edit.setText(db.get_setting("dmm_viewer") or "")
        self._dlsite_viewer_edit.setText(db.get_setting("dlsite_viewer") or "")
        for key, disp in self._shortcut_displays.items():
            val = db.get_setting(f"shortcut_{key}")
            if val is None:
                val = config.DEFAULT_SHORTCUTS.get(key, "")
            disp.setText((val or "").strip())

    def _is_valid_viewer_path(self, path: str) -> bool:
        """パスが空、または実在するファイル（.lnk の場合はリンク先が実在）なら True。"""
        p = (path or "").strip()
        if not p:
            return True
        if not os.path.isfile(p):
            return False
        resolved = resolve_shortcut(p)
        if not resolved:
            return False
        if os.path.splitext(p)[1].lower() == ".lnk":
            # ショートカットはリンク先が別パスで実在する場合のみ有効
            return resolved != p and os.path.isfile(resolved)
        return os.path.isfile(resolved)

    def _save(self):
        external = self._viewer_edit.text().strip()
        dmm = self._dmm_viewer_edit.text().strip()
        dlsite = self._dlsite_viewer_edit.text().strip()

        invalid = []
        if external and not self._is_valid_viewer_path(external):
            invalid.append("外部ビュアー")
        if dmm and not is_valid_store_viewer_path(dmm, for_dmm=True):
            invalid.append("DMMビュアー（DMMBooks.exe / DMMbookviewer.exe を指定してください）")
        if dlsite and not is_valid_store_viewer_path(dlsite, for_dmm=False):
            invalid.append("DLSiteビュアー（DLSitePlay.exe / DLsiteViewer.exe を指定してください）")

        if invalid:
            msg = QMessageBox(self)
            msg.setWindowTitle(config.APP_TITLE)
            msg.setIcon(QMessageBox.Warning)
            msg.setText("次の項目を確認してください。")
            msg.setInformativeText(
                "・外部ビュアー: パスが存在するか、ショートカットのリンク先が有効か確認してください。\n"
                "・DMMビュアー: DMMBooks.exe または DMMbookviewer.exe を指定してください。\n"
                "・DLSiteビュアー: DLSitePlay.exe または DLsiteViewer.exe を指定してください。\n\n"
                "該当: " + " / ".join(invalid)
            )
            msg.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Cancel)
            msg.button(QMessageBox.Save).setText("このまま保存する")
            msg.button(QMessageBox.Cancel).setText("キャンセル")
            if msg.exec() != QMessageBox.Save:
                return

        db.set_setting("external_viewer", external)
        db.set_setting("dmm_viewer", dmm)
        db.set_setting("dlsite_viewer", dlsite)
        db.set_setting(config.VIEWER_DIRECTION_SETTING_KEY, self._direction_combo.currentData())
        for key, disp in self._shortcut_displays.items():
            val = (disp.text() or "").strip()
            db.set_setting(f"shortcut_{key}", val if val else "")

        # カード表示設定の保存
        db.set_setting(config.CARD_SETTING_META_BADGE,  "1" if self._chk_meta_badge.isChecked()  else "0")
        db.set_setting(config.CARD_SETTING_PAGES_BADGE, "1" if self._chk_pages_badge.isChecked() else "0")
        db.set_setting(config.CARD_SETTING_STAR,        "1" if self._chk_star.isChecked()         else "0")
        db.set_setting(config.CARD_SETTING_STORE_ICON,  "1" if self._chk_store_icon.isChecked()  else "0")
        db.set_setting(config.CARD_SETTING_SUB_INFO,    self._combo_sub_info.currentData())
        db.set_setting("backup_max_count", str(self._backup_count_spin.value()))
        db.set_setting("disable_auto_update", "1" if self._disable_update_check.isChecked() else "0")

        self.accept()

    def _apply_font(self, family: str):
        """フォントファミリーを即時適用して保存"""
        db.set_setting("font_family", family)
        raw_size = db.get_setting("font_size")
        try:
            pt = int(raw_size) if raw_size is not None else config.FONT_SIZE_DEFAULT
        except (TypeError, ValueError):
            pt = config.FONT_SIZE_DEFAULT
        if pt <= 0:
            pt = config.FONT_SIZE_DEFAULT
        font = QFont(family, pt)
        app = QApplication.instance()
        if app is not None:
            app.setFont(font)
            for widget in app.allWidgets():
                widget.setFont(font)
                widget.update()

    def _on_bulk_rename(self):
        """[サークル名]作品名でフォルダ・ファイルを一括リネームし、一覧を更新する。"""
        library_folder = db.get_setting("library_folder") or ""
        if not library_folder or not os.path.isdir(library_folder):
            QMessageBox.warning(
                self,
                "一括リネーム",
                "先にライブラリフォルダを設定してください。",
            )
            return
        total = len(db.get_all_books())
        if total == 0:
            QMessageBox.information(self, "一括リネーム", "登録されている本がありません。")
            return

        progress = QProgressDialog("リネーム中...", "キャンセル", 0, total, self)
        progress.setWindowTitle(config.APP_TITLE)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_progress(current, total_count, path):
            progress.setMaximum(total_count)
            progress.setValue(current)
            progress.setLabelText(os.path.basename(path) or path)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise InterruptedError("canceled")

        try:
            renamed, err, failed = db.bulk_rename_to_current_format(library_folder, on_progress=on_progress)
        except InterruptedError:
            progress.close()
            return
        progress.close()

        if err:
            QMessageBox.critical(self, "一括リネーム エラー", err)
            return

        # 結果メッセージ
        if failed:
            summary = f"リネーム成功: {renamed} 件\nスキップ（失敗）: {len(failed)} 件"
            detail = "\n\n".join(
                f"[{i + 1}] {os.path.basename(path)}\n  → {new_name}\n  {msg}"
                for i, (path, new_name, msg) in enumerate(failed)
            )
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle(config.APP_TITLE)
            msgbox.setIcon(QMessageBox.Warning)
            msgbox.setText(summary)
            msgbox.setInformativeText("失敗した項目はスキップしました。詳細は「詳細表示」を押して確認してください。")
            msgbox.setDetailedText(detail)
            msgbox.setStandardButtons(QMessageBox.Ok)
            msgbox.exec()
        else:
            QMessageBox.information(
                self,
                "一括リネーム",
                f"{renamed} 件のフォルダ・ファイルを [サークル名]作品名 に合わせてリネームしました。",
            )

        # 親がメインウィンドウなら一覧を再読み込み
        parent = self.parent()
        if parent is not None and hasattr(parent, "_load_library"):
            parent._load_library()

    def _on_repair_paths(self):
        """パスがフォルダ名だけなど誤って登録されているブックを、ライブラリ配下の実在パスに修復する。"""
        library_folder = db.get_setting("library_folder") or ""
        if not library_folder or not os.path.isdir(library_folder):
            QMessageBox.warning(
                self,
                "パス修復",
                "先にライブラリフォルダを設定してください。",
            )
            return
        total = len(db.get_all_books())
        if total == 0:
            QMessageBox.information(self, "パス修復", "登録されている本がありません。")
            return

        progress = QProgressDialog("パスを確認中...", None, 0, total, self)
        progress.setWindowTitle(config.APP_TITLE)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_progress(current, total_count, path):
            progress.setMaximum(total_count)
            progress.setValue(current)
            progress.setLabelText(os.path.basename(path) or path or "(不明)")
            QApplication.processEvents()

        try:
            count, err, repaired = db.repair_wrong_paths(library_folder, on_progress=on_progress)
        finally:
            progress.close()

        if err:
            QMessageBox.critical(self, "パス修復 エラー", err)
            return
        if count == 0:
            QMessageBox.information(self, "パス修復", "修復対象のブックはありませんでした。")
            return
        detail = "\n".join(f"  {old!r} → {new!r}" for old, new in repaired[:20])
        if len(repaired) > 20:
            detail += f"\n  ... 他 {len(repaired) - 20} 件"
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle(config.APP_TITLE)
        msgbox.setIcon(QMessageBox.Information)
        msgbox.setText(f"{count} 件のブックのパスを修復しました。")
        msgbox.setDetailedText(detail)
        msgbox.setStandardButtons(QMessageBox.Ok)
        msgbox.exec()

        parent = self.parent()
        if parent is not None and hasattr(parent, "_refresh_books_from_db"):
            parent._refresh_books_from_db()
        elif parent is not None and hasattr(parent, "_load_library"):
            parent._load_library()

