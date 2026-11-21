# Scenario 1 — Wrong boot sector parameters
import math
import utility as ut

SIGNATURE_FAT = b"\xF8\xFF\xFF\x0F\xFF\xFF\xFF\x0F"


def do_tim_tham_so_dung(img, log):
    # đọc các trường không bị hỏng từ Boot sector
    bps = img.u16(0x0B)
    nfat = img.u8(0x10)
    root_clus = img.u32(0x2C)

    # quét tìm chữ ký 8 byte của bảng FAT
    fat1_off = img.tim(SIGNATURE_FAT, bat_dau=bps, buoc=bps)
    if fat1_off < 0:
        raise ValueError("Không tìm thấy bảng FAT1")

    fat2_off = img.tim(SIGNATURE_FAT, bat_dau=fat1_off + bps, buoc=bps)
    if fat2_off < 0:
        raise ValueError("Không tìm thấy bảng FAT2")
    
    # RsvdSecCnt và FATSz32 từ vị trí FAT1 và FAT2
    rsvd = fat1_off // bps 
    fatsz = (fat2_off - fat1_off) // bps

    log.buoc("Tìm thấy bảng FAT1 và FAT2", gia_tri=f"FAT1 tại {fat1_off:#x}, FAT2 tại {fat2_off:#x}")
    log.quyet_dinh(f"Suy ra BPB_RsvdSecCnt = {rsvd}", offset=0x0E, gia_tri=rsvd)
    log.quyet_dinh(f"Suy ra BPB_FATSz32 = {fatsz}", offset=0x24, gia_tri=fatsz)

    # tính data_offset (vị trí bắt đầu vùng chứa cluster dữ liệu)
    data_off = (rsvd + nfat * fatsz) * bps

    # đọc bảng FAT để chuẩn bị kiểm tra độ dài chuỗi cluster
    fat = ut.doc_bang_fat(img, fat1_off, fatsz, bps)

    # dò SecPerClus bằng cách đối chiếu độ dài chuỗi cluster
    spc_dung = None
    for spc in (1, 2, 4, 8, 16, 32, 64):
        cs = spc * bps
        # đọc thư mục Root
        root_entries = ut.doc_muc_thu_muc(img, root_clus, data_off, cs)
        data_dir = next((e for e in root_entries if e["name"] == "DATA" and e["is_dir"]), None)
        if not data_dir:
            continue

        # đọc thư mục DATA
        data_entries = ut.doc_muc_thu_muc(img, data_dir["fc"], data_off, cs)
        files = [e for e in data_entries if not e["is_dir"] and e["size"] > 0]
        if not files:
            continue

        # kiểm tra khớp giữa chuỗi FAT và kích thước file
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
        raise ValueError("Không thể suy luận được SecPerClus")

    log.quyet_dinh(f"Suy ra BPB_SecPerClus = {spc_dung}", offset=0x0D, gia_tri=spc_dung)

    cs = spc_dung * bps
    return {
        "bps": bps,
        "spc": spc_dung,
        "rsvd": rsvd,
        "nfat": nfat,
        "fatsz": fatsz,
        "root": root_clus,
        "cs": cs,
        "fat_off": fat1_off,
        "data_off": data_off,
        "fat": fat,
    }

def xu_ly(img, out, log):
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


def sua_anh(img, anh_moi, log):
    p = do_tim_tham_so_dung(img, log)
    ban_sua = img.sao_chep(anh_moi)
    bps = p["bps"]
    spc = p["spc"]
    rsvd = p["rsvd"]
    fatsz = p["fatsz"]

    # Sector 0: Boot Sector chính
    ban_sua.ghi_u8(0x0D, spc)
    ban_sua.ghi_u16(0x0E, rsvd)
    ban_sua.ghi_u32(0x24, fatsz)

    # Sector 6: Backup Boot Sector (chuẩn FAT32 sao lưu tại sector 6)
    bk_off = 6 * bps
    ban_sua.ghi_u8(bk_off + 0x0D, spc)
    ban_sua.ghi_u16(bk_off + 0x0E, rsvd)
    ban_sua.ghi_u32(bk_off + 0x24, fatsz)

    ban_sua.dong()
    log.quyet_dinh(f"Đã sửa Boot Sector và Backup Boot Sector thành công: {anh_moi}")