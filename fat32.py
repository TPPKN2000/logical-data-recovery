"""Giải mã FAT32 từ byte và các thuật toán phục hồi cho 3 tình huống.

Không có offset/giá trị nào gắn với ảnh cụ thể: mọi tham số được đọc hoặc suy ra từ nội dung ảnh.
"""
import struct
from bisect import bisect_right
from itertools import permutations
from math import ceil

import jpegscan

MASK = 0x0FFFFFFF
EOC_MIN = 0x0FFFFFF8
KY_TU_CAM = set(b'"*+,/:;<=>?[\\]|')


class LoiFat(Exception):
    pass


def _lfn_sum(n11):
    s = 0
    for b in n11:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


# ======================================================================= khối lượng (volume)
class Vol:
    def __init__(self, img, log, bps, spc, rsvd, nfat, fatsz, root, tot):
        self.img, self.log = img, log
        self.bps, self.spc, self.rsvd, self.nfat = bps, spc, rsvd, nfat
        self.fatsz, self.root, self.tot = fatsz, root, tot
        self.cs = bps * spc
        self.fat_off = rsvd * bps
        self.data_off = (rsvd + nfat * fatsz) * bps
        self.nclus = max(0, (tot - rsvd - nfat * fatsz) // spc)
        self._fat = None
        self.nguon = ""

    # ---- hợp lệ về hình thức
    def hop_le(self):
        if self.bps not in (512, 1024, 2048, 4096):
            return False
        if self.spc not in (1, 2, 4, 8, 16, 32, 64, 128):
            return False
        if self.rsvd < 1 or self.fatsz < 1 or self.nfat < 1:
            return False
        if self.nclus < 1 or self.data_off >= self.img.kich_thuoc:
            return False
        if self.data_off + self.nclus * self.cs > self.img.kich_thuoc:
            return False
        return True

    # ---- FAT
    def fat(self):
        if self._fat is None:
            cnt = min(self.fatsz * self.bps // 4, self.nclus + 2)
            if self.fat_off + cnt * 4 > self.img.kich_thuoc:
                raise LoiFat("FAT nằm ngoài ảnh")
            self._fat = struct.unpack("<%dI" % cnt, self.img.doc(self.fat_off, cnt * 4))
        return self._fat

    def chuoi(self, c):
        """Đi theo chuỗi FAT từ c. Trả (danh sách cluster, trạng thái)."""
        fat = self.fat()
        n = len(fat)
        seq, seen = [], set()
        while 2 <= c < n and c not in seen:
            seen.add(c)
            seq.append(c)
            nx = fat[c] & MASK
            if nx >= EOC_MIN:
                return seq, "eoc"
            if nx == 0:
                return seq, "trong"
            if nx == 0x0FFFFFF7:
                return seq, "hong"
            c = nx
        return seq, ("vong" if c in seen else "ngoai")

    def cluster_off(self, c):
        return self.data_off + (c - 2) * self.cs

    def doc_cluster(self, c):
        return self.img.doc(self.cluster_off(c), self.cs)

    def doc_chuoi(self, seq, size=None):
        d = b"".join(self.doc_cluster(c) for c in seq)
        return d if size is None else d[:size]

    # ---- thư mục
    def thu_muc(self, c):
        seq, _ = self.chuoi(c)
        if not seq:
            return []
        data = self.doc_chuoi(seq)
        out, lfn = [], []
        for i in range(0, len(data) - 31, 32):
            e = data[i:i + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5:
                lfn = []
                continue
            attr = e[11]
            if attr == 0x0F:
                lfn.append((e[0] & 0x1F, e[13], e[1:11] + e[14:26] + e[28:32]))
                continue
            if attr & 0x08:           # nhãn ổ đĩa
                lfn = []
                continue
            raw = bytes([0xE5]) + e[1:8] if e[0] == 0x05 else e[0:8]
            ten8 = raw.rstrip(b" ")
            ext = e[8:11].rstrip(b" ")
            if e[12] & 0x08:
                ten8 = ten8.lower()
            if e[12] & 0x10:
                ext = ext.lower()
            ten = ten8.decode("latin-1") + ("." + ext.decode("latin-1") if ext else "")
            if lfn and all(x[1] == _lfn_sum(e[0:11]) for x in lfn):
                chars = b"".join(x[2] for x in sorted(lfn))
                s = chars.decode("utf-16le", "replace")
                for stop in ("\x00", "\uffff"):
                    s = s.split(stop)[0]
                if s:
                    ten = s
            lfn = []
            thu_muc = bool(attr & 0x10)
            if thu_muc and ten in (".", ".."):
                continue
            hop_le = (attr & 0xC0) == 0 and e[0] > 0x20 and all(
                b >= 0x20 and b not in KY_TU_CAM for b in e[0:11])
            out.append({
                "ten": ten, "thu_muc": thu_muc, "attr": attr,
                "fc": (struct.unpack_from("<H", e, 20)[0] << 16) | struct.unpack_from("<H", e, 26)[0],
                "size": struct.unpack_from("<I", e, 28)[0],
                "off": self.cluster_off(seq[i // self.cs]) + i % self.cs,
                "hop_le": hop_le,
            })
        return out

    def duyet(self, toi_da=8):
        ket, da = [], set()

        def di(c, tien_to, sau):
            if c in da or sau > toi_da:
                return
            da.add(c)
            for e in self.thu_muc(c):
                e["duong_dan"] = tien_to + e["ten"]
                ket.append(e)
                if e["thu_muc"] and 2 <= e["fc"] <= self.nclus + 1:
                    di(e["fc"], e["duong_dan"] + "/", sau + 1)
        di(self.root, "", 0)
        return ket

    # ---- chấm điểm bộ tham số (dùng để chọn đúng/sai)
    def diem(self):
        try:
            if not self.hop_le():
                return -10 ** 6
            fat = self.fat()
            if (fat[0] & 0xFF) < 0xF0 or (fat[1] & MASK) < EOC_MIN:
                return -10 ** 6
            rseq, rst = self.chuoi(self.root)
            if rst != "eoc":
                return -10 ** 5
            tot = 0
            for e in self.duyet():
                if not e["hop_le"]:
                    tot -= 2
                    continue
                if e["thu_muc"]:
                    s, st = self.chuoi(e["fc"]) if 2 <= e["fc"] <= self.nclus + 1 else ([], "")
                    tot += 1 if st == "eoc" else -1
                    tot += 5 if s and self.dau_cham_dung(e["fc"]) else -5
                elif e["size"] > 0:
                    k = self.danh_gia(e)
                    tot += 2 if k == "tot" else (0 if k == "mo_coi" else -1)
            return tot
        except (LoiFat, ValueError, IndexError, struct.error):
            return -10 ** 6

    def dau_cham_dung(self, c):
        """Entry đầu của thư mục con phải là '.' có first cluster == chính cụm đó (kiểm tra rất chặt SecPerClus)."""
        d = self.doc_cluster(c)[:32]
        return d[0] == 0x2E and d[1] == 0x20 and bool(d[11] & 0x10) and \
            ((struct.unpack_from("<H", d, 20)[0] << 16) | struct.unpack_from("<H", d, 26)[0]) == c

    def danh_gia(self, e):
        """'rong' | 'tot' | 'mo_coi' (fc vô nghĩa) | 'dut' (fc có nghĩa nhưng chuỗi FAT sai)."""
        if e["size"] == 0:
            return "rong"
        need = ceil(e["size"] / self.cs)
        fc = e["fc"]
        if fc < 2 or fc > self.nclus + 1:
            return "mo_coi"
        seq, st = self.chuoi(fc)
        return "tot" if (st == "eoc" and len(seq) == need) else "dut"

    # ================================================================= phục hồi (TH 1,2,3)
    def phuc_hoi(self):
        """Trả về {"tap_tin": [{"path","data","loai"}], "sua": [thao tác sửa cho --repair]}."""
        log, cs, fat = self.log, self.cs, self.fat()
        ds = self.duyet()
        tap_tin = [e for e in ds if not e["thu_muc"]]
        tham_chieu = set(self.chuoi(self.root)[0])
        for e in ds:
            if e["thu_muc"] and 2 <= e["fc"] <= self.nclus + 1:
                tham_chieu.update(self.chuoi(e["fc"])[0])
        for e in tap_tin:
            e["loai"] = self.danh_gia(e)
            if e["loai"] == "tot":
                tham_chieu.update(self.chuoi(e["fc"])[0])
        for e in tap_tin:      # fc rơi vào chuỗi của tập tin khác => thực chất là mất liên kết
            if e["loai"] == "dut" and e["fc"] in tham_chieu:
                e["loai"] = "mo_coi"
        cap_phat = {c for c in range(2, len(fat)) if fat[c] & MASK != 0}
        log.buoc("Duyệt cây thư mục", gia_tri=f"{len(tap_tin)} tập tin; tốt="
                 f"{sum(e['loai']=='tot' for e in tap_tin)}, mồ côi={sum(e['loai']=='mo_coi' for e in tap_tin)}, "
                 f"đứt chuỗi={sum(e['loai']=='dut' for e in tap_tin)}")
        sua = []
        du_lieu = {}

        # ---- tập tin mất liên kết tên -> dữ liệu (Tình huống 2)
        mc = [e for e in tap_tin if e["loai"] == "mo_coi"]
        if mc:
            co_truoc = {fat[c] & MASK for c in cap_phat}
            dau = [c for c in sorted(cap_phat) if c not in tham_chieu and c not in co_truoc]
            ung = []
            for h in dau:
                seq, st = self.chuoi(h)
                if st == "eoc":
                    ung.append((h, seq))
            log.buoc("Ứng viên mồ côi (đã cấp phát trong FAT, không ai tham chiếu, không là mắt xích sau)",
                     gia_tri=[(h, len(s)) for h, s in ung])
            gan = self.ghep_mo_coi(mc, ung)
            for e, h, seq in gan:
                du_lieu[id(e)] = self.doc_chuoi(seq, e["size"])
                sua.append({"loai": "fc", "off": e["off"], "fc": h, "path": e["duong_dan"]})

        # ---- tập tin đứt chuỗi FAT (Tình huống 3)
        for e in [x for x in tap_tin if x["loai"] == "dut"]:
            seq = self.ghep_phan_manh(e, cap_phat)
            du_lieu[id(e)] = self.doc_chuoi(seq, e["size"])
            sua.append({"loai": "chuoi", "seq": seq, "path": e["duong_dan"]})

        ket = []
        for e in tap_tin:
            if e["loai"] == "rong":
                d = b""
            elif e["loai"] == "tot":
                d = self.doc_chuoi(self.chuoi(e["fc"])[0], e["size"])
            elif id(e) in du_lieu:
                d = du_lieu[id(e)]
            else:
                log.canh_bao(f"không phục hồi được {e['duong_dan']}")
                continue
            ket.append({"path": e["duong_dan"], "data": d, "loai": e["loai"], "size": e["size"], "e": e})
        return {"tap_tin": ket, "sua": sua}

    # ---- chấm điểm nội dung theo kiểu tập tin
    @staticmethod
    def diem_noi_dung(ten, data):
        ext = ten.rsplit(".", 1)[-1].upper() if "." in ten else ""
        d = 0
        if ext in ("JPG", "JPEG"):
            d += 3 if data[:3] == b"\xff\xd8\xff" else -3
            d += 3 if data[-2:] == b"\xff\xd9" else -2
        elif ext == "PNG":
            d += 3 if data[:8] == b"\x89PNG\r\n\x1a\n" else -3
            d += 3 if data[-12:] == b"\x00\x00\x00\x00IEND\xaeB`\x82" else -2
        elif ext == "PDF":
            d += 3 if data[:5] == b"%PDF-" else -3
            d += 3 if b"%%EOF" in data[-1100:] else -2
        else:
            ascii_ok = all(b in (9, 10, 13) or 32 <= b < 127 for b in data)
            d += 4 if ascii_ok else -4
        if ext not in ("JPG", "JPEG") and data[:3] == b"\xff\xd8\xff":
            d -= 5
        if ext != "PNG" and data[:4] == b"\x89PNG":
            d -= 5
        if ext != "PDF" and data[:5] == b"%PDF-":
            d -= 5
        return d

    def ghep_mo_coi(self, mc, ung):
        log, cs = self.log, self.cs
        if len(ung) < len(mc):
            log.canh_bao("số ứng viên mồ côi ít hơn số tập tin cần ghép", gia_tri=(len(ung), len(mc)))
        diem = {}
        for i, e in enumerate(mc):
            need = ceil(e["size"] / cs)
            for j, (h, seq) in enumerate(ung):
                s = 10 if len(seq) == need else -20
                s += self.diem_noi_dung(e["ten"], self.doc_chuoi(seq, e["size"]))
                diem[(i, j)] = s
        n_mc, n_ung = len(mc), len(ung)
        tot_nhat, cach = None, None
        if n_ung >= n_mc and n_ung <= 9:
            for hv in permutations(range(n_ung), n_mc):
                t = sum(diem[(i, hv[i])] for i in range(n_mc))
                if tot_nhat is None or t > tot_nhat:
                    tot_nhat, cach = t, hv
        else:   # tham lam khi quá nhiều ứng viên
            dung, cach_l = set(), []
            for i in range(n_mc):
                j = max((j for j in range(n_ung) if j not in dung), key=lambda j: diem[(i, j)], default=None)
                if j is None:
                    break
                dung.add(j)
                cach_l.append(j)
            cach = tuple(cach_l)
        kq = []
        for i, j in enumerate(cach or ()):
            e, (h, seq) = mc[i], ung[j]
            log.quyet_dinh(f"Ghép {e['duong_dan']} (size {e['size']}) với cụm đầu {h}",
                           tieu_chi=f"độ dài chuỗi FAT {len(seq)} == ceil(size/{cs}) = {ceil(e['size']/cs)}; "
                                    f"chữ ký/đuôi tệp khớp; điểm={diem[(i, j)]}", offset=self.cluster_off(h))
            kq.append((e, h, seq))
        return kq

    # ---- ghép mảnh JPEG theo nội dung
    def ghep_phan_manh(self, e, occ):
        log, cs = self.log, self.cs
        size, c0 = e["size"], e["fc"]
        need = ceil(size / cs)
        seq0, st = self.chuoi(c0)
        log.buoc(f"{e['duong_dan']}: chuỗi FAT từ cụm {c0} không khớp (trạng thái {st}, {len(seq0)} cụm)",
                 offset=e["off"], gia_tri=f"cần {need} cụm = ceil({size}/{cs}); thiếu {need - len(seq0)}")
        m = min(need + 140, self.nclus + 2 - c0)
        buf = b"".join(self.doc_cluster(c0 + i) for i in range(m))
        la_jpeg = buf[:3] == b"\xff\xd8\xff"
        lien_mach = list(range(c0, c0 + need))
        if not la_jpeg:
            log.canh_bao(f"{e['duong_dan']} không phải JPEG — giả định liền mạch")
            return lien_mach
        tail = size - (need - 1) * cs

        def hop_e(c):
            if c in occ:
                return False
            d = self.doc_cluster(c)
            return d[tail - 2:tail] == b"\xff\xd9" if tail >= 2 else True
        ecs = [c for c in range(c0 + need, min(c0 + need + 130, self.nclus + 2)) if hop_e(c)]
        log.buoc("Cụm cuối ứng viên (không bị chiếm, kết thúc bằng FF D9 đúng vị trí size)", gia_tri=ecs[:10])

        tt = jpegscan.phan_tich_dau(buf)
        if tt.ho_tro:
            snaps = []
            kq, p = jpegscan.giai_ma(buf, tt, None, snaps)
            if kq == "ok" and p == size:
                log.quyet_dinh("JPEG giải mã được liền mạch từ cụm đầu", gia_tri=p)
                return lien_mach
            log.buoc(f"Giải mã liền mạch dừng ở byte {p} của chuỗi liền kề (cụm thứ {p // cs} sau cụm đầu)",
                     offset=self.cluster_off(c0) + p, gia_tri=kq)
            kmax = min(need - 1, p // cs + 1)
            spos = [s[0] for s in snaps]
            thu = 0
            for ec in ecs:
                g = ec - (c0 + need - 1)
                for k in range(kmax, 0, -1):
                    s = ec - (need - k) + 1
                    if any(c in occ for c in range(s, ec + 1)) or any(c in occ for c in range(c0 + 1, c0 + k)):
                        continue
                    buf2 = (buf[:k * cs] + b"".join(self.doc_cluster(c) for c in range(s, ec + 1)))[:size]
                    i = bisect_right(spos, k * cs) - 1
                    thu += 1
                    kq2, p2 = jpegscan.giai_ma(buf2, tt, snaps[i] if i >= 0 else None, None)
                    if kq2 == "ok" and p2 == size:
                        seq = list(range(c0, c0 + k)) + list(range(s, ec + 1))
                        log.quyet_dinh(
                            f"Chuỗi vị trí của {e['duong_dan']}: mảnh 1 = cụm {c0}..{c0 + k - 1} ({k} cụm), "
                            f"mảnh 2 = cụm {s}..{ec} ({ec - s + 1} cụm), khoảng trống {g} cụm",
                            tieu_chi=f"giải mã Huffman đủ {tt.mcus} MCU và gặp EOI đúng vị trí {size} (đã thử {thu} cách)",
                            offset=self.cluster_off(s))
                        return seq
        else:
            log.canh_bao(f"không giải mã được cấu trúc JPEG: {tt.ly_do}; dùng heuristic")
        # heuristic: mảnh 1 = số cụm đầu có dữ liệu entropy hợp lệ; mảnh 2 kết thúc ở cụm FF D9 gần nhất
        kp = 1
        while kp < need - 1 and jpegscan.entropy_hop_le(self.doc_cluster(c0 + kp)):
            kp += 1
        if ecs:
            ec = ecs[0]
            s = ec - (need - kp) + 1
            log.canh_bao(f"heuristic: mảnh 1 = {kp} cụm, mảnh 2 bắt đầu ở cụm {s}")
            return list(range(c0, c0 + kp)) + list(range(s, ec + 1))
        return lien_mach


# ======================================================================= suy ra tham số boot
def tim_fat(img, bps, nfat, log):
    """Quét tìm đầu FAT: sector bắt đầu bằng entry0 = FFFFFFxF8 (media) và entry1 = EOC."""
    ket, o = [], bps
    gh = min(img.kich_thuoc, 64 * 1024 * 1024)
    while len(ket) < nfat:
        o = img.tim(b"\xff\xff\x0f", o, gh)
        if o < 0:
            break
        s = o - 1
        if s % bps == 0 and img.u8(s) >= 0xF0 and (img.u32(s + 4) & MASK) >= EOC_MIN:
            ket.append(s)
            log.buoc("Tìm thấy đầu bảng FAT (media + EOC)", offset=s, gia_tri=s // bps)
        o += 1
    return ket


def chon_tham_so(img, log):
    """Chọn tham số đúng: dùng BPB nếu nhất quán với cấu trúc, ngược lại suy ra từ FAT + thư mục."""
    bps = img.u16(0x0B)
    if bps not in (512, 1024, 2048, 4096):
        log.canh_bao("BPB_BytsPerSec bất thường, giả định 512", offset=0x0B, gia_tri=bps)
        bps = 512
    tot = img.u32(0x20) or img.u16(0x13)
    if tot == 0 or tot * bps > img.kich_thuoc:
        tot = img.kich_thuoc // bps
        log.quyet_dinh("BPB_TotSec32 sai/0: lấy theo kích thước ảnh", gia_tri=tot)
    nfat = img.u8(0x10)
    if nfat not in (1, 2):
        nfat = 2
    root = img.u32(0x2C)
    if root < 2:
        root = 2
    spc, rsvd, fz = img.u8(0x0D), img.u16(0x0E), img.u32(0x24)
    log.buoc("Đọc BPB_SecPerClus", offset=0x0D, gia_tri=spc)
    log.buoc("Đọc BPB_RsvdSecCnt", offset=0x0E, gia_tri=rsvd)
    log.buoc("Đọc BPB_FATSz32", offset=0x24, gia_tri=fz)
    v_bpb = Vol(img, log, bps, spc, rsvd, nfat, fz, root, tot)
    d_bpb = v_bpb.diem()
    log.buoc("Điểm nhất quán của tham số trong BPB", gia_tri=d_bpb)
    if d_bpb > 3:
        v_bpb.nguon = "bpb"
        log.quyet_dinh("BPB nhất quán với FAT/thư mục: dùng nguyên giá trị BPB")
        return v_bpb

    log.canh_bao("BPB không nhất quán — suy ra tham số từ cấu trúc còn nguyên")
    ket = tim_fat(img, bps, nfat, log)
    if not ket:
        raise LoiFat("không tìm thấy bảng FAT")
    rsvd2 = ket[0] // bps
    log.quyet_dinh("BPB_RsvdSecCnt = sector chứa FAT1", offset=0x0E, gia_tri=rsvd2)
    fz2 = (ket[1] - ket[0]) // bps if nfat == 2 and len(ket) == 2 else None
    if fz2:
        log.quyet_dinh("BPB_FATSz32 = khoảng cách FAT2 - FAT1 (sector)", offset=0x24, gia_tri=fz2)
    best, best_key = None, None
    for spc2 in (1, 2, 4, 8, 16, 32, 64, 128):
        f = fz2 or ceil((((tot - rsvd2) // spc2) + 2) * 4 / bps)
        v = Vol(img, log, bps, spc2, rsvd2, nfat, f, root, tot)
        d = v.diem()
        goi_y = ceil((v.nclus + 2) * 4 / bps) if v.nclus else 0
        log.buoc(f"Thử SecPerClus={spc2}", gia_tri=f"điểm={d}, FATSz kỳ vọng≈{goi_y}")
        key = (d, -abs(f - goi_y))
        if best_key is None or key > best_key:
            best, best_key = v, key
    if best_key[0] <= 0:
        raise LoiFat("không suy ra được SecPerClus")
    best.nguon = "suy_ra"
    log.quyet_dinh("BPB_SecPerClus được chọn vì mọi tập tin có số cụm trong chuỗi FAT = ceil(size/cluster) "
                   "và thư mục con đọc đúng", offset=0x0D, gia_tri=best.spc)
    return best
