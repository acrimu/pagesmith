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
        self.root.title("PDF Page Rearranger")
        self.root.geometry("960x700")
        self.root.minsize(640, 420)

        self.source_path: Path | None = None
        self.document = None
        self.pages: list[dict] = []
        self.photo_refs: list[tk.PhotoImage] = []
        self.drag_index: int | None = None
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
        ttk.Button(toolbar, text="Save reordered PDF…", command=self.save_pdf).pack(side="left", padx=(8, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(toolbar, text="Move left", command=lambda: self.move_selected(-1)).pack(side="left")
        ttk.Button(toolbar, text="Move right", command=lambda: self.move_selected(1)).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Rotate 90°", command=self.rotate_selected).pack(side="left", padx=(6, 0))
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
            messagebox.showinfo("Choose one PDF", "Drop one PDF at a time.")
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

        if self.document is not None:
            self.document.close()
        self.document = new_doc
        self.source_path = Path(filename)
        self.pages = [{"source_index": i, "rotation": 0} for i in range(len(new_doc))]
        self.file_label.configure(text=f"{self.source_path.name}  •  {len(self.pages)} pages")
        self.status.set("Drag page thumbnails to change their order. Select a page for move/rotate controls.")
        self._render_pages()

    def _render_pages(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self.photo_refs.clear()
        if not self.pages or self.document is None:
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
            page = self.document[entry["source_index"]]
            rect = page.rect
            max_image_h = max(1, int(420 * self.zoom.get() / 100))
            scale = min(max(1, cell_w - 2) / rect.width, max_image_h / rect.height)
            image_sizes.append((max(1, int(rect.width * scale)), max(1, int(rect.height * scale))))
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
            page = self.document[entry["source_index"]]
            # Scale the preview to the full available column width and let the
            # card height follow the PDF page's aspect ratio, avoiding letterbox gaps.
            render_scale = image_sizes[i][0] / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
            image = tk.PhotoImage(data=self._pixmap_to_ppm(pix))
            self.photo_refs.append(image)

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
                    self.selected_index = self.drag_index
                    self._render_pages()
                    return
        self.selected_index = None
        self._render_pages()

    def _canvas_drag(self, event: tk.Event) -> None:
        if self.drag_index is None or not self.pages:
            return
        width = max(self.canvas.winfo_width(), 300)
        cell_w = max(150, int(170 * self.zoom.get() / 100))
        columns = max(1, width // cell_w)
        cell_w = width // columns
        label_h = max(14, int(16 * self.zoom.get() / 100))
        gap = max(0, int(2 * self.zoom.get() / 100))
        cell_h = int(420 * self.zoom.get() / 100) + label_h + gap
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        col = min(columns - 1, max(0, int(x // cell_w)))
        row = max(0, int(y // cell_h))
        target = min(len(self.pages) - 1, row * columns + col)
        self._move_page(self.drag_index, target)
        self.drag_index = target

    def _canvas_release(self, _event: tk.Event) -> None:
        self.drag_index = None

    def _mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _move_page(self, old: int, new: int) -> None:
        if old == new or not (0 <= old < len(self.pages) and 0 <= new < len(self.pages)):
            return
        item = self.pages.pop(old)
        self.pages.insert(new, item)
        self.selected_index = new
        self._render_pages()

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
        self._render_pages()

    def save_pdf(self) -> None:
        if self.document is None or self.source_path is None:
            self.status.set("Open a PDF first.")
            return
        filename = filedialog.asksaveasfilename(
            title="Save reordered PDF", initialdir=str(self.source_path.parent),
            initialfile=f"{self.source_path.stem}_reordered.pdf",
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
        )
        if not filename:
            return
        try:
            output = fitz.open()
            for entry in self.pages:
                output.insert_pdf(self.document, from_page=entry["source_index"], to_page=entry["source_index"])
                rotation = entry["rotation"]
                if rotation:
                    output[-1].set_rotation((output[-1].rotation + rotation) % 360)
            output.save(filename, garbage=4, deflate=True)
            output.close()
        except Exception as exc:
            messagebox.showerror("Could not save PDF", str(exc))
            return
        self.status.set(f"Saved {Path(filename).name}")
        messagebox.showinfo("PDF saved", f"Your reordered PDF was saved to:\n{filename}")

    def _close(self) -> None:
        if self.document is not None:
            self.document.close()
        self.root.destroy()


def main() -> None:
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    PdfPageRearranger(root)
    root.mainloop()


if __name__ == "__main__":
    main()
