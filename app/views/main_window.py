"""Головне вікно: лише віджети, діалоги та відображення стану."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.font import nametofont
from typing import TYPE_CHECKING

from app import __version__
from app.models import AppState

if TYPE_CHECKING:
    from app.controllers.app_controller import AppController


BACKGROUND = "#F4F7FC"
SURFACE = "#FFFFFF"
TEXT = "#17243C"
MUTED = "#66758F"
BLUE = "#1769E8"
BORDER = "#DCE4F0"


class SurfacePanel(tk.Frame):
    """Повторно використовувана секція: зовнішня рамка та білий вміст."""

    def __init__(self, parent: tk.Misc, padding: int = 18) -> None:
        super().__init__(parent, background=BORDER, borderwidth=0)
        self.content = ttk.Frame(self, style="Surface.TFrame", padding=padding)
        self.content.pack(fill="both", expand=True, padx=1, pady=1)


class MainWindow(tk.Tk):
    """Представлення MVC; звертається до логіки тільки через контролер."""

    def __init__(self) -> None:
        super().__init__()
        self._controller: AppController | None = None
        self.title("FileGuard — Контроль цілісності файлів")
        self.configure(background=BACKGROUND)
        self.minsize(980, 780)
        width = min(1240, self.winfo_screenwidth() - 80)
        height = min(870, self.winfo_screenheight() - 100)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.folder_text = tk.StringVar(value="Папку ще не обрано")
        self.include_subfolders = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar()
        self.folder_hint = tk.StringVar(value="Оберіть папку, стан якої потрібно контролювати.")
        self._configure_styles()
        self._build_layout()

    def _configure_styles(self) -> None:
        """Спільні стилі дають змогу змінювати оформлення в одному місці."""
        # Загальний option_add('*Font') перекрив би розміри заголовків ttk.
        nametofont("TkDefaultFont", root=self).configure(family="Segoe UI", size=10)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("TLabel", background=BACKGROUND, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Surface.TLabel", background=SURFACE)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("SurfaceMuted.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        style.configure("Subtitle.TLabel", foreground=MUTED, font=("Segoe UI", 11))
        style.configure("Heading.TLabel", background=SURFACE, font=("Segoe UI", 12, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=(15, 9),
                        background="#F5F8FD", foreground=TEXT, bordercolor=BORDER,
                        lightcolor="#F5F8FD", darkcolor="#F5F8FD", focusthickness=1,
                        focuscolor=BLUE)
        style.map("TButton", background=[("active", "#E9F0FB")],
                  foreground=[("disabled", "#8995AA")])
        style.configure("Primary.TButton", background=BLUE, foreground="white",
                        bordercolor=BLUE, lightcolor=BLUE, darkcolor=BLUE)
        style.map("Primary.TButton", background=[("disabled", "#A4BFE9"), ("active", "#1057CB")],
                  foreground=[("disabled", "#FFFFFF")])
        style.configure("TEntry", padding=9, fieldbackground=SURFACE, bordercolor=BORDER)
        style.map("TEntry", fieldbackground=[("readonly", "#FAFCFF")],
                  foreground=[("readonly", TEXT)])
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT, padding=(0, 3))
        style.map("TCheckbutton", background=[("active", SURFACE)])
        style.configure("TNotebook", background=BACKGROUND, borderwidth=0, tabmargins=(0, 0, 0, 8))
        style.configure("TNotebook.Tab", padding=(21, 9), background=BACKGROUND,
                        foreground=MUTED, font=("Segoe UI", 11), borderwidth=0,
                        lightcolor=BACKGROUND, darkcolor=BACKGROUND)
        style.map("TNotebook.Tab", background=[("selected", SURFACE)],
                  foreground=[("selected", BLUE)])
        style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                        foreground=TEXT, rowheight=35, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#F1F5FB", foreground=TEXT,
                        font=("Segoe UI", 10, "bold"), padding=(10, 9), relief="flat")
        style.map("Treeview", background=[("selected", "#E3EDFE")],
                  foreground=[("selected", TEXT)])
        style.configure("TCombobox", padding=7, bordercolor=BORDER)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(26, 15, 26, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="FileGuard", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Контроль цілісності файлів · порівняння зі збереженим еталоном",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=22)
        self.check_tab = ttk.Frame(self.notebook, padding=(0, 4, 0, 12))
        self.history_tab = ttk.Frame(self.notebook, padding=(0, 4, 0, 12))
        self.settings_tab = ttk.Frame(self.notebook, padding=(0, 4, 0, 12))
        self.notebook.add(self.check_tab, text="Перевірка")
        self.notebook.add(self.history_tab, text="Історія")
        self.notebook.add(self.settings_tab, text="Налаштування")
        self._build_check_tab()
        self._build_history_tab()
        self._build_settings_tab()

        footer = ttk.Frame(self, padding=(26, 10, 26, 12))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_text, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(footer, text=f"FileGuard {__version__}", style="Muted.TLabel").grid(
            row=0, column=1, sticky="e"
        )

    def _build_check_tab(self) -> None:
        self.check_tab.columnconfigure(0, weight=1)
        self.check_tab.rowconfigure(2, weight=1)
        controls_panel = SurfacePanel(self.check_tab, padding=14)
        controls_panel.grid(row=0, column=0, sticky="ew")
        controls = controls_panel.content
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, text="Папка для перевірки", style="Surface.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        self.folder_entry = ttk.Entry(controls, textvariable=self.folder_text, state="readonly")
        self.folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        self.choose_button = ttk.Button(controls, text="Обрати папку", command=self._choose_folder)
        self.choose_button.grid(row=1, column=1, sticky="ew")
        ttk.Checkbutton(controls, text="Включати вкладені папки", variable=self.include_subfolders,
                        command=self._change_subfolders).grid(row=2, column=0, sticky="w", pady=(8, 10))

        actions = ttk.Frame(controls, style="Surface.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(0, weight=1)
        baseline = ttk.Frame(actions, style="Surface.TFrame")
        baseline.grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(baseline, text="Еталон не завантажено", style="Surface.TLabel").pack(anchor="w")
        ttk.Label(baseline, text="Алгоритм: SHA-256", style="SurfaceMuted.TLabel").pack(anchor="w", pady=(3, 0))
        # Кнопки залишаються неактивними, доки відповідні операції не реалізовано.
        self.create_baseline_button = ttk.Button(actions, text="Створити еталон", state="disabled")
        self.create_baseline_button.grid(row=0, column=1, padx=(0, 8))
        self.load_baseline_button = ttk.Button(actions, text="Завантажити еталон", state="disabled")
        self.load_baseline_button.grid(row=0, column=2, padx=(0, 8))
        self.check_button = ttk.Button(actions, text="Перевірити цілісність",
                                       style="Primary.TButton", state="disabled")
        self.check_button.grid(row=0, column=3)

        cards = ttk.Frame(self.check_tab)
        cards.grid(row=1, column=0, sticky="ew", pady=12)
        card_specs = [
            ("Усього", "#526A91"),
            ("Без змін", "#16854B"),
            ("Змінено", "#B46A0A"),
            ("Додано", BLUE),
            ("Видалено", "#D23E4F"),
        ]
        self.counter_labels: dict[str, ttk.Label] = {}
        for index, (label, color) in enumerate(card_specs):
            cards.columnconfigure(index, weight=1, uniform="counter")
            card_panel = SurfacePanel(cards, padding=10)
            card_panel.grid(row=0, column=index, sticky="nsew",
                            padx=(0 if index == 0 else 5, 0 if index == 4 else 5))
            card = card_panel.content
            tk.Label(card, text=label, background=SURFACE, foreground=MUTED,
                     font=("Segoe UI", 10)).pack(anchor="w")
            value = ttk.Label(card, text="—", background=SURFACE, foreground=color,
                              font=("Segoe UI", 23, "bold"))
            value.pack(anchor="w", pady=(2, 0))
            self.counter_labels[label] = value

        results_panel = SurfacePanel(self.check_tab, padding=14)
        results_panel.grid(row=2, column=0, sticky="nsew")
        results = results_panel.content
        results.columnconfigure(0, weight=1)
        results.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(results, style="Surface.TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="Результати перевірки", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.status_filter = ttk.Combobox(toolbar, values=("Усі статуси",), width=15, state="disabled")
        self.status_filter.set("Усі статуси")
        self.status_filter.grid(row=0, column=1, padx=(8, 10))
        self.export_button = ttk.Button(toolbar, text="Зберегти звіт", state="disabled")
        self.export_button.grid(row=0, column=2)

        table_area = ttk.Frame(results, style="Surface.TFrame")
        table_area.grid(row=1, column=0, sticky="nsew")
        table_area.columnconfigure(0, weight=1)
        table_area.rowconfigure(0, weight=1)
        self.results_table = ttk.Treeview(table_area, columns=("file", "status", "size", "modified"),
                                          show="headings", height=4, selectmode="browse")
        for column, title, width, minimum in [
            ("file", "Файл", 430, 200),
            ("status", "Статус", 170, 120),
            ("size", "Розмір", 110, 90),
            ("modified", "Остання зміна", 200, 160),
        ]:
            self.results_table.heading(column, text=title, anchor="w")
            self.results_table.column(column, width=width, minwidth=minimum, anchor="w")
        self.results_table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table_area, orient="vertical", command=self.results_table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_area, orient="horizontal", command=self.results_table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.results_table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        # Порожній стан не є рядком результатів і не потрапить до майбутнього експорту.
        self.empty_state = ttk.Frame(table_area, style="Surface.TFrame", padding=16)
        self.empty_state.place(relx=0.5, rely=0.56, anchor="center")
        ttk.Label(self.empty_state, text="Перевірку ще не виконано", style="Heading.TLabel").pack()
        ttk.Label(self.empty_state, textvariable=self.folder_hint, style="SurfaceMuted.TLabel",
                  wraplength=520, justify="center").pack(pady=(7, 0))
        ttk.Label(results, text="Результатів поки немає", style="SurfaceMuted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )

    def _build_history_tab(self) -> None:
        history_panel = SurfacePanel(self.history_tab, padding=26)
        history_panel.pack(fill="both", expand=True)
        panel = history_panel.content
        ttk.Label(panel, text="Історія перевірок", style="Heading.TLabel").pack(anchor="w")
        empty = ttk.Frame(panel, style="Surface.TFrame")
        empty.pack(expand=True)
        ttk.Label(empty, text="Історія перевірок порожня", style="Heading.TLabel").pack()
        ttk.Label(empty, text="Тут відображатимуться результати виконаних перевірок.",
                  style="SurfaceMuted.TLabel").pack(pady=(8, 0))

    def _build_settings_tab(self) -> None:
        settings_panel = SurfacePanel(self.settings_tab, padding=26)
        settings_panel.pack(fill="both", expand=True)
        panel = settings_panel.content
        ttk.Label(panel, text="Налаштування перевірки", style="Heading.TLabel").pack(anchor="w")
        ttk.Checkbutton(panel, text="Включати вкладені папки", variable=self.include_subfolders,
                        command=self._change_subfolders).pack(anchor="w", pady=(20, 5))
        ttk.Label(panel, text="Параметр синхронізовано з вкладкою «Перевірка».",
                  style="SurfaceMuted.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Алгоритм контролю", style="Heading.TLabel").pack(anchor="w", pady=(28, 8))
        ttk.Label(panel, text="SHA-256", style="Surface.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Еталон зберігатиме цифрові відбитки файлів, а не їхні резервні копії.",
                  style="SurfaceMuted.TLabel", wraplength=700).pack(anchor="w", pady=(7, 0))

    def set_controller(self, controller: AppController) -> None:
        self._controller = controller

    def _choose_folder(self) -> None:
        if self._controller is not None:
            self._controller.choose_folder()

    def _change_subfolders(self) -> None:
        if self._controller is not None:
            self._controller.set_include_subfolders(self.include_subfolders.get())

    def ask_directory(self, initial_directory: str | None) -> str:
        """Діалог належить представленню; перевірка шляху належить сервісу."""
        return filedialog.askdirectory(
            parent=self,
            title="Оберіть папку для контролю цілісності",
            initialdir=initial_directory or str(Path.home()),
            mustexist=True,
        )

    def show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self)

    def render_state(self, state: AppState) -> None:
        """Оновлює віджети зі стану моделі, не змінюючи саму модель."""
        self.folder_text.set(str(state.selected_folder) if state.selected_folder else "Папку ще не обрано")
        self.include_subfolders.set(state.include_subfolders)
        self.status_text.set(state.status_message)
        self.folder_hint.set(
            "Папку обрано. Результати з’являться після виконання перевірки."
            if state.selected_folder
            else "Оберіть папку, стан якої потрібно контролювати."
        )
