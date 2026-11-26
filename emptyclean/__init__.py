"""EmptyClean - delete empty folders and temp files safely, with undo."""

from .core import (
    VERSION,
    CleanItem,
    CleanOptions,
    execute,
    human_size,
    list_journals,
    plan_clean,
    summarize,
    undo,
)

__all__ = [
    "VERSION", "CleanItem", "CleanOptions", "execute", "human_size",
    "list_journals", "plan_clean", "summarize", "undo",
]
__version__ = VERSION