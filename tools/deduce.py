# -*- coding: utf-8 -*-
"""IceLom 规则级推导器: 只用"每条规则 + 单元传播"把盘面推到**推无可推**的不动点。

为什么单独写一个推导器(而不是只靠求解器):

  * 求解器的推理层与这里**同源但实现不同**(C++ vs Python): 求解器不输出"每个格还剩几种走法、
    每个 "?" 可能是哪些数"这类中间信息, 也不做"用真解核对每条结论"的可靠性审计;
  * 两套独立实现互为交叉验证: `tests/deduce_test.py` 每次都核对"推导器给出的确定边必须
    全部出现在真解里、被判禁的边一条都不在真解里", `tests/run_tests.py` T16 则钉住求解器
    在 db039 上同样 0 分支节点推完;
  * 中间盘面要的是"**规则推出的**确定边 + 仍未定的候选格", 这件事的本质是
    约束传播 (constraint propagation), 与搜索是两件事;
  * 本模块因此**按规则重写一遍传播**, 判据与 `tests/verify.py` / `docs/算法说明.md`
    第 4 节逐条对应(白格度数 2、冰格只能直行且每轴至多一次、"?" 冰格可十字交叉两次、
    覆盖所有白格、编号格落在自己的位次、IN/OUT 出框/入框方向)。

规则清单(每条都是"规则本身的推论", 不含任何猜测):

  R1 格内配置一致性: 每个格允许的"用边集合"必须非空(按格类型 + 当前可用边枚举);
     一条边只在**所有**允许配置里都出现时才是必用边。
  R2 冰段(ice stem)闭合: 线路在连通冰区里必须**一路直行到底** —— 冰区里任一被用的
     边界边, 必然连带整条贯穿该冰区的直线段一起被用(段两端落在非冰格或盘外)。
     于是"用一条边"= "用整条冰段"; 一段里只要有一条边被禁, 整段作废。
  R3 连通/无环: 边集最终必须是一条 IN→OUT 的简单路径, 于是
     ① 一条边若两端已被已用边连通(按**节点**算: 冰格两条轴是两个独立节点) ⇒ 用它必成环 ⇒ 禁用;
     ② 某格的连通块若到不了 IN 或到不了 OUT ⇒ 该块整个到不了线路上 ⇒ 块内边禁用;
     ③ 块的"线路接口数"= 出块边数 + 块内已用边数, 若为 0 则块永远接不上线路。
  R4 逐格逐方向**试连接**(`close_by_probe`, 主算法): 对每个格、每条还没定的
     候选边分别试"用"与试"禁" ——
       * 试"用"不可行(顺方向走撞死 / 合并后**路径检查**不过) ⇒ 这条边必禁;
       * 试"禁"不可行 ⇒ 这条边必用; 该格所有可行走法共有的边 ⇒ 必用; 只剩一种走法 ⇒ 全定。
     一有更新就刷新盘面并**从第一个格重新扫**, 直到一整轮扫完没有任何更新。
     全程确定性、无搜索、无递归。

**路径检查**(判定与官方 pzpr `checkNumberOrder` 同一条规则):
试连接后沿方向走下去 —— 冰格必须直行, 所以"接着冰格的那条边"是必被用的(即使它还没定);
撞到不可连接格(度数已满 / 冰格穿不过) ⇒ 这个方向不可行; 撞到别的路径段端点 ⇒ **路径合并**。
合并后对整条候选链做检查: 从起点遍历到终点, 每次"编号格访问"占第 1,2,3… 位:
  * 已知数字 v 必须落在第 v 位 ⇒ 链上所有已知数字的 (v − 局部序号) 必须一致
    ("数字必须一个个递增, 不能跳跃"), 相邻两个已知数字 a<b 之间必须正好 b−a−1 次 "?" 访问;
  * "?" 是通配符: 它的位次必须落在"?"选择集内(不是已知数字的位次, 且 ≤ slot_max),
    从第一个 "?" 起逐个赋值, 只要**存在**一种满足条件的赋值就可行;
  * 起点是 IN ⇒ 第一个位次必须是 1(第一个碰到的数字必须是 1);
  * 终点是 OUT ⇒ 到达 OUT 时位次必须已经走到 Vmax(**未达最大数字不能碰 OUT**)。

用法:
    python -X utf8 tools/deduce.py <题.json> [--out analysis/<id>_deduce.json]
                                   [--solution <解.json>] [--no-probe] [-v]

输出(stdout 中文报告 + 可选 JSON 状态文件):
    * 每个格的不动点信息(可用边、必用边、剩余配置数); 只打印**有分支的格**;
    * "确定边 / 仍未定边" 的统计;
    * 若给了 `--solution`: 用已知解做可靠性核对 —— 确定边必须全在解里(否则"推错"),
      仍未定的边里至少要有一条出现在解里(否则"推漏")。
"""
import argparse
import json
import sys
from collections import Counter

# 与 icelom_solver.cpp / icelom_gui.py / tests/verify.py 一致的方向序: R, D, L, U
DIRS = ("R", "D", "L", "U")
DV = {"R": (1, 0), "D": (0, 1), "L": (-1, 0), "U": (0, -1)}
OPP = {"R": "L", "L": "R", "U": "D", "D": "U"}
AXIS_OF = {"R": 0, "L": 0, "D": 1, "U": 1}      # 0 = 横轴, 1 = 竖轴

UNKNOWN, USED, FORBID = 0, 1, 2


def report(msg):
    print(msg, flush=True)


class Board(object):
    """题面 + 拓扑(格、边、冰段)。只读。"""

    def __init__(self, puz):
        self.w = puz["w"]
        self.h = puz["h"]
        self.cells = list(puz["cells"])
        self.numbers = {}
        for n in puz.get("numbers", []):
            self.numbers[self.cid(n["x"], n["y"])] = n["n"]
        self.walls = set()
        for ed in puz.get("edges", []):
            if ed.get("kind") == "wall":
                if "key" in ed:
                    self.walls.add(tuple(ed["key"]))
                else:
                    self.walls.add((ed["x"], ed["y"], ed["side"]))
        self.IN = (puz["in"]["x"], puz["in"]["y"])
        self.OUT = (puz["out"]["x"], puz["out"]["y"])
        self.IN_side = puz["in"]["side"]
        self.OUT_side = puz["out"]["side"]
        self.cover_all = bool(puz.get("options", {}).get("cover_all_whites", False))
        # 先建 cell_edges 容器, 再逐格逐方向建边(_cross/_frame_edge 会写进去)
        self.edges = []
        self.idx = {}
        self.cell_edges = [[None, None, None, None] for _ in range(self.w * self.h)]
        for y in range(self.h):
            for x in range(self.w):
                for s in DIRS:
                    self._cross(x, y, s)
        for which, side in (("IN", self.IN_side), ("OUT", self.OUT_side)):
            if side:
                self._frame_edge(which, side)
        # 冰段(拓扑)与墙: 由 build_stems 填充
        self.edge_stem = [-1] * len(self.edges)
        self.cell_stems = [[] for _ in range(self.w * self.h)]
        self.stems = []

    def cid(self, x, y):
        return y * self.w + x

    def xy(self, c):
        return (c % self.w, c // self.w)

    def edge_key(self, x, y, side):
        """归一化边键: 竖边存左格 R, 横边存上格 D, 边框存边框格外向 side。"""
        dx, dy = DV[side]
        nx, ny = x + dx, y + dy
        if 0 <= nx < self.w and 0 <= ny < self.h:
            if side == "R":
                return (x, y, "R")
            if side == "L":
                return (x - 1, y, "R")
            if side == "D":
                return (x, y, "D")
            return (x, y - 1, "D")
        return (x, y, side)

    def _cross(self, x, y, s):
        """从 (x,y) 沿 s 穿过的边号; 盘外返回 -1 (IN/OUT 的边框边除外)。"""
        dx, dy = DV[s]
        nx, ny = x + dx, y + dy
        if 0 <= nx < self.w and 0 <= ny < self.h:
            k = self.edge_key(x, y, s)
            e = self.idx.get(k)
            if e is None:
                e = len(self.edges)
                self.idx[k] = e
                self.edges.append({"a": self.cid(x, y), "b": self.cid(nx, ny), "key": k,
                                   "axis": AXIS_OF[s], "frame": False})
                for c, d2 in ((self.cid(x, y), s), (self.cid(nx, ny), OPP[s])):
                    self.cell_edges[c][DIRS.index(d2)] = e
            return e
        if (x, y) == self.IN and self.IN_side == s:
            return self._frame_edge("IN", s)
        if (x, y) == self.OUT and self.OUT_side == s:
            return self._frame_edge("OUT", s)
        return -1

    def _frame_edge(self, which, s):
        k = ("frame", which, s)
        e = self.idx.get(k)
        if e is None:
            e = len(self.edges)
            self.idx[k] = e
            cell = self.cid(*(self.IN if which == "IN" else self.OUT))
            self.edges.append({"a": cell, "b": -1, "key": k, "axis": AXIS_OF[s],
                               "frame": True})
            self.cell_edges[cell][DIRS.index(s)] = e
        return e

    def frame_edge_of(self, which):
        s = self.IN_side if which == "IN" else self.OUT_side
        if s is None:
            return None
        return self.idx.get(("frame", which, s))

    # ---------- 格类型 ----------
    def kind(self, c):
        """W 白格 / I 冰格 / IN / OUT。"""
        p = self.xy(c)
        if p == self.IN:
            return "IN"
        if p == self.OUT:
            return "OUT"
        return "I" if self.cells[c] == "i" else "W"

    def is_ice(self, c):
        return c is not None and c >= 0 and self.cells[c] == "i"

    def deg_bounds(self, c):
        """该格**格内边**(不含 IN/OUT 的边框边)最终被用条数的允许取值。

        边框边是"线路的出入口", 它**不是**格内边, 因此不计在这份度数里(也不进配置枚举):

        * IN 格: 入框边之外还要走一条**同轴**格内边(白质从入框边直接转出; 冰质沿入框轴直行);
          冰质 IN 之后再被**垂直穿过**一次(如与 OUT 同格)则是 3 条;
        * OUT 格: 出框边之外, 白质 1 条; 冰质"沿出框轴进格后出框"1 条,
          "先垂直穿过再沿出框轴出框"(穿过 OUT 两次)是 3 条;
        * 普通白格恰好 2 条; 普通冰格 0 / 2 / 4 条(两条轴各 0 或 2)。

        历史坑: 早先把边框边也算进配置的度数(`IN=(2,)` 靠"边框边 + 1 条格内边"凑),
        于是白质 OUT 格只剩下"边框边自己"这一种配置、冰质 OUT 格被垂直穿过时凑不出度数 ——
        db017 / db019 / db033 三道真题上直接报出**假矛盾**。
        """
        k = self.kind(c)
        if k == "W":
            return (2,)
        if k == "I":
            return (0, 2, 4)
        side = self.IN_side if k == "IN" else self.OUT_side
        if side is None:
            # 内部 IN/OUT(无边框方向): 按普通格处理(本推导器只对边框 IN/OUT 做入框/出框约束)
            return (2,) if not self.is_ice(c) else (0, 2, 4)
        return (1, 3) if self.is_ice(c) else (1,)

    def num_of(self, c):
        return self.numbers.get(c)

    def on_path(self, c):
        """该格是否必须位于线路上。冰格可以完全不经过(coverage 只要求白格)。"""
        return self.kind(c) != "I" or self.num_of(c) is not None

    # ---------- 冰段 ----------
    def build_stems(self):
        """把每条边归入唯一的"冰段"(贯穿一个连通冰区的一条直线)。

        从边 (c0→c1) 出发, 分别在 c0 与 c1 两侧沿该边轴向把**连通冰格**一路直行,
        直到碰到非冰格或盘外 —— 那一步所穿的边即段端点。非冰格旁的边自成闭段。
        """
        self.stems = []
        self.edge_stem = [-1] * len(self.edges)
        self.cell_stems = [[] for _ in range(self.w * self.h)]

        def walk(cell, axis, fwd):
            """从 cell 沿 axis 正/负方向直行, 返回 (经过的冰格, 穿过的边)。"""
            cells_seq, es = [], []
            cur = cell
            while True:
                x, y = self.xy(cur)
                d = ("R" if fwd else "L") if axis == 0 else ("D" if fwd else "U")
                e_next = self.cell_edges[cur][DIRS.index(d)]
                dx, dy = DV[d]
                nx, ny = x + dx, y + dy
                inside = 0 <= nx < self.w and 0 <= ny < self.h
                if not inside or self.cells[self.cid(nx, ny)] != "i":
                    # 终止那一步所穿的**格内边**才是本段的边界边; 走出盘外时那条边是
                    # IN/OUT 的**边框边**, 它不是格内边、不属于任何冰段(否则会被"整段必用"
                    # 顺带标成 USED —— db042/db017/db026 上的假矛盾就是这么来的)。
                    if (e_next is not None and e_next >= 0
                            and not self.edges[e_next]["frame"]):
                        es.append(e_next)
                    return cells_seq, es
                if e_next is None or e_next < 0 or self._is_wall(e_next):
                    return cells_seq, es
                es.append(e_next)
                cur = self.cid(nx, ny)
                cells_seq.append(cur)

        for e in range(len(self.edges)):
            if self.edge_stem[e] >= 0:
                continue
            ed = self.edges[e]
            ice_end = next((c for c in (ed["a"], ed["b"]) if self.is_ice(c)), None)
            if ed["frame"] or ice_end is None:
                self.edge_stem[e] = len(self.stems)
                self.stems.append([e])
                continue
            axis = ed["axis"]
            cells_seq, es = [ice_end], [e]
            for fwd in (False, True):
                cs, ex = walk(ice_end, axis, fwd)
                cells_seq += cs
                es += ex
            es = sorted(set(es))
            sid = len(self.stems)
            self.stems.append(es)
            for e2 in es:
                self.edge_stem[e2] = sid
            for c2 in set(cells_seq):
                self.cell_stems[c2].append(sid)
        self.cell_stems = [sorted(set(v)) for v in self.cell_stems]

    def _is_wall(self, e):
        return self.edges[e]["key"] in self.walls


class Deduce(object):
    """不动点传播器。状态 = 每条边的 USED / UNKNOWN / FORBID。"""

    def __init__(self, board, verbose=False):
        self.b = board
        self.verbose = verbose
        self.n = len(board.edges)
        self.used = bytearray(self.n)
        self.alive = True
        self.events = []
        self._need = None
        self.slot_info = None
        for e in range(self.n):
            if board._is_wall(e):
                self.used[e] = FORBID

    # ---------- 基本写入 ----------
    def mark(self, e, st, why=""):
        if not self.alive:
            return False
        cur = self.used[e]
        if cur == st:
            return False
        if cur != UNKNOWN:
            self.alive = False
            self.events.append(("矛盾", why, e, cur, st))
            return False
        self.used[e] = st
        if self.verbose:
            self.events.append(("推", why, e, cur, st))
        return True

    def avail(self, c):
        """该格当前**可能被用**的格内边(不含 IN/OUT 的边框边 —— 边框边是出入口, 恒定性)。"""
        return [e for e in self.b.cell_edges[c]
                if e is not None and e >= 0 and not self.b.edges[e]["frame"]
                and self.used[e] != FORBID]

    def used_edges(self, c):
        return [e for e in self.b.cell_edges[c]
                if e is not None and e >= 0 and self.used[e] == USED]

    def deg(self, c):
        return len(self.used_edges(c))

    # ---------- R1: 格内配置一致性 ----------
    def must_cross_twice(self):
        """计数推论(只用题面与规则): 哪些编号格**必须被穿越两次**。

        依据: 线路上的"编号格访问"依次占第 1,2,3… 位(已知数字 v 必须在第 v 位),
        最大数字 Vmax 必须落在第 Vmax 位 ⇒ 线路上至少有 Vmax 个位次;
        而位次数 = 已知数字个数 + ("?" 白格穿越次数 ≤1) + ("?" 冰格穿越次数 ≤2)。
        ⇒ 空缺数 G = Vmax − 已知数字个数 必须由 "?" 的穿越填满:
           * G > "?"白格数 + 2×"?"冰格数 ⇒ 结构无解;
           * G == "?"白格数 + 2×"?"冰格数(修满上限才刚好够) ⇒ **每一个**冰格 "?" 都必须
             被穿越两次、且每个白格 "?" 都要被穿越一次;
           * 中间(docstring 历史坑): 早先写成"G − 白格"?"数 ≥ 冰格"?"数 ⇒ 每个冰格 "?" 都
             穿越两次", 那是**不成立**的: 需要的是 G 次穿越, 只要 G 还没顶到上限,
             "1+1" 式的分配同样可行(例: 2 个冰格 "?"、G = 2 时两格各穿越一次也满足)。
             所以这里只在"无余量"时下结论。

        返回: {cell: 必须的穿越次数}, 不可行时返回 None。
        """
        if getattr(self, "_need", None) is not None:
            return self._need
        b = self.b
        nums = [(c, b.num_of(c)) for c in range(b.w * b.h) if b.num_of(c) is not None]
        known = [v for c, v in nums if v > 0]
        if not known:
            self._need = {}
            return self._need
        vmax = max(known)
        nq_i = [c for c, v in nums if v < 0 and b.is_ice(c)]
        nq_w = [c for c, v in nums if v < 0 and not b.is_ice(c)]
        gap = vmax - len(known)
        if gap > len(nq_w) + 2 * len(nq_i):
            self._need = None                     # 结构无解(空缺数超过问号能提供的位次数)
            return self._need
        all2 = (gap >= len(nq_w) + 2 * len(nq_i))  # 无余量 ⇒ 每个 "?" 冰格都必须穿越两次
        need = {}
        for c in nq_w:
            need[c] = 1
        for c in nq_i:
            need[c] = 2 if all2 else 1
        self._need = need
        return need

    def cell_configs(self, c):
        """该格所有与当前状态相容的配置(= 还需新用的**格内**边集合)。空列表 = 矛盾。

        判据(与 `icelom_solver.cpp` 的节点模型一致):

        * 白格 1 个节点、冰格 2 个轴节点(横/竖), 每个轴节点度数 **0 或 2**;
        * 例外是 **IN/OUT 所在的那条轴**: IN 格"入框边 + 同轴 1 条格内边"、OUT 格
          "沿出框轴 1 条格内边 + 出框边", 因此该轴正好 1 条格内边;
          IN/OUT 冰格**另一条轴**仍可以是 0 或 2(被垂直穿过一次);
        * **编号格必须被经过**: 已知数字的冰格只能被穿越一次(只能是它自己那条轴的 2 条边;
          作 IN/OUT 格时是"边框边 + 1 条"); "?" 冰格在计数强制时必须十字交叉两次
          (两条轴各一次 ⇒ 普通格 4 条边; 作 IN/OUT 格时是 1 + 2 条)。
        """
        b = self.b
        k = b.kind(c)
        u = self.used_edges(c)
        needdeg = set(b.deg_bounds(c))
        nv = b.num_of(c)
        ice_num = b.is_ice(c) and nv is not None
        must2 = bool(ice_num and self.must_cross_twice().get(c, 1) == 2)
        side = b.IN_side if k == "IN" else (b.OUT_side if k == "OUT" else None)
        ax0 = AXIS_OF[side] if side is not None else None

        def ok(sub):
            all_e = u + list(sub)
            d = len(all_e)
            if d not in needdeg:
                return False
            axs = {}
            for e in all_e:
                axs.setdefault(b.edges[e]["axis"], []).append(e)
            if not b.is_ice(c):
                return True                                # 白格: 度数已由 needdeg 定死
            n_ax0 = len(axs.get(ax0, ())) if ax0 is not None else None
            for ax, es in axs.items():                     # 冰格每条轴 0 或 2 条
                if ax == ax0:
                    continue
                if len(es) != 2:
                    return False
            if ax0 is not None and n_ax0 != 1:             # IN/OUT 那条轴: 正好 1 条格内边
                return False
            if nv is not None and nv > 0:
                # 已知数字的冰格: 必须被经过, 且只能穿越一次(不能十字交叉)
                if ax0 is not None:
                    if n_ax0 != 1 or d != 1:
                        return False
                elif len(axs) != 1 or len(list(axs.values())[0]) != 2:
                    return False
            elif nv is not None and nv < 0:
                # "?" 冰格: 必须被经过(至少一次穿越); 被计数强制时必须十字交叉两次
                if ax0 is not None:
                    if n_ax0 != 1:
                        return False
                    if must2 and len(axs.get(1 - ax0, ())) != 2:
                        return False
                elif not axs or any(len(es) != 2 for es in axs.values()):
                    return False
                elif must2 and len(axs) != 2:
                    return False
            return True

        cands = [e for e in self.avail(c) if self.used[e] != USED]
        res = []

        def rec(i, cur):
            if len(res) > 8192:
                return
            if i == len(cands):
                if ok(cur):
                    res.append(tuple(cur))
                return
            rec(i + 1, cur)
            cur.append(cands[i])
            rec(i + 1, cur)
            cur.pop()

        rec(0, [])
        return res

    def rule_cells(self):
        ch = False
        for c in range(self.b.w * self.b.h):
            cf = self.cell_configs(c)
            if not cf:
                self.alive = False
                self.events.append(("矛盾", "格 %s(%s) 无任何合法配置"
                                    % (self.b.xy(c), self.b.kind(c)), -1, 0, 0))
                return False
            common = set(cf[0])
            for t in cf[1:]:
                common &= set(t)
            for e in sorted(common):
                if self.mark(e, USED, "格 %s 的所有配置都含它" % (self.b.xy(c),)):
                    ch = True
        return ch

    # ---------- R2: 冰段闭合 ----------
    def stem_viable(self, s):
        """段 s 是否还能被用: 段内无边被禁 + 段经过的每格都还能沿该轴直行。"""
        b = self.b
        es = b.stems[s]
        if any(self.used[e] == FORBID for e in es):
            return False
        axis = b.edges[es[0]]["axis"]
        for c in range(len(b.cells)):
            if s not in b.cell_stems[c]:
                continue
            pair = [e for e in b.cell_edges[c]
                    if e is not None and e >= 0 and b.edges[e]["axis"] == axis]
            if len(pair) < 2:
                return False
            if any(self.used[e] == FORBID for e in pair):
                return False
        return True

    def rule_stems(self):
        ch = False
        b = self.b
        for s in range(len(b.stems)):
            es = b.stems[s]
            if any(self.used[e] == FORBID for e in es):
                for e in es:
                    if self.mark(e, FORBID, "冰段 %d 内有边被禁" % s):
                        ch = True
                continue
            if any(self.used[e] == USED for e in es):
                if not self.stem_viable(s):
                    self.alive = False
                    self.events.append(("矛盾", "已用冰段 %d 无法直行到底" % s, -1, 0, 0))
                    return False
                for e in es:
                    if self.mark(e, USED, "冰段 %d 已有一边被用(整段必用)" % s):
                        ch = True
        return ch

    # ---------- R2b: 编号格的"连接可行性" ----------
    def rule_nums(self):
        """编号格的连接可行性(位次模型的廉价前置判据)。

        **相邻的已知数字必须连续**: 两个已知数字格若在线路上直接相连, 它们之间没有别的编号格,
        位次差只能是 1 ⇒ |v2 − v1| 必须 == 1, 否则这条边根本不能走。
        (db039 里 9 与 13 上下相邻 ⇒ 9→13 这条边直接禁用; 求解器 `orderValid` 里一直有它,
         第一版推导器漏了。)

        更一般、更强的判据是**整条候选链的路径检查**(`_chain_ok`: 数字逐个递增不跳跃、
        "?" 通配符赋值、起点 IN 第一个必须是 1、未达最大数字不能碰 OUT), 它由
        `close_by_probe` 的逐格试连接在每条边上检验, 这里只留这条最便宜的快速剪枝。

        历史: 曾在这里写过一条"编号格走一条不含编号格的**必经走廊**直达 OUT/IN ⇒ 禁用"的判据,
        它其实只是路径检查的一个特例(而且当时漏了"冰格直行必被用"这一层) —— 现已删除,
        由 `_chain_ok` 统一处理(命中范围更大)。
        """
        b = self.b
        ch = False
        for c in range(b.w * b.h):
            va = b.num_of(c)
            if va is None or va <= 0:
                continue
            x, y = b.xy(c)
            for d, s in enumerate(DIRS):
                e = b.cell_edges[c][d]
                if e is None or e < 0 or b.edges[e]["frame"] or self.used[e] != UNKNOWN:
                    continue
                nb = b.cid(x + DV[s][0], y + DV[s][1])
                vb = b.num_of(nb)
                if vb is None or vb <= 0:
                    continue
                if abs(vb - va) != 1:
                    if self.mark(e, FORBID,
                                 "已知数字 %d 与 %d 直接相连(位次差必须为 1, 实际差 %d)"
                                 % (va, vb, abs(vb - va))):
                        ch = True
        return ch


    # ---------- R3: 连通 / 无环 ----------
    def rule_conn(self):
        """R3 连通/无环。

        关键: "成环" 只能用**已确定**的边判定 —— 未定的边将来可以不用, 所以
        "两端经由候选边相连" 不构成成环。于是:
          ① 已用边内部成环(同一连通块里再连一条已用边) ⇒ 矛盾;
          ② 一条**未定**边, 若两端已经被"已用边"连在一起 ⇒ 用它必成环 ⇒ 禁用;
          ③ 格/块的可达性: 用"非禁"边算连通块, 某块若到不了 IN 或 OUT ⇒ 该块
             不可能落在线路上 ⇒ 块内所有边禁用(到不了 IN 的块被禁空后由 ④ 收尾);
          ④ 每条**已用**边都必须通向 IN 与 OUT: 已用边必须落在"用已用+候选用边算"
             能同时到达 IN 与 OUT 的块里, 否则矛盾;
          ⑤ 块的接口: 已用边组成的块, 若还有未满足度数的端点(开放端)却没有任何
             出块候选边 ⇒ 这块再也长不出去了 ⇒ 矛盾。
        """
        ch = False
        b = self.b
        N = b.w * b.h
        ncells = N

        # ---- ① 已用边成环 / ② 未定边两端已被已用边连通 ⇒ 禁用 ----
        #
        # **按节点算, 不按格算**: 冰格的两个轴是两个独立节点(十字交叉的两条轴互不连通),
        # 按"格"算会把十字两侧错当成连通, 于是把真解边误判成"成环"而禁掉
        # (实测 db042: (2,2)、(3,2) 两个冰格被十字交叉, 按格算立刻误禁 4 条真解边 + 连带推错 1 条)。
        parent = {}

        def find(p, a):
            while p[a] != a:
                p[a] = p[p[a]]
                a = p[a]
            return a

        def node_of(c, axis):
            return (c, axis) if b.is_ice(c) else (c, 0)

        for c in range(ncells):
            for ax in ((0, 1) if b.is_ice(c) else (0,)):
                parent[node_of(c, ax)] = node_of(c, ax)
        for e in range(self.n):
            if b.edges[e]["frame"] or self.used[e] != USED:
                continue
            ax = b.edges[e]["axis"]
            a = find(parent, node_of(b.edges[e]["a"], ax))
            c = find(parent, node_of(b.edges[e]["b"], ax))
            if a == c:
                self.alive = False
                self.events.append(("矛盾", "已用边成环(边 %d)" % e, e, 0, 0))
                return False
            parent[a] = c

        for e in range(self.n):
            if b.edges[e]["frame"] or self.used[e] != UNKNOWN:
                continue
            ax = b.edges[e]["axis"]
            if (find(parent, node_of(b.edges[e]["a"], ax))
                    == find(parent, node_of(b.edges[e]["b"], ax))):
                if self.mark(e, FORBID, "两端已由已用边连通, 用它成环"):
                    ch = True
        if ch:
            return True

        # ---- ③ 可达性(非禁边) ----
        p_open = list(range(ncells))
        for e in range(self.n):
            if b.edges[e]["frame"] or self.used[e] == FORBID:
                continue
            a, c = find(p_open, b.edges[e]["a"]), find(p_open, b.edges[e]["b"])
            if a != c:
                p_open[a] = c
        groups = {}
        for c in range(ncells):
            groups.setdefault(find(p_open, c), []).append(c)
        for root, mem in groups.items():
            if len(mem) == ncells:
                continue
            memb = set(mem)
            has_in = b.cid(*b.IN) in memb
            has_out = b.cid(*b.OUT) in memb
            if has_in and has_out:
                continue
            # 块到不了 IN 或 OUT: 块内边全部禁用(该块不可能在线路上)
            for c in memb:
                x, y = b.xy(c)
                for d, s in enumerate(DIRS):
                    e = b.cell_edges[c][d]
                    if e is None or e < 0 or b.edges[e]["frame"]:
                        continue
                    if b.cid(x + DV[s][0], y + DV[s][1]) in memb:
                        if self.mark(e, FORBID, "块到不了 IN/OUT"):
                            ch = True
        if ch:
            return True

        # ---- ④⑤ 已用边块: 度数可行性 + 出块可达 ----
        # (这里只判"块整体有没有通向块外的候选边", 用格级并查集就够 —— 格级连通是节点级连通的
        #  **放宽**, 因此"格级也出不去 ⇒ 真的出不去"仍然是必要条件。)
        comps = {}
        for e in range(self.n):
            if b.edges[e]["frame"] or self.used[e] != USED:
                continue
            ax = b.edges[e]["axis"]
            comps.setdefault(find(parent, node_of(b.edges[e]["a"], ax)), []).append(e)
        for root, es in comps.items():
            cells = set()
            for e in es:
                cells.add(b.edges[e]["a"])
                cells.add(b.edges[e]["b"])
            # ④ 块整体至少要有一条通向块外的可用边(否则拼不进线路)。
            # 例外: 这一段已经把 IN 与 OUT 连起来了 ⇒ 线路已闭合, 不需要再往外长
            # (db042 实测: 推到"整条线路全部确定"时, 这条路会把**已经推完的盘面**判成矛盾)。
            if len(cells) == ncells:
                continue
            if b.cid(*b.IN) in cells and b.cid(*b.OUT) in cells:
                continue
            tot_iface = 0
            for c in cells:
                tot_iface += self.out_iface(c, cells)
            if tot_iface == 0:
                self.alive = False
                self.events.append(("矛盾", "已用块 %s 没有通向块外的候选边"
                                    % (sorted(b.xy(c) for c in cells)[:6],), -1, 0, 0))
                return False
        return ch

    def out_iface(self, c, cells):
        """格 c 通向块外(cells 之外)的可用边数。"""
        b = self.b
        n = 0
        x, y = b.xy(c)
        for d, s in enumerate(DIRS):
            e = b.cell_edges[c][d]
            if e is None or e < 0 or b.edges[e]["frame"] or self.used[e] == FORBID:
                continue
            nb = b.cid(x + DV[s][0], y + DV[s][1])
            if nb not in cells:
                n += 1
        return n

    # ---------- R4: 编号位次 / 距离界 ----------
    def bfs_dist(self, src, block_nums=False):
        """在"非禁边"图上从 src 求最短距离(-1 = 不可达)。"""
        b = self.b
        N = b.w * b.h
        dist = [-1] * N
        dist[src] = 0
        q = [src]
        while q:
            cur = q.pop(0)
            x, y = b.xy(cur)
            for d, s in enumerate(DIRS):
                e = b.cell_edges[cur][d]
                if e is None or e < 0 or b.edges[e]["frame"] or self.used[e] == FORBID:
                    continue
                nb = b.cid(x + DV[s][0], y + DV[s][1])
                if block_nums and b.num_of(nb) is not None and b.num_of(nb) != b.num_of(src):
                    continue
                if dist[nb] < 0:
                    dist[nb] = dist[cur] + 1
                    q.append(nb)
        return dist

    def num_sep(self, a, c, dmap):
        """编号格 a 与 c 在线路上相邻出现时, 位次差的最小值(= 两格之间的最少步数)。

        同格(同一 "?" 被穿越两次)最少 1 步(冰区里直行穿过自身, 不可能原地踏步);
        相邻格 1 步; 否则用非禁边图上的最短距离。dmap 为从 a 出发的 BFS 距离场。
        """
        if a == c:
            return 1
        d = dmap.get(a)
        if d is None or d[c] < 0:
            return None
        return d[c]

    def rule_slots(self):
        """R4 编号位次模型(与官方 checkNumberOrder 同一条规则)。

        线路上的"编号格访问"依次占第 1,2,3… 位: 已知数字 v 必须落在第 v 位,
        "?" 格的每一次穿越各占一位(同一 "?" 冰格可十字交叉两次 = 两个不同的数)。

        这里只建立**位次表**并做两条可证明的检查(供报告与 `_chain_ok` 使用):
          ① 计数: 空缺数 G = Vmax − 已知数字个数 不能超过 "?" 能提供的穿越次数;
          ② 每个 "?" 格至少要有一个"可用位次"可落(不是已知数字的位次, 且 ≤ slot_max)。
        真正的位次判据(数字不能逐个跳跃、起点必须是 1、未达 Vmax 不能碰 OUT、
        "?" 赋值存在性)在 `_chain_ok` 里对每条候选链逐条检验 —— 那才是 db039 能推完的关键。

        """
        b = self.b
        N = b.w * b.h
        nums = [(c, b.num_of(c)) for c in range(N) if b.num_of(c) is not None]
        if not nums:
            self.slot_info = None
            return False
        known = sorted([v for c, v in nums if v > 0])
        qmarks = [(c, v) for c, v in nums if v < 0]
        if not known:
            self.slot_info = None
            return False
        vmax = known[-1]
        n_known = len(known)
        known_set = set(known)
        n_qice = sum(1 for c, v in qmarks if b.is_ice(c))
        n_qwhite = len(qmarks) - n_qice
        gap = vmax - n_known                     # 1..Vmax 里空出来的位数
        if gap > n_qwhite + 2 * n_qice:
            self.alive = False
            self.events.append(("矛盾", "数字空缺数 %d 超过问号可提供的位次数" % gap, -1, 0, 0))
            return False
        empty_below = [p for p in range(1, vmax + 1) if p not in known_set]
        empty_set = set(empty_below)
        tail = n_qwhite + 2 * n_qice - gap
        slot_max = vmax + tail
        lo = {}
        hi = {}
        for c, v in nums:
            if v > 0:
                lo[c] = hi[c] = v
            else:
                lo[c] = 1
                hi[c] = slot_max

        # 位次差 k 与"曼哈顿距离 m"的关系:
        #   线路是格心到格心的路径, 两格之间的**步数** ≥ 曼哈顿距离 m(绕行只会更多);
        #   位次差 k ≤ 步数。早先这里写过 "k <= m + 1" 并用它卡区间, 但那条上界**不成立**:
        #   绕行会让步数远大于 m(例: (0,0)->(1,0)->(1,1)->(2,1)->(2,0) 五格全为编号格时,
        #   位次差 4 > 曼哈顿距离 2 + 1) ⇒ 它可能把真解卡掉(假矛盾)。
        #   现在只保留**可证明**的那部分:
        #     ① 每个 "?" 格的位次区间里至少有一个"可用位次"(不是已知数字的位次, 且 ≤ slot_max);
        #     ② 已知数字固定在自己的位次上(v)。
        #   链上的 "?" 赋值存在性由 `_chain_ok` 负责(那才是 db039 的关键判据),
        #   位次表本身见 slotQ / slotAllows。
        cells = [c for c, v in nums]
        lo = {}
        hi = {}
        for c, v in nums:
            if v > 0:
                lo[c] = hi[c] = v
            else:
                lo[c] = 1
                hi[c] = slot_max
        # ① 每个 "?" 都必须能落在某个可用位次上(否则结构性矛盾)
        for c in cells:
            if b.num_of(c) > 0:
                continue
            if not any(p > vmax or p in empty_set for p in range(1, slot_max + 1)):
                self.alive = False
                self.events.append(("矛盾", "? 格 %s 没有任何可用位次(空缺位次为空且位次上限 = Vmax)"
                                    % (b.xy(c),), -1, 0, 0))
                return False
        self.slot_info = {
            "vmax": vmax, "n_known": n_known, "gap": gap, "slot_max": slot_max,
            "empty_below": empty_below, "n_qice": n_qice, "n_qwhite": n_qwhite,
            "known": known, "lo": lo, "hi": hi, "cells": cells, "tail": tail,
        }
        return False

    # ---------- 主循环 ----------
    def _rules(self):
        ch = self.rule_cells()
        if not self.alive:
            return False
        ch = self.rule_stems() or ch
        if not self.alive:
            return False
        ch = self.rule_slots() or ch
        if not self.alive:
            return False
        ch = self.rule_nums() or ch
        if not self.alive:
            return False
        ch = self.rule_conn() or ch
        return ch

    def fixpoint(self, probe=True):
        """推到不动点: **规则** + **逐格逐方向试连**(`close_by_probe`, 主算法)。

        `probe=False` 只跑规则(用于对照/回归)。
        """
        it = 0
        while self.alive:
            it += 1
            if it > 400:
                raise RuntimeError("传播不收敛")
            if not self._rules():
                break
            if not probe:
                break
            n0 = sum(1 for e in range(self.n) if self.used[e] != UNKNOWN)
            self.close_by_probe()
            n1 = sum(1 for e in range(self.n) if self.used[e] != UNKNOWN)
            if n1 == n0:
                break
        return self.alive

    # ---------- 路径段遍历 + **路径检查**(文档 §3.4 / §3.11 的位次模型) ----------
    #
    # 判定与官方 pzpr `checkNumberOrder` 同一条规则:
    #   试连接后沿方向走下去; 冰格必须直行(所以"接着冰格的那条边"是**必被用**的, 即使它还没定);
    #   撞到不可连接格(度数已满 / 冰格穿不过) ⇒ 这个方向不可行;
    #   撞到别的路径段端点 ⇒ 执行**路径合并**, 然后对整条候选链做**路径检查**。
    #
    # 路径检查: 从起点遍历到终点, 每次"编号格访问"占第 1,2,3… 位:
    #   * 已知数字 v 必须落在第 v 位 ⇒ 链上所有已知数字的 (v − 局部序号) 必须一致
    #     ("数字必须一个个递增, 不能跳跃"), 相邻两个已知数字 a<b 之间必须正好 b−a−1 次 "?" 访问;
    #   * "?" 是通配符: 它的位次必须落在"?"选择集内(不是已知数字的位次, 且 ≤ slot_max);
    #   * 起点是 IN ⇒ 第一个位次必须是 1(第一个碰到的数字必须是 1);
    #   * 终点是 OUT ⇒ 到达 OUT 时位次必须已经走到 Vmax(**未达最大数字不能碰 OUT**)。
    # 全程确定性: 没有搜索、没有递归, 每一步都由"冰格直行 / 已用边"唯一确定。

    def _terminus(self, cur, prev):
        """线路端点判定: 返回 "IN" / "OUT" / None。

        * IN 格 ⇒ 线路起点; OUT 格 ⇒ 线路终点;
        * **但冰质 IN/OUT 格可以被垂直穿过**(穿过 OUT 两次是官方允许的走法, IN 同理):
          只有"沿入框轴 / 出框轴进入"那一次才是起点/终点, 垂直进入时继续直行
          (文档 §3.8 与 §3.4 里"IN/OUT 所在轴节点度数 1"那条例外)。
        """
        b = self.b
        if prev is None:
            return None
        px, py = b.xy(prev)
        x, y = b.xy(cur)
        ax = 1 if py != y else 0
        if cur == b.cid(*b.IN):
            if not b.is_ice(cur) or not b.IN_side:
                return "IN"
            return "IN" if ax == AXIS_OF[b.IN_side] else None
        if cur == b.cid(*b.OUT):
            if not b.is_ice(cur) or not b.OUT_side:
                return "OUT"
            return "OUT" if ax == AXIS_OF[b.OUT_side] else None
        return None

    def _edge_between(self, c1, c2):
        """c1 与 c2 之间那条内部边(不相邻返回 None)。"""
        b = self.b
        x, y = b.xy(c1)
        px, py = b.xy(c2)
        delta = (px - x, py - y)
        for dk, s in enumerate(DIRS):
            if DV[s] != delta:
                continue
            e = b.cell_edges[c1][dk]
            return e if (e is not None and e >= 0 and not b.edges[e]["frame"]) else None
        return None

    def _step(self, cur, prev, saved):
        """从 prev 走到 cur 之后, 沿**必经方向**的下一步。

        返回 (下一格, 边, 状态): 状态 "ok"(走得动; 下一格为 None = 自由端) / "sat"(走不通)。
        `saved` 记下被临时置成 USED 的边(调用方负责还原)。

        必经方向:
          * 冰格: 只能沿进入轴直行 —— 对面那条边还没定时, 在"**它必被用**"的假设下继续;
          * 白格: 沿除来路外那条已定的边走; 若它只剩**唯一**一条可用边, 那条也必被用;
            否则去路未定 ⇒ 自由端(停下)。
        """
        b = self.b
        x, y = b.xy(cur)
        ice = b.is_ice(cur)
        axis_in = None
        if prev is not None:
            px, py = b.xy(prev)
            axis_in = 1 if py != y else 0
        cands = []
        for dk, s in enumerate(DIRS):
            e = b.cell_edges[cur][dk]
            if e is None or e < 0 or b.edges[e]["frame"]:
                continue
            if ice and axis_in is not None and b.edges[e]["axis"] != axis_in:
                continue
            nb = b.cid(x + DV[s][0], y + DV[s][1])
            if nb == prev:
                continue
            cands.append((e, nb))
        if not ice:
            if not self.cell_configs(cur):
                return None, None, "sat"           # 这个白格已经凑不齐度数了
            for e, nb in cands:
                if self.used[e] == USED:
                    return nb, e, "ok"
            free = [(e, nb) for e, nb in cands if self.used[e] == UNKNOWN]
            if len(free) != 1:
                return None, None, "ok"            # 去路未定(或已无路) ⇒ 自由端
            e, nb = free[0]                        # 只剩一条可用边 ⇒ 必被用
            if not self._configs_with(cur, e, USED):
                return None, None, "sat"
            saved.append((e, self.used[e]))
            self.used[e] = USED
            if not self._configs_with(nb, e, USED):
                return None, None, "sat"
            return nb, e, "ok"
        # 冰格: 必须直行 ⇒ 对面那条边必被用
        if not cands:
            return None, None, "sat"
        e, nb = cands[0]
        if self.used[e] == FORBID:
            return None, None, "sat"
        if self.used[e] != USED:
            if not self._configs_with(cur, e, USED):
                return None, None, "sat"           # 该格已经不能再穿(已垂直连接的数字 / 已交叉的问号)
            saved.append((e, self.used[e]))
            self.used[e] = USED
        if not self._configs_with(nb, e, USED):
            return None, None, "sat"               # 对面格不可连接(度数已满等)
        return nb, e, "ok"

    def _walk_dir(self, cell, came_from, saved):
        """从 came_from 进入 cell 后, 沿必经方向一直走到头(确定性)。

        返回 (cells, end_kind, status):
          cells = [cell, 下一格, ...]; end_kind ∈ {"free","IN","OUT"};
          status = "ok" 走到头 / "sat" 半路撞死(必经方向走不通、成环、轴被走两次)。
        """
        b = self.b
        e_in = self._edge_between(cell, came_from) if came_from is not None else None
        nodes = {(cell, b.edges[e_in]["axis"] if (e_in is not None and b.is_ice(cell)) else -1)}
        cells = [cell]
        prev, cur = came_from, cell
        for _ in range(b.w * b.h * 3 + 4):
            k = self._terminus(cur, prev)
            if k is not None:
                return cells, k, "ok"
            nxt, e2, st = self._step(cur, prev, saved)
            if st != "ok":
                return cells, "free", st
            if nxt is None:
                return cells, "free", "ok"
            node = (nxt, b.edges[e2]["axis"] if b.is_ice(nxt) else -1)
            if node in nodes:
                return cells, "free", "sat"        # 同一格的同一条轴被走两次 ⇒ 成环
            nodes.add(node)
            cells.append(nxt)
            prev, cur = cur, nxt
        return cells, "free", "ok"

    def _side_seg(self, cell, other, saved):
        """从 cell 沿**除通向 other 的那条边以外**的必经方向往外走。

        返回 (cells=[cell, ...], end_kind, status); status "sat" ⇒ 这一侧走不通。
        """
        k = self._terminus(cell, other)
        if k is not None:
            return [cell], k, "ok"                    # cell 本身就是线路端点(IN/OUT)
        nxt, e2, st = self._step(cell, other, saved)
        if st != "ok":
            return [cell], "free", st
        if nxt is None:
            return [cell], "free", "ok"               # 去路未定 ⇒ 自由端
        cells, k2, st2 = self._walk_dir(nxt, cell, saved)
        return [cell] + cells, k2, st2

    def _chain_through(self, e):
        """在"边 e 被使用"的假设下构造整条**候选链**(含冰格直行所必经的未定边)。

        返回 (chains, status): chains = [(cells, start_kind, end_kind), (另一朝向)]。
        """
        b = self.b
        if b.edges[e]["frame"]:
            return None, "sat"
        a, c = b.edges[e]["a"], b.edges[e]["b"]
        saved = [(e, self.used[e])]
        self.used[e] = USED
        try:
            la, ka, sa = self._side_seg(a, c, saved)      # [a, ...]
            lc, kc, sc = self._side_seg(c, a, saved)      # [c, ...]
        finally:
            for ee, st in reversed(saved):
                self.used[ee] = st
        if sa != "ok" or sc != "ok":
            return None, "sat"
        chains = [(list(reversed(la)) + lc, ka, kc),      # [a侧远端 … a, c … c侧远端]
                  (list(reversed(lc)) + la, kc, ka)]
        return chains, "ok"

    def _chain_ok(self, cells, start_kind, end_kind):
        """**路径检查**(见本节开头的说明): 存在满足条件的 "?" 赋值 ⇒ True, 否则 False。"""
        b = self.b
        si = self.slot_info
        if not si:
            return True
        if start_kind == "OUT" or end_kind == "IN":
            return False                              # OUT 只能是终点, IN 只能是起点
        seen = set()
        for c in cells:                               # 线路不能重复经过同一个白格
            if b.is_ice(c):
                continue
            if c in seen:
                return False
            seen.add(c)
        vmax, slot_max = si["vmax"], si["slot_max"]
        known = set(si["known"])
        ap = [b.num_of(c) for c in cells if b.num_of(c) is not None]
        n = len(ap)
        p1 = None
        for i, v in enumerate(ap, 1):
            if v is not None and v > 0:
                q = v - i + 1
                if p1 is None:
                    p1 = q
                elif p1 != q:
                    return False                      # 数字跳跃 / 不同步 ⇒ 不可行
        if start_kind == "IN":
            if p1 is not None and p1 != 1:
                return False                          # 起点是 IN ⇒ 第一个碰到的必须是 1
            p1 = 1                                    # 起点是 IN ⇒ 第一个位次必须是 1
        lo, hi = 1, slot_max - n + 1
        if end_kind == "OUT":
            lo = max(lo, vmax - n + 1)                # 到 OUT 时位次必须已到 Vmax
        if lo > hi:
            return False
        if p1 is not None:
            if p1 < lo or p1 > hi:
                return False                          # 位次落不进允许区间(含"未达 Vmax 却碰 OUT")
            lo = hi = p1
        qs = [i for i, v in enumerate(ap, 1) if v is not None and v < 0]
        if not qs:
            return True
        for q in range(lo, hi + 1):
            if all((q + i - 1) not in known for i in qs):
                return True                           # 找到一种 "?" 赋值 ⇒ 可行
        return False

    def try_connect(self, e, use=True):
        """**单边试连接**(确定性、无递归、无搜索 —— 本项目采用的做法)。

        试"用"这条边:
          ① 两端格在"用它"的假设下必须还有合法配置;
          ② 顺方向走: 冰格直行(必被用的边一并假设)、撞到度数已满/穿不过 ⇒ 不可行;
          ③ 走到别的段端点就**合并**, 再对整条候选链做**路径检查**;
             两个朝向里有一个可行 ⇒ 这个方向可行, 否则不可行。
        试"禁"这条边: 只需两端格仍有合法配置(配置没了 ⇒ 这条边必用)。
        """
        b = self.b
        if b.edges[e]["frame"] or self.used[e] != UNKNOWN:
            return True
        a, c = b.edges[e]["a"], b.edges[e]["b"]
        if not use:
            for q in (a, c):
                if q is None or q < 0:
                    continue
                if not self._configs_with(q, e, FORBID):
                    return False
            return True
        for q in (a, c):
            if q is None or q < 0:
                continue
            if not self._configs_with(q, e, USED):
                return False
        chains, st = self._chain_through(e)
        if st != "ok":
            return False
        for cells, sk, ek in chains:
            if self._chain_ok(cells, sk, ek):
                return True
        return False

    def _configs_with(self, c, e, st):
        """该格在"边 e 取状态 st"的假设下还剩哪些配置(只算这一格, 不传播)。"""
        b = self.b
        keep = self.used[e]
        self.used[e] = st
        try:
            return self.cell_configs(c)
        finally:
            self.used[e] = keep

    def probe_counts(self):
        """用"单边试连接"重算每个格的**可行连接方式数**(报告用), 以及必用/必禁的边。

        语义:
          * `try_connect(e, use=True)`  能否被用   —— False ⇒ 这条边必禁;
          * `try_connect(e, use=False)` 能否被禁   —— False ⇒ 这条边必用;
          * 格 c 的"可行连接方式数" = 该格**既可得又可不失**的候选边数, 即把该格每条候选边
            单独试一遍(试"用"), 数出可行的条数 —— 与原来的"判断周围有几个可连接格"同义,
            但每条候选边都先过一遍"用它的假设下该格是否还有合法配置"。

        全程确定性、无搜索、无递归。
        """
        b = self.b
        counts = {}
        forced_use, forced_forbid = [], []
        for e in range(self.n):
            if b.edges[e]["frame"] or self.used[e] != UNKNOWN:
                continue
            if not self.try_connect(e, use=True):
                forced_forbid.append(e)
            elif not self.try_connect(e, use=False):
                forced_use.append(e)
        for c in range(b.w * b.h):
            av = [e for e in self.avail(c) if self.used[e] == UNKNOWN]
            counts[c] = len([e for e in av if self.try_connect(e, use=True)])
        return counts, forced_use, forced_forbid

    def close_by_probe(self, verbose=False, max_rounds=200):
        """**逐格扫、逐方向试连、推到不动点**(主算法)。

        每一轮都**从第一个格开始扫**, 对格内每条还没定的候选边分别试"用"与试"禁":
          * 试"用"不可行(顺方向走撞死 / 合并后路径检查不过) ⇒ 这条边**必禁**;
          * 试"禁"不可行(禁掉它该格就没走法了) ⇒ 这条边**必用**;
          * 该格剩下的合法走法(配置)里**所有走法都含有**的边 ⇒ 必用;
          * 只剩一种走法 ⇒ 那种走法的边全部必用。
        一有更新就刷新盘面(重跑一遍规则), 下一轮**从第一个格重新扫**;
        直到一整轮扫完没有任何更新 ⇒ 结束。全程确定性、无搜索、无递归。
        """
        b = self.b
        rounds = 0
        while self.alive and rounds < max_rounds:
            rounds += 1
            changed = False
            for c in range(b.w * b.h):
                if not self.alive:
                    break
                if b.kind(c) == "OUT":
                    continue                       # OUT 格只接一条边(与出框边一起)
                if b.is_ice(c) and self.deg(c) == 0 and b.num_of(c) is None:
                    continue                       # 冰格可以完全不经过
                av = [e for e in self.avail(c) if self.used[e] == UNKNOWN]
                if not av:
                    continue
                cfgs = self.cell_configs(c)
                if not cfgs:
                    self.alive = False
                    self.events.append(("矛盾", "格 %s 无任何合法走法" % (b.xy(c),), -1, 0, 0))
                    break
                ok_use = [e for e in av if self.try_connect(e, use=True)]
                # 试连不可行 ⇒ 必禁
                for e in av:
                    if e not in ok_use:
                        if self.mark(e, FORBID, "试连格 %s 时这个方向不可行" % (b.xy(c),)):
                            changed = True
                # 试"禁"不可行 ⇒ 必用
                for e in ok_use:
                    if not self.try_connect(e, use=False):
                        if self.mark(e, USED, "禁掉格 %s 的这条边就没走法了" % (b.xy(c),)):
                            changed = True
                # 该格剩下的合法走法: 全部边都通过试连
                viable = [t for t in cfgs
                          if all(self.used[x] == USED or x in ok_use for x in t)]
                if not viable:
                    self.alive = False
                    self.events.append(("矛盾", "格 %s 的每种走法都被试连否掉了" % (b.xy(c),),
                                        -1, 0, 0))
                    break
                common = set(viable[0])
                for t in viable[1:]:
                    common &= set(t)
                for x in sorted(common):
                    if self.mark(x, USED, "格 %s 的所有可行走法都含它" % (b.xy(c),)):
                        changed = True
                if len(viable) == 1:
                    for x in viable[0]:
                        if self.mark(x, USED, "格 %s 只剩这一种走法" % (b.xy(c),)):
                            changed = True
            if not changed:
                break
            while self.alive:
                if not self._rules():
                    break
        if verbose:
            print("close_by_probe: %d 轮" % rounds, flush=True)
        return rounds

    # ---------- 说明: 为什么不在这里做回溯搜索 ----------
    # 本推导器定位是"确定性推理器": 只做规则传播 + 逐格逐方向试连接(局部配置判定 + 路径检查),
    # 全程无搜索、无递归。
    #
    # 曾经实现过两版更重的东西, 都已删除:
    #   ① "有界回溯搜索"(`search_complete` / `probe`): Python 里对 db039 规模太大
    #      (20 万节点跑满十分钟仍无结论), 且违背"确定性推理"的定位;
    #   ② "每条未定边 fork + 假设传播"(`contradicts` / `fork` / `close_by_assumption`):
    #      属于递归式假设检验, 已明确不采用 —— 现在由 `close_by_probe` 的单边试连接代替。
    # 要更强的判定, 正确做法是**把判据补成规则**(如本文档 §3.4 的位次模型), 而不是塞搜索。


def path_to_edge_states(board, path):
    """把解路径转成 {边号: 1}。"""
    st = {}
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        s = None
        for d in DIRS:
            if (x0 + DV[d][0], y0 + DV[d][1]) == (x1, y1):
                s = d
                break
        if s is None:
            raise ValueError("路径不相邻: %s -> %s" % ((x0, y0), (x1, y1)))
        k = board.edge_key(x0, y0, s)
        e = board.idx.get(k)
        if e is None:
            raise ValueError("解里有题面上不存在的边: %s" % (k,))
        st[e] = 1
    return st


def deduced_path(board, ded):
    """推理把整条线路都定死时, 从 IN 起沿**已用边**还原格子序列(坐标列表)。

    还原不出(半路走死 / 重复经过白格)返回 None。给"整条线路推完"的题做独立核对用:
    还原出来的路径可以直接喂 `tests/verify.py` 的独立验证器。
    """
    b = board
    cur = b.cid(*b.IN)
    cells = [cur]
    prev = None
    for _ in range(b.w * b.h * 4):
        if prev is not None and ded._terminus(cur, prev) == "OUT":
            break                                     # 从 OUT 出框 ⇒ 线路走完
        nxt = None
        if prev is None:
            x, y = b.xy(cur)
            ax = AXIS_OF[b.IN_side] if b.IN_side else None
            for dk, s in enumerate(DIRS):
                e = b.cell_edges[cur][dk]
                if e is None or e < 0 or b.edges[e]["frame"] or ded.used[e] != USED:
                    continue
                if b.is_ice(cur) and ax is not None and b.edges[e]["axis"] != ax:
                    continue
                nxt = b.cid(x + DV[s][0], y + DV[s][1])
                break
        else:
            nxt, _e, st = ded._step(cur, prev, [])
            if st != "ok":
                return None
        if nxt is None:
            break
        if nxt in cells and not b.is_ice(nxt):
            return None                               # 白格不能重复经过
        cells.append(nxt)
        prev, cur = cur, nxt
    return [b.xy(c) for c in cells]


def main():
    ap = argparse.ArgumentParser(description="IceLom 规则级推导器(推到推无可推)")
    ap.add_argument("puzzle")
    ap.add_argument("--out", default=None, help="把不动点状态写成 JSON(供 GUI/渲染器显示)")
    ap.add_argument("--solution", default=None, help="用已知解核对推导的可靠性")
    ap.add_argument("--no-probe", action="store_true", help="只跑规则, 不做逐格试连接")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印每一步推导")
    args = ap.parse_args()

    puz = json.load(open(args.puzzle, encoding="utf-8"))
    board = Board(puz)
    board.build_stems()
    report("题面: %dx%d, 白格 %d, 冰格 %d, 编号格 %d (已知 %d / \"?\" %d)"
           % (board.w, board.h,
              sum(1 for c in board.cells if c == "w"),
              sum(1 for c in board.cells if c == "i"),
              len(board.numbers),
              sum(1 for v in board.numbers.values() if v > 0),
              sum(1 for v in board.numbers.values() if v < 0)))
    report("拓扑: 边 %d, 冰段 %d 条(最长 %d 条边)"
           % (len(board.edges), len(board.stems),
              max(len(s) for s in board.stems) if board.stems else 0))

    d = Deduce(board, verbose=args.verbose)
    t0 = None
    import time
    t0 = time.time()
    alive = d.fixpoint(probe=not args.no_probe)
    dt = time.time() - t0
    report("传播: %s, 用时 %.3f s%s"
           % ("无矛盾" if alive else "**矛盾(规则下无解)**", dt,
              "" if args.no_probe else " (含逐格试连接)"))

    sol = None
    if args.solution:
        s = json.load(open(args.solution, encoding="utf-8"))
        sol = path_to_edge_states(board, [tuple(p) for p in s["path"]])

    if not alive:
        for ev in d.events[-8:]:
            report("   " + str(ev))
        return 1

    det = [e for e in range(len(board.edges))
           if not board.edges[e]["frame"] and d.used[e] == USED]
    und = [e for e in range(len(board.edges))
           if not board.edges[e]["frame"] and d.used[e] == UNKNOWN]
    forb = [e for e in range(len(board.edges))
            if not board.edges[e]["frame"] and d.used[e] == FORBID]
    report("")
    report("确定要走的边: %d 条;  仍未定: %d 条;  已排除(禁): %d 条"
           % (len(det), len(und), len(forb)))
    # ---- 单边试连接: 确定性、无递归、无搜索 ----
    t2 = time.time()
    counts, fu, ff = d.probe_counts()
    report("单边试连接(每格重算可行连接数, 用时 %.3f s): 必用边 %d 条, 必禁边 %d 条"
           % (time.time() - t2, len(fu), len(ff)))
    cnt = Counter(len(d.avail(c)) for c in range(board.w * board.h))
    report("各格可用边数分布: " + ", ".join("%d条=%d格" % (k, cnt[k]) for k in sorted(cnt)))
    amb = [c for c in range(board.w * board.h) if counts.get(c, 0) > 2]
    report("仍有分支的格(试连接后可行连接数>2): %d 个" % len(amb))
    for c in amb[:30]:
        av = d.avail(c)
        report("   %s %s 可用边 %d 条, 已定 %d 条, 试连接可行 %d 条, 配置 %d 种"
               % (board.xy(c), board.kind(c), len(av), d.deg(c), counts.get(c, 0),
                  len(d.cell_configs(c))))
    # ---- 编号格逐个看: 它还剩几种走法(这是"人推到哪里"的直接指标) ----
    numcells = [c for c in range(board.w * board.h) if board.num_of(c) is not None]
    if numcells:
        report("")
        report("编号格的走法数(试连接后):")
        for c in sorted(numcells, key=lambda q: (board.num_of(q) is None or board.num_of(q) < 0,
                                                 board.num_of(q) or 0)):
            nv = board.num_of(c)
            report("   %s %s 数字 %s: 可用边 %s, 试连接可行 %d 条"
                   % (board.xy(c), "冰" if board.is_ice(c) else "白",
                      ("?" if nv is not None and nv < 0 else nv),
                      [board.edges[e]["key"] for e in d.avail(c)], counts.get(c, 0)))

    bad = []
    if sol is not None:
        for e in det:
            if e not in sol:
                bad.append(("推错(确定边不在解里)", e, board.edges[e]["key"]))
        report("")
        if not bad:
            n_hit = sum(1 for e in und if e in sol)
            report("用已知解核对: 确定边 %d 条**全部**出现在解里(没有推错); "
                   "仍未定的 %d 条里有 %d 条在解里(其余解里不用 —— 本工具只做"
                   "规则推导, 不做分支搜索, 这是正常的)"
                   % (len(det), len(und), n_hit))
        else:
            report("用已知解核对: **不一致 %d 处**" % len(bad))
            for t, e, k in bad[:20]:
                report("   %s: 边 %d %s" % (t, e, k))

    # ---- "?" 位次模型报告(计数推论: 每个 "?" 必须穿越几次 / 可能是哪些数) ----
    slot_state = None
    si = getattr(d, "slot_info", None)
    if si:
        vmax, gap, slot_max = si["vmax"], si["gap"], si["slot_max"]
        empty = si["empty_below"]
        n_qice, n_qwhite = si["n_qice"], si["n_qwhite"]
        forced2 = (gap == n_qice * 2 + n_qwhite)
        report("")
        report("位次模型: 最大已知数字 Vmax=%d, 已知数字 %d 个, 空缺位次 %d 个 %s"
               % (vmax, si["n_known"], gap, empty))
        report("          \"?\" 格 %d 个(冰上 %d), 最多可提供 %d 次穿越 ⇒ 位次上限 %d"
               % (n_qice + n_qwhite, n_qice, n_qice * 2 + n_qwhite, slot_max))
        if forced2:
            report("          计数相等 ⇒ **每个 \"?\" 冰格都必须被十字交叉穿越两次**, "
                   "空缺位次只能由 \"?\" 填满 ⇒ \"?\" 格代表的数字集合 = %s" % (empty,))
        else:
            report("          仍有 %d 个位次的余量 ⇒ 不能断定每个 \"?\" 都穿越两次"
                   % (slot_max - vmax - (n_qice * 2 + n_qwhite - gap)))
        qcells = [c for c in range(board.w * board.h) if board.num_of(c) is not None
                  and board.num_of(c) < 0]
        for c in qcells:
            lo_v, hi_v = si["lo"][c], si["hi"][c]
            vals = [p for p in range(max(lo_v, 1), min(hi_v, slot_max) + 1)
                    if p > vmax or p in set(empty)]
            report("   \"?\" 格 %s(%s): 位次区间 [%d,%d] ⇒ 可能是这些数: %s"
                   % (board.xy(c), "冰" if board.is_ice(c) else "白", lo_v, hi_v,
                      vals if vals else "无(矛盾)"))
        slot_state = {"vmax": vmax, "gap": gap, "slot_max": slot_max,
                      "empty_slots": empty, "forced_double_cross": forced2,
                      "qmarks": [{"x": board.xy(c)[0], "y": board.xy(c)[1],
                                  "ice": board.is_ice(c),
                                  "slot_lo": si["lo"][c], "slot_hi": si["hi"][c],
                                  "values": [p for p in range(max(si["lo"][c], 1),
                                                              min(si["hi"][c], slot_max) + 1)
                                             if p > vmax or p in set(empty)]}
                                 for c in qcells]}

    if args.out:
        def disp(e):
            """输出给 GUI/渲染器显示的边键: 竖边写左格 R, 横边写上格 D(与 GUI 约定一致)。"""
            x, y, s = board.edges[e]["key"]
            return [x, y, s]
        state = {
            "format": "icelom-deduce-v1",
            "puzzle": args.puzzle.replace("\\", "/"),
            "solution": args.solution.replace("\\", "/") if args.solution else None,
            "probe": not args.no_probe,
            "determined": [disp(e) for e in det],
            "possible": [disp(e) for e in und],
            "counts": {"determined": len(det), "possible": len(und), "forbidden": len(forb)},
            "slots": slot_state,
            "cell_table": [{"x": board.xy(c)[0], "y": board.xy(c)[1],
                            "kind": board.kind(c), "num": board.num_of(c),
                            "avail": len(d.avail(c)), "used": d.deg(c),
                            "conf": len(d.cell_configs(c))}
                           for c in range(board.w * board.h)],
        }
        json.dump(state, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        report("")
        report("状态文件: %s" % args.out)
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
