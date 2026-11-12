# Scenario 1 — Wrong boot sector parameters
import math
import utility as ut

SIGNATURE_FAT = b"\xF8\xFF\xFF\x0F\xFF\xFF\xFF\x0F"


def do_tim_tham_so_dung(img, log):
    bps = 512  # FAT32 tiêu chuẩn trên ảnh 512MB luôn dùng sector 512 byte

    # quét tìm chữ ký 8 byte của bảng FAT
    fat1_off = img.tim(SIGNATURE_FAT, bat_dau=512, buoc=512)
    if fat1_off < 0:
        raise ValueError("Không tìm thấy bảng FAT1!")

    fat2_off = img.tim(SIGNATURE_FAT, bat_dau=fat1_off + 512, buoc=512)
    if fat2_off < 0:
        raise ValueError("Không tìm thấy bảng FAT2!")
    
    # suy ra RsvdSecCnt và FATSz32 để tính data_offset (vị trí Cluster 2 - Thư mục gốc)
    rsvd = fat1_off // bps 
    fatsz = (fat2_off - fat1_off) // bps

    log.buoc("Tìm thấy bảng FAT1 và FAT2", gia_tri=f"FAT1 tại {fat1_off:#x}, FAT2 tại {fat2_off:#x}")
    log.quyet_dinh(f"Suy ra BPB_RsvdSecCnt = {rsvd}", offset=0x0E, gia_tri=rsvd)
    log.quyet_dinh(f"Suy ra BPB_FATSz32 = {fatsz}", offset=0x24, gia_tri=fatsz)

    # tính data_offset (vị trí Cluster 2 - Thư mục gốc)
    data_off = (rsvd + 2 * fatsz) * bps

    # đọc bảng FAT để chuẩn bị kiểm tra độ dài chuỗi cluster
    fat = ut.doc_bang_fat(img, fat1_off, fatsz, bps)

    # dò SecPerClus
    spc_dung = None
    for spc in (1, 2, 4, 8, 16, 32, 64):    # SecPerClus phải là lũy thừa của 2, tối đa 64
        cs = spc * bps
        # đọc thư mục Root thử với cluster_size = cs
        root_entries = ut.doc_muc_thu_muc(img, 2, data_off, cs)
        data_dir = next((e for e in root_entries if e["name"] == "DATA" and e["is_dir"]), None)
        if not data_dir:
            continue

        # thử đọc thư mục DATA
        data_entries = ut.doc_muc_thu_muc(img, data_dir["fc"], data_off, cs)
        files = [e for e in data_entries if not e["is_dir"] and e["size"] > 0]
        if not files:
            continue

        # Kiểm tra xem độ dài chuỗi cluster trong FAT có khớp với ceil(size / cs) không
        hop_le = True
        for f in files:
            seq = ut.lan_chuoi_fat(fat, f["fc"])
            so_clus_ky_vong = math.ceil(f["size"] / cs)
            if len(seq) != so_clus_ky_vong:
                hop_le = False
                break

        if hop_le:
            spc_dung = spc
            break

    if spc_dung is None:
        spc_dung = 8  # Giá trị mặc định chuẩn nếu không xác định được

    log.quyet_dinh(f"Suy ra BPB_SecPerClus = {spc_dung}", offset=0x0D, gia_tri=spc_dung)

    cs = spc_dung * bps
    return {
        "bps": bps,
        "spc": spc_dung,
        "rsvd": rsvd,
        "nfat": 2,
        "fatsz": fatsz,
        "root": 2,
        "cs": cs,
        "fat_off": fat1_off,
        "data_off": data_off,
        "fat": fat,
    }


def xu_ly(img, out, log):
    """Hàm chính xử lý khôi phục Case 1."""
    # dò tham số chuẩn
    p = do_tim_tham_so_dung(img, log)
    fat = p["fat"]

    # duyệt thư mục Root và DATA theo tham số chuẩn vừa tìm
    root_entries = ut.doc_muc_thu_muc(img, p["root"], p["data_off"], p["cs"])
    data_dir = next((e for e in root_entries if e["name"] == "DATA" and e["is_dir"]), None)
    if not data_dir:
        log.canh_bao("Không tìm thấy thư mục DATA!")
        return

    data_entries = ut.doc_muc_thu_muc(img, data_dir["fc"], p["data_off"], p["cs"])

    # trích xuất các tập tin ra thư mục output
    for e in data_entries:
        if not e["is_dir"]:
            # lần theo bảng FAT lấy toàn bộ cluster của tập tin
            seq = ut.lan_chuoi_fat(fat, e["fc"])
            data = ut.doc_du_lieu_file(img, seq, e["size"], p["data_off"], p["cs"])
            
            # lưu file ra thư mục kết quả
            duong_dan = f"DATA/{e['name']}"
            out.luu(duong_dan, data)
            log.buoc(f"Lưu tập tin {duong_dan}", gia_tri=f"{len(data)} bytes ({len(seq)} clusters)")