# Scenario 2 — Wrong directory entries
import math
import utility as ut

# kiểm tra xem dữ liệu đầu tiên của cluster có khớp với định dạng file hay không
def kiem_tra_dinh_dang(dau_du_lieu, phan_mo_rong):
    ext = phan_mo_rong.upper()
    if ext == "JPG":
        return dau_du_lieu.startswith(b"\xFF\xD8\xFF")
    elif ext == "PNG":
        return dau_du_lieu.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext == "PDF":
        return dau_du_lieu.startswith(b"%PDF-")
    elif ext == "TXT":
        # Văn bản ngắn: kiểm tra xem các byte có phải là ASCII in được không
        return all(32 <= b <= 126 or b in (9, 10, 13) for b in dau_du_lieu[:min(200, len(dau_du_lieu))])
    return False



# quét bảng FAT để tìm các cluster được cấp phát nhưng không có thư mục nào sử dụng
def tim_cac_chuoi_mo_coi(fat, tap_cluster_da_dung, tong_so_cluster):
    # tìm tập hợp tất cả các cluster là đích của một cluster khác
    cluster_duoc_tro_toi = set()
    for c in range(2, min(len(fat), tong_so_cluster + 2)):
        tiep = fat[c] & ut.MASK
        if 2 <= tiep < ut.EOC_MIN:
            cluster_duoc_tro_toi.add(tiep)

    # một cụm là đầu chuỗi nếu nó được cấp phát và không nằm trong cluster_duoc_tro_toi
    cac_chuoi = []
    for c in range(2, min(len(fat), tong_so_cluster + 2)):
        if fat[c] != 0 and c not in cluster_duoc_tro_toi:
            # nếu cụm này chưa được thư mục nào sử dụng -> đó là chuỗi mồ côi
            if c not in tap_cluster_da_dung:
                seq = ut.lan_chuoi_fat(fat, c)
                cac_chuoi.append(seq)

    return cac_chuoi


def xu_ly(img, out, log):
    p = ut.doc_bpb(img)
    fat = ut.doc_bang_fat(img, p["fat_off"], p["fatsz"], p["bps"])
    tong_so_cluster = (img.kich_thuoc - p["data_off"]) // p["cs"]

    # đọc thư mục Root và DATA
    root_entries = ut.doc_muc_thu_muc(img, p["root"], p["data_off"], p["cs"])
    data_dir = next((e for e in root_entries if e["name"] == "DATA" and e["is_dir"]), None)
    if not data_dir:
        log.canh_bao("Không tìm thấy thư mục DATA!")
        return

    data_entries = ut.doc_muc_thu_muc(img, data_dir["fc"], p["data_off"], p["cs"])

    # tập hợp các cluster đã có chủ (Root, DATA và các file còn First Cluster)
    cluster_da_dung = set()
    for c in ut.lan_chuoi_fat(fat, p["root"]): cluster_da_dung.add(c)
    for c in ut.lan_chuoi_fat(fat, data_dir["fc"]): cluster_da_dung.add(c)

    file_tot = []       # còn First Cluster
    file_mat_fc = []    # mất First Cluster

    for e in data_entries:
        if e["is_dir"]:
            continue
        if e["fc"] != 0:
            file_tot.append(e)
            for c in ut.lan_chuoi_fat(fat, e["fc"]):
                cluster_da_dung.add(c)
        else:
            file_mat_fc.append(e)

    log.buoc("Phân loại Directory Entry", gia_tri=f"Tốt: {len(file_tot)}, Mất FirstCluster: {len(file_mat_fc)}")

    # tìm các chuỗi mồ côi trong bảng FAT
    chuoi_mo_coi = tim_cac_chuoi_mo_coi(fat, cluster_da_dung, tong_so_cluster)
    log.buoc(f"Tìm thấy {len(chuoi_mo_coi)} chuỗi mồ côi trong bảng FAT")

    # ghép cặp giữa file_mat_fc và chuoi_mo_coi
    danh_sach_phuc_hoi = []
    chuoi_chua_ghep = list(chuoi_mo_coi)

    # loop từng file mất First Cluster để tìm chuỗi mồ côi phù hợp
    for f in file_mat_fc:
        so_clus_can = math.ceil(f["size"] / p["cs"])
        _, _, ext = f["name"].rpartition(".")
        
        chuoi_khop = None
        for seq in chuoi_chua_ghep:
            # Tiêu chí 1: Độ dài chuỗi bằng số cluster cần thiết
            if len(seq) == so_clus_can:
                # Tiêu chí 2: Kiểm tra Magic bytes ở cluster đầu tiên
                dau_du_lieu = ut.doc_cluster(img, seq[0], p["data_off"], p["cs"])
                if kiem_tra_dinh_dang(dau_du_lieu, ext):
                    chuoi_khop = seq
                    break

        if chuoi_khop:
            chuoi_chua_ghep.remove(chuoi_khop)
            f["seq"] = chuoi_khop
            danh_sach_phuc_hoi.append(f)
            log.quyet_dinh(f"Ghép thành công: {f['name']} -> Cluster đầu: {chuoi_khop[0]} (độ dài: {len(chuoi_khop)})")
        else:
            log.canh_bao(f"Không tìm thấy chuỗi phù hợp cho: {f['name']}")

    # lưu các tập tin ra thư mục kết quả
    # (Lưu các file đã khôi phục First Cluster)
    for f in danh_sach_phuc_hoi:
        data = ut.doc_du_lieu_file(img, f["seq"], f["size"], p["data_off"], p["cs"])
        out.luu(f"DATA/{f['name']}", data)
        log.buoc(f"Lưu tập tin khôi phục DATA/{f['name']}", gia_tri=f"{len(data)} bytes")

    # (Lưu các file vốn nguyên vẹn)
    for f in file_tot:
        seq = ut.lan_chuoi_fat(fat, f["fc"])
        data = ut.doc_du_lieu_file(img, seq, f["size"], p["data_off"], p["cs"])
        out.luu(f"DATA/{f['name']}", data)