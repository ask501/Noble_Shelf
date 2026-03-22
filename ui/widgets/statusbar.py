"""
statusbar.py - ステータスバーの構築
"""
from PySide6.QtWidgets import QLabel, QSlider, QWidget, QStatusBar
from PySide6.QtCore import Qt
import config
from version import VERSION


def setup_statusbar(window, sb: QStatusBar) -> QSlider:
    """
    ステータスバーを構築してスライダーを返す。
    window: MainWindow
    sb: QStatusBar
    戻り値: カードサイズスライダー
    """
    # 右端: カードサイズ スペース ライセンス
    size_label = QLabel("カードサイズ:")
    sb.addPermanentWidget(size_label)

    slider = QSlider(Qt.Horizontal)
    slider.setMinimum(config.SLIDER_MIN_WIDTH)
    slider.setMaximum(config.SLIDER_MAX_WIDTH)
    slider.setValue(config.DEFAULT_CARD_WIDTH)
    slider.setFixedWidth(config.STATUSBAR_SLIDER_WIDTH)
    slider.setToolTip("カードサイズ (Ctrl+ホイールでも変更可)")
    sb.addPermanentWidget(slider)

    license_label = QLabel(
        f"Noble Shelf v{VERSION} © 2026 ask501 – MIT License "
    )
    license_label.setStyleSheet(
        f"margin-left: {config.STATUSBAR_LICENSE_MARGIN_X}px; margin-right: {config.STATUSBAR_LICENSE_MARGIN_X}px;"
    )
    sb.addPermanentWidget(license_label)

    return slider

