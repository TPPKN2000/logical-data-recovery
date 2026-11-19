# Scenario 3 — Wrong location chain
import math
import utility as ut
import jpegscan


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

    # tập hợp các cluster đã bị chiếm bởi các file nguyên vẹn
    cluster_da_chiem = set()
    for c in ut.lan_chuoi_fat(fat, p["root"]): cluster_da_chiem.add(c)
    for c in ut.lan_chuoi_fat(fat, data_dir["fc"]): cluster_da_chiem.add(c)

    # tìm JPEG có First Cluster nhưng chuỗi FAT bị xóa = 0
    target = None
    for e in data_entries:
        if e["is_dir"]:
            continue
        seq = ut.lan_chuoi_fat(fat, e["fc"])
        so_clus_can = math.ceil(e["size"] / p["cs"])
        if len(seq) == so_clus_can:
            # File nguyên vẹn
            for c in seq: cluster_da_chiem.add(c)
        else:
            # File bị xóa chuỗi FAT (mục tiêu)
            if e["name"].upper().endswith(".JPG"):
                target = e

    if not target:
        log.canh_bao("Không tìm thấy tệp JPEG bị phân mảnh!")
        return

    size = target["size"]
    c0 = target["fc"]
    need = math.ceil(size / p["cs"])
    tail = size - (need - 1) * p["cs"]

    log.buoc(f"Tập tin JPEG mục tiêu: {target['name']}", gia_tri={
        "size": size, "FirstCluster": c0, "Số cluster cần": need
    })

    # đọc vùng dữ liệu bắt đầu từ First Cluster để phân tích Header JPEG
    m = min(need + 140, tong_so_cluster + 2 - c0)
    buf_dau = b"".join(ut.doc_cluster(img, c0 + i, p["data_off"], p["cs"]) for i in range(m))

    # phân tích thông số Header (SOF0, DHT, số khối MCU)
    tt = jpegscan.phan_tich_dau(buf_dau)
    if not tt.ho_tro:
        log.canh_bao(f"Không phân tích được header JPEG: {tt.ly_do}")
        return

    # tìm các cluster kết thúc bằng marker FF D9 ở đúng vị trí tail
    def la_cum_cuoi_hop_le(c):
        if c in cluster_da_chiem:
            return False
        d = ut.doc_cluster(img, c, p["data_off"], p["cs"])
        return d[tail - 2:tail] == b"\xFF\xD9"

    # mảnh 2 nằm trong phạm vi tối đa 64 cụm sau mảnh 1
    gioi_han = min(c0 + need + 130, tong_so_cluster + 2)
    ung_vien_cuoi = [c for c in range(c0 + need, gioi_han) if la_cum_cuoi_hop_le(c)]
    log.buoc("Các cụm ứng viên kết thúc bằng FF D9", gia_tri=ung_vien_cuoi[:10])

    # dò tìm điểm cắt k (độ dài mảnh 1) và điểm bắt đầu mảnh 2 (s)
    snaps = []
    _, _ = jpegscan.giai_ma(buf_dau, tt, None, snaps)
    spos = [s[0] for s in snaps]

    chuoi_dung = None
    du_lieu_dung = None

    for ec in ung_vien_cuoi:
        # k: số cụm mảnh 1 (duyệt từ need - 1 giảm dần về 1)
        for k in range(need - 1, 0, -1):
            s = ec - (need - k) + 1  # Cụm bắt đầu mảnh 2
            
            # Đảm bảo không đè lên các cụm của file khác
            if any(c in cluster_da_chiem for c in range(s, ec + 1)):
                continue
            if any(c in cluster_da_chiem for c in range(c0 + 1, c0 + k)):
                continue

            # Ghép tạm mảnh 1 và mảnh 2
            manh1 = buf_dau[:k * p["cs"]]
            manh2 = b"".join(ut.doc_cluster(img, c, p["data_off"], p["cs"]) for c in range(s, ec + 1))
            buf_thu = (manh1 + manh2)[:size]

            # Kiểm tra dòng bit giải mã bằng jpegscan
            snap_idx = jpegscan.vi_tri_snapshot(spos, k * p["cs"])
            snapshot = snaps[snap_idx] if snap_idx >= 0 else None
            kq, p_out = jpegscan.giai_ma(buf_thu, tt, snapshot, None)

            if kq == "ok" and p_out == size:
                chuoi_dung = list(range(c0, c0 + k)) + list(range(s, ec + 1))
                du_lieu_dung = buf_thu
                log.quyet_dinh(
                    f"Ghép thành công {target['name']}: Mảnh 1 ({c0}..{c0+k-1}, {k} cụm), "
                    f"Mảnh 2 ({s}..{ec}, {ec-s+1} cụm)",
                    tieu_chi=f"Giải mã đủ {tt.mcus} khối MCU và chạm marker EOI tại byte {size}"
                )
                break
        if chuoi_dung:
            break

    # lưu file hoàn chỉnh ra thư mục
    if du_lieu_dung:
        out.luu(f"DATA/{target['name']}", du_lieu_dung)
        log.buoc(f"Lưu tập tin khôi phục DATA/{target['name']}", gia_tri=f"{len(du_lieu_dung)} bytes")
    else:
        log.canh_bao("Không tìm được cách ghép hợp lệ cho tập tin JPEG!")