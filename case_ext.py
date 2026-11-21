# Scenario Extension — ext-root (Wrong root directory pointer)
import utility as ut

# --corrupt: Làm hỏng trường BPB_RootClus ở Sector 0 và Sector 6 theo đặc tả.
def lam_hong_anh(img, dac_ta, anh_hong, log):
    bps = img.u16(0x0B)
    off0 = dac_ta.get("offset_sector0", 0x2C)
    off6 = dac_ta.get("offset_sector6", 6 * bps + 0x2C)
    length = dac_ta.get("length", 4)
    gia_tri_hong = dac_ta.get("gia_tri_hong", 0)

    ban_sua = img.sao_chep(anh_hong)
    # Làm hỏng Sector 0 (Boot Sector chính)
    ban_sua.ghi_u32(off0, gia_tri_hong)

    # Làm hỏng Sector 6 (Backup Boot Sector)
    ban_sua.ghi_u32(off6, gia_tri_hong)
    ban_sua.dong()

    log.quyet_dinh(f"Đã làm hỏng BPB_RootClus thành {gia_tri_hong:#x} tại Sector 0 và Sector 6: {anh_hong}")

    return [
        {"offset": off0, "length": length, "cau_truc": "BPB_RootClus (sector 0)"},
        {"offset": off6, "length": length, "cau_truc": "BPB_RootClus (sector 6)"}
    ]

# quét tìm cluster Thư mục gốc (chứa thư mục DATA, không có entry . và ..)
def tim_thu_muc_goc(img, p, log):
    tong_so_cluster = (img.kich_thuoc - p["data_off"]) // p["cs"]
    gioi_han = min(tong_so_cluster + 2, 500)

    for c in range(2, gioi_han):
        d = ut.doc_cluster(img, c, p["data_off"], p["cs"])
        # thư mục gốc FAT32 không bao giờ bắt đầu bằng entry '.'
        if d.startswith(b"."):
            continue

        co_data = False
        for i in range(0, len(d), 32):
            e = d[i:i + 32]
            if e[0] == 0x00:
                break
            if e[0] == 0xE5 or e[0x0B] == 0x0F:
                continue
            raw_name = e[0:8].decode("latin1", errors="replace").strip()
            is_dir = bool(e[0x0B] & 0x10)
            if raw_name == "DATA" and is_dir:
                co_data = True
                break

        if co_data:
            log.quyet_dinh(f"Tìm thấy Thư mục gốc tại Cluster {c} (chứa thư mục con DATA)", offset=0x2C, gia_tri=c)
            return c

    log.canh_bao("Không tìm thấy Thư mục gốc!")
    return None

# --case ext: Tự tìm thư mục gốc, khôi phục toàn bộ tập tin.
def xu_ly(img, out, log):
    p = ut.doc_bpb(img)
    fat = ut.doc_bang_fat(img, p["fat_off"], p["fatsz"], p["bps"])

    root_clus = tim_thu_muc_goc(img, p, log)
    if not root_clus:
        return

    root_entries = ut.doc_muc_thu_muc(img, root_clus, p["data_off"], p["cs"])
    data_dir = next((e for e in root_entries if e["name"] == "DATA" and e["is_dir"]), None)
    if not data_dir:
        log.canh_bao("Không tìm thấy thư mục DATA trong thư mục gốc!")
        return

    data_entries = ut.doc_muc_thu_muc(img, data_dir["fc"], p["data_off"], p["cs"])
    for e in data_entries:
        if not e["is_dir"]:
            seq = ut.lan_chuoi_fat(fat, e["fc"])
            data = ut.doc_du_lieu_file(img, seq, e["size"], p["data_off"], p["cs"])
            out.luu(f"DATA/{e['name']}", data)
            log.buoc(f"Lưu tập tin khôi phục DATA/{e['name']}", gia_tri=f"{len(data)} bytes")


# --repair: Sửa lại BPB_RootClus đúng trên Sector 0 và Sector 6.
def sua_anh(img, anh_moi, log):
    p = ut.doc_bpb(img)
    root_clus = tim_thu_muc_goc(img, p, log)
    if not root_clus:
        return

    bps = p["bps"]
    ban_sua = img.sao_chep(anh_moi)
    ban_sua.ghi_u32(0x2C, root_clus)
    bk_off = 6 * bps + 0x2C
    ban_sua.ghi_u32(bk_off, root_clus)
    ban_sua.dong()

    log.quyet_dinh(f"Đã sửa BPB_RootClus = {root_clus} tại Sector 0 và Sector 6: {anh_moi}")
