import struct

MASK = 0x0FFFFFFF
EOC_MIN = 0x0FFFFFF8


# đọc boot sector
def doc_bpb(img):
    byts_per_sec = img.u16(0x0B)
    sec_per_clus = img.u8(0x0D)
    rsvd_sec_cnt = img.u16(0x0E)
    num_fats     = img.u8(0x10)
    fat_sz_32    = img.u32(0x24)
    root_clus    = img.u32(0x2C)

    cluster_size = byts_per_sec * sec_per_clus
    fat_offset   = rsvd_sec_cnt * byts_per_sec
    data_offset  = (rsvd_sec_cnt + num_fats * fat_sz_32) * byts_per_sec

    return {
        "bps": byts_per_sec,        # số byte mỗi sector
        "spc": sec_per_clus,        # số sector mỗi cluster
        "rsvd": rsvd_sec_cnt,       # số sector dành riêng (BPB_RsvdSecCnt)
        "nfat": num_fats,           # số bảng FAT (BPB_NumFATs)
        "fatsz": fat_sz_32,         # số sector mỗi bảng FAT (BPB_FATSz32)
        "root": root_clus,          # cluster của thư mục gốc (BPB_RootClus)
        "cs": cluster_size,         # kích thước cluster (byte)
        "fat_off": fat_offset,      # offset của bảng FAT đầu tiên (byte)
        "data_off": data_offset,    # offset của cluster 2 (thư mục gốc) (byte)
    }


# tính offset của cluster số c (c >= 2) trong ảnh đĩa
def offset_cluster(c, data_off, cs):
    return data_off + (c - 2) * cs

# đọc 1 cluster
def doc_cluster(img, c, data_off, cs):
    return img.doc(offset_cluster(c, data_off, cs), cs)

# đọc các Directory Entry 32-byte trong cluster thứ clus
def doc_muc_thu_muc(img, clus, data_off, cs):
    data = doc_cluster(img, clus, data_off, cs)
    entries = []
    
    for i in range(0, cs, 32):
        e = data[i:i + 32]
        if e[0] == 0x00:
            break
        if e[0] == 0xE5 or e[0x0B] == 0x0F or (e[0x0B] & 0x08):
            continue

        raw_name = e[0:8].decode("ascii", errors="ignore").strip()
        raw_ext  = e[8:11].decode("ascii", errors="ignore").strip()
        name = f"{raw_name}.{raw_ext}" if raw_ext else raw_name
        if name in (".", ".."):
            continue

        fc = (int.from_bytes(e[0x14:0x16], "little") << 16) | int.from_bytes(e[0x1A:0x1C], "little")
        size = int.from_bytes(e[0x1C:0x20], "little")
        is_dir = bool(e[0x0B] & 0x10)

        entries.append({
            "name": name,
            "is_dir": is_dir,
            "fc": fc,
            "size": size,
            "entry_offset": offset_cluster(clus, data_off, cs) + i  # Giữ lại offset của entry để phục vụ sửa lỗi/case 2
        })
    return entries

# đọc bảng FAT thành danh sách các số nguyên 32-bit
def doc_bang_fat(img, fat_off, fatsz, bps):
    so_entry = fatsz * bps // 4
    raw = img.doc(fat_off, so_entry * 4)
    return struct.unpack(f"<{so_entry}I", raw)

# lần theo bảng FAT để lấy danh sách các cluster của 1 file
def lan_chuoi_fat(fat, start_clus):
    seq = []
    seen = set()
    c = start_clus
    while 2 <= c < len(fat) and c not in seen:
        seen.add(c)
        seq.append(c)
        next_c = fat[c] & MASK
        if next_c >= EOC_MIN:  # End of Cluster
            break
        if next_c == 0:        # cụm chưa cấp phát (chuỗi bị đứt)
            break
        c = next_c
    return seq

# đọc dữ liệu từ một chuỗi cluster đã biết và cắt đúng kích thước file size
def doc_du_lieu_file(img, seq, size, data_off, cs):
    chunks = [doc_cluster(img, c, data_off, cs) for c in seq]
    full_data = b"".join(chunks)
    return full_data[:size]