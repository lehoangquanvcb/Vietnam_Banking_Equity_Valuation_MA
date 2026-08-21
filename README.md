# NỀN TẢNG PHÂN TÍCH, ĐỊNH GIÁ & M&A NGÂN HÀNG VIỆT NAM

## 1. Mục tiêu
Project được thiết kế cho ba mục đích:
- Đầu tư cổ phiếu ngân hàng;
- M&A / thâu tóm / giá trị quyền kiểm soát;
- Tái cơ cấu ngân hàng và phân bổ giá mua (PPA).

Giao diện được Việt hóa tối đa. Các viết tắt chuẩn ngành như ROE, ROA, NIM, CASA, CAR, NPL, P/B, P/E, P/TBV, EPS, BVPS được giữ nguyên.

## 2. Kiến trúc dữ liệu
Vnstock Sponsor Bronze chạy **trên máy local**:

`Vnstock Bronze → ACTUAL CSV → valuation engine → GitHub → Streamlit Cloud đọc outputs`

Streamlit Cloud không cần cài hoặc gọi Vnstock runtime.

Lineage:
- `ACTUAL`: dữ liệu Vnstock/BCTC/giá thị trường;
- `CALCULATED`: tính toán từ dữ liệu ACTUAL;
- `ASSUMPTION`: giả định định giá/kịch bản;
- dữ liệu thiếu giữ `N/A`, không tự biến assumption thành dữ liệu thực.

## 3. Phương pháp định giá cổ phiếu
Phương pháp nội tại chính:
- Thu nhập thặng dư (Residual Income / Excess Return).

Phương pháp đối chiếu:
- P/B hợp lý (Justified P/B);
- P/B nhóm tương đồng;
- P/B lịch sử;
- P/TBV và P/E dùng để bổ sung góc nhìn.

Mô hình không dùng FCFF/EV-EBITDA làm phương pháp lõi cho ngân hàng.

## 4. Thẻ điểm 6 trụ cột
- Sinh lời;
- Tăng trưởng;
- Chất lượng tài sản;
- Nguồn vốn;
- An toàn vốn;
- Định giá.

Trọng số nằm tại sheet `TRONG_SO_CHAM_DIEM` trong Excel Master và được chuẩn hóa về 100%.

## 5. M&A / Thâu tóm
Logic:
`Standalone Value + Control Premium + PV Synergies - Integration Cost - Recapitalization`

Các chỉ tiêu:
- giá trị quyền kiểm soát;
- implied P/B và P/TBV;
- goodwill / bargain purchase;
- credit mark;
- identifiable intangibles;
- recapitalization;
- giao dịch so sánh có nguồn xác thực.

## 6. Tái cơ cấu
Không kết luận cổ phiếu/ngân hàng “rẻ” chỉ vì P/B thấp.

Bridge:
`Reported Equity → Extra Provision → NPL Haircut → Recapitalization → Adjusted Equity → Adjusted BVPS → Restructured Value`

## 7. Báo cáo chính thức khoảng 10 trang A4
Tab `Báo cáo & Quản trị` cho phép tải trực tiếp:
- PDF A4;
- Word chỉnh sửa được.

Nội dung mặc định:
1. Tóm tắt điều hành;
2. Hồ sơ ngân hàng & vị thế;
3. Sinh lời & hiệu quả;
4. Chất lượng tài sản;
5. Nguồn vốn & thanh khoản;
6. Vốn & sức chống chịu;
7. Định giá tương đối;
8. Định giá nội tại hoặc M&A;
9. Sensitivity hoặc PPA;
10. Kết luận, động lực & rủi ro.

Dashboard và báo cáo sử dụng **cùng valuation outputs**, không copy số liệu bằng tay.

## 8. Cập nhật dữ liệu
Chạy:

`RUN_UPDATE_AND_PUSH.bat`

BAT thực hiện:
1. export assumptions từ Excel Master;
2. refresh BCTC + ratios + giá từ Vnstock Bronze;
3. build valuation/M&A outputs;
4. commit + push lên GitHub.

## 9. Tạo báo cáo local bằng CMD
Ví dụ:

`python scripts\generate_report.py --ticker MBB --mode investment`

hoặc:

`python scripts\generate_report.py --ticker MBB --mode mna`

## 10. Streamlit
Khuyến nghị Python **3.12**.

Main file:

`app.py`

## 11. Excel Master
Các sheet quan trọng:
- `VALUATION_ASSUMPTIONS`
- `BANK_ASSUMPTIONS`
- `TRONG_SO_CHAM_DIEM`
- `M&A_ASSUMPTIONS`
- `DEAL_SIMULATOR`
- `DEAL_PRECEDENTS`
- `RESTRUCTURING`
- `CAU_HINH_BAO_CAO`
- `GOVERNANCE`
- `SOURCES`

## 12. Quản trị
Mọi kết quả M&A/PPA/tái cơ cấu là mô hình kịch bản nếu chưa có giá giao dịch thực tế. Các assumptions phải được tách khỏi dữ liệu quan sát và thể hiện rõ trong deliverable.

## 13. V3 - Kiểm soát phát hành
V3 bổ sung `KIEM_SOAT_PHAT_HANH` trong Excel Master và `scripts/quality_engine.py`.

Trước khi cho tải báo cáo, hệ thống tự phân loại:
- `CHÍNH THỨC`: đủ ngưỡng độ phủ và không thiếu quá nhiều chỉ tiêu lõi;
- `BẢN NHÁP`: có thể xuất để rà soát, PDF được đóng dấu `BẢN NHÁP – CẦN RÀ SOÁT`;
- `CHƯA ĐỦ DỮ LIỆU`: khóa nút xuất báo cáo.

Các chỉ tiêu lõi gồm giá thị trường, BVPS, ROE, NPL, tổng tài sản, dư nợ, tiền gửi, vốn chủ sở hữu, LNST và giá trị hợp lý.

V3 cũng tự sinh `Điểm cần lưu ý khi định giá`, gồm cảnh báo ROE bất thường/normalization, NPL, CAR, P/B so với P/B hợp lý và biến động giá 12 tháng. Đây là lớp kiểm soát tự động; analyst vẫn phải rà soát trước khi phát hành cho khách hàng.


## HOTFIX 2026-08-21 — Ticker schema lock
- Sửa lỗi `KeyError: Ticker` tại bước merge giá sau refresh Vnstock.
- Mỗi ngân hàng luôn giữ một dòng snapshot có `Ticker`, kể cả khi Fundamental API lỗi.
- Chuẩn hóa ticker/symbol/index về cột `Ticker` trước merge.
- Merge giá dùng one-to-one validation; dữ liệu lịch sử và log luôn có schema ổn định.
- Một ngân hàng lỗi không còn làm dừng toàn bộ batch 20 ngân hàng.
- Cuối refresh in `REFRESH SUMMARY` để biết số ngân hàng lấy BCTC/giá thành công.

## Chế độ chạy nhanh

Từ bản tối ưu này, không cần chạy full refresh cho mọi thay đổi.

- `RUN_FAST.bat`: không gọi Vnstock. Chỉ đọc assumptions từ Excel Master, build lại valuation/report từ CSV hiện có và push GitHub. Dùng khi sửa giao diện, trọng số, giả định, mô hình hoặc báo cáo.
- `RUN_REFRESH_ONE_BANK.bat`: nhập một mã như `STB`. Chỉ refresh BCTC + giá incremental của ngân hàng đó, sau đó build và push. Đây là cách nhanh nhất để kiểm thử một ngân hàng.
- `RUN_REFRESH_BANKS.bat`: refresh BCTC/ratios cho toàn bộ universe nhưng giữ nguyên lịch sử giá hiện có.
- `RUN_PRICES_ONLY.bat`: chỉ cập nhật giá cổ phiếu theo kiểu incremental, không gọi Fundamental/BCTC.
- `RUN_FULL_REFRESH.bat`: refresh BCTC + ratios + giá incremental toàn universe, build và push.
- `RUN_UPDATE_AND_PUSH.bat`: giữ để tương thích; hiện gọi `RUN_FULL_REFRESH.bat`.

### Tối ưu tốc độ

`refresh_vnstock.py` hỗ trợ:

```text
--mode fundamentals | prices | full
--tickers STB,MBB
--workers 1..6
--full-price-history
```

Giá cổ phiếu mặc định chỉ lấy lại từ 7 ngày trước ngày cuối cùng đã lưu để vừa nhanh vừa có overlap sửa dữ liệu. BCTC/history mới được merge vào dữ liệu cũ và deduplicate, không xóa lịch sử của các ngân hàng không được refresh.

Mặc định BAT dùng 4 worker. Nếu Vnstock báo rate limit, giảm `VNSTOCK_WORKERS=4` xuống 2 trong BAT tương ứng.
