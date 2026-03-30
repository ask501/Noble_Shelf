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
        "はじめに（この機能は何？）",
        [
            "ブラウザで見ている「作品の紹介ページ」の内容（タイトルや表紙の画像の場所など）を読み取り、"
            "Noble Shelf のライブラリにある作品に反映するための補助です。",
            "※ 勝手に動くわけではありません。あなたがあらかじめ登録した「ブックマーク」を、"
            "作品ページを開いた状態でクリックして実行します（手動操作）。",
            "※ Noble Shelf は起動したままにしてください。アプリを閉じているとブラウザから送れません。",
            "※ 使うブラウザと Noble Shelf は、同じパソコン上である必要があります。",
        ],
        None,
    ),
    (
        "全体の流れ（4 ステップ）",
        [
            "① この画面の「ブックマークレットをコピー」を押し、長い文字（JavaScript）をコピーします。",
            "② ブラウザに「ブックマーク」として貼り付けて保存します（名前は分かりやすいもので OK。例：Noble送信）。",
            "③ あとから、作品の紹介ページを開いた状態で、そのブックマークをクリックします。"
            "成功するとページ上にメッセージが出て、このキュー一覧に項目が増えます。",
            "④ 一覧で項目を選び、必要なら「メタデータを適用」でライブラリに反映します（次のページ以降で説明）。",
        ],
        None,
    ),
    (
        "① ブックマークレットをコピーする",
        [
            "下の図の赤枠の「ブックマークレットをコピー」ボタンをクリックします。",
            "クリップボード（コピーされた場所）に、1 行の長い文字が入ります。そのまま次の「ブラウザ登録」で使います。",
            "コピーできたか不安なときは、メモ帳を開いて Ctrl+V で貼り付け、先頭が「javascript:」で始まっていれば成功です。",
        ],
        paths.BOOKMARKLET_HELP_COPY_SCREENSHOT,
    ),
    (
        "② ブラウザにブックマークとして登録する",
        [
            "Google Chrome または Microsoft Edge を例に説明します（他のブラウザも「お気に入り」や「ブックマーク」に URL を追加すれば同じ考え方です）。",
            "まずブックマークバー（お気に入りバー）を表示します。キーボードで Ctrl+Shift+B を押すと、表示・非表示が切り替わることが多いです。",
            "ブックマークバーの空いている場所で右クリックし、「新しいブックマーク」などを選びます。",
            "名前は自由です（例：Noble Shelf 送信）。「URL」欄に、さきほどコピーした内容を Ctrl+V で貼り付け、「保存」します。",
            "（下の図は ①名前 ②URL に貼り付け ③保存 のイメージです。）",
        ],
        paths.BOOKMARKLET_HELP_BROWSER_SCREENSHOT,
    ),
    (
        "③ 作品ページでブックマークを実行する",
        [
            "Noble Shelf を起動したまま、ブラウザで対象の作品の紹介ページを開きます。",
            "登録したブックマーク（ブックマークレット）をクリックします。",
            "「Noble Shelfに送信しました！」などとページに表示されれば、キューへの追加に成功しています。",
            "表示されない・エラーになるページは、構造が対象外の場合があります。その場合は手入力でプロパティを編集してください。",
        ],
        None,
    ),
    (
        "注意（利用規約・データの行き先）",
        [
            "表示中のページの内容を、ご利用の PC 上だけで読み取る機能です。各サイトの利用規約を確認のうえ、自己責任でご利用ください。",
            "送信先はあなたのパソコンの中だけです（Noble Shelf が待ち受けている「127.0.0.1」という内部アドレス）。"
            "インターネット上の別会社のサーバーに、作品情報をアップロードする仕組みではありません。",
            "セキュリティソフトやファイアウォールが「自分の PC 内の通信」を止めていると動かないことがあります。その場合は Noble Shelf やブラウザを許可リストに入れるなど、設定を確認してください。",
        ],
        None,
    ),
    (
        "一覧のマーク（色つきアイコン）の意味",
        [
            "キュー一覧の左側の記号は、ライブラリの作品と一致したかどうかの目安です。",
            "🟢（緑）… ライブラリの作品と一致し、設定で「自動適用」がオンなら、すでにメタデータを反映済みです。",
            "🟡（黄）… 一致する作品は見つかりましたが、自動適用されず待ち状態です。項目を選び「メタデータを適用」を押すと反映できます。",
            "🔴（赤）… ライブラリ内に同じ作品が見つかりませんでした。フォルダ名や登録の仕方を確認してください。",
        ],
        None,
    ),
    (
        "この画面（キュー）の操作",
        [
            "一覧で項目をクリックすると、下に取り込んだ情報のプレビューが表示されます。",
            "「メタデータを適用」… 選択中の項目の内容を、ライブラリの該当作品に書き込みます（🟡 のときに使います）。",
            "「完全一致時に自動適用」にチェックを入れると、🟢 のように一致したとき自動で適用する動きになります。オフにすると毎回手動になります。",
            "「サムネイルを上書きする」… オンにすると、表紙画像をページから取り込んだ画像で置き換える場合があります（既存の表紙を守りたいときはオフ推奨）。",
            "「🟢 削除」「🟡 削除」などは、その状態の項目だけをキューから消します。「全削除」は一覧を空にします。",
        ],
        None,
    ),
    (
        "うまくいかないとき（よくある原因）",
        [
            "・Noble Shelf を起動していますか？ 完全に終了していると送信できません。",
            "・アプリを更新したあと、古いブックマークのままになっていませんか？ 「ブックマークレットをコピー」から取り直し、ブラウザのブックマーク URL を差し替えてください。",
            "・セキュリティソフトが、ブラウザと Noble Shelf の通信をブロックしていませんか？",
            "・別のパソコンのブラウザからは送れません。Noble Shelf が動いている PC と同じ PC のブラウザで試してください。",
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
