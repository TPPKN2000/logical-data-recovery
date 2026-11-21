# Đồ án giữa kỳ — Phục hồi dữ liệu FAT32

Môn: An toàn và phục hồi dữ liệu. Hệ thống tập tin được giao: **FAT32** (512 MB, cluster 4 KB, `mkfs.fat -F 32 -S 512 -s 8`).

Chương trình chỉ dùng thư viện chuẩn Python (≥ 3.9). Không dùng thư viện phân tích hệ thống tập tin và không gọi công cụ ngoài (`subprocess`, `os.system`). Ảnh đầu vào luôn được mở ở chế độ chỉ đọc.

## 1. Cấu trúc thư mục

| Tệp | Vai trò | Nguồn |
| --- | --- | --- |
| `recover.py` | Giao diện dòng lệnh thống nhất | Khung của giảng viên (không sửa) |
| `binio.py` | `AnhDia`: đọc u8/u16/u32/u64, tìm chuỗi byte (`tim`), hexdump, `sao_chep` | Khung (không sửa) |
| `tienich.py` | `NhatKy`, `ThuMucKetQua` (ghi `SHA256SUMS`), checksum exFAT | Khung (không sửa) |
| `selftest.py` | Chạy chương trình trên ảnh mẫu và so với đáp án | Khung (không sửa) |
| `bai_lam.py` | Lớp `BaiLam`: điều phối `info`, `case1`, `case2`, `case3`, `case_ext`, `repair`, `corrupt` | Nhóm |
| `utility.py` | Giải mã FAT32: đọc BPB, đổi cluster ↔ offset, đọc directory entry 8.3, đọc bảng FAT, lần chuỗi cluster, đọc dữ liệu tập tin | Nhóm |
| `case1.py` | Tình huống 1: suy ra lại 3 tham số boot sector bị sai, trích xuất tập tin và sửa đĩa (`repair`) | Nhóm |
| `case2.py` | Tình huống 2: tìm chuỗi cluster mồ côi, ghép lại với tên tập tin và sửa đĩa (`repair`) | Nhóm |
| `case3.py` | Tình huống 3: ghép 2 mảnh của JPEG bị phân mảnh theo nội dung và sửa bảng FAT (`repair`) | Nhóm |
| `case_ext.py` | Tình huống mở rộng (Bonus): tự làm hỏng (`corrupt`), khôi phục (`case_ext`) và sửa đĩa (`repair`) cho kịch bản `ext-root` | Nhóm |
| `jpegscan.py` | Phân tích header JPEG baseline và giải mã entropy (Huffman) để kiểm tra một cách ghép | Nhóm |
| `bonus.json` | Tệp đặc tả JSON cho tình huống mở rộng `ext-root` | Nhóm |
| `nhom.json` | Mã nhóm, hệ thống, thành viên, khai báo phần cộng điểm (`repair`, `mo_rong`) | Nhóm |

Luồng gọi: `recover.py` → `BaiLam` (`bai_lam.py`) → `case1/2/3/ext.py` → `utility.py` (và `jpegscan.py` cho tình huống 3) → `binio.py`.

## 2. Cách chạy

```bash
# Xem thông tin phân vùng và danh sách tập tin (chạy trên ảnh nguyên vẹn)
python recover.py --image anh.img --info
python recover.py --image anh.img --info --json       # dạng JSON (dùng khi chấm thi)

# Phục hồi các tình huống chính (trích xuất tập tin)
python recover.py --image case1.img --case 1 --out ket_qua/case1
python recover.py --image case2.img --case 2 --out ket_qua/case2
python recover.py --image case3.img --case 3 --out ket_qua/case3

# Tình huống mở rộng Bonus (ext-root: hỏng con trỏ thư mục gốc)
python recover.py --image clean.img --corrupt bonus.json --out anh_hong.img   # tự làm hỏng ảnh
python recover.py --image anh_hong.img --case ext --out ket_qua/ext          # tự phục hồi

# Phần cộng điểm Sửa đĩa (--repair)
python recover.py --image case1.img --case 1 --out ket_qua/case1 --repair da_sua_case1.img
python recover.py --image case2.img --case 2 --out ket_qua/case2 --repair da_sua_case2.img
python recover.py --image case3.img --case 3 --out ket_qua/case3 --repair da_sua_case3.img
python recover.py --image anh_hong.img --case ext --out ket_qua/ext --repair da_sua_ext.img

# Ghi thêm nhật ký ra tệp
python recover.py ... --log nhat_ky.jsonl

# Tự kiểm tra trên ảnh mẫu (yêu cầu thư mục mẫu có kèm các file .json đáp án)
python selftest.py --mau duong_dan/mau/fat32
```

* Nhật ký (stderr) gồm mỗi dòng một bản ghi JSON, gồm `buoc` (đọc/tính), `quyet_dinh` (lựa chọn) và `canh_bao`. Offset được in dạng hex.
* Kết quả phục hồi lưu theo đúng đường dẫn gốc (`DATA/<TÊN>`) kèm tệp `SHA256SUMS`.
* Mã thoát: `0` thành công, `1` lỗi không xử lý được, `2` tính năng chưa cài đặt.

## 3. Trạng thái cài đặt

| Chức năng | Trạng thái |
| --- | --- |
| `--info` / `--info --json` | **Đã cài** |
| `--case 1` | **Đã cài** |
| `--case 2` | **Đã cài** |
| `--case 3` | **Đã cài** (JPEG baseline SOF0) |
| `--repair` | **Đã cài** (Hỗ trợ Case 1, 2, 3 và ext; kiểm chứng qua `fsck.fat -n` sạch lỗi 100%) |
| `--corrupt` / `--case ext` | **Đã cài** (Kịch bản `ext-root` với đặc tả `bonus.json`) |

`nhom.json` khớp hoàn toàn với bảng này: khai báo `"repair": [1, 2, 3]` và `"mo_rong": {"tinh_huong": "ext-root", "dac_ta": "bonus.json"}`.

## 4. Thuật toán

### 4.1 `--info`
1. `doc_bpb` đọc `BytsPerSec` (0x0B), `SecPerClus` (0x0D), `RsvdSecCnt` (0x0E), `NumFATs` (0x10), `FATSz32` (0x24), `RootClus` (0x2C).
2. `fat_off = Rsvd × bps`; `data_off = (Rsvd + NumFATs × FATSz32) × bps`; `offset(cluster c) = data_off + (c − 2) × cluster_size`.
3. Đọc thư mục gốc, tìm mục `DATA`, rồi liệt kê các tập tin trong `DATA`. Entry LFN (0x0F), entry đã xóa (0xE5) và nhãn volume bị bỏ qua.

### 4.2 Tình huống 1 — sai `SecPerClus`, `RsvdSecCnt`, `FATSz32`
Ba trường này sai ở cả boot sector và bản sao (sector 6), nên chương trình không dùng chúng mà suy ra từ nội dung đĩa:
1. Quét tìm chữ ký đầu bảng FAT `F8 FF FF 0F FF FF FF 0F` ở các offset là bội số của `BytsPerSec`, bắt đầu từ sector 1. Lần tìm thấy thứ nhất là FAT1, lần thứ hai là FAT2.
2. `RsvdSecCnt = off(FAT1) / bps`; `FATSz32 = (off(FAT2) − off(FAT1)) / bps`.
3. `SecPerClus`: thử 1, 2, 4, …, 64. Với mỗi giá trị, đọc thư mục gốc, `DATA`, rồi kiểm tra mọi tập tin có số cluster của chuỗi FAT bằng `ceil(size / cluster_size)`. Giá trị nhỏ nhất thỏa mãn được chọn.
4. Dùng bộ tham số đúng để trích xuất toàn bộ tập tin trong `DATA`.
5. Khi có `--repair`: ghi các tham số đúng vào Sector 0 và Sector 6 trên bản sao ảnh đĩa.

### 4.3 Tình huống 2 — mất liên kết tên → dữ liệu
Ba tập tin trong `DATA` có First Cluster (0x14 và 0x1A) sai; tên, kích thước và chuỗi FAT còn nguyên.
1. Entry có First Cluster khác 0 là tập tin còn nguyên (`file_tot`); các entry còn lại là `file_mat_fc`.
2. Quét FAT tìm chuỗi mồ côi. Đầu chuỗi là cluster đã cấp phát, không là đích của cluster nào khác và không thuộc root, `DATA` hay tập tin còn nguyên.
3. Ghép tên với chuỗi theo hai tiêu chí: số cluster của chuỗi bằng `ceil(size / cluster_size)` và byte đầu cluster khớp định dạng theo phần mở rộng (JPG `FF D8 FF`, PNG `89 50 4E 47…`, PDF `%PDF-`, TXT là ASCII in được).
4. Lưu các tập tin đã ghép và cả các tập tin còn nguyên.
5. Khi có `--repair`: ghi lại `FirstCluster` đúng vào trường `0x14` và `0x1A` của từng Directory Entry bị hỏng.

### 4.4 Tình huống 3 — mất chuỗi FAT của JPEG phân mảnh thành 2 mảnh
1. Tìm JPEG có số cluster trong chuỗi FAT khác `ceil(size / cluster_size)`. Đó là mục tiêu, với `c0` = First Cluster và `need = ceil(size / cs)`.
2. Phân tích header JPEG (`jpegscan.phan_tich_dau`): SOF, DHT, DRI, SOS, số khối MCU.
3. Ứng viên cluster cuối là cluster chưa thuộc tập tin nào khác, nằm trong khoảng sau `c0 + need`, và có `FF D9` đúng ở cuối phần dữ liệu thực của cluster cuối (vị trí `tail = size − (need − 1) × cs`).
4. Với mỗi ứng viên cuối `ec` và mỗi độ dài mảnh 1 là `k` (`need − 1` giảm dần về 1), mảnh 2 là `[ec − (need − k) + 1 … ec]`. Ghép thử mảnh 1 + mảnh 2.
5. Giải mã entropy bắt đầu từ snapshot MCU gần nhất trước điểm nối. Cách ghép đúng khi giải mã đủ số MCU và gặp `FF D9` đúng tại byte `size`.
6. Ghi chuỗi cluster cuối cùng vào nhật ký và lưu tập tin.
7. Khi có `--repair`: tái thiết toàn bộ chuỗi cluster của file ảnh vào cả 2 bảng FAT (FAT1 và FAT2), kết thúc bằng marker `0x0FFFFFFF`.

### 4.5 Tình huống mở rộng (Bonus) — `ext-root` (sai con trỏ thư mục gốc)
1. `--corrupt`: Nhận `bonus.json`, ghi đè `0` vào trường `BPB_RootClus` (offset `0x2C`) ở Sector 0 và Sector 6. Tạo ra `anh_hong.img` và tệp theo dõi `.changes.json`.
2. `--case ext`: Nhận thấy `RootClus` bị lỗi, chương trình quét các cluster từ cụm 2 trở đi để tìm Thư mục gốc. Cụm thư mục gốc được xác định chính xác nhờ đặc điểm: chứa mục thư mục con tên là `DATA` (attribute `0x10`) và không bắt đầu bằng entry `.` hay `..`.
3. Dùng cluster thư mục gốc tìm được để duyệt `DATA` và khôi phục toàn bộ các tập tin.
4. Khi có `--repair`: ghi lại số cluster thư mục gốc tìm được vào offset `0x2C` ở Sector 0 và Sector 6.

## 5. Giới hạn đã biết

* Chỉ đọc tên 8.3 (chưa ghép entry LFN, chưa xử lý cờ chữ thường ở byte 0x0C của entry).
* Thư mục gốc và `DATA` mỗi thư mục chỉ đọc đúng 1 cluster (đúng với bộ dữ liệu rút gọn của đề).
* Tình huống 2 coi `First Cluster = 0` là đã hỏng.
* Tình huống 3 chỉ hỗ trợ JPEG baseline (SOF0/SOF1) có quét đan xen và không có đường lui nếu giải mã thất bại.

## 6. Phân công

| Thành viên | MSSV | Phần phụ trách |
| --- | --- | --- |
| Lữ Bảo Đạt | 23127338 | Tình huống 1 (`case1.py`), Tình huống mở rộng Bonus (`case_ext.py`, `bonus.json`), Sửa đĩa `repair` (Case 1, ext) |
| Lương Thành Lộc | 23127405 | Tình huống 2 (`case2.py`), Tình huống 3 (`case3.py`, `jpegscan.py`), Tiện ích FAT (`utility.py`), Sửa đĩa `repair` (Case 2, 3) |

## 7. Sản phẩm nộp

* Báo cáo PDF (tối đa 20 trang).
* Mã nguồn trong repo này.
* Thư mục `recovered/` do chương trình tạo ra, có `SHA256SUMS`, cùng nhật ký chạy (`--log`) trên ảnh của nhóm.
* Phần cộng điểm: tệp đặc tả `bonus.json` và tệp ảnh tự làm hỏng (đặt trên Google Drive nếu kích thước lớn).
