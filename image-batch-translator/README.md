# Image Batch Translator & Smart Renamer

Desktop application written in Python (Tkinter GUI, single-file runnable) to batch translate images that share the same layout structure (such as certificates, receipts, game cards, UI screenshots, textbook pages), paint over original text with the median background color, render translated text with auto word-wrap and font resizing, and export renamed images according to customizable templates.

---

## 🌟 Key Features

1. **Natural Order Sorting**: Processes images in true natural numeric order (`img2.png` before `img10.png`). Supported formats: `PNG`, `JPG`, `JPEG`, `BMP`, `WEBP`, `TIFF`.
2. **Interactive Region Definition**:
   - Drag mouse on the sample image to draw multiple text regions.
   - Coordinates are stored as **relative ratios [0.0 - 1.0]**, so regions automatically scale to every image even if dimensions slightly vary.
   - Live region badges (`#1`, `#2`...) with highlight color indicators.
   - Region list with coordinate inspector and pixel-precise manual adjustment (`X1`, `Y1`, `X2`, `Y2`).
3. **Multi-Language OCR & Translation**:
   - OCR powered by `pytesseract` with intelligent image preprocessing: grayscale conversion, autocontrast enhancement, Lanczos upscaling for short text lines, and customizable `--psm` page segmentation modes.
   - Translation via Google Translate (`deep-translator`, no API key required).
   - In-memory translation caching to minimize network requests.
   - Graceful network error handling so batch processing never crashes.
   - Non-blocking execution in background threads with live progress bar.
4. **Editable Results Table (Treeview)**:
   - Columns: `Original File`, `Region`, `OCR Text`, `Translation`, `New Filename`.
   - **Double-click** on any OCR text or translation cell to edit inline; changes immediately recalculate the new filename.
5. **Smart Background Inpainting & Font Fitting**:
   - Calculates the **median color** of the pixels along the region border to seamlessly paint over the old text without leaving hard edges.
   - Automatic luminance detection: renders text in high-contrast black or white.
   - Automatic multi-line word wrapping and iterative font-size reduction so translated text always fits inside the bounding box.
6. **Live Preview Window**:
   - Inspect rendered images before exporting the full batch.
7. **Flexible File Renaming & Collision Handling**:
   - Variable template engine: `{index}`, `{index:03d}`, `{name}`, `{t1}`, `{t2}`, `{o1}`, `{o2}`.
   - Safe sanitization preserving Unicode and Vietnamese diacritics while stripping illegal characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`).
   - Automatic collision avoidance appending `_2`, `_3`, etc.
8. **Save & Load Configuration**:
   - Save all regions, languages, PSM, template, and font settings to a `.json` file.

---

## 🚀 Setup Instructions

### 1. Install Python Dependencies

Run the following command:

```bash
pip install -r requirements.txt
```

Or install directly:

```bash
pip install pillow pytesseract deep-translator
```

*(Note: `tkinter` comes pre-installed with standard Python on Windows and macOS. On Linux, if missing, install `sudo apt-get install python3-tk` or `sudo dnf install python3-tkinter`)*

---

### 2. Install Tesseract OCR & Language Packs

`pytesseract` requires the Tesseract OCR engine installed on your computer:

#### 🪟 Windows:
1. Download the official installer from UB-Mannheim:
   👉 [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
2. During installation, expand **"Additional script data"** and **"Additional language data"** to select the languages you need (e.g., Vietnamese, Japanese, Chinese, Korean).
3. The app automatically detects standard installation paths (`C:\Program Files\Tesseract-OCR\tesseract.exe`). If installed elsewhere, click **"⚙️ Tesseract Settings"** in the app toolbar to select your executable.

#### 🍎 macOS:
Using Homebrew:
```bash
brew install tesseract
brew install tesseract-lang
```

#### 🐧 Linux (Ubuntu / Debian):
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr
# Install language packs as needed:
sudo apt-get install -y tesseract-ocr-eng tesseract-ocr-vie tesseract-ocr-chi-sim tesseract-ocr-jpn tesseract-ocr-kor
```

---

## 📖 How to Use

1. **Launch the Application**:
   ```bash
   python image_batch_translator.py
   ```
2. **Choose Image Folder**:
   - Click **"📁 Choose Folder..."** and select the folder containing your batch of images.
   - The first image will be loaded onto the central canvas.
3. **Draw Text Regions**:
   - Click and drag with your mouse on the sample image to draw boxes around the text areas you want to translate.
   - Each region receives an index badge (`#1`, `#2`...).
   - Use the **Defined Regions** panel at the bottom-left to fine-tune pixel coordinates or delete regions.
4. **Configure Settings**:
   - **Source Language**: Language of the text in the images (e.g. `English`, `Japanese`, `Chinese`).
   - **Target Language**: Desired translated language (e.g. `Vietnamese`, `English`).
   - **PSM**: Page segmentation mode (default `6` works best for standard text blocks).
   - **Render Font**: Click **"Choose Font..."** to select a custom `.ttf` or `.otf` font (defaults to system Arial/DejaVu for full Vietnamese Unicode support).
   - **Name Template**: Customize how exported files are named. Click the quick-insert pills like `{index:03d}`, `{name}`, `{t1}`.
   - **Output Format**: Choose `Keep original`, `png`, or `jpg`.
5. **Scan OCR + Translate**:
   - Click **"🚀 Scan OCR + Translate"**.
   - The background worker will crop each region, run OCR preprocessing, fetch translations with caching, and populate the results table.
6. **Edit Results (Optional)**:
   - Double-click any cell in the **OCR Text** or **Translation** columns to edit text manually. The new filename will update in real-time.
7. **Preview**:
   - Click **"👁️ Preview Selected"** to see how the rendered image looks with the median background painted and translated text rendered.
8. **Export New Images**:
   - Click **"💾 Export New Images"**.
   - All translated images will be saved into the specified output folder (default: `<input_folder>/output`).
   - When finished, a prompt will offer to open the output folder directly in your system file manager.
9. **Save Configuration**:
   - Click **"💾 Save Config"** to export your region boxes and settings to a JSON file so you can reload them anytime.
