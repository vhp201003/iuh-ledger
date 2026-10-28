"""
IUH Dual-Authentication Orchestrator
Coordinates existing session recovery and native AES+Captcha login.
"""

import re
import os
from typing import Callable, Optional
from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.crypto import encrypt_iuh_password
from iuh_ledger.core.client import IUHClient

class IUHAuthenticator:
    def __init__(self, client: IUHClient, username: str, password: str = ""):
        self.client = client
        self.username = username
        self.password = password

    def login_with_existing_session(self, id_dot: str = "62") -> bool:
        """
        Attempts to resume session from session.json without re-entering credentials.
        """
        if not self.client.load_cookies():
            return False
        return self.client.is_session_valid(id_dot=id_dot)

    def login_native(self, captcha_callback: Callable[[bytes], str]) -> bool:
        """
        Executes full native login:
        1. Fetch __RequestVerificationToken
        2. Fetch one-time PrivateKey for username
        3. Encrypt password with AES-128-CBC
        4. Download Captcha image and invoke captcha_callback
        5. Submit form and capture session cookies
        """
        # 1. Fetch login page
        res = self.client.get(IUHEndpoints.LOGIN_PAGE)
        html = res.read().decode("utf-8", errors="replace")
        
        token_match = re.search(r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']*)["\']', html)
        if not token_match:
            raise RuntimeError("Không tìm thấy __RequestVerificationToken trên trang đăng nhập")
        token = token_match.group(1)

        # 2. Fetch PrivateKey
        key_res = self.client.get(f"{IUHEndpoints.GET_PRIVATE_KEY}?salt={self.username}")
        private_key = key_res.read().decode("utf-8", errors="replace").strip()
        if not private_key:
            raise RuntimeError("Không nhận được PrivateKey từ server")

        # 3. Encrypt Password
        if not self.password:
            raise ValueError("Mật khẩu không được để trống khi thực hiện Native Login")
        encrypted_pwd = encrypt_iuh_password(self.password, private_key)

        # 4. Fetch Captcha
        captcha_res = self.client.get(IUHEndpoints.GET_CAPTCHA)
        captcha_bytes = captcha_res.read()

        # 5. Get user captcha input
        captcha_code = captcha_callback(captcha_bytes)
        if not captcha_code:
            return False

        # 6. Submit login form
        post_data = {
            "__RequestVerificationToken": token,
            "UserName": self.username,
            "Password": encrypted_pwd,
            "IsSinhVienDaTotNghiep": "false",
            "Captcha": str(captcha_code).strip(),
            "SSOData": ""
        }

        login_res = self.client.post(
            IUHEndpoints.LOGIN_PAGE,
            data=post_data,
            follow_redirects=True
        )

        # Check cookies & validation
        cookies = self.client.get_cookies_dict()
        if "ASC.AUTH" in cookies:
            self.client.save_cookies()
            return True

        # Check if session is valid anyway
        if self.client.is_session_valid():
            self.client.save_cookies()
            return True

        return False

    def authenticate(self, captcha_callback: Optional[Callable[[bytes], str]] = None, id_dot: str = "62") -> bool:
        """
        Orchestrates dual-auth:
        Tries existing session first; if invalid, falls back to login_native.
        """
        if self.login_with_existing_session(id_dot=id_dot):
            return True

        if not captcha_callback:
            return False

        return self.login_native(captcha_callback)
