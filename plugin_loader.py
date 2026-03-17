"""
plugin_loader.py - メタデータ取得プラグインの自動検出・ロード

PLUGINS_DIR 直下の各サブフォルダを1プラグインとして読み込む。

プラグインの作り方:
  PLUGINS_DIR/
    my_plugin/
      __init__.py
      dependency.py

契約: PLUGIN_NAME, PLUGIN_SOURCE_KEY, search_sync, get_metadata_sync [, can_handle]

API:
  get_plugins()     = 有効なプラグインのみ
  get_all_plugins() = 全件（メニューのON/OFF表示用）
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from typing import Any

from paths import PLUGINS_DIR as _PLUGINS_DIR

_REQUIRED = ("PLUGIN_NAME", "PLUGIN_SOURCE_KEY", "search_sync", "get_metadata_sync")


def _is_plugin_dir(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    if os.path.basename(path).startswith("_"):
        return False
    return os.path.isfile(os.path.join(path, "__init__.py"))


def _load_plugin_module(plugin_dir: str):
    import logging
    log_path = os.path.join(os.environ.get("APPDATA", ""), "NobleShelf", "debug.log")
    logging.basicConfig(filename=log_path, level=logging.DEBUG, force=True)
    logging.debug(f"_load_plugin_module: {plugin_dir}, sys.path: {sys.path}")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    try:
        init_path = os.path.join(plugin_dir, "__init__.py")
        folder_name = os.path.basename(plugin_dir)
        spec_name = f"noble_shelf_plugins.{folder_name}"
        spec = importlib.util.spec_from_file_location(
            spec_name,
            init_path,
            submodule_search_locations=[plugin_dir],
        )
        if spec is None or spec.loader is None:
            return None
        if "noble_shelf_plugins" not in sys.modules:
            sys.modules["noble_shelf_plugins"] = types.ModuleType("noble_shelf_plugins")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec_name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _check_contract(obj: Any) -> bool:
    for attr in _REQUIRED:
        if not hasattr(obj, attr):
            return False
    if not isinstance(getattr(obj, "PLUGIN_NAME", None), str):
        return False
    if not isinstance(getattr(obj, "PLUGIN_SOURCE_KEY", None), str):
        return False
    return True


def _resolve_plugin(mod: Any) -> Any | None:
    if hasattr(mod, "get_plugin") and callable(mod.get_plugin):
        try:
            api = mod.get_plugin()
            if api is not None and _check_contract(api):
                return api
        except Exception as e:
            import logging
            import traceback
            logging.debug(f"get_plugin error: {traceback.format_exc()}")
        return None
    if _check_contract(mod):
        return mod
    return None


def get_all_plugins() -> list[Any]:
    """全プラグインを返す（有効/無効は問わない）。"""
    if not os.path.isdir(_PLUGINS_DIR):
        return []
    result = []
    for name in sorted(os.listdir(_PLUGINS_DIR)):
        plugin_dir = os.path.join(_PLUGINS_DIR, name)
        if not _is_plugin_dir(plugin_dir):
            continue
        mod = _load_plugin_module(plugin_dir)
        if mod is None:
            continue
        plugin = _resolve_plugin(mod)
        if plugin is not None:
            result.append(plugin)
    return result


def _plugin_enabled_key(source_key: str) -> str:
    return f"plugin_enabled_{source_key}"


def is_plugin_enabled(source_key: str) -> bool:
    try:
        import db
        val = db.get_setting(_plugin_enabled_key(source_key))
        if val is None:
            return True
        return str(val).strip().lower() != "0"
    except Exception:
        return False


def set_plugin_enabled(source_key: str, enabled: bool) -> None:
    try:
        import db
        db.set_setting(_plugin_enabled_key(source_key), "1" if enabled else "0")
    except Exception:
        pass


def get_plugins() -> list[Any]:
    """有効なプラグインのみ返す。"""
    return [p for p in get_all_plugins() if is_plugin_enabled(getattr(p, "PLUGIN_SOURCE_KEY", ""))]


def has_metadata_plugins() -> bool:
    return len(get_all_plugins()) > 0


def has_enabled_plugins() -> bool:
    return len(get_plugins()) > 0


def get_plugin_property_widgets(context: Any) -> list[Any]:
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