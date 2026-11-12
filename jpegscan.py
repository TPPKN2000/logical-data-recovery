"""
1. Phân tích Header JPEG (kích thước ảnh, bảng Huffman, số khối MCU).
2. Giải mã dòng bit nén Huffman (Entropy decoding) để đếm số khối MCU hợp lệ.
3. Xác nhận một cách ghép mảnh có tạo ra ảnh JPEG giải mã trơn tru tới marker EOI (FF D9) hay không.

cấu trúc jpeg
┌─────────┬──────────────┬──────────────┬──────────────┬──────────────────────────┬─────────┐
│   SOI   │     DHT      │     SOF0     │     SOS      │   DÒNG BIT NÉN HUFFMAN   │   EOI   │
│ (FF D8) │   (FF C4)    │   (FF C0)    │   (FF DA)    │    (Dữ liệu các pixel)   │ (FF D9) │
└─────────┴──────────────┴──────────────┴──────────────┴──────────────────────────┴─────────┘
  Bắt đầu    Bảng Huffman   Kích thước    Bắt đầu dữ liệu                          Kết thúc
"""

from bisect import bisect_right


class LoiGiaiMa(Exception):
    # ghép sai 
    pass


class ThongTinJpeg:
    def __init__(self):
        self.ho_tro = False     # True nếu ảnh là chuẩn JPEG Baseline tuần tự (SOF0)
        self.ly_do = ""         # dùng để hỗ trợ log
        self.scan_start = 0     # (ngay sau SOS)
        self.ri = 0             # khoảng cách lặp lại của marker Restart (DRI)
        self.rong = 0          
        self.cao = 0          
        self.mcus = 0           # số khối MCU cần giải mã trong toàn bộ bức ảnh
        self.khoi = []          # cấu trúc các khối thành phần (Y, Cb, Cr) trong 1 MCU
        self.ncomp = 0          # số thành phần màu (thường là 3: Y, Cb, Cr)


def _tao_bang_huffman(counts, vals): # counts: số lượng mã có độ dài từ 1 đến 16 bit, vals: các giá trị tương ứng với các mã
    maxcode = [-1] * 18 # dùng để 
    mincode = [0] * 18  
    valptr = [0] * 18   
    code = 0            
    k = 0               

    for l in range(1, 17):
        valptr[l] = k
        mincode[l] = code
        c = counts[l - 1]
        code += c
        k += c
        maxcode[l] = code - 1 if c else -1
        code <<= 1 # dịch trái 1 bit
    return (mincode, maxcode, valptr, vals)

# phân tích phần đầu ảnh JPEG (SOI … SOS)
def phan_tich_dau(buf):
    tt = ThongTinJpeg()
    n = len(buf)

    # kiểm tra 2 byte đầu tiên phải là SOI (0xFFD8)
    if buf[:2] != b"\xff\xd8":
        tt.ly_do = "Không tìm thấy marker SOI (FF D8)"
        return tt

    dht = {}
    sof = None
    p = 2

    # duyệt qua từng Marker trong Header
    while p + 4 <= n:
        if buf[p] != 0xFF:
            tt.ly_do = f"Marker không hợp lệ tại vị trí {p}"
            return tt
        m = buf[p + 1]

        # bỏ qua các byte 0xFF
        if m == 0xFF:
            p += 1
            continue
        # bỏ qua các marker độc lập không có dữ liệu kèm theo (TEM, RST0-RST7)
        if m == 0x01 or 0xD0 <= m <= 0xD8:
            p += 2
            continue
        # nếu gặp EOI trước SOS -> lỗi
        if m == 0xD9:
            tt.ly_do = "Gặp EOI trước khi có dữ liệu SOS"
            return tt

        # độ dài đoạn dữ liệu của marker (2 byte tiếp theo, Big-Endian)
        L = (buf[p + 2] << 8) | buf[p + 3]
        if p + 2 + L > n:
            tt.ly_do = "Phần đầu ảnh bị cắt ngắn"
            return tt

        seg = buf[p + 4:p + 2 + L]

        # DHT (0xFFC4): Định nghĩa bảng Huffman
        if m == 0xC4:
            q = 0
            while q + 17 <= len(seg):
                tc_th = seg[q]                      # 4 bit cao: loại bảng (0=DC, 1=AC); 4 bit thấp: ID bảng
                counts = list(seg[q + 1:q + 17])   # 16 byte số lượng mã từ 1 đến 16 bit
                tong = sum(counts)
                vals = list(seg[q + 17:q + 17 + tong])
                dht[(tc_th >> 4, tc_th & 15)] = _tao_bang_huffman(counts, vals)
                q += 17 + tong

        # SOF0 / SOF1 (0xFFC0, 0xFFC1): Kích thước và thông số khung hình
        elif m in (0xC0, 0xC1):
            if len(seg) < 6 or seg[0] != 8:        # seg[0] là precision (phải là 8-bit)
                tt.ly_do = "Độ chính xác mẫu không hỗ trợ (khác 8-bit)"
                return tt
            cao = (seg[1] << 8) | seg[2]
            rong = (seg[3] << 8) | seg[4]
            nf = seg[5]                            # Số thành phần màu (3 cho YCbCr)
            comps = []
            for i in range(nf):
                cid = seg[6 + 3 * i]
                hv = seg[7 + 3 * i]                # Hệ số lấy mẫu ngang (H) và dọc (V)
                comps.append((cid, hv >> 4, hv & 15))
            sof = (cao, rong, comps)

        # Từ chối các định dạng JPEG Progressive hoặc Lossless phức tạp
        elif m in (0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            tt.ly_do = f"Không hỗ trợ JPEG Progressive/Lossless (SOF {m:02X})"
            return tt

        # --- Marker DRI (0xFFDD): Định nghĩa chu kỳ Restart Interval ---
        elif m == 0xDD:
            tt.ri = (seg[0] << 8) | seg[1]

        # --- Marker SOS (0xFFDA): Bắt đầu dòng dữ liệu quét (Start of Scan) ---
        elif m == 0xDA:
            if sof is None:
                tt.ly_do = "Gặp SOS trước SOF"
                return tt
            cao, rong, comps = sof
            ns = seg[0]
            if ns != len(comps):
                tt.ly_do = "Quét không đan xen (Non-interleaved)"
                return tt

            idx = {c[0]: i for i, c in enumerate(comps)}
            khoi = []
            hmax = max(c[1] for c in comps)
            vmax = max(c[2] for c in comps)

            # Ghép từng thành phần màu với bảng Huffman DC/AC tương ứng
            for i in range(ns):
                cid = seg[1 + 2 * i]
                td_ta = seg[2 + 2 * i]
                if cid not in idx or (0, td_ta >> 4) not in dht or (1, td_ta & 15) not in dht:
                    tt.ly_do = "Thiếu bảng Huffman cho kênh màu"
                    return tt
                ci = idx[cid]
                _, h, v = comps[ci]
                nb = 1 if ns == 1 else h * v
                for _ in range(nb):
                    khoi.append((ci, dht[(0, td_ta >> 4)], dht[(1, td_ta & 15)]))

            # Tính toán tổng số khối MCU của toàn bộ bức ảnh
            if ns == 1:
                mx = -(-rong // 8)
                my = -(-cao // 8)
            else:
                mx = -(-rong // (8 * hmax))
                my = -(-cao // (8 * vmax))

            tt.ho_tro = True
            tt.scan_start = p + 2 + L
            tt.rong, tt.cao = rong, cao
            tt.mcus = mx * my                      # Tổng số khối MCU bắt buộc phải giải mã đủ
            tt.khoi = khoi
            tt.ncomp = ns
            return tt

        p += 2 + L

    tt.ly_do = "Không tìm thấy marker SOS trong phần đầu ảnh"
    return tt


class _BoDocBit:
    """Lớp đọc từng bit từ luồng nhị phân, tự động xử lý quy tắc Byte-Stuffing (FF 00 -> FF)."""
    __slots__ = ("buf", "n", "pos", "bits", "nb", "pad")

    def __init__(self, buf, pos, bits, nb, pad):
        self.buf = buf
        self.n = len(buf)
        self.pos = pos        # Con trỏ vị trí byte trong buf
        self.bits = bits      # Bộ đệm bit hiện tại
        self.nb = nb          # Số bit hợp lệ đang có trong self.bits
        self.pad = pad

    def nap_bit(self):
        """Nạp thêm byte từ bộ đệm vào self.bits cho đến khi có ít nhất 24 bits."""
        buf, pos, n, bits, nb, pad = self.buf, self.pos, self.n, self.bits, self.nb, self.pad
        while nb <= 24:
            if pos >= n:
                raise LoiGiaiMa("Hết dữ liệu giữa chừng")
            b = buf[pos]
            if b == 0xFF:
                if pos + 1 >= n:
                    raise LoiGiaiMa("Hết dữ liệu ngay sau byte FF")
                x = buf[pos + 1]
                if x == 0:
                    pos += 2          # Bỏ qua byte độn 0x00 (Byte-stuffing: FF 00 -> chỉ lấy FF)
                elif 0xD0 <= x <= 0xD7 or x == 0xD9:
                    bits <<= 8        # Gặp marker thật (RST hoặc EOI): không nuốt marker, đệm bit 0
                    nb += 8
                    pad += 8
                    continue
                else:
                    raise LoiGiaiMa(f"Gặp marker bất thường FF{x:02X} trong dòng dữ liệu nén")
            else:
                pos += 1
            bits = (bits << 8) | b
            nb += 8
        self.pos, self.bits, self.nb, self.pad = pos, bits, nb, pad

    def giai_ma_huffman(self, bang):
        """Đọc từng bit và đối chiếu với cây Huffman để lấy ra giá trị symbol."""
        mincode, maxcode, valptr, vals = bang
        if self.nb < 16:
            self.nap_bit()
        bits, nb = self.bits, self.nb
        code = 0
        for l in range(1, 17):
            code = (code << 1) | ((bits >> (nb - l)) & 1)
            if code <= maxcode[l]:
                self.nb = nb - l
                self.bits = bits & ((1 << self.nb) - 1)
                return vals[valptr[l] + code - mincode[l]]
        raise LoiGiaiMa("Mã Huffman không hợp lệ (sai cây tra cứu)")

    def doc_n_bit(self, n):
        """Đọc chính xác n bit tiếp theo."""
        if self.nb < n:
            self.nap_bit()
        nb = self.nb - n
        v = self.bits >> nb
        self.bits &= (1 << nb) - 1
        self.nb = nb
        return v


def giai_ma(buf, tt, trang_thai=None, snaps=None):
    """Giải mã toàn bộ các khối MCU của ảnh.
    
    - buf: Toàn bộ dữ liệu ảnh sau khi đã ghép thử 2 mảnh.
    - tt: Đối tượng ThongTinJpeg chứa thông số đã phân tích từ header.
    - trang_thai: Cho phép tiếp tục giải mã từ một Snapshot đã lưu (tăng tốc độ).
    - snaps: Danh sách lưu lại các ảnh chụp trạng thái tại đầu mỗi MCU.
    
    Trả về:
      ("ok", vi_tri_ngay_sau_EOI) nếu ảnh hoàn toàn hợp lệ 100%.
      ("loi", vi_tri_loi) nếu cách ghép bị sai bitstream.
    """
    if trang_thai is None:
        trang_thai = (tt.scan_start, 0, 0, 0, 0, tuple([0] * tt.ncomp), 0)
    pos, bits, nb, pad, mcu, preds, rst = trang_thai
    d = _BoDocBit(buf, pos, bits, nb, pad)
    preds = list(preds)
    khoi, total, ri = tt.khoi, tt.mcus, tt.ri

    try:
        while mcu < total:
            # Lưu ảnh chụp trạng thái để có thể tái sử dụng cho các lần thử sau
            if snaps is not None:
                snaps.append((d.pos, d.bits, d.nb, d.pad, mcu, tuple(preds), rst))

            # Duyệt qua từng khối 8x8 trong MCU
            for ci, dct, act in khoi:
                # 1. Giải mã hệ số DC (Độ sáng trung bình)
                t = d.giai_ma_huffman(dct)
                if t > 11:
                    raise LoiGiaiMa("Category DC vượt giới hạn cho phép (>11)")
                if t:
                    v = d.doc_n_bit(t)
                    if v < (1 << (t - 1)):
                        v -= (1 << t) - 1
                    preds[ci] += v     # Cộng dồn vi sai DC
                    if preds[ci] > 2100 or preds[ci] < -2100:
                        raise LoiGiaiMa("Hệ số DC vượt ngưỡng pixel bình thường")

                # 2. Giải mã 63 hệ số AC (Tần số chi tiết)
                k = 1
                while k < 64:
                    rs = d.giai_ma_huffman(act)
                    sz = rs & 15       # Số bit biên độ
                    if sz == 0:
                        if rs == 0xF0: # ZRL: Chuỗi 16 số 0 liên tiếp
                            k += 16
                            continue
                        break          # EOB (End of Block): Toàn bộ các hệ số AC còn lại đều bằng 0
                    k += rs >> 4       # Nhảy qua số lượng số 0 (Run-length)
                    if k > 63:
                        raise LoiGiaiMa("Số lượng hệ số AC vượt quá 63 trong khối 8x8")
                    d.doc_n_bit(sz)
                    k += 1
                if k > 64:
                    raise LoiGiaiMa("ZRL vượt quá kích thước khối")

            mcu += 1
            rst += 1

            # Xử lý marker Restart (RST0-RST7) nếu file có cài đặt DRI
            if ri and rst == ri and mcu < total:
                if d.nb < d.pad or d.nb - d.pad >= 8:
                    raise LoiGiaiMa("Dữ liệu dư thừa trước marker RST")
                d.bits = 0
                d.nb = 0
                d.pad = 0
                if d.buf[d.pos] != 0xFF or not (0xD0 <= d.buf[d.pos + 1] <= 0xD7):
                    raise LoiGiaiMa("Thiếu marker RST theo chu kỳ DRI")
                d.pos += 2
                preds = [0] * len(preds)
                rst = 0

        # Kiểm tra tính toàn vẹn ở đuôi file sau khi giải mã xong MCU cuối cùng:
        if d.nb < d.pad or d.nb - d.pad >= 8:
            raise LoiGiaiMa("Dữ liệu thừa/thiếu bit ở cuối dòng quét")
        # Byte tiếp theo BẮT BUỘC phải là marker EOI (0xFFD9)
        if d.buf[d.pos:d.pos + 2] != b"\xff\xd9":
            raise LoiGiaiMa("Không tìm thấy marker EOI (FF D9) ngay sau MCU cuối")

        # Thành công mỹ mãn! Trả về vị trí kết thúc file (ngay sau byte FF D9)
        return ("ok", d.pos + 2)

    except (LoiGiaiMa, IndexError):
        return ("loi", d.pos)


def vi_tri_snapshot(snaps_pos, bien):
    """Tìm chỉ số ảnh chụp cuối cùng có vị trí byte <= biên cắt."""
    return bisect_right(snaps_pos, bien) - 1