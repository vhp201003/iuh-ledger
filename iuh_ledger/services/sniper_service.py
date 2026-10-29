"""
IUH Ultra Sniper Engine
Polls target class enrollment statuses and fires instant registration when slots appear.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Callable
from iuh_ledger.core.models import Subject
from iuh_ledger.services.catalog_service import CatalogService
from iuh_ledger.services.registration_service import RegistrationService

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
        Executes one sweep across all targets in parallel (grouped by subject so multiple targets
        in the same subject only incur 1 catalog HTTP request).
        If a slot is detected, fires register_class immediately.
        """
        results: List[Dict[str, Any]] = []
        pending = [t for t in list(self.targets) if not t.get("registered")]
        if not pending:
            return results

        subject_groups: Dict[tuple, Dict[str, Any]] = {}
        for target in pending:
            key = (
                str(target.get("id_dot", "62")),
                str(target.get("ma_mon", "")),
                str(target.get("ma_hp", "")),
                int(target.get("loai_dk", 1)),
                str(target.get("ma_mon_cha", ""))
            )
            if key not in subject_groups:
                subject_groups[key] = {
                    "id_dot": key[0],
                    "loai_dk": key[3],
                    "subj": Subject(
                        id_mon="",
                        ma_mon=key[1],
                        ma_hp=key[2],
                        ten_mon=target.get("ten_mon", key[1]),
                        so_tc=0,
                        ma_mon_cha=key[4]
                    ),
                    "targets": []
                }
            subject_groups[key]["targets"].append(target)

        def _fetch_group(grp: Dict[str, Any]):
            t0 = time.time()
            try:
                cls_list = self.catalog.get_classes_for_subject(
                    grp["id_dot"],
                    grp["subj"],
                    khong_trung_lich=False,
                    loai_dk=grp["loai_dk"]
                )
                lat = int((time.time() - t0) * 1000)
                return (grp, cls_list, lat, None)
            except Exception as exc:
                lat = int((time.time() - t0) * 1000)
                return (grp, None, lat, exc)

        max_w = min(4, len(subject_groups))
        if max_w <= 1:
            group_outcomes = [_fetch_group(g) for g in subject_groups.values()]
        else:
            with ThreadPoolExecutor(max_workers=max_w) as pool:
                group_outcomes = list(pool.map(_fetch_group, subject_groups.values()))

        for grp, classes, latency_ms, err in group_outcomes:
            for target in grp["targets"]:
                if err is not None:
                    if on_event:
                        on_event("error", {"target": target, "error": str(err)})
                    continue

                matched_class = None
                for c in (classes or []):
                    if target.get("guid_lhp"):
                        matched = (c.guid_lhp == target["guid_lhp"])
                    else:
                        matched = bool(target.get("ten_lop") and c.ten_lop == target["ten_lop"])
                    if matched:
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
                    id_dot = str(target["id_dot"])
                    loai_dk_val = int(target.get("loai_dk", 1))
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

        return results

    def fire_all_once(self, on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> List[Dict[str, Any]]:
        """
        Dispatches direct registration requests in parallel for all pending targets
        without waiting for a catalog enrollment-count check (ideal for exact Giờ G opening).
        """
        results: List[Dict[str, Any]] = []
        pending = [t for t in list(self.targets) if not t.get("registered") and t.get("guid_lhp")]
        if not pending:
            return results

        def _fire_single(target: Dict[str, Any]):
            t0 = time.time()
            try:
                reg_res = self.registration.register_class(
                    id_dot=str(target.get("id_dot", "62")),
                    guid_lhp=str(target["guid_lhp"]),
                    loai_dk=int(target.get("loai_dk", 1)),
                    nhom_th=target.get("nhom_th"),
                    ma_mon_cha=str(target.get("ma_mon_cha", ""))
                )
                lat = int((time.time() - t0) * 1000)
                return (target, reg_res, lat, None)
            except Exception as exc:
                lat = int((time.time() - t0) * 1000)
                return (target, None, lat, exc)

        max_w = min(4, len(pending))
        if max_w <= 1:
            outcomes = [_fire_single(t) for t in pending]
        else:
            with ThreadPoolExecutor(max_workers=max_w) as pool:
                outcomes = list(pool.map(_fire_single, pending))

        for target, reg_res, latency_ms, err in outcomes:
            if err is not None:
                if on_event:
                    on_event("error", {"target": target, "error": str(err), "latency_ms": latency_ms})
                continue
            results.append({
                "target": target,
                "class": None,
                "registration_result": reg_res
            })
            if reg_res and reg_res.get("success"):
                target["registered"] = True
                if on_event:
                    on_event("success", {
                        "target": target,
                        "result": reg_res,
                        "class": None,
                        "slot_available": True,
                        "latency_ms": latency_ms
                    })
            else:
                if on_event:
                    on_event("failed", {
                        "target": target,
                        "result": reg_res or {},
                        "class": None,
                        "slot_available": False,
                        "latency_ms": latency_ms
                    })

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
