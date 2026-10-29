"""
IUH Ledger GUI Launcher (pywebview)
Starts native desktop window powered by Edge WebView2 / Chromium and Hallmark Dose UI.
"""

import os
import sys

# Ensure workspace root and frozen _internal DLL directories are registered before loading clr / webview
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    _exe_dir = os.path.dirname(sys.executable)
    for _dll_dir in (_meipass, _exe_dir, os.path.join(_meipass, 'pythonnet', 'runtime')):
        if os.path.isdir(_dll_dir):
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(_dll_dir)
                except Exception:
                    pass
            if _dll_dir not in os.environ.get('PATH', ''):
                os.environ['PATH'] = _dll_dir + os.pathsep + os.environ.get('PATH', '')
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_EXE_CONFIG = (
    '<?xml version="1.0" encoding="utf-8" ?>\n'
    '<configuration>\n  <runtime>\n    <loadFromRemoteSources enabled="true"/>\n  </runtime>\n</configuration>\n'
)


def _unblock_zone_identifiers(*roots):
    """Strip Mark-of-the-Web ADS so .NET/native DLLs from downloaded ZIPs load."""
    seen = set()
    for root in roots:
        if not root or root in seen or not os.path.isdir(root):
            continue
        seen.add(root)
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.lower().endswith(('.dll', '.pyd', '.exe', '.json')):
                    try:
                        os.remove(os.path.join(dirpath, name) + ':Zone.Identifier')
                    except OSError:
                        pass


if getattr(sys, 'frozen', False):
    _unblock_zone_identifiers(_meipass, _exe_dir)
    _cfg_path = sys.executable + '.config'
    if not os.path.exists(_cfg_path):
        try:
            with open(_cfg_path, 'w', encoding='utf-8') as _f:
                _f.write(_EXE_CONFIG)
        except OSError:
            pass

import webview
from iuh_ledger.gui_api import BridgeAPI
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    base_dir = get_base_dir()
    candidates = [
        os.path.join(base_dir, "iuh_ledger", "gui", "index.html"),
        os.path.join(base_dir, "gui", "index.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui", "index.html"),
        os.path.join("iuh_ledger", "gui", "index.html")
    ]
    index_html = next((c for c in candidates if os.path.exists(c)), candidates[0])

    bridge = BridgeAPI()

    window = webview.create_window(
        title="Sổ cái đăng ký học phần IUH — IUH Ledger",
        url=index_html,
        js_api=bridge,
        width=1360,
        height=860,
        min_size=(960, 640)
    )
    webview.start(debug=False)
if __name__ == "__main__":
    main()
