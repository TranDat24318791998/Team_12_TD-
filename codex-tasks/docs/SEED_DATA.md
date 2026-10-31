# Dữ liệu mẫu và hằng số

Mọi con số ở đây là **giả định cho demo**, không phải số liệu thật của sàn nào. Task 2.1 chuyển file này thành `data/seed.json`; các task khác đọc từ `data/seed.json` hoặc `app/config.py`, không gõ lại số.

## 1. Năm shop cùng ngành quạt mini

| Trường | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Tên shop | Quạt Xinh Official | Gió Mát Store | Tiện Ích 24h | Nhà Bé Lan | Mát Lạnh Shop |
| Chủ shop | anh Minh | chị Hoa | anh Tuấn | chị Lan | anh Phúc |
| Giá bán (đ) | 189.000 | 129.000 | 159.000 | 175.000 | 99.000 |
| Giá vốn (đ) | 110.000 | 112.000 | 95.000 | 115.000 | 60.000 |
| Tồn kho | 400 | 250 | 15 | 300 | 350 |
| Chất lượng listing | 0,45 | 0,35 | 0,40 | 0,55 | 0,50 |
| Trang tìm kiếm | 3 | 4 | 3 | 3 | 2 |
| Lượt hiển thị gốc/ngày | 3.000 | 2.000 | 1.500 | 2.500 | 2.200 |
| Cho chạy quảng cáo | có | không | có | có | có |
| Quảng cáo tối đa/ngày (đ) | 100.000 | 0 | 80.000 | 45.000 | 50.000 |
| Voucher tối đa | 10% | 5% | 10% | 8% | 5% |
| Lãi tối thiểu/đơn (đ) | 30.000 | 12.000 | 25.000 | 18.000 | 15.000 |
| ROAS hoà vốn tối đa chấp nhận | 6,5 | 6,5 | 6,5 | 6,5 | 6,5 |
| Đánh giá | 4,6 | 4,6 | 4,6 | 4,6 | 4,6 |

Người bán giả lập (chỉ dùng khi máy tự quyết, không agent nào đọc):

| Shop | Voucher thật sự thoải mái | Sở thích nội dung |
| --- | --- | --- |
| A | 5% (sẽ tự sửa thẻ 10% → 5%) | — |
| D | — | ảnh nền sáng (góp ý "Ảnh nền tối quá" ở bản đầu) |
| B, C, E | — | — |

Khi giám khảo chơi, shop D do giám khảo quyết định thay cho người bán giả lập.

## 2. Listing của shop D (giám khảo đóng vai chị Lan)

- Tiêu đề gốc: `Quạt mini cầm tay sạc usb loại tốt giá rẻ`
- Mô tả gốc: `Quạt mini cầm tay. Sạc usb. 3 tốc độ gió. Pin 2000mAh. Có 3 màu.`
- Thuộc tính (agent nội dung chỉ được dùng các thuộc tính này): `3 tốc độ gió`, `sạc USB`, `pin 2000mAh`, `3 màu: Trắng, Hồng, Xanh mint`
- Ảnh gốc: `assets/products/D-1.jpg` … `D-4.jpg`, nền tối, chụp đơn giản. Ảnh tự chụp hoặc tự tạo trong ngày thi; không dùng ảnh có bản quyền của người khác.

Các shop khác chỉ cần tiêu đề và mô tả ngắn cùng kiểu, không cần ảnh.

## 3. Trend, lịch, phí

- Từ khoá trend: `quạt mini cầm tay`, ngành `quat_mini`, tăng 240% trong 7 ngày.
- Chỉ số trend: ngày 1 = 1,00, tăng 12% mỗi ngày tới ngày 7 rồi đứng yên.
- Ngày 1 mô phỏng = 2026-11-01. Sự kiện lịch: 11.11 ngày 2026-11-11; nhắc khi còn ≤ 5 ngày.
- Giả định phí sàn: phí cố định 8%, phí xử lý giao dịch 5%, thuế hộ kinh doanh 1,5% (cả ba tính trên giá sau voucher của shop) và 3.000đ mỗi đơn.

Công thức (code trong `validators.py`):

```
gia_sau_voucher = gia * (100 - voucher) / 100
lai_moi_don     = gia_sau_voucher * (1 - (8 + 5 + 1.5) / 100) - 3000 - gia_von
roas_hoa_von    = gia_sau_voucher / lai_moi_don        (vô cực nếu lai_moi_don <= 0)
nguong_dung     = làm tròn lên bội số 0,5 của roas_hoa_von
```

## 4. Hằng số

| Hằng số | Giá trị | Dùng ở |
| --- | --- | --- |
| `MIN_STOCK` | 30 | loại shop sắp hết hàng; không chạy quảng cáo |
| `ADS_MIN_DAILY` | 10.000đ | quảng cáo tối thiểu/ngày |
| `CPC` | 1.800đ | giá mỗi click quảng cáo |
| `MAX_ROUNDS` | 3 | số lượt tối đa của agent sàn |
| Gói mở đầu mặc định của sàn | làm mới nội dung, quảng cáo 70.000đ/ngày, voucher 10%, dừng khi ROAS < 4 trong 2 ngày, 3 ngày | agent sàn khi chưa có lịch sử |
| `PACKAGE_DAYS` | 3 | thời hạn gói trong demo |
| `REJECT_COOLDOWN_DAYS` | 3 | bị từ chối thì chờ 3 ngày |
| `PREF_ASK_THRESHOLD` | 1 | số lần sửa/góp ý trước khi hỏi thành luật (chỉnh cho demo ngắn) |
| `PREF_DECLINE_SILENCE_DAYS` | 14 | người bán nói Không thì 14 ngày không hỏi lại |
| `LESSON_CAP_PER_SCOPE` | 30 | số bài học tối đa mỗi phạm vi |
| `CALIBRATION_MIN_POINTS` / `WINDOW` | 5 / 30 | hiệu chỉnh dự báo |
| `PRIOR_CVR_BIAS` | 1,5 | dự báo ban đầu cố ý lạc quan 50% để thấy hiệu chỉnh |
| `QUALITY_REFRESH_GAIN` | 0,25 | làm mới nội dung tăng chất lượng listing từ ngày thứ 2 của gói |
| `MAX_CONTENT_VERSIONS` | 3 | số lần làm lại nội dung tối đa |

## 5. Câu chuyện phải ra đúng (ngày 1)

Đây là kết quả tính tay từ các số trên. Test của task 1.3 và 1.5 dùng bảng này.

| Shop | Lãi/đơn sau phí, không voucher | Agent shop chốt | Hoà vốn → ngưỡng dừng | Cơ chế được minh hoạ |
| --- | --- | --- | --- | --- |
| A | 48.595đ | voucher 10%, quảng cáo 70.000đ, chốt ngay lượt đầu | 5,24 → 5,5 | người bán giả lập sửa 10% → 5% → hôm sau hỏi đặt thành luật; gia hạn dựa trên lịch sử |
| B | −4.705đ | chỉ làm mới nội dung, kèm cảnh báo giá bán đang lỗ sau phí | — | agent shop dám nói không với khuyến mãi |
| C | — | bị loại ở bước chọn shop (tồn kho 15 < 30) | — | lọc trước khi thương lượng |
| D | 31.625đ | quảng cáo 45.000đ/ngày (kéo từ 70.000đ), voucher 3% (trần 8% nhưng trên 3% thì hoà vốn vượt 6,5) | 6,26 → 6,5 | thương lượng nhiều lượt; góp ý nội dung thành câu hỏi luật |
| E | 21.645đ | quảng cáo 50.000đ/ngày (kéo từ 70.000đ), voucher 5% | 5,40 → 5,5 | ROAS thật khoảng 3 → tự dừng quảng cáo ngày 3; gia hạn không kèm quảng cáo |

Cách agent shop chọn voucher: lấy giá trị nhỏ nhất trong bốn số — voucher sàn đề xuất, voucher tối đa của chủ shop, voucher lớn nhất còn giữ lãi tối thiểu, và (nếu có quảng cáo) voucher lớn nhất giữ hoà vốn ≤ ROAS hoà vốn tối đa chấp nhận.
