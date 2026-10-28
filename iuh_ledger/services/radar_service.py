"""
IUH Radar Heartbeat Service
Maintains 24/7 session vitality and detects the exact moment registration opens.
"""

import time
import json
import threading
from typing import Callable, Optional, Dict, Any
from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.client import IUHClient

class RadarService:
    def __init__(self, client: IUHClient, id_dot: str = "62", interval_seconds: int = 180):
        self.client = client
        self.id_dot = str(id_dot)
        self.interval_seconds = interval_seconds
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def check_status(self) -> Dict[str, Any]:
        """
        Sends CheckDotChoPhepDangKy request to inspect registration period status.
        Code 00: Open for registration.
        Code 01: Not open / not permitted.
        """
        post_data = {
            "param[IDDotDangKy]": self.id_dot,
            "param[IsCheckThoiGianDangKyOnline]": "False"
        }

        try:
            res = self.client.post(
                IUHEndpoints.CHECK_DOT,
                data=post_data,
                headers={"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest"},
                timeout=10
            )
            raw = res.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"Code": "99", "Message": raw}

            code = str(data.get("Code", "99"))
            is_open = (code == "00")
            msg = data.get("Message") or data.get("ExceptionMessage") or "Trạng thái không xác định"

            return {
                "open": is_open,
                "code": code,
                "message": msg,
                "timestamp": time.strftime("%H:%M:%S")
            }
        except Exception as e:
            return {
                "open": False,
                "code": "EX",
                "message": f"Lỗi ping radar: {str(e)}",
                "timestamp": time.strftime("%H:%M:%S")
            }

    def _loop(self, on_open: Callable, on_ping: Optional[Callable] = None):
        while self.is_running:
            status = self.check_status()
            
            if on_ping:
                try:
                    on_ping(status)
                except Exception:
                    pass

            if status.get("open"):
                self.is_running = False
                try:
                    on_open(status)
                except Exception:
                    pass
                break

            # Sleep in small increments for clean shutdown
            for _ in range(self.interval_seconds):
                if not self.is_running:
                    break
                time.sleep(1)

    def start_heartbeat(self, on_open_callback: Callable, on_ping_callback: Optional[Callable] = None):
        """
        Starts the background heartbeat worker.
        """
        if self.is_running:
            return

        self.is_running = True
        self._thread = threading.Thread(
            target=self._loop,
            args=(on_open_callback, on_ping_callback),
            daemon=True
        )
        self._thread.start()

    def stop_heartbeat(self):
        """
        Signals the background heartbeat worker to stop.
        """
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
