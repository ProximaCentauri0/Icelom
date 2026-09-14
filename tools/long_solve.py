# -*- coding: utf-8 -*-
"""long_solve.py — 长时间求解一个题面(默认不限时), 找到解立即保存并用独立验证器核对。

用法:
  python tools/long_solve.py <谜题.json> [输出解.json]
         [--transform none|flip-x|flip-y|rot180|transpose]
         [--max-solutions N] [--label NAME] [--time-limit-ms MS]

- 默认不限时间(10^7 秒 ≈ 116 天), 一直搜到找到解或手动停止(Ctrl+C / 结束进程)。
- 每找到一个解**立即**写盘(坐标先做逆变换还原成原题坐标), 并用 tests/verify.py 独立核对;
  输出文件是 {"puzzle":..., "solution":[[x,y],...], "verify":"OK", ...} 形式。
- --transform 把盘面做对称变换后再求解(规则对称, 可解性等价, 解再变换回来)。
  不同变换会改变搜索顺序, 并行跑多个变换能显著提高"早日搜到"的概率。
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify  # noqa: E402

SIDE_X = {"L": "R", "R": "L", "U": "U", "D": "D"}
SIDE_Y = {"L": "L", "R": "R", "U": "D", "D": "U"}
SIDE_XY = {"L": "R", "R": "L", "U": "D", "D": "U"}   # rot180
SIDE_T = {"R": "D", "D": "R", "L": "U", "U": "L"}    # 转置


def make_map(kind, w, h):
    """返回 (点映射, 边长映射, 新尺寸)。四种变换都是对合(自逆)。"""
    if kind == "none":
        return (lambda x, y: (x, y)), {}, (w, h)
    if kind == "flip-x":
        return (lambda x, y: (w - 1 - x, y)), SIDE_X, (w, h)
    if kind == "flip-y":
        return (lambda x, y: (x, h - 1 - y)), SIDE_Y, (w, h)
    if kind == "rot180":
        return (lambda x, y: (w - 1 - x, h - 1 - y)), SIDE_XY, (w, h)
    if kind == "transpose":
        return (lambda x, y: (y, x)), SIDE_T, (h, w)
    raise SystemExit("unknown transform: " + kind)


def transform(puz, kind):
    w, h = puz["w"], puz["h"]
    f, smap, (nw, nh) = make_map(kind, w, h)
    if kind == "none":
        return json.loads(json.dumps(puz))
    out = json.loads(json.dumps(puz))
    out["w"], out["h"] = nw, nh
    cells = ["w"] * (nw * nh)
    for y in range(h):
        for x in range(w):
            nx, ny = f(x, y)
            cells[ny * nw + nx] = puz["cells"][y * w + x]
    out["cells"] = cells
    for key in ("numbers",):
        for it in out.get(key) or []:
            it["x"], it["y"] = f(it["x"], it["y"])
    for key in ("in", "out"):
        it = out.get(key)
        if it and it.get("x") is not None:
            it["x"], it["y"] = f(it["x"], it["y"])
            it["side"] = smap[it["side"]]
    for e in out.get("edges") or []:
        if e.get("x") is None:
            continue
        e["x"], e["y"] = f(e["x"], e["y"])
        e["side"] = smap[e["side"]]
        if e.get("dir"):
            e["dir"] = smap[e["dir"]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--transform", default="none",
                    choices=["none", "flip-x", "flip-y", "rot180", "transpose"])
    ap.add_argument("--max-solutions", type=int, default=1)
    ap.add_argument("--time-limit-ms", type=int, default=10_000_000_000)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    t0 = time.time()
    puz = json.load(open(args.puzzle, encoding="utf-8"))
    puz.setdefault("options", {})["cover_all_whites"] = True
    tpuz = transform(puz, args.transform)
    if args.out is None:
        base = os.path.splitext(os.path.basename(args.puzzle))[0]
        args.out = os.path.join(ROOT, "benchmark", "solutions",
                                f"{base}_{args.transform}.json")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    label = args.label or (os.path.basename(args.puzzle) + " / " + args.transform)
    print(f"[{label}] start: {puz['w']}x{puz['h']} -> {tpuz['w']}x{tpuz['h']} "
          f"transform={args.transform} out={args.out}", flush=True)

    tpuz["limits"] = {"max_solutions": args.max_solutions, "time_limit_ms": args.time_limit_ms}
    proc = subprocess.Popen([os.path.join(ROOT, "icelom_solver.exe")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=1)
    proc.stdin.write(json.dumps(tpuz, ensure_ascii=False).encode())
    proc.stdin.close()

    f, _, _ = make_map(args.transform, puz["w"], puz["h"])
    found = 0
    try:
        for line in proc.stdout:
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj["type"] == "solution":
                path = [list(f(x, y)) for x, y in obj["path"]]
                errs = verify.check(puz, [tuple(p) for p in path], cover_all=True)
                found += 1
                rec = {
                    "label": label, "transform": args.transform,
                    "puzzle": os.path.relpath(args.puzzle, ROOT).replace("\\", "/"),
                    "solution_index": obj.get("index"), "path": path,
                    "cells": len(path), "verify": "OK" if not errs else errs[:5],
                    "elapsed_s": round(time.time() - t0, 1),
                }
                with open(args.out, "w", encoding="utf-8") as fh:
                    json.dump(rec, fh, ensure_ascii=False, indent=1)
                print(f"[{label}] *** SOLUTION #{found} ({len(path)} cells) saved to {args.out} "
                      f"verify={'OK' if not errs else errs[:3]} at {time.time()-t0:.0f}s ***", flush=True)
                if found >= args.max_solutions:
                    proc.kill()
                    break
            elif obj["type"] == "done":
                print(f"[{label}] done: count={obj['count']} nodes={obj['nodes']} "
                      f"ms={obj['ms']} aborted={obj['aborted']} reason={obj.get('reason')} "
                      f"elapsed={time.time()-t0:.0f}s", flush=True)
                if found == 0:
                    print(f"[{label}] NO SOLUTION in this run "
                          f"(aborted={obj['aborted']}: True 表示只是到时限/被停, 不代表无解)", flush=True)
            else:
                print(f"[{label}] {line}", flush=True)
    except KeyboardInterrupt:
        proc.kill()
        print(f"[{label}] interrupted; solutions found={found}", flush=True)
        return 0 if found else 130
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
