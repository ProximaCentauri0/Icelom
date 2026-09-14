# -*- coding: utf-8 -*-
"""按作者提示造 db039 的弱化版(提示边作为强制线段), 先解弱化版, 再解原题(加强版)。

提示(1-based (行,列); 转成 0-based (x,y) 即 (列-1, 行-1)):
  A: "?"@0based(6,6) 十字交叉:
       横向 (5,6)-(6,6)-(7,6) 再向上拐 (7,6)-(7,5)
       纵向 (6,5)-(6,6)-(6,7) 再向左 (6,7)-(5,7), 向下 (5,7)-(5,8), 向左 (5,8)-(4,8)  <- 到 (9,5)
  B: "?"@0based(8,7) 十字交叉:
       横向 (9,7)-(8,7)-(7,7) 再向左下: (7,7)-(7,8), (7,8)-(6,8), (6,8)-(6,9), (6,9)-(5,9)  <- 到 (10,6)
       纵向 (8,6)-(8,7)-(8,8)
  C: "?"@0based(3,7): 横向 (2,7)-(3,7)-(4,7); 纵向 (3,6)-(3,7)-(3,8)
  D: "?"@0based(7,10): 横向 (6,10)-(7,10)-(8,10); 纵向 (7,9)-(7,10)-(7,11)
"""
import json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify

PUZ = os.path.join(ROOT, "benchmark", "puzzles", "db039_13x13_0vanillaice0.json")
OUTDIR = os.path.join(ROOT, "analysis")
os.makedirs(OUTDIR, exist_ok=True)

HINT_PATHS = [
    [(5, 6), (6, 6), (7, 6), (7, 5)],
    [(6, 5), (6, 6), (6, 7), (5, 7), (5, 8), (4, 8)],
    [(9, 7), (8, 7), (7, 7), (7, 8), (6, 8), (6, 9), (5, 9)],
    [(8, 6), (8, 7), (8, 8)],
    [(2, 7), (3, 7), (4, 7)],
    [(3, 6), (3, 7), (3, 8)],
    [(6, 10), (7, 10), (8, 10)],
    [(7, 9), (7, 10), (7, 11)],
]


def edge_mark(a, b):
    (x0, y0), (x1, y1) = a, b
    if x1 == x0 + 1:
        return {"x": x0, "y": y0, "side": "R", "kind": "segment"}
    if x1 == x0 - 1:
        return {"x": x0, "y": y0, "side": "L", "kind": "segment"}
    if y1 == y0 + 1:
        return {"x": x0, "y": y0, "side": "D", "kind": "segment"}
    if y1 == y0 - 1:
        return {"x": x0, "y": y0, "side": "U", "kind": "segment"}
    raise SystemExit("bad step")


def build_weakened():
    p = json.load(open(PUZ, encoding="utf-8"))
    marks, seen = [], set()
    for path in HINT_PATHS:
        for a, b in zip(path, path[1:]):
            m = edge_mark(a, b)
            key = (m["x"], m["y"], m["side"])
            if key in seen:
                continue
            seen.add(key)
            marks.append(m)
    p["edges"] = marks
    p["options"] = {"cover_all_whites": True}
    out = os.path.join(OUTDIR, "db039_weakened.json")
    json.dump(p, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"弱化版已写出: {out}  (提示强制边 {len(marks)} 条)")
    return p


def run(puz, seconds, tag, max_solutions=3):
    p = json.loads(json.dumps(puz))
    p["options"] = {"cover_all_whites": True}
    p["limits"] = {"max_solutions": max_solutions, "time_limit_ms": int(seconds * 1000)}
    t0 = time.time()
    proc = subprocess.run([os.path.join(ROOT, "icelom_solver.exe")],
                          input=json.dumps(p).encode(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    sols, done = [], None
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o["type"] == "solution":
            sols.append(o)
        elif o["type"] == "done":
            done = o
    wall = time.time() - t0
    print(f"[{tag}] wall={wall:.1f}s sols={len(sols)} done={done}")
    if proc.stderr:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        if err:
            print(f"    stderr: {err[-1][:160]}")
    for s in sols[:2]:
        path = [tuple(t) for t in s["path"]]
        errs = verify.check(p, path, cover_all=True)
        print(f"    解#{s['index']}: {len(path)} 格  verify={'OK' if not errs else errs[:3]}")
        if not errs:
            outp = os.path.join(OUTDIR, f"db039_solution_{tag}.json")
            json.dump({"source": tag, "path": s["path"], "cells": len(path),
                       "verify": "OK", "done": done},
                      open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"    已保存: {outp}")
    return sols, done


if __name__ == "__main__":
    p_weak = build_weakened()
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    print("\n=== 弱化版(带提示强制边) ===")
    run(p_weak, secs, "weakened")
    print("\n=== 加强版(原题, 无提示) ===")
    run(json.load(open(PUZ, encoding="utf-8")), secs, "original")
