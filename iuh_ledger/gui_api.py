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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
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
            "thoi_gian": ", ".join(all_dates)
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
            "thoi_gian": ", ".join(grp_dates)
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
        if getattr(sys, 'frozen', False):
            target = os.path.join(os.path.dirname(sys.executable), self.config_path)
        else:
            candidates = [self.config_path, os.path.join("iuh_ledger", self.config_path)]
            target = candidates[0]
            for c in candidates:
                if os.path.exists(c):
                    target = c
                    break
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

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
        return self.registration.register_class(
            id_dot=str(id_dot),
            guid_lhp=str(guid_lhp),
            loai_dk=int(loai_dk),
            nhom_th=norm_nhom,
            ma_mon_cha=str(ma_mon_cha or "")
        )

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
        return self.registration.cancel_registered_class(id_dk=str(id_dk), guid_dk=str(guid_dk))

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
        ma_mon_cha: str = ""
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
                "registered": False
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

            gui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui")
            os.makedirs(gui_dir, exist_ok=True)
            img_path = os.path.join(gui_dir, "captcha.jpg")
            with open(img_path, "wb") as f:
                f.write(cap_bytes)

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
                self.config["username"] = username
                self.config["password"] = password
                self._save_config()
                return {"success": True, "message": "Đăng nhập thành công"}

            return {"success": False, "message": "Mã bảo vệ hoặc thông tin tài khoản không khớp."}
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
                  "telegram_chat_id", "audio_chime_enabled", "auto_swap_same_course"]:
            if k in settings:
                self.config[k] = settings[k]
        if "heartbeat_interval_seconds" in settings:
            try:
                self.radar.interval_seconds = int(settings["heartbeat_interval_seconds"])
            except Exception:
                pass
        self._save_config()
        return {"success": True, "message": "Cấu hình đã được lưu thành công.", "settings": self.get_settings()["settings"]}

    def get_weekly_schedule(self, id_dot: str = "62", preview_classes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Builds weekly timetable matrix from actual registered courses in the semester,
        plus optional preview target classes (e.g. from Watchdog queue or interactive class preview).
        """
        raw_slots: List[Dict[str, Any]] = []
        has_live_session = False
        registered_count = 0

        try:
            reg_res = self.catalog.get_registered_courses(id_dot=str(id_dot))
            if reg_res is not None:
                # Check if session actually returned courses or if client has valid session
                if len(reg_res) > 0 or self.client.is_session_valid():
                    has_live_session = True
                registered_count = len(reg_res)

            def _fetch_reg_sched(c_item):
                g_lhp = getattr(c_item, "guid_lhp", "") or getattr(c_item, "guid", "")
                if not g_lhp:
                    return c_item, []
                try:
                    return c_item, self.catalog.get_class_schedule(g_lhp, timeout=10)
                except Exception:
                    return c_item, []

            if reg_res:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    for c_item, scheds in pool.map(_fetch_reg_sched, reg_res):
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
                            if parsed:
                                raw_slots.append(parsed)
        except Exception:
            pass

        # Fallback to authentic schedule template ONLY when offline / no live session and no preview
        if not raw_slots and not has_live_session and not preview_classes:
            raw_slots = self._get_default_authentic_schedule()

        # Append preview classes if provided (or from sniper targets belonging to id_dot)
        if preview_classes:
            for p in preview_classes:
                p_dot = str(p.get("id_dot", id_dot))
                if p_dot and p_dot != str(id_dot):
                    continue
                guid = p.get("guid_lhp", "")
                ten_mon = p.get("ten_mon", "")
                ma_lhp = p.get("ma_hp", "") or p.get("ma_lhp", "")
                ten_lop = p.get("ten_lop", "")
                p_nhom = extract_nhom_th_int(p.get("nhom_th"))
                if guid:
                    try:
                        p_scheds = self.catalog.get_class_schedule(guid, timeout=10)
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
                            if parsed:
                                raw_slots.append(parsed)
                    except Exception:
                        pass

        slots = self._dedupe_and_detect_conflicts(raw_slots)
        conflict_count = sum(1 for sl in slots if sl.get("has_conflict"))

        return {
            "success": True,
            "id_dot": str(id_dot),
            "has_live_session": has_live_session,
            "registered_count": registered_count,
            "conflict_count": conflict_count,
            "slots": slots
        }

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
                # Expand period range if a makeup/sub-range exists in the same shift
                st_old, en_old = existing.get("tiet_start", 0), existing.get("tiet_end", 0)
                st_new, en_new = sl.get("tiet_start", 0), sl.get("tiet_end", 0)
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
    def _get_default_authentic_schedule(self) -> List[Dict[str, Any]]:
        return [
            {
                "day": "2",
                "ca": "sang",
                "ten_mon": "Triết học Mác - Lênin",
                "ma_lhp": "429701380102",
                "ten_lop": "DHTMDT20B_TCTA - 429701380102",
                "tiet": "4 - 6",
                "phong": "N4.4 (N - Cơ sở Nguyễn Văn Dung)",
                "giang_vien": "Nguyễn Thị Kim Chung",
                "ghi_chu": "",
                "loai": "ly_thuyet",
                "is_preview": False
            },
            {
                "day": "2",
                "ca": "toi",
                "ten_mon": "Triết học Mác - Lênin",
                "ma_lhp": "429701380102",
                "ten_lop": "DHTMDT20B_TCTA - 429701380102",
                "tiet": "13 - 15",
                "phong": "Trực tuyến (Cơ sở 1)",
                "giang_vien": "Nguyễn Thị Kim Chung",
                "ghi_chu": "Teams: fbj2dsr",
                "loai": "truc_tuyen",
                "is_preview": False
            },
            {
                "day": "3",
                "ca": "chieu",
                "ten_mon": "Tài chính doanh nghiệp",
                "ma_lhp": "429700380206",
                "ten_lop": "DHKT21D_TCTA - 429700380206",
                "tiet": "7 - 9",
                "phong": "N10.3 (N - Cơ sở Nguyễn Văn Dung)",
                "giang_vien": "Lại Cao Mai Phương",
                "ghi_chu": "",
                "loai": "ly_thuyet",
                "is_preview": False
            },
            {
                "day": "4",
                "ca": "sang",
                "ten_mon": "Quản trị tác nghiệp Thương mại điện tử",
                "ma_lhp": "429701766202",
                "ten_lop": "DHTMDT20B_TCTA - 429701766202",
                "tiet": "1 - 3",
                "phong": "N4.4 (N - Cơ sở Nguyễn Văn Dung)",
                "giang_vien": "Võ Thị Minh Nhựt",
                "ghi_chu": "",
                "loai": "ly_thuyet",
                "is_preview": False
            },
            {
                "day": "6",
                "ca": "chieu",
                "ten_mon": "Tài chính doanh nghiệp",
                "ma_lhp": "429700380206",
                "ten_lop": "DHKT21D_TCTA - 429700380206",
                "tiet": "7 - 9",
                "phong": "N10.3 (N - Cơ sở Nguyễn Văn Dung)",
                "giang_vien": "Lại Cao Mai Phương",
                "ghi_chu": "",
                "loai": "ly_thuyet",
                "is_preview": False
            },
            {
                "day": "7",
                "ca": "sang",
                "ten_mon": "Phân tích thiết kế hệ thống thương mại điện tử",
                "ma_lhp": "429701766502",
                "ten_lop": "DHTMDT20B_TCTA - 429701766502",
                "tiet": "1 - 3",
                "phong": "H3.1.1 (H (CS1) - Cơ sở 1)",
                "giang_vien": "Lê Thị Ánh Tuyết",
                "ghi_chu": "",
                "loai": "thuc_hanh",
                "is_preview": False
            },
            {
                "day": "7",
                "ca": "chieu",
                "ten_mon": "Anh văn 3",
                "ma_lhp": "429701525716",
                "ten_lop": "DH Điện tử 20C TCTA - 429701525716",
                "tiet": "7 - 12",
                "phong": "X10.01",
                "giang_vien": "",
                "ghi_chu": "Lịch thi kết thúc học phần",
                "loai": "lich_thi",
                "is_preview": False
            }
        ]
