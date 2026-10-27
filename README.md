# IUH Ledger — Sổ Cái Đăng Ký Học Phần & Trạm Giám Sát Tự Động IUH

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-pywebview%20%7C%20Edge%20WebView2-emerald.svg)](https://pywebview.flowrl.com/)
[![Design](https://img.shields.io/badge/Design-Hallmark%20Dose%20Theme-186e55.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

Ứng dụng Desktop độc lập (Standalone Desktop Application) hỗ trợ sinh viên Trường Đại học Công nghiệp TP.HCM (IUH) tra cứu học phần kế hoạch, quản lý lịch học, xem thời khóa biểu tuần và giám sát đăng ký học phần tự động thông qua việc tương tác trực tiếp với API của cổng đào tạo nhà trường (`sv.iuh.edu.vn` & `dkhp.iuh.edu.vn`).

---

## ✨ Điểm Nổi Bật & Các Màn Hình Chính

1. **Học phần kế hoạch (Curriculum Catalog)**:
   - Tra cứu danh mục môn học mở theo từng học kỳ và từng loại học (Học mới, Học lại, Học cải thiện).
   - Bộ lọc thời gian thực: Tìm kiếm nhanh theo tên/mã môn học, lọc các lớp không bị trùng lịch với thời khóa biểu hiện tại.
   - Ngăn kéo chi tiết (Interactive Drawer): Xem đầy đủ danh sách lớp học phần mở, phân chia rõ ràng nhóm thực hành, lịch học từng buổi, phòng học và giảng viên phụ trách.

2. **Học phần đã đăng ký (Registered Study Ledger)**:
   - Tổng hợp danh sách tất cả các lớp học phần sinh viên đã đăng ký thành công trong học kỳ.
   - Thống kê chi tiết số lượng tín chỉ tích lũy, tổng học phí phát sinh, trạng thái khóa môn.
   - Hỗ trợ thao tác hủy lớp học phần trực tiếp với xác nhận an toàn.

3. **Thời khóa biểu tuần & Lịch dự kiến ghép lớp (Weekly Timetable Matrix)**:
   - Lưới thời khóa biểu 7 ngày (Thứ 2 đến Chủ nhật) $\times$ 3 ca học (Sáng, Chiều, Tối).
   - Chuẩn hóa 5 nhóm màu phân loại đồng bộ với cổng nhà trường: Lý thuyết, Thực hành, Trực tuyến (MS Teams), Lịch thi, Lịch tạm ngưng.
   - **Chế độ Lịch dự kiến ghép lớp (Interactive Preview)**: Tự động chiếu các lớp đang theo dõi trong hàng đợi giám sát lên lưới tuần dạng thẻ viền nét đứt, giúp sinh viên phát hiện xung đột lịch học trước khi đăng ký.

4. **Trạm giám sát đăng ký (Registration Watchdog / Slot Sniper)**:
   - Cơ chế hàng đợi mục tiêu đa lớp với khóa định danh kết hợp `(guid_lhp, nhom_th)`.
   - Vòng lặp thăm dò tự động (chu kỳ cấu hình từ 500ms đến 3000ms) bắt ngay thời điểm có sinh viên khác hủy lớp hoặc trường mở thêm chỉ tiêu.
   - Tự động ghi danh và phát chuông âm thanh Web Audio hai tông thông báo tức thì.
   - Nhật ký đo lường từ xa (Live Telemetry Console) hiển thị độ trễ từng lượt quét.

5. **Cấu hình hệ thống & Dịch vụ nền (Settings & Background Services)**:
   - **Dịch vụ duy trì phiên nền (Heartbeat Service)**: Tự động gửi tín hiệu giữ phiên định kỳ (mặc định 62s) ngăn chặn ngắt kết nối đột ngột khi treo máy qua đêm.
   - **Thông báo từ xa qua Telegram Bot**: Gửi tin nhắn tức thì về điện thoại khi có sự kiện đăng ký thành công.
   - **Chính sách an toàn**: Tùy chọn tự động đổi lớp cũ nếu lớp mới thuộc cùng môn học.

6. **Xác thực tài khoản & Quản lý phiên (Authentication & Session)**:
   - Mật khẩu được mã hóa an toàn bằng thuật toán AES-128-CBC cục bộ trên máy trạm trước khi gửi lên cổng nhà trường.
   - Tự động tải mã bảo vệ Captcha trực tiếp từ máy chủ IUH.
   - Hỗ trợ lưu trữ cookie phiên làm việc (`ASC.AUTH`) và nút đăng xuất/chuyển tài khoản tiện lợi.

---

## 🛠️ Cài Đặt & Chạy Trực Tiếp Từ Mã Nguồn

### Yêu cầu môi trường
- Python 3.10 trở lên trên hệ điều hành Windows 10/11.
- Microsoft Edge WebView2 Runtime (có sẵn mặc định trên Windows 10/11).

### Các bước cài đặt
```bash
# 1. Clone repository về máy
git clone git@github.com-vhp201003:vhp201003/iuh-ledger.git
cd iuh-ledger

# 2. Tạo và kích hoạt môi trường ảo (khuyến nghị)
python -m venv .venv
.venv\Scripts\activate

# 3. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt

# 4. Sao chép file cấu hình mẫu
copy config.example.json config.json

# 5. Khởi chạy ứng dụng
python -m iuh_sniper.run_gui
```

---

## 📦 Đóng Gói Thành File Thực Thi Độc Lập (.exe)

Dự án cung cấp sẵn script đóng gói 1-click sử dụng PyInstaller:

```bash
# Chạy file batch đóng gói
build_exe.bat
```

Sau khi đóng gói hoàn tất:
- File thực thi độc lập sẽ nằm tại: `iuh_sniper\dist\IUH_Ledger\IUH_Ledger.exe`
- Ứng dụng đã được nhúng sẵn Runtime, thư viện DLLs, biểu tượng vector icon và giao diện web cục bộ. Người dùng chỉ cần sao chép cả thư mục `IUH_Ledger` sang máy tính khác là có thể chạy ngay mà không cần cài đặt Python.

---

## 🧪 Kiểm Thử Tự Động (Test Suite)

Dự án đi kèm bộ 10 bài kiểm thử đơn vị và hợp thành bao phủ toàn bộ luồng hoạt động:

```bash
python -m unittest iuh_sniper.tests.test_e2e_cli -v
```

Kiểm tra tiêu chuẩn thiết kế giao diện bằng Hallmark Sloplint:
```bash
node <path-to-sloplint>/sloplint.mjs iuh_sniper/gui --scope app
```

---

## ⚖️ Tuyên Bố Miễn Trừ Trách Nhiệm (Disclaimer)

Ứng dụng được phát triển nhằm mục đích nghiên cứu học thuật, tìm hiểu kiến trúc mạng máy tính và hỗ trợ cá nhân trong quá trình sắp xếp thời khóa biểu học tập tại IUH. Tác giả không chịu bất kỳ trách nhiệm nào liên quan đến việc sử dụng sai mục đích hoặc vi phạm quy định đào tạo của nhà trường.
