"""
IUH Data Models
Structured representation of subjects, classes, schedules, and student profile.
"""

from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Semester:
    id_dot: str
    ten_dot: str
    is_selected: bool = False

@dataclass
class Subject:
    id_mon: str
    ma_mon: str
    ma_hp: str
    ten_mon: str
    so_tc: int = 0
    ma_mon_cha: str = ""

@dataclass
class CourseClass:
    guid_lhp: str
    ma_lhp: str
    ten_lop: str
    si_so_dk: int = 0
    si_so_max: int = 0
    trang_thai: str = "Đang mở"
    da_khoa: bool = False
    lop_du_kien: str = ""
    nhom_th: Optional[int] = None

@dataclass
class ClassSchedule:
    stt: str
    loai_tiet: str  # LT or TH
    thu_tiet: str   # e.g. Thứ 3 (Tiết 7 -> 9)
    nhom_th: str    # e.g. 1 or 2
    phong: str      # e.g. N4.6 CLC
    day_nha: str    # e.g. N (CS Nguyễn Văn Dung)
    co_so: str      # e.g. Cơ sở 1
    giang_vien: str # e.g. TS Phan Trần Minh Khuê
    thoi_gian: str  # e.g. 13/01/2026 - 07/04/2026

@dataclass
class RegisteredCourse:
    stt: str
    ma_lhp: str
    ten_mon: str
    lop_du_kien: str
    so_tc: int
    nhom_th: str
    hoc_phi: str
    han_nop: str
    trang_thai_dk: str
    trang_thai_lhp: str
    id_lhp_dk: str
    guid: str

@dataclass
class StudentProfile:
    mssv: str
    ho_ten: str
    lop: str
    khoa_hoc: str = ""
    nganh: str = ""
    bac_dao_tao: str = ""
