"""
IUH Catalog and Schedule Query Service
Retrieves open subjects, classes, detailed schedules, and registered courses.
"""

from typing import List, Optional
from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.client import IUHClient
from iuh_ledger.core.models import Semester, Subject, CourseClass, ClassSchedule, RegisteredCourse, StudentProfile
from iuh_ledger.core.parser import IUHHTMLParser

class CatalogService:
    def __init__(self, client: IUHClient):
        self.client = client

    def get_student_profile(self, id_dot: str = "62") -> Optional[StudentProfile]:
        """
        Retrieves student profile (name, student ID, class) from HocPhanDaDangKy.
        """
        res = self.client.post(
            IUHEndpoints.HOC_PHAN_DA_DK,
            data={
                "param[IDDotDangKy]": id_dot,
                "param[IDLoaiDangKy]": "1"
            }
        )
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_student_profile(html)

    def get_semesters(self) -> List[Semester]:
        """
        Retrieves available registration semesters (HK1, HK2, HK3) from /dang-ky-hoc-phan.html.
        """
        res = self.client.get(IUHEndpoints.DANG_KY_HP)
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_semesters(html)

    def get_open_subjects(self, id_dot: str = "62", loai_dk: int = 1) -> List[Subject]:
        """
        Retrieves the list of available subjects waiting for registration.
        """
        res = self.client.post(
            IUHEndpoints.MON_HOC_CHO_DK,
            data={
                "param[IDDotDangKy]": id_dot,
                "param[IDLoaiDangKy]": str(loai_dk)
            }
        )
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_subjects(html)

    def get_classes_for_subject(self, id_dot: str, subject: Subject, 
                                khong_trung_lich: bool = False, loai_dk: int = 1) -> List[CourseClass]:
        """
        Retrieves open class groups for a specific subject.
        """
        res = self.client.post(
            IUHEndpoints.LOP_HOC_CHO_DK,
            data={
                "param[IDDotDangKy]": id_dot,
                "param[MaMonHoc]": subject.ma_mon,
                "param[DSHocPhanDuocHoc]": subject.ma_hp,
                "param[IsLHPKhongTrungLich]": "true" if khong_trung_lich else "false",
                "param[LoaiDKHP]": str(loai_dk),
                "param[MaMonCha]": subject.ma_mon_cha
            }
        )
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_classes(html)

    def get_class_schedule(self, guid_lhp: str, timeout: int = 10) -> List[ClassSchedule]:
        """
        Retrieves detailed schedule (days, periods, room, lecturer) for a class group.
        """
        res = self.client.post(
            IUHEndpoints.CHI_TIET_LICH,
            data={
                "param[GuidIDLopHocPhan]": guid_lhp
            },
            timeout=timeout
        )
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_schedules(html)

    def get_registered_courses(self, id_dot: str = "62", loai_dk: int = 1) -> List[RegisteredCourse]:
        """
        Retrieves all currently registered courses for the given registration period.
        """
        res = self.client.post(
            IUHEndpoints.HOC_PHAN_DA_DK,
            data={
                "param[IDDotDangKy]": id_dot,
                "param[IDLoaiDangKy]": str(loai_dk)
            }
        )
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_registered_courses(html)

    def get_weekly_timetable(self, ngay_hien_tai: str = "", loai_lich: int = 0) -> dict:
        """
        Retrieves the student's weekly timetable matrix from POST /SinhVien/GetDanhSachLichTheoTuan.
        """
        post_data = {"pLoaiLich": str(loai_lich)}
        if ngay_hien_tai:
            post_data["pNgayHienTai"] = str(ngay_hien_tai)
        res = self.client.post(
            IUHEndpoints.LICH_THEO_TUAN,
            data=post_data,
            timeout=10
        )
        html = res.read().decode("utf-8", errors="replace")
        return IUHHTMLParser.parse_weekly_timetable(html)
