"""
IUH HTTP Session Client with Cookie Persistence
Manages connection pooling, SSL bypass, headers, and session.json caching.
"""

import os
import sys
import json
import ssl
import threading
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar, Cookie
from typing import Optional, Dict, Any

class IUHClient:
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://sv.iuh.edu.vn/dang-ky-hoc-phan.html",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    def __init__(self, session_path: Optional[str] = None):
        if session_path:
            self.session_path = session_path
        elif getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            self.session_path = os.path.join(exe_dir, "session.json")
        elif os.path.exists("session.json"):
            self.session_path = "session.json"
        elif os.path.exists(os.path.join("iuh_ledger", "session.json")):
            self.session_path = os.path.join("iuh_ledger", "session.json")
        else:
            self.session_path = "session.json"
        self._lock = threading.RLock()
        self.cookie_jar = CookieJar()
        # SSL Context
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

        self.cookie_handler = urllib.request.HTTPCookieProcessor(self.cookie_jar)
        self.ssl_handler = urllib.request.HTTPSHandler(context=self.ssl_ctx)
        self.opener = urllib.request.build_opener(self.cookie_handler, self.ssl_handler)

    def set_cookie(self, name: str, value: str, domain: str = "sv.iuh.edu.vn", path: str = "/"):
        cookie = Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain=domain, domain_specified=bool(domain), domain_initial_dot=domain.startswith("."),
            path=path, path_specified=bool(path), secure=False, expires=None,
            discard=True, comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False
        )
        with self._lock:
            self.cookie_jar.set_cookie(cookie)

    def clear_cookies(self):
        with self._lock:
            self.cookie_jar.clear()

    def get_cookies_dict(self) -> Dict[str, str]:
        with self._lock:
            return {c.name: c.value for c in self.cookie_jar}

    def save_cookies(self, filepath: Optional[str] = None):
        target = filepath or self.session_path
        data = self.get_cookies_dict()
        with self._lock:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    def load_cookies(self, filepath: Optional[str] = None) -> bool:
        target = filepath or self.session_path
        if not os.path.exists(target):
            return False
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                self.set_cookie(k, v)
            return len(data) > 0
        except Exception:
            return False

    def request(self, method: str, url: str, data: Optional[Dict[str, Any]] = None, 
                headers: Optional[Dict[str, str]] = None, follow_redirects: bool = True, timeout: int = 15):
        req_headers = dict(self.DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        post_bytes = None
        if data is not None:
            if isinstance(data, dict):
                post_bytes = urllib.parse.urlencode(data).encode("utf-8")
                if "Content-Type" not in req_headers:
                    req_headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            elif isinstance(data, (bytes, bytearray)):
                post_bytes = data
            elif isinstance(data, str):
                post_bytes = data.encode("utf-8")

        req = urllib.request.Request(url, data=post_bytes, headers=req_headers, method=method.upper())

        if not follow_redirects:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def http_error_302(self, req, fp, code, msg, hdrs):
                    return fp
                http_error_301 = http_error_303 = http_error_307 = http_error_302
            opener = urllib.request.build_opener(self.cookie_handler, self.ssl_handler, NoRedirect())
        else:
            opener = self.opener

        with self._lock:
            return opener.open(req, timeout=timeout)

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs):
        return self.request("GET", url, headers=headers, **kwargs)

    def post(self, url: str, data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, **kwargs):
        return self.request("POST", url, data=data, headers=headers, **kwargs)

    def is_session_valid(self, id_dot: str = "62") -> bool:
        """
        Pings HocPhanDaDangKy to verify if session cookies are alive.
        """
        try:
            res = self.post(
                IUHEndpoints.HOC_PHAN_DA_DK,
                data={
                    "param[IDDotDangKy]": id_dot,
                    "param[IDLoaiDangKy]": "1"
                },
                timeout=10
            )
            html = res.read().decode("utf-8", errors="replace")
            # If valid, HTML contains student table or registration header
            if any(k in html for k in ["Mã sinh viên", "Mã lớp  HP", "Lớp HP đã đăng ký", "Không tìm thấy lớp HP"]):
                return True
            return False
        except Exception:
            return False
