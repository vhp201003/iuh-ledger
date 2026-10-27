# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

here = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(here, 'iuh_sniper', 'gui'), os.path.join('iuh_sniper', 'gui')),
    (os.path.join(here, 'iuh_sniper', 'gui'), 'gui'),
    (os.path.join(here, 'iuh_sniper', 'assets'), os.path.join('iuh_sniper', 'assets')),
    (os.path.join(here, 'iuh_sniper', 'assets'), 'assets'),
]
if os.path.exists(os.path.join(here, 'iuh_sniper', 'config.json')):
    datas.append((os.path.join(here, 'iuh_sniper', 'config.json'), '.'))
elif os.path.exists(os.path.join(here, 'config.json')):
    datas.append((os.path.join(here, 'config.json'), '.'))
hiddenimports = [
    'webview',
    'webview.platforms.winforms',
    'clr',
    'pythonnet',
    'cryptography',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.ciphers.algorithms',
    'cryptography.hazmat.primitives.ciphers.modes',
    'concurrent.futures',
]

icon_path = os.path.join(here, 'iuh_sniper', 'assets', 'icon.ico')
if not os.path.exists(icon_path):
    icon_path = os.path.join(here, 'iuh_sniper', 'gui', 'icon.ico')
if not os.path.exists(icon_path):
    icon_path = None

a = Analysis(
    [os.path.join(here, 'iuh_sniper', 'run_gui.py')],
    pathex=[here],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IUH_Ledger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI application, no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IUH_Ledger',
)
