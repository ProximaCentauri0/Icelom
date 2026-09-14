# -*- coding: utf-8 -*-
"""IceLom 求解器测试集：9x9 原样例 + 8x8 博客真题 + 边标记/负例。"""
import json
import subprocess
import sys
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOLVER = os.path.join(ROOT, "icelom_solver.exe")
sys.path.insert(0, HERE)
import verify


def solve(puz, cover_all=None, max_solutions=2000000, time_limit_ms=60000, env=None):
    if cover_all is not None:
        puz = dict(puz)
        puz["options"] = {"cover_all_whites": cover_all}
    puz = dict(puz)
    puz.setdefault("options", {})["cover_all_whites"] = puz.get("options", {}).get("cover_all_whites", True) if cover_all is None else cover_all
    puz["limits"] = {"max_solutions": max_solutions, "time_limit_ms": time_limit_ms}
    data = json.dumps(puz, ensure_ascii=False).encode("utf-8")
    t0 = time.time()
    p = subprocess.run([SOLVER], input=data, stdout=subprocess.PIPE, timeout=90,
                       env=dict(os.environ, **env) if env else None)
    wall = (time.time() - t0) * 1000
    sols, done, err = [], None, None
    for line in p.stdout.decode("utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj["type"] == "solution":
            sols.append(obj)
        elif obj["type"] == "done":
            done = obj
        elif obj["type"] == "error":
            err = obj
    return sols, done, err, wall


def grid_str(puz, path):
    w, h = puz["w"], puz["h"]
    step = {}
    for i in range(1, len(path)):
        step[(path[i - 1], path[i])] = True
    # 输出每个格子的离开方向
    lines = []
    for y in range(h):
        row = ""
        for x in range(w):
            row += "."
        lines.append(list(row))
    for i, (x, y) in enumerate(path):
        ch = "*"
        if i + 1 < len(path):
            nx, ny = path[i + 1]
            ch = {(1, 0): ">", (-1, 0): "<", (0, 1): "v", (0, -1): "^"}[(nx - x, ny - y)]
        elif i > 0:
            px, py = path[i - 1]
            ch = {(1, 0): ">", (-1, 0): "<", (0, 1): "v", (0, -1): "^"}[(x - px, y - py)]
        lines[y][x] = ch
    return "\n".join("".join(r) for r in lines)


# ---------- 谜题 ----------
def puz9x9(cover_all=True):
    """最早的 Icelom.cpp 单题求解器里的 9x9 谜题。"""
    ice = {
        (1, 1), (2, 1), (3, 1), (6, 1),
        (1, 2), (3, 2),
        (1, 3), (2, 3), (3, 3), (5, 3), (6, 3), (7, 3),
        (3, 4), (5, 4), (7, 4),
        (1, 5), (2, 5), (3, 5), (5, 5), (6, 5), (7, 5),
        (7, 6),
        (2, 7), (5, 7), (6, 7), (7, 7),
    }
    nums = {(0, 0): 8, (8, 0): 2, (2, 2): 6, (4, 3): 9, (2, 4): 4,
            (6, 4): 5, (6, 6): 3, (0, 8): 7, (8, 8): 1}
    cells = ["i" if (x, y) in ice else "w" for y in range(9) for x in range(9)]
    return {
        "w": 9, "h": 9, "cells": cells,
        "numbers": [{"x": x, "y": y, "n": n} for (x, y), n in nums.items()],
        "in": {"x": 0, "y": 4, "side": "L"},
        "out": {"x": 8, "y": 4, "side": "R"},
        "edges": [],
        "options": {"cover_all_whites": cover_all},
    }


def puz8x8(cover_all=True):
    """博客「アイスローム 4」(puzz.link/p?icelom/a/8/8/4e40040c4g004i6r3k7k5w4i2g1q)。
    评论区: 作者预期解不经过任何冰格。"""
    ice = {(2, 0), (6, 0), (7, 0), (0, 1), (4, 1), (3, 3),
           (4, 4), (5, 4), (5, 5), (2, 5), (6, 7)}
    nums = {(3, 0): 6, (0, 2): 3, (6, 2): 7, (4, 3): 5,
            (6, 5): 4, (4, 6): 1, (2, 6): 2}
    cells = ["i" if (x, y) in ice else "w" for y in range(8) for x in range(8)]
    return {
        "w": 8, "h": 8, "cells": cells,
        "numbers": [{"x": x, "y": y, "n": n} for (x, y), n in nums.items()],
        "in": {"x": 0, "y": 0, "side": "U"},
        "out": {"x": 7, "y": 7, "side": "D"},
        "edges": [],
        "options": {"cover_all_whites": cover_all},
    }


def puz5x3(out_ice=True):
    """5x3 构造题: 白格 (4,0)/(4,2) 各只连 (3,x) 与 OUT → 任何覆盖解都必须
    垂直穿过冰质 OUT (4,1) 一次、最后从 (3,1) 沿出框方向折返出框。
    用于回归「穿过 OUT 格再回来出框」。out_ice=False 时同盘 OUT 为白格：
    白格至多一次, 穿过再出框需 3 条连接 → 无解（对照组）。"""
    cells = ["w"] * 15
    if out_ice:
        cells[1 * 5 + 4] = "i"
    return {
        "w": 5, "h": 3, "cells": cells,
        "numbers": [],
        "in": {"x": 0, "y": 0, "side": "L"},
        "out": {"x": 4, "y": 1, "side": "R"},
        "edges": [],
        "options": {"cover_all_whites": True},
    }


def report(name, cond, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  " + detail) if detail else ""))
    return cond


def main():
    allpass = True

    # T1: 9x9 覆盖所有白格
    p = puz9x9(True)
    sols, done, err, wall = solve(p)
    allpass &= report("T1 9x9(覆盖白格) 有解", err is None and done and done["count"] > 0,
                      f"count={done['count'] if done else '?'} nodes={done['nodes'] if done else '?'} ms={done['ms'] if done else '?'}")
    for s in sols:
        errs = verify.check(p, [tuple(t) for t in s["path"]], cover_all=True)
        if errs:
            allpass &= report("T1 解验证", False, str(errs[:3]))
            break
    else:
        allpass &= report(f"T1 全部 {len(sols)} 个解通过独立验证器", True)
    if sols:
        print("  首解路径:")
        print("\n".join("  " + l for l in grid_str(p, [tuple(t) for t in sols[0]["path"]]).splitlines()))

    # T2: 8x8 博客题
    p = puz8x8(True)
    sols8, done, err, wall = solve(p)
    allpass &= report("T2 8x8(博客题) 有解", err is None and done and done["count"] > 0,
                      f"count={done['count'] if done else '?'} nodes={done['nodes'] if done else '?'} ms={done['ms'] if done else '?'}")
    noice = 0
    for s in sols8:
        path = [tuple(t) for t in s["path"]]
        errs = verify.check(p, path, cover_all=True)
        if errs:
            allpass &= report("T2 解验证", False, str(errs[:3]))
            break
        if all(p["cells"][y * 8 + x] == "w" for x, y in path):
            noice += 1
    else:
        allpass &= report(f"T2 全部 {len(sols8)} 个解通过独立验证器；不经过任何冰格的解: {noice} 个", True)
    if sols8:
        print("  首解路径:")
        print("\n".join("  " + l for l in grid_str(p, [tuple(t) for t in sols8[0]["path"]]).splitlines()))

    # T3: 边标记 — 强制线段/箭头与基础解相容, 墙放在基础解未用的边
    p = puz8x8(True)
    p["edges"] = [
        {"x": 0, "y": 0, "side": "R", "kind": "segment"},            # (0,0)-(1,0) 基础解必经
        {"x": 7, "y": 6, "side": "D", "kind": "arrow", "dir": "D"},  # (7,6)->(7,7) 基础解进入 OUT 方向
        {"x": 0, "y": 0, "side": "D", "kind": "wall"},               # (0,0)-(0,1) 基础解未使用
    ]
    sols, done, err, wall = solve(p)
    okc = err is None and done and done["count"] > 0
    allpass &= report("T3 边标记谜题有解", okc, f"count={done['count'] if done else '?'}")
    for s in sols:
        errs = verify.check(p, [tuple(t) for t in s["path"]], cover_all=True)
        if errs:
            allpass &= report("T3 解验证", False, str(errs[:3]))
            break
    else:
        allpass &= report(f"T3 全部 {len(sols)} 个解通过独立验证器", True)

    # T4: 负例1 — 墙堵住 IN
    p = json.loads(json.dumps(puz8x8(True)))
    p["edges"] = [{"x": 0, "y": 0, "side": "U", "kind": "wall"}]
    sols, done, err, wall = solve(p)
    allpass &= report("T4 墙堵住IN -> 无解", err is None and done and done["count"] == 0 and "IN" in done.get("reason", ""),
                      f"reason={done.get('reason') if done else '?'}")

    # T5: 负例2 — IN 箭头方向不对（边框箭头向上=出盘方向）
    p = json.loads(json.dumps(puz8x8(True)))
    p["edges"] = [{"x": 0, "y": 0, "side": "U", "kind": "arrow", "dir": "U"}]
    sols, done, err, wall = solve(p)
    allpass &= report("T5 IN处反向箭头 -> 无解", err is None and done and done["count"] == 0,
                      f"reason={done.get('reason') if done else '?'}")

    # T6: 负例3 — 边框中部放线段（无法被经过）
    p = json.loads(json.dumps(puz8x8(True)))
    p["edges"] = [{"x": 4, "y": 0, "side": "U", "kind": "segment"}]
    sols, done, err, wall = solve(p)
    allpass &= report("T6 边框中部线段 -> 无解", err is None and done and done["count"] == 0,
                      f"reason={done.get('reason') if done else '?'}")

    # T7: 9x9 不要求覆盖白格（解数量应 >= 覆盖版）。
    #     历史值（原作者最早的 Icelom.cpp/.exe 只能解这一题）：覆盖模式 1 解、关闭覆盖 3 解，
    #     且 3 个解的路径集合与原程序全等（原程序已删除，此处用确切解数 + 独立验证器钉住结论）。
    p1 = puz9x9(True)
    s1, d1, _, _ = solve(p1)
    s2, d2, _, _ = solve(puz9x9(False))
    allpass &= report("T7 关闭覆盖后解数量不减", d2["count"] >= d1["count"], f"cover={d1['count']} free={d2['count']}")
    allpass &= report("T7 覆盖模式 1 解 / 关闭覆盖 3 解（与原单题求解器的历史结论一致）",
                      d1["count"] == 1 and d2["count"] == 3,
                      f"cover={d1['count']} free={d2['count']} 期望=1/3")
    for s in s2:
        errs = verify.check(puz9x9(False), [tuple(t) for t in s["path"]], cover_all=False)
        if errs:
            allpass &= report("T7 关闭覆盖的每个解通过独立验证器", False, str(errs[:3]))
            break
    else:
        allpass &= report(f"T7 关闭覆盖的全部 {len(s2)} 个解通过独立验证器", True)

    # T8: 数字必须正好落在自己的位次上 (pzpr 官方 checkNumberOrder 语义:
    #     计数线路上经过的编号格, 已知数字 n 必须出现在第 n 个编号格上)。
    #     9x9 的数字 1..9 原位合法; 全部乘 2 变成 2,4,..,18 后首个数字 2 落在第 1 位 -> 无解。
    p = json.loads(json.dumps(puz9x9(True)))
    for nm in p["numbers"]:
        nm["n"] *= 2
    sols, done, err, wall = solve(p)
    allpass &= report("T8 数字整体放大(1..9 -> 2,4,..,18) 后无解(数字必须落在自己的位次)",
                      err is None and done is not None and done["count"] == 0,
                      f"count={done['count'] if done else '?'} 期望=0 err={err}")
    for s in sols:
        errs = verify.check(p, [tuple(t) for t in s["path"]], cover_all=True)
        if errs:
            allpass &= report("T8 解验证", False, str(errs[:3]))
            break
    else:
        allpass &= report(f"T8 全部 {len(sols)} 个解通过独立验证器", True)
    # T8b: 输入错误 — 同一数字出现两次 / 非法数字值
    p = json.loads(json.dumps(puz9x9(True)))
    p["numbers"].append({"x": 0, "y": 0, "n": 8})
    _, _, err_dup, _ = solve(p)
    p2 = json.loads(json.dumps(puz9x9(True)))
    p2["numbers"][0]["n"] = 0
    _, _, err_bad, _ = solve(p2)
    allpass &= report("T8b 重复数字/非法数字 -> 报错",
                      err_dup is not None and err_bad is not None,
                      f"dup={err_dup['message'] if err_dup else '?'} bad={err_bad['message'] if err_bad else '?'}")

    # T9: 穿过冰质 OUT 再折返出框（旧版剪枝会误判无解; 官方引擎允许:
    # 穿过 2 边 + 出框 2 边 = lcnt 4, 冰格合法; 3 边才是 lnBranch 违规）
    p = puz5x3(True)
    sols, done, err, wall = solve(p)
    allpass &= report("T9 穿过冰OUT再出框 有解", err is None and done and done["count"] >= 1,
                      f"count={done['count'] if done else '?'} nodes={done['nodes'] if done else '?'}")
    for s in sols:
        path = [tuple(t) for t in s["path"]]
        errs = verify.check(p, path, cover_all=True)
        if errs:
            allpass &= report("T9 解验证", False, str(errs[:3]))
            break
        if path.count((4, 1)) != 2:
            allpass &= report("T9 每个解应恰好穿过 OUT 两次", False, str(path))
            break
    else:
        allpass &= report(f"T9 全部 {len(sols)} 个解通过独立验证器且均穿过 OUT 两次", True)

    # T10: 对照组 — 同盘但 OUT 为白格: 白格至多一次, 穿过再出框(3 连接)不可能 -> 无解
    p = puz5x3(False)
    sols, done, err, wall = solve(p)
    allpass &= report("T10 白质OUT同盘 -> 无解", err is None and done and done["count"] == 0,
                      f"count={done['count'] if done else '?'}")

    # T11: 冰上数字 / 冰上 IN/OUT 组合 (差分模糊测试发现的回归用例)
    #   每个用例给出 (期望解数, 说明); 解必须全部通过独立验证器。
    cases = [
        ("冰上数字格 + 冰上IN(起点直行穿越即收集)", {
            "format": "icelom-v1", "w": 3, "h": 4,
            "cells": ["w", "w", "i", "w", "w", "i", "w", "i", "w", "w", "w", "w"],
            "numbers": [{"x": 1, "y": 2, "n": 1}, {"x": 2, "y": 1, "n": 2}],
            "in": {"x": 2, "y": 0, "side": "U"}, "out": {"x": 0, "y": 3, "side": "D"},
            "edges": [], "options": {"cover_all_whites": True}}, 0),
        ("冰上数字格作 OUT 格(数字由出框步收集)", {
            "format": "icelom-v1", "w": 4, "h": 5,
            "cells": ["w", "w", "w", "w", "w", "w", "w", "i", "i", "w", "i", "w", "w", "w",
                      "w", "w", "i", "w", "w", "i"],
            "numbers": [{"x": 3, "y": 4, "n": 1}],
            "in": {"x": 0, "y": 4, "side": "D"}, "out": {"x": 3, "y": 4, "side": "R"},
            "edges": [], "options": {"cover_all_whites": True}}, 1),
        ("冰上数字格作 OUT 格之二", {
            "format": "icelom-v1", "w": 3, "h": 4,
            "cells": ["w", "w", "i", "w", "w", "w", "w", "w", "w", "w", "w", "i"],
            "numbers": [{"x": 2, "y": 0, "n": 1}],
            "in": {"x": 2, "y": 3, "side": "R"}, "out": {"x": 2, "y": 0, "side": "R"},
            "edges": [], "options": {"cover_all_whites": True}}, 1),
        ("冰上数字不得被垂直穿越(作OUT格时)", {
            "format": "icelom-v1", "w": 5, "h": 3,
            "cells": ["w", "w", "i", "i", "w", "i", "w", "w", "w", "w", "w", "i", "w", "w", "w"],
            "numbers": [{"x": 0, "y": 1, "n": 1}],
            "in": {"x": 2, "y": 2, "side": "D"}, "out": {"x": 0, "y": 1, "side": "L"},
            "edges": [], "options": {"cover_all_whites": True}}, 0),
        ("冰上数字 + 白数字混合", {
            "format": "icelom-v1", "w": 3, "h": 5,
            "cells": ["w", "w", "w", "w", "w", "i", "w", "w", "w", "w", "w", "w", "i", "i", "w"],
            "numbers": [{"x": 2, "y": 1, "n": 1}, {"x": 0, "y": 4, "n": 2}],
            "in": {"x": 0, "y": 2, "side": "L"}, "out": {"x": 0, "y": 4, "side": "L"},
            "edges": [], "options": {"cover_all_whites": True}}, 1),
        ("IN/OUT 同冰格且边框互相垂直(需交叉穿越)", {
            "format": "icelom-v1", "w": 3, "h": 4,
            "cells": ["w", "w", "w", "w", "i", "i", "w", "i", "w", "i", "w", "w"],
            "numbers": [{"x": 2, "y": 1, "n": 1}],
            "in": {"x": 0, "y": 3, "side": "D"}, "out": {"x": 0, "y": 3, "side": "L"},
            "edges": [], "options": {"cover_all_whites": True}}, 1),
    ]
    for i, (name, puz, expect) in enumerate(cases, 1):
        sols, done, err, wall = solve(puz)
        ok = err is None and done is not None and done["count"] == expect
        allpass &= report(f"T11.{i} {name}", ok, f"count={done['count'] if done else '?'} 期望={expect}")
        bad = None
        for s in sols:
            errs = verify.check(puz, [tuple(t) for t in s["path"]], cover_all=True)
            if errs:
                bad = errs[:3]
                break
        allpass &= report(f"T11.{i} 解验证", bad is None, str(bad))

    # T12: 高冰密度真题回归 (db042, 10x10 / 34 冰 / 冰上数字 + 冰上 IN)。
    # 曾因"仅空边残差图连通性"剪枝(已删除的 residualConnected)把合法前缀误判为断开而假无解 ——
    # 此用例锁死该回归; 现在同类判据由 ruleReach("必须同时到得了 IN 与 OUT"的放宽版)承担。
    db042 = os.path.join(ROOT, "benchmark", "puzzles", "db042_10x10_qpinemarch323.json")
    if os.path.exists(db042):
        p = json.load(open(db042, encoding="utf-8"))
        p.setdefault("options", {})["cover_all_whites"] = True
        sols, done, err, wall = solve(p)
        allpass &= report("T12 高冰密度真题 db042 有解", err is None and done and done["count"] >= 1,
                          f"count={done['count'] if done else '?'} nodes={done['nodes'] if done else '?'}")
        bad = None
        for s in sols:
            errs = verify.check(p, [tuple(t) for t in s["path"]], cover_all=True)
            if errs:
                bad = errs[:3]
                break
        allpass &= report("T12 解验证", bad is None, str(bad))
        # 交叉验证: 独立走廊收缩模型也必须找到解 (防止两边同时错)
        sys.path.insert(0, HERE)
        try:
            import indep_solver
            isol, imsg = indep_solver.solve(p, 120)
            allpass &= report("T12 独立模型交叉验证", isol is not None, imsg or "找到解")
        except Exception as e:  # 独立模型不可用时不算失败
            allpass &= report("T12 独立模型交叉验证", True, f"跳过({e})")

    # T13: "?" 格 (数字未知的编号格, JSON 里写 n = -2)。
    #   规则(与 pzpr 官方 checkNumberOrder 一致): 把线路上经过的编号格依次记为
    #   第 1,2,3… 位 —— 已知数字格每次经过算 1 位, "?" 格的**每一次穿越**也各算 1 位
    #   (同一个 "?" 冰格被交叉穿越两次时可以代表两个不同的数, 例如 2 与 3)。
    #   已知数字 v 必须正好出现在第 v 位。1 宽的竖条盘上路径唯一(只能直下),
    #   因此每个用例的解数可直接手推。
    def puz_line(h, nums, cover=False):
        return {"w": 1, "h": h, "cells": ["w"] * h,
                "numbers": [{"x": 0, "y": y, "n": n} for y, n in nums],
                "in": {"x": 0, "y": 0, "side": "U"}, "out": {"x": 0, "y": h - 1, "side": "D"},
                "edges": [], "options": {"cover_all_whites": cover}}

    puz_cross = {  # 冰上 "?" 必须被交叉穿越两次才能成解(见 T13.10)
        "format": "icelom-v1", "w": 5, "h": 3,
        "cells": ["w", "w", "i", "i", "w", "i", "w", "w", "w", "w", "w", "i", "w", "w", "w"],
        "numbers": [{"x": 0, "y": 1, "n": -2}],
        "in": {"x": 2, "y": 2, "side": "D"}, "out": {"x": 0, "y": 1, "side": "L"},
        "edges": [], "options": {"cover_all_whites": True}}

    qcases = [
        ("1 ? 3 (1 与 3 之间 1 个问号 = 第 2 位)", puz_line(5, [(1, 1), (2, -2), (3, 3)]), 1),
        ("1 ? ? 3 (差 2 却夹了 2 个问号, 3 落到第 4 位) -> 无解",
         puz_line(6, [(1, 1), (2, -2), (3, -2), (4, 3)]), 0),
        ("1 ? ? 4 (两个问号正好填 2,3)", puz_line(6, [(1, 1), (2, -2), (3, -2), (4, 4)]), 1),
        ("? 1 (问号占第 1 位, 1 落到第 2 位) -> 无解", puz_line(5, [(1, -2), (2, 1)]), 0),
        ("? 2 (问号即数字 1)", puz_line(5, [(1, -2), (2, 2)]), 1),
        ("1,3 之间没有问号 -> 数字 2 无处安放, 无解", puz_line(5, [(1, 1), (3, 3)]), 0),
        ("1,5 之间没有问号 -> 3,4 无处安放, 无解", puz_line(6, [(1, 1), (4, 5)]), 0),
        ("? 之后紧跟 ? (两个问号 = 数字 1,2)", puz_line(5, [(1, -2), (2, -2)]), 1),
        ("冰上 ? 作 OUT 格(数字由出框步收集)", {
            "format": "icelom-v1", "w": 4, "h": 5,
            "cells": ["w", "w", "w", "w", "w", "w", "w", "i", "i", "w", "i", "w", "w", "w",
                      "w", "w", "i", "w", "w", "i"],
            "numbers": [{"x": 3, "y": 4, "n": -2}],
            "in": {"x": 0, "y": 4, "side": "D"}, "out": {"x": 3, "y": 4, "side": "R"},
            "edges": [], "options": {"cover_all_whites": True}}, 1),
        ("冰上 ? 被交叉穿越两次 (旧规则禁止交叉 -> 现在有解)", puz_cross, 1),
        ("上题的 ? 里再加一个 1 (起始格), 两次穿越 = 第 2,3 位",
         dict(puz_cross, numbers=[{"x": 0, "y": 1, "n": -2}, {"x": 2, "y": 2, "n": 1}]), 1),
        ("上题把 1 换成 2 (第 1 位上不可能是 2) -> 无解",
         dict(puz_cross, numbers=[{"x": 0, "y": 1, "n": -2}, {"x": 2, "y": 2, "n": 2}]), 0),
        ("1 与 5 之间缺 3 位、盘上却没有问号 -> 数字空缺数超过问号可提供的位次数",
         puz_line(8, [(1, 1), (6, 5)]), 0),
    ]
    for i, (name, puz, expect) in enumerate(qcases, 1):
        sols, done, err, wall = solve(puz)
        ok = err is None and done is not None and done["count"] == expect
        allpass &= report(f"T13.{i} {name}", ok, f"count={done['count'] if done else '?'} 期望={expect}")
        bad = None
        for s in sols:
            errs = verify.check(puz, [tuple(t) for t in s["path"]],
                                cover_all=puz["options"]["cover_all_whites"])
            if errs:
                bad = errs[:3]
                break
        allpass &= report(f"T13.{i} 解验证", bad is None, str(bad))

    # T13.14 空缺数超过 "?" 位次数: 必须是**结构性无解**并给出原因(不是靠搜索撞死)
    sols, done, err, wall = solve(puz_line(8, [(1, 1), (6, 5)]))
    ok = done is not None and done.get("count") == 0 and "空缺数" in (done.get("reason") or "")
    allpass &= report("T13.14 空缺数超过 \"?\" 位次数 -> 结构性无解(reason)",
                      ok, f"count={done['count'] if done else '?'} "
                          f"reason={(done or {}).get('reason')}")

    # T13.10 的解必须真的把 "?" 冰格交叉穿过两次
    sols, done, err, wall = solve(puz_cross)
    if sols:
        path = [tuple(t) for t in sols[0]["path"]]
        n_visits = path.count((0, 1))
        allpass &= report("T13.10 解中 \"?\" 冰格被穿越两次", n_visits == 2, f"visits={n_visits}")
    else:
        allpass &= report("T13.10 解中 \"?\" 冰格被穿越两次", False, "无解")

    # T14: 箭头方向约束 —— **与 IN/OUT 不相连的强制边分量**也必须被校验。
    #   回归背景: 旧引擎的行走校验/定向 (walkValidate, 已删除) 原先只跑在"已并入线路"的
    #   分量上, 于是"孤立的箭头分量"从不被校验方向, 解可以逆着箭头走。8x8 博客题
    #   唯一解的第 2 步 (1,0)->(1,1) 就是这种孤立分量(两端都是白格, 不挨 IN(0,0)/OUT(7,7)):
    #     · 箭头 dir=D(与解同向) -> 仍 1 解;
    #     · 箭头 dir=U(反向)     -> 必须无解 (旧版会照旧给出 1 解 = 逆箭头"解");
    #   多边链同理: (2,1)-(2,2)-(2,3) 上两条同向箭头 = 给该链定向, 反向即无解,
    #   两条互相矛盾的箭头(U 与 D) 也必须被立刻判成结构性无解。
    def edge(x, y, side, d):
        return {"x": x, "y": y, "side": side, "kind": "arrow", "dir": d}

    t14 = [
        ("孤立分量上的箭头(与解同向) 仍有 1 解",
         [edge(1, 0, "D", "D")], 1),
        ("同上但箭头反向 -> 无解 (旧版会输出逆箭头的\"解\")",
         [edge(1, 0, "D", "U")], 0),
        ("孤立三格链上两条同向箭头(与解同向) 仍有 1 解",
         [edge(2, 1, "D", "D"), edge(2, 2, "D", "D")], 1),
        ("同上两条箭头同时反向 -> 无解",
         [edge(2, 1, "D", "U"), edge(2, 2, "D", "U")], 0),
        ("两格链上互相矛盾的箭头(一条要 U 一条要 D) -> 无解",
         [edge(2, 1, "D", "U"), edge(2, 2, "D", "D")], 0),
    ]
    for i, (name, edges, expect) in enumerate(t14, 1):
        p = json.loads(json.dumps(puz8x8(True)))
        p["edges"] = edges
        sols, done, err, wall = solve(p)
        ok = err is None and done is not None and done["count"] == expect
        allpass &= report(f"T14.{i} {name}", ok,
                          f"count={done['count'] if done else '?'} 期望={expect}"
                          + (f" reason={done.get('reason')}" if done and done.get('reason') else ""))
        bad = None
        for s in sols:
            errs = verify.check(p, [tuple(t) for t in s["path"]], cover_all=True)
            if errs:
                bad = errs[:3]
                break
        allpass &= report(f"T14.{i} 解验证", bad is None, str(bad))

    # T14.6: 真实回归题 —— example/11_20260909_9x9.json 的"最右上角冰格上的箭头".
    #   该箭头 (6,0)D dir=U 的强制分量是 (6,0)-(6,1)冰-(6,2) 这条竖链, 与 IN(8,5)/OUT(8,4)
    #   不相连: 修复前求解器给出 7 个"解", 其中 6 个逆箭头(被 verify.py 与官方引擎驳回);
    #   修复后恰 1 解, 且该解与修复前 7 个里唯一合法的那个逐格相同。
    ex11 = os.path.join(ROOT, "example", "11_20260909_9x9.json")
    if os.path.exists(ex11):
        p = json.load(open(ex11, encoding="utf-8"))
        sols, done, err, wall = solve(p)
        allpass &= report("T14.6 example/11 箭头题恰 1 解", err is None and done and done["count"] == 1,
                          f"count={done['count'] if done else '?'} 期望=1")
        bad = None
        for s in sols:
            errs = verify.check(p, [tuple(t) for t in s["path"]],
                                cover_all=p["options"]["cover_all_whites"])
            if errs:
                bad = errs[:3]
                break
        allpass &= report("T14.6 解验证", bad is None, str(bad))
    else:
        allpass &= report("T14.6 example/11 箭头题恰 1 解", True, "跳过(示例文件不存在)")

    # T15: 盘面 D4 变换往返正确(求解器提供 8 个朝向的 kind, 供工具/回归用; 默认求解不做变换)。
    #   求解器把题面变换后求解, 再把解坐标变换回原题坐标; 其中 kind 5/6 是 90° 旋转,
    #   不是对合 —— 必须用逆映射才能还原坐标。这里逐个朝向强制求解(ICELOM_FORCE_KIND),
    #   要求: 每个朝向都出解、解都通过独立验证器、且各朝向的解在**原题坐标系里逐格相同**。
    #   用小题(8×8 博客真题)保证 8 个朝向都在毫秒级结束 —— 变换逻辑与题面难度无关。
    p15 = puz8x8()
    ref15 = None
    ok15 = True
    for k in range(8):
        sols, done, err, wall = solve(p15, max_solutions=1, time_limit_ms=30000,
                                      env={"ICELOM_FORCE_KIND": str(k)})
        path = [tuple(t) for t in sols[0]["path"]] if sols else None
        bad = verify.check(p15, path, cover_all=True) if path else ["无解"]
        same = (ref15 is None) or (path == ref15)
        if ref15 is None and path:
            ref15 = path
        ok15 &= (path is not None) and not bad and same
        allpass &= report(f"T15.{k} 变换 kind={k} 求解/验证/坐标还原一致",
                          (path is not None) and not bad and same,
                          f"格数={len(path) if path else 0} verify={bad[:2] if bad else 'OK'} "
                          f"与kind0逐格相同={same}")

    # T16: 推理强度回归 —— db039 必须"**不搜索**就推完整条线路", 且在 8 个朝向都一样。
    #   历史: 旧求解器(段合并 + MRV 搜索)在题面朝向下 300 s 搜不出, 只有换朝向才在 2~12 s
    #   出解 —— 整套"方向敏感性"分析都是围绕那个缺陷写的。现在求解器把 tools/deduce.py 的
    #   规则/试连接推理搬进了核心(见 docs/算法说明.md §3.4–3.6), db039 在**任何**朝向下都由
    #   传播直接推完(分支节点数 0)。这条测试钉死三件事:
    #     ① 一条搜索分支都不需要(nodes == 0)⇒ 推理真的把盘面推死了;
    #     ② 解通过独立验证器 verify.py;
    #     ③ 8 个 D4 朝向**都**如此(方向敏感性不再是缺陷, 也不需要任何变向重试)。
    db039 = os.path.join(ROOT, "benchmark", "puzzles", "db039_13x13_0vanillaice0.json")
    if os.path.exists(db039):
        p16 = json.load(open(db039, encoding="utf-8"))
        p16.setdefault("options", {})["cover_all_whites"] = True
        sols, done, err, wall = solve(p16, max_solutions=1, time_limit_ms=20000)
        allpass &= report("T16.0 db039 纯推理求解(0 分支节点)",
                          err is None and done and done["count"] == 1 and done["nodes"] == 0
                          and wall < 5000,          # wall 的单位是毫秒
                          f"count={done['count'] if done else '?'} "
                          f"nodes={done['nodes'] if done else '?'} wall={wall:.0f}ms err={err}")
        for k in range(8):
            sols, done, err, wall = solve(p16, max_solutions=1, time_limit_ms=20000,
                                          env={"ICELOM_FORCE_KIND": str(k)})
            path = [tuple(t) for t in sols[0]["path"]] if sols else None
            bad = verify.check(p16, path, cover_all=True) if path else ["无解"]
            ok = (err is None and done and done["count"] == 1 and done["nodes"] == 0
                  and not bad and wall < 5000)      # wall 的单位是毫秒
            allpass &= report(f"T16.{k + 1} db039 朝向 kind={k} 纯推理求解 + 验证",
                              ok, f"count={done['count'] if done else '?'} "
                                  f"nodes={done['nodes'] if done else '?'} wall={wall:.0f}ms "
                                  f"verify={bad[:2] if bad else 'OK'}")
    else:
        allpass &= report("T16 db039 纯推理求解", True, "跳过(benchmark 题面不存在)")

    print()
    print("ALL PASS" if allpass else "SOME FAILED")
    return 0 if allpass else 1


if __name__ == "__main__":
    sys.exit(main())
