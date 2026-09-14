# -*- coding: utf-8 -*-
"""生成 example/ 示例文件夹: 原有两道例题 + benchmark 精选 + 新特性演示题。"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, "example")
SOLVER = os.path.join(ROOT, "icelom_solver.exe")
os.makedirs(EX, exist_ok=True)


def solve(puz, mode="unique", max_solutions=50):
    q = dict(puz)
    q["limits"] = {"mode": mode, "max_solutions": max_solutions, "time_limit_ms": 30000}
    p = subprocess.run([SOLVER], input=json.dumps(q).encode(),
                       stdout=subprocess.PIPE, timeout=60)
    sols, done = [], None
    for line in p.stdout.decode().strip().splitlines():
        o = json.loads(line)
        if o["type"] == "solution":
            sols.append(o["path"])
        elif o["type"] == "done":
            done = o
    return sols, done


def dump(name, puz, note=""):
    puz = dict(puz)
    if note:
        puz["_note"] = note
    fn = os.path.join(EX, name)
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(puz, f, ensure_ascii=False, indent=1)
    print("WROTE", name)


def grid(w, h, ice=()):
    return ["i" if (x, y) in set(ice) else "w" for y in range(h) for x in range(w)]


# ---- 1. 原始两道例题 ----
classic = {
    "format": "icelom-v1", "w": 9, "h": 9,
    "cells": grid(9, 9, [(1, 1), (2, 1), (3, 1), (6, 1), (1, 2), (3, 2),
                         (1, 3), (2, 3), (3, 3), (5, 3), (6, 3), (7, 3),
                         (3, 4), (5, 4), (7, 4),
                         (1, 5), (2, 5), (3, 5), (5, 5), (6, 5), (7, 5),
                         (7, 6), (2, 7), (5, 7), (6, 7), (7, 7)]),
    "numbers": [{"x": 0, "y": 0, "n": 8}, {"x": 8, "y": 0, "n": 2}, {"x": 2, "y": 2, "n": 6},
                {"x": 4, "y": 3, "n": 9}, {"x": 2, "y": 4, "n": 4}, {"x": 6, "y": 4, "n": 5},
                {"x": 6, "y": 6, "n": 3}, {"x": 0, "y": 8, "n": 7}, {"x": 8, "y": 8, "n": 1}],
    "in": {"x": 0, "y": 4, "side": "L"}, "out": {"x": 8, "y": 4, "side": "R"},
    "edges": [], "options": {"cover_all_whites": True},
}
dump("01_经典9x9.json", classic, "经典 9x9：9 个数字, 覆盖全部白格, 解唯一")

blog88 = {
    "format": "icelom-v1", "w": 8, "h": 8,
    "cells": grid(8, 8, [(2, 0), (6, 0), (7, 0), (0, 1), (4, 1), (3, 3),
                         (4, 4), (5, 4), (5, 5), (2, 5), (6, 7)]),
    "numbers": [{"x": 3, "y": 0, "n": 6}, {"x": 0, "y": 2, "n": 3}, {"x": 6, "y": 2, "n": 7},
                {"x": 4, "y": 3, "n": 5}, {"x": 6, "y": 5, "n": 4}, {"x": 4, "y": 6, "n": 1},
                {"x": 2, "y": 6, "n": 2}],
    "in": {"x": 0, "y": 0, "side": "U"}, "out": {"x": 7, "y": 7, "side": "D"},
    "edges": [], "options": {"cover_all_whites": True},
}
dump("02_博客8x8.json", blog88, "8x8 入门: 7 个数字, 解不经过任何冰格")

# ---- 2. benchmark 精选 (快且有趣) ----
picks = [
    ("db027_5x5_wand-125.json", "03_入门5x5.json", "5x5 入门: 无数字, 解是一条穿过 9 个冰格的冰廊"),
    ("db017_5x7_ericfox53.json", "04_冰迷宫5x7.json", "5x7 冰迷宫: 无数字, 17 个冰格"),
    ("db002_8x8_bachelor-seal.json", "05_进阶8x8.json", "8x8 进阶: 数字与冰格混排, 覆盖全部白格"),
    ("db016_9x9_dj-puzzles.json", "06_进阶9x9.json", "9x9 进阶: 冰格密集, 需要冰上十字交叉"),
    ("db019_10x10_bakpao-puz.json", "07_挑战10x10.json", "10x10 挑战: 32 个冰格, 无数字"),
    ("db034_10x7_pancakepuzzles.json", "08_问号格10x7.json", "10x7“?”格演示: 2 个数字未知的编号格"),
]
for src, dst, note in picks:
    puz = json.load(open(os.path.join(ROOT, "benchmark", "puzzles", src), encoding="utf-8"))
    sols, done = solve(puz, mode="unique", max_solutions=2)
    assert done and done["count"] == 1, (src, done)
    dump(dst, puz, note)

# ---- 3. 内部 IN/OUT 演示 (要求唯一解) ----
# 5x5: IN 内部 (1,1), OUT 内部 (3,3); 以一条哈密顿路径为骨架, 贪心补箭头直到唯一。
demo_path = [(1, 1), (0, 1), (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (4, 1), (4, 2), (3, 2),
             (3, 1), (2, 1), (2, 2), (1, 2), (0, 2), (0, 3), (0, 4), (1, 4), (1, 3), (2, 3),
             (2, 4), (3, 4), (4, 4), (4, 3), (3, 3)]
demo_ice = [(1, 0), (3, 0), (3, 1), (1, 2), (0, 3)]   # 均为路径上直行通过的格
DIRNAME = {(1, 0): "R", (-1, 0): "L", (0, 1): "D", (0, -1): "U"}


def edge_of(a, b):
    """a->b 相邻移动对应的规范边 key (内部边存 R/D 侧) + 行进方向名。"""
    (x1, y1), (x2, y2) = a, b
    d = DIRNAME[(x2 - x1, y2 - y1)]
    if d == "R":
        return (x1, y1, "R"), d
    if d == "L":
        return (x2, y2, "R"), d
    if d == "D":
        return (x1, y1, "D"), d
    return (x2, y2, "D"), d


def build_demo(ice, extra_nums=(), w=5, h=5):
    return {
        "format": "icelom-v1", "w": w, "h": h,
        "cells": grid(w, h, ice),
        "numbers": [{"x": x, "y": y, "n": n} for (x, y), n in extra_nums],
        "in": {"x": 1, "y": 1}, "out": {"x": 3, "y": 3},
        "edges": [], "options": {"cover_all_whites": True},
    }


def path_edges(path):
    return [edge_of(a, b) for a, b in zip(path, path[1:])]


def greedy_uniq(base_puz, path, want=1):
    """沿骨架路径贪心放箭头直到解数 = want(逐条尝试, 直到收敛)。"""
    cand = path_edges(path)
    puz = json.loads(json.dumps(base_puz))
    sols, done = solve(puz, mode="all", max_solutions=want + 9)
    if done and done["count"] <= want:
        return puz, done
    for key, d in cand:
        if done and done["count"] <= want:
            break
        puz["edges"] = [e for e in puz["edges"] if (e["x"], e["y"], e["side"]) != key]
        puz["edges"].append({"x": key[0], "y": key[1], "side": key[2],
                             "kind": "arrow", "dir": d})
        sols, done = solve(puz, mode="all", max_solutions=want + 9)
    return puz, done


demo_in = build_demo(demo_ice)
demo_in, done09 = greedy_uniq(demo_in, demo_path, want=1)
print("内部 IN/OUT 演示:", done09, "edges=", len(demo_in["edges"]))
assert done09 and done09["count"] == 1, done09
dump("09_内部INOUT演示.json", demo_in, "IN/OUT 在盘面内部(线路以格心为起/终点, 无入出界箭头)")

# ---- 4. 角冰格 IN/OUT 演示 (角上冰格需指定方向; 要求唯一解) ----
# 6x5: IN 角 (0,0) 冰 side=L(向右入), OUT 角 (5,4) 冰 side=R(向右出); 贪心补箭头到唯一
corner_path = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (5, 1), (4, 1), (3, 1), (2, 1),
               (1, 1), (0, 1), (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (5, 3), (4, 3),
               (3, 3), (2, 3), (1, 3), (0, 3), (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (5, 4)]
corner_ice = [(0, 0), (5, 4), (2, 0), (4, 1), (1, 2), (3, 3), (2, 4)]
corner_path_set = set(corner_path)
assert len(corner_path) == 30 and len(corner_path_set) == 30
# 校验: 冰格在路径上必须直行
for i in range(1, len(corner_path) - 1):
    (x1, y1), (x2, y2), (x3, y3) = corner_path[i - 1], corner_path[i], corner_path[i + 1]
    if (x2, y2) in corner_ice:
        assert (x3 - x2, y3 - y2) == (x2 - x1, y2 - y1), ((x2, y2), "ice turn!")
demo_corner = {
    "format": "icelom-v1", "w": 6, "h": 5,
    "cells": grid(6, 5, corner_ice),
    "numbers": [],
    "in": {"x": 0, "y": 0, "side": "L"}, "out": {"x": 5, "y": 4, "side": "R"},
    "edges": [], "options": {"cover_all_whites": True},
}
demo_corner, done10 = greedy_uniq(demo_corner, corner_path, want=1)
print("角冰格演示:", done10, "edges=", len(demo_corner["edges"]))
assert done10 and done10["count"] == 1, done10
dump("10_角冰格INOUT演示.json", demo_corner, "IN/OUT 位于角上的冰格(需点击相邻格指定入/出界方向)")

# ---- 5. 箭头方向回归题 (9x9, 作者 Hexi, 题面来自 Penpa+; 2026-09-13 加入) ----
# 题面里 10 条箭头, 其中 (6,0) 下边 / (6,1) 右边这两条贴在最右上角冰格 (6,1) 上,
# 它们的强制分量是 (6,0)-(6,1)-(6,2) 与 (5,1)-(6,1)-(7,1), **不与 IN/OUT 相连** ——
# 修复"孤立强制边分量不做行走校验"之前, 求解器会给出 7 个解, 其中 6 个逆箭头方向
# (被 tests/verify.py 与官方引擎驳回); 修复后恰 1 解。
# 本文件由 tests/run_tests.py T14.6 与 tests/check_engine_examples.py 双重守护。
# 注: 来源 URL 是 Penpa+ 的编码(不是 puzz.link 编码, tools/pzprurl2json.js 解不了),
#     完整 URL 记在 example/README.md 里, 所以题面与 10 条箭头直接内联在此。
ex11_ice = [(1, 1), (2, 1), (3, 1), (6, 1),
            (1, 2), (3, 2),
            (1, 3), (2, 3), (3, 3), (5, 3), (6, 3), (7, 3),
            (3, 4), (5, 4), (7, 4),
            (1, 5), (2, 5), (3, 5), (5, 5), (6, 5), (7, 5),
            (7, 6),
            (2, 7), (5, 7), (6, 7), (7, 7)]
ex11_arrows = [  # (起点格, 终点格): 线路必须沿这个方向经过该边
    ((1, 2), (1, 1)), ((2, 3), (1, 3)), ((2, 5), (1, 5)),
    ((2, 1), (3, 1)), ((2, 7), (2, 8)), ((2, 7), (3, 7)),
    ((3, 2), (3, 3)), ((3, 4), (3, 5)),
    ((6, 1), (6, 0)), ((6, 1), (7, 1)),
]
ex11 = {
    "format": "icelom-v1", "w": 9, "h": 9,
    "cells": grid(9, 9, ex11_ice),
    "numbers": [],
    "in": {"x": 8, "y": 5, "side": "R"}, "out": {"x": 8, "y": 4, "side": "R"},
    "edges": [{"x": k[0], "y": k[1], "side": k[2], "kind": "arrow", "dir": d}
              for k, d in (edge_of(a, b) for a, b in ex11_arrows)],
    "options": {"cover_all_whites": True},
}
sols, done11 = solve(ex11, mode="unique", max_solutions=2)
print("箭头方向回归题:", done11, "edges=", len(ex11["edges"]))
assert done11 and done11["count"] == 1, done11
dump("11_20260909_9x9.json", ex11,
     "9x9 箭头题: 10 条定向必经过边; 其中最右上角冰格 (6,1) 的上/右两条箭头所在的分量与 IN/OUT 不相连")

# ---- 4. 25x7 长条问号题 (作者自制: 用本项目的求解器反复验证到唯一解) ----
# 题面与 2 条箭头内联在此(作者手写的题面, 没有可解码的来源 URL)。
# 看点: 长条盘面上 5 个数字 + 2 个 "?" 冰格 —— 已知数字 5 个 + 2x2 = 9 = 最大数字,
#       修满上限才刚好够 ⇒ 两个 "?" 冰格**必须**各被十字交叉穿越两次(与 db039 同一条计数推论);
#       2 条箭头分别钉住两个"孤立强制边"的方向。
# 求解代价: 唯一解, 但需要 2.8 万分支节点(本目录里最重的一道, GUI 默认 120 s 时限内完成)。
ex12_ice = [(1, 1), (2, 1), (3, 1), (5, 1), (6, 1), (7, 1), (9, 1), (10, 1), (11, 1),
            (13, 1), (14, 1), (15, 1), (17, 1), (18, 1), (19, 1), (21, 1), (22, 1), (23, 1),
            (3, 2), (5, 2), (7, 2), (9, 2), (11, 2), (15, 2), (19, 2), (21, 2),
            (3, 3), (5, 3), (6, 3), (7, 3), (9, 3), (10, 3), (11, 3),
            (13, 3), (14, 3), (15, 3), (17, 3), (18, 3), (19, 3), (21, 3), (22, 3), (23, 3),
            (3, 4), (7, 4), (11, 4), (15, 4), (17, 4), (23, 4),
            (3, 5), (5, 5), (6, 5), (7, 5), (9, 5), (10, 5), (11, 5),
            (13, 5), (14, 5), (15, 5), (17, 5), (18, 5), (19, 5), (21, 5), (22, 5), (23, 5)]
ex12_numbers = [  # "? 格"在前、已知数字按升序(与界面保存出来的顺序一致)
    (9, 1, -2), (11, 5, -2), (18, 3, 2), (14, 3, 3), (22, 3, 5), (3, 3, 7), (6, 3, 9)]
ex12_arrows = [  # (起点格, 终点格): 线路必须沿这个方向经过该边
    ((1, 3), (1, 4)), ((16, 2), (16, 1))]
ex12 = {
    "format": "icelom-v1", "w": 25, "h": 7,
    "cells": grid(25, 7, ex12_ice),
    "numbers": [{"x": x, "y": y, "n": n} for x, y, n in ex12_numbers],
    "in": {"x": 0, "y": 3, "side": "L"}, "out": {"x": 24, "y": 3, "side": "R"},
    "edges": [{"x": k[0], "y": k[1], "side": k[2], "kind": "arrow", "dir": d}
              for k, d in (edge_of(a, b) for a, b in ex12_arrows)],
    "options": {"cover_all_whites": True},
}
sols, done12 = solve(ex12, mode="unique", max_solutions=2)
print("长条问号题:", done12, "edges=", len(ex12["edges"]))
assert done12 and done12["count"] == 1, done12
dump("12_799325.json", ex12,
     "25x7 长条题: 2 条箭头 + 2 个「?」冰格(已知数字 5 个 + 2x2 = 9 = 最大数字, 两个「?」都被逼成十字交叉), 唯一解")

print("DONE")
