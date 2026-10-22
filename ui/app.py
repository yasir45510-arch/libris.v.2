"""ReadEra-inspired desktop interface for the LIBRIS reading companion."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ai.brain import ask_about_book, summarise_text
from audio.microphone import listen
from audio.speaker import speak, stop_speaking
from library.book_manager import (
    INBOX_DIR,
    add_book,
    ensure_library_folders,
    get_current_book,
    import_inbox_books,
    list_books,
    select_book,
)
from library.book_reader import get_progress, read_book, save_progress, split_paragraphs


BLACK = "#0A0810"
BLACK_SOFT = "#141019"
PANEL = "#1B1522"
PURPLE_DARK = "#39264D"
PURPLE = "#D8C3FF"
PURPLE_SOFT = "#F3EDFF"
RED = "#E9445D"
RED_ACTIVE = "#C9334B"
TEXT = "#FBF8FF"
MUTED = "#B9AEC5"
BORDER = "#34273F"
PAGE = "#FAF7FF"
PAGE_INK = "#21192C"


def _load_artwork(filename: str, max_width: int, max_height: int) -> tk.PhotoImage | None:
    """Load and downscale an optional PNG using Tk's built-in image support."""
    path = Path(__file__).resolve().parent / "assets" / filename
    try:
        original = tk.PhotoImage(file=str(path))
        scale = max(
            1,
            (original.width() + max_width - 1) // max_width,
            (original.height() + max_height - 1) // max_height,
        )
        return original.subsample(scale, scale)
    except (tk.TclError, OSError):
        return None


class ReaderWindow(tk.Toplevel):
    """A page-like reader that follows the paragraph being spoken aloud."""

    def __init__(self, app: "LibrisApp", book: dict[str, str]) -> None:
        super().__init__(app)
        self.app = app
        self.book = book
        self.title(f"LIBRIS Reader — {book['title']}")
        self.geometry("860x720")
        self.minsize(620, 500)
        self.configure(bg=BLACK)
        self.paragraphs = split_paragraphs(read_book(book["path"]))
        self.current_index = min(
            get_progress(book["id"])["paragraph_index"],
            max(len(self.paragraphs) - 1, 0),
        )
        self.positions: list[tuple[str, str]] = []
        self._build()
        self._show_paragraph(self.current_index, save=False)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        header = tk.Frame(self, bg=BLACK_SOFT)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=self.book["title"],
            font=("Segoe UI", 16, "bold"),
            fg=PURPLE,
            bg=BLACK_SOFT,
        ).pack(anchor="w", padx=24, pady=(18, 1))
        self.location_text = tk.StringVar()
        tk.Label(
            header,
            textvariable=self.location_text,
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=BLACK_SOFT,
        ).pack(anchor="w", padx=24, pady=(0, 16))

        start_row = tk.Frame(header, bg=BLACK_SOFT)
        start_row.pack(fill=tk.X, padx=24, pady=(0, 16))
        tk.Label(
            start_row,
            text="Start at section:",
            font=("Segoe UI", 10, "bold"),
            fg=PURPLE_SOFT,
            bg=BLACK_SOFT,
        ).pack(side=tk.LEFT)
        self.section_input = tk.Entry(
            start_row,
            width=7,
            bg=PURPLE_SOFT,
            fg=BLACK,
            insertbackground=BLACK,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
        )
        self.section_input.pack(side=tk.LEFT, padx=(8, 8), ipady=4)
        self.section_input.bind("<Return>", lambda _event: self._go_to_section())
        self._button(start_row, "Go", self._go_to_section).pack(side=tk.LEFT)
        tk.Label(
            start_row,
            text="Choose a section, then press Read aloud.",
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BLACK_SOFT,
        ).pack(side=tk.LEFT, padx=(10, 0))

        controls = tk.Frame(self, bg=BLACK_SOFT)
        controls.pack(side=tk.BOTTOM, fill=tk.X)
        self._button(controls, "‹ Previous", self._previous).pack(side=tk.LEFT, padx=(20, 8), pady=15)
        self._button(controls, "Next ›", self._next).pack(side=tk.LEFT, padx=8, pady=15)
        self._button(controls, "Read aloud", self._read, primary=True).pack(side=tk.LEFT, padx=8, pady=15)
        self._button(controls, "Pause", self.app._stop_reading, danger=True).pack(side=tk.LEFT, padx=8, pady=15)
        self._button(controls, "Close", self._close).pack(side=tk.RIGHT, padx=20, pady=15)

        content = tk.Frame(self, bg=PAGE)
        content.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        scrollbar = tk.Scrollbar(
            content,
            bg=PURPLE_SOFT,
            troughcolor=PAGE,
            activebackground=PURPLE,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text = tk.Text(
            content,
            bg=PAGE,
            fg=PAGE_INK,
            insertbackground=PAGE_INK,
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
            font=("Georgia", 14),
            padx=22,
            pady=14,
            selectbackground=PURPLE,
            selectforeground=PAGE_INK,
            yscrollcommand=scrollbar.set,
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.text.yview)
        self.text.tag_configure("active", background="#E7D9FF", foreground=PAGE_INK)
        self.text.tag_configure("heading", foreground=PURPLE_DARK, font=("Georgia", 18, "bold"))
        self.text.insert(tk.END, f"{self.book['title']}\n\n", "heading")
        for paragraph in self.paragraphs:
            start = self.text.index(tk.END)
            self.text.insert(tk.END, f"{paragraph}\n\n")
            end = self.text.index(tk.END)
            self.positions.append((start, end))
        self.text.configure(state=tk.DISABLED)

    def _button(self, parent: tk.Misc, text: str, command, primary: bool = False, danger: bool = False) -> tk.Button:
        background = RED if danger else (PURPLE if primary else PURPLE_DARK)
        foreground = BLACK if primary else TEXT
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=RED_ACTIVE if danger else ("#E9D5FF" if primary else "#42255F"),
            activeforeground=TEXT if danger else BLACK if primary else TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
        )

    def _show_paragraph(self, index: int, save: bool = True) -> None:
        if not self.paragraphs:
            self.location_text.set("No readable text was found in this book.")
            return
        self.current_index = max(0, min(index, len(self.paragraphs) - 1))
        self.text.configure(state=tk.NORMAL)
        self.text.tag_remove("active", "1.0", tk.END)
        start, end = self.positions[self.current_index]
        self.text.tag_add("active", start, end)
        self.text.see(start)
        self.text.configure(state=tk.DISABLED)
        self.location_text.set(f"Reading section {self.current_index + 1} of {len(self.paragraphs)}")
        self.section_input.delete(0, tk.END)
        self.section_input.insert(0, str(self.current_index + 1))
        if save:
            progress = save_progress(self.book["id"], self.current_index, len(self.paragraphs))
            self.app._update_progress(progress["progress_percent"])

    def _previous(self) -> None:
        self.app._stop_reading()
        self._show_paragraph(self.current_index - 1)

    def _next(self) -> None:
        self.app._stop_reading()
        self._show_paragraph(self.current_index + 1)

    def _go_to_section(self) -> None:
        try:
            requested = int(self.section_input.get())
        except ValueError:
            messagebox.showerror("Choose a section", "Enter a whole-number section, for example 12.")
            return
        if not 1 <= requested <= len(self.paragraphs):
            messagebox.showerror(
                "Section out of range",
                f"Choose a section from 1 to {len(self.paragraphs)}.",
            )
            return
        self.app._stop_reading()
        self._show_paragraph(requested - 1)

    def _read(self) -> None:
        self.app._start_reading(self.book, self.current_index, self)

    def follow_spoken_paragraph(self, index: int) -> None:
        self._show_paragraph(index, save=False)

    def _close(self) -> None:
        self.app._stop_reading()
        if self.app.reader_window is self:
            self.app.reader_window = None
        self.destroy()


class LibrisApp(tk.Tk):
    """A purple, red, and black library with reader and voice features."""

    def __init__(self) -> None:
        super().__init__()
        ensure_library_folders()
        self.title("LIBRIS — Your Reading Companion")
        self.geometry("1180x760")
        self.minsize(960, 680)
        self.configure(bg=BLACK)

        self.active_book: dict[str, str] | None = None
        self.book_rows: list[dict[str, str]] = []
        self.reader_window: ReaderWindow | None = None
        self.reader_stop = threading.Event()
        self.reading = False
        self.status_text = tk.StringVar(value="Choose a book or import one to begin.")
        self.progress_text = tk.StringVar(value="0% complete")
        self.library_count_text = tk.StringVar(value="0 BOOKS")
        self.book_title_text = tk.StringVar(value="Reading now")
        self.book_meta_text = tk.StringVar(value="Your private library")
        self._configure_style()
        self._build_layout()
        self._refresh_library()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Libris.Horizontal.TProgressbar",
            troughcolor=PURPLE_DARK,
            background=RED,
            bordercolor=BLACK_SOFT,
            lightcolor=RED,
            darkcolor=RED,
            thickness=12,
        )

    def _build_layout(self) -> None:
        sidebar = tk.Frame(self, bg=BLACK_SOFT, width=270, highlightthickness=0)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=BLACK_SOFT)
        brand.pack(fill=tk.X, padx=22, pady=(25, 21))
        tk.Label(
            brand,
            text="L",
            font=("Georgia", 17, "bold"),
            fg=TEXT,
            bg=RED,
            width=2,
            height=1,
        ).pack(side=tk.LEFT, ipady=2)
        brand_copy = tk.Frame(brand, bg=BLACK_SOFT)
        brand_copy.pack(side=tk.LEFT, padx=(11, 0))
        tk.Label(
            brand_copy,
            text="LIBRIS",
            font=("Segoe UI", 21, "bold"),
            fg=TEXT,
            bg=BLACK_SOFT,
        ).pack(anchor="w")
        tk.Label(
            brand_copy,
            text="YOUR READING COMPANION",
            font=("Segoe UI", 8, "bold"),
            fg=MUTED,
            bg=BLACK_SOFT,
        ).pack(anchor="w", pady=(1, 0))
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill=tk.X, padx=20, pady=(0, 18))

        library_head = tk.Frame(sidebar, bg=BLACK_SOFT)
        library_head.pack(fill=tk.X, padx=22, pady=(0, 7))
        tk.Label(
            library_head,
            text="YOUR LIBRARY",
            font=("Segoe UI", 9, "bold"),
            fg=PURPLE,
            bg=BLACK_SOFT,
        ).pack(side=tk.LEFT)
        tk.Label(
            library_head,
            textvariable=self.library_count_text,
            font=("Segoe UI", 8, "bold"),
            fg=RED,
            bg=BLACK_SOFT,
        ).pack(side=tk.RIGHT)

        library_body = tk.Frame(sidebar, bg=BLACK_SOFT)
        library_body.pack(fill=tk.BOTH, expand=True, padx=12)
        self.book_list = tk.Listbox(
            library_body,
            bg=BLACK_SOFT,
            fg="#E9E1F1",
            selectbackground=PURPLE_DARK,
            selectforeground=PURPLE_SOFT,
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.book_list.bind("<<ListboxSelect>>", self._select_from_list)
        self.empty_shelf = tk.Frame(library_body, bg=BLACK_SOFT)
        self.empty_shelf_photo = _load_artwork("libris_empty_shelf.png", 132, 132)
        if self.empty_shelf_photo:
            tk.Label(self.empty_shelf, image=self.empty_shelf_photo, bg=BLACK_SOFT).pack(pady=(18, 8))
        tk.Label(
            self.empty_shelf,
            text="Your shelves are waiting.",
            font=("Georgia", 11, "bold"),
            fg=PURPLE,
            bg=BLACK_SOFT,
            wraplength=205,
            justify=tk.CENTER,
        ).pack(pady=(5, 4))
        tk.Label(
            self.empty_shelf,
            text="Import a book to begin your reading journey.",
            font=("Segoe UI", 9),
            fg=MUTED,
            bg=BLACK_SOFT,
            wraplength=205,
            justify=tk.CENTER,
        ).pack(pady=(0, 12))

        imports = tk.Frame(sidebar, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        imports.pack(fill=tk.X, padx=13, pady=16)
        tk.Label(
            imports,
            text="ADD TO YOUR LIBRARY",
            font=("Segoe UI", 8, "bold"),
            fg=PURPLE,
            bg=PANEL,
        ).pack(anchor="w", padx=12, pady=(12, 9))
        self._button(imports, "＋  Import a book", self._import_book, primary=True).pack(fill=tk.X, padx=10)
        self._button(imports, "Import from Inbox", self._import_inbox).pack(fill=tk.X, padx=10, pady=(7, 0))
        tk.Label(
            imports,
            text=f"Or place TXT, PDF, or EPUB files here:\n{INBOX_DIR}",
            wraplength=205,
            justify=tk.LEFT,
            font=("Segoe UI", 8),
            fg=MUTED,
            bg=PANEL,
        ).pack(anchor="w", padx=12, pady=(11, 12))

        main = tk.Frame(self, bg=BLACK)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hero = tk.Frame(main, bg=PANEL, height=240, highlightthickness=1, highlightbackground=BORDER)
        hero.pack(fill=tk.X, padx=32, pady=(20, 15))
        hero.pack_propagate(False)
        hero_copy = tk.Frame(hero, bg=PANEL)
        tk.Label(
            hero_copy,
            text="THE QUIET POWER OF READING",
            font=("Segoe UI", 9, "bold"),
            fg=PURPLE,
            bg=PANEL,
        ).pack(anchor="w", pady=(0, 7))
        title_label = tk.Label(
            hero_copy,
            textvariable=self.book_title_text,
            font=("Segoe UI", 25, "bold"),
            fg=TEXT,
            bg=PANEL,
            wraplength=450,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        title_label.pack(anchor="w")
        tk.Label(
            hero_copy,
            textvariable=self.book_meta_text,
            font=("Segoe UI", 10),
            fg=MUTED,
            bg=PANEL,
        ).pack(anchor="w", pady=(4, 0))
        tk.Frame(hero_copy, bg=RED, width=42, height=3).pack(anchor="w", pady=(12, 10))
        intro_label = tk.Label(
            hero_copy,
            text="Read, listen, and ask with answers grounded in your book.",
            font=("Segoe UI", 10),
            fg="#D0C5D8",
            bg=PANEL,
            wraplength=440,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        intro_label.pack(anchor="w")
        last_wrap_width = [0]

        def fit_hero_copy(_event=None) -> None:
            width = max(200, hero_copy.winfo_width() - 8)
            if width != last_wrap_width[0]:
                title_size = 21 if width < 340 else 25
                title_label.configure(wraplength=width, font=("Segoe UI", title_size, "bold"))
                intro_label.configure(wraplength=width)
                last_wrap_width[0] = width

        hero_copy.bind("<Configure>", fit_hero_copy)
        art_panel = tk.Frame(hero, bg=BLACK, width=280, height=220)
        art_panel.pack(side=tk.RIGHT, padx=10, pady=9)
        art_panel.pack_propagate(False)
        hero_copy.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(23, 10), pady=19)
        self.after_idle(fit_hero_copy)
        self.hero_photo = _load_artwork("libris_hero.png", 270, 200)
        if self.hero_photo:
            tk.Label(art_panel, image=self.hero_photo, bg=BLACK, bd=0).place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        else:
            tk.Label(
                art_panel,
                text="A LIBRARY\nOF YOUR OWN",
                font=("Georgia", 17, "bold"),
                fg=PURPLE,
                bg=BLACK,
                justify=tk.CENTER,
            ).place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        progress = tk.Frame(main, bg=BLACK_SOFT, highlightthickness=1, highlightbackground=BORDER)
        progress.pack(fill=tk.X, padx=38, pady=(0, 17))
        tk.Label(progress, text="READING PROGRESS", font=("Segoe UI", 9, "bold"), fg=PURPLE, bg=BLACK_SOFT).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 5))
        tk.Label(progress, textvariable=self.progress_text, font=("Segoe UI", 9, "bold"), fg=RED, bg=BLACK_SOFT).grid(row=0, column=1, sticky="e", padx=18, pady=(14, 5))
        progress.grid_columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress, style="Libris.Horizontal.TProgressbar", maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 14))

        controls = tk.Frame(main, bg=BLACK)
        controls.pack(fill=tk.X, padx=38, pady=(0, 17))
        self._button(controls, "Open reader", self._open_selected_reader, primary=True).pack(side=tk.LEFT)
        self._button(controls, "Read aloud", self._read_book).pack(side=tk.LEFT, padx=(8, 0))
        self._button(controls, "Pause", self._stop_reading, danger=True).pack(side=tk.LEFT, padx=(8, 0))
        self._button(controls, "Summarise", self._summarise_book).pack(side=tk.LEFT, padx=(8, 0))
        self._button(controls, "Liberian", self._voice_command, primary=True).pack(side=tk.RIGHT)

        status_row = tk.Frame(main, bg=BLACK)
        status_row.pack(side=tk.BOTTOM, fill=tk.X, padx=38, pady=(0, 15))
        tk.Label(status_row, text="●", font=("Segoe UI", 8), fg=RED, bg=BLACK).pack(side=tk.LEFT)
        tk.Label(status_row, textvariable=self.status_text, anchor="w", font=("Segoe UI", 9), fg=MUTED, bg=BLACK).pack(side=tk.LEFT, padx=(7, 0))

        discussion = tk.Frame(main, bg=BLACK_SOFT, highlightthickness=1, highlightbackground=BORDER)
        discussion.pack(fill=tk.BOTH, expand=True, padx=38, pady=(0, 14))
        discussion_head = tk.Frame(discussion, bg=BLACK_SOFT)
        discussion_head.pack(fill=tk.X, padx=19, pady=(15, 7))
        tk.Label(discussion_head, text="Discuss this book", font=("Segoe UI", 12, "bold"), fg=TEXT, bg=BLACK_SOFT).pack(side=tk.LEFT)
        tk.Label(discussion_head, text="BOOK-GROUNDED QUESTIONS", font=("Segoe UI", 8, "bold"), fg=PURPLE, bg=BLACK_SOFT).pack(side=tk.RIGHT)
        ask_row = tk.Frame(discussion, bg=BLACK_SOFT)
        ask_row.pack(side=tk.BOTTOM, fill=tk.X, padx=19, pady=(0, 16))
        self.question = tk.Entry(
            ask_row,
            bg=PURPLE_SOFT,
            fg=BLACK,
            insertbackground=BLACK,
            relief=tk.FLAT,
            font=("Segoe UI", 11),
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PURPLE,
        )
        self.question.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10)
        self.question.bind("<Return>", lambda _event: self._ask_question())
        self._button(ask_row, "Ask  ↗", self._ask_question, primary=True).pack(side=tk.LEFT, padx=(9, 0))
        self.answer_box = tk.Text(
            discussion,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            height=9,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            padx=15,
            pady=12,
            selectbackground=PURPLE_DARK,
        )
        self.answer_box.pack(fill=tk.BOTH, expand=True, padx=19, pady=(0, 10))
        self._write_answer("Import a book to open it in the reader, follow the spoken text, and ask questions using that book only.")

    def _button(self, parent: tk.Misc, text: str, command, primary: bool = False, danger: bool = False) -> tk.Button:
        bg = RED if danger else (PURPLE if primary else PURPLE_DARK)
        fg = TEXT if danger else BLACK if primary else TEXT
        hover = "#F26176" if danger else "#E7D9FF" if primary else "#4A345F"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=RED_ACTIVE if danger else "#E7D9FF" if primary else "#4A345F",
            activeforeground=TEXT if danger else BLACK if primary else TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PURPLE,
            padx=15,
            pady=10,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=bg))
        return button

    def _refresh_library(self, selected_id: str | None = None) -> None:
        self.book_rows = list_books()
        self.library_count_text.set(f"{len(self.book_rows)} BOOKS")
        self.book_list.pack_forget()
        self.empty_shelf.pack_forget()
        if self.book_rows:
            self.book_list.pack(fill=tk.BOTH, expand=True)
        else:
            self.empty_shelf.pack(fill=tk.BOTH, expand=True)
        self.book_list.delete(0, tk.END)
        for book in self.book_rows:
            self.book_list.insert(tk.END, f"  {book['title']}")
        current = get_current_book()
        target_id = selected_id or (current["id"] if current else None)
        if target_id:
            for index, book in enumerate(self.book_rows):
                if book["id"] == target_id:
                    self.book_list.selection_set(index)
                    self.book_list.activate(index)
                    self._activate_book(book)
                    return
        self._activate_book(None)

    def _select_from_list(self, _event=None) -> None:
        selected = self.book_list.curselection()
        if selected:
            self._activate_book(self.book_rows[selected[0]])

    def _activate_book(self, book: dict[str, str] | None) -> None:
        self.active_book = book
        if book is None:
            self.book_title_text.set("Reading now")
            self.book_meta_text.set("Your private library")
            self._update_progress(0)
            return
        select_book(book["id"])
        self.book_title_text.set(book["title"])
        self.book_meta_text.set(f"{book['author']}  •  {book['format'].upper()} book")
        self._update_progress(get_progress(book["id"])["progress_percent"])
        self.status_text.set(f"Selected: {book['title']}")

    def _import_book(self) -> None:
        path = filedialog.askopenfilename(title="Choose a book to import", filetypes=[("Books", "*.txt *.pdf *.epub"), ("All files", "*.*")])
        if not path:
            return
        try:
            book = add_book(path)
            self._refresh_library(book["id"])
            self._open_reader(book)
            self._offer_start_reading(book)
            self.status_text.set(f"Imported and opened {book['title']}.")
        except (FileNotFoundError, ValueError, OSError, RuntimeError) as error:
            messagebox.showerror("Could not import book", str(error))

    def _import_inbox(self) -> None:
        try:
            books = import_inbox_books()
        except (ValueError, OSError) as error:
            messagebox.showerror("Could not import Inbox", str(error))
            return
        if not books:
            messagebox.showinfo("Inbox is empty", f"Place TXT, PDF, or EPUB files in:\n{INBOX_DIR}")
            return
        self._refresh_library(books[-1]["id"])
        self._open_reader(books[-1])
        self._offer_start_reading(books[-1])

    def _require_book(self) -> dict[str, str] | None:
        if self.active_book is None:
            messagebox.showinfo("Choose a book", "Import or select a book first.")
        return self.active_book

    def _open_selected_reader(self) -> None:
        book = self._require_book()
        if book:
            self._open_reader(book)

    def _open_reader(self, book: dict[str, str], autoplay: bool = False) -> None:
        try:
            if self.reader_window and self.reader_window.winfo_exists():
                if self.reader_window.book["id"] == book["id"]:
                    self.reader_window.deiconify()
                    self.reader_window.lift()
                    if autoplay:
                        self._start_reading(book, self.reader_window.current_index, self.reader_window)
                    return
                self.reader_window.destroy()
            self.reader_window = ReaderWindow(self, book)
            if autoplay:
                self._start_reading(book, self.reader_window.current_index, self.reader_window)
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("Could not open reader", str(error))

    def _offer_start_reading(self, book: dict[str, str]) -> None:
        """Let the reader decide whether to narrate immediately after import."""
        if self.reader_window is None:
            return
        section = self.reader_window.current_index + 1
        should_start = messagebox.askyesno(
            "Book imported",
            f"{book['title']} is open at section {section}.\n\n"
            "Start reading aloud now? Choose No to select another section first.",
        )
        if should_start:
            self._start_reading(book, self.reader_window.current_index, self.reader_window)

    def _read_book(self) -> None:
        book = self._require_book()
        if book is None:
            return
        self._open_reader(book)
        if self.reader_window:
            self._start_reading(book, self.reader_window.current_index, self.reader_window)

    def _start_reading(self, book: dict[str, str], start: int, reader: ReaderWindow | None = None) -> None:
        if self.reading:
            return
        self.reader_stop.clear()
        self.reading = True
        self.status_text.set("Reading aloud. The reader highlights each spoken section.")
        threading.Thread(target=self._reading_worker, args=(book, start, reader), daemon=True).start()

    def _reading_worker(self, book: dict[str, str], start: int, reader: ReaderWindow | None) -> None:
        try:
            paragraphs = split_paragraphs(read_book(book["path"]))
            if not paragraphs:
                raise RuntimeError("This book does not contain readable text.")
            for index in range(start, len(paragraphs)):
                if self.reader_stop.is_set():
                    break
                if reader and reader.winfo_exists():
                    self.after(0, reader.follow_spoken_paragraph, index)
                self.after(0, self._write_answer, paragraphs[index])
                speak(paragraphs[index], stop_event=self.reader_stop)
                if self.reader_stop.is_set():
                    break
                progress = save_progress(book["id"], index + 1, len(paragraphs))
                self.after(0, self._update_progress, progress["progress_percent"])
            if self.reader_stop.is_set():
                status = "Paused. Progress is saved through the last completed section."
            else:
                status = "Finished reading. Your progress is saved."
            self.after(0, self._set_status, status)
        except Exception as error:
            self.after(0, self._set_status, f"Reading problem: {error}")
        finally:
            self.reading = False

    def _stop_reading(self) -> None:
        self.reader_stop.set()
        stopped = stop_speaking()
        self.status_text.set("Paused. Speech stopped immediately." if stopped else "Playback paused.")

    def _summarise_book(self) -> None:
        book = self._require_book()
        if book:
            self.status_text.set("Finding key ideas throughout the book…")
            threading.Thread(target=self._summary_worker, args=(book,), daemon=True).start()

    def _summary_worker(self, book: dict[str, str]) -> None:
        try:
            summary = summarise_text(read_book(book["path"]))
            response = f"Summary of {book['title']}:\n\n{summary}"
            self.after(0, self._show_and_speak, response)
        except Exception as error:
            self.after(0, self._set_status, f"Summary problem: {error}")

    def _ask_question(self) -> None:
        book = self._require_book()
        question = self.question.get().strip()
        if not book or not question:
            return
        self.question.delete(0, tk.END)
        self.status_text.set("Searching the selected book for supporting text…")
        threading.Thread(target=self._question_worker, args=(book, question), daemon=True).start()

    def _question_worker(self, book: dict[str, str], question: str) -> None:
        try:
            answer = ask_about_book(question, read_book(book["path"]), book["title"])
            self.after(0, self._show_and_speak, answer)
        except Exception as error:
            self.after(0, self._set_status, f"Question problem: {error}")

    def _voice_command(self) -> None:
        if self._require_book():
            self.status_text.set("Liberian is listening for a six-second command…")
            threading.Thread(target=self._voice_worker, daemon=True).start()

    def _voice_worker(self) -> None:
        self.after(0, self._handle_voice_command, listen())

    def _handle_voice_command(self, command: str) -> None:
        if not command:
            self.status_text.set("No voice command was recognised.")
        elif "stop" in command or "pause" in command:
            self._stop_reading()
        elif "read" in command or "continue" in command or "resume" in command:
            self._read_book()
        elif "back" in command or "previous" in command:
            if self.reader_window:
                self.reader_window._previous()
        elif "progress" in command or "where did i stop" in command:
            assert self.active_book is not None
            self._show_and_speak(f"You are {get_progress(self.active_book['id'])['progress_percent']}% through {self.active_book['title']}.")
        else:
            self.question.delete(0, tk.END)
            self.question.insert(0, command)
            self._ask_question()

    def _show_and_speak(self, text: str) -> None:
        self._write_answer(text)
        self.status_text.set("Response ready. Speaking it now.")
        threading.Thread(target=speak, args=(text,), daemon=True).start()

    def _write_answer(self, text: str) -> None:
        self.answer_box.configure(state=tk.NORMAL)
        self.answer_box.delete("1.0", tk.END)
        self.answer_box.insert("1.0", text)
        self.answer_box.configure(state=tk.DISABLED)

    def _update_progress(self, percent: float) -> None:
        self.progress_bar["value"] = percent
        self.progress_text.set(f"{percent}% complete")

    def _set_status(self, text: str) -> None:
        self.status_text.set(text)

    def _close(self) -> None:
        self.reader_stop.set()
        stop_speaking()
        self.destroy()


def run() -> None:
    LibrisApp().mainloop()
