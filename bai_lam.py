"""PHẦN LÀM BÀI CỦA NHÓM.

Quy tắc:
  * Tự giải mã mọi cấu trúc từ byte (dùng binio.AnhDia). Cấm thư viện phân tích hệ thống tập tin
    (pytsk3, dfvfs, pyfatfs, libntfs, libext2fs...) và cấm gọi công cụ ngoài (subprocess, os.system).
  * Không cố định offset / số cluster / giá trị của ảnh nhóm: chương trình sẽ chạy trên ảnh ẩn.
  * Không ghi lên ảnh đầu vào; muốn sửa thì img.sao_chep(...).
  * Ghi nhật ký mọi bước quan trọng: self.log.buoc(...), self.log.quyet_dinh(...).
  * Có thể tách mã ra nhiều tệp (vd. ntfs.py, runlist.py) và import vào đây.
"""
import utility as ut
import case1
import case2

class BaiLam:
    def __init__(self, log):
        self.log = log

    # ------------------------------------------------------------------ --info
    def info(self, img):
        """Đọc ảnh NGUYÊN VẸN, trả về dict:
            {"fs": "fat32|exfat|ntfs|ext4",
             "cluster_size": 4096,                # kích thước cluster/block (byte)
             ...                                  # các tham số khác tuỳ hệ thống (không chấm)
             "files": [{"path": "DATA/A12.JPG", "size": 123456}, ...]}   # chỉ tập tin, không thư mục
        """
        p = ut.doc_bpb(img)
        self.log.buoc("Đọc thông số BPB", gia_tri={
            "BytsPerSec": p["bps"], "SecPerClus": p["spc"],
            "RsvdSecCnt": p["rsvd"], "FATSz32": p["fatsz"], "RootClus": p["root"]
        })
        # duyệt Root Dir tìm thư mục DATA
        root_entries = ut.doc_muc_thu_muc(img, p["root"], p["data_off"], p["cs"])
        data_dir = next((e for e in root_entries if e["name"] == "DATA" and e["is_dir"]), None)
        files = []
        if data_dir:
            data_entries = ut.doc_muc_thu_muc(img, data_dir["fc"], p["data_off"], p["cs"])
            for e in data_entries:
                if not e["is_dir"]:
                    files.append({"path": f"DATA/{e['name']}", "size": e["size"]})
                    self.log.buoc(f"Tìm thấy tập tin: DATA/{e['name']}", gia_tri=f"{e['size']} bytes")
        return {
            "fs": "fat32",
            "cluster_size": p["cs"],
            "bytes_per_sector": p["bps"],
            "sectors_per_cluster": p["spc"],
            "reserved_sectors": p["rsvd"],
            "fat_count": p["nfat"],
            "fat_size_sectors": p["fatsz"],
            "root_cluster": p["root"],
            "fat_offset": p["fat_off"],
            "data_offset": p["data_off"],
            "files": files,
        }

    # ------------------------------------------------------------- tình huống
    def case1(self, img, out):
        """Tình huống 1 — sai tham số boot sector / superblock.
        Suy ra giá trị đúng, rồi trích xuất MỌI tập tin: out.luu("DATA/A12.JPG", data)."""
        case1.xu_ly(img, out, self.log)

    def case2(self, img, out):
        """Tình huống 2 — sai directory entry. Ghép đúng tên với dữ liệu, lưu các tập tin bị ảnh hưởng
        (lưu thêm cả tập tin không bị ảnh hưởng cũng được)."""
        case2.xu_ly(img, out, self.log)

    def case3(self, img, out):
        """Tình huống 3 — sai chuỗi vị trí. Ghép mảnh theo nội dung, lưu tập tin JPEG mục tiêu."""
        raise NotImplementedError("case3")

    def case_ext(self, img, out):
        """Tình huống mở rộng nhóm đã chọn (khai trong nhom.json)."""
        raise NotImplementedError("case_ext")

    # --------------------------------------------------------------- cộng điểm
    def repair(self, img, case, anh_moi):
        """--repair: sửa trên BẢN SAO và ghi ra anh_moi.
            ban_sua = img.sao_chep(anh_moi)
            ban_sua.ghi_u16(..., ...)
            ban_sua.dong()
        """
        raise NotImplementedError("repair")

    def corrupt(self, img, dac_ta, anh_hong):
        """--corrupt: từ ảnh sạch, tạo ảnh hỏng theo đặc tả JSON của nhóm.
        Trả về danh sách vùng đã sửa (giảng viên đối chiếu tự động):
            [{"offset": 1234, "length": 4, "cau_truc": "BPB_RootClus (sector 0)"}, ...]
        Mọi byte thay đổi phải nằm trong các vùng này và không được chạm vùng dữ liệu tập tin."""
        raise NotImplementedError("corrupt")
