# -*- coding: utf-8 -*-
"""按"人怎么推"的顺序出一份推导报告 + 盘面图:

  1. 题面结构(白/冰/编号格、IN/OUT、覆盖要求);
  2. **规则级传播不动点**: 规则 + 逐格逐方向试连接能推出哪些边;
  3. **计数推论**: `已知数字数 + 2×"?"冰格数` 与最大数字的关系 ⇒ 每个 "?" 必须穿越几次、
     只能代表哪些数(db039: 4 个 "?" 必须十字交叉两次, 只能代表 2,4,…,16);
  4. **可解性规律的地面真值核对**(用的是"凡解必满足"的几何事实, 不是猜测):
     * 真解里每个编号格只被访问一次(已知数字格与"?"冰格各一次);
     * 任意两编号格之间: 路径步数与曼哈顿距离**同奇偶**;
     * 曼哈顿距离 <= 步数 (显然), 以及 "位次差 <= 步数 + 1"(编号穿越不能凭空出现)。
  5. 结论: 哪些边是**规则唯一确定**的、哪些位置仍然有多个候选("推无可推"的边界在哪)。

用法:
    python -X utf8 tools/deduce_report.py <题.json> --solution <解.json>
                                         [--id db039] [--no-probe] [--png analysis/xxx.png]
产物: stdout 报告 + 可选 PNG(analysis/<id>_deduce.png)。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from deduce import Board, Deduce, UNKNOWN, USED, FORBID  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def out(msg=""):
    print(msg, flush=True)


def numbered_visits(puz, path):
    """返回 [(路径下标, 坐标)]: 真解里每一次"编号格访问"(已知数字格 / "?" 格的每次穿越)。"""
    nums = {(n["x"], n["y"]) for n in puz.get("numbers", [])}
    return [(i, tuple(p)) for i, p in enumerate(path) if tuple(p) in nums]


def check_laws(puz, path):
    """核对"凡解必满足"的几条规律, 返回 (结论列表, 是否全部成立)。"""
    res = []
    nums = {(n["x"], n["y"]): n["n"] for n in puz.get("numbers", [])}
    vis = numbered_visits(puz, path)
    dup = {}
    for _, p in vis:
        dup[p] = dup.get(p, 0) + 1
    bad_dup = {p: c for p, c in dup.items() if nums.get(p, 0) > 0 and c > 1}
    res.append(("真解里**已知数字格**只被访问一次", not bad_dup, bad_dup))
    n_slot = len(vis)
    res.append(("编号格访问次数 == 已知数字数 + 2×\"?\"冰格数(每个 \"?\" 各两次)",
                n_slot == sum(1 for v in nums.values() if v > 0)
                + 2 * sum(1 for p, v in nums.items() if v < 0
                          and puz["cells"][p[1] * puz["w"] + p[0]] == "i"),
                n_slot))
    # 位次 = 访问序号; 已知数字 v 必须落在第 v 位
    bad_slot = []
    for idx, (_, p) in enumerate(vis, start=1):
        v = nums[p]
        if v > 0 and v != idx:
            bad_slot.append((p, v, idx))
    res.append(("已知数字 v 正好落在第 v 位(官方位次规则)", not bad_slot, bad_slot[:3]))
    # 位次可填性: 第 p 位若没有已知数字, 必须由 "?" 填
    known = {v for v in nums.values() if v > 0}
    bad_fill = []
    for idx, (_, p) in enumerate(vis, start=1):
        if nums[p] < 0 and idx in known:
            bad_fill.append((p, idx))
    res.append(("没有 \"?\" 占用已知数字的位次", not bad_fill, bad_fill[:3]))
    # 几何规律: 任意两编号格之间 步数 ≡ 曼哈顿 (mod 2) 且 步数 >= 曼哈顿
    bad_par = []
    for j in range(len(vis)):
        for k in range(j + 1, len(vis)):
            i1, p1 = vis[j]
            i2, p2 = vis[k]
            gap = i2 - i1
            man = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
            if gap < man or (gap - man) % 2:
                bad_par.append((p1, p2, gap, man))
    res.append(("任意两编号格之间: 步数 >= 曼哈顿 且 与曼哈顿同奇偶", not bad_par, bad_par[:3]))
    # 位次差的上界: 每一步至多推进一个位次
    bad_k = []
    for j in range(len(vis)):
        for k in range(j + 1, len(vis)):
            i1, _ = vis[j]
            i2, _ = vis[k]
            if (k - j) > (i2 - i1) + 1:
                bad_k.append((vis[j][1], vis[k][1], k - j, i2 - i1))
    res.append(("位次差 <= 两者之间的步数 + 1", not bad_k, bad_k[:3]))
    return res, all(ok for _, ok, _ in res)


def main():
    ap = argparse.ArgumentParser(description="IceLom 推导报告(规则传播 + 计数推论 + 地面真值核对)")
    ap.add_argument("puzzle")
    ap.add_argument("--solution", required=True, help="已知真解 JSON(用于核对)")
    ap.add_argument("--id", default=None)
    ap.add_argument("--no-probe", action="store_true", help="只跑规则, 不做逐格试连接")
    ap.add_argument("--png", default=None, help="顺便渲染盘面图")
    args = ap.parse_args()

    puz = json.load(open(args.puzzle, encoding="utf-8"))
    path = [tuple(p) for p in json.load(open(args.solution, encoding="utf-8"))["path"]]
    pid = args.id or os.path.splitext(os.path.basename(args.puzzle))[0]

    out("=" * 78)
    out("IceLom 推导报告: %s" % pid)
    out("=" * 78)
    out("题面: %dx%d, 白格 %d, 冰格 %d, 编号格 %d(已知 %d / \"?\" %d), IN=%s, OUT=%s, 覆盖所有白格=%s"
        % (puz["w"], puz["h"],
           sum(1 for c in puz["cells"] if c == "w"),
           sum(1 for c in puz["cells"] if c == "i"),
           len(puz.get("numbers", [])),
           sum(1 for n in puz.get("numbers", []) if n["n"] > 0),
           sum(1 for n in puz.get("numbers", []) if n["n"] < 0),
           (puz["in"]["x"], puz["in"]["y"]), (puz["out"]["x"], puz["out"]["y"]),
           puz.get("options", {}).get("cover_all_whites", True)))
    out("真解: %d 步(含冰格交叉的重复格)" % len(path))

    board = Board(puz)
    board.build_stems()
    d = Deduce(board)
    alive = d.fixpoint(probe=not args.no_probe)
    det = [e for e in range(len(board.edges))
           if not board.edges[e]["frame"] and d.used[e] == USED]
    und = [e for e in range(len(board.edges))
           if not board.edges[e]["frame"] and d.used[e] == UNKNOWN]
    forb = [e for e in range(len(board.edges))
            if not board.edges[e]["frame"] and d.used[e] == FORBID]

    out()
    out("-" * 78)
    out("【1】规则级传播 + 逐格试连接(%s)"
        % ("纯规则" if args.no_probe else "规则 + 逐格逐方向试连(不动点)"))
    out("-" * 78)
    out("传播结论: %s" % ("无矛盾" if alive else "**出现矛盾(题面在规则下无解)**"))
    out("  规则唯一确定的边: %d 条 %s"
        % (len(det), sorted(tuple(board.edges[e]["key"]) for e in det) if det else ""))
    out("  仍未排除的候选边: %d 条; 已被规则排除: %d 条" % (len(und), len(forb)))
    from collections import Counter
    cnt = Counter(len(d.avail(c)) for c in range(board.w * board.h))
    out("  各格候选边数分布: %s" % ", ".join("%d条=%d格" % (k, cnt[k]) for k in sorted(cnt)))
    amb = [c for c in range(board.w * board.h) if len(d.avail(c)) > 2]
    out("  仍有分支的格(候选边 > 2): %d 个 —— 这些格就是 规则推不下去 的地方" % len(amb))

    si = getattr(d, "slot_info", None)
    if si:
        vmax, gap, empty = si["vmax"], si["gap"], si["empty_below"]
        nq_i, nq_w = si["n_qice"], si["n_qwhite"]
        out()
        out("-" * 78)
        out("【2】\"?\" 位次模型(计数推论, 只用题面与规则)")
        out("-" * 78)
        out("  最大已知数字 Vmax=%d; 已知数字 %d 个 ⇒ 第 1..%d 位里空着 %d 个: %s"
            % (vmax, si["n_known"], vmax, gap, empty))
        out("  \"?\" 格 %d 个(冰上 %d, 白格 %d); 冰上 \"?\" 最多被穿越两次 ⇒ 最多提供 %d 次穿越"
            % (nq_i + nq_w, nq_i, nq_w, 2 * nq_i + nq_w))
        if gap > 2 * nq_i + nq_w:
            out("  ⇒ 空缺数超过问号能提供的位次数: **结构上无解**")
        elif gap == 2 * nq_i + nq_w:
            out("  ⇒ 空缺数恰好等于问号能提供的位次数 ⇒ **每个 \"?\" 冰格都必须被十字交叉穿越两次**,"
                " 且空缺位次只能由它们填满 ⇒ \"?\" 格代表的数字集合 = %s" % (empty,))
        else:
            out("  ⇒ 有余量(%d 次), 不能断定每个 \"?\" 都穿越两次" % (2 * nq_i + nq_w - gap))
        for c in range(board.w * board.h):
            if board.num_of(c) is None or board.num_of(c) >= 0:
                continue
            out("     \"?\" 格 %s(%s): 位次区间 [%d,%d] ⇒ 可能是这些数: %s"
                % (board.xy(c), "冰" if board.is_ice(c) else "白",
                   si["lo"][c], si["hi"][c],
                   [p for p in range(max(si["lo"][c], 1), min(si["hi"][c], si["slot_max"]) + 1)
                    if p > vmax or p in set(empty)]))

    out()
    out("-" * 78)
    out("【3】地面真值核对(用真解验证 凡解必满足 的规律)")
    out("-" * 78)
    laws, all_ok = check_laws(puz, path)
    for name, ok, detail in laws:
        out("  [%s] %s%s" % ("OK" if ok else "违背", name, ("  " + str(detail)) if detail else ""))
    out("  ⇒ %s" % ("全部成立" if all_ok else "**有不成立的规律**(说明该规律不是普遍成立的, 不能用来剪枝)"))

    # 可靠性: 确定边必须都在真解里
    from deduce import path_to_edge_states
    sol = path_to_edge_states(board, path)
    wrong = [tuple(board.edges[e]["key"]) for e in det if e not in sol]
    over = [tuple(board.edges[e]["key"]) for e in forb if e in sol]
    out()
    out("【4】可靠性: 确定边全部出现在真解里 = %s; 被排除的边里没有真解边 = %s"
        % ("是" if not wrong else "**否** %s" % wrong,
           "是" if not over else "**否** %s" % over))

    if args.png:
        sys.path.insert(0, ROOT)
        import icelom_render
        state = {"determined": [[board.edges[e]["key"][0], board.edges[e]["key"][1],
                                 board.edges[e]["key"][2]] for e in det],
                 "possible": [[board.edges[e]["key"][0], board.edges[e]["key"][1],
                               board.edges[e]["key"][2]] for e in und],
                 "cell_table": [{"x": board.xy(c)[0], "y": board.xy(c)[1],
                                 "avail": len(d.avail(c))}
                                for c in range(board.w * board.h)],
                 "show_avail": False}
        icelom_render.render_state(
            puz, state, cell=56, scale=3, out_png=args.png,
            title="%s 规则推导不动点: 粉=确定要走的边(%d 条), 灰虚线=仍未排除的候选边(%d 条)"
                  % (pid, len(det), len(und)))
        out()
        out("盘面图: %s" % args.png)
    return 0 if (alive and all_ok and not wrong and not over) else 1


if __name__ == "__main__":
    sys.exit(main())
