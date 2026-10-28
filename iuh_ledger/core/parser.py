"""
IUH HTML Response Parser
Transforms raw server HTML responses into strongly-typed domain models.
"""

import re
import html as html_lib
from typing import List, Optional
from iuh_ledger.core.models import Semester, Subject, CourseClass, ClassSchedule, RegisteredCourse, StudentProfile

def _clean_text(text: str) -> str:
    if not text:
        return ""
    # Strip HTML tags
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities like &#194; &gt; &amp;
    decoded = html_lib.unescape(cleaned)
    # Collapse multiple whitespaces
    return re.sub(r'\s+', ' ', decoded).strip()

class IUHHTMLParser:

    @staticmethod
    def parse_student_profile(html: str) -> Optional[StudentProfile]:
        """
        Parses student basic profile from HocPhanDaDangKy or Dashboard HTML.
        """
        if not html:
            return None
            
        name_m = re.search(r'Họ\s*tên</span>:\s*([^<]+)', html, re.I)
        masv_m = re.search(r'Mã\s*sinh\s*viên</span>:\s*([^<]+)', html, re.I)
        lop_m = re.search(r'Lớp\s*học</span>:\s*([^<]+)', html, re.I)

        # Fallback to dashboard patterns
        if not name_m:
            name_m = re.search(r'Họ\s*tên:\s*<strong>([^<]+)</strong>', html, re.I)
        if not masv_m:
            masv_m = re.search(r'MSSV:\s*([0-9]+)', html, re.I)
        if not lop_m:
            lop_m = re.search(r'Lớp\s*học:\s*([A-Za-z0-9_]+)', html, re.I)

        if not (name_m or masv_m):
            return None

        return StudentProfile(
            ho_ten=_clean_text(name_m.group(1)) if name_m else "",
            mssv=_clean_text(masv_m.group(1)) if masv_m else "",
            lop=_clean_text(lop_m.group(1)) if lop_m else ""
        )

    @staticmethod
    def parse_semesters(html: str) -> List[Semester]:
        """
        Parses #cboIDDotDangKy options from /dang-ky-hoc-phan.html.
        """
        semesters = []
        if not html:
            return semesters

        select_m = re.search(r'<select[^>]*id=["\']cboIDDotDangKy["\'][^>]*>(.*?)</select>', html, re.DOTALL | re.I)
        target_html = select_m.group(1) if select_m else html

        for m in re.finditer(r'<option([^>]*)>(.*?)</option>', target_html, re.DOTALL | re.I):
            attrs = m.group(1)
            label = _clean_text(m.group(2))
            val_m = re.search(r'value=["\']([^"\']*)["\']', attrs, re.I)
            val = val_m.group(1).strip() if val_m else ""
            if val and val.isdigit():
                is_sel = "selected" in attrs.lower()
                semesters.append(Semester(id_dot=val, ten_dot=label, is_selected=is_sel))

        return semesters

    @staticmethod
    def parse_subjects(html: str) -> List[Subject]:
        """
        Parses open subject list from /SinhVienDangKy/MonHocPhanChoDangKy.
        """
        subjects = []
        if not html:
            return subjects

        # Match table rows with SelectMonHocChoDangKy
        row_pattern = re.compile(r'<tr[^>]*onclick=["\']SelectMonHocChoDangKy\(this\);?["\'][^>]*>(.*?)</tr>', re.DOTALL | re.I)
        for m in row_pattern.finditer(html):
            row_tag = html[m.start():html.find('>', m.start()) + 1]
            row_body = m.group(1)

            id_mon = re.search(r'data-id=["\']([^"\']*)["\']', row_tag)
            ma_mon = re.search(r'data-mamh=["\']([^"\']*)["\']', row_tag)
            ma_hp = re.search(r'data-mahpduochoc=["\']([^"\']*)["\']', row_tag)
            ma_cha = re.search(r'data-mhmaster=["\']([^"\']*)["\']', row_tag)

            cells = [c.group(1) for c in re.finditer(r'<td[^>]*>(.*?)</td>', row_body, re.DOTALL)]
            # Col 1: STT, Col 2: Ma HP, Col 3: Ten MH, Col 4: So TC
            ten_mon = _clean_text(cells[3]) if len(cells) > 3 else ""
            so_tc_str = _clean_text(cells[4]) if len(cells) > 4 else "0"
            so_tc = int(so_tc_str) if so_tc_str.isdigit() else 0

            subjects.append(Subject(
                id_mon=id_mon.group(1) if id_mon else "",
                ma_mon=ma_mon.group(1) if ma_mon else "",
                ma_hp=ma_hp.group(1) if ma_hp else "",
                ten_mon=ten_mon,
                so_tc=so_tc,
                ma_mon_cha=ma_cha.group(1) if ma_cha else ""
            ))

        return subjects

    @staticmethod
    def parse_classes(html: str) -> List[CourseClass]:
        """
        Parses course class list from /SinhVienDangKy/LopHocPhanChoDangKy.
        """
        classes = []
        if not html:
            return classes

        row_pattern = re.compile(r'<tr[^>]*onclick=["\']SelectLopHocPhanChoDangKy\(this\);?["\'][^>]*>(.*?)</tr>', re.DOTALL | re.I)
        for m in row_pattern.finditer(html):
            row_tag = html[m.start():html.find('>', m.start()) + 1]
            row_body = m.group(1)

            guid_m = re.search(r'data-guidlhp=["\']([^"\']*)["\']', row_tag)
            guid = guid_m.group(1) if guid_m else ""

            cells = [_clean_text(c.group(1)) for c in re.finditer(r'<td[^>]*>(.*?)</td>', row_body, re.DOTALL)]
            
            # Col 0: STT, Col 1: Ten MH + Trang thai + Ma LHP - LopDuKien, Col 2: Si so (e.g. 0 / 45)
            col1_raw = cells[1] if len(cells) > 1 else ""
            siso_str = cells[2] if len(cells) > 2 else ""

            # Extract Ma LHP (12 digits)
            ma_lhp_m = re.search(r'Mã\s*lớp\s*học\s*phần:\s*([0-9]+)', col1_raw, re.I)
            ma_lhp = ma_lhp_m.group(1) if ma_lhp_m else ""

            # Extract Lop du kien after " - "
            lop_dk_m = re.search(r'-\s*([A-Za-z0-9_]+)', col1_raw)
            lop_du_kien = lop_dk_m.group(1) if lop_dk_m else ""

            # Extract Trang thai
            tt_m = re.search(r'Trạng\s*thái:\s*([^<\n\r]+)', col1_raw, re.I)
            trang_thai = tt_m.group(1).strip() if tt_m else "Đang mở"
            da_khoa = "khóa" in trang_thai.lower()

            # Sĩ số: "0 / 45"
            si_so_dk = 0
            si_so_max = 60
            if "/" in siso_str:
                parts = siso_str.split("/")
                si_so_dk = int(parts[0].strip()) if parts[0].strip().isdigit() else 0
                si_so_max = int(parts[1].strip()) if parts[1].strip().isdigit() else 60
            elif siso_str.isdigit():
                si_so_dk = int(siso_str)

            classes.append(CourseClass(
                guid_lhp=guid,
                ma_lhp=ma_lhp,
                ten_lop=lop_du_kien or ma_lhp,
                si_so_dk=si_so_dk,
                si_so_max=si_so_max,
                trang_thai=trang_thai,
                da_khoa=da_khoa,
                lop_du_kien=lop_du_kien
            ))

        return classes

    @staticmethod
    def parse_schedules(html: str) -> List[ClassSchedule]:
        """
        Parses detailed schedule table from /SinhVienDangKy/GetChiTietLichHoc.
        """
        schedules = []
        if not html:
            return schedules

        row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
        for m in row_pattern.finditer(html):
            row_body = m.group(1)
            cells = [_clean_text(c.group(1)) for c in re.finditer(r'<td[^>]*>(.*?)</td>', row_body, re.DOTALL)]
            
            # Row format: [STT, Thứ & Tiết, Nhóm TH, Phòng, Dãy nhà, Cơ sở, Giảng viên, Thời gian]
            if len(cells) >= 7 and cells[0].isdigit():
                thu_tiet = cells[1]
                loai_tiet = "TH" if "TH" in thu_tiet else "LT"
                schedules.append(ClassSchedule(
                    stt=cells[0],
                    loai_tiet=loai_tiet,
                    thu_tiet=thu_tiet,
                    nhom_th=cells[2] if len(cells) > 2 else "",
                    phong=cells[3] if len(cells) > 3 else "",
                    day_nha=cells[4] if len(cells) > 4 else "",
                    co_so=cells[5] if len(cells) > 5 else "",
                    giang_vien=cells[6] if len(cells) > 6 else "",
                    thoi_gian=cells[7] if len(cells) > 7 else ""
                ))

        return schedules

    @staticmethod
    def parse_registered_courses(html: str) -> List[RegisteredCourse]:
        """
        Parses currently registered courses from /SinhVienDangKy/HocPhanDaDangKy.
        """
        courses = []
        if not html:
            return courses

        # Strip hidden print template (#id-hoc-phan-da-dk) which duplicates rows without the 'Thao tác' column
        print_idx = html.find('id="id-hoc-phan-da-dk"')
        if print_idx == -1:
            print_idx = html.find("id='id-hoc-phan-da-dk'")
        active_html = html[:print_idx] if print_idx != -1 else html

        row_pattern = re.compile(r'<tr[^>]*onclick=["\']SelectHocPhanDaDangKy\(this\);?["\'][^>]*>(.*?)</tr>', re.DOTALL | re.I)
        for m in row_pattern.finditer(active_html):
            row_body = m.group(1)
            guid_m = re.search(r'data-guid=["\']([^"\']*)["\']', row_body)
            id_lhp_m = re.search(r'data-idlhpdk=["\']([^"\']*)["\']', row_body)
            guid_lhp_m = re.search(r'XemChiTietLichHoc\s*\(\s*this\s*,\s*["\']([^"\']+)["\']', row_body)

            cells = [_clean_text(c.group(1)) for c in re.finditer(r'<td[^>]*>(.*?)</td>', row_body, re.DOTALL)]
            # Main table has 13 cells:
            # [0:Thao tác, 1:STT, 2:Mã LHP, 3:Tên môn, 4:Lớp dự kiến, 5:TC, 6:Nhóm TH, 7:Học phí, 8:Hạn nộp, 9:Thu, 10:Trạng thái ĐK, 11:Ngày ĐK, 12:TT lớp HP]
            # Guard: cells[1] must be STT (digits) and cells[2] must be Mã LHP (digits)
            if len(cells) >= 13 and cells[1].isdigit() and cells[2].isdigit():
                courses.append(RegisteredCourse(
                    stt=cells[1],
                    ma_lhp=cells[2],
                    ten_mon=cells[3],
                    lop_du_kien=cells[4],
                    so_tc=int(cells[5]) if cells[5].isdigit() else 0,
                    nhom_th=cells[6],
                    hoc_phi=cells[7],
                    han_nop=cells[8],
                    trang_thai_dk=cells[10],
                    trang_thai_lhp=cells[12],
                    id_lhp_dk=id_lhp_m.group(1) if id_lhp_m else "",
                    guid=guid_m.group(1) if guid_m else "",
                    guid_lhp=guid_lhp_m.group(1) if guid_lhp_m else (guid_m.group(1) if guid_m else "")
                ))
        return courses

    @staticmethod
    def parse_weekly_timetable(html_str: str) -> dict:
        """
        Parses the weekly timetable matrix HTML from POST /SinhVien/GetDanhSachLichTheoTuan.
        Extracts navigation dates (firstDatePrevOffWeek, firstDateOffWeek, firstDateNextOffWeek),
        column dates for Thứ 2..Chủ nhật, and all rendered schedule slot cards.
        """
        result = {
            "prev_week": "",
            "current_week": "",
            "next_week": "",
            "day_dates": {},
            "slots": []
        }
        if not html_str:
            return result

        prev_m = re.search(r'id=["\']firstDatePrevOffWeek["\'][^>]*value=["\']([^"\']+)["\']', html_str, re.I)
        curr_m = re.search(r'id=["\']firstDateOffWeek["\'][^>]*value=["\']([^"\']+)["\']', html_str, re.I)
        next_m = re.search(r'id=["\']firstDateNextOffWeek["\'][^>]*value=["\']([^"\']+)["\']', html_str, re.I)
        if prev_m:
            result["prev_week"] = prev_m.group(1).strip()
        if curr_m:
            result["current_week"] = curr_m.group(1).strip()
        if next_m:
            result["next_week"] = next_m.group(1).strip()

        day_codes = ["2", "3", "4", "5", "6", "7", "CN"]
        thead_m = re.search(r'<thead[^>]*>(.*?)</thead>', html_str, re.DOTALL | re.I)
        if thead_m:
            ths = re.findall(r'<th[^>]*>(.*?)</th>', thead_m.group(1), re.DOTALL | re.I)
            for idx, code in enumerate(day_codes):
                if idx + 1 < len(ths):
                    dm = re.search(r'(\d{2}/\d{2}/\d{4})', ths[idx + 1])
                    if dm:
                        result["day_dates"][code] = dm.group(1)

        tbody_m = re.search(r'<tbody[^>]*>(.*?)</tbody>', html_str, re.DOTALL | re.I)
        if not tbody_m:
            return result

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_m.group(1), re.DOTALL | re.I)
        shift_map = {0: "sang", 1: "chieu", 2: "toi"}
        for r_idx, row_html in enumerate(rows):
            ca = shift_map.get(r_idx)
            if not ca:
                continue
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.I)
            for d_idx, day_code in enumerate(day_codes):
                if d_idx + 1 >= len(tds):
                    break
                cell_html = tds[d_idx + 1]
                for card_m in re.finditer(r'<div[^>]*class=["\']([^"\']*content[^"\']*)["\'][^>]*>(.*?)</div>', cell_html, re.DOTALL | re.I):
                    card_tag = cell_html[card_m.start():cell_html.find('>', card_m.start()) + 1]
                    card_cls = card_m.group(1).lower()
                    card_body = card_m.group(2)

                    style_m = re.search(r'style=["\']([^"\']*)["\']', card_tag, re.I)
                    style_str = (style_m.group(1) if style_m else "").lower()
                    if "lichthi" in card_cls or "color-lichhoc" not in card_cls:
                        loai = "lich_thi"
                    elif "tamngung" in card_cls:
                        loai = "tam_ngung"
                    elif "#71cb35" in style_str:
                        loai = "thuc_hanh"
                    elif "#92d6ff" in style_str:
                        loai = "truc_tuyen"
                    else:
                        loai = "ly_thuyet"
                    title_m = re.search(r'<b>\s*<a[^>]*>(.*?)</a>\s*</b>', card_body, re.DOTALL | re.I)
                    ten_mon = _clean_text(title_m.group(1)) if title_m else "Học phần"

                    p_tags = [_clean_text(p.group(1)) for p in re.finditer(r'<p[^>]*>(.*?)</p>', card_body, re.DOTALL | re.I)]
                    ten_lop = p_tags[0] if p_tags else ""
                    ma_lhp_m = re.search(r'(\d{10,14})', ten_lop)
                    ma_lhp = ma_lhp_m.group(1) if ma_lhp_m else ""

                    tiet_str = ""
                    tiet_start, tiet_end = 0, 0
                    phong_str = ""
                    gv_str = ""
                    ghi_chu_parts = []

                    for pt in p_tags[1:]:
                        if pt.lower().startswith("tiết"):
                            tm = re.search(r'(\d+)\s*(?:->|-)\s*(\d+)', pt)
                            if tm:
                                tiet_start, tiet_end = int(tm.group(1)), int(tm.group(2))
                                tiet_str = f"{tiet_start} - {tiet_end}"
                        elif pt.lower().startswith("phòng"):
                            phong_str = re.sub(r'^phòng\s*:\s*', '', pt, flags=re.I).strip()
                        elif pt.lower().startswith("gv"):
                            gv_str = re.sub(r'^gv\s*:\s*', '', pt, flags=re.I).strip()
                        elif pt:
                            ghi_chu_parts.append(pt)

                    result["slots"].append({
                        "day": day_code,
                        "ca": ca,
                        "ten_mon": ten_mon,
                        "ma_lhp": ma_lhp,
                        "ten_lop": ten_lop,
                        "tiet": tiet_str,
                        "tiet_start": tiet_start,
                        "tiet_end": tiet_end,
                        "phong": phong_str,
                        "giang_vien": gv_str,
                        "thoi_gian": result["day_dates"].get(day_code, ""),
                        "ghi_chu": ", ".join(ghi_chu_parts),
                        "loai": loai,
                        "is_preview": False
                    })
        return result
