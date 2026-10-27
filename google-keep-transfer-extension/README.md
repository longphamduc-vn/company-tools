# Google Keep Text File Transfer (Chrome Extension - Manifest V3)

A Chrome extension designed to **upload**, **split**, **reassemble**, and **download** large text files through **Google Keep** (`keep.google.com`).

---

## 🌟 Key Features

1. **📤 Upload & Automated Chunking**:
   - Handles any text file (`.txt`, `.json`, `.csv`, `.md`, `.js`, `.py`, `.xml`, `.log`, `.yaml`, etc.) or direct text paste.
   - Splits files into safe, bite-sized notes (default 10,000 characters per note, well within Google Keep's character limits).
   - Generates structured, padded titles for alphabetical and natural sorting:
     `[KT] <filename> | Part 01/05 | ID:<file_id>`
   - **Master Config Note (`[KT-CONFIG]`)**: Automatically creates a manifest note containing the file metadata, file ID, timestamp, and chunk map.
   - Robust note saving: Accurately triggers Keep's content editor, sets title and body, awaits debounced state, and closes/saves cleanly.

2. **⚡ Autonomous In-Page Execution & Floating Widget**:
   - Transfers run directly in the `keep.google.com` tab with an injected on-screen floating widget.
   - The floating widget displays live progress, note counters, character verification badges, Pause, Resume, and Stop buttons directly inside Google Keep.
   - **Auto-Close Popup**: The extension popup automatically closes when transfer starts to return 100% native window focus to Google Keep, allowing Closure auto-save and blur listeners to commit notes instantaneously.
   - You can reopen the popup at any time to inspect logs, or click **"👁 View in Keep"** to focus the tab.

3. **📥 Automated Detection & Reassembly (Download)**:
   - **Quick Scan**: Rapidly checks note cards currently in the Keep tab.
   - **Deep Scan (No Omissions)**: Automatically scrolls the entire Keep page to the bottom and reads full note modal contents without skipping.
   - Detects **Master Config Notes** and correlates them with chunk notes.
   - Checks completeness: Displays `Complete (5/5) ✅` or lists missing parts (`Missing parts: 02, 04 ⚠️`).
   - Reassembles parts in sequential order (`Part 01 -> Part 02 -> ... -> Part N`) and downloads the exact original text file.
   - Live content preview modal with one-click copy and download.

4. **⧉ Pop Out Window Support**:
   - Use the **⧉ Pop Out** button in the header if you want to keep Keep Transfer open as a detached, standalone window alongside Google Keep.

5. **📑 Manual Merger**:
   - Select any combination of notes scanned from Google Keep.
   - Choose delimiter: Direct concatenation, Single newline (`\n`), Double newline (`\n\n`), or Divider line (`---`).
   - Download as a merged `.txt` file or export everything as a structured JSON file.

5. **⚙️ Customization**:
   - Chunk Size: 5,000 / 10,000 (Recommended) / 15,000 / 18,000 characters.
   - Delay between notes: 400ms / 800ms (Recommended) / 1,200ms / 2,000ms.
   - Customizable prefix tags: Chunk prefix (`[KT]`) and Config prefix (`[KT-CONFIG]`).
   - Scroll delay on scan: 800ms / 1,200ms / 1,800ms.

---

## 📂 Project Structure

```
google-keep-transfer-extension/
├── manifest.json       # Manifest V3 configuration
├── background.js      # Background service worker for downloads & tab management
├── content.js         # Google Keep DOM automation & extraction engine
├── popup.html         # English extension UI with Pop Out and Config Note options
├── popup.css          # Modern dark-mode styling with status badges and animations
├── popup.js           # Chunking, config note manifest, reassembly, and scan logic
├── icons/             # 16x16, 32x32, 48x48, 128x128 icons
└── README.md          # Documentation & usage guide
```

---

## 🚀 Installation Guide

1. Open Google Chrome, Brave, Edge, or any Chromium-based browser.
2. Navigate to:
   ```
   chrome://extensions/
   ```
3. Enable **Developer mode** (toggle in the top-right corner).
4. Click **Load unpacked** (top-left).
5. Select the extension directory:
   ```
   /home/longp/projects/company-tools/google-keep-transfer-extension
   ```
6. The **Keep Transfer** extension icon will appear on your browser toolbar!

---

## 📖 How to Use

### 1. Upload a File to Google Keep:
1. Open [https://keep.google.com/](https://keep.google.com/) in a browser tab.
2. Click the **Keep Transfer** icon on your browser toolbar.
3. *(Recommended)* Click **⧉ Pop Out** in the top header to keep the extension window open side-by-side.
4. Drag and drop your text file or paste text directly.
5. Ensure the **"Create Master Config Note"** checkbox is checked.
6. Click **"Split File & Upload to Google Keep"**. Watch the live progress bar and logs as each note is created and saved.

### 2. Reassemble & Download:
1. Open [https://keep.google.com/](https://keep.google.com/).
2. Open Keep Transfer and switch to the **"Reassemble & Download"** tab.
3. Click **"Quick Scan"** or **"Deep Scan (All Notes)"**.
4. The extension detects your file and displays its status:
   - `Config ✅` (Master config note identified)
   - `Complete (X/X) ✅` (All chunks found)
5. Click **"📥 Download (.txt)"** to reassemble and save your original file!
