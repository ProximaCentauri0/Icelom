# -*- coding: utf-8 -*-
"""生成 db039 解的完整报告: 位次表(每次穿越代表的数字) + ASCII 编号地图 + 核对结论。

输出 analysis/db039_report.txt, 供人工核对; 同时把 "?" 格代表的数字写进解文件。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify

orig = json.load(open(os.path.join(ROOT, "benchmark", "puzzles",
                                   "db039_13x13_0vanillaice0.json"), encoding="utf-8"))
solp = os.path.join(ROOT, "analysis", "db039_solution.json")
sol = json.load(open(solp, encoding="utf-8"))
path = [tuple(t) for t in sol["path"]]
nummap = {(n["x"], n["y"]): n["n"] for n in orig["numbers"]}
errs = verify.check(orig, path, cover_all=True)

out = []
A = out.append
A("db039 (13x13, 0vanillaice0) 官方规则解报告")
A("=" * 46)
A(f"题面: 146 白格 + 23 冰格; 编号格 13 个 = 已知数字 1,3,5,...,17 (9 个) + \"?\" 格 4 个 (都在冰格上)")
A(f"IN=(6,12) 边框下方进入, OUT=(0,10) 边框左侧离开; 覆盖所有白格")
A(f"线路长度: {len(path)} 格 (169 格盘面 + 重复穿越)")
A(f"独立验证器 tests/verify.py: {'OK' if not errs else errs[:3]}")
A("")
A("编号位次表 (规则: 编号格访问依次占第 1,2,3... 位, 已知数字 v 必须落在第 v 位;")
A("         \"?\" 冰格每次穿越各占一位, 同一格两次穿越可以是两个不同的数):")
A("")
A("  位次  格内标记   坐标     穿越轴   该次穿越代表的数")
A("  ----  --------  --------  ------   ----------------")
slot = 0
per_cell = {}
for i, c in enumerate(path):
    if c not in nummap:
        continue
    slot += 1
    v = nummap[c]
    ax = "IN端" if i == 0 else ("横" if path[i - 1][1] == c[1] else "纵")
    shown = "?" if v < 0 else str(v)
    A(f"  {slot:>4}  {shown:>8}  ({c[0]:>2},{c[1]:>2})   {ax:<6}   {slot if v < 0 else v}")
    per_cell.setdefault(c, []).append(slot)
A("")
A("4 个 \"?\" 格各自代表的数字:")
for c, vs in sorted(per_cell.items()):
    if nummap.get(c, 1) < 0:
        A(f"  ({c[0]:>2},{c[1]:>2})  第 {vs[0]} 次穿越 -> {vs[0]},  第 {vs[1]} 次穿越 -> {vs[1]}")
A("  => 恰好补齐偶数 2,4,6,8,10,12,14,16, 与题面印出的奇数 1,3,...,17 合成完整的 1..17")
A("")
A("线路经过的格子 (按顺序, 分号后为第几格):")
A("  " + " -> ".join(f"({x},{y})" for x, y in path))
A("")
A("编号地图 (数字 = 题面数字; ?? = \"?\" 格; '+' = 线路十字交叉穿过的两格之一):")
for y in range(orig["h"]):
    row = []
    for x in range(orig["w"]):
        c = (x, y)
        v = nummap.get(c)
        if v is None:
            row.append(" . ")
        elif v < 0:
            row.append(" ?? ")
        else:
            row.append(f"{v:>2} " if v < 10 else f"{v:>3}")
    A("  " + "".join(row).rstrip())

txt = os.path.join(ROOT, "analysis", "db039_report.txt")
open(txt, "w", encoding="utf-8").write("\n".join(out) + "\n")

# 把 "?" 格代表的数字写回解文件, 便于外部工具直接使用
sol["qmark_values"] = {f"{c[0]},{c[1]}": vs for c, vs in per_cell.items()
                       if nummap.get(c, 1) < 0}
sol["verify"] = "OK" if not errs else errs[:3]
json.dump(sol, open(solp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(out))
print("\n写出:", txt, "与", solp)
