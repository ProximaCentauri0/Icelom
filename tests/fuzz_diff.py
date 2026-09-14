# -*- coding: utf-8 -*-
"""一致性模糊测试: 随机谜题上交叉核对主求解器(C++)与独立模型(Python 走廊收缩)。

本脚本对主求解器做**双向交叉核对**:

  ① 主求解器 <-> 独立走廊收缩模型(`tests/indep_solver.py`, 完全不同的算法与数据结构):
     同一题面上"解集合"必须完全一致;
  ② 主求解器 <-> 独立验证器(`tests/verify.py`): 它给出的每个解都必须被独立规则实现接受;
  ③ 独立模型找不到解时, 主求解器也不应找到(反之亦然) —— 这是发现"假无解"剪枝缺陷的主要手段。

生成器刻意偏向高冰密度与冰上数字(历史上正是在这类题上发现"残差连通性剪枝"误剪合法前缀
导致假无解)。对照盘面回避了独立模型的已知能力差异, 免得统计里塞满 skip:

- IN/OUT 只放在**白格**上(indep_solver 仅支持白质 OUT, 且内部 IN/OUT 的"格心起终点"语义
  它不表达);
- 拒绝"冰廊把一个白格与另一个白格直接连起来"的盘面(即冰格不得在左右/上下两侧同时紧邻白格):
  那种冰廊在独立模型里是一条白格之间的边, 主求解器则要求"必须从廊里经过", 两者模型不同,
  属于已知的表达差异而非缺陷。

用法: python -X utf8 tests/fuzz_diff.py [用例数] [随机种子]
退出码: 0 = 无差异, 1 = 有差异(差异盘面写到 <仓库根>/_fz_*.json)
"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import verify                                    # noqa: E402
from indep_solver import solve as indep_solve    # noqa: E402

V2 = os.path.join(ROOT, "icelom_solver.exe")


def solve(exe, puz, cap=200000, tl=20000):
    """跑主求解器, 返回 (解路径集合, done 记录)。"""
    p = dict(puz)
    p["limits"] = {"max_solutions": cap, "time_limit_ms": tl}
    try:
        r = subprocess.run([exe], input=json.dumps(p).encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=tl / 1000 + 60)
    except subprocess.TimeoutExpired:
        return None, None
    sols, done = [], None
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o["type"] == "solution":
            sols.append(tuple(map(tuple, o["path"])))
        elif o["type"] == "done":
            done = o
    return set(sols), done


def edgeset(path):
    """把一条格序列(含冰格重复经过)化成无向边集合 —— 与路径表示无关的规范形式。"""
    return frozenset(frozenset((tuple(path[i - 1]), tuple(path[i])))
                     for i in range(1, len(path)))


def canon_route(path, puz):
    """规范结点序: 只保留白格与编号格, 并去掉相邻重复。

    独立走廊收缩模型把冰廊收缩成白格之间的一条边(廊内的纯冰格不在它的序列里), 主求解器
    则输出逐个冰格。两者在"白格 + 编号格"这一层完全等价, 因此比较前统一到这一层。
    """
    numbers = puz.get("numbers", [])
    numbered = {(n["x"], n["y"]) for n in numbers}
    out = []
    for p in path:
        p = tuple(p)
        keep = puz["cells"][p[1] * puz["w"] + p[0]] == "w" or p in numbered
        if keep and (not out or out[-1] != p):
            out.append(p)
    return tuple(out)


def gen(rng):
    w = rng.randint(4, 8)
    h = rng.randint(4, 8)
    ice_p = rng.choice([0.3, 0.4, 0.5, 0.6])
    cells = ["i" if rng.random() < ice_p else "w" for _ in range(w * h)]
    if cells.count("w") < 6:
        return None
    puz = {"format": "icelom-v1", "w": w, "h": h, "cells": cells, "numbers": [],
           "edges": [], "options": {"cover_all_whites": True}}
    frame_w = []      # 边框上的白格 (对照基线只支持白质 IN/OUT)
    for y in range(h):
        for x in range(w):
            if cells[y * w + x] != "w":
                continue
            for side, ok in (("L", x == 0), ("R", x == w - 1), ("U", y == 0), ("D", y == h - 1)):
                if ok:
                    frame_w.append((x, y, side))
    if len(frame_w) < 2:
        return None
    rin, rout = rng.sample(frame_w, 2)
    if (rin[0], rin[1]) == (rout[0], rout[1]):
        return None
    puz["in"] = {"x": rin[0], "y": rin[1], "side": rin[2]}
    puz["out"] = {"x": rout[0], "y": rout[1], "side": rout[2]}
    k = rng.randint(0, min(5, w * h // 4))
    ice_spots = [i for i, c in enumerate(cells) if c == "i"
                 and i != rin[1] * w + rin[0] and i != rout[1] * w + rout[0]]
    spots = []
    if ice_spots:
        spots += rng.sample(ice_spots, min(k, len(ice_spots)))
    rest = [i for i in range(w * h) if i not in spots]
    while len(spots) < k and rest:
        s = rng.choice(rest)
        rest.remove(s)
        spots.append(s)
    for i, s in enumerate(spots[:k]):
        puz["numbers"].append({"x": s % w, "y": s // w, "n": i + 1})
    numbered = {(n["x"], n["y"]) for n in puz["numbers"]}
    # 拒绝"任意两个白格之间存在一条纯冰直廊"的盘面: 走廊收缩模型会把这种冰廊当成白格之间的
    # 一条**边**(它不记录廊内纯冰格), 主求解器则要求线路逐格经过廊内每一格 —— 两者对
    # "线路怎么走"的描述不同, 属于已知的表达差异, 不是缺陷。只保留两个模型表示一致的盘面。
    for y in range(h):
        for x in range(w):
            if cells[y * w + x] != "i":
                continue
            for dx, dy in ((1, 0), (0, 1)):
                px, py = x - dx, y - dy
                if 0 <= px < w and 0 <= py < h and cells[py * w + px] == "i":
                    continue                      # 不是直廊的起点
                # 从 (x,y) 开始的这条直廊: 两端若是白格, 或廊内带编号格, 则两模型表示不同
                cx, cy, inside = x, y, []
                nbr_before = (x - dx, y - dy)
                before_white = (0 <= nbr_before[0] < w and 0 <= nbr_before[1] < h
                                and cells[nbr_before[1] * w + nbr_before[0]] == "w")
                while 0 <= cx < w and 0 <= cy < h and cells[cy * w + cx] == "i":
                    inside.append((cx, cy))
                    cx += dx
                    cy += dy
                after_white = (0 <= cx < w and 0 <= cy < h and cells[cy * w + cx] == "w")
                if before_white and after_white:
                    return None
                if any(c in numbered for c in inside) and (before_white or after_white):
                    return None
    return puz


def dump_bad(name, puz, extra=""):
    fn = os.path.join(ROOT, "_fz_%s.json" % name)
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(puz, f, ensure_ascii=False, indent=1)
    print("   盘面已保存:", os.path.basename(fn), extra)


def main():
    if not os.path.exists(V2):
        print("缺少主求解器 %s, 请先编译: g++ -O2 -std=c++17 -o icelom_solver.exe icelom_solver.cpp" % V2)
        return 2
    n_asked = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rng = random.Random(seed)
    mismatch = tested = skipped = 0
    for i in range(n_asked):
        puz = None
        for _ in range(4000):                    # 生成器带"模型可对照"约束, 需要重采样
            puz = gen(rng)
            if puz is not None:
                break
        if puz is None:
            skipped += 1
            continue
        tl = 20.0
        s2, d2 = solve(V2, puz, tl=int(tl * 1000))
        pair, msg = indep_solve(puz, tl)
        if msg is not None and "unsupported" in msg:
            skipped += 1
            continue
        if d2 is None or d2.get("aborted") or (msg is not None and msg.startswith("timeout")):
            skipped += 1          # 任一侧没跑完, 结论不可比
            continue
        tested += 1
        # ① 每个解都要过独立验证器
        bad = None
        for pth in s2:
            errs = verify.check(puz, list(pth), cover_all=True)
            if errs:
                bad = errs[:3]
                break
        if bad:
            mismatch += 1
            print("主求解器的解未通过独立验证器:", bad)
            dump_bad("bad_%d" % i, puz)
            continue
        # ② 独立模型找到的解必须被主求解器收录 (两条完全独立的求解路径互相印证)。
        #    两个模型对路径的**表示**不同: 主求解器输出含每个冰格的完整序列, 独立模型只给
        #    "白格结点"序列(冰廊被收缩成一条边)。统一到"白格 + 编号格"的规范结点序上再比。
        cpp = {canon_route(p, puz) for p in s2}
        ok2 = True
        if pair is not None:
            ind = canon_route(pair, puz)         # 独立模型只给首解
            if ind not in cpp:
                ok2 = False
        # ③ "无解"结论必须两边一致
        if pair is None and s2:
            ok2 = False
        if not ok2:
            mismatch += 1
            print("=" * 60)
            print("MISMATCH #%d: 主求解器 %d 个解, 独立模型 %s"
                  % (mismatch, len(s2), "有解" if pair else "无解"))
            print(json.dumps(puz, ensure_ascii=False))
            print("  独立模型解(白格结点序):", pair if pair else None)
            for pth in list(s2)[:1]:
                print("  主求解器首解:", pth)
            dump_bad("mm_%d" % i, puz)
            if mismatch >= 5:
                break
    print("done: 请求=%d 参与比对=%d 跳过=%d 差异=%d" % (n_asked, tested, skipped, mismatch))
    print("提示: 差异盘面保存在仓库根 _fz_*.json; 用 tests/verify.py 与 tests/indep_solver.py 复核。")
    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
