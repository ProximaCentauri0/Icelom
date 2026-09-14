# -*- coding: utf-8 -*-
"""求解器接口回归测试（独立于 tests/run_tests.py 的一套）:
`limits.mode`（first/unique/all）、内部 IN/OUT(白格/冰格)、角冰格 IN/OUT、
`options.symmetry_retry`（旧开关, 兼容接受但已不参与判定）、以及 benchmark 前 12 题的批量冒烟。

用法: python -X utf8 tests/solver_newapi_test.py [求解器路径]
      默认用仓库根的 icelom_solver.exe。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "icelom_solver.exe")
sys.path.insert(0, HERE)
import verify                                     # noqa: E402
ok = True


def report(name, cond, detail=""):
    global ok
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  " + str(detail)[:220]) if detail else ""))
    ok = ok and cond


def run(puz):
    p = subprocess.run([EXE], input=json.dumps(puz).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    sols, done = [], None
    for line in p.stdout.decode().strip().splitlines():
        o = json.loads(line)
        if o["type"] == "solution":
            sols.append(o["path"])
        elif o["type"] == "done":
            done = o
    return sols, done


def base(w=5, h=5, ice=(), nums=(), fin=None, fout=None, edges=()):
    cells = ["i" if (x, y) in set(ice) else "w" for y in range(h) for x in range(w)]
    return {
        "format": "icelom-v1", "w": w, "h": h, "cells": cells,
        "numbers": [{"x": x, "y": y, "n": n} for (x, y), n in nums],
        "in": fin, "out": fout,
        "edges": list(edges),
        "options": {"cover_all_whites": True, "symmetry_retry": True},
    }


def lim(p, **kw):
    q = dict(p)
    q["limits"] = kw
    return q


# --- 1. 简单 3x3: 框上 IN/OUT, 唯一解? ---
# 3x3 全白, IN=(0,0,U), OUT=(2,2,D): 哈密顿路径数量 >1, 用于区分模式
p1 = base(3, 3, fin={"x": 0, "y": 0, "side": "U"}, fout={"x": 2, "y": 2, "side": "D"})
sols, done = run(p1)
report("旧协议 max=1 → 唯一性模式 count∈{1,2}", done and done["count"] in (1, 2), done)

p1b = lim(p1, mode="unique")
sols, done = run(p1b)
report("mode=unique 输出 count", done and done["count"] in (1, 2), done)

p1c = lim(p1, mode="first")
sols, done = run(p1c)
report("mode=first 恰好 1 个解且不 aborted", done and done["count"] == 1 and not done["aborted"]
       and len(sols) == 1, done)

p1d = lim(p1, mode="all", max_solutions=3)
sols, done = run(p1d)
report("mode=all 上限 3 生效", done and done["count"] <= 3, done)

p1e = lim(p1, mode="all", max_solutions=200000)
sols, done = run(p1e)
n_all = done["count"] if done else -1
report("mode=all 大上限不 aborted", done and not done["aborted"], done)

# --- 2. 内部白格 IN/OUT ---
# 1x3 全白, IN 内部 (0,0), OUT 内部 (2,0): 唯一路径 [0,0]->[1,0]->[2,0]
p2 = base(3, 1, fin={"x": 0, "y": 0}, fout={"x": 2, "y": 0})
p2["limits"] = {"mode": "unique"}
sols, done = run(p2)
report("内部白格 IN/OUT: 唯一解", done and done["count"] == 1 and sols == [[[0, 0], [1, 0], [2, 0]]],
       (sols, done))

# --- 3. 内部冰格 IN/OUT (方向枚举) ---
# 1x3: 中间冰格, IN 内部 (0,0) 白, OUT 内部 (2,0) 白 → 同上
# 3x3 十字冰: IN=(1,0,U) 改为内部冰 (1,1)?
# 3x1 全冰没有白格落点 → 用 3x3: 冰 (1,0),(1,2); IN 内部冰 (1,1)?? 冰十字:
# 简单构造: 4x1 "w i w i w"? 5 格一行: cells w i w i w, IN 内部 (2,0) 白格, OUT 内部... 
# 改用: 5x1, IN=(1,0) 冰(内部), OUT=(3,0) 冰(内部): 线路 2,0->1,0(冰,方向L) ... 
# 起点 (2,0) 白?  cells: x=0 w,1 i,2 w,3 i,4 w → IN 在 (2,0)(白,内部) OUT (2,0)? 不行。
# 直接: IN 内部冰 (1,0), OUT 内部冰 (3,0): 线路必须 (1,0)->(2,0)->(3,0), 白格 (0,0)/(4,0) 不需要?
# cover_all=True 会要求 (0,0),(2,0),(4,0) 全覆盖 → 无解。cover_all=False:
p3 = base(5, 1, ice={(1, 0), (3, 0)}, fin={"x": 1, "y": 0}, fout={"x": 3, "y": 0})
p3["options"]["cover_all_whites"] = False
p3["limits"] = {"mode": "all", "max_solutions": 50}
sols, done = run(p3)
# 可能解: [1,0]->[2,0]->[3,0] (IN 向右滑 / OUT 从左到右抵达) 与 [3,0]->[2,0]->[1,0]? 不 — IN 起点固定 (1,0)
# IN(1,0) 冰: 起点出发 4 方向; L 出界不可; U/D 出界不可; R → (2,0) 落点白格 ✓
# 之后 (2,0)->(3,0): 抵达冰质 OUT (3,0), 同轴 → 终止 ✓; 也可 (2,0)→? (2,0) 是白格可转弯: (2,0)->(1,0)?
# (1,0) 是 IN 分量已含起点桩, 再进去 = 边重复/分量已闭 → 不行; (2,0)->(3,0) 唯一出路 ✓
report("内部冰格 IN/OUT 枚举方向: count>=1 且路径正确",
       done and done["count"] >= 1 and [[[1, 0], [2, 0], [3, 0]]] == [s for s in sols],
       (sols, done))

# --- 4. 角上冰格 IN/OUT (显式 side) ---
# 2x2 全冰? 角 (0,0) 冰 IN side=U (向下进入), OUT (1,1) 冰 side=D (从上来到达)
# 2x2 全冰 cover_all 无白格: IN (0,0) 向下滑 → (0,1)冰 继续直行 → 出界撞框? (0,1) 向下无格 → 失败
# 换: IN (0,0) side=U (inDir=D): (0,0)->(0,1) 冰直行 → (0,1) 出界? 失败 → side=L (inDir=R):
# (0,0)->(1,0) 冰直行 → (1,0)→出界失败… 2x2 全冰不可行。用 2x3:
# cells 2 列 3 行全冰, IN (0,0) side=L (向右), OUT (1,2) side=D (向上进入终点? outDir=D)
# OUT (1,2) 在底框 side=D: outDir=D; 抵达方向必须同轴竖直: 从 (1,1) 向下 ✓
# 路径: (0,0)→R(1,0)→D(1,1)→D(1,2)终止? (1,0) 冰转弯 R→D ✗!
p4 = base(2, 3, ice={(x, y) for x in range(2) for y in range(3)},
          fin={"x": 0, "y": 0, "side": "L"}, fout={"x": 1, "y": 2, "side": "D"})
p4["options"]["cover_all_whites"] = False
p4["limits"] = {"mode": "first"}
sols, done = run(p4)
# 全冰 → 任何路径必须全直线 → 2x3 无转弯: IN 向右 (0,0)->(1,0) 直行出界 → 无解
report("角冰格 IN side=L: 全冰 2x3 无解(直行限制)", done and done["count"] == 0, done)

# --- 4b. 角上冰格 IN/OUT 有解例 ---
# 3x3: 冰 (0,0),(2,2); IN=(0,0) side=L (向右进入), OUT=(2,2) side=D (从上方抵达)
# cover_all=False: 路径 (0,0)->(1,0)->(2,0)->(2,1)->(2,2)
p4b = base(3, 3, ice={(0, 0), (2, 2)},
           fin={"x": 0, "y": 0, "side": "L"}, fout={"x": 2, "y": 2, "side": "D"})
p4b["options"]["cover_all_whites"] = False
p4b["limits"] = {"mode": "first"}
sols, done = run(p4b)
# 语义检查(用独立验证器; **不钉死具体路线**): 该题在 cover_all=False 下有多条合法路线
# (经 (1,1) 绕行的那条同样合法), mode=first 返回哪一条取决于搜索顺序 —— 早期版本把具体
# 路径写死在断言里, 于是把"搜索顺序"当成了接口语义。搜索顺序改成单一固定顺序后,
# 首解换成另一条合法路线, 这里改成"起点/出框轴/终点 + 独立验证器"三件事。
errs = verify.check(p4b, [tuple(t) for t in sols[0]], cover_all=False) if sols else ["无解"]
good = (done and done["count"] == 1 and len(sols) == 1 and not errs
        and sols[0][0] == [0, 0] and sols[0][1] == [1, 0] and sols[0][-1] == [2, 2]
        and len(sols[0]) >= 4)
report("角冰格 IN/OUT 显式方向: 求得解(过独立验证器)", good, (sols, done, errs[:2]))

# --- 4c. 同题换轴: IN side=U (向下, 落 (0,1) 白格), OUT side=D (从上方抵达) ---
p4c = base(3, 3, ice={(0, 0), (2, 2)},
           fin={"x": 0, "y": 0, "side": "U"}, fout={"x": 2, "y": 2, "side": "D"})
p4c["options"]["cover_all_whites"] = False
p4c["limits"] = {"mode": "first"}
sols, done = run(p4c)
good = (sols and sols[0][0] == [0, 0] and sols[0][1] == [0, 1] and sols[0][-1] == [2, 2]
        and done and done["count"] == 1)
report("角冰格 IN side=U / OUT side=D: 沿另一轴求得解", good, (sols, done))

# --- 5. 回归: benchmark 前几题唯一性结果应与 results.json 一致 ---
import os
bench = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "benchmark")
n_checked = 0
n_mismatch = 0
for fn in sorted(os.listdir(os.path.join(bench, "puzzles")))[:12]:
    puz = json.load(open(os.path.join(bench, "puzzles", fn), encoding="utf-8"))
    sols, done = run(puz)
    n_checked += 1
    if not done or done["count"] < 1:
        n_mismatch += 1
        print("  !!", fn, done)
report(f"回归: benchmark 前 {n_checked} 题全部有解", n_mismatch == 0, f"mismatch={n_mismatch}")

print()
print("SOLVER NEW-API ALL PASS" if ok else "SOLVER NEW-API SOME FAILED")
sys.exit(0 if ok else 1)
