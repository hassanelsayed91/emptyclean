# EmptyClean

Safely remove empty folders and temporary files on Windows, with a one-command undo.

![screenshot](docs/screenshot.png)

## Problem

Over time folders fill up with empty directories left behind by uninstalled apps
and temp files (`*.tmp`, `*.crdownload`, `Thumbs.db`, ...). Deleting them by
hand is tedious and risky. EmptyClean plans every deletion first, shows a
preview, refuses to touch non-empty folders, and moves deleted files into a
per-run trash folder so `emptyclean undo` restores everything.

## Features

- Remove empty folders (cascading: a folder that becomes empty is removed too).
- Remove temporary files by glob patterns (customisable).
- Preview before deleting, dry-run support.
- Never deletes a non-empty folder.
- Deleted files go to a per-run trash folder and can be restored.
- `--min-age` to only touch old temp files.
- Recursive or top-level only, hidden files optional.
- Desktop app (Tkinter) and CLI. No runtime dependencies.

## Install

Download `EmptyClean.exe` from the
[Releases](https://github.com/hassanelsayed91/emptyclean/releases) page, or run
from source:

```powershell
git clone https://github.com/hassanelsayed91/emptyclean.git
cd emptyclean
python -m emptyclean gui
```

## Examples

```powershell
# preview
emptyclean plan C:\Downloads

# apply
emptyclean run C:\Downloads --yes

# only temp files, keep empty folders
emptyclean run C:\Downloads --no-empty --yes

# custom patterns
emptyclean run C:\Downloads --patterns "*.tmp,*.bak,*.log" --yes

# undo
emptyclean undo
```

## Safety

- Nothing is changed until you confirm (or pass `--yes`).
- `--dry-run` shows exactly what would happen.
- A folder is removed only if it is empty (or becomes empty after temp removal).
- Deleted files are moved to a trash folder, not permanently erased.
- `emptyclean undo` restores every file and recreates every folder.

## Arabic / العربية

**EmptyClean** حذف آمن للفولدرات الفاضية والملفات المؤقتة. معاينة قبل
الحذف، وعدم حذف أي فولدر غير فاضٍ. الملفات المحذوفة تنتقل إلى سلة مهملات
لكل عملية ويمكن استرجاعها بأمر واحد `emptyclean undo`.

## License

MIT
