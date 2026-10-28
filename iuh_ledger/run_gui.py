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
