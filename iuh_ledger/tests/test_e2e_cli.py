"""
Comprehensive End-to-End and Integration Test Suite
Verifies crypto, parser, client session, endpoints contract, and services.
"""

import os
import json
import unittest
from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.crypto import encrypt_iuh_password
from iuh_ledger.core.client import IUHClient
from iuh_ledger.core.parser import IUHHTMLParser
from iuh_ledger.core.models import Subject, CourseClass, ClassSchedule
from iuh_ledger.services.catalog_service import CatalogService
from iuh_ledger.services.registration_service import RegistrationService
from iuh_ledger.services.radar_service import RadarService
from iuh_ledger.services.sniper_service import SniperService
from iuh_ledger.gui_api import BridgeAPI, flatten_class_with_schedules, extract_nhom_th_int

class TestIUHSniperE2E(unittest.TestCase):

    def test_01_crypto_equivalence(self):
        """Verifies bit-for-bit equivalence with browser CryptoJS."""
        priv_key = "7eb6a0215c8b2a81e3cb3653a73d3afd"
        pwd = "MySecretPassword123"
        expected = "o7cpYaHKR/Px37vfpxYiJTf7QqPMKSJjQdj+pv6YcG8="
        actual = encrypt_iuh_password(pwd, priv_key)
        self.assertEqual(actual, expected)

    def test_02_endpoints_contract(self):
        """Verifies all required endpoints on sv.iuh.edu.vn are present."""
        self.assertTrue(IUHEndpoints.LOGIN_PAGE.startswith("https://sv.iuh.edu.vn"))
        self.assertTrue(IUHEndpoints.MON_HOC_CHO_DK.endswith("/MonHocPhanChoDangKy"))
        self.assertTrue(IUHEndpoints.LOP_HOC_CHO_DK.endswith("/LopHocPhanChoDangKy"))
        self.assertTrue(IUHEndpoints.CHI_TIET_LICH.endswith("/GetChiTietLichHoc"))
        self.assertTrue(IUHEndpoints.HOC_PHAN_DA_DK.endswith("/HocPhanDaDangKy"))
        self.assertTrue(IUHEndpoints.DANG_KY_HP.endswith("/dang-ky-hoc-phan.html"))

    def test_03_parser_offline(self):
        """Tests parsing with synthetic HTML matching IUH table structures."""
        sample_subject_html = '''
        <table>
            <tr onclick="SelectMonHocChoDangKy(this);" data-id="3634" data-mamh="003634" data-mahpduochoc="4297003634" data-mhmaster="">
                <td></td><td>1</td><td>4297003634</td><td>Âm nhạc</td><td>3</td><td></td>
            </tr>
        </table>
        '''
        subjects = IUHHTMLParser.parse_subjects(sample_subject_html)
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0].ten_mon, "Âm nhạc")
        self.assertEqual(subjects[0].ma_mon, "003634")
        self.assertEqual(subjects[0].so_tc, 3)

        sample_class_html = '''
        <table>
            <tr onclick="SelectLopHocPhanChoDangKy(this)" data-guidlhp="TEST_GUID" data-mhmaster="">
                <td>1</td><td>Âm nhạc<br>Mã lớp học phần: 429700363401 - DHSH20A_TCTA</td><td>10 / 45</td>
            </tr>
        </table>
        '''
        classes = IUHHTMLParser.parse_classes(sample_class_html)
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].guid_lhp, "TEST_GUID")
        self.assertEqual(classes[0].si_so_dk, 10)
        self.assertEqual(classes[0].si_so_max, 45)

    def test_04_client_cookie_lifecycle(self):
        """Tests save, load, and cookie jar operations."""
        tmp_session = "tmp_test_session.json"
        try:
            client1 = IUHClient(session_path=tmp_session)
            client1.set_cookie("ASC.AUTH", "TEST_VALUE")
            client1.set_cookie("DT_DKHP_Reg", "UUID_TEST")
            client1.save_cookies()

            client2 = IUHClient(session_path=tmp_session)
            self.assertTrue(client2.load_cookies())
            cookies = client2.get_cookies_dict()
            self.assertEqual(cookies.get("ASC.AUTH"), "TEST_VALUE")
            self.assertEqual(cookies.get("DT_DKHP_Reg"), "UUID_TEST")
        finally:
            if os.path.exists(tmp_session):
                os.remove(tmp_session)

    def test_05_services_initialization(self):
        """Tests services instantiate and bind to client cleanly."""
        client = IUHClient()
        cat = CatalogService(client)
        reg = RegistrationService(client)
        radar = RadarService(client, id_dot="62")
        self.assertIsNotNone(cat)
        self.assertIsNotNone(reg)
        self.assertIsNotNone(radar)

    def test_06_flatten_enriched_schedules_by_nhom_th(self):
        """Verifies flattening class schedules into per-practice-group rows and pure theory rows."""
        cls_th = CourseClass(
            guid_lhp="GUID_TH",
            ma_lhp="429700363401",
            ten_lop="DHSH20A_TCTA",
            si_so_dk=18,
            si_so_max=45,
            trang_thai="Đang mở",
            da_khoa=False
        )
        schedules = [
            ClassSchedule("1", "LT", "LT - Thứ 3 (Tiết 7 -> 9)", "", "N4.6 CLC", "N", "Cơ sở 1", "TS Phan Trần Minh Khuê", "13/01/2026 - 07/04/2026"),
            ClassSchedule("2", "TH", "TH - Thứ 5 (Tiết 1 -> 3)", "1", "H7.01", "H", "Cơ sở 1", "DH Lìu Cẩm Bình", "13/01/2026 - 07/04/2026"),
            ClassSchedule("3", "TH", "TH - Thứ 6 (Tiết 4 -> 6)", "Nhóm 2", "H7.02", "H", "Cơ sở 1", "ThS Nguyễn Văn A", "13/01/2026 - 07/04/2026")
        ]
        rows = flatten_class_with_schedules(cls_th, schedules)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["nhom_th"], 1)
        self.assertEqual(rows[0]["row_key"], "GUID_TH_1")
        self.assertIn("TS Phan Trần Minh Khuê", rows[0]["giang_vien"])
        self.assertIn("DH Lìu Cẩm Bình", rows[0]["giang_vien"])
        self.assertIn("N4.6 CLC", rows[0]["lich_lt"])
        self.assertIn("H7.01", rows[0]["lich_th"])

        self.assertEqual(rows[1]["nhom_th"], 2)
        self.assertEqual(rows[1]["row_key"], "GUID_TH_2")
        self.assertIn("ThS Nguyễn Văn A", rows[1]["giang_vien"])

        # Pure LT class
        rows_lt = flatten_class_with_schedules(cls_th, [schedules[0]])
        self.assertEqual(len(rows_lt), 1)
        self.assertIsNone(rows_lt[0]["nhom_th"])
        self.assertEqual(rows_lt[0]["nhom_th_label"], "Thuần LT")

    def test_07_bridge_composite_dedup_and_sniper_loai_dk(self):
        """Verifies composite deduplication (guid_lhp, nhom_th) and loai_dk propagation in SniperService."""
        tmp_cfg = "tmp_test_config.json"
        try:
            bridge = BridgeAPI(config_path=tmp_cfg, session_path="tmp_nonexistent.json")
            bridge.config["target_classes"] = []

            # Add same GUID with Nhóm TH 1 and Nhóm TH 2 -> must store 2 distinct targets
            r1 = bridge.add_target("62", "003634", "4297003634", "Âm nhạc", "GUID_1", "DH20A", nhom_th=1, loai_dk=2)
            r2 = bridge.add_target("62", "003634", "4297003634", "Âm nhạc", "GUID_1", "DH20A", nhom_th=2, loai_dk=2)
            self.assertEqual(len(r2["targets"]), 2)
            self.assertEqual(r1["target_key"], "GUID_1_1")
            self.assertEqual(r2["target_key"], "GUID_1_2")

            # Add duplicate (GUID_1, nhom_th=1) -> must not duplicate
            r3 = bridge.add_target("62", "003634", "4297003634", "Âm nhạc", "GUID_1", "DH20A", nhom_th=1, loai_dk=2)
            self.assertEqual(len(r3["targets"]), 2)

            # Verify SniperService poll_once forwards loai_dk and nhom_th to register_class
            captured_calls = []
            class DummyCatalog:
                def get_classes_for_subject(self, id_dot, subj, khong_trung_lich=False, loai_dk=1):
                    return [CourseClass(guid_lhp="GUID_1", ma_lhp="4201", ten_lop="DH20A", si_so_dk=10, si_so_max=45)]
            class DummyReg:
                def register_class(self, id_dot, guid_lhp, loai_dk=1, nhom_th=None, ma_mon_cha=""):
                    captured_calls.append({"id_dot": id_dot, "guid_lhp": guid_lhp, "loai_dk": loai_dk, "nhom_th": nhom_th})
                    return {"success": True, "code": "00", "message": "OK"}

            sniper = SniperService(DummyCatalog(), DummyReg(), targets=bridge.config["target_classes"])
            sniper.poll_once()
            self.assertEqual(len(captured_calls), 2)
            self.assertEqual(captured_calls[0]["loai_dk"], 2)
            self.assertEqual(captured_calls[0]["nhom_th"], 1)
            self.assertEqual(captured_calls[1]["nhom_th"], 2)
        finally:
            if os.path.exists(tmp_cfg):
                os.remove(tmp_cfg)
    def test_08_registered_courses_ignores_hidden_print_table(self):
        """Verifies parse_registered_courses strips #id-hoc-phan-da-dk print table so columns never shift."""
        html_with_print_dup = '''
        <div class="table-responsive">
            <table id="dkHocPhan">
                <tbody>
                    <tr onclick="SelectHocPhanDaDangKy(this);">
                        <td><button data-idlhpdk="10393865" data-guid="GUID_CSDL">Hủy</button></td>
                        <td>1</td>
                        <td>429701766302</td>
                        <td>Dự án Thương mại điện tử</td>
                        <td>DHTMDT20B_TCTA</td>
                        <td>3</td>
                        <td>2</td>
                        <td><span>3.600.000</span></td>
                        <td>30/01/2026</td>
                        <td><div class="check"></div></td>
                        <td>Đăng ký mới</td>
                        <td>28/10/2025</td>
                        <td>Đã khóa</td>
                    </tr>
                </tbody>
            </table>
        </div>
        <div id="id-hoc-phan-da-dk" style="display:none;">
            <table id="dkHocPhan">
                <tbody>
                    <tr onclick="SelectHocPhanDaDangKy(this);">
                        <td>1</td>
                        <td>429701766302</td>
                        <td>Dự án Thương mại điện tử</td>
                        <td>DHTMDT20B_TCTA</td>
                        <td>3</td>
                        <td>2</td>
                        <td><span>3.600.000</span></td>
                        <td>30/01/2026</td>
                        <td><div class="check"></div></td>
                        <td>Đăng ký mới</td>
                        <td>28/10/2025</td>
                        <td>Đã khóa</td>
                    </tr>
                </tbody>
            </table>
        </div>
        '''
        courses = IUHHTMLParser.parse_registered_courses(html_with_print_dup)
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].ma_lhp, "429701766302")
        self.assertEqual(courses[0].ten_mon, "Dự án Thương mại điện tử")
        self.assertEqual(courses[0].so_tc, 3)
        self.assertEqual(courses[0].nhom_th, "2")
        self.assertEqual(courses[0].hoc_phi, "3.600.000")
        self.assertEqual(courses[0].trang_thai_lhp, "Đã khóa")

    def test_09_bridge_target_lifecycle_and_telemetry(self):
        """Verifies BridgeAPI target lifecycle (get, remove, clear) and rich telemetry event structure."""
        tmp_cfg = "tmp_test_p75.json"
        try:
            bridge = BridgeAPI(config_path=tmp_cfg, session_path="tmp_nonexistent.json")
            bridge.clear_targets()

            # 1. Add targets with distinct practice groups
            r1 = bridge.add_target("62", "003634", "4297003634", "Âm nhạc", "GUID_A", "DH20A", nhom_th=1, loai_dk=1)
            r2 = bridge.add_target("62", "003634", "4297003634", "Âm nhạc", "GUID_A", "DH20A", nhom_th=2, loai_dk=1)
            targets = bridge.get_targets()["targets"]
            self.assertEqual(len(targets), 2)
            self.assertEqual(targets[0]["target_key"], "GUID_A_1")
            self.assertEqual(targets[1]["target_key"], "GUID_A_2")

            # 2. Remove single target
            rem_res = bridge.remove_target("GUID_A_1")
            self.assertEqual(len(rem_res["targets"]), 1)
            self.assertEqual(rem_res["targets"][0]["target_key"], "GUID_A_2")

            # 3. Rich Telemetry in poll_sniper_once
            class DummyCatalog:
                def get_classes_for_subject(self, id_dot, subj, khong_trung_lich=False, loai_dk=1):
                    return [CourseClass(guid_lhp="GUID_A", ma_lhp="429700363402", ten_lop="DH20A", si_so_dk=44, si_so_max=45)]

            class DummyReg:
                def register_class(self, id_dot, guid_lhp, loai_dk=1, nhom_th=None, ma_mon_cha=""):
                    return {"success": True, "code": "00", "message": "Ghi danh thành công"}

            bridge.sniper = SniperService(DummyCatalog(), DummyReg(), targets=bridge.config["target_classes"])
            poll_res = bridge.poll_sniper_once()
            self.assertTrue(poll_res["success"])
            self.assertEqual(len(poll_res["events"]), 2)
            ev_checked = poll_res["events"][0]
            self.assertEqual(ev_checked["type"], "checked")
            self.assertEqual(ev_checked["target_key"], "GUID_A_2")
            self.assertEqual(ev_checked["si_so_dk"], 44)
            self.assertEqual(ev_checked["si_so_max"], 45)

            ev_success = poll_res["events"][1]
            self.assertEqual(ev_success["type"], "success")
            self.assertEqual(ev_success["target_key"], "GUID_A_2")
            self.assertEqual(ev_success["ten_mon"], "Âm nhạc")
            self.assertTrue(ev_success["slot_available"])
            self.assertTrue(ev_success["registered"])
            self.assertIn("Ghi danh thành công", ev_success["message"])

            # 4. Clear all targets
            clr_res = bridge.clear_targets()
            self.assertEqual(len(clr_res["targets"]), 0)
            self.assertEqual(len(bridge.get_targets()["targets"]), 0)
        finally:
            if os.path.exists(tmp_cfg):
                os.remove(tmp_cfg)


    def test_10_settings_and_schedule_contract(self):
        """Verifies settings get/save operations and weekly schedule parsing/generation."""
        tmp_cfg = "tmp_test_cfg_10.json"
        try:
            with open(tmp_cfg, "w", encoding="utf-8") as f:
                json.dump({"username": "24687201", "heartbeat_interval_seconds": 62}, f)
            bridge = BridgeAPI(config_path=tmp_cfg, session_path="tmp_nonexistent.json")

            # 1. Get settings
            s_res = bridge.get_settings()
            self.assertTrue(s_res["success"])
            self.assertEqual(s_res["settings"]["heartbeat_interval_seconds"], 62)
            self.assertEqual(s_res["settings"]["sniper_poll_interval_ms"], 1500)
            self.assertTrue(s_res["settings"]["audio_chime_enabled"])

            # 2. Save settings
            up_res = bridge.save_settings({
                "heartbeat_interval_seconds": 45,
                "sniper_poll_interval_ms": 1000,
                "telegram_chat_id": "12345678"
            })
            self.assertTrue(up_res["success"])
            self.assertEqual(up_res["settings"]["heartbeat_interval_seconds"], 45)
            self.assertEqual(bridge.radar.interval_seconds, 45)
            self.assertEqual(up_res["settings"]["telegram_chat_id"], "12345678")

            # 3. Weekly schedule contract
            sched_res = bridge.get_weekly_schedule(id_dot="62")
            self.assertTrue(sched_res["success"])
            self.assertGreaterEqual(len(sched_res["slots"]), 7)
            first_slot = sched_res["slots"][0]
            self.assertIn("day", first_slot)
            self.assertIn("ca", first_slot)
            self.assertIn("ten_mon", first_slot)
            self.assertIn("loai", first_slot)
            self.assertFalse(first_slot["is_preview"])

            # 4. Registered + Preview schedule integration & Conflict Detection
            from iuh_ledger.core.models import RegisteredCourse
            preview_class = {
                "id_dot": "62",
                "guid_lhp": "PREVIEW_GUID",
                "ten_mon": "Lập trình Web",
                "ma_hp": "429709999",
                "ten_lop": "DHKTPM18A",
                "nhom_th": 1
            }
            class MockCatalog:
                def get_registered_courses(self, id_dot="62"):
                    return [
                        RegisteredCourse(
                            stt="1", ma_lhp="429701111", ten_mon="Cơ sở dữ liệu",
                            lop_du_kien="DHKTPM18A", so_tc=3, nhom_th="1", hoc_phi="3.600.000",
                            han_nop="", trang_thai_dk="Đăng ký mới", trang_thai_lhp="Đã khóa",
                            id_lhp_dk="1001", guid="GUID_DK_1", guid_lhp="REG_GUID_1"
                        )
                    ]
                def get_class_schedule(self, guid, timeout=10):
                    if guid == "REG_GUID_1":
                        return [
                            ClassSchedule(stt="1", loai_tiet="LT", thu_tiet="Thứ 5 (Tiết 1 -> 3)", nhom_th="", phong="A1.02", day_nha="A", co_so="1", giang_vien="TS Nguyễn", thoi_gian="01/01/2026 - 01/05/2026"),
                            ClassSchedule(stt="2", loai_tiet="TH", thu_tiet="Thứ 6 (Tiết 1 -> 3)", nhom_th="2", phong="H7.01", day_nha="H", co_so="1", giang_vien="TS Nguyễn", thoi_gian="01/01/2026 - 01/05/2026")
                        ]
                    return [
                        ClassSchedule(stt="1", loai_tiet="LT", thu_tiet="Thứ 5 (Tiết 2 -> 4)", nhom_th="", phong="B2.04", day_nha="B", co_so="1", giang_vien="TS Trần", thoi_gian="01/01/2026 - 01/05/2026")
                    ]
            bridge.catalog = MockCatalog()
            p_res = bridge.get_weekly_schedule(id_dot="62", preview_classes=[preview_class])
            self.assertEqual(p_res["registered_count"], 1)
            # Group 2 TH row of REG_GUID_1 must be filtered out because student registered in nhom_th=1
            reg_slots = [s for s in p_res["slots"] if not s.get("is_preview")]
            self.assertEqual(len(reg_slots), 1)
            preview_slots = [s for s in p_res["slots"] if s.get("is_preview")]
            self.assertEqual(len(preview_slots), 1)
            self.assertEqual(preview_slots[0]["day"], "5")
            self.assertEqual(preview_slots[0]["ca"], "sang")
            self.assertEqual(preview_slots[0]["ten_mon"], "Lập trình Web")
            # Period 1-3 and Period 2-4 on Thursday overlap -> conflict detected!
            self.assertTrue(preview_slots[0]["has_conflict"])
            self.assertIn("Cơ sở dữ liệu", preview_slots[0]["conflict_with"])
            self.assertEqual(p_res["conflict_count"], 2)

            # 5. Zero-network embedded schedules & lich_lt/lich_th string synthesis fallback
            class EmptyNetworkCatalog:
                def get_registered_courses(self, id_dot="62"):
                    return []
                def get_class_schedule(self, guid, timeout=10):
                    return []
            bridge.catalog = EmptyNetworkCatalog()
            demo_preview = {
                "id_dot": "62",
                "guid_lhp": "CqLpKkViKTvbXLsCooUfPg",
                "ten_mon": "Âm nhạc, Nhạc lý và Guitar căn bản",
                "ma_hp": "429700363401",
                "ten_lop": "DHSH20A_TCTA",
                "nhom_th": 1,
                "lich_lt": "Thứ 3 (Tiết 7 - 9), Phòng N4.6 CLC",
                "lich_th": "Thứ 5 (Tiết 1 - 3), Phòng H7.01",
                "giang_vien": "TS Phan Trần Minh Khuê"
            }
            demo_res = bridge.get_weekly_schedule(id_dot="62", preview_classes=[demo_preview])
            demo_prev_slots = [s for s in demo_res["slots"] if s.get("is_preview")]
            self.assertEqual(len(demo_prev_slots), 2)
            # LT on Tuesday afternoon (7-9) overlaps with default Cơ sở dữ liệu (Tuesday 7-9)
            tue_slot = next(s for s in demo_prev_slots if s["day"] == "3")
            thu_slot = next(s for s in demo_prev_slots if s["day"] == "5")
            self.assertTrue(tue_slot["has_conflict"])
            self.assertFalse(thu_slot["has_conflict"])
        finally:
            if os.path.exists(tmp_cfg):
                os.remove(tmp_cfg)

if __name__ == "__main__":
    unittest.main()
