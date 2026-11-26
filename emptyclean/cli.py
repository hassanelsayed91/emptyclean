"""Command line interface for EmptyClean."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import core
from .core import CleanOptions

BANNER = "EmptyClean {v} - remove empty folders and temp files safely".format(v=core.VERSION)


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _default_root() -> Path:
    return Path.cwd()


def _build_options(args: argparse.Namespace) -> CleanOptions:
    opts = CleanOptions()
    opts.delete_empty_dirs = not getattr(args, "no_empty", False)
    opts.delete_temp_files = not getattr(args, "no_temp", False)
    if getattr(args, "patterns", None):
        opts.temp_patterns = [p.strip() for p in args.patterns.split(",") if p.strip()]
    if getattr(args, "recursive", None) is not None:
        opts.recursive = args.recursive
    if getattr(args, "include_hidden", False):
        opts.include_hidden = True
    if getattr(args, "min_age", None) is not None:
        opts.min_age_seconds = args.min_age
    return opts


def _print_plan(items, limit=None):
    counts = core.summarize(items)
    st = counts.get("status", {})
    kinds = counts.get("kinds", {})
    print(f"  total: {len(items)}   empty dirs: {kinds.get('empty_dir', 0)}   "
          f"temp files: {kinds.get('temp_file', 0)}")
    print(f"  planned: {st.get('planned', 0)}")
    print()
    if limit is not None:
        shown = items[:limit]
        for it in shown:
            size = core.human_size(it.size) if it.size else ""
            print(f"  [{it.kind}] {it.src}  {size}")
        if len(items) > len(shown):
            print(f"  ... and {len(items) - len(shown)} more")
        print()


def cmd_plan(args):
    root = Path(args.path).expanduser() if args.path else _default_root()
    opts = _build_options(args)
    items = core.plan_clean(root, opts)
    print(f"\n{BANNER}\n  folder: {root}\n")
    _print_plan(items, limit=args.limit)
    return 0


def cmd_run(args):
    root = Path(args.path).expanduser() if args.path else _default_root()
    opts = _build_options(args)
    items = core.plan_clean(root, opts)
    print(f"\n{BANNER}\n  folder: {root}\n")
    _print_plan(items, limit=args.limit)
    if not items:
        return 0
    if args.dry_run:
        print("  dry run: nothing was changed.\n")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("  refusing to delete without --yes in a non-interactive shell.\n")
            return 2
        n = len(items)
        answer = input(f"  Delete {n} item(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("  cancelled.\n")
            return 0
    summary, journal = core.execute(items)
    st = summary
    print(f"  deleted: {st.get('deleted', 0)}   skipped: {st.get('skipped', 0)}   "
          f"errors: {st.get('error', 0)}")
    if journal:
        print(f"  undo with:  emptyclean undo \"{journal}\"")
    print()
    return 0 if st.get("error", 0) == 0 else 1


def cmd_undo(args):
    journal = Path(args.journal).expanduser() if args.journal else None
    summary, used = core.undo(journal, dry_run=args.dry_run)
    if not used:
        print("No journal found - nothing to undo.")
        return 1
    prefix = "would restore" if args.dry_run else "restored"
    print(f"\n{BANNER}\n  journal: {used}\n")
    print(f"  {prefix}: {summary.get('restored', 0)}   "
          f"missing: {summary.get('missing', 0)}   errors: {summary.get('error', 0)}\n")
    return 0


def cmd_journals(args):
    journals = core.list_journals()
    if not journals:
        print(f"No journals yet in {core.journal_dir()}")
        return 0
    print(f"\n  {len(journals)} journal(s) in {core.journal_dir()}\n")
    for path in journals[:args.limit]:
        import datetime as _dt
        stamp = _dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {stamp}   {path.name}")
    print()
    return 0


def cmd_gui(args):
    try:
        from .gui import main as gui_main
    except ImportError as exc:
        print(f"Tkinter is not available: {exc}", file=sys.stderr)
        return 1
    gui_main(args.path)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="emptyclean", description="Remove empty folders and temp files safely.")
    parser.add_argument("--version", action="version", version=f"EmptyClean {core.VERSION}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-empty", action="store_true", help="do not remove empty folders")
    common.add_argument("--no-temp", action="store_true", help="do not remove temp files")
    common.add_argument("--patterns", help="comma-separated glob patterns for temp files")
    common.add_argument("-r", "--recursive", action="store_true", default=True, help="recurse into subfolders")
    common.add_argument("--no-recursive", dest="recursive", action="store_false", help="only the top folder")
    common.add_argument("--include-hidden", action="store_true", help="include hidden files/folders")
    common.add_argument("--min-age", type=int, metavar="SECONDS", help="only temp files older than this")
    common.add_argument("-n", "--limit", type=int, default=25, help="how many items to print")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", parents=[common], help="show what would be removed")
    plan.add_argument("path", nargs="?")
    plan.set_defaults(func=cmd_plan)
    run = sub.add_parser("run", parents=[common], help="actually remove")
    run.add_argument("path", nargs="?")
    run.add_argument("-y", "--yes", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)
    undo = sub.add_parser("undo", help="restore from a journal")
    undo.add_argument("journal", nargs="?")
    undo.add_argument("--dry-run", action="store_true")
    undo.set_defaults(func=cmd_undo)
    journals = sub.add_parser("journals", help="list journals")
    journals.add_argument("-n", "--limit", type=int, default=20)
    journals.set_defaults(func=cmd_journals)
    gui = sub.add_parser("gui", help="open the desktop app")
    gui.add_argument("path", nargs="?")
    gui.set_defaults(func=cmd_gui)
    return parser


def main(argv=None):
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (NotADirectoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
