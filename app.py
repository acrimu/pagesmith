"""A small desktop app for manually rearranging PDF pages."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import fitz  # PyMuPDF
except ImportError:  # Give a useful message when dependencies have not been installed.
    fitz = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None


class PdfPageRearranger:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PageSmith")
        self.root.geometry("960x700")
        self.root.minsize(640, 420)

        self.source_path: Path | None = None
        self.document = None
        self.documents: list[dict] = []
        self.pages: list[dict] = []
        self.has_unsaved_changes = False
        self.photo_refs: list[tk.PhotoImage] = []
        self.drag_index: int | None = None
        self.drag_overlay: int | None = None
        self.drag_start_xy: tuple[float, float] | None = None
        self.drag_start_page: int | None = None
        self.animation_id: str | None = None
        self.tile_positions: dict[int, tuple[float, float]] = {}
        self.drag_images: dict[int, tk.PhotoImage] = {}
        self.drag_start_order: list[dict] | None = None
        self.drag_placeholder: int | None = None
        self.drag_image: tk.PhotoImage | None = None
        self.animating_drop = False
        self.zoom = tk.IntVar(value=100)
        self.zoom_entry_var = tk.StringVar(value="100%")
        self._setup_file_drop()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        if fitz is None:
            self.root.after(100, self._show_missing_dependency)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(1, 1, 1, 2))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open PDF…", command=self.open_pdf).pack(side="left")
        ttk.Button(toolbar, text="Add PDF…", command=self.add_pdf).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Clear all", command=self.clear_all).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Save reordered PDF…", command=self.save_pdf).pack(side="left", padx=(8, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(toolbar, text="Move left", command=lambda: self.move_selected(-1)).pack(side="left")
        ttk.Button(toolbar, text="Move right", command=lambda: self.move_selected(1)).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Rotate 90°", command=self.rotate_selected).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Delete page", command=self.delete_selected).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Insert blank page", command=self.insert_blank_page).pack(side="left", padx=(6, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Label(toolbar, text="Zoom").pack(side="left")
        self.zoom_presets = ttk.Combobox(
            toolbar, state="normal", width=7, textvariable=self.zoom_entry_var,
            values=("50%", "75%", "100%", "125%", "150%", "200%", "300%", "500%", "750%", "1000%"),
        )
        self.zoom_presets.set("100%")
        self.zoom_presets.bind("<<ComboboxSelected>>", self._zoom_preset_selected)
        self.zoom_presets.pack(side="left", padx=(6, 4))
        self.zoom_presets.bind("<Return>", self._apply_zoom_entry)
        self.zoom_presets.bind("<FocusOut>", self._restore_zoom_entry)

        self.file_label = ttk.Label(self.root, text="Open a PDF to get started", padding=(2, 1, 2, 3))
        self.file_label.pack(fill="x")

        body = ttk.Frame(self.root, padding=(1, 0, 1, 2))
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#e9edf2", highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._render_pages())
        self.canvas.bind("<Button-1>", self._canvas_click)
        self.canvas.bind("<B1-Motion>", self._canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_release)
        self.canvas.bind("<MouseWheel>", self._mousewheel)

        self.status = tk.StringVar(value="Drag page thumbnails to change their order.")
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=(2, 2)).pack(fill="x")

    def _setup_file_drop(self) -> None:
        if DND_FILES is None:
            self.root.after(100, self._show_missing_drop_dependency)
            return
        # Register on the main window and content area so a PDF can be dropped
        # anywhere in the app, including over the thumbnail canvas.
        for widget in (self.root,):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_file_drop)

    def _show_missing_drop_dependency(self) -> None:
        messagebox.showinfo(
            "Install drag and drop support",
            "To enable dropping PDFs from File Explorer, run:\n\n"
            "python -m pip install -r requirements.txt\n\n"
            "Then restart the app.",
        )

    def _on_file_drop(self, event: tk.Event) -> str:
        try:
            dropped = self.root.tk.splitlist(event.data)
        except (tk.TclError, AttributeError):
            dropped = [event.data]
        pdfs = [Path(path) for path in dropped if str(path).lower().endswith(".pdf")]
        if not pdfs:
            messagebox.showerror("No PDF found", "Drop a PDF file onto the app.")
        elif len(pdfs) > 1:
            for pdf_path in pdfs:
                self._append_pdf(pdf_path)
        else:
            if self.documents:
                self._append_pdf(pdfs[0])
            else:
                self.load_pdf(pdfs[0])
        return "break"

    def _show_missing_dependency(self) -> None:
        if fitz is None:
            messagebox.showinfo(
                "Install dependency",
                "This app needs PyMuPDF. In a terminal in this folder, run:\n\n"
                "python -m pip install -r requirements.txt",
            )

    def open_pdf(self) -> None:
        if fitz is None:
            self._show_missing_dependency()
            return
        filename = filedialog.askopenfilename(
            title="Open PDF", filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not filename:
            return
        self.load_pdf(Path(filename))

    def load_pdf(self, filename: Path) -> None:
        if fitz is None:
            self._show_missing_dependency()
            return
        try:
            new_doc = fitz.open(filename)
            if not new_doc.is_pdf:
                new_doc.close()
                raise ValueError("The selected file is not a PDF.")
            if len(new_doc) == 0:
                new_doc.close()
                raise ValueError("The selected PDF has no pages.")
        except Exception as exc:
            messagebox.showerror("Could not open PDF", str(exc))
            return

        if self.has_unsaved_changes and not self._confirm_discard_changes():
            new_doc.close()
            return

        self._close_documents()
        self.document = new_doc
        self.documents = [{"document": new_doc, "path": Path(filename)}]
        self.source_path = Path(filename)
        self.pages = [{"document_index": 0, "source_index": i, "rotation": 0} for i in range(len(new_doc))]
        self.has_unsaved_changes = False
        self.file_label.configure(text=f"{self.source_path.name}  •  {len(self.pages)} pages")
        self.status.set("Drag page thumbnails to change their order. Select a page for move/rotate controls.")
        self._render_pages()

    def add_pdf(self) -> None:
        if fitz is None:
            self._show_missing_dependency()
            return
        if not self.documents:
            self.open_pdf()
            return
        filenames = filedialog.askopenfilenames(
            title="Add PDF pages", filetypes=[("PDF files", "*.pdf")]
        )
        for filename in filenames:
            self._append_pdf(Path(filename))

    def _append_pdf(self, filename: Path) -> None:
        try:
            doc = fitz.open(filename)
            if not doc.is_pdf or len(doc) == 0:
                doc.close()
                raise ValueError("The selected file is not a non-empty PDF.")
        except Exception as exc:
            messagebox.showerror("Could not add PDF", f"{filename.name}: {exc}")
            return
        document_index = len(self.documents)
        self.documents.append({"document": doc, "path": filename})
        self.pages.extend({"document_index": document_index, "source_index": i, "rotation": 0}
                          for i in range(len(doc)))
        self.has_unsaved_changes = True
        self.file_label.configure(text=f"{len(self.documents)} documents  •  {len(self.pages)} pages")
        self.status.set(f"Added {filename.name}; its pages are at the end. Drag them to rearrange.")
        self._render_pages()

    def delete_selected(self) -> None:
        index = self._selected_index()
        if index is None or not 0 <= index < len(self.pages):
            self.status.set("Select a page to delete.")
            return
        if not messagebox.askyesno(
            "Delete page?",
            f"Delete page {index + 1}? This will remove it from the saved PDF.",
            icon="warning",
        ):
            return
        removed = self.pages.pop(index)
        self.has_unsaved_changes = True
        if self.pages:
            self.selected_index = min(index, len(self.pages) - 1)
        else:
            self.selected_index = None
        self.file_label.configure(text=f"{len(self.documents)} documents  •  {len(self.pages)} pages")
        origin = "blank page" if removed.get("blank") else self.documents[removed["document_index"]]["path"].name
        self.status.set(f"Deleted page {index + 1} ({origin}).")
        self._render_pages()

    def clear_all(self) -> None:
        if self.has_unsaved_changes and not self._confirm_discard_changes():
            return
        self._close_documents()
        self.pages.clear()
        self.has_unsaved_changes = False
        self.selected_index = None
        self.drag_index = None
        self.drag_overlay = None
        self.drag_image = None
        self.file_label.configure(text="Open or drop a PDF to get started")
        self.status.set("All documents cleared.")
        self._render_pages()

    def insert_blank_page(self) -> None:
        width, height = 595, 842  # A4 portrait default.
        anchor_index = self._selected_index()
        anchor = self.pages[anchor_index] if anchor_index is not None else None
        if anchor and not anchor.get("blank"):
            source_doc = self.documents[anchor["document_index"]]["document"]
            rect = source_doc[anchor["source_index"]].rect
            width, height = rect.width, rect.height
        elif not anchor and self.pages:
            for existing in reversed(self.pages):
                if not existing.get("blank"):
                    rect = self.documents[existing["document_index"]]["document"][existing["source_index"]].rect
                    width, height = rect.width, rect.height
                    break
        blank = {"blank": True, "width": width, "height": height, "rotation": 0}
        selected = self._selected_index()
        insert_at = selected if selected is not None else len(self.pages)
        self.pages.insert(insert_at, blank)
        self.has_unsaved_changes = True
        self.selected_index = insert_at
        self.file_label.configure(text=f"{len(self.documents)} documents  •  {len(self.pages)} pages")
        self.status.set(f"Inserted a blank page at position {insert_at + 1}.")
        self._render_pages()

    def _render_pages(self, drag_placeholder: int | None = None) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self.photo_refs.clear()
        self.tile_positions.clear()
        self.drag_images.clear()
        if not self.pages:
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        width = max(self.canvas.winfo_width(), 300)
        cell_w = max(150, int(170 * self.zoom.get() / 100))
        columns = max(1, width // cell_w)
        cell_w = width // columns
        label_h = max(14, int(16 * self.zoom.get() / 100))
        gap = max(0, int(2 * self.zoom.get() / 100))
        selected = self._selected_index()
        row_heights: list[int] = []
        image_sizes: list[tuple[int, int]] = []
        for entry in self.pages:
            if entry.get("blank"):
                page_width, page_height = entry["width"], entry["height"]
            else:
                doc = self.documents[entry["document_index"]]["document"]
                page = doc[entry["source_index"]]
                page_width, page_height = page.rect.width, page.rect.height
            max_image_h = max(1, int(420 * self.zoom.get() / 100))
            scale = min(max(1, cell_w - 2) / page_width, max_image_h / page_height)
            image_sizes.append((max(1, int(page_width * scale)), max(1, int(page_height * scale))))
        for row in range((len(self.pages) + columns - 1) // columns):
            row_start = row * columns
            row_end = min(len(self.pages), row_start + columns)
            row_heights.append(max(image_sizes[i][1] for i in range(row_start, row_end)) + label_h + gap)
        row_tops = []
        cursor_y = 0
        for height in row_heights:
            row_tops.append(cursor_y)
            cursor_y += height
        for i, entry in enumerate(self.pages):
            row, col = divmod(i, columns)
            x, y = col * cell_w, row_tops[row]
            self.tile_positions[i] = (x + cell_w / 2, y + image_sizes[i][1] / 2)
            if i == drag_placeholder:
                self.canvas.create_rectangle(x, y, x + cell_w, y + image_sizes[i][1] + label_h + gap,
                                             fill="#d8dee7", outline="#2674d9", width=2,
                                             dash=(5, 3), tags=(f"page:{i}", "page", "placeholder"))
                self.canvas.create_text(x + cell_w / 2, y + image_sizes[i][1] + label_h / 2,
                                        text=f"Page {i + 1}", font=("Segoe UI", 10, "bold"),
                                        fill="#6b7788", tags=(f"page:{i}", "page", "placeholder"))
                continue
            if entry.get("blank"):
                image = tk.PhotoImage(width=image_sizes[i][0], height=image_sizes[i][1])
                self.photo_refs.append(image)
                self.drag_images[i] = image
                is_selected = i == selected
                border = "#2674d9" if is_selected else "#aab4c0"
                bg = "#dceaff" if is_selected else "#f9fafb"
                image_h = image_sizes[i][1]
                self.canvas.create_rectangle(x, y, x + cell_w, y + image_h + label_h + gap,
                                             fill=bg, outline=border, width=2 if is_selected else 1,
                                             tags=(f"page:{i}", "page"))
                self.canvas.create_image(x + cell_w / 2, y + image_h / 2,
                                         image=image, anchor="center", tags=(f"page:{i}", "page"))
                self.canvas.create_text(x + cell_w / 2, y + image_h + label_h / 2,
                                        text=f"Page {i + 1} (blank)", font=("Segoe UI", 10, "bold"),
                                        fill="#253244", tags=(f"page:{i}", "page"))
                continue
            doc = self.documents[entry["document_index"]]["document"]
            page = doc[entry["source_index"]]
            # Scale the preview to the full available column width and let the
            # card height follow the PDF page's aspect ratio, avoiding letterbox gaps.
            render_scale = image_sizes[i][0] / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
            image = tk.PhotoImage(data=self._pixmap_to_ppm(pix))
            self.photo_refs.append(image)
            self.drag_images[i] = image

            is_selected = i == selected
            border = "#2674d9" if is_selected else "#aab4c0"
            bg = "#dceaff" if is_selected else "#f9fafb"
            image_h = image_sizes[i][1]
            self.canvas.create_rectangle(x, y, x + cell_w, y + image_h + label_h + gap,
                                         fill=bg, outline=border, width=2 if is_selected else 1,
                                         tags=(f"page:{i}", "page"))
            self.canvas.create_image(x + cell_w / 2, y + image_h / 2,
                                     image=image, anchor="center", tags=(f"page:{i}", "page"))
            self.canvas.create_text(x + cell_w / 2, y + image_h + label_h / 2,
                                    text=f"Page {i + 1}" + (f"  ↻{entry['rotation']}°" if entry["rotation"] else ""),
                                    font=("Segoe UI", 10, "bold"), fill="#253244", tags=(f"page:{i}", "page"))
        self.canvas.configure(scrollregion=(0, 0, width, cursor_y))

    def _set_zoom(self, value: int) -> None:
        self.zoom.set(value)
        self.zoom_entry_var.set(f"{value}%")
        self._render_pages()

    def _zoom_preset_selected(self, _event: tk.Event) -> None:
        self._set_zoom(int(self.zoom_presets.get().rstrip("%")))

    def _apply_zoom_entry(self, _event: tk.Event | None = None) -> str:
        raw_value = self.zoom_entry_var.get().strip().rstrip("%").strip()
        try:
            value = int(raw_value)
            if not 50 <= value <= 1000:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid zoom", "Enter a whole-number zoom from 50% to 1000%.")
            self.zoom_entry_var.set(f"{self.zoom.get()}%")
            self.zoom_presets.focus_set()
            return "break"
        self._set_zoom(value)
        return "break"

    def _restore_zoom_entry(self, _event: tk.Event | None = None) -> None:
        self.zoom_entry_var.set(f"{self.zoom.get()}%")

    @staticmethod
    def _pixmap_to_ppm(pix: fitz.Pixmap) -> bytes:
        # Tk PhotoImage supports PPM directly; convert RGB pixmap samples to its P6 form.
        rgb = fitz.Pixmap(fitz.csRGB, pix) if pix.n != 3 else pix
        return f"P6\n{rgb.width} {rgb.height}\n255\n".encode("ascii") + rgb.samples

    def _selected_index(self) -> int | None:
        current = self.canvas.find_withtag("selected") if hasattr(self, "canvas") else ()
        return getattr(self, "selected_index", None)

    def _canvas_click(self, event: tk.Event) -> None:
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        hits = self.canvas.find_overlapping(x, y, x, y)
        self.drag_index = None
        for item in reversed(hits):
            for tag in self.canvas.gettags(item):
                if tag.startswith("page:"):
                    self.drag_index = int(tag.split(":", 1)[1])
                    self.drag_start_page = self.drag_index
                    self.drag_start_order = self.pages.copy()
                    self.drag_start_xy = (x, y)
                    self._pre_drag_positions = self.tile_positions.copy()
                    self.drag_image = self.drag_images.get(self.drag_index)
                    self.selected_index = self.drag_index
                    self._render_pages()
                    return
        self.selected_index = None
        self._render_pages()

    def _canvas_drag(self, event: tk.Event) -> None:
        if self.drag_index is None or not self.pages:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.drag_overlay is None and self.drag_start_xy is not None:
            if abs(x - self.drag_start_xy[0]) + abs(y - self.drag_start_xy[1]) < 8:
                return
            self._create_drag_overlay()
        if self.drag_overlay is None:
            return

        self.canvas.coords(self.drag_overlay, x, y)
        target = self._index_at_position(x, y)
        if target is not None and target != self.drag_placeholder:
            source = self.drag_start_page
            if source is None or self.drag_start_order is None:
                return
            reordered = self.drag_start_order.copy()
            moved = reordered.pop(source)
            target = max(0, min(target, len(reordered)))
            reordered.insert(target, moved)
            if reordered != self.pages:
                self.has_unsaved_changes = True
            self.pages = reordered
            self.selected_index = target
            self.drag_index = target
            self.drag_placeholder = target
            self._render_pages(drag_placeholder=target)
            self._create_drag_overlay()
            self.canvas.coords(self.drag_overlay, x, y)

    def _index_at_position(self, x: float, y: float) -> int | None:
        hits = self.canvas.find_overlapping(x, y, x, y)
        for item in reversed(hits):
            for tag in self.canvas.gettags(item):
                if tag.startswith("page:"):
                    return int(tag.split(":", 1)[1])
        return None

    def _create_drag_overlay(self) -> None:
        if self.drag_index is None:
            return
        if self.drag_overlay is not None:
            self.canvas.delete(self.drag_overlay)
        image = self.drag_image or self.drag_images.get(self.drag_index)
        if image is None:
            return
        self.drag_overlay = self.canvas.create_image(
            self.canvas.canvasx(0), self.canvas.canvasy(0), image=image,
            anchor="center", tags=("drag-overlay",),
        )
        self.canvas.tag_raise(self.drag_overlay)

    def _canvas_release(self, _event: tk.Event) -> None:
        if self.drag_overlay is not None and self.drag_index is not None:
            target = self.tile_positions.get(self.drag_index)
            if target is not None:
                self.animating_drop = True
                self._slide_overlay_to(self.drag_overlay, target, 0)
            else:
                self.canvas.delete(self.drag_overlay)
                self.drag_overlay = None
                self._render_pages()
        else:
            self._render_pages()
        self.drag_index = None
        self.drag_start_page = None
        self.drag_start_xy = None
        self.drag_start_order = None
        self.drag_placeholder = None

    def _slide_overlay_to(self, overlay: int, target: tuple[float, float], frame: int) -> None:
        frames = 12
        if frame == 0:
            self._overlay_start = tuple(self.canvas.coords(overlay))
        start = self._overlay_start
        t = min(1.0, frame / frames)
        eased = 1 - (1 - t) ** 3
        self.canvas.coords(overlay, start[0] + (target[0] - start[0]) * eased,
                           start[1] + (target[1] - start[1]) * eased)
        if frame < frames:
            self.root.after(16, lambda: self._slide_overlay_to(overlay, target, frame + 1))
        else:
            self.canvas.delete(overlay)
            self.drag_overlay = None
            self.animating_drop = False
            self.drag_image = None
            self._render_pages()

    def _mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _move_page(self, old: int, new: int) -> None:
        if old == new or not (0 <= old < len(self.pages) and 0 <= new < len(self.pages)):
            return
        item = self.pages.pop(old)
        self.pages.insert(new, item)
        self.has_unsaved_changes = True
        self.selected_index = new
        self._render_pages()

    def _animate_reorder(self, old: int, new: int) -> None:
        """Glide all page tiles into their final positions after a drag."""
        if old == new or not self.pages:
            return
        starts = getattr(self, "_pre_drag_positions", {})
        ends = self.tile_positions.copy()
        moves: list[tuple[int, float, float, float, float]] = []
        for index, (end_x, end_y) in ends.items():
            start = starts.get(index)
            if start is None or start == (end_x, end_y):
                continue
            items = self.canvas.find_withtag(f"page:{index}")
            if items:
                moves.append((index, start[0], start[1], end_x, end_y))
                self.canvas.move(f"page:{index}", start[0] - end_x, start[1] - end_y)
        if moves:
            self._run_slide_animation(moves, 0)

    def _run_slide_animation(self, moves: list[tuple[int, float, float, float, float]], frame: int) -> None:
        frames = 10
        t = min(1.0, frame / frames)
        # Ease out cubic for a quick start and gentle settle.
        eased = 1 - (1 - t) ** 3
        for index, start_x, start_y, end_x, end_y in moves:
            dx = (end_x - start_x) * eased
            dy = (end_y - start_y) * eased
            current = self.canvas.coords(self.canvas.find_withtag(f"page:{index}")[0])
            if len(current) >= 2:
                self.canvas.move(f"page:{index}", start_x + dx - current[0], start_y + dy - current[1])
        if frame < frames:
            self.root.after(16, lambda: self._run_slide_animation(moves, frame + 1))
        else:
            for index, (x, y) in self.tile_positions.items():
                item = self.canvas.find_withtag(f"page:{index}")[0]
                current = self.canvas.coords(item)
                self.canvas.move(f"page:{index}", x - current[0], y - current[1])

    def move_selected(self, delta: int) -> None:
        index = self._selected_index()
        if index is None:
            self.status.set("Select a page first.")
            return
        self._move_page(index, index + delta)

    def rotate_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            self.status.set("Select a page first.")
            return
        self.pages[index]["rotation"] = (self.pages[index]["rotation"] + 90) % 360
        self.has_unsaved_changes = True
        self._render_pages()

    def save_pdf(self) -> None:
        if not self.pages:
            self.status.set("Open a PDF first.")
            return
        filename = filedialog.asksaveasfilename(
            title="Save reordered PDF",
            initialdir=str(self.source_path.parent) if self.source_path else None,
            initialfile=f"{self.source_path.stem}_pagesmith.pdf" if self.source_path else "pagesmith.pdf",
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
        )
        if not filename:
            return
        try:
            output = fitz.open()
            for entry in self.pages:
                if entry.get("blank"):
                    page = output.new_page(width=entry["width"], height=entry["height"])
                else:
                    source = self.documents[entry["document_index"]]["document"]
                    output.insert_pdf(source, from_page=entry["source_index"], to_page=entry["source_index"])
                    page = output[-1]
                rotation = entry["rotation"]
                if rotation:
                    page.set_rotation((page.rotation + rotation) % 360)
            output.save(filename, garbage=4, deflate=True)
            output.close()
        except Exception as exc:
            messagebox.showerror("Could not save PDF", str(exc))
            return
        self.status.set(f"Saved {Path(filename).name}")
        self.has_unsaved_changes = False
        messagebox.showinfo("PDF saved", f"Your reordered PDF was saved to:\n{filename}")

    def _confirm_discard_changes(self) -> bool:
        return messagebox.askyesno(
            "Discard unsaved changes?",
            "Your page order or contents have changed. Continue and lose those changes?",
            icon="warning",
        )

    def _close(self) -> None:
        if self.has_unsaved_changes and not self._confirm_discard_changes():
            return
        self._close_documents()
        self.root.destroy()

    def _close_documents(self) -> None:
        for source in self.documents:
            source["document"].close()
        self.documents.clear()
        self.document = None


def main() -> None:
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    PdfPageRearranger(root)
    root.mainloop()


if __name__ == "__main__":
    main()
