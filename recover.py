#!/usr/bin/env python3
"""Giao diện dòng lệnh thống nhất (KHÔNG sửa tệp này — phần làm bài nằm trong bai_lam.py).

  python recover.py --image anh.img --info [--json]
  python recover.py --image anh.img --case {1,2,3,ext} --out ket_qua/ [--repair da_sua.img]
  python recover.py --image anh_sach.img --corrupt mo_rong.json --out anh_hong.img
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binio import AnhDia                     # noqa: E402
from tienich import NhatKy, ThuMucKetQua     # noqa: E402
from bai_lam import BaiLam                   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Công cụ phục hồi dữ liệu — đồ án môn An toàn và phục hồi dữ liệu")
    ap.add_argument("--image", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--info", action="store_true")
    g.add_argument("--case", choices=["1", "2", "3", "ext"])
    g.add_argument("--corrupt", metavar="DAC_TA.json")
    ap.add_argument("--json", action="store_true", help="--info in kết quả dạng JSON (dùng khi chấm)")
    ap.add_argument("--out")
    ap.add_argument("--repair", metavar="ANH_MOI.img")
    ap.add_argument("--log", help="ghi thêm nhật ký vào tệp này")
    a = ap.parse_args()

    log = NhatKy(a.log)
    bai = BaiLam(log)
    img = AnhDia(a.image)
    try:
        if a.info:
            kq = bai.info(img)
            if a.json:
                print(json.dumps(kq, ensure_ascii=False, indent=1))
            else:
                for k, v in kq.items():
                    if k != "files":
                        print(f"{k}: {v}")
                for f in kq.get("files", []):
                    print(f"  {f['path']}  ({f['size']} byte)")
        elif a.corrupt:
            if not a.out:
                ap.error("--corrupt cần --out <ảnh hỏng>")
            with open(a.corrupt, encoding="utf-8") as fh:
                dac_ta = json.load(fh)
            thay_doi = bai.corrupt(img, dac_ta, a.out)
            with open(a.out + ".changes.json", "w", encoding="utf-8") as fh:
                json.dump(thay_doi, fh, ensure_ascii=False, indent=1)
        else:
            if not a.out:
                ap.error("--case cần --out <thư mục kết quả>")
            out = ThuMucKetQua(a.out)
            fn = {"1": bai.case1, "2": bai.case2, "3": bai.case3, "ext": bai.case_ext}[a.case]
            fn(img, out)
            out.ket_thuc()
            if a.repair:
                bai.repair(img, a.case, a.repair)
    except NotImplementedError as e:
        log.canh_bao(f"chưa cài đặt: {e}")
        sys.exit(2)
    except Exception:
        log.canh_bao("lỗi không xử lý được", chi_tiet=traceback.format_exc())
        sys.exit(1)
    finally:
        img.dong()


if __name__ == "__main__":
    main()
