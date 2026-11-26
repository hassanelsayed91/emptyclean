"""Tkinter desktop app for EmptyClean."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import core
from .core import CleanItem, CleanOptions


class App:
    def __init__(self, root_path=None):
        self.root = tk.Tk()
        self.root.title("EmptyClean")
        self.root.geometry("900x600")
        self.root.minsize(700, 450)

        self.folder_var = tk.StringVar(value=root_path or str(Path.cwd()))
        self.no_empty_var = tk.BooleanVar(value=False)
        self.no_temp_var = tk.BooleanVar(value=False)
        self.patterns_var = tk.StringVar(value=", ".join(core.DEFAULT_TEMP_PATTERNS))
        self.recursive_var = tk.BooleanVar(value=True)
        self.include_hidden_var = tk.BooleanVar(value=False)
        self.min_age_var = tk.StringVar(value="")

        self.items = []
        self._build()
        self._refresh()

    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.folder_var, width=52).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self._browse).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Refresh", command=self._refresh).grid(row=0, column=3, padx=4)
        top.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(self.root, text="Options", padding=8)
        opts.pack(fill="x", padx=8, pady=4)
        ttk.Checkbutton(opts, text="Skip empty folders", variable=self.no_empty_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Skip temp files", variable=self.no_temp_var).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Checkbutton(opts, text="Recursive", variable=self.recursive_var).grid(row=0, column=2, sticky="w", padx=8)
        ttk.Checkbutton(opts, text="Include hidden", variable=self.include_hidden_var).grid(row=0, column=3, sticky="w", padx=8)
        ttk.Label(opts, text="Patterns:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(opts, textvariable=self.patterns_var).grid(row=1, column=1, columnspan=3, sticky="we", pady=2, padx=4)
        ttk.Label(opts, text="Min age (s):").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(opts, textvariable=self.min_age_var, width=10).grid(row=2, column=1, sticky="w", pady=2, padx=4)

        preview = ttk.Frame(self.root, padding=8)
        preview.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree = ttk.Treeview(preview, columns=("kind", "path", "size"), show="headings")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("path", text="Path")
        self.tree.heading("size", text="Size")
        self.tree.column("kind", width=100)
        self.tree.column("path", width=620)
        self.tree.column("size", width=90)
        vsb = ttk.Scrollbar(preview, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        ttk.Button(bar, text="Undo last", command=self._undo).pack(side="right", padx=4)
        ttk.Button(bar, text="Delete", command=self._apply).pack(side="right", padx=4)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get() or None)
        if d:
            self.folder_var.set(d)
            self._refresh()

    def _options(self):
        opts = CleanOptions()
        opts.delete_empty_dirs = not self.no_empty_var.get()
        opts.delete_temp_files = not self.no_temp_var.get()
        opts.temp_patterns = [p.strip() for p in self.patterns_var.get().split(",") if p.strip()]
        opts.recursive = self.recursive_var.get()
        opts.include_hidden = self.include_hidden_var.get()
        try:
            opts.min_age_seconds = int(self.min_age_var.get())
        except ValueError:
            opts.min_age_seconds = 0
        return opts

    def _refresh(self):
        try:
            self.items = core.plan_clean(self.folder_var.get(), self._options())
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            self.items = []
            return
        self.tree.delete(*self.tree.get_children())
        for it in self.items:
            self.tree.insert("", "end", values=(it.kind, str(it.src), core.human_size(it.size) if it.size else ""))
        st = core.summarize(self.items).get("status", {})
        self.status_var.set(f"{len(self.items)} item(s): {st}")

    def _apply(self):
        if not self.items:
            return
        if not messagebox.askyesno("Confirm", f"Delete {len(self.items)} item(s)?"):
            return

        def worker():
            summary, journal = core.execute(list(self.items))
            self.root.after(0, lambda: self._done(summary, journal))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, summary, journal):
        msg = f"deleted: {summary.get('deleted', 0)}   skipped: {summary.get('skipped', 0)}   errors: {summary.get('error', 0)}"
        if journal:
            msg += f"\nundo: {journal}"
        messagebox.showinfo("Done", msg)
        self._refresh()

    def _undo(self):
        summary, used = core.undo()
        if not used:
            messagebox.showinfo("Undo", "No journal found.")
            return
        messagebox.showinfo("Undo", f"restored: {summary.get('restored', 0)}   missing: {summary.get('missing', 0)}   errors: {summary.get('error', 0)}")
        self._refresh()

    def run(self):
        self.root.mainloop()


def main(root_path=None):
    App(root_path).run()


if __name__ == "__main__":
    main()
