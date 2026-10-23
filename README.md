# PDF Page Rearranger

A small Windows desktop app for manually changing the order of PDF pages.

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

- Choose **Open PDF…** and select a file, or drag one PDF from File Explorer onto the app window.
- Drag thumbnails to rearrange pages. The displayed page numbers update to show the new order.
- Select a page and use **Move left** / **Move right** for one-position changes, or **Rotate 90°** to rotate it clockwise.
- Choose **Save reordered PDF…** to save a new PDF. The original file is not overwritten by default.

The app uses Tkinter (included with most Windows Python installations) and PyMuPDF for PDF reading and writing.
