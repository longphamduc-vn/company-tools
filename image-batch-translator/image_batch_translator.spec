# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec for Smart Batch Character Extractor & Renamer.
Optimized for the absolute minimum .exe size:
- Excludes heavy libraries (torch, scipy, pandas, matplotlib, IPython, etc.)
- Strips unused ONNX Runtime GPU/CUDA/DirectML backends (CPU inference only)
- Single-file standalone executable (--onefile)
- Windowed mode without console window (--noconsole)
- UPX binary compression enabled
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect RapidOCR ONNX models and yaml configs (~5MB)
rapidocr_datas = []
try:
    rapidocr_datas = collect_data_files('rapidocr_onnxruntime')
except Exception as e:
    print("Warning collecting rapidocr data files:", e)

datas = rapidocr_datas

# Hidden imports needed for runtime
hiddenimports = [
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL.ImageDraw',
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.drawing.image',
    'rapidocr_onnxruntime',
    'onnxruntime',
    'deep_translator',
    'chrome_lens_py',
]

# HEAVY UNUSED MODULES TO EXCLUDE (CRITICAL FOR MINIMUM EXE SIZE!)
# Excluding these prevents PyInstaller from bundling 300MB+ of unused scientific packages
excludes = [
    'torch',
    'torchvision',
    'torchaudio',
    'scipy',
    'pandas',
    'matplotlib',
    'IPython',
    'jupyter',
    'notebook',
    'jedi',
    'pytest',
    'unittest',
    'test',
    'tests',
    'tkinter.test',
    'distutils',
    'setuptools',
    'pip',
    'wheel',
    'pydoc',
    'sqlite3',
    'curses',
    'wx',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    # Exclude unused onnxruntime GPU/CUDA/DirectML providers
    'onnxruntime.providers.cuda',
    'onnxruntime.providers.tensorrt',
    'onnxruntime.providers.directml',
    'onnxruntime.providers.openvino',
    'onnxruntime.providers.rocm',
]

a = Analysis(
    ['image_batch_translator.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SmartBatchExtractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Enables UPX compression for 50%+ size reduction
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed GUI application (no black command prompt)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
