# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import glob
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_data_files

block_cipher = None

here = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(here, 'iuh_ledger', 'gui'), os.path.join('iuh_ledger', 'gui')),
    (os.path.join(here, 'iuh_ledger', 'gui'), 'gui'),
    (os.path.join(here, 'iuh_ledger', 'assets'), os.path.join('iuh_ledger', 'assets')),
    (os.path.join(here, 'iuh_ledger', 'assets'), 'assets'),
]
if os.path.exists(os.path.join(here, 'capture', '004_GetDanhSachLichTheoTuan_POST.txt')):
    datas.append((os.path.join(here, 'capture', '004_GetDanhSachLichTheoTuan_POST.txt'), 'capture'))
if os.path.exists(os.path.join(here, 'config.example.json')):
    datas.append((os.path.join(here, 'config.example.json'), '.'))
binaries = []
hiddenimports = [
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'clr',
    'clr_loader',
    'pythonnet',
    'cryptography',
    'cryptography.hazmat.primitives.ciphers',
    'cryptography.hazmat.primitives.ciphers.algorithms',
    'cryptography.hazmat.primitives.ciphers.modes',
    'concurrent.futures',
]

# 1. Collect all pythonnet, clr_loader, and webview runtime assemblies & native DLLs
for pkg_name in ('pythonnet', 'clr_loader', 'webview'):
    try:
        pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg_name)
        datas.extend(pkg_datas)
        binaries.extend(pkg_bins)
        for h in pkg_hidden:
            if h not in hiddenimports:
                hiddenimports.append(h)
    except Exception:
        pass

# 2. Bundle Python DLLs & Windows UCRT / MSVC Runtime DLLs so target PCs need zero pre-installed runtimes
py_dir = os.path.dirname(sys.executable)
sys32_dir = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
runtime_dll_names = [
    'python3.dll',
    f'python{sys.version_info.major}{sys.version_info.minor}.dll',
    'vcruntime140.dll',
    'vcruntime140_1.dll',
    'msvcp140.dll',
    'ucrtbase.dll',
    'concrt140.dll',
]
for dll_name in runtime_dll_names:
    for candidate_dir in (py_dir, os.path.join(py_dir, 'DLLs'), sys32_dir):
        candidate_path = os.path.join(candidate_dir, dll_name)
        if os.path.exists(candidate_path):
            binaries.append((candidate_path, '.'))
            break

icon_path = os.path.join(here, 'iuh_ledger', 'assets', 'icon.ico')
if not os.path.exists(icon_path):
    icon_path = os.path.join(here, 'iuh_ledger', 'gui', 'icon.ico')
if not os.path.exists(icon_path):
    icon_path = None

a = Analysis(
    [os.path.join(here, 'iuh_ledger', 'run_gui.py')],
    pathex=[here],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'tkinter', 'unittest'],
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
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='IUH_Ledger',
)
