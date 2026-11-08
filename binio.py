"""Đọc ảnh đĩa theo byte. KHÔNG chứa bất kỳ đoạn giải mã hệ thống tập tin nào.

    img = AnhDia("case1.img")          # mở chỉ đọc
    img.u32(0x24)                      # số nguyên 4 byte little-endian tại offset 0x24
    img.u32be(0x2021000)               # big-endian (journal Ext4)
    print(img.hexdump(0x400, 0x40))    # in hex giống WinHex

    ban_sua = img.sao_chep("da_sua.img")   # bản sao ghi được, dùng cho --repair / --corrupt
    ban_sua.ghi_u16(0x0E, 32)
"""
import mmap
import os
import shutil
import struct


class AnhDia:
    def __init__(self, duong_dan, ghi=False):
        self.duong_dan = duong_dan
        self.ghi_duoc = ghi
        self._f = open(duong_dan, "r+b" if ghi else "rb")
        self.kich_thuoc = os.path.getsize(duong_dan)
        self._m = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_WRITE if ghi else mmap.ACCESS_READ)

    def dong(self):
        if self.ghi_duoc:
            self._m.flush()
        self._m.close()
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.dong()

    # ---------- đọc ----------
    def doc(self, offset, n):
        if offset < 0 or n < 0 or offset + n > self.kich_thuoc:
            raise ValueError(f"đọc ngoài ảnh: offset {offset:#x}, {n} byte")
        return bytes(self._m[offset:offset + n])

    def _s(self, fmt, offset):
        return struct.unpack_from(fmt, self.doc(offset, struct.calcsize(fmt)))[0]

    def u8(self, o):    return self._s("<B", o)
    def u16(self, o):   return self._s("<H", o)
    def u32(self, o):   return self._s("<I", o)
    def u64(self, o):   return self._s("<Q", o)
    def s8(self, o):    return self._s("<b", o)
    def u16be(self, o): return self._s(">H", o)
    def u32be(self, o): return self._s(">I", o)
    def u64be(self, o): return self._s(">Q", o)

    def so(self, offset, n, signed=False):
        """Số nguyên little-endian n byte (1–8), dùng cho runlist NTFS."""
        return int.from_bytes(self.doc(offset, n), "little", signed=signed)

    def tim(self, mau: bytes, bat_dau=0, ket_thuc=None, buoc=1):
        """Tìm chuỗi byte; buoc > 1 chỉ nhận vị trí là bội số của buoc (vd. 4096: đầu cluster)."""
        ket_thuc = self.kich_thuoc if ket_thuc is None else ket_thuc
        o = bat_dau
        while True:
            o = self._m.find(mau, o, ket_thuc)
            if o < 0:
                return -1
            if o % buoc == 0:
                return o
            o += 1

    def hexdump(self, offset, n=0x100):
        dong = []
        for o in range(offset - offset % 16, offset + n, 16):
            b = self.doc(o, min(16, self.kich_thuoc - o))
            hx = " ".join(f"{x:02X}" for x in b)
            asc = "".join(chr(x) if 32 <= x < 127 else "." for x in b)
            dong.append(f"{o:08X}  {hx:<47}  {asc}")
        return "\n".join(dong)

    # ---------- ghi (chỉ trên bản sao) ----------
    def sao_chep(self, dich):
        """Tạo bản sao ghi được; ảnh gốc không bao giờ bị sửa."""
        if os.path.abspath(dich) == os.path.abspath(self.duong_dan):
            raise ValueError("không được ghi đè ảnh đầu vào")
        shutil.copyfile(self.duong_dan, dich)
        return AnhDia(dich, ghi=True)

    def ghi(self, offset, data: bytes):
        if not self.ghi_duoc:
            raise PermissionError("ảnh đang mở chỉ đọc — dùng sao_chep() trước")
        if offset < 0 or offset + len(data) > self.kich_thuoc:
            raise ValueError(f"ghi ngoài ảnh: offset {offset:#x}")
        self._m[offset:offset + len(data)] = data

    def ghi_u8(self, o, v):  self.ghi(o, struct.pack("<B", v))
    def ghi_u16(self, o, v): self.ghi(o, struct.pack("<H", v))
    def ghi_u32(self, o, v): self.ghi(o, struct.pack("<I", v))
    def ghi_u64(self, o, v): self.ghi(o, struct.pack("<Q", v))
