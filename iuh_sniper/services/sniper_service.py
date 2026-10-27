"""
IUH Ultra Sniper Engine
Polls target class enrollment statuses and fires instant registration when slots appear.
"""

import time
import threading
from typing import List, Dict, Any, Optional, Callable
from iuh_sniper.core.models import Subject
from iuh_sniper.services.catalog_service import CatalogService
from iuh_sniper.services.registration_service import RegistrationService

class SniperService:
    def __init__(self, catalog_service: CatalogService, registration_service: RegistrationService, 
                 targets: Optional[List[Dict[str, Any]]] = None):
        self.catalog = catalog_service
        self.registration = registration_service
        self.targets = targets or []
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def add_target(self, id_dot: str, ma_mon: str, ma_hp: str, guid_lhp: str, 
                   ten_lop: str = "", nhom_th: Optional[int] = None, ma_mon_cha: str = "", loai_dk: int = 1):
        self.targets.append({
            "id_dot": str(id_dot),
            "ma_mon": str(ma_mon),
            "ma_hp": str(ma_hp),
            "guid_lhp": str(guid_lhp),
            "ten_lop": ten_lop or guid_lhp,
            "nhom_th": int(nhom_th) if nhom_th is not None and str(nhom_th).strip() != "" else None,
            "ma_mon_cha": str(ma_mon_cha),
            "loai_dk": int(loai_dk),
            "registered": False
        })

    def poll_once(self, on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> List[Dict[str, Any]]:
        """
        Executes one sweep across all targets.
        If a slot is detected, fires register_class immediately.
        """
        results = []

        for target in self.targets:
            if target.get("registered"):
                continue

            id_dot = target["id_dot"]
            subj = Subject(
                id_mon="",
                ma_mon=target["ma_mon"],
                ma_hp=target["ma_hp"],
                ten_mon=target.get("ten_mon", target["ma_mon"]),
                so_tc=0,
                ma_mon_cha=target.get("ma_mon_cha", "")
            )

            try:
                t0 = time.time()
                loai_dk_val = int(target.get("loai_dk", 1))
                classes = self.catalog.get_classes_for_subject(id_dot, subj, khong_trung_lich=False, loai_dk=loai_dk_val)
                latency_ms = int((time.time() - t0) * 1000)

                # Match class
                matched_class = None
                for c in classes:
                    if c.guid_lhp == target["guid_lhp"] or (target.get("ten_lop") and c.ten_lop == target["ten_lop"]):
                        matched_class = c
                        break

                if not matched_class:
                    if on_event:
                        on_event("not_found", {"target": target, "latency_ms": latency_ms})
                    continue

                slot_available = (matched_class.si_so_dk < matched_class.si_so_max) and not matched_class.da_khoa

                if on_event:
                    on_event("checked", {
                        "target": target,
                        "class": matched_class,
                        "slot_available": slot_available,
                        "latency_ms": latency_ms
                    })

                if slot_available:
                    # FIRE REGISTRATION
                    reg_res = self.registration.register_class(
                        id_dot=id_dot,
                        guid_lhp=matched_class.guid_lhp,
                        loai_dk=loai_dk_val,
                        nhom_th=target.get("nhom_th"),
                        ma_mon_cha=target.get("ma_mon_cha", "")
                    )

                    results.append({
                        "target": target,
                        "class": matched_class,
                        "registration_result": reg_res
                    })

                    if reg_res.get("success"):
                        target["registered"] = True
                        if on_event:
                            on_event("success", {
                                "target": target,
                                "result": reg_res,
                                "class": matched_class,
                                "slot_available": True,
                                "latency_ms": latency_ms
                            })
                    else:
                        if on_event:
                            on_event("failed", {
                                "target": target,
                                "result": reg_res,
                                "class": matched_class,
                                "slot_available": True,
                                "latency_ms": latency_ms
                            })

            except Exception as e:
                if on_event:
                    on_event("error", {"target": target, "error": str(e)})

        return results

    def run_loop(self, delay_ms: int = 1500, max_attempts: int = 1000, 
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        """
        Runs the continuous polling sniper loop.
        """
        self.is_running = True
        attempts = 0

        while self.is_running and attempts < max_attempts:
            attempts += 1
            self.poll_once(on_event=on_event)

            # Check if all targets registered
            if all(t.get("registered") for t in self.targets) and len(self.targets) > 0:
                self.is_running = False
                break

            time.sleep(max(0.2, delay_ms / 1000.0))

        self.is_running = False

    def stop(self):
        self.is_running = False
