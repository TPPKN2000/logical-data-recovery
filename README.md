# Khung chương trình — Đồ án phục hồi dữ liệu

Khung chỉ lo phần "ống nước": dòng lệnh, đọc byte, nhật ký, lưu kết quả, checksum exFAT, tự kiểm tra. **Toàn bộ việc giải mã hệ thống tập tin và phục hồi là phần của nhóm**, viết trong `bai_lam.py` (có thể tách thêm tệp và import).

| Tệp | Nội dung | Được sửa? |
| --- | --- | --- |
| `bai_lam.py` | Lớp `BaiLam`: `info`, `case1`, `case2`, `case3`, `case_ext`, `repair`, `corrupt` | **Có — phần làm bài** |
| `nhom.json` | Mã nhóm, hệ thống, thành viên, phần cộng điểm đăng ký | **Có** |
| `recover.py` | Giao diện dòng lệnh thống nhất | Không |
| `binio.py` | `AnhDia`: đọc u8/u16/u32/u64 (LE/BE), tìm chuỗi byte, hexdump, sao chép để ghi | Không |
| `tienich.py` | `NhatKy`, `ThuMucKetQua`, checksum exFAT | Không |
| `selftest.py` | Chạy chương trình trên bộ ảnh mẫu và so với đáp án mẫu | Không |

Yêu cầu: Python 3.9 trở lên, **chỉ thư viện chuẩn**. Cấm thư viện phân tích hệ thống tập tin (pytsk3, dfvfs, pyfatfs, libfsntfs…) và cấm gọi công cụ ngoài (`subprocess`, `os.system`).

## Dòng lệnh

```
python recover.py --image anh.img --info              # in tham số và danh sách tập tin
python recover.py --image anh.img --info --json       # dạng JSON (giảng viên dùng khi chấm)
python recover.py --image case2.img --case 2 --out ket_qua/
python recover.py --image case1.img --case 1 --out ket_qua/ --repair da_sua.img
python recover.py --image clean.img --corrupt mo_rong.json --out anh_hong.img
python recover.py ... --log nhat_ky.jsonl             # lưu thêm nhật ký ra tệp
```

* `--info --json` phải trả về `{"fs": ..., "cluster_size": ..., "files": [{"path": "DATA/A12.JPG", "size": 123}]}` (chỉ tập tin, không thư mục; đường dẫn tính từ gốc volume, dùng `/`).
* `--case` lưu tập tin bằng `out.luu("DATA/A12.JPG", data)` — giữ đúng đường dẫn gốc; đường dẫn đúng được tính điểm riêng.
* Nhật ký (stderr) là căn cứ đối chiếu với báo cáo: ghi mọi bước quan trọng bằng `self.log.buoc(...)`, mọi lựa chọn bằng `self.log.quyet_dinh(...)`.
* Không bao giờ ghi lên ảnh đầu vào: `--repair` và `--corrupt` phải dùng `img.sao_chep(duong_dan_moi)`.

## Tự kiểm tra

Bộ ảnh mẫu (`mau/<he_thong>/`) được phát kèm đáp án. Chạy:

```
python selftest.py --mau duong_dan/mau/ntfs
```

Kết quả cho biết số tập tin khôi phục đúng nội dung và đúng đường dẫn ở từng tình huống. Giảng viên chấm đúng theo cách này, nhưng trên **ảnh của nhóm và một bộ ảnh ẩn** — vì vậy không được cố định offset, số cluster hay tên tập tin của ảnh mẫu/ảnh nhóm trong mã.

## Phần cộng điểm

Khai báo trong `nhom.json`:

```json
"cong_diem": {"repair": [1, 2], "mo_rong": {"tinh_huong": "ext-size", "dac_ta": "mo_rong.json"}}
```

* `repair`: danh sách tình huống có cài `--repair`. Ảnh sửa được kiểm tra bằng cách đọc lại toàn bộ tập tin và chạy `fsck` chế độ chỉ đọc.
* `mo_rong`: một trong `ext-root`, `ext-size`, `ext-mbr`. `corrupt()` phải trả về danh sách vùng đã sửa, ví dụ `[{"offset": 61468, "length": 4, "cau_truc": "DIR_FileSize của A12.JPG"}]`; `recover.py` tự ghi danh sách này ra `<ảnh hỏng>.changes.json`. Mọi byte thay đổi phải nằm trong các vùng đã khai và không được chạm vùng dữ liệu tập tin. Sau đó `--case ext` sẽ được chạy trên ảnh nhóm tự làm hỏng và trên ảnh ẩn cùng tình huống.
