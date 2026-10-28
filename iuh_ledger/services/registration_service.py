"""
IUH Course Registration and Cancellation Service
Dispatches direct enrollment and drop commands with ASP.NET model-binding.
"""

import json
from typing import Optional, Dict, Any
from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.client import IUHClient

class RegistrationService:
    def __init__(self, client: IUHClient):
        self.client = client

    def register_class(self, id_dot: str, guid_lhp: str, loai_dk: int = 1, 
                       nhom_th: Optional[int] = None, ma_mon_cha: str = "") -> Dict[str, Any]:
        """
        Submits direct class enrollment command to POST /dang-ky-hoc-phan.html.
        Returns normalized status dictionary.
        """
        post_data = {
            "param[IDDotDangKy]": str(id_dot),
            "param[IDLoaiDangKy]": str(loai_dk),
            "param[GuidIDLopHocPhan]": str(guid_lhp),
            "param[IDNhomThucHanh]": str(nhom_th) if nhom_th is not None else "",
            "param[MaMonCha]": str(ma_mon_cha)
        }

        try:
            res = self.client.post(
                IUHEndpoints.DANG_KY_HP,
                data=post_data,
                headers={"Accept": "application/json, text/javascript, */*; q=0.01"},
                timeout=12
            )
            raw = res.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"Code": "99", "Message": raw, "ExceptionMessage": raw}

            code = str(data.get("Code", "99"))
            is_success = (code == "00")
            msg = data.get("Message") or data.get("ExceptionMessage") or "Không có phản hồi từ server"

            return {
                "success": is_success,
                "code": code,
                "message": msg,
                "raw": data
            }
        except Exception as e:
            return {
                "success": False,
                "code": "EX",
                "message": f"Lỗi mạng: {str(e)}",
                "raw": None
            }

    def cancel_registered_class(self, id_dk: str, guid_dk: str) -> Dict[str, Any]:
        """
        Cancels an already enrolled course class via POST /SinhVienDangKy/HuyDangKyHocPhan.
        """
        post_data = {
            "param[IDDangKyHocPhan]": str(id_dk),
            "param[GuidIDDangKyLopHocPhan]": str(guid_dk)
        }

        try:
            res = self.client.post(
                IUHEndpoints.HUY_DANG_KY_HP,
                data=post_data,
                headers={"Accept": "application/json, text/javascript, */*; q=0.01"},
                timeout=12
            )
            raw = res.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"Code": "99", "Message": raw, "ExceptionMessage": raw}

            code = str(data.get("Code", "99"))
            is_success = (code == "00") or bool(data.get("isSuccess", False))
            msg = data.get("Message") or data.get("ExceptionMessage") or "Không có thông báo từ server"

            return {
                "success": is_success,
                "code": code,
                "message": msg,
                "raw": data
            }
        except Exception as e:
            return {
                "success": False,
                "code": "EX",
                "message": f"Lỗi mạng khi hủy môn: {str(e)}",
                "raw": None
            }
