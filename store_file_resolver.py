from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import config
from typing import Literal


@dataclass
class DBRowSummary:
    uuid: str
    path: str
    content_hash: str | None
    mtime: float | None
    file_ext: str
    is_dlst: bool
    rowid: int


@dataclass
class DBIndex:
    row_by_path: dict[str, DBRowSummary]
    rows_by_content_hash: dict[str, list[DBRowSummary]]
    missing_path_set: set[str]
    meta_by_path: dict[str, tuple[float | None, str | None]]


@dataclass
class FileContext:
    abs_path: str
    db_path: str
    content_hash: str | None
    mtime: float | None
    file_ext: str
    is_dlst: bool


@dataclass
class ActionResult:
    status: Literal["created", "updated", "rename", "duplicate", "unchanged", "error"]
    db_path: str
    existing_uuid: str | None = None
    existing_path: str | None = None
    duplicate_row: DBRowSummary | None = None
    error_type: Literal["IO_ERROR", "HASH_ERROR"] | None = None
    error_message: str | None = None


def _norm_ext(ext: str) -> str:
    return (ext or "").strip().lower()


def build_db_index(db_rows: list[dict], library_root: str) -> DBIndex:
    row_by_path: dict[str, DBRowSummary] = {}
    rows_by_content_hash: dict[str, list[DBRowSummary]] = {}
    missing_path_set: set[str] = set()
    meta_by_path: dict[str, tuple[float | None, str | None]] = {}

    for row in db_rows or []:
        try:
            path = str(row.get("path") or "").strip()
            if not path:
                continue
            summary = DBRowSummary(
                uuid=str(row.get("uuid") or ""),
                path=path,
                content_hash=(str(row.get("content_hash")).strip() if row.get("content_hash") else None),
                mtime=float(row["mtime"]) if row.get("mtime") is not None else None,
                file_ext=_norm_ext(str(row.get("file_ext") or os.path.splitext(path)[1])),
                is_dlst=bool(row.get("is_dlst")),
                rowid=int(row.get("rowid") or 0),
            )
            row_by_path[path] = summary
            meta_by_path[path] = (summary.mtime, summary.content_hash)
            if row.get("missing_since_date"):
                missing_path_set.add(path)
            if summary.content_hash:
                rows_by_content_hash.setdefault(summary.content_hash, []).append(summary)
        except Exception as e:
            logging.warning(
                config.LOG_RESOLVER_DB_ROW_SKIP_TEMPLATE,
                row.get("path"),
                e,
            )
            continue

    for key in list(rows_by_content_hash.keys()):
        rows_by_content_hash[key].sort(key=lambda r: r.rowid)

    return DBIndex(
        row_by_path=row_by_path,
        rows_by_content_hash=rows_by_content_hash,
        missing_path_set=missing_path_set,
        meta_by_path=meta_by_path,
    )


def resolve_store_file_action(ctx: FileContext, index: DBIndex) -> ActionResult:
    if not ctx.db_path or not str(ctx.db_path).strip():
        return ActionResult(
            status="error",
            db_path=ctx.db_path,
            error_type="IO_ERROR",
            error_message="db_path is empty",
        )
    if (ctx.content_hash is None or str(ctx.content_hash).strip() == "") and ctx.mtime is None:
        return ActionResult(
            status="error",
            db_path=ctx.db_path,
            error_type="HASH_ERROR",
            error_message="both content_hash and mtime are missing",
        )

    db_path = str(ctx.db_path).strip()
    current = index.row_by_path.get(db_path)

    if current is not None:
        if ctx.content_hash:
            if current.content_hash and current.content_hash == ctx.content_hash:
                return ActionResult(
                    status="unchanged",
                    db_path=db_path,
                    existing_uuid=current.uuid,
                    existing_path=current.path,
                )
            return ActionResult(
                status="updated",
                db_path=db_path,
                existing_uuid=current.uuid,
                existing_path=current.path,
            )
        if current.mtime is not None and ctx.mtime is not None and current.mtime == ctx.mtime:
            return ActionResult(
                status="unchanged",
                db_path=db_path,
                existing_uuid=current.uuid,
                existing_path=current.path,
            )
        return ActionResult(
            status="updated",
            db_path=db_path,
            existing_uuid=current.uuid,
            existing_path=current.path,
        )

    if ctx.content_hash:
        candidates = index.rows_by_content_hash.get(ctx.content_hash, [])
        if candidates:
            matched = [
                c
                for c in candidates
                if _norm_ext(c.file_ext) == _norm_ext(ctx.file_ext)
                and bool(c.is_dlst) == bool(ctx.is_dlst)
            ]
            if not matched:
                return ActionResult(status="created", db_path=db_path)

            winner = matched[0]
            if winner.path in index.missing_path_set:
                return ActionResult(
                    status="rename",
                    db_path=db_path,
                    existing_uuid=winner.uuid,
                    existing_path=winner.path,
                )
            return ActionResult(
                status="duplicate",
                db_path=db_path,
                existing_uuid=winner.uuid,
                existing_path=winner.path,
                duplicate_row=winner,
            )

    return ActionResult(status="created", db_path=db_path)
