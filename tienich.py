"""Nhật ký, lưu tập tin phục hồi, và hàm checksum exFAT (được phép dùng theo đề)."""
import hashlib
import json
import os
import sys
import time


class NhatKy:
    """Nhật ký thống nhất: mỗi bước một dòng, có offset và giá trị để đối chiếu với báo cáo.

        log.buoc("Đọc BPB_BytsPerSec", offset=0x0B, gia_tri=512)
        log.quyet_dinh("Chọn SecPerClus = 8 vì ...")
    """

    def __init__(self, tep=None):
        self.tep = open(tep, "a", encoding="utf-8") if tep else None
        self.t0 = time.time()

    def _ghi(self, loai, msg, **kv):
        rec = {"t": round(time.time() - self.t0, 3), "loai": loai, "msg": msg}
        for k, v in kv.items():
            rec[k] = f"{v:#x}" if k == "offset" and isinstance(v, int) else v
        line = json.dumps(rec, ensure_ascii=False)
        print(line, file=sys.stderr)
        if self.tep:
            self.tep.write(line + "\n")
            self.tep.flush()

    def buoc(self, msg, offset=None, gia_tri=None):
        self._ghi("buoc", msg, **({} if offset is None else {"offset": offset}),
                  **({} if gia_tri is None else {"gia_tri": gia_tri}))

    def quyet_dinh(self, msg, **kv):
        self._ghi("quyet_dinh", msg, **kv)

    def canh_bao(self, msg, **kv):
        self._ghi("canh_bao", msg, **kv)


class ThuMucKetQua:
    """Lưu tập tin phục hồi theo đúng đường dẫn tương đối (vd. 'DATA/A12.JPG') và ghi SHA256SUMS."""

    def __init__(self, goc):
        self.goc = os.path.abspath(goc)
        os.makedirs(self.goc, exist_ok=True)
        self.tong = []

    def luu(self, duong_dan_tuong_doi, data: bytes):
        rel = duong_dan_tuong_doi.replace("\\", "/").lstrip("/")
        p = os.path.abspath(os.path.join(self.goc, rel))
        if not p.startswith(self.goc + os.sep):
            raise ValueError(f"đường dẫn không hợp lệ: {duong_dan_tuong_doi}")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        self.tong.append((hashlib.sha256(data).hexdigest(), rel))
        return p

    def ket_thuc(self):
        with open(os.path.join(self.goc, "SHA256SUMS"), "w") as fh:
            for h, rel in self.tong:
                fh.write(f"{h}  {rel}\n")


# ---------------- checksum exFAT (giảng viên cấp sẵn) ----------------
def exfat_boot_checksum(vung_boot: bytes, bytes_per_sector: int) -> int:
    """Boot Checksum trên 11 sector đầu của vùng boot (bỏ byte 106, 107, 112). Ghi lặp lại vào sector 11."""
    c = 0
    for i in range(11 * bytes_per_sector):
        if i in (106, 107, 112):
            continue
        c = ((((c & 1) << 31) | (c >> 1)) + vung_boot[i]) & 0xFFFFFFFF
    return c


def exfat_set_checksum(entry_set: bytes) -> int:
    """SetChecksum của một entry set (32 × (SecondaryCount + 1) byte), bỏ byte 2, 3 của entry đầu."""
    c = 0
    for i, b in enumerate(entry_set):
        if i in (2, 3):
            continue
        c = ((((c & 1) << 15) | (c >> 1)) + b) & 0xFFFF
    return c


def exfat_name_hash(ten: str) -> int:
    h = 0
    for ch in ten.upper():
        v = ord(ch)
        for b in (v & 0xFF, v >> 8):
            h = ((((h & 1) << 15) | (h >> 1)) + b) & 0xFFFF
    return h
