"""
launcher.py - Noble Shelf ランチャー

起動時にクリーンアップ・アップデート確認を行ってから本体を起動する。
"""
import sys
from updater import cleanup_on_startup, check_and_prompt_update
from main import main


if __name__ == "__main__":
    # 前回アップデートの残骸をクリーンアップ
    cleanup_on_startup()

    # アップデート確認（設定で無効化可能）
    # QApplicationが必要なのでmain()内で呼ぶ
    main(on_startup=check_and_prompt_update)
