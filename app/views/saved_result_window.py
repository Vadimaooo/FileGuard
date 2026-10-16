"""Окреме вікно історії не змінює поточну перевірку або її еталон."""

import tkinter as tk
from tkinter import ttk


class SavedResultWindow(tk.Toplevel):
    def __init__(self, parent, result, text: str, on_export=None):
        super().__init__(parent)
        self.title("Збережена перевірка — FileGuard")
        self.transient(parent)
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - 950) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - 620) // 2)
        self.geometry(f"950x620+{x}+{y}")
        self.minsize(650, 400)
        self._append_after = None
        self.bind("<Destroy>", self._cancel_append, add="+")
        toolbar = ttk.Frame(self, padding=12)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Збережений результат · поточні файли повторно не читаються").pack(side="left")
        if on_export:
            ttk.Button(toolbar, text="Зберегти звіт", command=lambda: on_export(result)).pack(side="right")
        content = tk.Text(self, wrap="word", font=("Consolas", 10), background="white", padx=14, pady=12)
        scroll = ttk.Scrollbar(self, command=content.yview)
        scroll.pack(side="right", fill="y")
        content.pack(fill="both", expand=True)
        content.configure(yscrollcommand=scroll.set, state="disabled")
        self.content = content

        def append(start=0):
            self._append_after = None
            content.configure(state="normal")
            content.insert("end", text[start:start + 16384])
            content.configure(state="disabled")
            if start + 16384 < len(text):
                self._append_after = self.after(1, lambda: append(start + 16384))

        append()

    def _cancel_append(self, event):
        if event.widget is self and self._append_after is not None:
            self.after_cancel(self._append_after)
            self._append_after = None
