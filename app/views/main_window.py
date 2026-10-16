"""Головне вікно: лише віджети, діалоги та відображення стану."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.font import nametofont
from typing import TYPE_CHECKING, Callable

from app import __version__
from app.models import AppState, Baseline, CheckResult, FileStatus
from app.views.saved_result_window import SavedResultWindow

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
        self.minsize(980, 820)
        width = min(1240, self.winfo_screenwidth() - 80)
        height = min(920, self.winfo_screenheight() - 100)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.folder_text = tk.StringVar(value="Папку ще не обрано")
        self.include_subfolders = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar()
        self.folder_hint = tk.StringVar(value="Оберіть папку, стан якої потрібно контролювати.")
        self.baseline_name = tk.StringVar(value="Еталон не завантажено")
        self.baseline_summary = tk.StringVar(value="Алгоритм: SHA-256")
        self.baseline_details = tk.StringVar()
        self.table_title = tk.StringVar(value="Результати перевірки")
        self.table_footer = tk.StringVar(value="Результатів поки немає")
        self._rendered_baseline: Baseline | None = None
        self._rendered_check: CheckResult | None = None
        self._rendered_filter: FileStatus | None = None
        self._rendered_patterns = None
        self._visible_files = ()
        self._rendered_history = None
        self._history_available = False
        self._saved_result_window = None
        self.empty_title = tk.StringVar(value="Перевірку ще не виконано")
        self._error_count = 0
        self._busy = False
        self._table_generation = 0
        self._progress_running = False
        self._issues_window: tk.Toplevel | None = None
        self._details_window: tk.Toplevel | None = None
        self._configure_styles()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._request_close)

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
        self.subfolders_check = ttk.Checkbutton(
            controls, text="Включати вкладені папки", variable=self.include_subfolders,
            command=self._change_subfolders,
        )
        self.subfolders_check.grid(row=2, column=0, sticky="w", pady=(8, 10))

        actions = ttk.Frame(controls, style="Surface.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure(0, weight=1)
        baseline = ttk.Frame(actions, style="Surface.TFrame")
        baseline.grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(baseline, textvariable=self.baseline_name, style="Surface.TLabel").pack(anchor="w")
        ttk.Label(baseline, textvariable=self.baseline_summary, style="SurfaceMuted.TLabel").pack(anchor="w", pady=(3, 0))
        self.create_baseline_button = ttk.Button(actions, text="Створити еталон", state="disabled",
                                                 command=self._create_baseline)
        self.create_baseline_button.grid(row=0, column=1, padx=(0, 8))
        self.load_baseline_button = ttk.Button(actions, text="Завантажити еталон", command=self._load_baseline)
        self.load_baseline_button.grid(row=0, column=2, padx=(0, 8))
        self.check_button = ttk.Button(actions, text="Перевірити цілісність",
                                       style="Primary.TButton", state="disabled", command=self._check_integrity)
        self.check_button.grid(row=0, column=3)

        details = ttk.Frame(controls, style="Surface.TFrame")
        details.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        details.columnconfigure(0, weight=1)
        ttk.Label(details, textvariable=self.baseline_details, style="SurfaceMuted.TLabel", wraplength=600).grid(
            row=0, column=0, sticky="w"
        )
        self.issues_button = ttk.Button(details, text="Пропущені шляхи", command=self._show_issues)
        self.issues_button.grid(row=0, column=1, padx=(8, 0))
        self.issues_button.grid_remove()

        self.progress_area = ttk.Frame(controls, style="Surface.TFrame")
        self.progress_area.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.progress_area.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(self.progress_area, mode="indeterminate")
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.cancel_button = ttk.Button(self.progress_area, text="Скасувати", command=self._cancel_operation)
        self.cancel_button.grid(row=0, column=1)
        self.progress_area.grid_remove()

        cards = ttk.Frame(self.check_tab)
        cards.grid(row=1, column=0, sticky="ew", pady=12)
        card_specs = [
            ("Усього", "#526A91"),
            ("Без змін", "#16854B"),
            ("Змінено", "#B46A0A"),
            ("Додано", BLUE),
            ("Видалено", "#D23E4F"),
            ("Помилки", "#7C3BB5"),
        ]
        self.counter_labels: dict[str, ttk.Label] = {}
        for index, (label, color) in enumerate(card_specs):
            cards.columnconfigure(index, weight=1, uniform="counter")
            card_panel = SurfacePanel(cards, padding=10)
            card_panel.grid(row=0, column=index, sticky="nsew",
                            padx=(0 if index == 0 else 5, 0 if index == len(card_specs) - 1 else 5))
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
        ttk.Label(toolbar, textvariable=self.table_title, style="Heading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.status_filter = ttk.Combobox(toolbar, values=("Усі статуси",) + tuple(s.value for s in FileStatus),
                                          width=15, state="disabled")
        self.status_filter.set("Усі статуси")
        self.status_filter.bind("<<ComboboxSelected>>", self._change_filter)
        self.status_filter.grid(row=0, column=1, padx=(8, 10))
        self.details_button = ttk.Button(toolbar, text="Відомості", state="disabled", command=self._show_file_details)
        self.details_button.grid(row=0, column=2, padx=(0, 8))
        self.export_button = ttk.Menubutton(toolbar, text="Зберегти звіт", state="disabled")
        self.export_menu = tk.Menu(self.export_button, tearoff=False)
        self.export_menu.add_command(label="Текстовий звіт (.txt)", command=lambda: self._export_report("txt"))
        self.export_menu.add_command(label="Таблиця CSV (.csv)", command=lambda: self._export_report("csv"))
        self.export_button.configure(menu=self.export_menu)
        self.export_button.grid(row=0, column=3)

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
        for status, background, foreground in (
            (FileStatus.UNCHANGED, "#EBF7EF", "#17663B"),
            (FileStatus.CHANGED, "#FFF4DF", "#8C5207"),
            (FileStatus.ADDED, "#EAF1FF", "#1759B8"),
            (FileStatus.DELETED, "#FFF0F1", "#AE263B"),
            (FileStatus.ERROR, "#F4EAFE", "#7532A7"),
        ):
            self.results_table.tag_configure(status.name, background=background, foreground=foreground)
        self.results_table.bind("<<TreeviewSelect>>", lambda event: self._sync_details_button())
        self.results_table.bind("<Double-1>", self._show_file_details)
        self.results_table.bind("<Return>", self._show_file_details)
        vertical = ttk.Scrollbar(table_area, orient="vertical", command=self.results_table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_area, orient="horizontal", command=self.results_table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.results_table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        # Порожній стан не є рядком результатів і не потрапить до майбутнього експорту.
        self.empty_state = ttk.Frame(table_area, style="Surface.TFrame", padding=16)
        self.empty_state.place(relx=0.5, rely=0.56, anchor="center")
        ttk.Label(self.empty_state, textvariable=self.empty_title, style="Heading.TLabel").pack()
        ttk.Label(self.empty_state, textvariable=self.folder_hint, style="SurfaceMuted.TLabel",
                  wraplength=520, justify="center").pack(pady=(7, 0))
        ttk.Label(results, textvariable=self.table_footer, style="SurfaceMuted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )

    def _build_history_tab(self) -> None:
        history_panel = SurfacePanel(self.history_tab, padding=26)
        history_panel.pack(fill="both", expand=True)
        panel = history_panel.content
        toolbar = ttk.Frame(panel, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(0, 16))
        ttk.Label(toolbar, text="Історія перевірок", style="Heading.TLabel").pack(side="left")
        self.history_open_button = ttk.Button(toolbar, text="Відкрити", command=self._open_history, state="disabled")
        self.history_open_button.pack(side="right")
        self.history_refresh_button = ttk.Button(toolbar, text="Оновити", command=self._refresh_history)
        self.history_refresh_button.pack(side="right", padx=(0, 10))
        area = ttk.Frame(panel, style="Surface.TFrame")
        area.pack(fill="both", expand=True)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.history_table = ttk.Treeview(area, columns=("date", "folder", "total", "changes", "errors", "duration"),
                                          show="headings", selectmode="browse")
        for column, label, width in (("date", "Дата", 170), ("folder", "Папка", 380),
                                     ("total", "Усього", 80), ("changes", "Зміни", 80),
                                     ("errors", "Помилки", 80), ("duration", "Час, с", 80)):
            self.history_table.heading(column, text=label)
            self.history_table.column(column, width=width, minwidth=70)
        self.history_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(area, command=self.history_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.history_table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.history_table.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.history_table.bind("<<TreeviewSelect>>", lambda event: self._sync_history_button())
        self.history_table.bind("<Double-1>", self._open_history)
        self.history_table.bind("<Return>", self._open_history)
        self.history_summary = tk.StringVar(value="Історія перевірок порожня")
        ttk.Label(panel, textvariable=self.history_summary, style="SurfaceMuted.TLabel").pack(anchor="w", pady=(12, 0))

    def _build_settings_tab(self) -> None:
        settings_panel = SurfacePanel(self.settings_tab, padding=26)
        settings_panel.pack(fill="both", expand=True)
        panel = settings_panel.content
        ttk.Label(panel, text="Налаштування перевірки", style="Heading.TLabel").pack(anchor="w")
        self.settings_subfolders_check = ttk.Checkbutton(
            panel, text="Включати вкладені папки", variable=self.include_subfolders,
            command=self._change_subfolders,
        )
        self.settings_subfolders_check.pack(anchor="w", pady=(20, 5))
        ttk.Label(panel, text="Параметр для нового еталона. Перевірка використовує параметри збереженого еталона.",
                  style="SurfaceMuted.TLabel", wraplength=760).pack(anchor="w")
        ttk.Label(panel, text="Алгоритм контролю", style="Heading.TLabel").pack(anchor="w", pady=(28, 8))
        ttk.Label(panel, text="SHA-256", style="Surface.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Еталон зберігатиме цифрові відбитки файлів, а не їхні резервні копії.",
                  style="SurfaceMuted.TLabel", wraplength=700).pack(anchor="w", pady=(7, 0))
        ttk.Label(panel, text="Виключення для нового еталона", style="Heading.TLabel").pack(anchor="w", pady=(24, 8))
        ttk.Label(panel, text="Одне правило на рядок. Приклади: *.tmp, .git, __pycache__, cache/, logs/*.log.",
                  style="SurfaceMuted.TLabel", wraplength=760).pack(anchor="w", pady=(0, 8))
        self.exclusions_input = tk.Text(panel, height=6, width=65, font=("Consolas", 10),
                                        relief="solid", borderwidth=1, padx=8, pady=8)
        self.exclusions_input.pack(anchor="w", fill="x")
        self.apply_exclusions_button = ttk.Button(panel, text="Застосувати виключення", command=self._apply_exclusions)
        self.apply_exclusions_button.pack(anchor="w", pady=(10, 0))
        self.save_settings_button = ttk.Button(panel, text="Зберегти налаштування", command=self._save_settings)
        self.save_settings_button.pack(anchor="w", pady=(16, 0))
        ttk.Label(panel, text="Застосовані параметри також зберігаються під час закриття програми.",
                  style="SurfaceMuted.TLabel").pack(anchor="w", pady=(8, 0))

    def set_controller(self, controller: AppController) -> None:
        self._controller = controller

    def _choose_folder(self) -> None:
        if self._controller is not None:
            self._controller.choose_folder()

    def _change_subfolders(self) -> None:
        if self._controller is not None:
            self._controller.set_include_subfolders(self.include_subfolders.get())

    def _create_baseline(self) -> None:
        if self._controller is not None:
            self._controller.create_baseline()

    def _load_baseline(self) -> None:
        if self._controller is not None:
            self._controller.load_baseline()

    def _check_integrity(self) -> None:
        if self._controller is not None:
            self._controller.check_integrity()

    def _apply_exclusions(self) -> None:
        if self._controller is not None:
            patterns = [line.strip() for line in self.exclusions_input.get("1.0", "end").splitlines() if line.strip()]
            self._controller.set_exclusion_patterns(patterns)

    def _change_filter(self, event=None) -> None:
        if self._controller is not None:
            self._controller.set_status_filter(self.status_filter.get())

    def _save_settings(self):
        if self._controller is not None:
            self._controller.save_settings()

    def get_window_size(self):
        return max(980, self.winfo_width()), max(820, self.winfo_height())

    def apply_window_size(self, size):
        width = max(980, min(size[0], self.winfo_screenwidth() - 80))
        height = max(820, min(size[1], self.winfo_screenheight() - 100))
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _refresh_history(self) -> None:
        if self._controller is not None:
            self._controller.refresh_history()

    def _open_history(self, event=None) -> None:
        selection = self.history_table.selection()
        if selection and self._controller is not None and not self._busy:
            self._controller.open_history(selection[0])

    def _sync_history_button(self) -> None:
        self.history_open_button.configure(state="normal" if self.history_table.selection()
                                            and self._history_available and not self._busy else "disabled")

    def show_saved_result(self, result: CheckResult, text: str) -> None:
        if self._saved_result_window is not None and self._saved_result_window.winfo_exists():
            self._saved_result_window.destroy()
        self._saved_result_window = SavedResultWindow(self, result, text, self._export_saved_report)

    def _export_report(self, extension):
        if self._controller is not None:
            self._controller.export_result(extension=extension)

    def _export_saved_report(self, result, extension):
        if self._controller is not None:
            self._controller.export_result(result, extension)

    def _cancel_operation(self) -> None:
        if self._controller is not None:
            self._controller.cancel_operation()

    def _request_close(self) -> None:
        if self._controller is not None:
            self._controller.request_close()
        else:
            self.destroy()

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

    def ask_save_baseline(self, directory: Path, filename: str) -> str:
        return filedialog.asksaveasfilename(
            parent=self, title="Зберегти еталон", initialdir=str(directory),
            initialfile=filename, defaultextension=".json", filetypes=(("Еталон JSON", "*.json"),),
            confirmoverwrite=True,
        )

    def ask_open_baseline(self, directory: Path) -> str:
        return filedialog.askopenfilename(
            parent=self, title="Завантажити еталон", initialdir=str(directory),
            filetypes=(("Еталон JSON", "*.json"), ("Усі файли", "*.*")),
        )

    def ask_save_report(self, directory: Path, filename: str, extension: str) -> str:
        label = "Текстовий звіт" if extension == "txt" else "Таблиця CSV"
        return filedialog.asksaveasfilename(parent=self, title="Зберегти звіт", initialdir=str(directory),
                                          initialfile=filename, defaultextension="." + extension,
                                          filetypes=((label, "*." + extension),), confirmoverwrite=True)

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        self.after(delay_ms, callback)

    def close(self) -> None:
        self.destroy()

    def _show_issues(self) -> None:
        baseline = self._rendered_baseline
        result = self._rendered_check
        if result is not None:
            issues = [(item.path, item.message) for item in result.files if item.status == FileStatus.ERROR]
            title = "Помилки перевірки"
            heading = "Ці шляхи не вдалося достовірно перевірити"
        else:
            issues = [(item.path, item.message) for item in baseline.issues] if baseline else []
            title = "Шляхи, не включені до еталона"
            heading = "Ці шляхи не охоплені еталоном"
        if not issues:
            return
        if self._issues_window is not None and self._issues_window.winfo_exists():
            self._issues_window.destroy()
        dialog = tk.Toplevel(self)
        self._issues_window = dialog
        dialog.title(title)
        dialog.geometry("820x430")
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=heading, style="Subtitle.TLabel").pack(anchor="w")
        content = tk.Text(body, wrap="word", font=("Segoe UI", 10), background=SURFACE,
                          foreground=TEXT, relief="flat", padx=12, pady=12)
        scroll = ttk.Scrollbar(body, command=content.yview)
        scroll.pack(side="right", fill="y", pady=(12, 0))
        content.pack(fill="both", expand=True, pady=(12, 0))
        content.configure(yscrollcommand=scroll.set)
        # Повний набір зберігається в моделі; вікно обмежене для швидкого відкриття.
        for path, message in issues[:1000]:
            content.insert("end", f"{path}\n{message}\n\n")
        if len(issues) > 1000:
            location = "в таблиці результатів" if result is not None else "у збереженому еталоні"
            content.insert("end", f"Показано перші 1000 записів. Повний список доступний {location}.")
        content.configure(state="disabled")

    def _sync_details_button(self) -> None:
        self.details_button.configure(
            state="normal" if self.results_table.selection() and not self._busy else "disabled"
        )

    def _show_file_details(self, event=None) -> None:
        selection = self.results_table.selection()
        if not selection or self._busy:
            return
        index = int(selection[0].split("-")[-1])
        result = self._rendered_check
        if result is not None:
            item = self._visible_files[index]
            path, status, before, after, message = item.path, item.status.value, item.expected, item.actual, item.message
        elif self._rendered_baseline is not None:
            before = self._rendered_baseline.files[index]
            path, status, after, message = before.path, "В еталоні", None, "Порівняння ще не виконано."
        else:
            return
        if self._details_window is not None and self._details_window.winfo_exists():
            self._details_window.destroy()
        dialog = tk.Toplevel(self)
        self._details_window = dialog
        dialog.title("Відомості про файл")
        dialog.geometry("840x400")
        dialog.transient(self)
        content = tk.Text(dialog, wrap="word", font=("Consolas", 10), background=SURFACE,
                          foreground=TEXT, relief="flat", padx=18, pady=18)
        scroll = ttk.Scrollbar(dialog, command=content.yview)
        scroll.pack(side="right", fill="y")
        content.pack(fill="both", expand=True)
        content.configure(yscrollcommand=scroll.set)
        content.insert("end", f"Шлях: {path}\nСтатус: {status}\n\n{message}\n\n")
        for label, snapshot in (("Еталон", before), ("Поточний стан", after)):
            content.insert("end", f"{label}:\n")
            if snapshot is None:
                content.insert("end", "  Дані відсутні\n\n")
            else:
                content.insert("end", f"  Розмір: {snapshot.size} Б\n  SHA-256: {snapshot.sha256}\n\n")
        content.configure(state="disabled")

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} Б"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} КіБ"
        return f"{size / (1024 * 1024):.1f} МіБ"

    def _render_files(self, baseline: Baseline | None, result: CheckResult | None, status_filter=None) -> None:
        if self._issues_window is not None and self._issues_window.winfo_exists():
            self._issues_window.destroy()
            self._issues_window = None
        if self._details_window is not None and self._details_window.winfo_exists():
            self._details_window.destroy()
            self._details_window = None
        self._rendered_baseline = baseline
        self._rendered_check = result
        self._rendered_filter = status_filter
        self._table_generation += 1
        generation = self._table_generation
        rows = self.results_table.get_children()
        if rows:
            self.results_table.delete(*rows)
        if baseline is None:
            self._visible_files = ()
            self.empty_state.place(relx=0.5, rely=0.56, anchor="center")
            self.table_title.set("Результати перевірки")
            self.table_footer.set("Результатів поки немає")
            return
        self.empty_state.place_forget()
        self.table_title.set("Результати перевірки" if result else "Файли еталона")
        items = (tuple(item for item in result.files if status_filter is None or item.status == status_filter)
                 if result else baseline.files)
        self._visible_files = items
        if not items:
            self.empty_state.place(relx=0.5, rely=0.56, anchor="center")

        def append_batch(start: int = 0) -> None:
            if generation != self._table_generation:
                return
            end = min(start + 200, len(items))
            for index in range(start, end):
                item = items[index]
                snapshot = item.actual if result else item
                status = item.status.value if result else "В еталоні"
                tags = (item.status.name,) if result else ()
                try:
                    modified = (
                        datetime.fromtimestamp(snapshot.modified_ns / 1_000_000_000).strftime("%d.%m.%Y %H:%M")
                        if snapshot is not None else "—"
                    )
                except (OverflowError, OSError, ValueError):
                    modified = "—"
                self.results_table.insert("", "end", iid=f"row-{index}", tags=tags, values=(
                    item.path, status, self._format_size(snapshot.size) if snapshot else "—", modified,
                ))
            if result is not None:
                completed = result.completed_at.astimezone().strftime("%d.%m.%Y %H:%M:%S")
                self.table_footer.set(f"Показано {end} із {len(items)} · усього: {len(result.files)} шляхів · {completed} · {result.duration_seconds:.2f} с")
            else:
                self.table_footer.set(f"Показано {end} із {len(items)} файлів еталона · порівняння ще не виконано")
            if end < len(items):
                # Додаємо рядки порціями, щоб великі еталони не блокували вікно.
                self.after(1, lambda: append_batch(end))

        append_batch()

    def render_state(self, state: AppState) -> None:
        """Оновлює віджети зі стану моделі, не змінюючи саму модель."""
        self.folder_text.set(str(state.selected_folder) if state.selected_folder else "Папку ще не обрано")
        self.include_subfolders.set(state.include_subfolders)
        self._busy = state.busy
        self._history_available = state.history_available
        self.history_refresh_button.configure(state="normal" if state.history_available and not state.busy else "disabled")
        self._sync_history_button()
        if state.history_entries is not self._rendered_history:
            self._rendered_history = state.history_entries
            children = self.history_table.get_children()
            if children:
                self.history_table.delete(*children)
            for entry in state.history_entries:
                changes = sum(entry.counts.get(s, 0) for s in (FileStatus.CHANGED, FileStatus.ADDED, FileStatus.DELETED))
                self.history_table.insert("", "end", iid=entry.identifier, values=(
                    entry.completed_at.astimezone().strftime("%d.%m.%Y %H:%M:%S"), str(entry.root_folder),
                    sum(entry.counts.values()), changes, entry.counts.get(FileStatus.ERROR, 0),
                    f"{entry.duration_seconds:.2f}",
                ))
            self.history_summary.set(f"Показано {len(state.history_entries)} останніх перевірок (до 200). Повні результати доступні через «Відкрити»."
                                     if state.history_entries else "Історія перевірок порожня")
        self.status_text.set(state.status_message)
        enabled = "disabled" if state.busy else "normal"
        self.choose_button.configure(state=enabled)
        self.load_baseline_button.configure(state=enabled)
        self.subfolders_check.configure(state=enabled)
        self.settings_subfolders_check.configure(state=enabled)
        self.apply_exclusions_button.configure(state=enabled)
        self.save_settings_button.configure(state=enabled)
        self.exclusions_input.configure(state=enabled)
        if state.exclusion_patterns != self._rendered_patterns:
            self.exclusions_input.configure(state="normal")
            self.exclusions_input.delete("1.0", "end")
            self.exclusions_input.insert("1.0", "\n".join(state.exclusion_patterns))
            self.exclusions_input.configure(state=enabled)
            self._rendered_patterns = state.exclusion_patterns
        self.create_baseline_button.configure(
            state="normal" if state.selected_folder is not None and not state.busy else "disabled"
        )
        self.check_button.configure(state="normal" if state.baseline is not None and not state.busy else "disabled")
        self.export_button.configure(state="normal" if state.check_result is not None and not state.busy else "disabled")
        if self._saved_result_window is not None and self._saved_result_window.winfo_exists():
            self._saved_result_window.set_busy(state.busy)
        self.cancel_button.configure(state="disabled" if state.cancel_requested else "normal")
        if state.busy:
            self.progress_area.grid()
            if not self._progress_running:
                self.progress_bar.start(15)
                self._progress_running = True
        else:
            self.progress_bar.stop()
            self._progress_running = False
            self.progress_area.grid_remove()
        baseline = state.baseline
        result = state.check_result
        self.status_filter.configure(state="readonly" if result is not None and not state.busy else "disabled")
        self.status_filter.set(state.status_filter.value if state.status_filter is not None else "Усі статуси")
        if (baseline is not self._rendered_baseline or result is not self._rendered_check
                or state.status_filter != self._rendered_filter):
            counts = result.counts if result else {}
            self.counter_labels["Усього"].configure(
                text=str(len(result.files)) if result else str(len(baseline.files)) if baseline else "—"
            )
            for status in FileStatus:
                label = "Помилки" if status == FileStatus.ERROR else status.value
                self.counter_labels[label].configure(text=str(counts.get(status, 0)) if result else "—")
            self._error_count = counts.get(FileStatus.ERROR, 0)
            self._render_files(baseline, result, state.status_filter)
        if baseline is not None:
            name = state.baseline_path.name if state.baseline_path else "Еталон"
            self.baseline_name.set(name if len(name) <= 25 else name[:22] + "…")
            self.baseline_summary.set(f"SHA-256 · файлів: {len(baseline.files)}")
            try:
                created = baseline.created_at.astimezone().strftime("%d.%m.%Y %H:%M:%S")
            except (OverflowError, OSError, ValueError):
                created = baseline.created_at.isoformat(timespec="seconds")
            self.baseline_details.set(
                f"Створено: {created} · вкладені папки: {'так' if baseline.include_subfolders else 'ні'}"
                + f" · правил виключення: {len(baseline.exclusion_patterns)}"
            )
        else:
            self.baseline_name.set("Еталон не завантажено")
            self.baseline_summary.set("Алгоритм: SHA-256")
            self.baseline_details.set("")
        if result and self._error_count:
            self.issues_button.configure(text=f"Помилки перевірки: {self._error_count}")
            self.issues_button.grid()
        elif result is None and baseline and baseline.issues:
            self.issues_button.configure(text=f"Пропущені шляхи: {len(baseline.issues)}")
            self.issues_button.grid()
        else:
            self.issues_button.grid_remove()
        if result is not None:
            self.table_title.set("Попередні результати перевірки" if state.busy else "Результати перевірки")
        self._sync_details_button()
        if result is not None and not self._visible_files:
            self.empty_title.set("Немає результатів за цим фільтром")
            self.folder_hint.set("Оберіть інший статус або «Усі статуси».")
        elif baseline is not None and not baseline.files and result is None:
            self.empty_title.set("Еталон не містить файлів")
            self.folder_hint.set("Папка порожня або всі її файли виключені правилами.")
        else:
            self.empty_title.set("Перевірку ще не виконано")
            self.folder_hint.set(
            "Папку обрано. Результати з’являться після виконання перевірки."
            if state.selected_folder
            else "Оберіть папку, стан якої потрібно контролювати."
            )
