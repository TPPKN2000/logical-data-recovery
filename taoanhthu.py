#!/usr/bin/env python3
"""Tạo ảnh FAT32 thử (512 MB, cluster 4 KB) + hỏng theo tình huống 1/2/3, kèm đáp án.  Cần Pillow (chỉ để TẠO ẢNH THỬ).

  python tao_anh_thu.py <thu_muc> <seed>
"""
import hashlib, io, json, os, random, struct, sys
from PIL import Image

BPS, SPC, RSVD, NFAT, FATSZ = 512, 8, 32, 2, 1024
TOT = 512 * 1024 * 1024 // BPS
CS = BPS * SPC
DATA_OFF = (RSVD + NFAT * FATSZ) * BPS


def tao_jpeg(rng, muc_tieu, **kw):
    w = int((muc_tieu / 1.15) ** 0.5) // 16 * 16
    im = Image.frombytes("RGB", (w, w), rng.randbytes(w * w * 3))
    b = io.BytesIO(); im.save(b, "JPEG", quality=kw.get("q", 85), optimize=kw.get("opt", False)); return b.getvalue()


def tao_png(rng, muc_tieu):
    w = int((muc_tieu / 3) ** 0.5)
    im = Image.frombytes("RGB", (w, w), rng.randbytes(w * w * 3))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def tao_pdf(rng, muc_tieu):
    return b"%PDF-1.4\n1 0 obj<</Length " + str(muc_tieu).encode() + b">>stream\n" + rng.randbytes(muc_tieu) + b"\nendstream\nendobj\ntrailer<<>>\n%%EOF\n"


def ten(rng, ext):
    return "%s%02d.%s" % (rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ"), rng.randint(0, 99), ext)


def dirent(name, attr, fc, size):
    if name in (".", ".."):
        n11 = name.ljust(11)
    else:
        base, _, ext = name.partition(".")
        n11 = base.ljust(8) + ext.ljust(3)
    return struct.pack("<11sBBBHHHHHHHI", n11.encode(), attr, 0, 0, 0x1234, 0x5678,
                       0x5678, fc >> 16, 0x1234, 0x5678, fc & 0xFFFF, size)


def tao(thu_muc, seed, big_opt=False):
    rng = random.Random(seed)
    os.makedirs(thu_muc, exist_ok=True)
    jpg_nho = tao_jpeg(rng, rng.randint(90000, 130000))
    jpg_lon = tao_jpeg(rng, rng.randint(260000, 400000), opt=big_opt)
    png = tao_png(rng, rng.randint(250000, 350000))
    pdf = tao_pdf(rng, rng.randint(100000, 250000))
    txt = (b"Hello FAT32 test %d\n" % seed) * rng.randint(8, 25)
    files = [(ten(rng, "JPG"), jpg_nho), (ten(rng, "PNG"), png), (ten(rng, "PDF"), pdf), (ten(rng, "TXT"), txt),
             (ten(rng, "JPG"), jpg_lon)]
    layout, cur = {}, 4
    fat = {0: 0x0FFFFFF8, 1: 0x0FFFFFFF, 2: 0x0FFFFFFF, 3: 0x0FFFFFFF}
    big_name = files[-1][0]
    gap_info = None
    for nm, d in files:
        n = -(-len(d) // CS)
        if nm == big_name:
            k = rng.randint(n // 4, n * 3 // 5); g = rng.randint(3, 40)
            runs = [(cur, k), (cur + k + g, n - k)]; gap_info = (cur + k, g)
            cur = cur + k + g + n - k
        else:
            runs = [(cur, n)]; cur += n + rng.randint(0, 3)
        layout[nm] = runs
    img = {}
    def w(off, b): img[off] = b
    bs = bytearray(512)
    bs[0:3] = b"\xeb\x58\x90"; bs[3:11] = b"mkfs.fat"
    struct.pack_into("<HBHBHHBHHHII", bs, 11, BPS, SPC, RSVD, NFAT, 0, 0, 0xF8, 0, 32, 64, 0, TOT)
    struct.pack_into("<IHHI", bs, 36, FATSZ, 0, 0, 2); struct.pack_into("<HH", bs, 48, 1, 6)
    bs[64] = 0x80; bs[66] = 0x29; struct.pack_into("<I", bs, 67, seed & 0xFFFFFFFF)
    bs[71:82] = b"NO NAME    "; bs[82:90] = b"FAT32   "; bs[510:512] = b"\x55\xaa"
    fsi = bytearray(512); struct.pack_into("<I", fsi, 0, 0x41615252); struct.pack_into("<III", fsi, 484, 0x61417272, 0, 0xFFFFFFFF)
    fsi[510:512] = b"\x55\xaa"
    root = dirent("DATA", 0x10, 3, 0)
    sub = dirent(".", 0x10, 3, 0) + dirent("..", 0x10, 0, 0)
    ents = {}
    for nm, d in files:
        runs = layout[nm]
        cl = [c for s, l in runs for c in range(s, s + l)]
        for a, b in zip(cl, cl[1:] + [None]): fat[a] = 0x0FFFFFFF if b is None else b
        ents[nm] = (len(sub), cl[0], len(d))
        sub += dirent(nm, 0x20, cl[0], len(d))
    # dữ liệu tập tin
    for nm, d in files:
        pos = 0
        for s, l in layout[nm]:
            chunk = d[pos:pos + l * CS]; pos += l * CS
            w(DATA_OFF + (s - 2) * CS, chunk)
    if gap_info:   # dữ liệu rác (ngẫu nhiên) vào khoảng trống
        w(DATA_OFF + (gap_info[0] - 2) * CS, rng.randbytes(gap_info[1] * CS))
    w(DATA_OFF, root); w(DATA_OFF + CS, sub)
    ftab = bytearray(FATSZ * BPS)
    for c, v in fat.items(): struct.pack_into("<I", ftab, 4 * c, v)
    def ghi_anh(path, hong=None):
        with open(path, "wb") as f:
            f.truncate(512 * 1024 * 1024)
            ws = dict(img)
            ws[0] = bytes(bs); ws[BPS] = bytes(fsi); ws[6 * BPS] = bytes(bs); ws[7 * BPS] = bytes(fsi)
            for i in range(NFAT):
                ws[RSVD * BPS + i * FATSZ * BPS] = bytes(ftab)
            if hong: hong(ws)
            for o in sorted(ws): f.seek(o); f.write(ws[o])
    sha = {nm: hashlib.sha256(d).hexdigest() for nm, d in files}
    ghi_anh(os.path.join(thu_muc, "clean.img"))
    def h1(ws):
        for base in (0, 6 * BPS):
            b = bytearray(ws[base]); b[0x0D] = 2; struct.pack_into("<H", b, 0x0E, 16); struct.pack_into("<I", b, 0x24, 1252); ws[base] = bytes(b)
    ghi_anh(os.path.join(thu_muc, "case1.img"), h1)
    muc2 = [files[0][0], files[2][0], files[3][0]]
    def h2(ws):
        b = bytearray(sub)
        for nm in muc2:
            o = ents[nm][0]; b[o + 20:o + 22] = b"\0\0"; b[o + 26:o + 28] = b"\0\0"
        ws[DATA_OFF + CS] = bytes(b)
    ghi_anh(os.path.join(thu_muc, "case2.img"), h2)
    def h3(ws):
        ft = bytearray(ftab)
        for s, l in layout[big_name]:
            for c in range(s, s + l): struct.pack_into("<I", ft, 4 * c, 0)
        for i in range(NFAT): ws[RSVD * BPS + i * FATSZ * BPS] = bytes(ft)
    ghi_anh(os.path.join(thu_muc, "case3.img"), h3)
    dap = {"sha": {"DATA/" + k: v for k, v in sha.items()}, "case2": ["DATA/" + n for n in muc2], "case3": ["DATA/" + big_name],
           "layout": {k: v for k, v in layout.items()}}
    json.dump(dap, open(os.path.join(thu_muc, "dap_an.json"), "w"), indent=1)
    return dap


if __name__ == "__main__":
    tao(sys.argv[1], int(sys.argv[2]))
