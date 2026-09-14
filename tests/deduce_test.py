# -*- coding: utf-8 -*-
"""规则级推导器 (tools/deduce.py) 的回归测试。

守两件事:
  ① **可靠性**: 推导器给出的"确定边"必须全部出现在真解里(推错 = 规则实现有 bug);
     同时用"把真解所有边都标成强制边"的合成题面反问一次: 每条确定边都被那条真解用到。
  ② **计数推论**: "?" 冰格在`已知数字数 + 2×"?"冰格数 == 最大数字`时必须被穿越两次
     (db039 的 4 个 "?" = 2,4,…,16), 且传播过程不得出现任何矛盾。

用法: python -X utf8 tests/deduce_test.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

import verify                                    # noqa: E402
from deduce import (Board, Deduce, UNKNOWN, USED, FORBID, DIRS,  # noqa: E402
                    path_to_edge_states, deduced_path)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OK = True


def report(name, cond, detail=""):
    global OK
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  " + str(detail))[:240] if detail else ""))
    OK = OK and cond


def solve(puz, ms=60000):
    p = json.loads(json.dumps(puz))
    p["options"] = {"cover_all_whites": True, "symmetry_retry": True}
    p["limits"] = {"max_solutions": 1, "time_limit_ms": ms}
    r = subprocess.run([os.path.join(ROOT, "icelom_solver.exe")],
                       input=json.dumps(p).encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
    lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    sols = [json.loads(l) for l in lines if '"solution"' in l]
    return [tuple(q) for q in sols[0]["path"]] if sols else None


def load(f):
    return json.load(open(os.path.join(ROOT, f), encoding="utf-8"))


def deduce_run(puz, probe):
    b = Board(puz)
    b.build_stems()
    d = Deduce(b)
    alive = d.fixpoint(probe=probe)
    det = [e for e in range(len(b.edges))
           if not b.edges[e]["frame"] and d.used[e] == USED]
    und = [e for e in range(len(b.edges))
           if not b.edges[e]["frame"] and d.used[e] == UNKNOWN]
    return b, d, alive, det, und


def check_case(tag, puzfile, solfile, expect_qmark_double=None, probe_when_pinned=True):
    puz = load(puzfile)
    path = None
    if solfile and os.path.exists(os.path.join(ROOT, solfile)):
        path = [tuple(q) for q in load(solfile)["path"]]
    if path is None:
        path = solve(puz)
    report(f"{tag}: 拿到真解", path is not None)
    if path is None:
        return
    errs = verify.check(puz, path)
    report(f"{tag}: 真解通过独立验证器", not errs, errs[:2])

    for probe in (False, True):
        b, d, alive, det, und = deduce_run(puz, probe)
        name = "纯规则" if not probe else "纯规则+逐格试连"
        report(f"{tag}[{name}]: 传播无矛盾", alive,
               [e[1] for e in d.events[-2:]] if not alive else "")
        if not alive:
            continue
        sol = path_to_edge_states(b, path)
        wrong = [b.edges[e]["key"] for e in det if e not in sol]
        report(f"{tag}[{name}]: 确定边 {len(det)} 条全部在真解里(没推错)", not wrong,
               wrong[:5])
        # 反向可靠性: 不许把真解要走的边判成"禁"(那同样是推错)
        forb = [e for e in range(len(b.edges))
                if not b.edges[e]["frame"] and d.used[e] == FORBID]
        over = [b.edges[e]["key"] for e in forb if e in sol]
        report(f"{tag}[{name}]: 被排除的 {len(forb)} 条边没有一条在真解里(没推过头)",
               not over, over[:5])
        # 每条确定边都要真的可能被用: 把它们作为"强制边"喂给 C++ 求解器继续求解。
        # 难例(db039)钉死后可能搜不出来 —— 这种情况只做记录, 不算失败
        # (可靠性已由上面两条 + 独立验证器给足: 确定边逐条出现在官方判定通过的真解里)。
        if not probe or not probe_when_pinned:
            continue
        pin = json.loads(json.dumps(puz))
        pin["edges"] = [{"x": b.edges[e]["key"][0], "y": b.edges[e]["key"][1],
                         "side": b.edges[e]["key"][2], "kind": "segment"} for e in det]
        pin["options"] = {"cover_all_whites": True}
        pin["limits"] = {"max_solutions": 1, "time_limit_ms": 20000}
        r = subprocess.run([os.path.join(ROOT, "icelom_solver.exe")],
                           input=json.dumps(pin).encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
        lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
        got = [json.loads(l) for l in lines if '"solution"' in l]
        report(f"{tag}[{name}]: 把 {len(det)} 条确定边钉死后仍能搜到解",
               bool(got), lines[-1][:120] if lines else "无输出")
    # 计数推论
    b, d, alive, det, und = deduce_run(puz, True)
    si = getattr(d, "slot_info", None)
    if expect_qmark_double is not None and si:
        report(f"{tag}: 计数推论断言(每个 \"?\" 冰格穿越两次)",
               si["gap"] == si["n_qice"] * 2 + si["n_qwhite"],
               (si["gap"], si["n_qice"], si["n_qwhite"]))
        report(f"{tag}: \"?\" 格只能代表空缺位次 {si['empty_below']}",
               si["empty_below"] == expect_qmark_double, si["empty_below"])


def check_db039_target():
    """db039 的**验收目标**(验收目标): 逐格逐方向试连推到不动点后, 确定边数 >= 35。

    并且逐条核对 9 格那一步推理的结论(手工推导的结果):
    9→左、9→下 都不可行 ⇒ 9 的需求度数是 2 ⇒ 9 必须与上方、右方相连。
    另外核: 推到不动点后**整条线路都定死了**(0 条未定), 且还原出来的线路
    能通过 `tests/verify.py` 这个独立验证器。
    """
    puz = load(os.path.join("benchmark", "puzzles", "db039_13x13_0vanillaice0.json"))
    b, d, alive, det, und = deduce_run(puz, True)
    report("db039 目标: 试连不动点后确定边数 >= 35", len(det) >= 35, len(det))
    if not alive:
        return
    c9 = b.cid(3, 10)
    want_used, want_forbid = set(), set()
    for dk, s in enumerate(DIRS):
        e = b.cell_edges[c9][dk]
        if e is None or e < 0 or b.edges[e]["frame"]:
            continue
        (want_forbid if s in ("L", "D") else want_used).add(e)
    states = {e: d.used[e] for e in want_used | want_forbid}
    report("db039: 9 往左不可行(禁)", all(states[e] == FORBID for e in want_forbid),
           [b.edges[e]["key"] for e in want_forbid if states[e] != FORBID])
    report("db039: 9 必须连上方与右方", all(states[e] == USED for e in want_used),
           [b.edges[e]["key"] for e in want_used if states[e] != USED])
    report("db039: 试连不动点后整条线路推完(0 条未定)", not und, len(und))
    if not und:
        p2 = deduced_path(b, d)
        errs = verify.check(puz, p2) if p2 else ["无法还原线路"]
        report("db039: 推出来的整条线路通过独立验证器", not errs, errs[:2])


def check_db042_complete():
    """db042 上这套推理能**整题推完**(确定边 = 真解的 84 条边, 无未定边)。"""
    f = os.path.join("benchmark", "puzzles", "db042_10x10_qpinemarch323.json")
    if not os.path.exists(os.path.join(ROOT, f)):
        return
    puz = load(f)
    b, d, alive, det, und = deduce_run(puz, True)
    report("db042: 试连不动点后无未定边(整条线路推完)", alive and not und,
           "%d 确定 / %d 未定" % (len(det), len(und)))


def check_same_cell_inout():
    """**同格 IN/OUT**（同一个角冰格的两条互相垂直外边框 = 冰上垂直交叉）。

    历史坑: `deg_bounds` 早先只认"一条端点轴"（`ax0`），同格 IN/OUT 被算成
    "端点轴 1 条 + 另一轴 0 或 2 条"，而真解是"两条轴各 1 条" ⇒ 试连把每条走法都否掉，
    推导器直接报**假无解**（假矛盾）。判据改成与求解器一致的口径：边框边按轴计数，
    冰格每条轴"边框边 + 格内边" ∈ {0, 2}。
    """
    puz = {"format": "icelom-v1", "w": 3, "h": 3,
           "cells": ["i", "w", "w", "w", "i", "w", "w", "w", "w"],
           "numbers": [],
           "in": {"x": 0, "y": 0, "side": "L"}, "out": {"x": 0, "y": 0, "side": "U"},
           "edges": [], "options": {"cover_all_whites": True}}
    path = solve(puz)
    report("同格IN/OUT: 拿到真解", path is not None)
    if path is None:
        return
    report("同格IN/OUT: 真解通过独立验证器", not verify.check(puz, path),
           verify.check(puz, path)[:2])
    b, d, alive, det, und = deduce_run(puz, True)
    report("同格IN/OUT: 传播无矛盾 (不得报假无解)", alive,
           [e[1] for e in d.events[-2:]] if not alive else "")
    if not alive:
        return
    sol = path_to_edge_states(b, path)
    wrong = [b.edges[e]["key"] for e in det if e not in sol]
    report(f"同格IN/OUT: {len(det)} 条确定边全部在真解里", not wrong, wrong[:5])
    report("同格IN/OUT: 整条线路推完 (0 条未定)", not und, len(und))
    if not und:
        p2 = deduced_path(b, d)
        errs = verify.check(puz, p2) if p2 else ["无法还原线路"]
        report("同格IN/OUT: 推出来的线路通过独立验证器", not errs, errs[:2])


def main():
    # db039: 13x13, 9 个已知数字 1,3,…,17 + 4 个 "?" 冰格 ⇒ 计数强制交叉两次
    check_case("db039", os.path.join("benchmark", "puzzles", "db039_13x13_0vanillaice0.json"),
               None,  # 旧 analysis/db039_solution.json 已删, 现场求解(毫秒级)即真解
               expect_qmark_double=[2, 4, 6, 8, 10, 12, 14, 16],
               probe_when_pinned=False)
    check_db039_target()
    # 经典 9x9(已知数字 1..9, 无 "?")
    check_case("经典9x9", os.path.join("example", "01_经典9x9.json"), None)
    # 博客 8x8
    check_case("博客8x8", os.path.join("example", "02_博客8x8.json"), None)
    # db042: 10x10 高冰密度真题(曾触发假无解的那个)
    db42 = "db042_10x10_qpinemarch323.json"
    if os.path.exists(os.path.join(ROOT, "benchmark", "puzzles", db42)):
        check_case("db042", os.path.join("benchmark", "puzzles", db42), None)
        check_db042_complete()
    # 同格 IN/OUT(角冰格两条互相垂直外边框): 推导器不得报假无解
    check_same_cell_inout()

    print("ALL PASS" if OK else "*** 有失败 ***")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
