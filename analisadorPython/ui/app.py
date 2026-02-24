from __future__ import annotations

import json
import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core import DEFAULT_CONTEXT, DEFAULT_KEYWORDS, MAX_FILE_SIZE_MB, extract_exception_blocks_from_lines, validate_input_path


class LogAnalyzerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Analisador de Logs")
        self.root.geometry("1280x820")
        self.root.minsize(760, 520)

        self.file_path: Path | None = None
        self.analysis_content = ""
        self.displayed_content = ""
        self.source_lines: list[str] = []
        self.exception_blocks: list[str] = []
        self.block_buttons: list[tk.Button] = []
        self.selected_block_index = -1

        self.highlights: list[tuple[int, int, int]] = []
        self.current_highlight_index = -1
        self.filters_visible = False
        self.pending_context_reload = False
        self.pending_keyword_reload = False
        self.applied_context = DEFAULT_CONTEXT
        self.reload_keep_index = 0
        self.keyword_store_path = self._resolve_keyword_store_path()
        self.custom_keywords, persisted_custom_active, self.ignored_terms = self._load_keyword_preferences()
        self.all_keywords = list(DEFAULT_KEYWORDS) + list(self.custom_keywords)
        self.active_keywords = set(DEFAULT_KEYWORDS) | set(persisted_custom_active)
        self.applied_keywords = tuple(self._active_keywords_in_order())
        self.applied_ignored_terms = tuple(self.ignored_terms)
        self.keyword_modal: tk.Toplevel | None = None
        self.found_keyword_counts: dict[str, int] = {}
        self.metric_card_frames: list[ttk.Frame] = []
        self._keyword_label_wraplength = 130
        self.custom_keyword_color = "#6EE7B7"
        self.stack_modal: tk.Toplevel | None = None
        self.stack_context_var = tk.IntVar(value=40)
        self.stack_context_scale: ttk.Scale | None = None
        self.stack_context_value_label: ttk.Label | None = None
        self.stack_context_info_label: ttk.Label | None = None
        self.stack_above_output: scrolledtext.ScrolledText | None = None
        self.stack_above_xscroll: ttk.Scrollbar | None = None
        self.stack_current_output: scrolledtext.ScrolledText | None = None
        self.stack_current_xscroll: ttk.Scrollbar | None = None
        self.stack_current_block_index = -1

        self._configure_style()
        self._build_layout()
        self._bind_shortcuts()

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        self.root.configure(bg="#0E1116")
        style.configure("TFrame", background="#0E1116")
        style.configure("Card.TFrame", background="#171B22", relief="flat")
        style.configure("Header.TLabel", background="#0E1116", foreground="#E6EDF3", font=("Segoe UI", 17, "bold"))
        style.configure("Muted.TLabel", background="#0E1116", foreground="#9BA7B4", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#171B22", foreground="#8FA3B8", font=("Segoe UI", 9, "bold"))
        style.configure("CardValue.TLabel", background="#171B22", foreground="#E6EDF3", font=("Segoe UI", 13, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(9, 4))
        style.configure("TButton", font=("Segoe UI", 9), padding=(7, 3))
        style.configure("ChipPrimary.TButton", font=("Segoe UI", 8, "bold"), padding=(5, 1))
        style.configure("ChipSecondary.TButton", font=("Segoe UI", 8, "bold"), padding=(5, 1))
        style.configure("TLabel", background="#0E1116", foreground="#E6EDF3", font=("Segoe UI", 10))

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Analisador de Logs", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Extracao de excecoes com contexto, busca e exportacao segura.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.toolbar = ttk.Frame(self.root)
        self.toolbar.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        for idx in range(14):
            self.toolbar.columnconfigure(idx, weight=0)
        self.toolbar.columnconfigure(9, weight=1)
        self.toolbar.columnconfigure(12, weight=1)

        self.btn_open = ttk.Button(self.toolbar, text="Abrir Log", style="Primary.TButton", command=self.open_file)
        self.btn_open.grid(row=0, column=0, padx=(0, 8))

        ttk.Button(self.toolbar, text="Limpar", command=self.clear_view).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(self.toolbar, text="Exportar", command=self.export_results).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(self.toolbar, text="Exportar Bloco", command=self.export_current_block).grid(row=0, column=3, padx=(0, 14))
        ttk.Button(self.toolbar, text="Opcoes", command=self.open_keywords_modal).grid(row=0, column=13, padx=(8, 0))

        self.context_label = ttk.Label(self.toolbar, text="Contexto abaixo (linhas):")
        self.context_label.grid(row=0, column=4, padx=(0, 6))
        self.context_var = tk.IntVar(value=DEFAULT_CONTEXT)
        self.context_scale = ttk.Scale(
            self.toolbar,
            from_=20,
            to=500,
            orient="horizontal",
            length=170,
            command=self._on_context_slider_changed,
        )
        self.context_scale.grid(row=0, column=5, padx=(0, 6))
        self.context_scale.set(DEFAULT_CONTEXT)
        self.context_value_label = ttk.Label(self.toolbar, text=str(DEFAULT_CONTEXT), width=3)
        self.context_value_label.grid(row=0, column=6, padx=(0, 14))

        self.reload_context_button = tk.Button(
            self.toolbar,
            text="RECARREGAR",
            command=self._reload_current_file_with_new_context,
            bg="#FF5A3D",
            fg="#FFFFFF",
            activebackground="#FF8E3C",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        self.reload_context_button.grid(row=0, column=7, padx=(0, 10))
        self.reload_context_button.grid_remove()

        self.search_label = ttk.Label(self.toolbar, text="Buscar:")
        self.search_label.grid(row=0, column=8, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.toolbar, textvariable=self.search_var, width=24)
        self.search_entry.grid(row=0, column=9, sticky="ew", padx=(0, 8))

        self.search_button = ttk.Button(self.toolbar, text="Localizar", command=self.search_keyword)
        self.search_button.grid(row=0, column=10, padx=(0, 6))
        self.prev_button = ttk.Button(self.toolbar, text="Anterior", width=10, command=self.previous_highlight)
        self.prev_button.grid(row=0, column=11, padx=(0, 6))
        self.next_button = ttk.Button(self.toolbar, text="Proximo", width=10, command=self.next_highlight)
        self.next_button.grid(row=0, column=12)

        self.status_var = tk.StringVar(value="Nenhum arquivo selecionado")
        self.status_label = ttk.Label(self.toolbar, textvariable=self.status_var, style="Muted.TLabel", anchor="e")
        self.status_label.grid(row=1, column=0, columnspan=14, sticky="ew", pady=(6, 0))

        self.body = ttk.Frame(self.root)
        self.body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(2, weight=1)

        self.cards = ttk.Frame(self.body)
        self.cards.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.cards.columnconfigure((0, 1, 2), weight=1)

        self.file_card = self._build_metric_card(self.cards, "Arquivo", "-", 0)
        self.blocks_card = self._build_metric_card(self.cards, "Blocos encontrados", "0", 1)
        self.matches_card = self._build_metric_card(self.cards, "Ocorrencias na busca", "0", 2)

        self._build_exception_slider(self.body)

        self.text_container = ttk.Frame(self.body, style="Card.TFrame", padding=8)
        self.text_container.grid(row=2, column=0, sticky="nsew")
        self.text_container.columnconfigure(0, weight=0)
        self.text_container.columnconfigure(1, weight=1)
        self.text_container.rowconfigure(0, weight=1)

        self.keyword_sidebar = tk.Frame(self.text_container, bg="#11161D", width=250, padx=8, pady=8)
        self.keyword_sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        self.keyword_sidebar.grid_propagate(False)
        self.keyword_sidebar.rowconfigure(1, weight=1)
        self.keyword_sidebar.columnconfigure(0, weight=1)

        tk.Label(
            self.keyword_sidebar,
            text="Palavras Encontradas",
            bg="#11161D",
            fg="#E6EDF3",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.keyword_list_canvas = tk.Canvas(
            self.keyword_sidebar,
            background="#11161D",
            highlightthickness=0,
            borderwidth=0,
            width=234,
        )
        self.keyword_list_canvas.grid(row=1, column=0, sticky="nsew")

        keyword_scroll = ttk.Scrollbar(self.keyword_sidebar, orient="vertical", command=self.keyword_list_canvas.yview)
        keyword_scroll.grid(row=1, column=1, sticky="ns")
        self.keyword_list_canvas.configure(yscrollcommand=keyword_scroll.set)

        self.keyword_list_inner = tk.Frame(self.keyword_list_canvas, bg="#11161D")
        self.keyword_list_window = self.keyword_list_canvas.create_window((0, 0), window=self.keyword_list_inner, anchor="nw")
        self.keyword_list_inner.bind("<Configure>", self._on_keyword_list_configure)
        self.keyword_list_canvas.bind("<Configure>", self._on_keyword_canvas_configure)

        self.output = scrolledtext.ScrolledText(
            self.text_container,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#0B0F14",
            fg="#E6EDF3",
            insertbackground="#E6EDF3",
            selectbackground="#24507A",
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=12,
            state="disabled",
        )
        self.output.grid(row=0, column=1, sticky="nsew")

        self.output.tag_config("match", background="#F2CC60", foreground="#101214")
        self.output.tag_config("current", background="#FF8E3C", foreground="#101214")
        self._refresh_found_keywords_panel()
        self._apply_responsive_layout(self.root.winfo_width())

    def _build_metric_card(self, parent: ttk.Frame, title: str, value: str, column: int) -> tk.StringVar:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        frame.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        frame.columnconfigure(0, weight=1)
        self.metric_card_frames.append(frame)
        ttk.Label(frame, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        var = tk.StringVar(value=value)
        ttk.Label(frame, textvariable=var, style="CardValue.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        return var

    def _build_exception_slider(self, parent: ttk.Frame) -> None:
        self.slider_outer = ttk.Frame(parent, style="Card.TFrame", padding=(10, 8))
        self.slider_outer.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.slider_outer.columnconfigure(1, weight=1)
        self.slider_outer.rowconfigure(1, weight=1)

        ttk.Label(self.slider_outer, text="Excecoes Encontradas", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Button(self.slider_outer, text="<", width=3, command=lambda: self._scroll_exception_cards(-1)).grid(row=1, column=0, padx=(0, 8))

        self.slider_canvas = tk.Canvas(
            self.slider_outer,
            height=118,
            background="#171B22",
            highlightthickness=0,
            borderwidth=0,
        )
        self.slider_canvas.grid(row=1, column=1, sticky="ew")

        ttk.Button(self.slider_outer, text=">", width=3, command=lambda: self._scroll_exception_cards(1)).grid(row=1, column=2, padx=(8, 0))

        self.slider_xscroll = ttk.Scrollbar(self.slider_outer, orient="horizontal", command=self.slider_canvas.xview)
        self.slider_xscroll.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        self.slider_canvas.configure(xscrollcommand=self.slider_xscroll.set)
        self.slider_inner = tk.Frame(self.slider_canvas, bg="#171B22")
        self.slider_window = self.slider_canvas.create_window((0, 0), window=self.slider_inner, anchor="nw")

        self.slider_inner.bind("<Configure>", self._on_slider_content_configure)
        self.slider_canvas.bind("<Configure>", self._on_slider_canvas_configure)

        self.filter_widgets = [
            self.context_label,
            self.context_scale,
            self.context_value_label,
            self.search_label,
            self.search_entry,
            self.search_button,
            self.prev_button,
            self.next_button,
        ]
        self._set_filters_visible(False)

    def _set_filters_visible(self, visible: bool) -> None:
        self.filters_visible = visible
        for widget in self.filter_widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

        if visible:
            self.slider_outer.grid()
        else:
            self.slider_outer.grid_remove()
            self._set_reload_button_visible(False)

    def _set_reload_button_visible(self, visible: bool) -> None:
        if visible and self.filters_visible:
            self.reload_context_button.grid()
        else:
            self.reload_context_button.grid_remove()

    def _active_keywords_in_order(self) -> list[str]:
        return [keyword for keyword in self.all_keywords if keyword in self.active_keywords]

    def _resolve_keyword_store_path(self) -> Path:
        base_dir = Path(os.getenv("LOCALAPPDATA") or Path.home())
        return base_dir / "AnalisadorLogs" / "keywords.json"

    def _load_keyword_preferences(self) -> tuple[list[str], list[str], list[str]]:
        default_lowers = {keyword.lower() for keyword in DEFAULT_KEYWORDS}
        if not self.keyword_store_path.exists():
            return [], [], []
        try:
            payload = json.loads(self.keyword_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [], [], []

        raw_custom = payload.get("custom_keywords", [])
        raw_active_custom = payload.get("active_custom_keywords")
        custom_keywords: list[str] = []
        custom_lowers: set[str] = set()

        for item in raw_custom:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            lowered = cleaned.lower()
            if not cleaned or lowered in default_lowers or lowered in custom_lowers:
                continue
            custom_keywords.append(cleaned)
            custom_lowers.add(lowered)

        active_custom_keywords: list[str] = []
        if isinstance(raw_active_custom, list):
            for item in raw_active_custom:
                if not isinstance(item, str):
                    continue
                cleaned = item.strip()
                if cleaned in custom_keywords:
                    active_custom_keywords.append(cleaned)
        else:
            active_custom_keywords = list(custom_keywords)

        raw_ignored_terms = payload.get("ignored_terms", [])
        ignored_terms: list[str] = []
        ignored_lowers: set[str] = set()
        for item in raw_ignored_terms:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            lowered = cleaned.lower()
            if not cleaned or lowered in ignored_lowers:
                continue
            ignored_terms.append(cleaned)
            ignored_lowers.add(lowered)

        return custom_keywords, active_custom_keywords, ignored_terms

    def _save_keyword_preferences(self) -> None:
        active_custom_keywords = [keyword for keyword in self.custom_keywords if keyword in self.active_keywords]
        payload = {
            "custom_keywords": self.custom_keywords,
            "active_custom_keywords": active_custom_keywords,
            "ignored_terms": self.ignored_terms,
        }
        try:
            self.keyword_store_path.parent.mkdir(parents=True, exist_ok=True)
            self.keyword_store_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # Keep running even if persistence storage is unavailable.
            pass

    def _update_reload_state(self) -> None:
        self.pending_context_reload = self.context_var.get() != self.applied_context
        self.pending_keyword_reload = tuple(self._active_keywords_in_order()) != self.applied_keywords
        pending_ignored_reload = tuple(self.ignored_terms) != self.applied_ignored_terms
        has_pending = self.pending_context_reload or self.pending_keyword_reload or pending_ignored_reload
        self._set_reload_button_visible(has_pending)

        if not self.file_path:
            return
        if has_pending:
            reasons = []
            if self.pending_context_reload:
                reasons.append("contexto")
            if self.pending_keyword_reload:
                reasons.append("palavras-chave")
            if pending_ignored_reload:
                reasons.append("desconsideradas")
            self.status_var.set(
                f"Filtro alterado ({' + '.join(reasons)}). Clique em RECARREGAR para aplicar."
            )
        else:
            self.status_var.set(f"Arquivo: {self.file_path}")

    def _on_slider_content_configure(self, _event: tk.Event) -> None:
        self.slider_canvas.configure(scrollregion=self.slider_canvas.bbox("all"))

    def _on_slider_canvas_configure(self, event: tk.Event) -> None:
        self.slider_canvas.itemconfigure(self.slider_window, height=event.height)

    def _on_keyword_list_configure(self, _event: tk.Event) -> None:
        self.keyword_list_canvas.configure(scrollregion=self.keyword_list_canvas.bbox("all"))

    def _on_keyword_canvas_configure(self, event: tk.Event) -> None:
        self.keyword_list_canvas.itemconfigure(self.keyword_list_window, width=event.width)

    def _apply_responsive_layout(self, width: int) -> None:
        if width < 920:
            self.status_label.configure(anchor="w")
            for idx, frame in enumerate(self.metric_card_frames):
                frame.grid_configure(row=idx, column=0, padx=0, pady=(0 if idx == 0 else 8, 0))
            self.cards.columnconfigure(0, weight=1)
            self.cards.columnconfigure(1, weight=0)
            self.cards.columnconfigure(2, weight=0)

            self.text_container.rowconfigure(0, weight=0)
            self.text_container.rowconfigure(1, weight=1)
            self.text_container.columnconfigure(0, weight=1)
            self.text_container.columnconfigure(1, weight=0)
            self.keyword_sidebar.grid_configure(row=0, column=0, sticky="ew", padx=(0, 0), pady=(0, 8))
            self.output.grid_configure(row=1, column=0, sticky="nsew")
            sidebar_width = max(180, width - 80)
            self.keyword_sidebar.configure(width=sidebar_width, height=185)
            self._keyword_label_wraplength = max(120, sidebar_width - 140)
        else:
            self.status_label.configure(anchor="e")
            for idx, frame in enumerate(self.metric_card_frames):
                frame.grid_configure(row=0, column=idx, padx=(0 if idx == 0 else 8, 0), pady=0)
            self.cards.columnconfigure(0, weight=1)
            self.cards.columnconfigure(1, weight=1)
            self.cards.columnconfigure(2, weight=1)

            self.text_container.rowconfigure(0, weight=1)
            self.text_container.rowconfigure(1, weight=0)
            self.text_container.columnconfigure(0, weight=0)
            self.text_container.columnconfigure(1, weight=1)
            self.keyword_sidebar.grid_configure(row=0, column=0, sticky="nsw", padx=(0, 8), pady=(0, 0))
            self.output.grid_configure(row=0, column=1, sticky="nsew")
            sidebar_width = 300 if width >= 1600 else 260 if width >= 1300 else 230 if width >= 1100 else 200
            self.keyword_sidebar.configure(width=sidebar_width, height=1)
            self._keyword_label_wraplength = max(110, sidebar_width - 120)

    def _on_root_resized(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        self._apply_responsive_layout(event.width)

    def _refresh_found_keywords_panel(self) -> None:
        for child in self.keyword_list_inner.winfo_children():
            child.destroy()

        source_blocks = self.exception_blocks if self.exception_blocks else []
        keyword_counts: dict[str, int] = {}
        for keyword in self.applied_keywords:
            total = 0
            for block_text in source_blocks:
                total += len(self._find_term_offsets(block_text, keyword))
            if total > 0:
                keyword_counts[keyword] = total

        self.found_keyword_counts = keyword_counts
        if not keyword_counts:
            tk.Label(
                self.keyword_list_inner,
                text="Nenhuma palavra-chave encontrada.",
                bg="#11161D",
                fg="#9BA7B4",
                justify="left",
                anchor="w",
                wraplength=210,
                padx=6,
                pady=8,
            ).grid(row=0, column=0, sticky="ew")
            return

        for row_idx, (keyword, count) in enumerate(keyword_counts.items()):
            row = tk.Frame(self.keyword_list_inner, bg="#1A212B", padx=6, pady=6)
            row.grid(row=row_idx, column=0, sticky="ew", pady=(0, 6))
            row.columnconfigure(0, weight=1)
            row.columnconfigure(1, weight=1)

            tk.Label(
                row,
                text=f"{keyword} ({count})",
                bg="#1A212B",
                fg=self.custom_keyword_color if keyword in self.custom_keywords else "#DCE7F3",
                anchor="w",
                justify="left",
                wraplength=self._keyword_label_wraplength,
                font=("Segoe UI", 9, "bold"),
            ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

            ttk.Button(
                row,
                text="Buscar",
                command=lambda term=keyword: self._search_from_keyword_button(term),
                style="ChipPrimary.TButton",
            ).grid(row=1, column=0, sticky="ew", padx=(0, 3))

            ttk.Button(
                row,
                text="Anterior",
                command=lambda term=keyword: self._search_previous_from_keyword_button(term),
                style="ChipSecondary.TButton",
            ).grid(row=1, column=1, sticky="ew", padx=(3, 0))

    def _search_from_keyword_button(self, keyword: str) -> None:
        normalized = keyword.strip()
        if not normalized:
            return
        is_same_term = self.search_var.get().strip().lower() == normalized.lower()
        self.search_var.set(normalized)
        if is_same_term and self.highlights:
            self.next_highlight()
            return
        self.search_keyword()

    def _search_previous_from_keyword_button(self, keyword: str) -> None:
        normalized = keyword.strip()
        if not normalized:
            return
        is_same_term = self.search_var.get().strip().lower() == normalized.lower()
        self.search_var.set(normalized)
        if is_same_term and self.highlights:
            self.previous_highlight()
            return
        self.search_keyword()
        if self.highlights:
            self.current_highlight_index = len(self.highlights) - 1
            self._scroll_to_highlight(self.current_highlight_index)

    def _scroll_exception_cards(self, direction: int) -> None:
        self.slider_canvas.xview_scroll(3 * direction, "units")

    def _scroll_slider_to_x(self, target_x: int) -> None:
        bbox = self.slider_canvas.bbox("all")
        if not bbox:
            return
        content_left, _content_top, content_right, _content_bottom = bbox
        content_width = max(content_right - content_left, 1)
        viewport_width = self.slider_canvas.winfo_width()
        max_offset = max(content_width - viewport_width, 0)
        clamped_offset = max(0, min(target_x, max_offset))
        fraction = 0.0 if max_offset == 0 else clamped_offset / max_offset
        self.slider_canvas.xview_moveto(fraction)

    def _ensure_selected_card_visible(self, index: int) -> None:
        if index < 0 or index >= len(self.block_buttons):
            return

        self.root.update_idletasks()
        button = self.block_buttons[index]
        button_left = button.winfo_x()
        button_right = button_left + button.winfo_width()
        visible_left = int(self.slider_canvas.canvasx(0))
        visible_right = visible_left + self.slider_canvas.winfo_width()

        if button_left < visible_left:
            self._scroll_slider_to_x(button_left)
        elif button_right > visible_right:
            self._scroll_slider_to_x(button_right - self.slider_canvas.winfo_width())

    def _on_context_slider_changed(self, value: str) -> None:
        context_value = int(round(float(value)))
        context_value = min(500, max(20, context_value))
        self.context_var.set(context_value)
        self.context_value_label.configure(text=str(context_value))

        self._update_reload_state()

    def _reload_current_file_with_new_context(self) -> None:
        if not self.file_path:
            return

        self.reload_keep_index = max(self.selected_block_index, 0)
        self.status_var.set(f"Recarregando com contexto {self.context_var.get()}...")
        self.btn_open.configure(state="disabled")
        self.reload_context_button.configure(state="disabled")
        thread = threading.Thread(target=self._analyze_file_worker, args=(self.file_path,), daemon=True)
        thread.start()

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _evt: self.open_file())
        self.root.bind("<Control-f>", lambda _evt: self.search_entry.focus_set() if self.filters_visible else None)
        self.root.bind("<F3>", lambda _evt: self.next_highlight())
        self.root.bind("<Shift-F3>", lambda _evt: self.previous_highlight())
        self.root.bind("<Control-s>", lambda _evt: self.export_results())
        self.root.bind("<Configure>", self._on_root_resized)

    def open_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecione um arquivo de log",
            filetypes=[("Arquivos de log", "*.log *.txt *.out *.trace"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return

        candidate = Path(selected)
        valid, error = validate_input_path(candidate, max_file_size_mb=MAX_FILE_SIZE_MB)
        if not valid:
            messagebox.showerror("Erro", error)
            return

        self.file_path = candidate
        self.reload_keep_index = 0
        self.pending_context_reload = False
        self.pending_keyword_reload = False
        self._set_reload_button_visible(False)
        self.status_var.set("Analisando arquivo...")
        self.btn_open.configure(state="disabled")

        thread = threading.Thread(target=self._analyze_file_worker, args=(candidate,), daemon=True)
        thread.start()

    def _analyze_file_worker(self, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as file_obj:
                source_lines = file_obj.readlines()

            result = extract_exception_blocks_from_lines(
                source_lines,
                context=self.context_var.get(),
                keywords=self._active_keywords_in_order(),
                ignored_terms=self.ignored_terms,
            )
            self.root.after(
                0,
                lambda: self._on_analysis_success(path, result.content, list(result.blocks), source_lines),
            )
        except Exception as exc:
            self.root.after(0, lambda: self._on_analysis_error(str(exc)))

    def _on_analysis_success(self, path: Path, content: str, blocks: list[str], source_lines: list[str]) -> None:
        self.analysis_content = content
        self.source_lines = source_lines
        self.exception_blocks = blocks
        self.highlights = []
        self.current_highlight_index = -1
        self.matches_card.set("0")
        self.applied_context = self.context_var.get()
        self.applied_keywords = tuple(self._active_keywords_in_order())
        self.applied_ignored_terms = tuple(self.ignored_terms)
        self.pending_context_reload = False
        self.pending_keyword_reload = False

        self.file_card.set(path.name)
        self.blocks_card.set(str(len(blocks)))
        self.status_var.set(f"Arquivo: {path}")
        self.btn_open.configure(state="normal")
        self.reload_context_button.configure(state="normal")
        self._set_filters_visible(True)
        self._update_reload_state()
        self._refresh_found_keywords_panel()

        self._populate_exception_cards(blocks)

        if blocks:
            selected_index = min(self.reload_keep_index, len(blocks) - 1)
            self._select_exception_block(selected_index)
        else:
            self.selected_block_index = -1
            self.displayed_content = content
            self._set_output_text(content)
            self._refresh_found_keywords_panel()
        self.reload_keep_index = 0

    def _populate_exception_cards(self, blocks: list[str]) -> None:
        for child in self.slider_inner.winfo_children():
            child.destroy()
        self.block_buttons = []

        if not blocks:
            empty = tk.Label(
                self.slider_inner,
                text="Nenhuma excecao encontrada para exibir em cards.",
                bg="#171B22",
                fg="#9BA7B4",
                font=("Segoe UI", 10),
                padx=12,
                pady=16,
            )
            empty.grid(row=0, column=0, sticky="w")
            self.slider_canvas.xview_moveto(0)
            return

        for idx, block in enumerate(blocks):
            title = self._build_block_title(idx, block)
            preview = self._build_block_preview(block)
            text = f"{title}\n{preview}"

            card = tk.Frame(self.slider_inner, bg="#171B22")
            card.grid(row=0, column=idx, padx=(0, 8), sticky="nsew")
            card.columnconfigure(0, weight=1)

            btn = tk.Button(
                card,
                text=text,
                justify="left",
                anchor="nw",
                width=32,
                height=3,
                wraplength=260,
                bg="#1E2530",
                fg="#DCE7F3",
                activebackground="#2A3342",
                activeforeground="#FFFFFF",
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                command=lambda i=idx: self._select_exception_block(i),
                padx=8,
                pady=4,
            )
            btn.grid(row=0, column=0, sticky="nsew")

            stack_button = tk.Button(
                card,
                text=f"Ver pilha acima: {self._build_stack_button_description(block)}",
                justify="left",
                anchor="w",
                wraplength=260,
                bg="#2A3342",
                fg="#DCE7F3",
                activebackground="#3A4558",
                activeforeground="#FFFFFF",
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                command=lambda i=idx: self._open_stack_modal(i),
                padx=8,
                pady=4,
                font=("Segoe UI", 8, "bold"),
            )
            stack_button.grid(row=1, column=0, sticky="ew", pady=(6, 0))
            self.block_buttons.append(btn)

        self.slider_canvas.xview_moveto(0)

    def _build_block_title(self, index: int, block: str) -> str:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        summary = lines[0] if lines else "Sem conteudo"
        if len(summary) > 58:
            summary = summary[:58].rstrip() + "..."
        return f"Bloco {index + 1}: {summary}"

    def _build_block_preview(self, block: str) -> str:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            return "Clique para visualizar o trecho completo."
        preview = lines[1]
        if len(preview) > 75:
            preview = preview[:75].rstrip() + "..."
        return preview

    def _build_stack_button_description(self, block: str) -> str:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            return "Detalhes do bloco"
        description = lines[1]
        if len(description) > 42:
            description = description[:42].rstrip() + "..."
        return description

    def _select_exception_block(self, index: int) -> None:
        if index < 0 or index >= len(self.exception_blocks):
            return

        self.selected_block_index = index
        self.displayed_content = self._build_stack_current_text(index)
        self._set_output_text(self.displayed_content)

        for idx, btn in enumerate(self.block_buttons):
            if idx == index:
                btn.configure(bg="#FF8E3C", fg="#101214", activebackground="#FF8E3C", activeforeground="#101214")
            else:
                btn.configure(bg="#1E2530", fg="#DCE7F3", activebackground="#2A3342", activeforeground="#FFFFFF")

        self._ensure_selected_card_visible(index)
        self._render_current_search_highlights()

    def _open_stack_modal(self, block_index: int) -> None:
        if block_index < 0 or block_index >= len(self.exception_blocks):
            return

        self.stack_current_block_index = block_index
        self.stack_context_var.set(40)

        if self.stack_modal is not None and self.stack_modal.winfo_exists():
            self.stack_modal.focus_force()
            self._refresh_stack_modal_content()
            return

        modal = tk.Toplevel(self.root)
        modal.title("Pilha acima do bloco")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        modal_width = min(screen_width - 40, max(720, int(screen_width * 0.7)))
        modal_height = min(screen_height - 80, max(520, int(screen_height * 0.7)))
        pos_x = max(0, (screen_width - modal_width) // 2)
        pos_y = max(0, (screen_height - modal_height) // 2)
        modal.geometry(f"{modal_width}x{modal_height}+{pos_x}+{pos_y}")
        modal.minsize(700, 500)
        modal.configure(bg="#11161D")
        modal.transient(self.root)
        modal.grab_set()
        modal.protocol("WM_DELETE_WINDOW", self._close_stack_modal)
        self.stack_modal = modal

        container = ttk.Frame(modal, padding=14)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)
        container.rowconfigure(7, weight=1)

        ttk.Label(
            container,
            text="Bloco atual e linhas acima",
            style="Header.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        control_row = ttk.Frame(container)
        control_row.grid(row=1, column=0, sticky="ew")
        control_row.columnconfigure(1, weight=1)

        ttk.Label(control_row, text="Linhas acima:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.stack_context_scale = ttk.Scale(
            control_row,
            from_=40,
            to=200,
            orient="horizontal",
            command=self._on_stack_context_changed,
        )
        self.stack_context_scale.grid(row=0, column=1, sticky="ew")
        self.stack_context_scale.set(40)
        self.stack_context_value_label = ttk.Label(control_row, text="40", width=4)
        self.stack_context_value_label.grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.stack_context_info_label = ttk.Label(container, text="", style="Muted.TLabel")
        self.stack_context_info_label.grid(row=2, column=0, sticky="w", pady=(8, 8))

        ttk.Label(container, text="Linhas acima", style="CardTitle.TLabel").grid(row=3, column=0, sticky="nw")
        self.stack_above_output = scrolledtext.ScrolledText(
            container,
            wrap=tk.NONE,
            font=("Consolas", 10),
            bg="#0B0F14",
            fg="#E6EDF3",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
            height=9,
            state="disabled",
        )
        self.stack_above_output.grid(row=4, column=0, sticky="nsew", pady=(4, 10))
        self.stack_above_xscroll = ttk.Scrollbar(container, orient="horizontal", command=self.stack_above_output.xview)
        self.stack_above_xscroll.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self.stack_above_output.configure(xscrollcommand=self.stack_above_xscroll.set)

        ttk.Label(container, text="Bloco atual", style="CardTitle.TLabel").grid(row=6, column=0, sticky="nw")
        self.stack_current_output = scrolledtext.ScrolledText(
            container,
            wrap=tk.NONE,
            font=("Consolas", 10),
            bg="#0B0F14",
            fg="#E6EDF3",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
            state="disabled",
        )
        self.stack_current_output.grid(row=7, column=0, sticky="nsew", pady=(4, 0))
        self.stack_current_xscroll = ttk.Scrollbar(container, orient="horizontal", command=self.stack_current_output.xview)
        self.stack_current_xscroll.grid(row=8, column=0, sticky="ew", pady=(0, 10))
        self.stack_current_output.configure(xscrollcommand=self.stack_current_xscroll.set)

        ttk.Button(container, text="Fechar", command=self._close_stack_modal).grid(row=9, column=0, sticky="e", pady=(12, 0))
        self._refresh_stack_modal_content()

    def _close_stack_modal(self) -> None:
        if self.stack_modal is not None and self.stack_modal.winfo_exists():
            self.stack_modal.grab_release()
            self.stack_modal.destroy()
        self.stack_modal = None
        self.stack_context_scale = None
        self.stack_context_value_label = None
        self.stack_context_info_label = None
        self.stack_above_output = None
        self.stack_above_xscroll = None
        self.stack_current_output = None
        self.stack_current_xscroll = None

    def _on_stack_context_changed(self, value: str) -> None:
        context_value = int(round(float(value)))
        context_value = min(200, max(40, context_value))
        self.stack_context_var.set(context_value)
        if self.stack_context_value_label is not None:
            self.stack_context_value_label.configure(text=str(context_value))
        self._refresh_stack_modal_content()

    def _refresh_stack_modal_content(self) -> None:
        if self.stack_modal is None or not self.stack_modal.winfo_exists():
            return
        if self.stack_current_block_index < 0 or self.stack_current_block_index >= len(self.exception_blocks):
            return
        if self.stack_above_output is None or self.stack_current_output is None:
            return

        above_count = self.stack_context_var.get()
        above_text = self._build_stack_above_text(self.stack_current_block_index, above_count)
        block_text = self._build_stack_current_text(self.stack_current_block_index)
        self._set_scrolled_text(self.stack_above_output, above_text)
        self._set_scrolled_text(self.stack_current_output, block_text)
        if self.stack_context_info_label is not None:
            self.stack_context_info_label.configure(
                text=f"Bloco {self.stack_current_block_index + 1} com {above_count} linhas acima."
            )

    def _set_scrolled_text(self, widget: scrolledtext.ScrolledText, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def _build_stack_above_text(self, block_index: int, above_count: int) -> str:
        if block_index < 0 or block_index >= len(self.exception_blocks):
            return "Bloco invalido."
        if not self.source_lines:
            return "Nao foi possivel carregar as linhas do arquivo para exibir o contexto acima."

        first_hit_line = self._extract_first_hit_line_number(self.exception_blocks[block_index])
        if first_hit_line is None:
            return "Nao foi possivel identificar a linha inicial do bloco."

        hit_idx = max(0, first_hit_line - 1)
        start_idx = max(0, hit_idx - above_count)
        context_lines = self.source_lines[start_idx:hit_idx]
        if not context_lines:
            return "Nao existem linhas anteriores para este bloco."

        numbered_lines = [
            f"{line_no:>6}: {line.rstrip()}"
            for line_no, line in enumerate(context_lines, start=start_idx + 1)
        ]
        return "\n".join(numbered_lines)

    def _build_stack_current_text(self, block_index: int) -> str:
        if block_index < 0 or block_index >= len(self.exception_blocks):
            return "Bloco invalido."

        block = self.exception_blocks[block_index]
        lines = block.splitlines()
        if len(lines) <= 1:
            return block

        first_hit_line = self._extract_first_hit_line_number(block)
        if first_hit_line is None:
            return block

        numbered_lines = [
            f"{line_no:>6}: {line.rstrip()}"
            for line_no, line in enumerate(lines[1:], start=first_hit_line)
        ]
        return "\n".join(numbered_lines)

    def _extract_first_hit_line_number(self, block: str) -> int | None:
        header = block.splitlines()[0].strip() if block.splitlines() else ""
        match = re.search(r"\d+", header)
        if not match:
            return None
        return int(match.group())

    def open_keywords_modal(self) -> None:
        if self.keyword_modal is not None and self.keyword_modal.winfo_exists():
            self.keyword_modal.focus_force()
            return

        modal = tk.Toplevel(self.root)
        modal.title("Opcoes de Palavras-chave")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_usable_width = max(420, screen_width - 40)
        modal_min_width = min(max_usable_width, max(760, int(screen_width * 0.7)))
        modal_width = min(screen_width - 40, modal_min_width)
        modal_height = min(screen_height - 80, 560)
        pos_x = max(0, (screen_width - modal_width) // 2)
        pos_y = max(0, (screen_height - modal_height) // 2)
        modal.minsize(modal_min_width, 480)
        modal.geometry(f"{modal_width}x{modal_height}+{pos_x}+{pos_y}")
        modal.configure(bg="#11161D")
        modal.transient(self.root)
        modal.grab_set()
        modal.protocol("WM_DELETE_WINDOW", self._close_keywords_modal)
        self.keyword_modal = modal

        self.keyword_modal_container = ttk.Frame(modal, padding=14)
        self.keyword_modal_container.pack(fill="both", expand=True)
        self.keyword_modal_container.columnconfigure(0, weight=1)
        self.keyword_modal_container.columnconfigure(2, weight=0)
        self.keyword_modal_container.columnconfigure(4, weight=1)
        self.keyword_modal_container.rowconfigure(2, weight=1)
        self.keyword_modal_container.rowconfigure(4, weight=1)

        ttk.Label(
            self.keyword_modal_container,
            text="Palavras-chave para deteccao de blocos no log",
            style="Header.TLabel",
        ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 10))

        self.active_label = ttk.Label(self.keyword_modal_container, text="Ativas", style="CardTitle.TLabel")
        self.active_label.grid(row=1, column=0, sticky="w")
        self.ignored_label = ttk.Label(self.keyword_modal_container, text="Ignoradas", style="CardTitle.TLabel")
        self.ignored_label.grid(row=1, column=4, sticky="w")

        self.active_keywords_listbox = tk.Listbox(
            self.keyword_modal_container,
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="#0B0F14",
            fg="#E6EDF3",
            selectbackground="#24507A",
            relief="flat",
            width=30,
            height=12,
        )
        self.active_keywords_listbox.grid(row=2, column=0, sticky="nsew", padx=(0, 8))

        self.ignored_keywords_listbox = tk.Listbox(
            self.keyword_modal_container,
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="#0B0F14",
            fg="#E6EDF3",
            selectbackground="#24507A",
            relief="flat",
            width=30,
            height=12,
        )
        self.ignored_keywords_listbox.grid(row=2, column=4, sticky="nsew", padx=(8, 0))

        self.transfer_frame = ttk.Frame(self.keyword_modal_container)
        self.transfer_frame.grid(row=2, column=2, padx=8)
        self.transfer_to_ignored_button = ttk.Button(self.transfer_frame, text="Ignorar >>", command=self._move_keywords_to_ignored)
        self.transfer_to_ignored_button.grid(row=0, column=0, pady=(0, 8))
        self.transfer_to_active_button = ttk.Button(self.transfer_frame, text="<< Ativar", command=self._move_keywords_to_active)
        self.transfer_to_active_button.grid(row=1, column=0)

        self.add_area = ttk.Frame(self.keyword_modal_container)
        self.add_area.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(14, 0))
        self.add_area.columnconfigure(1, weight=1)

        ttk.Label(self.add_area, text="Adicionar palavra-chave:").grid(row=0, column=0, padx=(0, 8))
        self.new_keyword_var = tk.StringVar()
        entry = ttk.Entry(self.add_area, textvariable=self.new_keyword_var)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(self.add_area, text="Adicionar", command=self._submit_new_keyword).grid(row=0, column=2)
        self.new_keyword_status = tk.StringVar(value="")
        ttk.Label(self.add_area, textvariable=self.new_keyword_status, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        self.ignored_area = ttk.Frame(self.keyword_modal_container)
        self.ignored_area.grid(row=4, column=0, columnspan=5, sticky="nsew", pady=(14, 0))
        self.ignored_area.columnconfigure(0, weight=1)
        self.ignored_area.rowconfigure(1, weight=1)

        ttk.Label(self.ignored_area, text="Palavras desconsideradas na deteccao", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.ignored_terms_listbox = tk.Listbox(
            self.ignored_area,
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="#0B0F14",
            fg="#E6EDF3",
            selectbackground="#24507A",
            relief="flat",
            height=5,
        )
        self.ignored_terms_listbox.grid(row=1, column=0, sticky="nsew")

        self.ignored_entry_area = ttk.Frame(self.ignored_area)
        self.ignored_entry_area.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.ignored_entry_area.columnconfigure(0, weight=1)
        self.new_ignored_var = tk.StringVar()
        ignored_entry = ttk.Entry(self.ignored_entry_area, textvariable=self.new_ignored_var)
        ignored_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(self.ignored_entry_area, text="Adicionar", command=self._submit_ignored_term).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(self.ignored_entry_area, text="Remover Selecionadas", command=self._remove_selected_ignored_terms).grid(row=0, column=2)
        ignored_entry.bind("<Return>", lambda _evt: self._submit_ignored_term())

        self.keyword_footer = ttk.Frame(self.keyword_modal_container)
        self.keyword_footer.grid(row=5, column=0, columnspan=5, sticky="e", pady=(14, 0))
        ttk.Button(self.keyword_footer, text="Excluir Inseridas", command=self._delete_selected_custom_keywords).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(self.keyword_footer, text="Fechar", command=self._close_keywords_modal).grid(row=0, column=1)

        entry.bind("<Return>", lambda _evt: self._submit_new_keyword())
        self._refresh_keyword_modal_lists()
        self._refresh_ignored_terms_listbox()
        self._apply_keywords_modal_layout(modal.winfo_width())
        modal.bind("<Configure>", self._on_keywords_modal_resized)
        entry.focus_set()

    def _close_keywords_modal(self) -> None:
        if self.keyword_modal is not None and self.keyword_modal.winfo_exists():
            self.keyword_modal.grab_release()
            self.keyword_modal.destroy()
        self.keyword_modal = None

    def _apply_keywords_modal_layout(self, width: int) -> None:
        if self.keyword_modal is None or not self.keyword_modal.winfo_exists():
            return

        if width < 900:
            self.keyword_modal_container.columnconfigure(0, weight=1)
            self.keyword_modal_container.columnconfigure(2, weight=0)
            self.keyword_modal_container.columnconfigure(4, weight=0)
            self.keyword_modal_container.rowconfigure(2, weight=1)
            self.keyword_modal_container.rowconfigure(5, weight=1)

            self.active_label.grid_configure(row=1, column=0, sticky="w", pady=(0, 4))
            self.active_keywords_listbox.grid_configure(row=2, column=0, columnspan=1, sticky="nsew", padx=0)

            self.transfer_frame.grid_configure(row=3, column=0, padx=0, pady=(8, 8), sticky="ew")
            self.transfer_frame.columnconfigure(0, weight=1)
            self.transfer_frame.columnconfigure(1, weight=1)
            self.transfer_to_ignored_button.grid_configure(row=0, column=0, pady=0, padx=(0, 6), sticky="ew")
            self.transfer_to_active_button.grid_configure(row=0, column=1, pady=0, padx=(6, 0), sticky="ew")

            self.ignored_label.grid_configure(row=4, column=0, sticky="w", pady=(0, 4))
            self.ignored_keywords_listbox.grid_configure(row=5, column=0, columnspan=1, sticky="nsew", padx=0)

            self.add_area.grid_configure(row=6, column=0, columnspan=1, sticky="ew", pady=(12, 0))
            self.ignored_area.grid_configure(row=7, column=0, columnspan=1, sticky="nsew", pady=(12, 0))
            self.keyword_footer.grid_configure(row=8, column=0, columnspan=1, sticky="ew", pady=(12, 0))
        else:
            self.keyword_modal_container.columnconfigure(0, weight=1)
            self.keyword_modal_container.columnconfigure(2, weight=0)
            self.keyword_modal_container.columnconfigure(4, weight=1)
            self.keyword_modal_container.rowconfigure(2, weight=1)
            self.keyword_modal_container.rowconfigure(5, weight=0)

            self.active_label.grid_configure(row=1, column=0, sticky="w", pady=0)
            self.active_keywords_listbox.grid_configure(row=2, column=0, columnspan=1, sticky="nsew", padx=(0, 8))

            self.transfer_frame.grid_configure(row=2, column=2, padx=8, pady=0, sticky="ns")
            self.transfer_frame.columnconfigure(0, weight=1)
            self.transfer_frame.columnconfigure(1, weight=0)
            self.transfer_to_ignored_button.grid_configure(row=0, column=0, pady=(0, 8), padx=0, sticky="ew")
            self.transfer_to_active_button.grid_configure(row=1, column=0, pady=0, padx=0, sticky="ew")

            self.ignored_label.grid_configure(row=1, column=4, sticky="w", pady=0)
            self.ignored_keywords_listbox.grid_configure(row=2, column=4, columnspan=1, sticky="nsew", padx=(8, 0))

            self.add_area.grid_configure(row=3, column=0, columnspan=5, sticky="ew", pady=(14, 0))
            self.ignored_area.grid_configure(row=4, column=0, columnspan=5, sticky="nsew", pady=(14, 0))
            self.keyword_footer.grid_configure(row=5, column=0, columnspan=5, sticky="e", pady=(14, 0))

    def _on_keywords_modal_resized(self, event: tk.Event) -> None:
        if self.keyword_modal is None or event.widget is not self.keyword_modal:
            return
        self._apply_keywords_modal_layout(event.width)

    def _refresh_keyword_modal_lists(self) -> None:
        if self.keyword_modal is None or not self.keyword_modal.winfo_exists():
            return

        self.active_keywords_listbox.delete(0, tk.END)
        self.ignored_keywords_listbox.delete(0, tk.END)
        for keyword in self.all_keywords:
            if keyword in self.active_keywords:
                self.active_keywords_listbox.insert(tk.END, keyword)
                if keyword in self.custom_keywords:
                    self.active_keywords_listbox.itemconfig(tk.END, fg=self.custom_keyword_color)
            else:
                self.ignored_keywords_listbox.insert(tk.END, keyword)
                if keyword in self.custom_keywords:
                    self.ignored_keywords_listbox.itemconfig(tk.END, fg=self.custom_keyword_color)

    def _refresh_ignored_terms_listbox(self) -> None:
        if self.keyword_modal is None or not self.keyword_modal.winfo_exists():
            return
        self.ignored_terms_listbox.delete(0, tk.END)
        for term in self.ignored_terms:
            self.ignored_terms_listbox.insert(tk.END, term)

    def _submit_ignored_term(self) -> None:
        raw_term = self.new_ignored_var.get().strip()
        if not raw_term:
            self.new_keyword_status.set("Informe uma palavra desconsiderada valida.")
            return

        existing = self._find_term_case_insensitive(self.ignored_terms, raw_term)
        if existing is not None:
            self.new_keyword_status.set(f"'{existing}' ja esta na lista de desconsideradas.")
            self.new_ignored_var.set("")
            return

        self.ignored_terms.append(raw_term)
        self.new_ignored_var.set("")
        self._save_keyword_preferences()
        self._refresh_ignored_terms_listbox()
        self._update_reload_state()
        self.new_keyword_status.set(f"'{raw_term}' adicionada em desconsideradas.")

    def _remove_selected_ignored_terms(self) -> None:
        selected_indexes = list(self.ignored_terms_listbox.curselection())
        if not selected_indexes:
            self.new_keyword_status.set("Selecione ao menos uma palavra desconsiderada para remover.")
            return

        selected_terms = [self.ignored_terms_listbox.get(i) for i in selected_indexes]
        self.ignored_terms = [term for term in self.ignored_terms if term not in selected_terms]
        self._save_keyword_preferences()
        self._refresh_ignored_terms_listbox()
        self._update_reload_state()
        self.new_keyword_status.set(f"Removidas das desconsideradas: {', '.join(selected_terms)}.")

    def _move_keywords_to_ignored(self) -> None:
        selected = [self.active_keywords_listbox.get(i) for i in self.active_keywords_listbox.curselection()]
        if not selected:
            return
        for keyword in selected:
            self.active_keywords.discard(keyword)
        self._save_keyword_preferences()
        self._refresh_keyword_modal_lists()
        self._update_reload_state()

    def _move_keywords_to_active(self) -> None:
        selected = [self.ignored_keywords_listbox.get(i) for i in self.ignored_keywords_listbox.curselection()]
        if not selected:
            return
        for keyword in selected:
            self.active_keywords.add(keyword)
        self._save_keyword_preferences()
        self._refresh_keyword_modal_lists()
        self._update_reload_state()

    def _submit_new_keyword(self) -> None:
        raw_term = self.new_keyword_var.get().strip()
        if not raw_term:
            self.new_keyword_status.set("Informe uma palavra-chave valida.")
            return

        existing = self._find_keyword_case_insensitive(raw_term)
        if existing is None:
            self.all_keywords.append(raw_term)
            self.active_keywords.add(raw_term)
            self.custom_keywords.append(raw_term)
            self._save_keyword_preferences()
            self.new_keyword_status.set(f"'{raw_term}' adicionada e ativada.")
        else:
            self.active_keywords.add(existing)
            if existing in self.custom_keywords:
                self._save_keyword_preferences()
            self.new_keyword_status.set(f"'{existing}' ja existia e foi ativada.")

        self.new_keyword_var.set("")
        self._refresh_keyword_modal_lists()
        self._update_reload_state()

    def _delete_selected_custom_keywords(self) -> None:
        selected_active = [self.active_keywords_listbox.get(i) for i in self.active_keywords_listbox.curselection()]
        selected_ignored = [self.ignored_keywords_listbox.get(i) for i in self.ignored_keywords_listbox.curselection()]
        selected = list(dict.fromkeys(selected_active + selected_ignored))
        selected_ignored_terms = [self.ignored_terms_listbox.get(i) for i in self.ignored_terms_listbox.curselection()]

        removed_ignored_terms: list[str] = []
        for term in selected_ignored_terms:
            if term in self.ignored_terms:
                self.ignored_terms.remove(term)
                removed_ignored_terms.append(term)

        if not selected:
            if removed_ignored_terms:
                self._save_keyword_preferences()
                self._refresh_ignored_terms_listbox()
                self._update_reload_state()
                self.new_keyword_status.set(
                    f"Removidas desconsideradas: {', '.join(removed_ignored_terms)}."
                )
                return
            self.new_keyword_status.set("Selecione ao menos uma palavra para excluir.")
            return

        removable = [keyword for keyword in selected if keyword in self.custom_keywords]
        blocked = [keyword for keyword in selected if keyword not in self.custom_keywords]
        if not removable:
            if removed_ignored_terms:
                self._save_keyword_preferences()
                self._refresh_ignored_terms_listbox()
                self._update_reload_state()
                self.new_keyword_status.set(
                    f"Removidas desconsideradas: {', '.join(removed_ignored_terms)}."
                )
                return
            self.new_keyword_status.set("Apenas palavras inseridas podem ser excluidas.")
            return

        for keyword in removable:
            if keyword in self.custom_keywords:
                self.custom_keywords.remove(keyword)
            if keyword in self.active_keywords:
                self.active_keywords.remove(keyword)
            self.all_keywords = [item for item in self.all_keywords if item != keyword]

        self._save_keyword_preferences()
        self._refresh_keyword_modal_lists()
        self._refresh_ignored_terms_listbox()
        self._update_reload_state()

        if blocked:
            parts = [f"Excluidas: {', '.join(removable)}.", f"Padroes ignoradas: {', '.join(blocked)}."]
        else:
            parts = [f"Excluidas: {', '.join(removable)}."]
        if removed_ignored_terms:
            parts.append(f"Desconsideradas removidas: {', '.join(removed_ignored_terms)}.")
        self.new_keyword_status.set(" ".join(parts))

    def _find_keyword_case_insensitive(self, target: str) -> str | None:
        return self._find_term_case_insensitive(self.all_keywords, target)

    def _find_term_case_insensitive(self, terms: list[str], target: str) -> str | None:
        target_lower = target.lower()
        for term in terms:
            if term.lower() == target_lower:
                return term
        return None

    def _on_analysis_error(self, error_message: str) -> None:
        self.btn_open.configure(state="normal")
        self.reload_context_button.configure(state="normal")
        self.status_var.set("Falha na analise")
        messagebox.showerror("Erro na analise", f"Nao foi possivel processar o arquivo.\n{error_message}")

    def _set_output_text(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text)
        self.output.configure(state="disabled")

    def clear_view(self) -> None:
        self.file_path = None
        self.analysis_content = ""
        self.displayed_content = ""
        self.source_lines = []
        self.exception_blocks = []
        self.selected_block_index = -1
        self.highlights = []
        self.current_highlight_index = -1
        self.pending_context_reload = False
        self.pending_keyword_reload = False
        self.reload_keep_index = 0
        self.applied_context = self.context_var.get()
        self.applied_keywords = tuple(self._active_keywords_in_order())
        self.applied_ignored_terms = tuple(self.ignored_terms)

        self.search_var.set("")
        self._set_output_text("")
        self._populate_exception_cards([])
        self._refresh_found_keywords_panel()
        self._set_filters_visible(False)

        self.file_card.set("-")
        self.blocks_card.set("0")
        self.matches_card.set("0")
        self.status_var.set("Nenhum arquivo selecionado")

    def search_keyword(self) -> None:
        term = self.search_var.get().strip()
        self.highlights = []
        self.current_highlight_index = -1

        if not term:
            self.matches_card.set("0")
            self._render_current_search_highlights()
            return

        if self.exception_blocks:
            source_blocks = [self._build_stack_current_text(i) for i in range(len(self.exception_blocks))]
        else:
            source_blocks = [self.displayed_content]
        for block_index, block_text in enumerate(source_blocks):
            for start, end in self._find_term_offsets(block_text, term):
                self.highlights.append((block_index, start, end))

        self.matches_card.set(str(len(self.highlights)))

        if self.highlights:
            self.current_highlight_index = 0
            self._scroll_to_highlight(0)
        else:
            self._render_current_search_highlights()

    def _find_term_offsets(self, content: str, term: str) -> list[tuple[int, int]]:
        matches: list[tuple[int, int]] = []
        if not term:
            return matches

        content_lower = content.lower()
        term_lower = term.lower()
        ignored_spans = self._find_ignored_spans(content_lower)
        start = 0
        while True:
            found = content_lower.find(term_lower, start)
            if found == -1:
                break
            end = found + len(term)
            if not self._span_inside_any_ignored(found, end, ignored_spans):
                matches.append((found, end))
            start = end
        return matches

    def _find_ignored_spans(self, content_lower: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        if not self.ignored_terms:
            return spans
        for ignored in self.ignored_terms:
            ignored_clean = ignored.strip().lower()
            if not ignored_clean:
                continue
            start = 0
            while True:
                found = content_lower.find(ignored_clean, start)
                if found == -1:
                    break
                spans.append((found, found + len(ignored_clean)))
                start = found + len(ignored_clean)
        return spans

    def _span_inside_any_ignored(self, start: int, end: int, ignored_spans: list[tuple[int, int]]) -> bool:
        for ignored_start, ignored_end in ignored_spans:
            if start >= ignored_start and end <= ignored_end:
                return True
        return False

    def _render_current_search_highlights(self) -> None:
        self.output.configure(state="normal")
        self.output.tag_remove("match", "1.0", tk.END)
        self.output.tag_remove("current", "1.0", tk.END)

        if not self.highlights:
            self.output.configure(state="disabled")
            return

        active_block = self.selected_block_index if self.exception_blocks else 0
        for idx, (block_index, start, end) in enumerate(self.highlights):
            if block_index != active_block:
                continue
            start_idx = f"1.0+{start}c"
            end_idx = f"1.0+{end}c"
            self.output.tag_add("match", start_idx, end_idx)
            if idx == self.current_highlight_index:
                self.output.tag_add("current", start_idx, end_idx)
                self.output.see(start_idx)

        self.output.configure(state="disabled")

    def _scroll_to_highlight(self, index: int) -> None:
        if not self.highlights:
            return

        block_index, _start, _end = self.highlights[index]
        if self.exception_blocks and block_index != self.selected_block_index:
            self._select_exception_block(block_index)
        self._render_current_search_highlights()

    def next_highlight(self) -> None:
        if not self.highlights:
            return
        self.current_highlight_index = (self.current_highlight_index + 1) % len(self.highlights)
        self._scroll_to_highlight(self.current_highlight_index)

    def previous_highlight(self) -> None:
        if not self.highlights:
            return
        self.current_highlight_index = (self.current_highlight_index - 1) % len(self.highlights)
        self._scroll_to_highlight(self.current_highlight_index)

    def export_results(self) -> None:
        if not self.analysis_content.strip():
            messagebox.showwarning("Aviso", "Nao ha dados para exportar.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt")],
            title="Salvar analise",
        )
        if not save_path:
            return

        output_path = Path(save_path)
        try:
            with output_path.open("w", encoding="utf-8", newline="\n") as out:
                out.write(self.analysis_content)
        except OSError as exc:
            messagebox.showerror("Erro", f"Falha ao exportar arquivo:\n{exc}")
            return

        messagebox.showinfo("Exportacao concluida", f"Arquivo salvo em:\n{output_path}")

    def export_current_block(self) -> None:
        if not self.exception_blocks or self.selected_block_index < 0 or self.selected_block_index >= len(self.exception_blocks):
            messagebox.showwarning("Aviso", "Nenhum bloco selecionado para exportar.")
            return

        block_content = self.exception_blocks[self.selected_block_index]
        if not block_content.strip():
            messagebox.showwarning("Aviso", "O bloco selecionado esta vazio.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt")],
            title="Salvar bloco selecionado",
        )
        if not save_path:
            return

        output_path = Path(save_path)
        try:
            with output_path.open("w", encoding="utf-8", newline="\n") as out:
                out.write(block_content)
        except OSError as exc:
            messagebox.showerror("Erro", f"Falha ao exportar bloco:\n{exc}")
            return

        messagebox.showinfo("Exportacao concluida", f"Bloco salvo em:\n{output_path}")


def main() -> None:
    root = tk.Tk()
    LogAnalyzerApp(root)
    root.mainloop()
