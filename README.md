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

## Nâng cấp lớp định giá chiến lược / M&A (2026-08-21)
- Tách 3 lớp giá trị: thị trường, giá trị cơ bản, giá trị chiến lược/M&A.
- Thêm `config/market_intelligence.csv`; dữ liệu market intelligence không ghi đè fair value fundamental.
- STB được cấu hình vùng market intelligence 80.000-100.000 đồng/cp theo thông tin người dùng cung cấp, gắn nhãn USER_MARKET_INTELLIGENCE.
- Thêm đường cong giá lô chiến lược theo quy mô sở hữu, peer benchmarking mở rộng và đưa peer median vào báo cáo.
- Sửa hiển thị đơn vị giá nội bộ nghìn đồng/cp thành đồng/cp trên app/báo cáo.
- Biểu đồ CAR bỏ các điểm 0/âm không hợp lệ thay vì nối về 0.


## ENGINE V5.0 - bản hợp nhất sửa hồi quy
Bản này hợp nhất ba nhánh trước đây để tránh tái xuất hiện lỗi cũ:
- Data Quality Guardrails: CAR thiếu dữ liệu không biến thành 0; CIR chuẩn hóa dấu; NPL ưu tiên exact metric ID; ratio cache được repair trước RUN_FAST.
- Peer Benchmarking: app và báo cáo so ngân hàng với peer mean và peer median cho ROE, ROA, NIM, NPL, CAR, CASA, CIR, LDR, P/B và P/TBV.
- Strategic / M&A Value: giá trị cơ bản tách khỏi Market Intelligence / strategic block value; STB có input 80.000-100.000 đồng/cp theo USER_MARKET_INTELLIGENCE.
- Báo cáo phải có dòng `ENGINE V5.0` ở header. Nếu không thấy dòng này, Streamlit/GitHub vẫn đang chạy code cũ.

Sau khi copy đè package vào project hiện tại (giữ `.git`), chạy `RUN_FAST.bat`. RUN_FAST V5.0 sẽ chạy `repair_cached_data.py` trước `build_valuation.py`, không gọi API Vnstock.

## V6.0 - Bình quân 20 ngân hàng + Strategic Acquisition Case

- Mọi biểu đồ phân tích ngân hàng có benchmark `Bình quân 20 NH` (bình quân số học các ngân hàng trong universe có dữ liệu hợp lệ tại từng kỳ).
- Giá cổ phiếu được benchmark theo chỉ số hóa đầu kỳ = 100 để tránh so sánh sai do mệnh giá/thị giá khác nhau.
- ROE-P/B scatter có crosshair bình quân 20 ngân hàng; Football Field có giá hàm ý từ P/B bình quân 20 ngân hàng.
- Excel Master bổ sung `BENCHMARK_20_NH` và `STB_STRATEGIC_CASE`.
- STB Strategic Case tách rõ: standalone/fundamental value, public research benchmark và strategic/block value.
- Khoảng 80.000-100.000 đồng/cp là USER MARKET INTELLIGENCE, không được ghi nhận như giao dịch đã xác nhận.
- Kiểm tra tính hợp lý sử dụng: premium so với thị giá; implied P/B hiện tại/hậu xử lý; giá trị lô 32,5%; tỷ lệ thu hồi trên ước tính 63.250 tỷ đồng; benchmark nghiên cứu công khai 2026.
- Kết luận V6: 80.000 đồng/cp có thể biện minh tương đối tốt; 100.000 đồng/cp là hợp lý có điều kiện, cần xác suất xử lý tái cơ cấu cao và strategic/scarcity premium.


## V6.1 - Sửa chart và trục thời gian
- Tách chart quy mô bảng cân đối thành: (1) Tổng tài sản; (2) Dư nợ + tiền gửi.
- Tách chart sinh lời thành: (1) ROE + ROA; (2) NIM + CIR.
- Toàn bộ time-series chart dùng trục thời gian thực `PeriodDate`, không dùng categorical order của chuỗi ký tự quý.
- Target bank và Bình quân 20 NH được sort theo cùng khóa thời gian trước khi vẽ; thiếu quý không làm xáo trộn trục hoành.
- Sửa đồng thời Streamlit, PDF và Word report.


## V6.3 - Định dạng số Việt Nam & tự động dồn trang
- Báo cáo dùng quy ước số Việt Nam: `74.700 đồng/cp`, `892.049 tỷ đồng`, `5,0%`, `2,24x`.
- Biểu đồ trong Word/PDF dùng gần toàn bộ chiều ngang vùng in A4.
- Không còn ép mỗi mục phân tích vào một trang cố định.
- Word và PDF sử dụng cơ chế flow: nội dung tự chuyển sang trang kế tiếp khi hết chỗ, hạn chế khoảng trắng lớn.
- Biểu đồ được thiết kế dạng ngang rộng, chiều cao gọn hơn để tăng mật độ thông tin mà vẫn dễ đọc.
- Trục số của biểu đồ cũng sử dụng dấu chấm hàng nghìn và dấu phẩy thập phân theo quy ước Việt Nam.


## V6.4 - Chuẩn typography báo cáo
- Font Lato toàn bộ Word/PDF và biểu đồ.
- Nội dung chính: 11 pt, căn đều hai lề (Justified), line spacing 1,3; Before 6 pt; After 0 pt.
- Bảng: Lato 10 pt.
- Biểu đồ: Lato 10 pt cho nhãn, trục, chú giải và tiêu đề.
- Heading 1: Lato Bold 14 pt; Heading 2: Lato Bold 12 pt.
- Project không đóng gói/chia sẻ file font; máy chạy report cần cài Lato để xuất PDF đúng chuẩn.

## V7.0 - Xếp hạng tín nhiệm ngân hàng
- Bổ sung tab **Xếp hạng tín nhiệm** và chế độ phân tích riêng.
- Khung phân tích tham khảo cấu trúc báo cáo xếp hạng ngân hàng KLB do người dùng cung cấp: Vị thế kinh doanh; Vốn, đòn bẩy & lợi nhuận; Vị thế rủi ro; Huy động vốn; Thanh khoản; Quản trị & quản trị rủi ro; Hỗ trợ bên ngoài; Triển vọng; yếu tố nâng/hạ bậc.
- Kết quả tự động là **Xếp hạng mô phỏng / nội bộ**, không phải xếp hạng tín nhiệm chính thức. Các yếu tố quản trị, hỗ trợ và điều chỉnh chuyên viên phải được rà soát định tính.
- Có thể xuất **PDF + Word** báo cáo XHTN cho bất kỳ ngân hàng nào trong universe 20 ngân hàng.
- Báo cáo XHTN kế thừa chuẩn trình bày V6.4: Lato, nội dung 11 pt, bảng/biểu đồ 10 pt, căn đều hai lề, số kiểu Việt Nam.

### Xuất nhanh báo cáo XHTN trên Windows
Chạy `RUN_CREDIT_RATING_REPORT.bat`, nhập mã ngân hàng (KLB/STB/VCB...) và báo cáo Word/PDF sẽ được tạo trong thư mục `reports`.


## V7.2 - BICRA Anchor + notch methodology
- BICRA/Anchor Việt Nam mặc định: vnA- theo Phương pháp XHTN Ngân hàng 2025.
- Không còn tính rating bằng weighted composite score.
- Hồ sơ kinh doanh, Vốn & lợi nhuận, Vị thế rủi ro được chuyển trực tiếp thành notch (+2/+1/0/-1/-2 hoặc -3/-4 hoặc -5).
- Huy động vốn và Thanh khoản được chấm riêng 4 mức và kết hợp theo ma trận Bảng 10 để ra notch chung.
- SACP = Anchor + toàn bộ notch nội tại.
- ICR cuối cùng = SACP + notch hỗ trợ bên ngoài.
- Báo cáo bổ sung bảng cầu nối BICRA -> SACP -> ICR và phần Rủi ro vĩ mô & ngành tổng hợp từ báo cáo KLB tham khảo.
- Benchmark hiển thị là "Bình quân 20 ngân hàng niêm yết".
