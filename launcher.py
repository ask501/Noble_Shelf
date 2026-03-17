"""
launcher.py - Noble Shelf ランチャー
"""
from __future__ import annotations
from updater import cleanup_on_startup, check_and_prompt_update
from main import main


if __name__ == "__main__":
    cleanup_on_startup()
    main(on_startup=check_and_prompt_update)
