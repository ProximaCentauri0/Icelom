# -*- coding: utf-8 -*-
"""独立 ground-truth 求解器: 走廊收缩模型 (与 C++ 主求解器完全不同的实现思路)。

- 冰廊(连续直线冰格)收缩为白格结点之间的一条边; 白格相邻也构成边。
- 目标: 哈密顿路径(覆盖所有白格) IN->OUT, 每条边至多用一次。
- 冰格交叉: 两条垂直廊共用一格, 逐格轴占用表判定; 已知数字的冰格禁止被垂直穿越,
  而 "?" 冰格**允许**被十字交叉穿越两次(两个轴各一次)。
- 数字位次规则(与 pzpr 官方一致): 线路上经过的编号格依次计第 1,2,3… 位 ——
  已知数字格每次经过算 1 位, "?" 格的每一次穿越也各算 1 位(同一格被穿过两次
  = 两个不同的数, 例如 2 与 3); 已知数字 v 必须正好落在第 v 位。
仅支持白质 OUT; 用于独立交叉验证主求解器结论。
用法: python tests/indep_solver.py <puzzle.json> [时限秒]
作为交叉验证工具被 tests/run_tests.py 的 T12 调用。
"""
import json
import sys
import time


def solve(puz, limit_s=120, verbose=False):
    w, h = puz["w"], puz["h"]
    cells = puz["cells"]
    nums = {(n["x"], n["y"]): n["n"] for n in puz.get("numbers", [])}
    IN, OUT = puz["in"], puz["out"]
    inCell = (IN["x"], IN["y"])
    outCell = (OUT["x"], OUT["y"])
    D = {"R": (1, 0), "D": (0, 1), "L": (-1, 0), "U": (0, -1)}

    def ctype(c):
        return cells[c[1] * w + c[0]]

    runs = []
    seen = set()
    for y in range(h):
        for x in range(w):
            if ctype((x, y)) != "i":
                continue
            for dx, dy, ax in ((1, 0, 0), (0, 1, 1)):
                px, py = x - dx, y - dy
                if 0 <= px < w and 0 <= py < h and ctype((px, py)) == "i":
                    continue
                cx, cy = x, y
                rc = []
                a = b = None
                if 0 <= px < w and 0 <= py < h and ctype((px, py)) == "w":
                    a = (px, py)
                while 0 <= cx < w and 0 <= cy < h and ctype((cx, cy)) == "i":
                    rc.append((cx, cy))
                    cx += dx
                    cy += dy
                if 0 <= cx < w and 0 <= cy < h and ctype((cx, cy)) == "w":
                    b = (cx, cy)
                key = (rc[0], ax)
                if key in seen:
                    continue
                seen.add(key)
                runs.append(dict(a=a, b=b, cells=rc, axis=ax,
                                 nums=sorted(nums[c] for c in rc if c in nums)))

    edges = []
    for y in range(h):
        for x in range(w):
            if ctype((x, y)) != "w":
                continue
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and ctype((nx, ny)) == "w":
                    edges.append(((x, y), (nx, ny), -1))
    for i, r in enumerate(runs):
        if r["a"] and r["b"]:
            edges.append((r["a"], r["b"], i))

    start = inCell
    pre_runs = []
    if ctype(inCell) == "i":
        din = D[{"R": "L", "L": "R", "U": "D", "D": "U"}[IN["side"]]]
        for i, r in enumerate(runs):
            if inCell in r["cells"] and r["axis"] == (0 if din[0] else 1):
                pre_runs.append(i)
                cx, cy = inCell
                while True:
                    cx += din[0]
                    cy += din[1]
                    if not (0 <= cx < w and 0 <= cy < h):
                        return None, "IN run exits frame (bad puzzle)"
                    if ctype((cx, cy)) == "w":
                        start = (cx, cy)
                        break
                break
    goal = outCell
    if ctype(outCell) != "w":
        return None, "ice-OUT unsupported by independent checker"
    if start == goal:
        return None, "IN==OUT degenerate, skipped"

    nodes_needed = {(x, y) for y in range(h) for x in range(w) if ctype((x, y)) == "w"}
    adj = {}
    for i, (a, b, ri) in enumerate(edges):
        adj.setdefault(a, []).append(i)
        adj.setdefault(b, []).append(i)

    edge_used = [False] * len(edges)
    cell_axes = {}
    visited = {start}
    order = [start]
    # 数字位次状态: [已收集的编号格数 pos]。已知数字 v 必须正好是第 v 个编号格访问。
    # left_known: 尚未收集的已知数字集合 —— 已知数字必须按升序收集, 因此下一个
    # 被收集的已知数字只能是其中最小的那个(与 v == pos 等价, 用作快速剪枝)。
    st = [0]
    left_known = set(v for v in nums.values() if v > 0)
    seen_num = set()

    def num_step(c, s):
        """收集一次编号格访问(已知数字格 / "?" 格的某一次穿越), 返回 (是否合法, 新状态)。"""
        v = nums[c]
        pos = s[0] + 1
        if v > 0:
            if v != pos or (left_known and v != min(left_known)):
                return False, s
            left_known.discard(v)
        seen_num.add(c)
        return True, [pos]

    t0 = time.time()
    result = []
    steps = [0]

    def con_ok(cur):
        # 残余图 = 未访问结点 ∪ {cur}; 边 = 未用边且两端都在该集合内。
        # 必要条件: 单连通 + 除 cur/goal 外每点度数>=2, cur/goal >=1。
        # (cur 必须计入残余图, 否则"只能从 cur 连出去"的格子会被误判为死点)
        keep = set(nodes_needed) - visited
        keep.add(cur)
        seen = {goal}
        stack = [goal]
        degres = {}
        while stack:
            c = stack.pop()
            d = 0
            for ei in adj.get(c, []):
                if edge_used[ei]:
                    continue
                a, b, _ = edges[ei]
                o = b if a == c else a
                if o not in keep:
                    continue
                d += 1
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
            degres[c] = d
        for nd in keep:
            if nd not in seen:
                return False
        for nd, d in degres.items():
            need = 1 if (nd == goal or nd == cur) else 2
            if d < need:
                return False
        return True

    def dfs(cur):
        steps[0] += 1
        if steps[0] % 2048 == 0 and time.time() - t0 > limit_s:
            raise TimeoutError
        if len(visited) == len(nodes_needed):
            # 所有白格已覆盖; 必须终止于 OUT 且所有编号格(含 "?")都至少被经过一次
            if cur == goal and seen_num == set(nums):
                result.append(list(order))
                return True
            return False
        if not con_ok(cur):
            return False
        for ei in adj.get(cur, []):
            if edge_used[ei]:
                continue
            a, b, ri = edges[ei]
            nxt = b if a == cur else a
            if nxt in visited:
                continue
            if nxt == goal and len(visited) != len(nodes_needed) - 1:
                continue
            r = runs[ri] if ri >= 0 else None
            if r is not None:
                # 冰廊占用: 同轴重叠非法; 垂直交叉合法; 已知数字的冰格不可被交叉,
                # "?" 冰格可被两个轴各穿一次(每次各占一个数字位次)
                ok = True
                for c in r["cells"]:
                    used = cell_axes.get(c)
                    if used is not None and r["axis"] in used:
                        ok = False
                        break
                    if used and nums.get(c, -2) > 0:
                        ok = False
                        break
                if not ok:
                    continue
                # 廊上的编号格按实际行进方向收集(廊可能是反向穿过的)
                cells_order = r["cells"] if r["a"] == cur else list(reversed(r["cells"]))
                vals = [c for c in cells_order if c in nums]
                if nxt in nums:
                    vals.append(nxt)   # 落地白格上的编号格
                prev_st = list(st)
                got = []                     # 本步收集到的已知数字(回溯时放回)
                for c in vals:
                    ok, st[:] = num_step(c, st)
                    if not ok:
                        break
                    if nums[c] > 0:
                        got.append(nums[c])
                if ok:
                    edge_used[ei] = True
                    for c in r["cells"]:
                        cell_axes.setdefault(c, set()).add(r["axis"])
                    visited.add(nxt)
                    order.append(nxt)
                    if dfs(nxt):
                        return True
                    for c in r["cells"]:
                        cell_axes[c].discard(r["axis"])
                        if not cell_axes[c]:
                            del cell_axes[c]
                    edge_used[ei] = False
                    visited.discard(nxt)
                    order.pop()
                left_known.update(got)
                st[:] = prev_st
            else:
                prev_st = list(st)
                got = []
                ok = True
                if nxt in nums:
                    ok, st[:] = num_step(nxt, st)
                    if ok and nums[nxt] > 0:
                        got.append(nums[nxt])
                if ok:
                    visited.add(nxt)
                    order.append(nxt)
                    if dfs(nxt):
                        return True
                    visited.discard(nxt)
                    order.pop()
                left_known.update(got)
                st[:] = prev_st
        return False

    sys.setrecursionlimit(1000000)
    for i in pre_runs:
        r = runs[i]
        for c in r["cells"]:
            cell_axes.setdefault(c, set()).add(r["axis"])
        # IN 侧冰廊上的编号格: 按行进方向收集
        cx, cy = inCell
        while 0 <= cx < w and 0 <= cy < h and ctype((cx, cy)) == "i":
            if (cx, cy) in nums:
                okp, st[:] = num_step((cx, cy), st)
                if not okp:
                    return None, "IN run number order fail"
            cx += din[0]
            cy += din[1]
    # IN 廊尽头那个白格(起点)自己也可能带编号, 必须一并收集
    if start in nums:
        okp, st[:] = num_step(start, st)
        if not okp:
            return None, "start cell number order fail"
    if verbose:
        print("nodes:", len(nodes_needed), "edges:", len(edges), "runs:", len(runs),
              "start:", start, "goal:", goal, "pre_runs:", pre_runs, file=sys.stderr)
    try:
        dfs(start)
    except TimeoutError:
        return None, "timeout (steps=%d)" % steps[0]
    if result:
        return result[0], None
    return None, "no solution (exhaustive, steps=%d)" % steps[0]


if __name__ == "__main__":
    puz = json.load(open(sys.argv[1], encoding="utf-8"))
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 120
    sol, msg = solve(puz, limit, verbose=True)
    if sol:
        print("SOLUTION FOUND, cells on path:", len(sol))
        print(json.dumps(sol))
    else:
        print("NO SOLUTION:", msg)
