# -*- mode: python ; coding: utf-8 -*-
# Meraki Backup & Restore — RSITServices
# PyInstaller spec file — Windows .exe

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'meraki', 'tkinter', 'logging', 'json',
        'threading', 'pathlib', 'traceback',
        'requests', 'urllib3', 'cryptography',
        'certifi', 'charset_normalizer', 'idna', 'socket',
        'ssl', 'http.client', 'tkinter.ttk',
    ],
    excludes=[
        'numpy', 'pandas', 'scipy', 'matplotlib',
        'PIL', 'cv2',
    ],
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
    name='MerakiBackupRestore',
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=None,
)