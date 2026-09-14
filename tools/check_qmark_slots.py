# -*- coding: utf-8 -*-
"""check_qmark_slots.py — 用求解器的一个解，独立校验 "?" 位次模型（见 docs/算法说明.md §3.11）。

规则依据：pzprjs `icebarn` 的 `checkNumberOrder` —— 沿线第 p 次"编号格穿越"上的数字必须 == p。
因此对任意一个解都应有：
  ① 每个已知数字 v 恰好落在第 v 位；
  ② 每次 "?" 穿越落在的位次 p 不是任何已知数字的位次（等价于"已知数字之间空出来的位次由 ? 填"）；
  ③ "?" 穿越次数不超过上界 (问号总数 + 冰格问号数 − 空缺数)；
  ④ 计数强制的情形（空缺数 == 问号总数 + 冰格问号数）下，每个冰格 "?" 都被穿越两次（十字交叉）；
  ⑤ 已知数字之间夹的 "?" 穿越数恰好等于两者数字之差减一。

用法:
  python -X utf8 tools/check_qmark_slots.py <谜题.json> [朝向] [--mode first|unique] [--limit-ms N]
  # 朝向 ∈ none/flip-x/flip-y/rot180/transpose/rot90/rot270/anti-t（默认 none）
输出: 逐条结论 + 退出码（0 = 全部一致）
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import measure_transforms as mt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle")
    ap.add_argument("transform", nargs="?", default="none", choices=list(mt.KIND_COMPOSE))
    ap.add_argument("--mode", default="first", choices=["first", "unique", "all"])
    ap.add_argument("--limit-ms", type=int, default=120000)
    ap.add_argument("--solver", default=mt.SOLVER)
    args = ap.parse_args()

    with open(args.puzzle, encoding="utf-8") as f:
        puz = json.load(f)
    tp = mt.apply_kind(puz, args.transform)
    tp.setdefault("options", {})["cover_all_whites"] = True
    tp["limits"] = {"mode": args.mode, "time_limit_ms": args.limit_ms, "max_solutions": 1}
    p = subprocess.run([args.solver], input=json.dumps(tp).encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    path, done = None, None
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o.get("type") == "solution" and path is None:
            path = [tuple(pt) for pt in o["path"]]
        elif o.get("type") == "done":
            done = o
    name = os.path.basename(args.puzzle)
    if path is None:
        print(f"{name} [{args.transform}]: 未求出解（done={done}），无法校验")
        return 2

    W = tp["w"]
    ice = {(i % W, i // W) for i, c in enumerate(tp["cells"]) if c == "i"}
    num = {(e["x"], e["y"]): e["n"] for e in tp.get("numbers", [])}
    known = sorted(v for v in num.values() if v > 0)
    knownSet = set(known)
    Vmax = max(known) if known else 0
    gap = Vmax - len(known)
    nQ = sum(1 for v in num.values() if v == -2)
    nQI = sum(1 for xy, v in num.items() if v == -2 and xy in ice)
    tail = nQ + nQI - gap
    bad = []

    # 逐格走一遍解路径，累计"编号穿越"位次
    slot, qslots, at = 0, [], {}
    for xy in path:
        n = num.get(xy)
        if n is None:
            continue
        slot += 1
        at[slot] = (xy, n)
        if n > 0:
            if n != slot:
                bad.append(f"① 已知数字 {n} 落在第 {slot} 位")
        else:
            qslots.append(slot)
            if slot in knownSet:
                bad.append(f"② \"?\" 穿越落在已知数字 {slot} 的位次上")
    if qslots and max(qslots) > Vmax + max(tail, 0):
        bad.append(f"③ \"?\" 穿越位次 {max(qslots)} 超过上界 {Vmax}+{max(tail, 0)}")
    if tail < 0:
        bad.append(f"③ 空缺数 {gap} 超过问号可提供的穿越数 {nQ + nQI}（结构无解）")

    # ④ 计数强制交叉
    cnt = Counter(path)
    forced = gap == nQ + nQI and nQI > 0
    for xy, v in sorted(num.items(), key=lambda t: (t[1], t[0])):
        if v != -2:
            continue
        if forced and xy in ice and cnt[xy] != 2:
            bad.append(f"④ 计数强制交叉的 \"?\" 格 {xy} 只被穿越 {cnt[xy]} 次")

    # ⑤ 已知数字之间的 "?\" 穿越数
    ks = sorted(k for k in at if at[k][1] > 0)
    for a, b in zip(ks, ks[1:]):
        va, vb = at[a][1], at[b][1]
        between = sum(1 for p in range(a + 1, b) if at[p][1] == -2)
        if between != vb - va - 1:
            bad.append(f"⑤ 数字 {va}→{vb} 之间夹了 {between} 次 \"?\" 穿越，应为 {vb - va - 1}")

    print(f"{name} [{args.transform}]: 解 {len(path)} 格；已知数字 {known}；Vmax={Vmax} gap={gap} "
          f"问号={nQ}(冰上 {nQI})")
    print(f"  编号穿越共 {slot} 次；\"?\" 穿越位次 = {sorted(qslots)}")
    for xy, v in sorted(num.items(), key=lambda t: (t[1], t[0])):
        if v == -2:
            print(f"    \"?\" 格 {xy}（{'冰' if xy in ice else '白'}）穿越 {cnt[xy]} 次")
    if bad:
        print("结论: 不一致 ✗")
        for b in bad:
            print("  -", b)
        return 1
    print("结论: 位次模型与解一致 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
