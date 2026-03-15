"""
plugin_loader.py - メタデータ取得プラグインの自動検出・ロード

plugins/get_api/ フォルダ直下の各サブフォルダを1プラグインとして読み込む。
（get_api が無い場合は plugins/ 直下のサブフォルダをスキャン）

各プラグインは __init__.py で契約を export する（直で並べるか get_api() で返す）。

契約: PLUGIN_NAME, PLUGIN_SOURCE_KEY, search_sync, get_metadata_sync [, can_handle]

API: get_plugins() = 有効なプラグインのみ（検索・メタ取得はここだけ使う＝スイッチ一箇所）。
     get_all_plugins() = 全件（メニュー「プラグイン」のON/OFF表示用）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any

try:
    import config
    _APP_BASE = config.APP_BASE
    _PLUGINS_DIR = os.path.join(_APP_BASE, "plugins")
except Exception:
    _APP_BASE = os.path.dirname(os.path.abspath(__file__))
    _PLUGINS_DIR = os.path.join(_APP_BASE, "plugins")


def _ensure_plugin_import_path():
    """exe 化時、プラグインから本体モジュール（dlsite_api 等）を import できるよう sys.path を通す"""
    base = getattr(sys, "_MEIPASS", _APP_BASE)  # PyInstaller なら _MEIPASS に本体が入る
    if base and base not in sys.path:
        sys.path.insert(0, base)
    if _APP_BASE and _APP_BASE not in sys.path:
        sys.path.insert(0, _APP_BASE)


# プラグインをスキャンするディレクトリ: plugins/get_api/ があればその直下、なければ plugins/ 直下
_GET_API_DIR = os.path.join(_PLUGINS_DIR, "get_api")
_PLUGINS_SCAN_DIR = _GET_API_DIR if os.path.isdir(_GET_API_DIR) else _PLUGINS_DIR

_REQUIRED = ("PLUGIN_NAME", "PLUGIN_SOURCE_KEY", "search_sync", "get_metadata_sync")


def _is_plugin_dir(path: str) -> bool:
    """plugins 直下のサブディレクトリで、__init__.py があるものをプラグインとする"""
    if not os.path.isdir(path):
        return False
    name = os.path.basename(path)
    if name.startswith("_"):
        return False
    init = os.path.join(path, "__init__.py")
    return os.path.isfile(init)


def _load_plugin_module(folder_name: str):
    """_PLUGINS_SCAN_DIR/<folder_name>/__init__.py を import してモジュールを返す。失敗時は None"""
    _ensure_plugin_import_path()
    try:
        init_path = os.path.join(_PLUGINS_SCAN_DIR, folder_name, "__init__.py")
        if not os.path.isfile(init_path):
            return None
        # モジュール名はスキャン元に応じて一意に（plugins.get_api.dlsite_sites など）
        if _PLUGINS_SCAN_DIR == _GET_API_DIR:
            spec_name = f"plugins.get_api.{folder_name}"
        else:
            spec_name = f"plugins.{folder_name}"
        spec = importlib.util.spec_from_file_location(
            spec_name,
            init_path,
            submodule_search_locations=[os.path.dirname(init_path)],
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        for part in (["plugins"] + (["plugins.get_api"] if _PLUGINS_SCAN_DIR == _GET_API_DIR else [])):
            if part not in sys.modules:
                import types
                sys.modules[part] = types.ModuleType(part)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _check_contract(obj: Any) -> bool:
    """契約を満たすか（モジュールまたは get_api() の返り値）"""
    for attr in _REQUIRED:
        if not hasattr(obj, attr):
            return False
    name = getattr(obj, "PLUGIN_NAME", None)
    if not name or not isinstance(name, str):
        return False
    key = getattr(obj, "PLUGIN_SOURCE_KEY", None)
    if not key or not isinstance(key, str):
        return False
    return True


def _resolve_plugin(mod: Any) -> Any | None:
    """モジュールからプラグインオブジェクトを取得。get_api() があればその返り値、なければ mod 自身"""
    if hasattr(mod, "get_api") and callable(mod.get_api):
        try:
            api = mod.get_api()
            if api is not None and _check_contract(api):
                return api
        except Exception:
            pass
        return None
    if _check_contract(mod):
        return mod
    return None


def get_all_plugins() -> list[Any]:
    """
    読み込み済みの全プラグインを返す（有効/無効は問わない）。
    メニュー「プラグイン」の一覧表示など、ON/OFF の切り替え用。
    """
    if not os.path.isdir(_PLUGINS_SCAN_DIR):
        return []
    result = []
    for name in sorted(os.listdir(_PLUGINS_SCAN_DIR)):
        path = os.path.join(_PLUGINS_SCAN_DIR, name)
        if not _is_plugin_dir(path):
            continue
        mod = _load_plugin_module(name)
        if mod is None:
            continue
        plugin = _resolve_plugin(mod)
        if plugin is not None:
            result.append(plugin)
    return result


# DB の設定キー: plugin_enabled_<PLUGIN_SOURCE_KEY> = "1" / "0"（未設定は有効）
def _plugin_enabled_key(source_key: str) -> str:
    return f"plugin_enabled_{source_key}"


def is_plugin_enabled(source_key: str) -> bool:
    """プラグインが有効か。未設定は True。明示的に "0" なら False。例外時は False（切り離しを優先）。"""
    try:
        import db
        val = db.get_setting(_plugin_enabled_key(source_key))
        if val is None:
            return True  # 未設定＝従来どおり有効
        return (str(val).strip() or "").lower() != "0"
    except Exception:
        return False


def set_plugin_enabled(source_key: str, enabled: bool) -> None:
    """プラグインの有効/無効を保存する。"""
    try:
        import db
        db.set_setting(_plugin_enabled_key(source_key), "1" if enabled else "0")
    except Exception:
        pass


def get_plugins() -> list[Any]:
    """
    有効なプラグインのみ返す。検索・メタ取得はすべてここを通す（スイッチ一箇所）。
    呼び出し側は get_plugins() だけ使えばよく、OFF のプラグインは含まれない。
    """
    return [p for p in get_all_plugins() if is_plugin_enabled(getattr(p, "PLUGIN_SOURCE_KEY", ""))]


def has_metadata_plugins() -> bool:
    """読み込み済みプラグインが1つでもあるか（メニュー「プラグイン」の表示用。有効/無効は問わない）"""
    return len(get_all_plugins()) > 0


def has_enabled_plugins() -> bool:
    """有効なプラグインが1つでもあるか。コンテキストメニュー・プロパティの取得/メタ検索・サイドバー「メタデータ」の表示に使う。"""
    return len(get_plugins()) > 0


def get_plugin_property_widgets(context: Any) -> list[Any]:
    """
    有効なプラグインから「プロパティ用ボタン」を集める。
    各プラグインが get_property_buttons(context) を実装していれば呼び出し、返されたウィジェットのリストを平坦に返す。
    メインUIはコンテナにこれらを並べるだけ。プラグインが「ここに置く」と宣言したボタンが並ぶ。
    """
    out: list[Any] = []
    for plugin in get_plugins():
        get_buttons = getattr(plugin, "get_property_buttons", None)
        if not callable(get_buttons):
            continue
        try:
            widgets = get_buttons(context)
            if widgets:
                out.extend(widgets if isinstance(widgets, (list, tuple)) else [widgets])
        except Exception:
            pass
    return out
