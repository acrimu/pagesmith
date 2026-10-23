# PageSmith

PageSmith is a small Windows desktop app for combining PDFs and manually managing page order.

## Run

1. Install Python 3.10 or newer.
2. Open PowerShell in this folder and install the dependency:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the app:

   ```powershell
   python app.py
   ```

## Use

- Choose **Open PDF…** and select a file to start a set, or drag a PDF from File Explorer onto the app window. Dropped PDFs are appended after the existing pages.
- Choose **Add PDF…** to append pages from one or more PDFs to the current document. Added pages appear at the end and can be moved anywhere in the page order.
- Choose **Clear all** to remove all loaded documents and start a new set.
- Choose **Insert blank page** to add an empty page before the selected page, or at the end when no page is selected. It matches the selected page's size when possible.
- Drag thumbnails to rearrange pages. The displayed page numbers update to show the new order.
- Select a page and use **Move left** / **Move right** for one-position changes, **Rotate 90°** to rotate it clockwise, or **Delete page** to remove it from the output.
- Choose **Save reordered PDF…** to save a new PDF. The original file is not overwritten by default.

The app uses Tkinter (included with most Windows Python installations) and PyMuPDF for PDF reading and writing.
