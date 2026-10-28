"""
IUH Ledger GUI - Python to JavaScript Bridge API (pywebview)
Exposes core authentication, catalog, registration, radar, and sniper services to the frontend.
"""

import os
import re
import sys
import json
import time
import base64
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from types import SimpleNamespace
from typing import Dict, Any, List, Optional
from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.client import IUHClient
from iuh_ledger.core.auth import IUHAuthenticator
from iuh_ledger.core.models import Subject, CourseClass, ClassSchedule
from iuh_ledger.services.catalog_service import CatalogService
from iuh_ledger.services.registration_service import RegistrationService
from iuh_ledger.services.radar_service import RadarService
from iuh_ledger.services.sniper_service import SniperService


def extract_nhom_th_int(raw_val: Any) -> Optional[int]:
    """
    Extracts integer practice group number (nhom_th) from string/int input.
    Returns None if empty or no digit exists.
    """
    if raw_val is None:
        return None
    s = str(raw_val).strip()
    if not s:
        return None
    m = re.search(r'\d+', s)
    return int(m.group(0)) if m else None


def _unique_non_empty(items: List[str]) -> List[str]:
    seen = []
    for item in items:
        val = (item or "").strip()
        if val and val not in seen:
            seen.append(val)
    return seen


def _format_schedule_lines(rows: List[ClassSchedule]) -> str:
    parts = []
    for s in rows:
        tiet = (s.thu_tiet or "").strip()
        phong = (s.phong or "").strip()
        if tiet and phong:
            line = f"{tiet} · Phòng {phong}"
        elif tiet:
            line = tiet
        elif phong:
            line = f"Phòng {phong}"
        else:
            line = ""
        if line and line not in parts:
            parts.append(line)
    return " | ".join(parts)


def flatten_class_with_schedules(
    cls_obj: CourseClass,
    schedules: List[ClassSchedule],
    ma_mon_cha: str = ""
) -> List[Dict[str, Any]]:
    """
    Flattens a CourseClass and its detailed ClassSchedule rows into displayable selection rows.
    - Pure theory classes (no nhom_th) yield 1 row with nhom_th=None.
    - Classes with practice groups yield 1 distinct row per nhom_th group, combining common LT schedule + group TH schedule.
    """
    lt_rows: List[ClassSchedule] = []
    th_by_group: Dict[int, List[ClassSchedule]] = {}

    for s in schedules or []:
        grp = extract_nhom_th_int(s.nhom_th)
        if grp is None:
            lt_rows.append(s)
        else:
            th_by_group.setdefault(grp, []).append(s)

    lich_lt_str = _format_schedule_lines(lt_rows)
    lt_lecturers = _unique_non_empty([s.giang_vien for s in lt_rows])
    all_lecturers = _unique_non_empty([s.giang_vien for s in (schedules or [])])
    all_rooms = _unique_non_empty([s.phong for s in (schedules or [])])
    all_campuses = _unique_non_empty([s.co_so for s in (schedules or [])])
    all_dates = _unique_non_empty([s.thoi_gian for s in (schedules or [])])

    base_info = {
        "guid_lhp": cls_obj.guid_lhp,
        "ma_lhp": cls_obj.ma_lhp,
        "ten_lop": cls_obj.ten_lop,
        "lop_du_kien": cls_obj.lop_du_kien or cls_obj.ten_lop,
        "si_so_dk": cls_obj.si_so_dk,
        "si_so_max": cls_obj.si_so_max,
        "trang_thai": cls_obj.trang_thai,
        "da_khoa": cls_obj.da_khoa,
        "ma_mon_cha": ma_mon_cha or ""
    }

    if not th_by_group:
        gv_str = ", ".join(all_lecturers) if all_lecturers else "Đang cập nhật"
        return [{
            **base_info,
            "row_key": f"{cls_obj.guid_lhp}_0",
            "nhom_th": None,
            "nhom_th_label": "Thuần LT",
            "lich_lt": lich_lt_str or "Chưa công bố lịch LT",
            "lich_th": "",
            "giang_vien": gv_str,
            "phong": ", ".join(all_rooms),
            "co_so": ", ".join(all_campuses),
            "thoi_gian": ", ".join(all_dates),
            "schedules": [asdict(s) for s in (schedules or [])]
        }]
    flattened: List[Dict[str, Any]] = []
    for grp_num in sorted(th_by_group.keys()):
        th_rows = th_by_group[grp_num]
        lich_th_str = _format_schedule_lines(th_rows)
        th_lecturers = _unique_non_empty([s.giang_vien for s in th_rows])

        if lt_lecturers and th_lecturers:
            if lt_lecturers == th_lecturers:
                gv_combined = ", ".join(lt_lecturers)
            else:
                gv_combined = f"LT: {', '.join(lt_lecturers)} · TH: {', '.join(th_lecturers)}"
        elif lt_lecturers:
            gv_combined = ", ".join(lt_lecturers)
        elif th_lecturers:
            gv_combined = ", ".join(th_lecturers)
        else:
            gv_combined = "Đang cập nhật"

        grp_rooms = _unique_non_empty([s.phong for s in lt_rows + th_rows])
        grp_campuses = _unique_non_empty([s.co_so for s in lt_rows + th_rows])
        grp_dates = _unique_non_empty([s.thoi_gian for s in lt_rows + th_rows])

        flattened.append({
            **base_info,
            "row_key": f"{cls_obj.guid_lhp}_{grp_num}",
            "nhom_th": grp_num,
            "nhom_th_label": f"Nhóm TH {grp_num}",
            "lich_lt": lich_lt_str or "Lịch LT chung",
            "lich_th": lich_th_str,
            "giang_vien": gv_combined,
            "phong": ", ".join(grp_rooms),
            "co_so": ", ".join(grp_campuses),
            "thoi_gian": ", ".join(grp_dates),
            "schedules": [asdict(s) for s in (lt_rows + th_rows)]
        })
    return flattened


class BridgeAPI:
    def __init__(self, config_path: str = "config.json", session_path: Optional[str] = None):
        self.config_path = config_path
        self.config = self._load_config()
        self.client = IUHClient(session_path=session_path)
        try:
            self.client.load_cookies()
        except Exception:
            pass
        self.catalog = CatalogService(self.client)
        self.registration = RegistrationService(self.client)
        self.radar = RadarService(self.client, id_dot=self.config.get("id_dot_dang_ky", "62"))
        self.sniper = SniperService(self.catalog, self.registration, self.config.get("target_classes", []))
        self._login_token: Optional[str] = None
        self._reg_sched_cache: Dict[str, tuple] = {}
        self._config_lock = threading.RLock()
    def _load_config(self) -> Dict[str, Any]:
        candidates = [
            os.path.join(os.path.dirname(sys.executable), self.config_path) if getattr(sys, 'frozen', False) else None,
            self.config_path,
            os.path.join("iuh_ledger", self.config_path)
        ]
        for c in candidates:
            if c and os.path.exists(c):
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {
            "username": "24687201",
            "password": "",
            "id_dot_dang_ky": "62",
            "loai_dk": 1,
            "target_classes": []
        }

    def _save_config(self):
        with self._config_lock:
            if getattr(sys, 'frozen', False):
                target = os.path.join(os.path.dirname(sys.executable), self.config_path)
            else:
                candidates = [self.config_path, os.path.join("iuh_ledger", self.config_path)]
                target = candidates[0]
                for c in candidates:
                    if os.path.exists(c):
                        target = c
                        break
            target_dir = os.path.dirname(os.path.abspath(target)) or "."
            os.makedirs(target_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix="cfg_", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, target)
            except Exception:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

    def get_initial_state(self) -> Dict[str, Any]:
        """
        Called by frontend on startup to hydrate student profile, semester list, and session status.
        """
        id_dot = str(self.config.get("id_dot_dang_ky", "62"))
        loai_dk = int(self.config.get("loai_dk", 1))
        auth = IUHAuthenticator(self.client, self.config.get("username", ""), self.config.get("password", ""))
        is_valid = auth.login_with_existing_session(id_dot=id_dot)

        profile_dict = None
        semesters_list = []

        if is_valid:
            try:
                prof = self.catalog.get_student_profile(id_dot=id_dot)
                if prof:
                    profile_dict = asdict(prof)
            except Exception:
                pass

            try:
                sems = self.catalog.get_semesters()
                semesters_list = [asdict(s) for s in sems]
            except Exception:
                pass

        return {
            "authenticated": is_valid,
            "current_dot": id_dot,
            "loai_dk": loai_dk,
            "profile": profile_dict,
            "semesters": semesters_list,
            "targets": self.get_targets()["targets"]
        }

    def get_open_subjects(self, id_dot: str = "62", loai_dk: int = 1) -> Dict[str, Any]:
        try:
            self.config["id_dot_dang_ky"] = str(id_dot)
            self.config["loai_dk"] = int(loai_dk)
            self._save_config()
            subjects = self.catalog.get_open_subjects(id_dot=str(id_dot), loai_dk=int(loai_dk))
            return {
                "success": True,
                "subjects": [asdict(s) for s in subjects]
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "subjects": []
            }

    def get_enriched_classes_for_subject(
        self,
        id_dot: str,
        ma_mon: str,
        ma_hp: str,
        ten_mon: str = "",
        ma_mon_cha: str = "",
        loai_dk: int = 1,
        khong_trung_lich: bool = False
    ) -> Dict[str, Any]:
        """
        Fetches open classes for a subject and concurrently fetches detailed schedules
        for all classes using ThreadPoolExecutor(max_workers=4), returning flattened rows per nhom_th.
        """
        try:
            subj = Subject(
                id_mon="",
                ma_mon=str(ma_mon),
                ma_hp=str(ma_hp),
                ten_mon=str(ten_mon),
                so_tc=0,
                ma_mon_cha=str(ma_mon_cha or "")
            )
            classes = self.catalog.get_classes_for_subject(
                id_dot=str(id_dot),
                subject=subj,
                khong_trung_lich=bool(khong_trung_lich),
                loai_dk=int(loai_dk)
            )

            schedules_map: Dict[str, List[ClassSchedule]] = {}

            def _fetch_one(c_obj: CourseClass):
                try:
                    return c_obj.guid_lhp, self.catalog.get_class_schedule(c_obj.guid_lhp, timeout=10)
                except Exception:
                    return c_obj.guid_lhp, []

            if classes:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    for guid, sched_list in pool.map(_fetch_one, classes):
                        schedules_map[guid] = sched_list

            flattened_rows: List[Dict[str, Any]] = []
            for c_obj in classes:
                scheds = schedules_map.get(c_obj.guid_lhp, [])
                flattened_rows.extend(
                    flatten_class_with_schedules(c_obj, scheds, ma_mon_cha=str(ma_mon_cha or ""))
                )

            return {
                "success": True,
                "rows": flattened_rows,
                "classes": [asdict(c) for c in classes]
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "rows": [],
                "classes": []
            }

    def get_classes_for_subject(self, id_dot: str, ma_mon: str, ma_hp: str, ten_mon: str = "") -> Dict[str, Any]:
        """
        Backward-compatible wrapper around get_enriched_classes_for_subject.
        """
        return self.get_enriched_classes_for_subject(
            id_dot=id_dot,
            ma_mon=ma_mon,
            ma_hp=ma_hp,
            ten_mon=ten_mon
        )

    def direct_register(
        self,
        id_dot: str,
        guid_lhp: str,
        nhom_th: Optional[Any] = None,
        loai_dk: int = 1,
        ma_mon_cha: str = ""
    ) -> Dict[str, Any]:
        """
        Executes immediate course registration when a class has available slots.
        """
        norm_nhom = extract_nhom_th_int(nhom_th)
        res = self.registration.register_class(
            id_dot=str(id_dot),
            guid_lhp=str(guid_lhp),
            loai_dk=int(loai_dk),
            nhom_th=norm_nhom,
            ma_mon_cha=str(ma_mon_cha or "")
        )
        if res.get("success"):
            self._reg_sched_cache.pop(str(id_dot), None)
        return res
    def get_registered_courses(self, id_dot: str = "62", loai_dk: int = 1) -> Dict[str, Any]:
        try:
            courses = self.catalog.get_registered_courses(id_dot=str(id_dot), loai_dk=int(loai_dk))
            return {
                "success": True,
                "courses": [asdict(c) for c in courses]
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "courses": []
            }

    def cancel_course(self, id_dk: str, guid_dk: str) -> Dict[str, Any]:
        res = self.registration.cancel_registered_class(id_dk=str(id_dk), guid_dk=str(guid_dk))
        if res.get("success"):
            self._reg_sched_cache.clear()
        return res
    def get_schedule_for_class(self, guid_lhp: str) -> Dict[str, Any]:
        """
        Retrieves detailed schedule rows for any given class GUID.
        """
        try:
            scheds = self.catalog.get_class_schedule(str(guid_lhp), timeout=10)
            return {
                "success": True,
                "schedules": [asdict(s) for s in scheds]
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "schedules": []
            }

    def get_targets(self) -> Dict[str, Any]:
        """
        Returns the current list of sniper targets with normalized target_key fields.
        """
        targets = self.config.setdefault("target_classes", [])
        for t in targets:
            norm_nhom = extract_nhom_th_int(t.get("nhom_th"))
            guid = str(t.get("guid_lhp", ""))
            if not t.get("target_key"):
                t["target_key"] = f"{guid}_{norm_nhom if norm_nhom is not None else 0}"
            t["nhom_th"] = norm_nhom
        return {"success": True, "targets": targets}

    def remove_target(self, target_key: str) -> Dict[str, Any]:
        """
        Removes a target from config and sniper service by target_key.
        """
        targets = self.config.get("target_classes", [])
        new_targets = []
        for t in targets:
            norm_nhom = extract_nhom_th_int(t.get("nhom_th"))
            guid = str(t.get("guid_lhp", ""))
            t_key = t.get("target_key") or f"{guid}_{norm_nhom if norm_nhom is not None else 0}"
            if t_key != str(target_key):
                new_targets.append(t)

        self.config["target_classes"] = new_targets
        self._save_config()
        self.sniper.targets = new_targets
        return {"success": True, "targets": new_targets}

    def clear_targets(self) -> Dict[str, Any]:
        """
        Clears all targets from config and sniper service.
        """
        self.config["target_classes"] = []
        self._save_config()
        self.sniper.targets = []
        return {"success": True, "targets": []}
    def add_target(
        self,
        id_dot: str,
        ma_mon: str,
        ma_hp: str,
        ten_mon: str,
        guid_lhp: str,
        ten_lop: str,
        nhom_th: Optional[Any] = None,
        loai_dk: int = 1,
        ma_mon_cha: str = "",
        schedules: Optional[List[Dict[str, Any]]] = None,
        lich_lt: str = "",
        lich_th: str = "",
        giang_vien: str = ""
    ) -> Dict[str, Any]:
        """
        Adds a target class + practice group to the sniper queue using composite key (guid_lhp, nhom_th).
        """
        norm_nhom = extract_nhom_th_int(nhom_th)
        target_key = f"{guid_lhp}_{norm_nhom if norm_nhom is not None else 0}"
        targets = self.config.setdefault("target_classes", [])

        exists = any(
            t.get("guid_lhp") == str(guid_lhp) and extract_nhom_th_int(t.get("nhom_th")) == norm_nhom
            for t in targets
        )
        if not exists:
            entry = {
                "target_key": target_key,
                "id_dot": str(id_dot),
                "ma_mon": str(ma_mon),
                "ma_hp": str(ma_hp),
                "ten_mon": str(ten_mon),
                "guid_lhp": str(guid_lhp),
                "ten_lop": str(ten_lop),
                "nhom_th": norm_nhom,
                "loai_dk": int(loai_dk),
                "ma_mon_cha": str(ma_mon_cha or ""),
                "registered": False,
                "schedules": schedules or [],
                "lich_lt": str(lich_lt or ""),
                "lich_th": str(lich_th or ""),
                "giang_vien": str(giang_vien or "")
            }
            targets.append(entry)
            self._save_config()
            self.sniper.targets = targets

        return {"success": True, "target_key": target_key, "targets": targets}

    def poll_sniper_once(self) -> Dict[str, Any]:
        events = []
        any_registered = False

        def on_ev(ev_type: str, data: Dict[str, Any]):
            nonlocal any_registered
            t_obj = data.get("target", {})
            cls_obj = data.get("class")
            res_obj = data.get("result") or {}
            norm_nhom = extract_nhom_th_int(t_obj.get("nhom_th"))
            guid = t_obj.get("guid_lhp", "")
            t_key = t_obj.get("target_key") or f"{guid}_{norm_nhom if norm_nhom is not None else 0}"
            is_reg = bool(t_obj.get("registered", False))
            if is_reg:
                any_registered = True

            events.append({
                "type": ev_type,
                "target_key": t_key,
                "guid_lhp": guid,
                "ten_mon": t_obj.get("ten_mon", t_obj.get("ma_mon", "")),
                "ten_lop": t_obj.get("ten_lop", guid),
                "nhom_th": norm_nhom,
                "loai_dk": int(t_obj.get("loai_dk", 1)),
                "si_so_dk": getattr(cls_obj, "si_so_dk", None) if cls_obj else None,
                "si_so_max": getattr(cls_obj, "si_so_max", None) if cls_obj else None,
                "slot_available": bool(data.get("slot_available", False)),
                "latency_ms": data.get("latency_ms", 0),
                "registered": is_reg,
                "message": res_obj.get("message") or data.get("error") or "",
                "timestamp": time.strftime("%H:%M:%S")
            })

        self.sniper.poll_once(on_event=on_ev)
        if any_registered:
            self._reg_sched_cache.clear()
            self._save_config()
        return {"success": True, "events": events}

    def ping_radar(self, id_dot: str = "62") -> Dict[str, Any]:
        self.radar.id_dot = str(id_dot)
        return self.radar.check_status()

    def prepare_login_challenge(self) -> Dict[str, Any]:
        """
        Downloads fresh CSRF token and Captcha image, returning Base64 data URI for inline GUI rendering.
        """
        try:
            res = self.client.get(IUHEndpoints.LOGIN_PAGE)
            html = res.read().decode("utf-8", errors="replace")
            m = re.search(r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']*)["\']', html)
            if m:
                self._login_token = m.group(1)

            cap_res = self.client.get(IUHEndpoints.GET_CAPTCHA)
            cap_bytes = cap_res.read()

            img_path = os.path.join(tempfile.gettempdir(), "iuh_ledger_captcha.jpg")
            try:
                with open(img_path, "wb") as f:
                    f.write(cap_bytes)
            except Exception:
                pass
            b64_str = base64.b64encode(cap_bytes).decode("ascii")
            data_uri = f"data:image/jpeg;base64,{b64_str}"

            return {
                "success": True,
                "image_data_uri": data_uri,
                "path": os.path.abspath(img_path)
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def submit_login(self, username: str, password: str, captcha_code: str) -> Dict[str, Any]:
        from iuh_ledger.core.crypto import encrypt_iuh_password
        try:
            if not self._login_token:
                self.prepare_login_challenge()

            key_res = self.client.get(f"{IUHEndpoints.GET_PRIVATE_KEY}?salt={username}")
            priv_key = key_res.read().decode("utf-8", errors="replace").strip()
            enc_pwd = encrypt_iuh_password(password, priv_key)

            post_data = {
                "__RequestVerificationToken": self._login_token or "",
                "UserName": username,
                "Password": enc_pwd,
                "IsSinhVienDaTotNghiep": "false",
                "Captcha": str(captcha_code).strip(),
                "SSOData": ""
            }
            self.client.post(IUHEndpoints.LOGIN_PAGE, data=post_data, follow_redirects=True)
            cookies = self.client.get_cookies_dict()

            if "ASC.AUTH" in cookies or self.client.is_session_valid():
                self.client.save_cookies()
                self._reg_sched_cache.clear()
                self.config["username"] = username
                self.config["password"] = password
                self._save_config()
                return {"success": True, "message": "Đăng nhập thành công"}

            return {"success": False, "message": "Mã bảo vệ hoặc thông tin tài khoản không khớp."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def logout(self) -> Dict[str, Any]:
        """
        Clears in-memory cookies, deletes session.json, and invalidates schedule caches.
        """
        try:
            self.radar.stop_heartbeat()
            self.sniper.stop()
            self.client.clear_cookies()
            self._reg_sched_cache.clear()
            if self.client.session_path and os.path.exists(self.client.session_path):
                try:
                    os.remove(self.client.session_path)
                except Exception:
                    pass
            return {"success": True, "message": "Đã đăng xuất và xóa phiên làm việc."}
        except Exception as e:
            return {"success": False, "message": str(e)}
    def get_settings(self) -> Dict[str, Any]:
        """
        Retrieves current system settings and background job configuration.
        """
        return {
            "success": True,
            "settings": {
                "heartbeat_interval_seconds": int(self.config.get("heartbeat_interval_seconds", 62)),
                "sniper_poll_interval_ms": int(self.config.get("sniper_poll_interval_ms", 1500)),
                "telegram_bot_token": str(self.config.get("telegram_bot_token", "")),
                "telegram_chat_id": str(self.config.get("telegram_chat_id", "")),
                "audio_chime_enabled": bool(self.config.get("audio_chime_enabled", True)),
                "auto_swap_same_course": bool(self.config.get("auto_swap_same_course", True)),
                "username": str(self.config.get("username", "")),
                "id_dot_dang_ky": str(self.config.get("id_dot_dang_ky", "62")),
                "loai_dk": int(self.config.get("loai_dk", 1))
            }
        }

    def save_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves system settings and updates active service parameters.
        """
        if not isinstance(settings, dict):
            return {"success": False, "message": "Cấu hình không hợp lệ."}
        for k in ["heartbeat_interval_seconds", "sniper_poll_interval_ms", "telegram_bot_token",
                  "telegram_chat_id", "audio_chime_enabled", "auto_swap_same_course",
                  "id_dot_dang_ky", "loai_dk"]:
            if k in settings:
                self.config[k] = settings[k]
        if "heartbeat_interval_seconds" in settings:
            try:
                self.radar.interval_seconds = int(settings["heartbeat_interval_seconds"])
            except Exception:
                pass
        self._save_config()
        return {"success": True, "message": "Cấu hình đã được lưu thành công.", "settings": self.get_settings()["settings"]}

    @staticmethod
    def _compute_week_dates(anchor_date_str: str = "") -> Dict[str, Any]:
        from datetime import datetime, timedelta
        if anchor_date_str:
            try:
                dt = datetime.strptime(str(anchor_date_str).strip(), "%d/%m/%Y")
            except Exception:
                dt = datetime.now()
        else:
            dt = datetime.now()
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = dt - timedelta(days=dt.weekday())
        prev_monday = monday - timedelta(days=7)
        next_monday = monday + timedelta(days=7)
        day_codes = ["2", "3", "4", "5", "6", "7", "CN"]
        day_dates = {}
        day_dt_map = {}
        for idx, code in enumerate(day_codes):
            d_obj = monday + timedelta(days=idx)
            day_dates[code] = d_obj.strftime("%d/%m/%Y")
            day_dt_map[code] = d_obj
        return {
            "prev_week": prev_monday.strftime("%d/%m/%Y"),
            "current_week": monday.strftime("%d/%m/%Y"),
            "next_week": next_monday.strftime("%d/%m/%Y"),
            "day_dates": day_dates,
            "day_dt_map": day_dt_map
        }

    def get_weekly_schedule(
        self,
        id_dot: str = "62",
        preview_classes: Optional[List[Dict[str, Any]]] = None,
        ngay_hien_tai: str = "",
        loai_lich: int = 0
    ) -> Dict[str, Any]:
        """
        Builds weekly timetable matrix:
        1. Computes the target week dates (or adjusts to the semester's active week when switching semesters).
        2. Fetches registered courses and their detailed schedules (cached in memory to prevent 429 rate-limits)
           and filters every schedule row strictly by `start_date <= column_date <= end_date` so one-off makeup
           or past/future phase rows NEVER stack on the same week!
        3. If the semester has 0 registered courses or is in current week, supplements from GetDanhSachLichTheoTuan
           (including Lịch thi / exam cards).
        4. Offline fallback: parses captured GetDanhSachLichTheoTuan HTML response.
        """
        raw_slots: List[Dict[str, Any]] = []
        has_live_session = False
        registered_count = 0
        week_info = self._compute_week_dates(ngay_hien_tai)

        # 1. Fetch semester registered courses & their schedules (with in-memory caching to avoid 429)
        try:
            cache_key = str(id_dot)
            cached_entry = self._reg_sched_cache.get(cache_key)
            now_ts = time.time()
            if cached_entry and (now_ts - cached_entry[0] < 120):
                reg_res, scheds_by_guid = cached_entry[1], cached_entry[2]
                has_live_session = True
                registered_count = len(reg_res)
            else:
                reg_res = self.catalog.get_registered_courses(id_dot=str(id_dot))
                scheds_by_guid: Dict[str, List[Any]] = {}
                if reg_res is not None:
                    if len(reg_res) > 0 or self.client.is_session_valid():
                        has_live_session = True
                    registered_count = len(reg_res)

                def _fetch_reg_sched(c_item):
                    g_lhp = getattr(c_item, "guid_lhp", "") or getattr(c_item, "guid", "")
                    if not g_lhp:
                        return g_lhp, []
                    try:
                        return g_lhp, self.catalog.get_class_schedule(g_lhp, timeout=10)
                    except Exception:
                        return g_lhp, []

                if reg_res:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        for g_lhp, scheds in pool.map(_fetch_reg_sched, reg_res):
                            if g_lhp:
                                scheds_by_guid[g_lhp] = scheds
                    if scheds_by_guid:
                        self._reg_sched_cache[cache_key] = (now_ts, reg_res, scheds_by_guid)

            if reg_res:
                # If user hasn't manually picked a week date, check if current week falls outside the semester's date range
                if not ngay_hien_tai:
                    all_start_dates = []
                    for g_lhp, scheds in scheds_by_guid.items():
                        for s in scheds:
                            st_d, en_d = self._parse_date_range(getattr(s, "thoi_gian", ""))
                            if st_d and en_d:
                                all_start_dates.append((st_d, en_d))
                    if all_start_dates:
                        sem_min = min(x[0] for x in all_start_dates)
                        sem_max = max(x[1] for x in all_start_dates)
                        curr_mon = week_info["day_dt_map"]["2"]
                        curr_sun = week_info["day_dt_map"]["CN"]
                        if curr_sun < sem_min or curr_mon > sem_max:
                            # Jump to the first active week of that semester so the user sees its real weekly schedule
                            week_info = self._compute_week_dates(sem_min.strftime("%d/%m/%Y"))

                for c_item in reg_res:
                    g_lhp = getattr(c_item, "guid_lhp", "") or getattr(c_item, "guid", "")
                    scheds = scheds_by_guid.get(g_lhp, [])
                    c_nhom = extract_nhom_th_int(getattr(c_item, "nhom_th", None))
                    for s in scheds:
                        s_nhom = extract_nhom_th_int(getattr(s, "nhom_th", None))
                        if s_nhom is not None and c_nhom is not None and s_nhom != c_nhom:
                            continue
                        parsed = self._parse_schedule_slot(
                            s,
                            c_item.ten_mon,
                            c_item.ma_lhp,
                            c_item.lop_du_kien,
                            is_preview=False,
                            selected_nhom=c_nhom
                        )
                        if not parsed:
                            continue
                        # Strict week-date filter: only include rows active on that weekday's exact date!
                        d_code = parsed.get("day", "")
                        col_dt = week_info["day_dt_map"].get(d_code)
                        st_dt, en_dt = self._parse_date_range(parsed.get("thoi_gian", ""))
                        if col_dt and st_dt and en_dt:
                            if not (st_dt <= col_dt <= en_dt):
                                continue
                        raw_slots.append(parsed)
        except Exception:
            pass

        # 2. Supplement or populate from POST /SinhVien/GetDanhSachLichTheoTuan (includes exam cards like Lịch thi)
        try:
            if hasattr(self.catalog, "get_weekly_timetable") and (not raw_slots or week_info["current_week"] == self._compute_week_dates("")["current_week"]):
                tt_res = self.catalog.get_weekly_timetable(ngay_hien_tai=week_info["current_week"], loai_lich=loai_lich)
                if tt_res:
                    for k in ("prev_week", "current_week", "next_week", "day_dates"):
                        if tt_res.get(k):
                            week_info[k] = tt_res[k]
                    if tt_res.get("day_dates"):
                        from datetime import datetime
                        week_info["day_dt_map"] = {
                            code: datetime.strptime(d_str, "%d/%m/%Y")
                            for code, d_str in tt_res["day_dates"].items()
                            if re.match(r'^\d{2}/\d{2}/\d{4}$', str(d_str))
                        }
                    if tt_res.get("slots"):
                        has_live_session = True
                        if not raw_slots:
                            raw_slots = list(tt_res["slots"])
                            if not registered_count:
                                registered_count = len({s.get("ma_lhp") or s.get("ten_mon") for s in raw_slots})
                        else:
                            # Merge any exam slots (lich_thi) from GetDanhSachLichTheoTuan not present in GetChiTietLichHoc
                            for ts in tt_res["slots"]:
                                if ts.get("loai") == "lich_thi":
                                    raw_slots.append(ts)
        except Exception:
            pass

        # 3. Offline fallback: parse directly from captured GetDanhSachLichTheoTuan HTML response (when not authenticated)
        if not raw_slots and not has_live_session:
            cap_tt = self._load_captured_weekly_timetable()
            if cap_tt:
                raw_slots = list(cap_tt.get("slots", []))
                for k in ("prev_week", "current_week", "next_week", "day_dates"):
                    if cap_tt.get(k):
                        week_info[k] = cap_tt[k]
                if cap_tt.get("day_dates"):
                    from datetime import datetime
                    week_info["day_dt_map"] = {
                        code: datetime.strptime(d_str, "%d/%m/%Y")
                        for code, d_str in cap_tt["day_dates"].items()
                        if re.match(r'^\d{2}/\d{2}/\d{4}$', str(d_str))
                    }
                if not registered_count:
                    registered_count = len({s.get("ma_lhp") or s.get("ten_mon") for s in raw_slots})

        # 4. Append preview classes if provided (from Schedule Sandbox or Watchdog queue)
        if preview_classes:
            for p in preview_classes:
                p_dot = str(p.get("id_dot", id_dot))
                if p_dot and p_dot != str(id_dot):
                    continue
                guid = p.get("guid_lhp", "")
                ten_mon = p.get("ten_mon", "")
                ma_lhp = p.get("ma_lhp", "") or p.get("ma_hp", "")
                ten_lop = p.get("ten_lop", "")
                p_nhom = extract_nhom_th_int(p.get("nhom_th"))
                p_scheds: List[Any] = []

                embedded_scheds = p.get("schedules")
                if isinstance(embedded_scheds, list) and len(embedded_scheds) > 0:
                    p_scheds = [SimpleNamespace(**s) if isinstance(s, dict) else s for s in embedded_scheds]

                if not p_scheds and guid:
                    try:
                        p_scheds = self.catalog.get_class_schedule(guid, timeout=10)
                    except Exception:
                        p_scheds = []

                if not p_scheds:
                    p_scheds = self._synthesize_schedules_from_strings(p)

                # Check if any preview row has dates overlapping the displayed week
                week_mon = week_info["day_dt_map"].get("2")
                week_sun = week_info["day_dt_map"].get("CN")
                has_overlapping_preview_dates = False
                if week_mon and week_sun:
                    for ps in p_scheds:
                        st_d, en_d = self._parse_date_range(getattr(ps, "thoi_gian", ""))
                        if st_d and en_d and max(st_d, week_mon) <= min(en_d, week_sun):
                            has_overlapping_preview_dates = True
                            break

                for ps in p_scheds:
                    s_nhom = extract_nhom_th_int(getattr(ps, "nhom_th", None))
                    if s_nhom is not None and p_nhom is not None and s_nhom != p_nhom:
                        continue
                    parsed = self._parse_schedule_slot(
                        ps,
                        ten_mon,
                        ma_lhp,
                        ten_lop,
                        is_preview=True,
                        selected_nhom=p_nhom
                    )
                    if not parsed:
                        continue
                    if has_overlapping_preview_dates:
                        col_dt = week_info["day_dt_map"].get(parsed.get("day", ""))
                        st_d, en_d = self._parse_date_range(parsed.get("thoi_gian", ""))
                        if col_dt and st_d and en_d and not (st_d <= col_dt <= en_d):
                            continue
                    parsed["target_key"] = p.get("target_key") or f"{guid}_{p_nhom if p_nhom is not None else 0}"
                    raw_slots.append(parsed)

        slots = self._dedupe_and_detect_conflicts(raw_slots)
        conflict_count = sum(1 for sl in slots if sl.get("has_conflict"))

        return {
            "success": True,
            "id_dot": str(id_dot),
            "has_live_session": has_live_session,
            "registered_count": registered_count,
            "conflict_count": conflict_count,
            "prev_week": week_info.get("prev_week", ""),
            "current_week": week_info.get("current_week", ""),
            "next_week": week_info.get("next_week", ""),
            "day_dates": week_info.get("day_dates", {}),
            "slots": slots
        }
    @staticmethod
    def _synthesize_schedules_from_strings(p: Dict[str, Any]) -> List[Any]:
        """
        Synthesizes ClassSchedule-compatible objects from formatted summary strings (lich_lt, lich_th)
        when live GetChiTietLichHoc is unavailable or for demo/offline preview classes.
        """
        results = []
        gv = str(p.get("giang_vien", "") or "Đang cập nhật")
        thoi_gian = str(p.get("thoi_gian", "") or "")
        co_so = str(p.get("co_so", "") or "Cơ sở 1")
        p_nhom = p.get("nhom_th")

        for loai_code, raw_str, nhom_val in [
            ("LT", str(p.get("lich_lt", "") or ""), ""),
            ("TH", str(p.get("lich_th", "") or ""), str(p_nhom) if p_nhom is not None else "1")
        ]:
            if not raw_str:
                continue
            for seg in re.split(r'\s*\|\s*', raw_str):
                seg = seg.strip()
                if not seg or "chưa công bố" in seg.lower():
                    continue
                m_phong = re.search(r'Phòng\s*([^|·,]+)', seg, re.IGNORECASE)
                phong = m_phong.group(1).strip() if m_phong else (str(p.get("phong", "")) or "N4.6 CLC")
                results.append(SimpleNamespace(
                    stt=str(len(results) + 1),
                    loai_tiet=loai_code,
                    thu_tiet=f"{loai_code} - {seg}",
                    nhom_th=nhom_val if loai_code == "TH" else "",
                    phong=phong,
                    day_nha="",
                    co_so=co_so,
                    giang_vien=gv,
                    thoi_gian=thoi_gian
                ))
        return results

    @staticmethod
    def _parse_date_range(tg_str: str):
        if not tg_str:
            return None, None
        from datetime import datetime
        dates = re.findall(r'(\d{2}/\d{2}/\d{4})', str(tg_str))
        if not dates:
            return None, None
        try:
            parsed_dates = [datetime.strptime(d, "%d/%m/%Y") for d in dates]
            return min(parsed_dates), max(parsed_dates)
        except Exception:
            return None, None

    def _dedupe_and_detect_conflicts(self, raw_slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merges multi-phase rows of the same course in the same (day, ca, ma_lhp, is_preview)
        and detects true period + date-range overlaps between different courses on the same day.
        """
        merged_map: Dict[tuple, Dict[str, Any]] = {}
        for sl in raw_slots:
            key = (
                sl.get("day"),
                sl.get("ca"),
                sl.get("ma_lhp") or sl.get("ten_mon"),
                bool(sl.get("is_preview", False))
            )
            if key not in merged_map:
                merged_map[key] = dict(sl)
            else:
                existing = merged_map[key]
                st_old, en_old = existing.get("tiet_start", 0), existing.get("tiet_end", 0)
                st_new, en_new = sl.get("tiet_start", 0), sl.get("tiet_end", 0)
                # If two sessions of the same course in the same shift have disjoint periods (e.g. LT tiết 1-2 and TH tiết 4-6), keep both slots separate
                if st_new and en_new and st_old and en_old and max(st_old, st_new) > min(en_old, en_new) + 1:
                    disjoint_key = (*key, st_new, sl.get("loai", ""))
                    merged_map[disjoint_key] = dict(sl)
                    continue
                if st_new and en_new:
                    st_min = min(st_old, st_new) if st_old else st_new
                    en_max = max(en_old, en_new) if en_old else en_new
                    existing["tiet_start"] = st_min
                    existing["tiet_end"] = en_max
                    existing["tiet"] = f"{st_min} - {en_max}"
                # Prefer physical room over "Trực tuyến" when a course has both phases, or combine rooms
                p_new = sl.get("phong", "")
                p_old = existing.get("phong", "")
                if p_new and p_new not in p_old:
                    if "trực tuyến" in p_old.lower() and "trực tuyến" not in p_new.lower():
                        existing["phong"] = f"{p_new} (kèm lịch Trực tuyến)"
                        if existing.get("loai") == "truc_tuyen":
                            existing["loai"] = sl.get("loai", "ly_thuyet")
                    elif "trực tuyến" in p_new.lower() and "trực tuyến" not in p_old.lower():
                        if "Trực tuyến" not in existing["phong"]:
                            existing["phong"] = f"{p_old} (kèm lịch Trực tuyến)"
                    else:
                        existing["phong"] = f"{p_old}, {p_new}"
                t_new = sl.get("thoi_gian", "")
                t_old = existing.get("thoi_gian", "")
                if t_new and t_new not in t_old:
                    existing["thoi_gian"] = f"{t_old}; {t_new}" if t_old else t_new

        slots = list(merged_map.values())

        # Detect period + date overlaps on the same day between distinct courses
        for i, s1 in enumerate(slots):
            s1["has_conflict"] = False
            s1["conflict_with"] = []
            d1 = s1.get("day")
            st1 = s1.get("tiet_start", 0)
            en1 = s1.get("tiet_end", 0)
            id1 = s1.get("ma_lhp") or s1.get("ten_mon")
            if not st1 or not en1:
                continue
            dt1_start, dt1_end = self._parse_date_range(s1.get("thoi_gian", ""))
            for j, s2 in enumerate(slots):
                if i == j or s2.get("day") != d1:
                    continue
                id2 = s2.get("ma_lhp") or s2.get("ten_mon")
                if id1 == id2 and s1.get("is_preview") == s2.get("is_preview"):
                    continue
                st2 = s2.get("tiet_start", 0)
                en2 = s2.get("tiet_end", 0)
                if st2 and en2 and max(st1, st2) <= min(en1, en2):
                    dt2_start, dt2_end = self._parse_date_range(s2.get("thoi_gian", ""))
                    # Check date overlap if both have dates
                    if dt1_start and dt1_end and dt2_start and dt2_end:
                        if max(dt1_start, dt2_start) > min(dt1_end, dt2_end):
                            continue
                    s1["has_conflict"] = True
                    other_name = s2.get("ten_mon", "Học phần khác")
                    if other_name not in s1["conflict_with"]:
                        s1["conflict_with"].append(other_name)

        slots.sort(key=lambda x: (str(x.get("day", "")), int(x.get("tiet_start", 0) or 0)))
        return slots

    def _parse_schedule_slot(
        self,
        s: Any,
        ten_mon: str,
        ma_lhp: str,
        ten_lop: str,
        is_preview: bool = False,
        selected_nhom: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        thu_tiet = getattr(s, "thu_tiet", "")
        phong = getattr(s, "phong", "")
        loai_tiet = getattr(s, "loai_tiet", "")
        gv = getattr(s, "giang_vien", "")
        thoi_gian = getattr(s, "thoi_gian", "")
        s_nhom = extract_nhom_th_int(getattr(s, "nhom_th", None))

        # Match Day
        m_day = re.search(r'(Thứ\s*[2-7]|Chủ\s*nhật)', thu_tiet, re.IGNORECASE)
        if not m_day:
            return None
        day_raw = m_day.group(1).lower()
        day_code = "CN" if "chủ" in day_raw else re.sub(r'[^\d]', '', day_raw)

        # Match Period (Tiết)
        m_tiet = re.search(r'Tiết\s*(\d+)(?:\s*(?:->|-)\s*(\d+))?', thu_tiet, re.IGNORECASE)
        if not m_tiet:
            return None
        start_t = int(m_tiet.group(1))
        end_t = int(m_tiet.group(2)) if m_tiet.group(2) else start_t
        tiet_range = f"{start_t} - {end_t}"

        if start_t <= 6:
            ca = "sang"
        elif start_t <= 12:
            ca = "chieu"
        else:
            ca = "toi"

        # Classification legend
        if "thi" in loai_tiet.lower():
            loai = "lich_thi"
        elif "tạm ngưng" in loai_tiet.lower() or "ngưng" in loai_tiet.lower():
            loai = "tam_ngung"
        elif "trực tuyến" in phong.lower() or "online" in phong.lower() or "teams" in phong.lower():
            loai = "truc_tuyen"
        elif str(loai_tiet).upper() == "TH" or "thực hành" in loai_tiet.lower():
            loai = "thuc_hanh"
        else:
            loai = "ly_thuyet"

        ghi_chu_parts = []
        if s_nhom is not None:
            ghi_chu_parts.append(f"Nhóm TH {s_nhom}")
        elif selected_nhom is not None and loai == "thuc_hanh":
            ghi_chu_parts.append(f"Nhóm TH {selected_nhom}")
        if "teams" in phong.lower():
            ghi_chu_parts.append("MS Teams")

        full_lop = f"{ten_lop} - {ma_lhp}" if ma_lhp and ma_lhp not in ten_lop else ten_lop
        day_nha = getattr(s, "day_nha", "")
        full_phong = f"{phong} ({day_nha})" if day_nha and day_nha not in phong else phong

        return {
            "day": day_code,
            "ca": ca,
            "ten_mon": ten_mon,
            "ma_lhp": ma_lhp,
            "ten_lop": full_lop,
            "tiet": tiet_range,
            "tiet_start": start_t,
            "tiet_end": end_t,
            "phong": full_phong,
            "giang_vien": gv,
            "thoi_gian": thoi_gian,
            "ghi_chu": ", ".join(ghi_chu_parts),
            "loai": loai,
            "is_preview": is_preview
        }
    @staticmethod
    def _load_captured_weekly_timetable() -> Dict[str, Any]:
        """
        Loads and parses the authentic captured response from POST /SinhVien/GetDanhSachLichTheoTuan
        stored in capture/004_GetDanhSachLichTheoTuan_POST.txt when running offline.
        """
        from iuh_ledger.core.parser import IUHHTMLParser
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [
            os.path.join(base_dir, "capture", "004_GetDanhSachLichTheoTuan_POST.txt"),
            os.path.join("capture", "004_GetDanhSachLichTheoTuan_POST.txt"),
            os.path.join("iuh-ledger", "capture", "004_GetDanhSachLichTheoTuan_POST.txt"),
            os.path.join("iuh-dkhp-tool-master", "capture", "004_GetDanhSachLichTheoTuan_POST.txt")
        ]
        for c_path in candidates:
            if os.path.exists(c_path):
                try:
                    with open(c_path, "r", encoding="utf-8") as f:
                        raw = f.read()
                    resp_html = raw.split("# Response", 1)[1] if "# Response" in raw else raw
                    return IUHHTMLParser.parse_weekly_timetable(resp_html)
                except Exception:
                    pass
        return {"prev_week": "", "current_week": "", "next_week": "", "day_dates": {}, "slots": []}
