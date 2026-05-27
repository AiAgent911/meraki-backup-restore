# -*- mode: python ; coding: utf-8 -*-
# Meraki Backup & Restore — RSITServices
# PyInstaller spec file — Windows .exe

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['/home/openclaw01/meraki-backup-restore'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'meraki', 'tkinter', 'logging', 'json',
        'threading', 'pathlib',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'numpy', 'pandas', 'scipy', 'matplotlib',
        'PIL', 'cv2', 'requests', 'urllib3', 'Cryptography',
    ],
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
    name='MerakiBackupRestore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
    version=None,
)