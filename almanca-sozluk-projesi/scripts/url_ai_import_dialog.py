from __future__ import annotations

import os
import re
import threading
import tkinter as tk
import unicodedata
from tkinter import messagebox, ttk


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_text_for_compare(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    normalized = normalized.replace("ß", "ss")
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return normalize_whitespace(normalized)


def normalize_import_term_for_compare(term: str) -> str:
    cleaned = normalize_whitespace(term)
    cleaned = re.sub(r"^(der|die|das)\s+", "", cleaned, flags=re.IGNORECASE)
    return normalize_text_for_compare(cleaned)


def split_translation_variants_for_compare(value: str) -> list[str]:
    raw = normalize_whitespace(value)
    if not raw:
        return []
    parts = [raw, *re.split(r"[;,/|\n]+", raw)]
    variants: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = normalize_whitespace(re.sub(r"^\d+[.)]\s*", "", part)).strip(" -:()[]{}")
        key = normalize_text_for_compare(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        variants.append(cleaned)
    return variants


class EnhancedUrlImportDialog(tk.Toplevel):
    def __init__(self, app, runtime: dict, initial_url: str = "", initial_mode: str = "url") -> None:
        super().__init__(app)
        self.app = app
        self.runtime = runtime
        self.initial_mode = str(initial_mode or "url").strip().lower()
        self.title("URL'den Kelime Aktar")
        self.transient(app)
        self.grab_set()
        self.geometry("1160x820")
        self.minsize(1020, 720)

        self._url_vars: list[tk.StringVar] = []
        self._url_row_frames: list[ttk.Frame] = []
        self.url_var = tk.StringVar(value=initial_url.strip())  # always points to first URL
        self.auto_add_var = tk.BooleanVar(value=False)  # resets every open
        self._url_queue: list[str] = []
        self._url_scan_idx: int = 0
        self._url_total: int = 0
        self._total_saved: int = 0
        self._url_continue_pending: bool = False  # URL bekleme modu
        self.status_var = tk.StringVar(
            value="URL taraması sayfadaki görünür Almanca metni toplar, yeni kelimeleri ve eksik anlamları hazırlar."
        )
        self.summary_var = tk.StringVar(value="Henüz tarama yapılmadı.")
        self.word_var = tk.StringVar(value="-")
        self.source_var = tk.StringVar(value="Kaynak önerisi: -")
        self.frequency_var = tk.StringVar(value="Metinde tekrar: -")
        self.include_var = tk.BooleanVar(value=True)
        self.local_missing_translation_only_var = tk.BooleanVar(value=False)
        self.local_has_translation_only_var = tk.BooleanVar(value=False)
        self.translation_var = tk.StringVar()
        self.pos_var = tk.StringVar(value="belirsiz")
        self.article_var = tk.StringVar(value="")
        self.local_summary_note = "Henüz tarama yapılmadı."
        self.form_note_var = tk.StringVar(value="Çeviri ve tür alanlarını kaydetmeden önce düzenleyebilirsiniz.")

        self.ai_summary_var = tk.StringVar(value="Model anlam taramasi henuz yapilmadi.")
        self.ai_word_var = tk.StringVar(value="-")
        self.ai_existing_var = tk.StringVar(value="Mevcut anlamlar: -")
        self.ai_source_var = tk.StringVar(value="Model: -")
        self.ai_frequency_var = tk.StringVar(value="Metinde tekrar: -")
        self.ai_include_var = tk.BooleanVar(value=True)
        self.ai_translation_var = tk.StringVar()
        self.ai_pos_var = tk.StringVar(value="belirsiz")
        self.ai_article_var = tk.StringVar(value="")
        self.ai_form_note_var = tk.StringVar(value="Bu sekme yalnızca sözlükte eksik görünen anlamları önerir.")

        self.pair_summary_var = tk.StringVar(value="1. Almanca metni girin. 2. Türkçe metni girin. 3. 'Kelimeleri Çıkar' düğmesine basın.")
        self.pair_word_var = tk.StringVar(value="-")
        self.pair_existing_var = tk.StringVar(value="Mevcut anlamlar: -")
        self.pair_source_var = tk.StringVar(value="Model: -")
        self.pair_context_var = tk.StringVar(value="Bağlam: -")
        self.pair_include_var = tk.BooleanVar(value=True)
        self.pair_translation_var = tk.StringVar()
        self.pair_pos_var = tk.StringVar(value="belirsiz")
        self.pair_article_var = tk.StringVar(value="")
        self.pair_form_note_var = tk.StringVar(
            value="Almanca metin ve verdiğiniz Türkçe çeviri birlikte analiz edilir. Sadece eksik görünen anlamlar ekleme listesine düşer."
        )

        self.scan_button: ttk.Button | None = None
        self.pair_scan_button: ttk.Button | None = None
        self.save_button: ttk.Button | None = None
        self.notebook: ttk.Notebook | None = None

        self.local_tab: ttk.Frame | None = None
        self.ai_tab: ttk.Frame | None = None
        self.pair_tab: ttk.Frame | None = None

        self.tree: ttk.Treeview | None = None
        self.translation_entry: ttk.Entry | None = None
        self.include_check: ttk.Checkbutton | None = None

        self.ai_tree: ttk.Treeview | None = None
        self.ai_translation_entry: ttk.Entry | None = None
        self.ai_include_check: ttk.Checkbutton | None = None

        self.pair_tree: ttk.Treeview | None = None
        self.pair_translation_entry: ttk.Entry | None = None
        self.pair_include_check: ttk.Checkbutton | None = None
        self.pair_source_text: tk.Text | None = None
        self.pair_target_text: tk.Text | None = None

        self.is_scanning = False
        self.is_pair_scanning = False
        self.form_loading = False
        self.ai_form_loading = False
        self.pair_form_loading = False

        self.current_candidate_id: str | None = None
        self.current_ai_candidate_id: str | None = None
        self.current_pair_candidate_id: str | None = None

        self.candidates: list[dict] = []
        self.candidate_map: dict[str, dict] = {}
        self.ai_candidates: list[dict] = []
        self.ai_candidate_map: dict[str, dict] = {}
        self.pair_candidates: list[dict] = []
        self.pair_candidate_map: dict[str, dict] = {}

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="URL'den Kelime Aktar", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Bu pencere yalnızca URL taraması içindir. Sayfadaki yeni kelimeleri ve URL bağlamına göre eksik anlam önerilerini burada görüp sözlüğe ekleyebilirsiniz.",
            style="Muted.TLabel",
            wraplength=1040,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))

        urls_outer = ttk.Frame(frame)
        urls_outer.grid(row=2, column=0, sticky="ew")
        urls_outer.columnconfigure(0, weight=1)

        # Scrollable URL list — max 4 satır görünür
        ROW_HEIGHT = 34
        MAX_VISIBLE = 4
        scroll_frame = ttk.Frame(urls_outer)
        scroll_frame.grid(row=0, column=0, sticky="ew")
        scroll_frame.columnconfigure(0, weight=1)
        self._urls_canvas = tk.Canvas(scroll_frame, height=ROW_HEIGHT, highlightthickness=0, bd=0)
        self._urls_canvas.grid(row=0, column=0, sticky="ew")
        self._urls_scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=self._urls_canvas.yview)
        self._urls_scrollbar.grid(row=0, column=1, sticky="ns")
        self._urls_canvas.configure(yscrollcommand=self._urls_scrollbar.set)
        self._urls_inner = ttk.Frame(self._urls_canvas)
        _win = self._urls_canvas.create_window((0, 0), window=self._urls_inner, anchor="nw")

        def _sync(_event=None):
            self._urls_canvas.configure(scrollregion=self._urls_canvas.bbox("all"))
            rows = len(self._url_vars) or 1
            h = min(rows, MAX_VISIBLE) * ROW_HEIGHT
            self._urls_canvas.configure(height=h)
            show = rows > MAX_VISIBLE
            if show:
                self._urls_scrollbar.grid()
            else:
                self._urls_scrollbar.grid_remove()

        def _resize(event):
            self._urls_canvas.itemconfigure(_win, width=event.width)

        self._urls_inner.bind("<Configure>", _sync)
        self._urls_canvas.bind("<Configure>", _resize)
        self._urls_canvas.bind("<MouseWheel>", lambda e: self._urls_canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self._urls_inner.bind("<MouseWheel>", lambda e: self._urls_canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self._add_url_row(initial_url)

        btn_row = ttk.Frame(urls_outer)
        btn_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        btn_row.columnconfigure(1, weight=1)
        ttk.Button(btn_row, text="+ URL Ekle", command=self._add_url_row).grid(row=0, column=0)
        ttk.Checkbutton(
            btn_row, text="Her URL sonrası otomatik ekle",
            variable=self.auto_add_var,
        ).grid(row=0, column=1, padx=(12, 0), sticky="w")
        self.scan_button = ttk.Button(btn_row, text="URL'yi Tara", style="Primary.TButton", command=self.start_scan)
        self.scan_button.grid(row=0, column=2, padx=(8, 0))
        self._api_test_button = ttk.Button(btn_row, text="API Test", command=self._test_api_connection)
        self._api_test_button.grid(row=0, column=3, padx=(6, 0))

        self._api_status_var = tk.StringVar(value="")
        self._api_status_label = ttk.Label(frame, textvariable=self._api_status_var, style="Meta.TLabel", wraplength=1040, justify="left")
        self._api_status_label.grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Label(frame, textvariable=self.status_var, style="Meta.TLabel", wraplength=1040, justify="left").grid(
            row=4, column=0, sticky="w", pady=(4, 12)
        )

        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=5, column=0, sticky="nsew")
        frame.rowconfigure(5, weight=1)
        self.local_tab = ttk.Frame(self.notebook, padding=6)
        self.ai_tab = ttk.Frame(self.notebook, padding=6)
        self.pair_tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(self.local_tab, text="Yeni Kelimeler")
        self.notebook.add(self.ai_tab, text="Eksik Anlamlar (Model)")
        self._build_new_words_tab(self.local_tab)
        self._build_ai_meanings_tab(self.ai_tab)
        self._build_parallel_text_tab(self.pair_tab)

        footer = ttk.Frame(frame, padding=(0, 16, 0, 0))
        footer.grid(row=6, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="İptal", command=self.destroy).grid(row=0, column=1)
        self.save_button = ttk.Button(footer, text="Seçilenleri Sözlüğe Aktar", style="Primary.TButton", command=self.save_selected)
        self.save_button.grid(row=0, column=2, padx=(8, 0))

        for variable in [self.translation_var, self.pos_var, self.article_var]:
            variable.trace_add("write", self.on_local_editor_change)
        self.pos_var.trace_add("write", self.on_local_pos_change)
        for variable in [self.ai_translation_var, self.ai_pos_var, self.ai_article_var]:
            variable.trace_add("write", self.on_ai_editor_change)
        self.ai_pos_var.trace_add("write", self.on_ai_pos_change)
        for variable in [self.pair_translation_var, self.pair_pos_var, self.pair_article_var]:
            variable.trace_add("write", self.on_pair_editor_change)
        self.pair_pos_var.trace_add("write", self.on_pair_pos_change)
        self.local_missing_translation_only_var.trace_add("write", self.on_local_filter_change)
        self.local_has_translation_only_var.trace_add("write", self.on_local_filter_change)

        self.set_local_editor_state(False)
        self.set_ai_editor_state(False)
        self.set_pair_editor_state(False)
        self.refresh_save_button_state()
        self.after(80, lambda: self.set_initial_mode(self.initial_mode))
        if initial_url.strip():
            self.after(120, self.start_scan)

    def _build_new_words_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        list_box = ttk.LabelFrame(parent, text="Sözlükte olmayan kelimeler", padding=12)
        list_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_box.columnconfigure(0, weight=1)
        list_box.rowconfigure(3, weight=1)
        ttk.Label(list_box, textvariable=self.summary_var, style="Muted.TLabel", wraplength=540, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        ttk.Checkbutton(
            list_box,
            text="Türkçesi bulunmayanları göster",
            variable=self.local_missing_translation_only_var,
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Checkbutton(
            list_box,
            text="Türkçesi bulunanları göster",
            variable=self.local_has_translation_only_var,
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))
        tree_wrap = ttk.Frame(list_box)
        tree_wrap.grid(row=3, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_wrap,
            columns=("word", "translation", "pos", "source", "count", "state"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("word", text="Almanca")
        self.tree.heading("translation", text="Türkçe öneri")
        self.tree.heading("pos", text="Tür")
        self.tree.heading("source", text="Artikel/Cekim")
        self.tree.heading("count", text="Tekrar")
        self.tree.heading("state", text="Durum")
        self.tree.column("word", width=160, anchor="w")
        self.tree.column("translation", width=210, anchor="w")
        self.tree.column("pos", width=90, anchor="w")
        self.tree.column("source", width=120, anchor="w")
        self.tree.column("count", width=70, anchor="center")
        self.tree.column("state", width=80, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_local_tree_select)
        self.tree.bind("<Double-1>", self._on_local_tree_double_click)
        self.tree.bind("<Control-a>", lambda e: self._select_all_tree(self.tree))
        self.tree.bind("<Control-c>", lambda e: self._copy_tree_selection(self.tree))

        local_action_bar = ttk.Frame(list_box)
        local_action_bar.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(local_action_bar, text="Tümünü Seç", command=lambda: self._select_all_tree(self.tree)).pack(side="left", padx=(0, 4))
        ttk.Button(local_action_bar, text="Seçimi Kaldır", command=lambda: self.tree.selection_set()).pack(side="left", padx=(0, 4))
        ttk.Button(local_action_bar, text="Seçilenleri Ekle", command=lambda: self._bulk_set_state(self.tree, self.candidate_map, True)).pack(side="left", padx=(0, 4))
        ttk.Button(local_action_bar, text="Seçilenleri Atla", command=lambda: self._bulk_set_state(self.tree, self.candidate_map, False)).pack(side="left")

        editor = ttk.LabelFrame(parent, text="Seçili kelime", padding=12)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        ttk.Label(editor, text="Almanca", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.word_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(editor, text="Türkçe", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        self.translation_entry = ttk.Entry(editor, textvariable=self.translation_var)
        self.translation_entry.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Tür", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pos_combo = ttk.Combobox(editor, textvariable=self.pos_var, values=self.runtime["import_pos_choices"], state="readonly")
        self.pos_combo.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Artikel", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        self.article_combo = ttk.Combobox(editor, textvariable=self.article_var, values=["", "der", "die", "das"], state="readonly")
        self.article_combo.grid(row=3, column=1, sticky="ew", pady=6)
        self.include_check = ttk.Checkbutton(editor, text="Bu kelimeyi aktar", variable=self.include_var, command=self.update_current_candidate)
        self.include_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))

        info_box = ttk.Frame(editor, style="SoftPanel.TFrame", padding=12)
        info_box.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        info_box.columnconfigure(0, weight=1)
        ttk.Label(info_box, textvariable=self.source_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(info_box, textvariable=self.frequency_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(info_box, textvariable=self.form_note_var, style="Muted.TLabel", wraplength=300, justify="left").grid(row=2, column=0, sticky="w", pady=(10, 0))

    def _build_ai_meanings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        list_box = ttk.LabelFrame(parent, text="Eksik veya yeni anlamlar", padding=12)
        list_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_box.columnconfigure(0, weight=1)
        list_box.rowconfigure(1, weight=1)
        ttk.Label(list_box, textvariable=self.ai_summary_var, style="Muted.TLabel", wraplength=540, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        tree_wrap = ttk.Frame(list_box)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.ai_tree = ttk.Treeview(
            tree_wrap,
            columns=("word", "existing", "translation", "pos", "count", "state"),
            show="headings",
            selectmode="extended",
        )
        self.ai_tree.heading("word", text="Almanca")
        self.ai_tree.heading("existing", text="Mevcut")
        self.ai_tree.heading("translation", text="Önerilen anlam")
        self.ai_tree.heading("pos", text="Tür")
        self.ai_tree.heading("count", text="Tekrar")
        self.ai_tree.heading("state", text="Durum")
        self.ai_tree.column("word", width=150, anchor="w")
        self.ai_tree.column("existing", width=190, anchor="w")
        self.ai_tree.column("translation", width=210, anchor="w")
        self.ai_tree.column("pos", width=90, anchor="w")
        self.ai_tree.column("count", width=70, anchor="center")
        self.ai_tree.column("state", width=80, anchor="center")
        self.ai_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.ai_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.ai_tree.configure(yscrollcommand=tree_scroll.set)
        self.ai_tree.bind("<<TreeviewSelect>>", self.on_ai_tree_select)
        self.ai_tree.bind("<Double-1>", self._on_ai_tree_double_click)
        self.ai_tree.bind("<Control-a>", lambda e: self._select_all_tree(self.ai_tree))
        self.ai_tree.bind("<Control-c>", lambda e: self._copy_tree_selection(self.ai_tree))

        ai_action_bar = ttk.Frame(list_box)
        ai_action_bar.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(ai_action_bar, text="Tümünü Seç", command=lambda: self._select_all_tree(self.ai_tree)).pack(side="left", padx=(0, 4))
        ttk.Button(ai_action_bar, text="Seçimi Kaldır", command=lambda: self.ai_tree.selection_set()).pack(side="left", padx=(0, 4))
        ttk.Button(ai_action_bar, text="Seçilenleri Ekle", command=lambda: self._bulk_set_state(self.ai_tree, self.ai_candidate_map, True)).pack(side="left", padx=(0, 4))
        ttk.Button(ai_action_bar, text="Seçilenleri Atla", command=lambda: self._bulk_set_state(self.ai_tree, self.ai_candidate_map, False)).pack(side="left")

        editor = ttk.LabelFrame(parent, text="Seçili anlam", padding=12)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        ttk.Label(editor, text="Almanca", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.ai_word_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(editor, text="Mevcut", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.ai_existing_var, style="Muted.TLabel", wraplength=300, justify="left").grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(editor, text="Yeni anlam", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        self.ai_translation_entry = ttk.Entry(editor, textvariable=self.ai_translation_var)
        self.ai_translation_entry.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Tür", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        self.ai_pos_combo = ttk.Combobox(editor, textvariable=self.ai_pos_var, values=self.runtime["import_pos_choices"], state="readonly")
        self.ai_pos_combo.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Artikel", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 8))
        self.ai_article_combo = ttk.Combobox(editor, textvariable=self.ai_article_var, values=["", "der", "die", "das"], state="readonly")
        self.ai_article_combo.grid(row=4, column=1, sticky="ew", pady=6)
        self.ai_include_check = ttk.Checkbutton(editor, text="Bu anlamı ekle", variable=self.ai_include_var, command=self.update_current_ai_candidate)
        self.ai_include_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 4))

        info_box = ttk.Frame(editor, style="SoftPanel.TFrame", padding=12)
        info_box.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        info_box.columnconfigure(0, weight=1)
        ttk.Label(info_box, textvariable=self.ai_source_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(info_box, textvariable=self.ai_frequency_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(info_box, textvariable=self.ai_form_note_var, style="Muted.TLabel", wraplength=300, justify="left").grid(row=2, column=0, sticky="w", pady=(10, 0))

    def _build_parallel_text_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        ttk.Label(
            top,
            text="Bu sekme şu şekilde çalışır: soldaki kutuya Almanca metni, sağdaki kutuya onun Türkçe çevirisini yapıştırın. Sonra 'Kelimeleri Çıkar' düğmesine basın. Sistem Almanca kelimeleri ve Türkçe karşılıklarını çıkarıp aşağıda listeleyecek.",
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        source_box = ttk.LabelFrame(top, text="Almanca metin", padding=10)
        source_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        source_box.columnconfigure(0, weight=1)
        source_box.rowconfigure(0, weight=1)
        self.pair_source_text = tk.Text(source_box, height=8, wrap="word", relief="flat", padx=8, pady=8)
        self.pair_source_text.grid(row=0, column=0, sticky="nsew")
        source_scroll = ttk.Scrollbar(source_box, orient="vertical", command=self.pair_source_text.yview)
        source_scroll.grid(row=0, column=1, sticky="ns")
        self.pair_source_text.configure(yscrollcommand=source_scroll.set)

        target_box = ttk.LabelFrame(top, text="Türkçe çeviri", padding=10)
        target_box.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        target_box.columnconfigure(0, weight=1)
        target_box.rowconfigure(0, weight=1)
        self.pair_target_text = tk.Text(target_box, height=8, wrap="word", relief="flat", padx=8, pady=8)
        self.pair_target_text.grid(row=0, column=0, sticky="nsew")
        target_scroll = ttk.Scrollbar(target_box, orient="vertical", command=self.pair_target_text.yview)
        target_scroll.grid(row=0, column=1, sticky="ns")
        self.pair_target_text.configure(yscrollcommand=target_scroll.set)

        action_row = ttk.Frame(top)
        action_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        action_row.columnconfigure(0, weight=1)
        ttk.Label(action_row, textvariable=self.pair_summary_var, style="Muted.TLabel", wraplength=880, justify="left").grid(row=0, column=0, sticky="w")
        self.pair_scan_button = ttk.Button(action_row, text="Kelimeleri Çıkar", style="Primary.TButton", command=self.start_pair_scan)
        self.pair_scan_button.grid(row=0, column=1, padx=(10, 0))

        bottom = ttk.Frame(parent)
        bottom.grid(row=1, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=2)
        bottom.rowconfigure(0, weight=1)

        list_box = ttk.LabelFrame(bottom, text="Bulunan kelimeler ve Türkçe karşılıkları", padding=12)
        list_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_box.columnconfigure(0, weight=1)
        list_box.rowconfigure(1, weight=1)
        ttk.Label(list_box, textvariable=self.pair_summary_var, style="Muted.TLabel", wraplength=540, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        tree_wrap = ttk.Frame(list_box)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.pair_tree = ttk.Treeview(
            tree_wrap,
            columns=("word", "existing", "translation", "pos", "state"),
            show="headings",
            selectmode="browse",
        )
        self.pair_tree.heading("word", text="Almanca")
        self.pair_tree.heading("existing", text="Sözlükte olan")
        self.pair_tree.heading("translation", text="Bulunan Türkçe")
        self.pair_tree.heading("pos", text="Tür")
        self.pair_tree.heading("state", text="Durum")
        self.pair_tree.column("word", width=160, anchor="w")
        self.pair_tree.column("existing", width=200, anchor="w")
        self.pair_tree.column("translation", width=220, anchor="w")
        self.pair_tree.column("pos", width=90, anchor="w")
        self.pair_tree.column("state", width=80, anchor="center")
        self.pair_tree.grid(row=0, column=0, sticky="nsew")
        pair_tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.pair_tree.yview)
        pair_tree_scroll.grid(row=0, column=1, sticky="ns")
        self.pair_tree.configure(yscrollcommand=pair_tree_scroll.set)
        self.pair_tree.bind("<<TreeviewSelect>>", self.on_pair_tree_select)

        editor = ttk.LabelFrame(bottom, text="Seçili kelime", padding=12)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        ttk.Label(editor, text="Almanca", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.pair_word_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(editor, text="Sözlükte olan", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.pair_existing_var, style="Muted.TLabel", wraplength=300, justify="left").grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(editor, text="Türkçe", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pair_translation_entry = ttk.Entry(editor, textvariable=self.pair_translation_var)
        self.pair_translation_entry.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Tür", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pair_pos_combo = ttk.Combobox(editor, textvariable=self.pair_pos_var, values=self.runtime["import_pos_choices"], state="readonly")
        self.pair_pos_combo.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Artikel", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pair_article_combo = ttk.Combobox(editor, textvariable=self.pair_article_var, values=["", "der", "die", "das"], state="readonly")
        self.pair_article_combo.grid(row=4, column=1, sticky="ew", pady=6)
        self.pair_include_check = ttk.Checkbutton(editor, text="Bunu sözlüğe ekle", variable=self.pair_include_var, command=self.update_current_pair_candidate)
        self.pair_include_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 4))

        info_box = ttk.Frame(editor, style="SoftPanel.TFrame", padding=12)
        info_box.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        info_box.columnconfigure(0, weight=1)
        ttk.Label(info_box, textvariable=self.pair_source_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(info_box, textvariable=self.pair_context_var, style="Muted.TLabel", wraplength=300, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(info_box, textvariable=self.pair_form_note_var, style="Muted.TLabel", wraplength=300, justify="left").grid(row=2, column=0, sticky="w", pady=(10, 0))

    def bring_to_front(self) -> None:
        self.lift()
        self.focus_force()

    def destroy(self) -> None:
        if getattr(self.app, "import_dialog", None) is self:
            self.app.import_dialog = None
        super().destroy()

    def set_initial_url(self, url: str) -> None:
        self.url_var.set(url.strip())

    def set_initial_mode(self, mode: str = "url") -> None:
        if self.notebook is None:
            return
        normalized_mode = str(mode or "url").strip().lower()
        if normalized_mode == "ai" and self.ai_tab is not None:
            self.notebook.select(self.ai_tab)
            return
        if self.local_tab is not None:
            self.notebook.select(self.local_tab)

    def set_local_editor_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.pos_combo.configure(state=state)
        self.article_combo.configure(state=state if self.pos_var.get() == "isim" else "disabled")
        if self.translation_entry is not None:
            self.translation_entry.configure(state=entry_state)
        if self.include_check is not None:
            self.include_check.configure(state="normal" if enabled else "disabled")
        self.refresh_save_button_state()

    def set_ai_editor_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.ai_pos_combo.configure(state=state)
        self.ai_article_combo.configure(state=state if self.ai_pos_var.get() == "isim" else "disabled")
        if self.ai_translation_entry is not None:
            self.ai_translation_entry.configure(state=entry_state)
        if self.ai_include_check is not None:
            self.ai_include_check.configure(state="normal" if enabled else "disabled")
        self.refresh_save_button_state()

    def set_pair_editor_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.pair_pos_combo.configure(state=state)
        self.pair_article_combo.configure(state=state if self.pair_pos_var.get() == "isim" else "disabled")
        if self.pair_translation_entry is not None:
            self.pair_translation_entry.configure(state=entry_state)
        if self.pair_include_check is not None:
            self.pair_include_check.configure(state="normal" if enabled else "disabled")
        self.refresh_save_button_state()

    def refresh_save_button_state(self) -> None:
        if self.save_button is None:
            return
        any_selected = (
            any(item.get("ekle") for item in self.candidates)
            or any(item.get("ekle") for item in self.ai_candidates)
            or any(item.get("ekle") for item in self.pair_candidates)
        )
        self.save_button.configure(state="normal" if any_selected else "disabled")

    def get_visible_local_candidates(self) -> list[dict]:
        show_missing_only = self.local_missing_translation_only_var.get()
        show_with_translation_only = self.local_has_translation_only_var.get()
        if show_missing_only == show_with_translation_only:
            return list(self.candidates)
        if show_missing_only:
            return [item for item in self.candidates if not normalize_whitespace(item.get("turkce", ""))]
        return [item for item in self.candidates if normalize_whitespace(item.get("turkce", ""))]

    def refresh_local_summary(self) -> None:
        if not self.candidates:
            self.summary_var.set(self.local_summary_note)
            return
        selected_count = sum(1 for item in self.candidates if item.get("ekle"))
        visible_candidates = self.get_visible_local_candidates()
        message = f"{len(self.candidates)} yeni kelime hazır. Şu an {selected_count} tanesi aktarılacak."
        show_missing_only = self.local_missing_translation_only_var.get()
        show_with_translation_only = self.local_has_translation_only_var.get()
        if show_missing_only != show_with_translation_only:
            filter_label = "Türkçesi bulunmayanlar" if show_missing_only else "Türkçesi bulunanlar"
            message += f" Filtre açık: {filter_label}. {len(visible_candidates)} kayıt görünüyor."
        self.summary_var.set(message)

    def refresh_local_tree(self, preferred_id: str | None = None) -> None:
        if self.tree is None:
            return
        visible_candidates = self.get_visible_local_candidates()
        self.tree.delete(*self.tree.get_children())
        for candidate in visible_candidates:
            self.tree.insert("", "end", iid=candidate["id"], values=self.row_values(candidate))

        if not visible_candidates:
            return

        target_id = preferred_id if preferred_id and any(item["id"] == preferred_id for item in visible_candidates) else visible_candidates[0]["id"]
        self.tree.selection_set(target_id)
        self.load_candidate(target_id)

    def on_local_filter_change(self, *_args) -> None:
        preferred_id = self.current_candidate_id
        self.refresh_local_tree(preferred_id)
        self.refresh_local_summary()

    def _add_url_row(self, url: str = "") -> None:
        var = tk.StringVar(value=str(url).strip())
        self._url_vars.append(var)
        if len(self._url_vars) == 1:
            self.url_var = var
        row_frame = ttk.Frame(self._urls_inner)
        row_frame.pack(fill="x", pady=(0, 2))
        lbl = ttk.Label(row_frame, text=f"URL {len(self._url_vars)}", width=6, anchor="w")
        lbl.pack(side="left", padx=(0, 4))
        remove_btn = ttk.Button(row_frame, text="×", width=2,
                                command=lambda f=row_frame, v=var: self._remove_url_row(f, v))
        remove_btn.pack(side="right", padx=(4, 0))
        entry = ttk.Entry(row_frame, textvariable=var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.start_scan())
        entry.bind("<<Paste>>", lambda _event, v=var: self.after(20, lambda: self._check_and_split_urls(v)))
        if len(self._url_vars) == 1:
            remove_btn.configure(state="disabled")
        self._url_row_frames.append(row_frame)

    def _check_and_split_urls(self, source_var: tk.StringVar) -> None:
        text = source_var.get()
        urls = re.findall(r'https?://\S+', text)
        if len(urls) <= 1:
            return
        source_var.set(urls[0])
        existing = {v.get().strip() for v in self._url_vars}
        for url in urls[1:]:
            url = url.rstrip(".,;)")
            if url and url not in existing:
                self._add_url_row(url)
                existing.add(url)

    def _remove_url_row(self, row_frame: ttk.Frame, var: tk.StringVar) -> None:
        if len(self._url_vars) <= 1:
            return
        idx = self._url_vars.index(var)
        self._url_vars.pop(idx)
        self._url_row_frames.pop(idx)
        row_frame.destroy()
        self.url_var = self._url_vars[0]
        for i, (f, _v) in enumerate(zip(self._url_row_frames, self._url_vars)):
            lbl = next((c for c in f.winfo_children() if isinstance(c, ttk.Label)), None)
            if lbl:
                lbl.configure(text=f"URL {i + 1}")
            if i == 0:
                for c in f.winfo_children():
                    if isinstance(c, ttk.Button) and c.cget("text") == "×":
                        c.configure(state="disabled" if len(self._url_vars) == 1 else "normal")
        if len(self._url_vars) == 1:
            for c in self._url_row_frames[0].winfo_children():
                if isinstance(c, ttk.Button) and c.cget("text") == "×":
                    c.configure(state="disabled")

    def _test_api_connection(self) -> None:
        if self.is_scanning:
            return
        self._api_status_var.set("API test ediliyor...")
        self._api_test_button.configure(state="disabled")
        api_url = str(self.app.settings.get("llm_api_url", self.runtime["default_llm_model_api_url"]) or self.runtime["default_llm_model_api_url"]).strip()
        api_key = str(self.app.settings.get("llm_api_key", "") or os.getenv("LLM_API_KEY", "")).strip()
        model = str(self.app.settings.get("llm_model", self.runtime["default_llm_model"]) or self.runtime["default_llm_model"])

        def _worker():
            ok, msg = self.runtime["test_llm_connection"](api_url, api_key, model)
            self.after(0, lambda: self._on_api_test_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_api_test_done(self, ok: bool, msg: str) -> None:
        self._api_status_var.set(msg)
        self._api_test_button.configure(state="normal")

    def start_scan(self) -> None:
        if self.is_scanning:
            return
        urls = []
        for var in self._url_vars:
            raw = var.get().strip()
            if not raw:
                continue
            if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
                raw = f"https://{raw}"
                var.set(raw)
            urls.append(raw)
        if not urls:
            messagebox.showerror("Kelime Aktar", "Önce en az bir URL girin.", parent=self)
            return

        self._url_queue = list(urls)
        self._url_scan_idx = 0
        self._url_total = len(urls)
        self._total_saved = 0
        self._start_next_url_scan()

    def _start_next_url_scan(self) -> None:
        self._url_continue_pending = False
        if self._url_scan_idx >= self._url_total:
            if self._url_total > 1:
                self.status_var.set(f"Tüm URL'ler tamamlandı. Toplam {self._total_saved} kelime eklendi.")
            self.is_scanning = False
            if self.scan_button is not None:
                self.scan_button.configure(text="URL'yi Tara", command=self.start_scan, state="normal")
            return

        url = self._url_queue[self._url_scan_idx]
        self.is_scanning = True
        self.candidates = []
        self.candidate_map = {}
        self.current_candidate_id = None
        self.ai_candidates = []
        self.ai_candidate_map = {}
        self.current_ai_candidate_id = None
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
        if self.ai_tree is not None:
            self.ai_tree.delete(*self.ai_tree.get_children())
        self.set_local_editor_state(False)
        self.set_ai_editor_state(False)
        idx_label = f"[{self._url_scan_idx + 1}/{self._url_total}] " if self._url_total > 1 else ""
        self.status_var.set(f"{idx_label}Taranıyor: {url}")
        self.summary_var.set("Tarama sürüyor...")
        self.ai_summary_var.set("Model taraması hazırlanıyor...")
        if self.scan_button is not None:
            self.scan_button.configure(state="disabled")

        existing_terms = self.app.get_existing_german_terms()
        existing_meaning_index = self.runtime["build_existing_meaning_index"](self.app.records)
        api_url = str(self.app.settings.get("llm_api_url", self.runtime["default_llm_model_api_url"]) or self.runtime["default_llm_model_api_url"]).strip()
        api_key = str(self.app.settings.get("llm_api_key", "") or os.getenv("LLM_API_KEY", "")).strip()
        model = str(self.app.settings.get("llm_model", self.runtime["default_llm_model"]) or self.runtime["default_llm_model"])
        threading.Thread(
            target=self._scan_worker,
            args=(url, existing_terms, existing_meaning_index, api_url, api_key, model),
            daemon=True,
        ).start()

    def _scan_worker(self, url: str, existing_terms: set[str], existing_meaning_index: dict, api_url: str, api_key: str, model: str) -> None:
        idx_label = f"[{self._url_scan_idx + 1}/{self._url_total}] " if self._url_total > 1 else ""

        def progress_cb(current: int, total: int, message: str) -> None:
            self.after(0, lambda c=current, t=total, m=f"{idx_label}{message}": self._on_scan_progress(c, t, m))

        try:
            final_url, local_cands, ai_cands, note, seen_existing = self.runtime["collect_url_import_scan"](
                url, existing_terms, existing_meaning_index, api_url, api_key, model,
                progress_callback=progress_cb,
            )
            frekans_updated = 0
            if seen_existing and "increment_frekans_for_seen_terms" in self.runtime:
                try:
                    frekans_updated = self.runtime["increment_frekans_for_seen_terms"](seen_existing)
                except Exception as frek_exc:
                    print(f"[frekans] increment hatası: {frek_exc}", flush=True)
            self.after(0, lambda fu=frekans_updated: self._on_single_url_done(final_url, local_cands, ai_cands, note, fu))
        except Exception as exc:
            self.after(0, lambda: self._on_single_url_failed(str(exc)))

    def _on_scan_progress(self, current: int, total: int, message: str) -> None:
        self._api_status_var.set(f"[{current}/{total}] {message}")
        self.status_var.set(f"Taranıyor... Parça {current}/{total} — {message}")

    def on_scan_failed(self, message: str) -> None:
        self.is_scanning = False
        if self.scan_button is not None:
            self.scan_button.configure(state="normal")
        self.status_var.set(f"Tarama başarısız oldu. {message}")
        self.summary_var.set("Yeni kelimeler hazırlanamadı.")
        self.ai_summary_var.set("Model anlam taramasi tamamlanamadi.")

    def _on_single_url_failed(self, message: str) -> None:
        idx_label = f"URL {self._url_scan_idx + 1}/{self._url_total}: " if self._url_total > 1 else ""
        self._api_status_var.set(f"{idx_label}Hata — {message[:120]}")
        self._url_scan_idx += 1
        if self._url_total > 1:
            self._start_next_url_scan()
        else:
            self.on_scan_failed(message)

    def _on_single_url_done(self, final_url: str, local_cands: list[dict], ai_cands: list[dict], note: str, frekans_updated: int = 0) -> None:
        if frekans_updated:
            self.app.reload_data()
        self.on_scan_complete(final_url, local_cands, ai_cands, note)
        if self._url_total <= 1:
            return
        # Çoklu URL modu: otomatik veya bekleme
        count = len(local_cands) + len(ai_cands)
        url_label = f"URL {self._url_scan_idx + 1}/{self._url_total}"
        self._url_scan_idx += 1
        if count == 0:
            # Kelime bulunamadı, sormadan sonraki URL'ye geç
            self.after(300, self._start_next_url_scan)
            return
        if self.auto_add_var.get():
            saved = self._save_silently()
            self._total_saved += saved
            self._api_status_var.set(f"{url_label} tamamlandı — {saved} kelime eklendi. Sonraki taranıyor...")
            self.after(600, self._start_next_url_scan)
        else:
            # Düzenleme bekleme modu: butonu "Sonraki URL'ye Geç" yap
            self._url_continue_pending = True
            remaining = self._url_total - self._url_scan_idx
            self._api_status_var.set(
                f"{url_label} tamamlandı — {len(local_cands)} yeni kelime, {len(ai_cands)} eksik anlam. "
                f"Düzenleyin, hazır olunca 'Sonraki URL'ye Geç' düğmesine basın. ({remaining} URL kaldı)"
            )
            if self.scan_button is not None:
                self.scan_button.configure(
                    text="Sonraki URL'ye Geç →",
                    style="Primary.TButton",
                    state="normal",
                    command=self._continue_url_queue,
                )

    def _continue_url_queue(self) -> None:
        """Kullanıcı düzenlemeyi bitirip 'Sonraki URL'ye Geç' butonuna bastığında çağrılır."""
        self._url_continue_pending = False
        if self.scan_button is not None:
            self.scan_button.configure(text="URL'yi Tara", command=self.start_scan)
        self._start_next_url_scan()

    def _save_silently(self) -> int:
        """Onay kutusu göstermeden, pencereyi kapatmadan seçili kelimeleri kaydeder."""
        selected = [item for item in [*self.candidates, *self.ai_candidates, *self.pair_candidates] if item.get("ekle")]
        if not selected:
            return 0
        payloads = [self.build_save_payload(item) for item in selected]
        conflicts = self.find_duplicate_conflicts(payloads)
        if conflicts:
            payloads = [p for p in payloads if p.get("almanca") not in conflicts]
        count = 0
        for payload in payloads:
            validation = self.runtime["validate_user_entry"](payload)
            if validation.get("status") == "error":
                continue
            self.runtime["save_user_entry"](payload)
            count += 1
        if count:
            self.app.reload_data()
        return count

    def on_scan_complete(self, final_url: str, candidates: list[dict], ai_candidates: list[dict], ai_note: str) -> None:
        self.is_scanning = False
        if self.scan_button is not None:
            self.scan_button.configure(state="normal")

        self.candidates = []
        self.candidate_map = {}
        self.ai_candidates = []
        self.ai_candidate_map = {}
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
        if self.ai_tree is not None:
            self.ai_tree.delete(*self.ai_tree.get_children())

        for candidate in candidates:
            candidate["kaynak_url"] = final_url
            candidate["not"] = f"URL'den aktarıldı: {final_url}"
            self.candidates.append(candidate)
            self.candidate_map[candidate["id"]] = candidate

        for candidate in ai_candidates:
            candidate["kaynak_url"] = final_url
            self.ai_candidates.append(candidate)
            self.ai_candidate_map[candidate["id"]] = candidate
            if self.ai_tree is not None:
                self.ai_tree.insert("", "end", iid=candidate["id"], values=self.ai_row_values(candidate))

        # Surface AI failure prominently if it happened
        ai_failed = ai_note and ai_note.startswith("AI taraması başarısız")
        if ai_failed:
            self._api_status_var.set(f"⚠ {ai_note}")

        if not self.candidates and not self.ai_candidates:
            self.status_var.set("Bu URL için yeni kelime veya eksik anlam bulunamadı.")
            self.ai_summary_var.set(ai_note or "AI sekmesinde eklenecek anlam çıkmadı.")
            self.refresh_save_button_state()
            return

        local_count = sum(1 for item in self.candidates if item.get("ekle"))
        ai_count = sum(1 for item in self.ai_candidates if item.get("ekle"))
        if ai_failed:
            self.status_var.set(f"{len(self.candidates)} kelime bulundu (AI başarısız — WikDict ile tarandı).")
        else:
            self.status_var.set(f"{len(self.candidates)} yeni kelime ve {len(self.ai_candidates)} eksik anlam hazır.")
        self.summary_var.set(f"{len(self.candidates)} yeni kelime hazır. Şu an {local_count} tanesi aktarılacak.")
        self.ai_summary_var.set(
            ai_note if not self.ai_candidates else f"{len(self.ai_candidates)} eksik anlam hazır. Şu an {ai_count} tanesi aktarılacak."
        )
        self.set_local_editor_state(bool(self.candidates))
        self.set_ai_editor_state(bool(self.ai_candidates))
        self.on_local_filter_change()
        visible_local_candidates = self.get_visible_local_candidates()
        if self.tree is not None and visible_local_candidates:
            first_id = visible_local_candidates[0]["id"]
            self.tree.selection_set(first_id)
            self.load_candidate(first_id)
        if self.ai_tree is not None and self.ai_candidates:
            first_id = self.ai_candidates[0]["id"]
            self.ai_tree.selection_set(first_id)
            self.load_ai_candidate(first_id)
        self.refresh_save_button_state()

    def start_pair_scan(self) -> None:
        if self.is_pair_scanning:
            return
        german_text = self.get_text_widget_value(self.pair_source_text)
        turkish_text = self.get_text_widget_value(self.pair_target_text)
        if not german_text or not turkish_text:
            messagebox.showerror("Metin Eşleme", "Önce Almanca metni ve Türkçe çeviriyi girin.", parent=self)
            return

        self.is_pair_scanning = True
        self.pair_candidates = []
        self.pair_candidate_map = {}
        self.current_pair_candidate_id = None
        if self.pair_tree is not None:
            self.pair_tree.delete(*self.pair_tree.get_children())
        self.set_pair_editor_state(False)
        self.pair_summary_var.set("Metin eşleme hazırlanıyor...")
        self.status_var.set("Almanca metin ve Türkçe çeviri eşleştiriliyor. Eksik kayıtlar hazırlanıyor...")
        if self.pair_scan_button is not None:
            self.pair_scan_button.configure(state="disabled")

        existing_meaning_index = self.runtime["build_existing_meaning_index"](self.app.records)
        api_url = str(self.app.settings.get("llm_api_url", self.runtime["default_llm_model_api_url"]) or self.runtime["default_llm_model_api_url"]).strip()
        api_key = str(self.app.settings.get("llm_api_key", "") or os.getenv("LLM_API_KEY", "")).strip()
        model = str(self.app.settings.get("llm_model", self.runtime["default_llm_model"]) or self.runtime["default_llm_model"])
        worker = threading.Thread(
            target=self._pair_scan_worker,
            args=(german_text, turkish_text, existing_meaning_index, api_url, api_key, model),
            daemon=True,
        )
        worker.start()

    def _pair_scan_worker(self, german_text: str, turkish_text: str, existing_meaning_index: dict, api_url: str, api_key: str, model: str) -> None:
        try:
            payload = self.runtime["collect_parallel_text_import_scan"](german_text, turkish_text, existing_meaning_index, api_url, api_key, model)
            self.after(0, lambda: self.on_pair_scan_complete(*payload))
        except Exception as exc:
            self.after(0, lambda: self.on_pair_scan_failed(str(exc)))

    def on_pair_scan_failed(self, message: str) -> None:
        self.is_pair_scanning = False
        if self.pair_scan_button is not None:
            self.pair_scan_button.configure(state="normal")
        self.status_var.set(f"Metin eşleme başarısız oldu. {message}")
        self.pair_summary_var.set("Metin eşleme tamamlanamadı.")

    def on_pair_scan_complete(self, candidates: list[dict], note: str) -> None:
        self.is_pair_scanning = False
        if self.pair_scan_button is not None:
            self.pair_scan_button.configure(state="normal")

        self.pair_candidates = []
        self.pair_candidate_map = {}
        if self.pair_tree is not None:
            self.pair_tree.delete(*self.pair_tree.get_children())

        for candidate in candidates:
            self.pair_candidates.append(candidate)
            self.pair_candidate_map[candidate["id"]] = candidate
            if self.pair_tree is not None:
                self.pair_tree.insert("", "end", iid=candidate["id"], values=self.pair_row_values(candidate))

        if not self.pair_candidates:
            self.status_var.set(note)
            self.pair_summary_var.set(note)
            self.set_pair_editor_state(False)
            self.refresh_save_button_state()
            return

        selected_count = sum(1 for item in self.pair_candidates if item.get("ekle"))
        self.status_var.set(f"{len(self.pair_candidates)} yeni kelime veya eksik anlam metin eşleme ile hazırlandı.")
        self.pair_summary_var.set(f"{len(self.pair_candidates)} kayıt hazır. Şu an {selected_count} tanesi aktarılacak. {note}")
        self.set_pair_editor_state(True)
        if self.pair_tree is not None:
            first_id = self.pair_candidates[0]["id"]
            self.pair_tree.selection_set(first_id)
            self.load_pair_candidate(first_id)
        self.refresh_save_button_state()

    def _extra_info_cell(self, candidate: dict) -> str:
        """Isimler icin artikel, fiiller icin cekim ozeti dondurur."""
        pos = str(candidate.get("tur", "")).strip().lower()
        if pos == "isim":
            art = candidate.get("artikel", "").strip()
            return art if art else "-"
        if pos == "fiil":
            cekimler = candidate.get("cekimler") or {}
            praesens = cekimler.get("präsens") or {}
            er_form = ""
            if isinstance(praesens, dict):
                er_form = (praesens.get("er/sie/es") or praesens.get("er") or "").strip()
            perfekt = str(cekimler.get("perfekt") or "").strip()
            parts = []
            if er_form:
                parts.append(er_form)
            if perfekt:
                parts.append(perfekt)
            return "  |  ".join(parts) if parts else "-"
        return ""

    # ------------------------------------------------------------------
    # Tree helpers: select-all, copy, double-click toggle
    # ------------------------------------------------------------------

    def _select_all_tree(self, tree: ttk.Treeview) -> None:
        tree.selection_set(tree.get_children())

    def _copy_tree_selection(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            return
        rows = []
        for iid in selected:
            vals = tree.item(iid, "values")
            rows.append("\t".join(str(v) for v in vals))
        text = "\n".join(rows)
        self.clipboard_clear()
        self.clipboard_append(text)

    def _bulk_set_state(self, tree: ttk.Treeview, candidate_map: dict, ekle: bool) -> None:
        selected = tree.selection()
        if not selected:
            return
        is_local = tree is self.tree
        for iid in selected:
            candidate = candidate_map.get(iid)
            if candidate is None:
                continue
            candidate["ekle"] = ekle
            if is_local:
                tree.item(iid, values=self.row_values(candidate))
            else:
                tree.item(iid, values=self.ai_row_values(candidate))
        if is_local:
            self.refresh_local_summary()
        self.refresh_save_button_state()

    def _on_local_tree_double_click(self, event) -> None:
        if self.tree is None:
            return
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        candidate = self.candidate_map.get(iid)
        if candidate is None:
            return
        candidate["ekle"] = not candidate.get("ekle", True)
        self.tree.item(iid, values=self.row_values(candidate))
        if self.current_candidate_id == iid:
            self.include_var.set(candidate["ekle"])
        self.refresh_local_summary()
        self.refresh_save_button_state()

    def _on_ai_tree_double_click(self, event) -> None:
        if self.ai_tree is None:
            return
        region = self.ai_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        iid = self.ai_tree.identify_row(event.y)
        if not iid:
            return
        candidate = self.ai_candidate_map.get(iid)
        if candidate is None:
            return
        candidate["ekle"] = not candidate.get("ekle", True)
        self.ai_tree.item(iid, values=self.ai_row_values(candidate))
        if self.current_ai_candidate_id == iid:
            self.ai_include_var.set(candidate["ekle"])
        self.refresh_save_button_state()

    def row_values(self, candidate: dict) -> tuple:
        return (
            candidate.get("almanca", ""),
            candidate.get("turkce", ""),
            candidate.get("tur", ""),
            self._extra_info_cell(candidate),
            candidate.get("frekans", 0),
            "Ekle" if candidate.get("ekle", True) else "Atla",
        )

    def ai_row_values(self, candidate: dict) -> tuple:
        return (
            candidate.get("almanca", ""),
            candidate.get("mevcut_turkce", "") or "-",
            candidate.get("turkce", ""),
            candidate.get("tur", ""),
            candidate.get("frekans", 0),
            "Ekle" if candidate.get("ekle", True) else "Atla",
        )

    def pair_row_values(self, candidate: dict) -> tuple:
        return (
            candidate.get("almanca", ""),
            candidate.get("mevcut_turkce", "") or "-",
            candidate.get("turkce", ""),
            candidate.get("tur", ""),
            "Ekle" if candidate.get("ekle", True) else "Atla",
        )

    def on_local_tree_select(self, _event=None) -> None:
        if self.tree is None:
            return
        selection = self.tree.selection()
        if selection:
            self.load_candidate(selection[0])

    def on_ai_tree_select(self, _event=None) -> None:
        if self.ai_tree is None:
            return
        selection = self.ai_tree.selection()
        if selection:
            self.load_ai_candidate(selection[0])

    def on_pair_tree_select(self, _event=None) -> None:
        if self.pair_tree is None:
            return
        selection = self.pair_tree.selection()
        if selection:
            self.load_pair_candidate(selection[0])

    def load_candidate(self, candidate_id: str) -> None:
        candidate = self.candidate_map.get(candidate_id)
        if not candidate:
            return
        self.current_candidate_id = candidate_id
        self.form_loading = True
        self.word_var.set(candidate.get("almanca", "-"))
        self.translation_var.set(candidate.get("turkce", ""))
        self.pos_var.set(candidate.get("tur", "belirsiz") or "belirsiz")
        self.article_var.set(candidate.get("artikel", ""))
        self.include_var.set(bool(candidate.get("ekle", True)))
        self.source_var.set(f"Kaynak önerisi: {candidate.get('kaynak_etiketi', 'Öneri yok')}")
        self.frequency_var.set(f"Metinde tekrar: {candidate.get('frekans', 0)}")
        self.form_note_var.set(
            "Kaynak sayfadaki gerçek kullanım cümlesi ve otomatik Türkçe çevirisi örnekler bölümüne kaydedilecek."
            if candidate.get("ornek_almanca")
            else "Çeviri yerel kaynaktan önerildi. Kaydetmeden önce dilediğiniz gibi düzenleyebilirsiniz."
        )
        self.on_local_pos_change()
        self.form_loading = False

    def load_ai_candidate(self, candidate_id: str) -> None:
        candidate = self.ai_candidate_map.get(candidate_id)
        if not candidate:
            return
        self.current_ai_candidate_id = candidate_id
        self.ai_form_loading = True
        self.ai_word_var.set(candidate.get("almanca", "-"))
        self.ai_existing_var.set(f"Mevcut anlamlar: {candidate.get('mevcut_turkce', '-') or '-'}")
        self.ai_translation_var.set(candidate.get("turkce", ""))
        self.ai_pos_var.set(candidate.get("tur", "belirsiz") or "belirsiz")
        self.ai_article_var.set(candidate.get("artikel", ""))
        self.ai_include_var.set(bool(candidate.get("ekle", True)))
        self.ai_source_var.set(f"Model: {candidate.get('kaynak_etiketi', '-')}")
        self.ai_frequency_var.set(f"Metinde tekrar: {candidate.get('frekans', 0)}")
        self.ai_form_note_var.set("Bu anlam AI tarafından bağlama göre önerildi. Kaydetmeden önce düzenleyebilirsiniz.")
        self.on_ai_pos_change()
        self.ai_form_loading = False

    def load_pair_candidate(self, candidate_id: str) -> None:
        candidate = self.pair_candidate_map.get(candidate_id)
        if not candidate:
            return
        self.current_pair_candidate_id = candidate_id
        self.pair_form_loading = True
        self.pair_word_var.set(candidate.get("almanca", "-"))
        self.pair_existing_var.set(f"Mevcut anlamlar: {candidate.get('mevcut_turkce', '-') or '-'}")
        self.pair_translation_var.set(candidate.get("turkce", ""))
        self.pair_pos_var.set(candidate.get("tur", "belirsiz") or "belirsiz")
        self.pair_article_var.set(candidate.get("artikel", ""))
        self.pair_include_var.set(bool(candidate.get("ekle", True)))
        self.pair_source_var.set(f"Model: {candidate.get('kaynak_etiketi', '-')}")
        german_sentence = candidate.get("ornek_almanca", "")
        turkish_sentence = candidate.get("ornek_turkce", "")
        if german_sentence or turkish_sentence:
            self.pair_context_var.set(f"Bağlam: DE: {german_sentence or '-'}\nTR: {turkish_sentence or '-'}")
        else:
            self.pair_context_var.set("Bağlam: Bu kayıt için cümle bilgisi yok.")
        self.pair_form_note_var.set("Bu kayıt Almanca metin ile verdiğiniz Türkçe çeviriden eşleştirilerek önerildi.")
        self.on_pair_pos_change()
        self.pair_form_loading = False

    def on_local_editor_change(self, *_args) -> None:
        if not self.form_loading:
            self.update_current_candidate()

    def on_ai_editor_change(self, *_args) -> None:
        if not self.ai_form_loading:
            self.update_current_ai_candidate()

    def on_pair_editor_change(self, *_args) -> None:
        if not self.pair_form_loading:
            self.update_current_pair_candidate()

    def on_local_pos_change(self, *_args) -> None:
        is_noun = self.pos_var.get() == "isim"
        if not is_noun and self.article_var.get():
            self.article_var.set("")
        self.article_combo.configure(state="readonly" if is_noun and self.current_candidate_id else "disabled")

    def on_ai_pos_change(self, *_args) -> None:
        is_noun = self.ai_pos_var.get() == "isim"
        if not is_noun and self.ai_article_var.get():
            self.ai_article_var.set("")
        self.ai_article_combo.configure(state="readonly" if is_noun and self.current_ai_candidate_id else "disabled")

    def on_pair_pos_change(self, *_args) -> None:
        is_noun = self.pair_pos_var.get() == "isim"
        if not is_noun and self.pair_article_var.get():
            self.pair_article_var.set("")
        self.pair_article_combo.configure(state="readonly" if is_noun and self.current_pair_candidate_id else "disabled")

    def update_current_candidate(self) -> None:
        candidate = self.candidate_map.get(self.current_candidate_id or "")
        if not candidate:
            return
        candidate["turkce"] = self.translation_var.get().strip()
        candidate["tur"] = self.pos_var.get().strip() or "belirsiz"
        candidate["artikel"] = self.article_var.get().strip() if candidate["tur"] == "isim" else ""
        candidate["ekle"] = bool(self.include_var.get())
        self.refresh_local_tree(candidate["id"])
        self.refresh_local_summary()
        self.refresh_save_button_state()

    def update_current_ai_candidate(self) -> None:
        candidate = self.ai_candidate_map.get(self.current_ai_candidate_id or "")
        if not candidate:
            return
        candidate["turkce"] = self.ai_translation_var.get().strip()
        candidate["tur"] = self.ai_pos_var.get().strip() or "belirsiz"
        candidate["artikel"] = self.ai_article_var.get().strip() if candidate["tur"] == "isim" else ""
        candidate["ekle"] = bool(self.ai_include_var.get())
        if self.ai_tree is not None:
            self.ai_tree.item(candidate["id"], values=self.ai_row_values(candidate))
        self.refresh_save_button_state()

    def update_current_pair_candidate(self) -> None:
        candidate = self.pair_candidate_map.get(self.current_pair_candidate_id or "")
        if not candidate:
            return
        candidate["turkce"] = self.pair_translation_var.get().strip()
        candidate["tur"] = self.pair_pos_var.get().strip() or "belirsiz"
        candidate["artikel"] = self.pair_article_var.get().strip() if candidate["tur"] == "isim" else ""
        candidate["ekle"] = bool(self.pair_include_var.get())
        if self.pair_tree is not None:
            self.pair_tree.item(candidate["id"], values=self.pair_row_values(candidate))
        self.refresh_save_button_state()

    def get_text_widget_value(self, widget: tk.Text | None) -> str:
        if widget is None:
            return ""
        return widget.get("1.0", "end").strip()

    def build_save_payload(self, item: dict) -> dict:
        return {
            "almanca": item.get("almanca", "").strip(),
            "artikel": item.get("artikel", "").strip(),
            "turkce": item.get("turkce", "").strip(),
            "tur": item.get("tur", "").strip(),
            "aciklama_turkce": "",
            "ornek_almanca": item.get("ornek_almanca", ""),
            "ornek_turkce": item.get("ornek_turkce", ""),
            "ornekler": item.get("ornekler", []),
            "kaynak": item.get("kaynak", "kullanici-ekleme"),
            "not": item.get("not", ""),
            "kaynak_url": item.get("kaynak_url", ""),
            "ceviri_kaynaklari": item.get("ceviri_kaynaklari", []),
            "ceviri_durumu": item.get("ceviri_durumu", "kullanici-eklemesi"),
            "ceviri_inceleme_notu": item.get("ceviri_inceleme_notu", ""),
        }

    def find_duplicate_conflicts(self, payloads: list[dict]) -> list[str]:
        existing_meaning_index = self.runtime["build_existing_meaning_index"](self.app.records)
        by_word = existing_meaning_index.get("by_word", {})
        by_word_pos = existing_meaning_index.get("by_word_pos", {})
        selected_seen: set[tuple[str, str, str]] = set()
        conflicts: list[str] = []

        for payload in payloads:
            word = payload.get("almanca", "").strip()
            translation = payload.get("turkce", "").strip()
            pos = payload.get("tur", "").strip() or "belirsiz"
            word_key = normalize_import_term_for_compare(word)
            pos_key = normalize_text_for_compare(pos)
            variants = split_translation_variants_for_compare(translation)
            if not word_key or not variants:
                continue

            for variant in variants:
                meaning_key = normalize_text_for_compare(variant)
                if not meaning_key:
                    continue
                if meaning_key in by_word_pos.get((word_key, pos_key), set()) or meaning_key in by_word.get(word_key, set()):
                    conflicts.append(f"{word} -> {variant} (zaten sozlukte var)")
                    break
                dedupe_key = (word_key, pos_key, meaning_key)
                if dedupe_key in selected_seen:
                    conflicts.append(f"{word} -> {variant} (secili listede tekrar ediyor)")
                    break
                selected_seen.add(dedupe_key)

        return conflicts

    def build_confirmation_message(self, selected: list[dict]) -> str:
        preview_lines: list[str] = []
        for item in selected[:12]:
            article = item.get("artikel", "").strip()
            word = item.get("almanca", "").strip()
            translation = item.get("turkce", "").strip()
            label = " ".join(part for part in [article, word] if part)
            preview_lines.append(f"- {label} -> {translation}")
        if len(selected) > 12:
            preview_lines.append(f"- ... ve {len(selected) - 12} kayit daha")
        return "Su kayitlar sozluge eklenecek:\n\n" + "\n".join(preview_lines) + "\n\nEkleyeyim mi?"

    def save_selected(self) -> None:
        selected = [item for item in [*self.candidates, *self.ai_candidates, *self.pair_candidates] if item.get("ekle")]
        if not selected:
            messagebox.showinfo("Kelime Aktar", "Aktarılacak kayıt seçili değil.", parent=self)
            return

        payloads = [self.build_save_payload(item) for item in selected]

        first_key = None
        for payload in payloads:
            validation = self.runtime["validate_user_entry"](payload)
            if validation.get("status") == "error":
                messagebox.showerror("Kelime Aktar", validation.get("note", "Bu kayıt kaydedilemedi."), parent=self)
                return

        conflicts = self.find_duplicate_conflicts(payloads)
        if conflicts:
            preview = "\n".join(f"- {item}" for item in conflicts[:10])
            extra = ""
            if len(conflicts) > 10:
                extra = f"\n- ... ve {len(conflicts) - 10} cakisma daha"
            messagebox.showerror(
                "Kelime Aktar",
                "Bazi secili kayitlar zaten sozlukte var veya secili listede tekrar ediyor:\n\n"
                f"{preview}{extra}\n\nLutfen bu kayitlari duzeltin ya da isaretlerini kaldirin.",
                parent=self,
            )
            return

        if not messagebox.askyesno("Kelime Aktar Onayi", self.build_confirmation_message(selected), parent=self):
            return

        for payload in payloads:
            saved = self.runtime["save_user_entry"](payload)
            if first_key is None:
                first_key = self.runtime["record_key"](saved)

        self.app.reload_data(select_key=first_key)

        if self._url_continue_pending:
            # Çoklu URL modunda: kaydet ama pencereyi kapatma, sonraki URL'ye geç
            self._total_saved += len(selected)
            remaining = self._url_total - self._url_scan_idx
            self._api_status_var.set(
                f"{len(selected)} kayıt eklendi. "
                + (f"{remaining} URL daha var — sonraki taranıyor..." if remaining > 0 else "Tüm URL'ler tamamlandı.")
            )
            self._continue_url_queue()
        else:
            messagebox.showinfo("Kelime Aktar", f"{len(selected)} kayıt sözlüğe eklendi.", parent=self)
            self.destroy()
