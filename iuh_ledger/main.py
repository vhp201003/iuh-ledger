"""
IUH Sniper Pro - Main CLI Interface
High-performance interactive terminal dashboard for IUH course registration.
"""

import os
import sys
import json
import time
import argparse
import subprocess

# Ensure workspace root is in sys.path when executed directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from iuh_ledger.core.endpoints import IUHEndpoints
from iuh_ledger.core.client import IUHClient
from iuh_ledger.core.auth import IUHAuthenticator
from iuh_ledger.core.models import Subject, CourseClass, ClassSchedule
from iuh_ledger.services.catalog_service import CatalogService
from iuh_ledger.services.registration_service import RegistrationService
from iuh_ledger.services.radar_service import RadarService
from iuh_ledger.services.sniper_service import SniperService

console = Console()

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    candidates = [config_path, os.path.join("iuh_ledger", config_path)]
    for c in candidates:
        if os.path.exists(c):
            with open(c, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "username": "",
        "password": "",
        "id_dot_dang_ky": "62",
        "target_classes": []
    }

def save_config(config: Dict[str, Any], config_path: str = "config.json"):
    candidates = [config_path, os.path.join("iuh_ledger", config_path)]
    target = candidates[0]
    for c in candidates:
        if os.path.exists(c):
            target = c
            break
    with open(target, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def captcha_prompt(captcha_bytes: bytes) -> str:
    img_path = "captcha.jpg"
    with open(img_path, "wb") as f:
        f.write(captcha_bytes)

    # Try auto-opening image
    try:
        if sys.platform == "win32":
            os.startfile(os.path.abspath(img_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", img_path])
        else:
            subprocess.Popen(["xdg-open", img_path])
    except Exception:
        pass

    console.print(f"[bold yellow]⚠️ Đã tải ảnh Captcha về:[/] [cyan]{os.path.abspath(img_path)}[/]")
    console.print("[dim](Ảnh vừa tự động mở trên màn hình của bạn)[/]")
    code = Prompt.ask("[bold green]👉 Nhập 4 ký tự Captcha[/]")
    return code.strip()

def run_auth_flow(client: IUHClient, config: Dict[str, Any]) -> bool:
    username = config.get("username", "")
    password = config.get("password", "")
    id_dot = config.get("id_dot_dang_ky", "62")

    auth = IUHAuthenticator(client, username=username, password=password)

    console.print("[dim]🔍 Đang kiểm tra phiên làm việc cũ...[/]")
    if auth.login_with_existing_session(id_dot=id_dot):
        console.print("[bold green]✅ Session hợp lệ từ session.json! Bỏ qua đăng nhập.[/]")
        return True

    console.print("[yellow]⚠️ Chưa có session hoặc phiên đã hết hạn. Bắt đầu đăng nhập trực tiếp...[/]")
    if not username:
        username = Prompt.ask("[cyan]Nhập Mã sinh viên[/]")
        config["username"] = username
    if not password:
        password = Prompt.ask("[cyan]Nhập Mật khẩu[/]", password=True)
        config["password"] = password

    auth.username = username
    auth.password = password

    with console.status("[bold blue]Đang kết nối tới cổng IUH và lấy khóa bảo mật...[/]"):
        pass

    success = auth.login_native(captcha_prompt)
    if success:
        console.print("[bold green]🎉 Đăng nhập thành công! Bộ Cookie phiên đã được lưu.[/]")
        save_config(config)
        return True
    else:
        console.print("[bold red]❌ Đăng nhập thất bại! Vui lòng kiểm tra tài khoản, mật khẩu hoặc mã Captcha.[/]")
        return False

def show_banner(catalog: CatalogService, id_dot: str):
    profile = catalog.get_student_profile(id_dot=id_dot)
    profile_text = f"👤 Sinh viên: [bold cyan]{profile.ho_ten}[/] | MSSV: [bold yellow]{profile.mssv}[/] | Lớp: [green]{profile.lop}[/]" if profile else "👤 Trạng thái: [green]Đã xác thực[/]"
    
    panel = Panel(
        f"[bold blue]🎯 IUH SNIPER PRO - CỔNG THÔNG TIN SINH VIÊN (sv.iuh.edu.vn)[/]\n"
        f"{profile_text}\n"
        f"📅 Đợt đăng ký: [bold magenta]ID {id_dot}[/] | 🛰️ Radar Keepalive: [green]Sẵn sàng[/]",
        border_style="bright_blue"
    )
    console.print(panel)

def handle_view_open_subjects(catalog: CatalogService, id_dot: str, config: Dict[str, Any]):
    with console.status("[cyan]Đang tải danh sách môn học...[/]"):
        subjects = catalog.get_open_subjects(id_dot=id_dot)

    if not subjects:
        console.print("[yellow]Không tìm thấy môn học nào đang mở cho đợt này.[/]")
        return

    table = Table(title=f"Danh Sách Môn Học Đang Mở (Đợt ID: {id_dot})")
    table.add_column("STT", justify="center", style="cyan", width=5)
    table.add_column("Mã Môn", style="magenta")
    table.add_column("Mã Học Phần", style="dim")
    table.add_column("Tên Môn Học", style="bold green")
    table.add_column("Số TC", justify="center", style="yellow", width=6)

    for i, s in enumerate(subjects, 1):
        table.add_row(str(i), s.ma_mon, s.ma_hp, s.ten_mon, str(s.so_tc))

    console.print(table)

    choice = Prompt.ask("\n[bold cyan]👉 Chọn STT môn học để xem các lớp mở (hoặc gõ 0 để quay lại)[/]", default="0")
    if not choice.isdigit() or int(choice) <= 0 or int(choice) > len(subjects):
        return

    selected_subj = subjects[int(choice) - 1]
    with console.status(f"[cyan]Đang tải lớp cho môn '{selected_subj.ten_mon}'...[/]"):
        classes = catalog.get_classes_for_subject(id_dot=id_dot, subject=selected_subj)

    if not classes:
        console.print("[yellow]Chưa có lớp nào được mở cho môn này.[/]")
        return

    cls_table = Table(title=f"Danh Sách Lớp Học Phần: {selected_subj.ten_mon}")
    cls_table.add_column("STT", justify="center", style="cyan", width=5)
    cls_table.add_column("Tên Lớp / Dự Kiến", style="bold magenta")
    cls_table.add_column("Mã LHP", style="dim")
    cls_table.add_column("Sĩ Số", justify="center", style="yellow")
    cls_table.add_column("Trạng Thái", justify="center")

    for idx, c in enumerate(classes, 1):
        tt_style = "red" if c.da_khoa or c.si_so_dk >= c.si_so_max else "green"
        cls_table.add_row(
            str(idx), c.ten_lop, c.ma_lhp, 
            f"{c.si_so_dk}/{c.si_so_max}", 
            f"[{tt_style}]{c.trang_thai}[/]"
        )

    console.print(cls_table)

    sub_choice = Prompt.ask("\n[bold cyan]👉 Chọn STT lớp để xem Lịch Chi Tiết / Thêm vào mục tiêu săn (hoặc 0 để quay lại)[/]", default="0")
    if not sub_choice.isdigit() or int(sub_choice) <= 0 or int(sub_choice) > len(classes):
        return

    chosen_class = classes[int(sub_choice) - 1]
    with console.status("[cyan]Đang tải lịch học chi tiết...[/]"):
        schedules = catalog.get_class_schedule(guid_lhp=chosen_class.guid_lhp)

    if schedules:
        sch_table = Table(title=f"Lịch Chi Tiết: {chosen_class.ten_lop}")
        sch_table.add_column("Loại", style="cyan", width=6)
        sch_table.add_column("Thứ & Tiết", style="green")
        sch_table.add_column("Nhóm", justify="center", width=6)
        sch_table.add_column("Phòng", style="yellow")
        sch_table.add_column("Giảng Viên", style="bold magenta")
        sch_table.add_column("Thời Gian", style="dim")

        for sch in schedules:
            sch_table.add_row(sch.loai_tiet, sch.thu_tiet, sch.nhom_th or "-", sch.phong, sch.giang_vien, sch.thoi_gian)
        console.print(sch_table)

    if Confirm.ask(f"[bold green]🎯 Bạn có muốn thêm lớp '{chosen_class.ten_lop}' vào danh sách mục tiêu SĂN SLOT không?[/]", default=True):
        config.setdefault("target_classes", [])
        # Check if already added
        if not any(t.get("guid_lhp") == chosen_class.guid_lhp for t in config["target_classes"]):
            config["target_classes"].append({
                "id_dot": id_dot,
                "ma_mon": selected_subj.ma_mon,
                "ma_hp": selected_subj.ma_hp,
                "ten_mon": selected_subj.ten_mon,
                "guid_lhp": chosen_class.guid_lhp,
                "ten_lop": chosen_class.ten_lop,
                "nhom_th": chosen_class.nhom_th,
                "ma_mon_cha": selected_subj.ma_mon_cha
            })
            save_config(config)
            console.print(f"[bold green]✅ Đã thêm lớp '{chosen_class.ten_lop}' vào targets thành công![/]")
        else:
            console.print("[yellow]Lớp này đã có sẵn trong danh sách mục tiêu.[/]")

def handle_view_registered(catalog: CatalogService, reg_service: RegistrationService, id_dot: str):
    with console.status("[cyan]Đang tải danh sách học phần đã đăng ký...[/]"):
        registered = catalog.get_registered_courses(id_dot=id_dot)

    if not registered:
        console.print("[yellow]Chưa có học phần nào được đăng ký trong học kỳ này.[/]")
        return

    table = Table(title="Học Phần Đã Đăng Ký Trong Học Kỳ")
    table.add_column("STT", justify="center", width=5)
    table.add_column("Mã LHP", style="dim")
    table.add_column("Tên Môn Học", style="bold green")
    table.add_column("Lớp Dự Kiến", style="magenta")
    table.add_column("Số TC", justify="center", width=6)
    table.add_column("Nhóm TH", justify="center", width=8)
    table.add_column("Học Phí", justify="right", style="yellow")
    table.add_column("Trạng Thái", justify="center")

    for r in registered:
        table.add_row(r.stt, r.ma_lhp, r.ten_mon, r.lop_du_kien, str(r.so_tc), r.nhom_th or "-", r.hoc_phi, r.trang_thai_lhp)

    console.print(table)

    cancel_choice = Prompt.ask("\n[bold red]👉 Nhập STT môn muốn HỦY ĐĂNG KÝ (hoặc 0 để quay lại)[/]", default="0")
    if not cancel_choice.isdigit() or int(cancel_choice) <= 0 or int(cancel_choice) > len(registered):
        return

    item = registered[int(cancel_choice) - 1]
    if Confirm.ask(f"[bold red]⚠️ Bạn có CHẮC CHẮN muốn HỦY môn '{item.ten_mon}' ({item.lop_du_kien})?[/]", default=False):
        with console.status("[red]Đang gửi lệnh hủy môn...[/]"):
            res = reg_service.cancel_registered_class(id_dk=item.id_lhp_dk, guid_dk=item.guid)
        if res.get("success"):
            console.print(f"[bold green]✅ Hủy môn '{item.ten_mon}' thành công![/]")
        else:
            console.print(f"[bold red]❌ Hủy thất bại: {res.get('message')}[/]")

def handle_sniper_mode(catalog: CatalogService, reg_service: RegistrationService, config: Dict[str, Any]):
    targets = config.get("target_classes", [])
    if not targets:
        console.print("[bold yellow]⚠️ Chưa có lớp mục tiêu nào trong config.json![/]")
        console.print("[dim]Hãy vào Menu 1 để chọn môn và thêm lớp vào mục tiêu săn trước nhé.[/]")
        return

    console.print(Panel(f"🎯 [bold red]KÍCH HOẠT CHẾ ĐỘ SNIPER SĂN SLOT[/]\nĐang theo dõi [bold cyan]{len(targets)}[/] lớp mục tiêu...", border_style="red"))
    for idx, t in enumerate(targets, 1):
        console.print(f"  {idx}. [bold green]{t.get('ten_mon', '')}[/] - [magenta]{t.get('ten_lop', '')}[/]")

    sniper = SniperService(catalog, reg_service, targets)

    def on_event(ev_type: str, data: Dict[str, Any]):
        t = time.strftime("%H:%M:%S")
        if ev_type == "checked":
            c = data["class"]
            lat = data.get("latency_ms", 0)
            status_text = "[bold green]CÓ SLOT TRỐNG![/]" if data["slot_available"] else "[dim]Đầy (0 slot)[/]"
            console.print(f"[{t}] [cyan]{c.ten_lop}[/] | Sĩ số: {c.si_so_dk}/{c.si_so_max} | {status_text} [dim]({lat}ms)[/]")
        elif ev_type == "success":
            console.print(f"\n[bold green]🎉 [{t}] ĐĂNG KÝ THÀNH CÔNG LỚP: {data['target'].get('ten_lop')}! ({data['result'].get('message')})[/]\a")
        elif ev_type == "failed":
            console.print(f"[bold red]❌ [{t}] Bắn slot thất bại: {data['result'].get('message')}[/]")
        elif ev_type == "error":
            console.print(f"[bold red]⚠️ [{t}] Lỗi mạng: {data.get('error')}[/]")

    console.print("\n[dim]Bấm Ctrl + C để dừng Sniper bất cứ lúc nào.[/]\n")
    try:
        sniper.run_loop(delay_ms=1500, on_event=on_event)
    except KeyboardInterrupt:
        console.print("\n[yellow]Đã dừng Sniper Mode.[/]")

def handle_radar_mode(client: IUHClient, catalog: CatalogService, reg_service: RegistrationService, config: Dict[str, Any]):
    id_dot = config.get("id_dot_dang_ky", "62")
    radar = RadarService(client, id_dot=id_dot, interval_seconds=120)

    console.print(Panel(f"🛰️ [bold green]KÍCH HOẠT CHẾ ĐỘ RADAR 24/7 (NUÔI COOKIE & CANH MỞ ĐỢT)[/]\nĐang gửi ping mỗi 2 phút tới ID Đợt: [magenta]{id_dot}[/]...", border_style="green"))

    def on_ping(status: Dict[str, Any]):
        t = status.get("timestamp", time.strftime("%H:%M:%S"))
        code = status.get("code")
        msg = status.get("message", "")
        console.print(f"[{t}] 🛰️ Radar Heartbeat: Session sống | Đợt ID {id_dot}: [{code}] {msg[:60]}")

    def on_open(status: Dict[str, Any]):
        console.print(f"\n[bold red]🚨 [{time.strftime('%H:%M:%S')}] PHÁT HIỆN TRƯỜNG ĐÃ MỞ ĐỢT ĐĂNG KÝ HỌC PHẦN![/]\a\a\a")
        if config.get("target_classes"):
            console.print("[bold yellow]🚀 Tự động kích hoạt Sniper Mode ngay lập tức...[/]")
            handle_sniper_mode(catalog, reg_service, config)

    console.print("[dim]Bấm Ctrl + C để dừng Radar.[/]\n")
    radar.start_heartbeat(on_open_callback=on_open, on_ping_callback=on_ping)

    try:
        while radar.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        radar.stop_heartbeat()
        console.print("\n[yellow]Đã dừng Radar Mode.[/]")

def main():
    parser = argparse.ArgumentParser(description="IUH Sniper Pro CLI")
    parser.add_argument("--config", type=str, default="config.json", help="Đường dẫn file cấu hình")
    parser.add_argument("--session", type=str, default=None, help="Đường dẫn file session.json")
    parser.add_argument("--radar", action="store_true", help="Chạy trực tiếp chế độ Radar Heartbeat")
    parser.add_argument("--sniper", action="store_true", help="Chạy trực tiếp chế độ Sniper")
    args = parser.parse_args()

    config = load_config(args.config)
    client = IUHClient(session_path=args.session)

    if not run_auth_flow(client, config):
        sys.exit(1)

    id_dot = config.get("id_dot_dang_ky", "62")
    catalog = CatalogService(client)
    reg_service = RegistrationService(client)

    if args.radar:
        handle_radar_mode(client, catalog, reg_service, config)
        return

    if args.sniper:
        handle_sniper_mode(catalog, reg_service, config)
        return

    while True:
        console.print("\n")
        show_banner(catalog, id_dot)
        console.print("\n[bold cyan]DANH MỤC CHỨC NĂNG:[/]")
        console.print("  [bold green][1][/] 📋 Xem danh sách môn học đang mở & Chọn lớp săn")
        console.print("  [bold green][2][/] 📚 Xem học phần đã đăng ký (Kèm chức năng Hủy môn)")
        console.print("  [bold green][3][/] 🎯 Bắt đầu Chế độ SNIPER (Săn slot tự động)")
        console.print("  [bold green][4][/] 🛰️ Chế độ RADAR (Treo máy nuôi cookie 24/7 & Canh mở đợt)")
        console.print("  [bold red][5][/] 🚪 Đăng xuất / Xóa session")
        console.print("  [bold dim][0] Thoát chương trình[/]")

        cmd = Prompt.ask("\n[bold yellow]👉 Chọn chức năng [0-5][/]", default="1")
        if cmd == "1":
            handle_view_open_subjects(catalog, id_dot, config)
        elif cmd == "2":
            handle_view_registered(catalog, reg_service, id_dot)
        elif cmd == "3":
            handle_sniper_mode(catalog, reg_service, config)
        elif cmd == "4":
            handle_radar_mode(client, catalog, reg_service, config)
        elif cmd == "5":
            if os.path.exists(client.session_path):
                os.remove(client.session_path)
            console.print("[green]Đã xóa session.json. Lần sau mở sẽ yêu cầu đăng nhập lại.[/]")
            break
        elif cmd == "0":
            console.print("[dim]Tạm biệt![/]")
            break

if __name__ == "__main__":
    main()
