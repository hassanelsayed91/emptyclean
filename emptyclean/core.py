"""EmptyClean core engine.

Safe cleanup of empty folders and temporary files:
  * plans what would be removed (no changes on disk)
  * moves temporary files to a per-run trash folder so they can be restored
  * removes empty folders (recreated on undo)
  * writes a journal so every run can be undone with one command
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

APP_NAME = "EmptyClean"
VERSION = "1.0.0"
JOURNAL_VERSION = 1
PROJECT_URL = "https://github.com/hassanelsayed91/emptyclean"

DEFAULT_TEMP_PATTERNS = [
    "*.tmp", "*.temp", "*.crdownload", "*.partial", "*.part", "*.download",
    "*.bak", "*.old", "~$*", "desktop.ini", "thumbs.db", "*.log",
]

DEFAULT_EXCLUDE_DIRS = [
    "node_modules", ".git", "__pycache__", "$RECYCLE.BIN",
    "System Volume Information", ".venv", "venv",
]


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def journal_dir() -> Path:
    return data_dir() / "journal"


def trash_root() -> Path:
    return data_dir() / "trash"


# --------------------------------------------------------------------------- #
# options
# --------------------------------------------------------------------------- #
@dataclass
class CleanOptions:
    delete_empty_dirs: bool = True
    delete_temp_files: bool = True
    temp_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_TEMP_PATTERNS))
    recursive: bool = True
    include_hidden: bool = False
    min_age_seconds: int = 0
    exclude_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_DIRS))
    exclude_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "delete_empty_dirs": self.delete_empty_dirs,
            "delete_temp_files": self.delete_temp_files,
            "temp_patterns": self.temp_patterns,
            "recursive": self.recursive,
            "include_hidden": self.include_hidden,
            "min_age_seconds": self.min_age_seconds,
            "exclude_dirs": self.exclude_dirs,
            "exclude_names": self.exclude_names,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CleanOptions":
        opts = cls()
        for key, value in (data or {}).items():
            if hasattr(opts, key):
                setattr(opts, key, value)
        return opts


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
@dataclass
class CleanItem:
    src: Path
    dst: Path            # trash path (files) or src (dirs)
    kind: str            # empty_dir | temp_file
    status: str = "planned"   # planned | deleted | skipped | error | restored | unchanged
    error: str = ""
    size: int = 0
    mtime: float = 0.0

    def to_dict(self) -> dict:
        return {
            "src": str(self.src), "dst": str(self.dst), "kind": self.kind,
            "status": self.status, "error": self.error, "size": self.size,
            "mtime": self.mtime,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CleanItem":
        return cls(
            src=Path(data["src"]), dst=Path(data["dst"]),
            kind=data.get("kind", "temp_file"),
            status=data.get("status", "planned"),
            error=data.get("error", ""),
            size=int(data.get("size") or 0),
            mtime=float(data.get("mtime") or 0.0),
        )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    if os.name != "nt":
        return False
    try:
        attrs = path.stat().st_file_attributes
    except (OSError, AttributeError):
        return False
    import stat as _stat
    hidden = getattr(_stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)
    system = getattr(_stat, "FILE_ATTRIBUTE_SYSTEM", 0x4)
    return bool(attrs & (hidden | system))


def _is_excluded_dir(name: str, excluded: Iterable[str]) -> bool:
    lowered = name.lower()
    return lowered in {d.lower() for d in excluded}


def _is_temp(name: str, patterns: Iterable[str]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pat.lower()) for pat in patterns)


def _iter_dirs(root: Path, options: CleanOptions) -> list[Path]:
    if not options.recursive:
        return [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    result: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d, options.exclude_dirs)]
        if not options.include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        p = Path(dirpath)
        if p != root:
            result.append(p)
    return result


def _all_files(root: Path, options: CleanOptions) -> list[Path]:
    result: list[Path] = []
    if not options.recursive:
        candidates = root.iterdir() if root.exists() else []
        for p in candidates:
            if p.is_file():
                result.append(p)
        return result
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d, options.exclude_dirs)]
        if not options.include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if not options.include_hidden and _is_hidden(p):
                continue
            if _is_excluded_dir(p.name, options.exclude_names):
                continue
            result.append(p)
    return result


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
def plan_clean(root: str | os.PathLike, options: CleanOptions | None = None) -> list[CleanItem]:
    options = options or CleanOptions()
    root_path = Path(root).expanduser()
    if not root_path.is_dir():
        raise NotADirectoryError(f"not a folder: {root_path}")

    items: list[CleanItem] = []
    deleted_file_paths: set[str] = set()

    # temp files
    if options.delete_temp_files:
        now = datetime.now().timestamp()
        for path in _all_files(root_path, options):
            if not path.is_file():
                continue
            if not options.include_hidden and _is_hidden(path):
                continue
            if _is_excluded_dir(path.name, options.exclude_names):
                continue
            if not _is_temp(path.name, options.temp_patterns):
                continue
            if options.min_age_seconds:
                try:
                    age = now - path.stat().st_mtime
                except OSError:
                    continue
                if age < options.min_age_seconds:
                    continue
            try:
                st = path.stat()
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                size, mtime = 0, 0.0
            items.append(CleanItem(src=path, dst=path, kind="temp_file",
                                  size=size, mtime=mtime))
            deleted_file_paths.add(_norm(path))

    # empty dirs (cascading): a dir is deletable if no surviving files in subtree
    if options.delete_empty_dirs:
        dirs = _iter_dirs(root_path, options)
        # sort deepest first
        dirs_sorted = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
        surviving_cache: dict[Path, bool] = {}

        def has_surviving(d: Path) -> bool:
            if d in surviving_cache:
                return surviving_cache[d]
            # a surviving file directly or in any child
            found = False
            try:
                for child in d.iterdir():
                    if child.is_file():
                        if _norm(child) not in deleted_file_paths:
                            found = True
                            break
                    elif child.is_dir():
                        if _is_excluded_dir(child.name, options.exclude_dirs):
                            continue
                        if not options.include_hidden and _is_hidden(child):
                            # hidden dir still occupies space; treat as surviving
                            found = True
                            break
                        if has_surviving(child):
                            found = True
                            break
            except OSError:
                found = True
            surviving_cache[d] = found
            return found

        deletable: set[Path] = set()
        for d in dirs_sorted:
            if _is_excluded_dir(d.name, options.exclude_dirs):
                continue
            if not options.include_hidden and _is_hidden(d):
                continue
            if has_surviving(d):
                continue
            # all child dirs must be deletable or absent
            children_dirs = [c for c in d.iterdir() if c.is_dir()] if d.exists() else []
            children_dirs = [c for c in children_dirs if not _is_excluded_dir(c.name, options.exclude_dirs)]
            if all(c in deletable for c in children_dirs):
                deletable.add(d)

        for d in sorted(deletable, key=lambda p: len(p.parts), reverse=True):
            items.append(CleanItem(src=d, dst=d, kind="empty_dir", size=0,
                                  mtime=d.stat().st_mtime if d.exists() else 0.0))

    return items


# --------------------------------------------------------------------------- #
# journals
# --------------------------------------------------------------------------- #
def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _save_journal(path: Path, items: list[CleanItem], note: str, trash_dir: str) -> None:
    payload = {
        "app": APP_NAME,
        "version": VERSION,
        "journal_version": JOURNAL_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "note": note,
        "trash_dir": trash_dir,
        "items": [m.to_dict() for m in items],
    }
    _write_json(path, payload)


def latest_journal() -> Path | None:
    folder = journal_dir()
    if not folder.is_dir():
        return None
    journals = sorted(folder.glob("journal-*.json"), key=lambda p: p.stat().st_mtime)
    return journals[-1] if journals else None


def list_journals() -> list[Path]:
    folder = journal_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob("journal-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


# --------------------------------------------------------------------------- #
# executing / undoing
# --------------------------------------------------------------------------- #
def execute(items: list[CleanItem], dry_run: bool = False, record: bool = True):
    summary: Counter = Counter()

    if dry_run or not items:
        for item in items:
            summary[item.status] += 1
        return summary, None

    if not record:
        for item in items:
            _apply(item, summary, None)
        return summary, None

    journal_dir().mkdir(parents=True, exist_ok=True)
    trash_root().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    run_trash = trash_root() / f"run-{stamp}-{os.getpid()}"
    run_trash.mkdir(parents=True, exist_ok=True)
    journal = journal_dir() / f"journal-{stamp}-{os.getpid()}.json"
    _save_journal(journal, items, note="pending", trash_dir=str(run_trash))
    try:
        for item in items:
            _apply(item, summary, run_trash)
    finally:
        _save_journal(journal, items, note="finished", trash_dir=str(run_trash))

    if summary.get("deleted", 0) == 0:
        try:
            journal.unlink()
        except OSError:
            pass
        return summary, None
    return summary, journal


def _apply(item: CleanItem, summary: Counter, run_trash: Path | None) -> None:
    if item.status in ("skipped", "unchanged", "error", "restored"):
        summary[item.status] += 1
        return
    try:
        if item.kind == "temp_file":
            if not item.src.exists():
                item.status, item.error = "skipped", "source no longer exists"
                summary["skipped"] += 1
                return
            if run_trash is None:
                item.src.unlink()
                item.dst = item.src
                item.status = "deleted"
                summary["deleted"] += 1
                return
            # move to trash
            run_trash.mkdir(parents=True, exist_ok=True)
            dst = run_trash / item.src.name
            # unique in trash
            if dst.exists():
                stem, suffix = dst.stem, dst.suffix
                i = 1
                while True:
                    cand = run_trash / f"{stem} ({i}){suffix}"
                    if not cand.exists():
                        dst = cand
                        break
                    i += 1
            item.src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.src), str(dst))
            item.dst = dst
            item.status = "deleted"
            summary["deleted"] += 1
        else:  # empty_dir
            if not item.src.exists():
                item.status, item.error = "skipped", "source no longer exists"
                summary["skipped"] += 1
                return
            # remove dir (should be empty)
            try:
                item.src.rmdir()
            except OSError:
                # maybe not empty; try shutil.rmtree? safety: only rmdir
                raise
            item.dst = item.src
            item.status = "deleted"
            summary["deleted"] += 1
    except Exception as exc:  # noqa: BLE001
        item.status = "error"
        item.error = f"{type(exc).__name__}: {exc}"
        summary["error"] += 1


def undo(journal: str | os.PathLike | None = None, dry_run: bool = False):
    path = Path(journal) if journal else latest_journal()
    if not path or not path.exists():
        return Counter({"missing": 1}), None

    data = json.loads(path.read_text(encoding="utf-8"))
    trash_dir = Path(data.get("trash_dir", "")) if data.get("trash_dir") else None
    summary: Counter = Counter()
    updated: list[dict] = []

    for record in reversed(data.get("items", [])):
        item = CleanItem.from_dict(record)
        if item.status != "deleted":
            updated.append(record)
            continue
        try:
            if item.kind == "temp_file":
                if not item.dst.exists():
                    summary["missing"] += 1
                    updated.append(record)
                    continue
                destination = item.src
                if destination.exists():
                    # unique
                    stem, suffix = destination.stem, destination.suffix
                    parent = destination.parent
                    i = 1
                    while destination.exists():
                        destination = parent / f"{stem} ({i}){suffix}"
                        i += 1
                if not dry_run:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item.dst), str(destination))
                record["status"] = "restored"
                record["restored_to"] = str(destination)
                summary["restored"] += 1
                updated.append(record)
            else:  # empty_dir
                if not dry_run:
                    item.src.mkdir(parents=True, exist_ok=True)
                record["status"] = "restored"
                summary["restored"] += 1
                updated.append(record)
        except Exception as exc:  # noqa: BLE001
            summary["error"] += 1
            moved = dict(record)
            moved["error"] = f"{type(exc).__name__}: {exc}"
            updated.append(moved)
            print(f"[{APP_NAME}] could not restore {item.src}: {exc}", file=sys.stderr)

    if not dry_run:
        data["undone_at"] = datetime.now().isoformat(timespec="seconds")
        data["items"] = list(reversed(updated))
        _write_json(path, data)
        # remove trash dir if empty
        if trash_dir and trash_dir.exists():
            try:
                if not any(trash_dir.iterdir()):
                    trash_dir.rmdir()
            except OSError:
                pass

    return summary, path


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024 or unit == "TB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def summarize(items: Iterable[CleanItem]) -> dict:
    counts: Counter = Counter()
    for item in items:
        counts[item.status] += 1
    kinds: Counter = Counter()
    for item in items:
        kinds[item.kind] += 1
    return {"status": dict(counts), "kinds": dict(kinds)}
