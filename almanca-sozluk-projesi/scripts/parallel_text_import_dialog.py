from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from url_ai_import_dialog import (
        normalize_import_term_for_compare,
        normalize_text_for_compare,
        normalize_whitespace,
        split_translation_variants_for_compare,
    )
except ModuleNotFoundError:
    from scripts.url_ai_import_dialog import (
        normalize_import_term_for_compare,
        normalize_text_for_compare,
        normalize_whitespace,
        split_translation_variants_for_compare,
    )


def format_confidence(value: object) -> str:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return "-"
    confidence = max(0.0, min(1.0, confidence))
    return f"%{round(confidence * 100)}"


class ParallelTextImportDialog(tk.Toplevel):
    def __init__(self, app, runtime: dict) -> None:
        super().__init__(app)
        self.app = app
        self.runtime = runtime
        self.title("Metin Esleme ile Kelime Cikar")
        self.transient(app)
        self.grab_set()
        self.geometry("1160x820")
        self.minsize(1020, 720)

        self.status_var = tk.StringVar(
            value=(
                "Soldaki alana Almanca metni, sagdaki alana ayni metnin Turkce cevirisini girin. "
                "Sistem iki metni karsilastirip sadece yeterince destekli eslesmeleri onerir. "
                "Yerel model endpointi yoksa yerel sozluk ipuclariyla calisir."
            )
        )
        self.summary_var = tk.StringVar(
            value="1. Almanca metni girin. 2. Turkce ceviriyi girin. 3. 'Metinleri Karsilastir' dugmesine basin."
        )
        self.word_var = tk.StringVar(value="-")
        self.existing_var = tk.StringVar(value="Mevcut anlamlar: -")
        self.source_var = tk.StringVar(value="Kaynak: -")
        self.confidence_var = tk.StringVar(value="Guven: -")
        self.evidence_var = tk.StringVar(value="Eslesme kaniti: -")
        self.context_var = tk.StringVar(value="Baglam: -")
        self.include_var = tk.BooleanVar(value=True)
        self.translation_var = tk.StringVar()
        self.pos_var = tk.StringVar(value="belirsiz")
        self.article_var = tk.StringVar(value="")
        self.form_note_var = tk.StringVar(
            value="Bu ekran sadece paralel metin eslemeden gelen adaylara odaklanir. Kaydetmeden once duzenleyebilirsiniz."
        )

        self.tree: ttk.Treeview | None = None
        self.translation_entry: ttk.Entry | None = None
        self.include_check: ttk.Checkbutton | None = None
        self.source_text: tk.Text | None = None
        self.target_text: tk.Text | None = None
        self.context_text: tk.Text | None = None
        self.scan_button: ttk.Button | None = None
        self.save_button: ttk.Button | None = None

        self.is_scanning = False
        self.form_loading = False
        self.current_candidate_id: str | None = None
        self.candidates: list[dict] = []
        self.candidate_map: dict[str, dict] = {}

        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="Metin Esleme ile Kelime Cikar", style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text=(
                "Bu pencere, Almanca kaynak metin ile onun Turkce cevirisini karsilastirir. "
                "Yerel/uyumlu model endpointi varsa daha guclu esleme kullanir, yoksa yerel sozluk ipuclariyla devam eder. "
                "Zayif veya belirsiz eslesmeler otomatik elenir; sozluge sadece makul adaylar duser."
            ),
            style="Muted.TLabel",
            wraplength=1040,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))

        shell = ttk.Frame(frame)
        shell.grid(row=2, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        top = ttk.Frame(shell)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        source_box = ttk.LabelFrame(top, text="Almanca metin", padding=10)
        source_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        source_box.columnconfigure(0, weight=1)
        source_box.rowconfigure(0, weight=1)
        self.source_text = tk.Text(source_box, height=10, wrap="word", relief="flat", padx=8, pady=8)
        self.source_text.grid(row=0, column=0, sticky="nsew")
        source_scroll = ttk.Scrollbar(source_box, orient="vertical", command=self.source_text.yview)
        source_scroll.grid(row=0, column=1, sticky="ns")
        self.source_text.configure(yscrollcommand=source_scroll.set)

        target_box = ttk.LabelFrame(top, text="Turkce ceviri", padding=10)
        target_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        target_box.columnconfigure(0, weight=1)
        target_box.rowconfigure(0, weight=1)
        self.target_text = tk.Text(target_box, height=10, wrap="word", relief="flat", padx=8, pady=8)
        self.target_text.grid(row=0, column=0, sticky="nsew")
        target_scroll = ttk.Scrollbar(target_box, orient="vertical", command=self.target_text.yview)
        target_scroll.grid(row=0, column=1, sticky="ns")
        self.target_text.configure(yscrollcommand=target_scroll.set)

        action_row = ttk.Frame(top)
        action_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        action_row.columnconfigure(0, weight=1)
        ttk.Label(action_row, textvariable=self.status_var, style="Meta.TLabel", wraplength=880, justify="left").grid(
            row=0, column=0, sticky="w"
        )
        self.scan_button = ttk.Button(
            action_row,
            text="Metinleri Karsilastir",
            style="Primary.TButton",
            command=self.start_scan,
        )
        self.scan_button.grid(row=0, column=1, padx=(10, 0))

        bottom = ttk.Frame(shell)
        bottom.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=2)
        bottom.rowconfigure(0, weight=1)

        list_box = ttk.LabelFrame(bottom, text="Bulunan kelimeler ve anlamlar", padding=12)
        list_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_box.columnconfigure(0, weight=1)
        list_box.rowconfigure(1, weight=1)
        ttk.Label(list_box, textvariable=self.summary_var, style="Muted.TLabel", wraplength=540, justify="left").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        tree_wrap = ttk.Frame(list_box)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_wrap,
            columns=("word", "existing", "translation", "pos", "confidence", "state"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("word", text="Almanca")
        self.tree.heading("existing", text="Sozlukte olan")
        self.tree.heading("translation", text="Bulunan Turkce")
        self.tree.heading("pos", text="Tur")
        self.tree.heading("confidence", text="Guven")
        self.tree.heading("state", text="Durum")
        self.tree.column("word", width=150, anchor="w")
        self.tree.column("existing", width=190, anchor="w")
        self.tree.column("translation", width=220, anchor="w")
        self.tree.column("pos", width=90, anchor="w")
        self.tree.column("confidence", width=80, anchor="center")
        self.tree.column("state", width=80, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        editor = ttk.LabelFrame(bottom, text="Secili kelime", padding=12)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(6, weight=1)
        ttk.Label(editor, text="Almanca", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.word_var, style="Section.TLabel", wraplength=300, justify="left").grid(
            row=0, column=1, sticky="w", pady=6
        )
        ttk.Label(editor, text="Mevcut", style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 8))
        ttk.Label(editor, textvariable=self.existing_var, style="Muted.TLabel", wraplength=300, justify="left").grid(
            row=1, column=1, sticky="w", pady=6
        )
        ttk.Label(editor, text="Turkce", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 8))
        self.translation_entry = ttk.Entry(editor, textvariable=self.translation_var)
        self.translation_entry.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Tur", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 8))
        self.pos_combo = ttk.Combobox(editor, textvariable=self.pos_var, values=self.runtime["import_pos_choices"], state="readonly")
        self.pos_combo.grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(editor, text="Artikel", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 8))
        self.article_combo = ttk.Combobox(editor, textvariable=self.article_var, values=["", "der", "die", "das"], state="readonly")
        self.article_combo.grid(row=4, column=1, sticky="ew", pady=6)
        self.include_check = ttk.Checkbutton(editor, text="Bu kaydi ekle", variable=self.include_var, command=self.update_current_candidate)
        self.include_check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 4))

        info_box = ttk.Frame(editor, style="SoftPanel.TFrame", padding=12)
        info_box.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        info_box.columnconfigure(0, weight=1)
        info_box.rowconfigure(4, weight=1)
        ttk.Label(info_box, textvariable=self.source_var, style="Section.TLabel", wraplength=300, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(info_box, textvariable=self.confidence_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(info_box, textvariable=self.evidence_var, style="Muted.TLabel", wraplength=300, justify="left").grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Label(info_box, text="Baglam", style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 4))
        context_wrap = ttk.Frame(info_box)
        context_wrap.grid(row=4, column=0, sticky="nsew")
        context_wrap.columnconfigure(0, weight=1)
        context_wrap.rowconfigure(0, weight=1)
        self.context_text = tk.Text(context_wrap, height=8, wrap="word", relief="flat", padx=8, pady=8)
        self.context_text.grid(row=0, column=0, sticky="nsew")
        context_scroll = ttk.Scrollbar(context_wrap, orient="vertical", command=self.context_text.yview)
        context_scroll.grid(row=0, column=1, sticky="ns")
        self.context_text.configure(yscrollcommand=context_scroll.set, state="disabled")
        ttk.Label(info_box, textvariable=self.form_note_var, style="Muted.TLabel", wraplength=300, justify="left").grid(
            row=5, column=0, sticky="ew", pady=(10, 0)
        )

        footer = ttk.Frame(frame, padding=(0, 16, 0, 0))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="Iptal", command=self.destroy).grid(row=0, column=1)
        self.save_button = ttk.Button(footer, text="Secilenleri Sozluge Aktar", style="Primary.TButton", command=self.save_selected)
        self.save_button.grid(row=0, column=2, padx=(8, 0))

        for variable in [self.translation_var, self.pos_var, self.article_var]:
            variable.trace_add("write", self.on_editor_change)
        self.pos_var.trace_add("write", self.on_pos_change)

        self.set_editor_state(False)
        self.refresh_save_button_state()
        self.after(40, lambda: self.source_text.focus_set() if self.source_text is not None else None)

    def bring_to_front(self) -> None:
        self.lift()
        self.focus_force()

    def destroy(self) -> None:
        if getattr(self.app, "parallel_text_import_dialog", None) is self:
            self.app.parallel_text_import_dialog = None
        super().destroy()

    def set_editor_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        entry_state = "normal" if enabled else "disabled"
        self.pos_combo.configure(state=state)
        self.article_combo.configure(state=state if self.pos_var.get() == "isim" else "disabled")
        if self.translation_entry is not None:
            self.translation_entry.configure(state=entry_state)
        if self.include_check is not None:
            self.include_check.configure(state="normal" if enabled else "disabled")
        if not enabled:
            self.set_readonly_text(self.context_text, "Baglam: -")
        self.refresh_save_button_state()

    def set_readonly_text(self, widget: tk.Text | None, value: str) -> None:
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")
        widget.yview_moveto(0.0)

    def refresh_save_button_state(self) -> None:
        if self.save_button is None:
            return
        self.save_button.configure(state="normal" if any(item.get("ekle") for item in self.candidates) else "disabled")

    def start_scan(self) -> None:
        if self.is_scanning:
            return
        german_text = self.get_text_widget_value(self.source_text)
        turkish_text = self.get_text_widget_value(self.target_text)
        if not german_text or not turkish_text:
            messagebox.showerror("Metin Esleme", "Once Almanca metni ve Turkce ceviriyi girin.", parent=self)
            return

        self.is_scanning = True
        self.candidates = []
        self.candidate_map = {}
        self.current_candidate_id = None
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
        self.set_editor_state(False)
        self.summary_var.set("Metin esleme hazirlaniyor...")
        self.status_var.set("Almanca metin ile Turkce ceviri parcalanip karsilastiriliyor. Guclu eslesmeler hazirlaniyor...")
        if self.scan_button is not None:
            self.scan_button.configure(state="disabled")

        existing_meaning_index = self.runtime["build_existing_meaning_index"](self.app.records)
        api_url = str(self.app.settings.get("llm_api_url", self.runtime["default_llm_model_api_url"]) or self.runtime["default_llm_model_api_url"]).strip()
        api_key = str(self.app.settings.get("llm_api_key", "") or os.getenv("LLM_API_KEY", "")).strip()
        model = str(self.app.settings.get("llm_model", self.runtime["default_llm_model"]) or self.runtime["default_llm_model"])
        worker = threading.Thread(
            target=self._scan_worker,
            args=(german_text, turkish_text, existing_meaning_index, api_url, api_key, model),
            daemon=True,
        )
        worker.start()

    def _scan_worker(self, german_text: str, turkish_text: str, existing_meaning_index: dict, api_url: str, api_key: str, model: str) -> None:
        try:
            payload = self.runtime["collect_parallel_text_import_scan"](german_text, turkish_text, existing_meaning_index, api_url, api_key, model)
            self.after(0, lambda: self.on_scan_complete(*payload))
        except Exception as exc:
            self.after(0, lambda: self.on_scan_failed(str(exc)))

    def on_scan_failed(self, message: str) -> None:
        self.is_scanning = False
        if self.scan_button is not None:
            self.scan_button.configure(state="normal")
        self.status_var.set(f"Metin esleme basarisiz oldu. {message}")
        self.summary_var.set("Metin esleme tamamlanamadi.")

    def on_scan_complete(self, candidates: list[dict], note: str) -> None:
        self.is_scanning = False
        if self.scan_button is not None:
            self.scan_button.configure(state="normal")

        self.candidates = []
        self.candidate_map = {}
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())

        for candidate in candidates:
            self.candidates.append(candidate)
            self.candidate_map[candidate["id"]] = candidate
            if self.tree is not None:
                self.tree.insert("", "end", iid=candidate["id"], values=self.row_values(candidate))

        if not self.candidates:
            self.status_var.set(note)
            self.summary_var.set(note)
            self.set_editor_state(False)
            self.refresh_save_button_state()
            return

        selected_count = sum(1 for item in self.candidates if item.get("ekle"))
        self.status_var.set(f"{len(self.candidates)} yeni kelime veya eksik anlam paralel metin esleme ile hazirlandi.")
        self.summary_var.set(f"{len(self.candidates)} kayit hazir. Su an {selected_count} tanesi aktarilacak. {note}")
        self.set_editor_state(True)
        if self.tree is not None:
            first_id = self.candidates[0]["id"]
            self.tree.selection_set(first_id)
            self.load_candidate(first_id)
        self.refresh_save_button_state()

    def row_values(self, candidate: dict) -> tuple:
        return (
            candidate.get("almanca", ""),
            candidate.get("mevcut_turkce", "") or "-",
            candidate.get("turkce", ""),
            candidate.get("tur", ""),
            format_confidence(candidate.get("guven", 0.0)),
            "Ekle" if candidate.get("ekle", True) else "Atla",
        )

    def on_tree_select(self, _event=None) -> None:
        if self.tree is None:
            return
        selection = self.tree.selection()
        if selection:
            self.load_candidate(selection[0])

    def load_candidate(self, candidate_id: str) -> None:
        candidate = self.candidate_map.get(candidate_id)
        if not candidate:
            return
        self.current_candidate_id = candidate_id
        self.form_loading = True
        self.word_var.set(candidate.get("almanca", "-"))
        self.existing_var.set(f"Mevcut anlamlar: {candidate.get('mevcut_turkce', '-') or '-'}")
        self.translation_var.set(candidate.get("turkce", ""))
        self.pos_var.set(candidate.get("tur", "belirsiz") or "belirsiz")
        self.article_var.set(candidate.get("artikel", ""))
        self.include_var.set(bool(candidate.get("ekle", True)))
        self.source_var.set(f"Kaynak: {candidate.get('kaynak_etiketi', '-')}")
        self.confidence_var.set(f"Guven: {format_confidence(candidate.get('guven', 0.0))}")
        self.evidence_var.set(f"Eslesme kaniti: {candidate.get('eslesme_kaniti', '-') or '-'}")
        german_sentence = candidate.get("ornek_almanca", "")
        turkish_sentence = candidate.get("ornek_turkce", "")
        if german_sentence or turkish_sentence:
            self.context_var.set(f"Baglam: DE: {german_sentence or '-'} | TR: {turkish_sentence or '-'}")
            self.set_readonly_text(
                self.context_text,
                f"DE:\n{german_sentence or '-'}\n\nTR:\n{turkish_sentence or '-'}",
            )
        else:
            self.context_var.set("Baglam: Bu kayit icin cumle bilgisi yok.")
            self.set_readonly_text(self.context_text, "Bu kayit icin cumle bilgisi yok.")
        self.form_note_var.set(
            "Bu kayit, paralel metinden yeterli kanitla cikarildi. Dusuk guvenli eslesmeler listeye alinmadi."
        )
        self.on_pos_change()
        self.form_loading = False

    def on_editor_change(self, *_args) -> None:
        if not self.form_loading:
            self.update_current_candidate()

    def on_pos_change(self, *_args) -> None:
        is_noun = self.pos_var.get() == "isim"
        if not is_noun and self.article_var.get():
            self.article_var.set("")
        self.article_combo.configure(state="readonly" if is_noun and self.current_candidate_id else "disabled")

    def update_current_candidate(self) -> None:
        candidate = self.candidate_map.get(self.current_candidate_id or "")
        if not candidate:
            return
        candidate["turkce"] = self.translation_var.get().strip()
        candidate["tur"] = self.pos_var.get().strip() or "belirsiz"
        candidate["artikel"] = self.article_var.get().strip() if candidate["tur"] == "isim" else ""
        candidate["ekle"] = bool(self.include_var.get())
        if self.tree is not None:
            self.tree.item(candidate["id"], values=self.row_values(candidate))
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
        selected = [item for item in self.candidates if item.get("ekle")]
        if not selected:
            messagebox.showinfo("Metin Esleme", "Aktarilacak kayit secili degil.", parent=self)
            return

        payloads = [self.build_save_payload(item) for item in selected]
        first_key = None
        for payload in payloads:
            validation = self.runtime["validate_user_entry"](payload)
            if validation.get("status") == "error":
                messagebox.showerror("Metin Esleme", validation.get("note", "Bu kayit kaydedilemedi."), parent=self)
                return

        conflicts = self.find_duplicate_conflicts(payloads)
        if conflicts:
            preview = "\n".join(f"- {item}" for item in conflicts[:10])
            extra = f"\n- ... ve {len(conflicts) - 10} cakisma daha" if len(conflicts) > 10 else ""
            messagebox.showerror(
                "Metin Esleme",
                "Bazi secili kayitlar zaten sozlukte var veya secili listede tekrar ediyor:\n\n"
                f"{preview}{extra}\n\nLutfen bu kayitlari duzeltin ya da isaretlerini kaldirin.",
                parent=self,
            )
            return

        if not messagebox.askyesno("Metin Esleme Onayi", self.build_confirmation_message(selected), parent=self):
            return

        for payload in payloads:
            saved = self.runtime["save_user_entry"](payload)
            if first_key is None:
                first_key = self.runtime["record_key"](saved)

        self.app.reload_data(select_key=first_key)
        messagebox.showinfo("Metin Esleme", f"{len(selected)} kayit sozluge moduler olarak eklendi.", parent=self)
        self.destroy()
