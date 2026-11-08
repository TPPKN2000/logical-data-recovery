"""PHẦN LÀM BÀI — FAT32.  Giải mã/phục hồi nằm trong fat32.py và jpegscan.py (chỉ dùng thư viện chuẩn)."""
import fat32


class BaiLam:
    def __init__(self, log):
        self.log = log

    # ------------------------------------------------------------------ --info
    def info(self, img):
        vol = fat32.chon_tham_so(img, self.log)
        files = [{"path": e["duong_dan"], "size": e["size"]} for e in vol.duyet() if not e["thu_muc"]]
        return {
            "fs": "fat32", "cluster_size": vol.cs, "bytes_per_sector": vol.bps,
            "sectors_per_cluster": vol.spc, "reserved_sectors": vol.rsvd, "fat_count": vol.nfat,
            "fat_size_sectors": vol.fatsz, "root_cluster": vol.root,
            "fat_offset": vol.fat_off, "data_offset": vol.data_off, "files": files,
        }

    def _chay(self, img, out, ten):
        vol = fat32.chon_tham_so(img, self.log)
        self.log.buoc(f"Tình huống {ten}: tham số dùng để trích xuất", gia_tri={
            "SecPerClus": vol.spc, "RsvdSecCnt": vol.rsvd, "FATSz32": vol.fatsz, "nguon": vol.nguon})
        kq = vol.phuc_hoi()
        for f in kq["tap_tin"]:
            out.luu(f["path"], f["data"])
            self.log.buoc(f"Lưu {f['path']}", gia_tri=f"{len(f['data'])} byte ({f['loai']})")
        return vol, kq

    def case1(self, img, out):
        self._chay(img, out, "1")

    def case2(self, img, out):
        self._chay(img, out, "2")

    def case3(self, img, out):
        self._chay(img, out, "3")

    def case_ext(self, img, out):
        raise NotImplementedError("case_ext")

    # --------------------------------------------------------------- cộng điểm
    def repair(self, img, case, anh_moi):
        case = str(case)
        vol = fat32.chon_tham_so(img, self.log)
        kq = vol.phuc_hoi()
        ban = img.sao_chep(anh_moi)
        try:
            if case == "1" and vol.nguon != "bpb":
                bk = img.u16(0x32)
                if bk in (0, 0xFFFF) or (bk + 1) * vol.bps > img.kich_thuoc:
                    bk = 6
                for base in (0, bk * vol.bps):
                    ban.ghi_u8(base + 0x0D, vol.spc)
                    ban.ghi_u16(base + 0x0E, vol.rsvd)
                    ban.ghi_u32(base + 0x24, vol.fatsz)
                    self.log.buoc("Sửa boot sector", offset=base, gia_tri=(vol.spc, vol.rsvd, vol.fatsz))
            da_sua_fat = False
            for s in kq["sua"]:
                if s["loai"] == "fc":
                    ban.ghi_u16(s["off"] + 0x14, s["fc"] >> 16)
                    ban.ghi_u16(s["off"] + 0x1A, s["fc"] & 0xFFFF)
                    self.log.buoc(f"Sửa first cluster của {s['path']}", offset=s["off"] + 0x1A, gia_tri=s["fc"])
                else:
                    seq = s["seq"]
                    for i in range(vol.nfat):
                        base = vol.fat_off + i * vol.fatsz * vol.bps
                        for a, b in zip(seq, seq[1:] + [None]):
                            ban.ghi_u32(base + 4 * a, 0x0FFFFFFF if b is None else b)
                    da_sua_fat = True
                    self.log.buoc(f"Dựng lại chuỗi FAT của {s['path']}", gia_tri=f"{len(seq)} cụm")
            if da_sua_fat:     # cập nhật số cụm trống trong FSInfo
                fi = img.u16(0x30) * vol.bps
                if img.u32(fi) == 0x41615252 and img.u32(fi + 0x1E4) == 0x61417272:
                    import struct
                    cnt = vol.nclus + 2
                    fat = struct.unpack("<%dI" % cnt, ban.doc(vol.fat_off, cnt * 4))
                    ban.ghi_u32(fi + 0x1E8, sum(1 for c in range(2, cnt) if fat[c] & 0x0FFFFFFF == 0))
        finally:
            ban.dong()

    def corrupt(self, img, dac_ta, anh_hong):
        raise NotImplementedError("corrupt")
