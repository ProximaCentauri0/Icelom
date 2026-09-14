# -*- coding: utf-8 -*-
"""差分测试: 做题规则引擎 (icelom_gui.check_play_rules) vs pzprjs 官方 icelom check()。

同一个盘面状态分别用两套引擎判定, 结论必须一致:
  * pzprjs PASS  ⟺  规则引擎 complete;
  * 硬性违规 (分叉/交叉/冰格转弯/越出边框/数字位次) 双方都判 FAIL, 且规则引擎给出对应提示;
  * 未完成状态 (线路中断/白格未覆盖) 双方都判 FAIL, 但规则引擎只报"未完成"而不报违规。

用法: python tests/check_engine_pzprjs.py
"""
import json
import os
import subprocess as sp
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import icelom_gui as g

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build(name, w, h, ice, numbers, edges, fin, fout, kind, pz_code="", kw="", arrows=()):
    """kind: "pass" | "error" | "incomplete" (规则引擎的预期判定档位)。
    fin/fout = ((x, y), side); edges 为格对列表 (可含出界一格端点)。
    arrows 为 (起点格, 终点格) 列表 = "线路必须从前者走向后者" 的箭头标记。
    含箭头时必须走 pid "icebarn" 侧的官方判定 —— pzprjs 对 pid "icelom" 会把
    checkFollowArrow@icebarn 整条过滤掉(见 engine_diff_probe.js 顶部说明)。"""
    puz = g.Puzzle(w, h)
    for (x, y) in ice:
        puz.cells[y][x] = "i"
    puz.numbers = dict(numbers)
    puz.fin = {"x": fin[0][0], "y": fin[0][1], "side": fin[1]}
    puz.fout = {"x": fout[0][0], "y": fout[0][1], "side": fout[1]}
    E = {frozenset({tuple(a), tuple(b)}) for a, b in edges}
    DIRV = {"R": (1, 0), "D": (0, 1), "L": (-1, 0), "U": (0, -1)}
    DIRCODE = {"U": 1, "D": 2, "L": 3, "R": 4}

    def border_of(p):
        return [2 * p[0] + 1, 2 * p[1] + 1]

    def inout_border(f):
        dx, dy = g.DIRS[f[1]]
        return [2 * f[0][0] + 1 + dx, 2 * f[0][1] + 1 + dy]

    def arrow_key(a, b):
        """a->b 相邻移动的规范边键 + 行进方向名 (与 pzprurl2json/GUI 的规范一致)。"""
        d = {(1, 0): "R", (-1, 0): "L", (0, 1): "D", (0, -1): "U"}[(b[0] - a[0], b[1] - a[1])]
        if d == "R":
            return (a[0], a[1], "R"), d, [2 * a[0] + 2, 2 * a[1] + 1]
        if d == "L":
            return (b[0], b[1], "R"), d, [2 * a[0], 2 * a[1] + 1]
        if d == "D":
            return (a[0], a[1], "D"), d, [2 * a[0] + 1, 2 * a[1] + 2]
        return (b[0], b[1], "D"), d, [2 * a[0] + 1, 2 * a[1]]

    pz_arrows = []
    for a, b in arrows:
        key, d, bxby = arrow_key(tuple(a), tuple(b))
        puz.edge[key] = {"kind": "arrow", "dir": d}
        pz_arrows.append([bxby[0], bxby[1], DIRCODE[d]])

    lines = []
    for e in E:
        a, b = sorted(tuple(q) for q in e)
        lines.append([a[0] + b[0] + 1, a[1] + b[1] + 1])
    pz_state = {
        "name": name, "w": w, "h": h,
        "pid": "icebarn" if pz_arrows else "icelom",   # 只有 icebarn 侧才真校验箭头
        "ice": [y * w + x for (x, y) in ice],
        "numbers": {str(y * w + x): int(n) for (x, y), n in numbers.items()},
        "in": inout_border((fin[0], fin[1])),
        "out": inout_border((fout[0], fout[1])),
        "arrows": pz_arrows,
        "lines": lines,
    }
    return {"name": name, "puz": puz, "edges": E, "kind": kind,
            "pz_code": pz_code, "kw": kw, "pz_state": pz_state}


S = [
    # 正确直线: 2x1, IN 上 (0,0), OUT 右 (1,0)
    build("S1 正确直线", 2, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "pass"),
    # 冰格直行穿过 (冰 (0,0): 入界向下 → 直行)
    build("S2 冰格直行", 2, 2, [(0, 0)], {},
          [((0, 0), (0, -1)), ((0, 0), (0, 1)), ((0, 1), (1, 1)),
           ((1, 1), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "pass"),
    # 冰格转弯 → lnCurveOnIce
    build("S3 冰格转弯", 3, 2, [(0, 0)], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0)),
           ((2, 0), (2, 1)), ((2, 1), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (-1, 1))],
          ((0, 0), "U"), ((0, 1), "L"), "error", "lnCurveOnIce", "冰格"),
    # 白格分叉 (多一条出界短边) → lnBranch
    build("S4 白格分叉", 3, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0)),
           ((2, 0), (3, 0)), ((1, 0), (1, -1))],
          ((0, 0), "U"), ((2, 0), "R"), "error", "lnBranch", "分叉"),
    # 白格十字交叉 → lnCrossExIce
    build("S5 白格交叉", 3, 3, [], {},
          [((1, 0), (1, -1)), ((2, 2), (3, 2)),
           ((1, 1), (0, 1)), ((1, 1), (2, 1)), ((1, 1), (1, 0)), ((1, 1), (1, 2))],
          ((1, 0), "U"), ((2, 2), "R"), "error", "lnCrossExIce", "交叉"),
    # 从非 OUT 处越出边框 → lrOffField
    build("S6 非 OUT 出界", 3, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (1, -1))],
          ((0, 0), "U"), ((2, 0), "R"), "error", "lrOffField", "越出边框"),
    # 数字位次错误 (线路中段): 1,3,2 → 第 2 位出现 3 → lrOrder
    build("S7 位次错误", 3, 1, [], {(0, 0): 1, (1, 0): 3, (2, 0): 2},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))],
          ((0, 0), "U"), ((2, 0), "R"), "error", "lrOrder", "位次"),
    # 数字位次错误 (IN 格即错): 官方"完整判定"在此报的是其下游原因 lrOffField, 只核对"双方都判错"
    build("S7b 位次错误(起点)", 2, 1, [], {(0, 0): 2, (1, 0): 1},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "error", "", "位次"),
    # 数字位次正确
    build("S8 位次正确", 2, 1, [], {(0, 0): 1, (1, 0): 2},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "pass"),
    # "?" 格: 每次穿越各占一位 (两格都是 "?")
    build("S9 两个?格", 2, 1, [], {(0, 0): -2, (1, 0): -2},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "pass"),
    # 线路中断 (只画了入界线) → 官方 lrDeadEnd; 规则引擎只报"未完成"
    build("S10 线路中断", 2, 1, [], {},
          [((0, 0), (0, -1))],
          ((0, 0), "U"), ((1, 0), "R"), "incomplete", "lrDeadEnd"),
    # 白格未覆盖 (2x2 只画了上排) → 官方 cuNoLine; 规则引擎只报"未完成"
    build("S11 白格未覆盖", 2, 2, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "incomplete", "cuNoLine"),
    # 游离线段 (线路已成解 + 一条不接触线路的线) → lnPlLine
    build("S12 游离线段", 3, 3, [], {},
          [((0, 1), (-1, 1)), ((0, 1), (1, 1)), ((1, 1), (2, 1)), ((2, 1), (3, 1)),
           ((0, 0), (1, 0))],
          ((0, 1), "L"), ((2, 1), "R"), "error", "lnPlLine", "多余"),
    # ---- 箭头方向 (lrReverse / arNoLine) ----
    # pzprjs 只在 pid "icebarn" 侧校验内部箭头, 故含箭头的状态一律走 icebarn 判定;
    # 盘面全是白格、无数字, 两种 pid 的差异(冰区/白格覆盖检查)在这些状态里不生效。
    build("A1 箭头顺向", 2, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "pass", arrows=[((0, 0), (1, 0))]),
    build("A2 箭头逆向", 2, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0))],
          ((0, 0), "U"), ((1, 0), "R"), "error", "lrReverse", "逆箭头",
          arrows=[((1, 0), (0, 0))]),
    build("A3 两条同向箭头", 3, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))],
          ((0, 0), "U"), ((2, 0), "R"), "pass",
          arrows=[((0, 0), (1, 0)), ((1, 0), (2, 0))]),
    build("A4 两条矛盾箭头", 3, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))],
          ((0, 0), "U"), ((2, 0), "R"), "error", "lrReverse", "逆箭头",
          arrows=[((0, 0), (1, 0)), ((2, 0), (1, 0))]),
    #   官方在 A5 上报的是清单里更靠前的 lrDeadEnd(它命中第一个原因就停),
    #   箭头未被经过的原因 (arNoLine) 排在 checkAllArrow, 更靠后。
    build("A5 箭头所在边没有线", 3, 1, [], {},
          [((0, 0), (0, -1)), ((0, 0), (1, 0))],
          ((0, 0), "U"), ((2, 0), "R"), "incomplete", "lrDeadEnd",
          arrows=[((1, 0), (2, 0))]),
]


def main():
    states = [s["pz_state"] for s in S]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(states, fh, ensure_ascii=False)
        tmp = fh.name
    try:
        r = sp.run(["node", os.path.join(HERE, "engine_diff_probe.js"), tmp],
                   stdout=sp.PIPE, stderr=sp.PIPE, timeout=180)
        if r.returncode != 0:
            print("node 探针失败:", r.stderr.decode("utf-8", "replace")[:600])
            return 1
        official = json.loads(r.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    finally:
        os.unlink(tmp)

    ok = True
    print(f"{'状态':<14}{'pzprjs':<26}{'规则引擎':<44}判定")
    print("-" * 110)
    for st, pz in zip(S, official):
        errs, inc, complete, route, redges = g.check_play_rules(
            st["puz"], st["edges"], cover_all=True)
        pz_pass = bool(pz.get("complete"))
        pz_codes = pz.get("codes", []) or ([pz["error"]] if pz.get("error") else [])
        mine_pass = complete and not errs and not inc
        mine_txt = ("complete" if complete else
                    ("error: " + errs[0]) if errs else
                    ("incomplete: " + inc[0]) if inc else "?")
        good = (pz_pass == mine_pass)
        if st["kind"] == "pass":
            good = good and mine_pass and pz_pass
        elif st["kind"] == "error":
            # 双方都判 FAIL; 规则引擎必须给出"硬性违规"而不只是"未完成"
            good = good and not mine_pass and bool(errs) \
                and any(st["kw"] in e for e in errs)
            if st["pz_code"]:      # 官方引擎确切报出的原因 (可核对时)
                good = good and any(st["pz_code"] in c for c in pz_codes)
        else:  # incomplete: 双方都判未通过, 但规则引擎不报违规
            good = good and not mine_pass and not errs and bool(inc) \
                and any(st["pz_code"] in c for c in pz_codes)
        ok = ok and good
        print(f"{st['name']:<14}{('PASS' if pz_pass else ','.join(pz_codes)):<26}"
              f"{mine_txt[:42]:<44}{'OK' if good else 'MISMATCH'}")

    print()
    print("ENGINE VS PZPRJS: " + ("ALL MATCH" if ok else "MISMATCH"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
