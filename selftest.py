#!/usr/bin/env python3
"""Tự kiểm tra chương trình trên bộ ảnh MẪU công khai (giống cách giảng viên chấm, nhưng trên ảnh mẫu).

  python selftest.py --mau duong_dan/mau/fat32
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, timeout):
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "recover.py")] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -9, "", "QUÁ THỜI GIAN"


def sha_tree(d):
    out = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            if f == "SHA256SUMS":
                continue
            p = os.path.join(root, f)
            out[os.path.relpath(p, d).replace(os.sep, "/")] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def score_case(ans, outdir):
    got = sha_tree(outdir)
    files = {f["path"]: f["sha256"] for f in ans["files"]}
    noi_dung = sum(1 for t in ans["targets"] if files[t] in got.values())
    ten = sum(1 for t in ans["targets"] if got.get(t) == files[t])
    return noi_dung, ten, len(ans["targets"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mau", required=True, help="thư mục mẫu của hệ thống nhóm làm, vd. mau/ntfs")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
    clean = json.load(open(os.path.join(a.mau, "clean.json"), encoding="utf-8"))
    print(f"Hệ thống: {clean['fs']}")

    code, so, se = run(["--image", os.path.join(a.mau, "clean.img"), "--info", "--json"], a.timeout)
    try:
        kq = json.loads(so)
        want = {(f["path"], f["size"]) for f in clean["files"]}
        got = {(f["path"], f["size"]) for f in kq.get("files", [])}
        ok_cs = kq.get("cluster_size") == clean["unit_size"]
        print(f"--info: cluster_size {'đúng' if ok_cs else 'SAI'}; tập tin đúng {len(want & got)}/{len(want)}")
    except Exception:
        print(f"--info: không đọc được JSON (mã thoát {code}). stderr cuối:\n{se[-800:]}")

    for c in ("1", "2", "3"):
        p = os.path.join(a.mau, f"case{c}.img")
        if not os.path.exists(p):
            continue
        ans = json.load(open(os.path.join(a.mau, f"case{c}.json"), encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            code, so, se = run(["--image", p, "--case", c, "--out", d], a.timeout)
            nd, ten, n = score_case(ans, d)
        tail = "" if code == 0 else f"  (mã thoát {code}: {se.strip().splitlines()[-1][:160] if se.strip() else ''})"
        print(f"Tình huống {c}: nội dung đúng {nd}/{n}, đúng cả tên/đường dẫn {ten}/{n}{tail}")


if __name__ == "__main__":
    main()
