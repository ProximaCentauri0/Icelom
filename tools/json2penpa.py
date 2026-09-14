#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/json2penpa.py — 把 icelom-v1 题面 JSON 导出成 Penpa+（penpa-edit）链接。

Penpa+ 链接的形状是 ``https://swaroopg92.github.io/penpa-edit/#m=solve&p=<载荷>``，
其中 ``p`` = ``base64( raw-deflate( 题面文本 ) )``（penpa-edit `general.js` 的
`encrypt_data` / `decrypt_data`：`Zlib.RawDeflate` + `btoa`）。
题面文本是一份多行结构，逐行含义（行号即解析顺序，见 `general.js::load`）：

| 行 | 内容 | 是否必需 |
| --- | --- | --- |
| 0 | 抬头：棋盘类型、宽高、格宽、显示/画布参数、标题/作者/来源/规则、边框开关 | 必需 |
| 1 | `space`（画布留白，四元数组） | 必需 |
| 2 | 网格显示设置（绘制模式还会用 `~` 续写当前工具） | 求解模式只读第一段 |
| 3 | 提问层 `pu_q`：全部题面元素都挂在这里 | 必需 |
| 4 | 作答层 `pu_a`（求解模式忽略） | 可留空 |
| 5 | 可用格清单（**差分编码**，penpa 用它画粗外框） | 必需 |
| 6 | 标签页设置 | 可留空 |
| 7 | 判定设置（`sol_loopline` 等开关；**带答案的链接才写**） | 可留空 |
| 8-13 | 计时/竞赛/版本/主题/自定义配色 等占位 | 可留空 |
| 14-17 | 自定义配色层、OR 判定、genre 标签 | 可留空 |

带答案的链接再加一个 ``a`` 参数：``#m=solve&p=<题面>&a=<答案>``，``a`` 的编码与 ``p`` 完全相同，
内容是 `make_solution()` 的输出 —— ``[[], ["格1,格2,样式", …], [], [], [], []]``
（六个槽位：底色 / 线条 / 边线 / 墙 / 数字 / 符号；只判定**线条**时只需要第 2 个槽位）。
条目里的两个点号是**相邻两格的格点号**（取小在前），整表按 JS 的字典序 `sort()` 排过，
所以画线的先后顺序不影响判定。

判定用**精确**那一套（抬头第 7 行开 `sol_loopline_exact`）：页面把玩家画的线与 `a` 载荷
**逐字节比**（`text === this.solution`），而这一套下 `make_solution()` 照原样记线的样式号，
所以**答案里的样式号就是"页面上要用哪号笔画"** —— 本工具统一记 **9 号（淡蓝）**，
与题面外框同色，页面上把作答笔选成 9 号再画即可判过。
（"只比形状"的 `sol_loopline` 那套在本机实测**判不过**：它把线归一化成 1 却只把 3 号绿线
算进线路槽，答案无论写 1 还是 3 都对不上 `make_solution()` 的输出 —— 详见 `ANSWER_STYLE`
处的说明。`example/README.md` 里 11 号题面的官方链接用的也是"精确 + 9 号"这一套。）

答案里**含进出框那两段**：`path` 只到 IN/OUT 格，链接里再各补一段连到留白圈的格
（与官方题面链接的做法一致），所以画的时候要把线画到框外那一格。

坐标系（`class_square.js::create_point`，``nx0 = nx + 4``、``ny0 = ny + 4``、``S = nx0*ny0``）：
点号是「区段 + 行主序下标 `i + j*nx0`」——

* `0 .. S-1`：格（`(i+0.5)s, (j+0.5)s`）
* `S .. 2S-1`：格点（`(i+1)s, (j+1)s`）
* `2S .. 3S-1`：横边中点（`(i+0.5)s, (j+1)s`），即**格 (i,j) 的下边**
* `3S .. 4S-1`：竖边中点（`(i+1)s, (j+0.5)s`），即**格 (i,j) 的右边**

题面四周留 ``MARGIN`` 格空白（默认 1），所以题面格 `(x,y)` 落在 `i = x+2+MARGIN`、
`j = y+2+MARGIN`：留白既用来写 IN/OUT 文字与题面外框，也让「线路画出界」那一段有地方画。

⚠️ **出界那一步必须用 `Board.edge_cell`**：penpa 的点号是「区段 + `i + j*nx0`」，
棋盘右/下边界往外走一步会得到 `i == nx0` / `j == ny0`，公式把它**折进下一行/列**
（右边界那一格折到左边缘、下边界折到顶部）—— 答案里就凭空多出一条横穿整个盘面的线。
`edge_cell` 把行内偏移挪一格（`±nx0` / `±nx0²`），让那个点号停在"画布外那一格"上。

元素表示（沿用 penpa-edit 自己的做法）：

* 冰格 → `surface` 色号 5（`set_surface_style` case 5 = `#c0e0ff` 浅蓝）；
  再把**冰区边界**（含被冰围住的白洞）用 `lineE` 淡蓝粗线描一圈，冰格才连成一条"冰道"
* 数字 → `number[格点] = [文本, 1, "1"]`；`n = -2` 的 "?" 格写文本 `"?"`
* 箭头 → `symbol[边点] = [方向号, "arrow_N_B", 2]`，方向号 1=W 3=N 5=E 7=S
  （`draw_arrow`：`th = (num-1)*45 - 180`，画布 y 轴向下；末位 2 = 画在线条之上）
* IN/OUT → `number = ["IN"/"OUT", 1, "6"]` 写在沿 side 方向**留白圈最外那条格线**上
  （留白格本身空着给"线路画出界"那一段；内部 IN/OUT 则写在格心），
  并在入框/出框那条边上补一支同向箭头
* 线段/墙标记 → `lineE` / `wall`（键是 `"点号,点号"`，端点取该边的两个格点）

用法::

    python -X utf8 tools/json2penpa.py example/12_799325.json
    python -X utf8 tools/json2penpa.py example/12_799325.json --out link.txt --stats
    python -X utf8 tools/json2penpa.py example/12_799325.json --solve    # 带答案（开自动判定）
    python -X utf8 tools/json2penpa.py example/01_经典9x9.json --solution 解.json
    python -X utf8 tools/json2penpa.py --selftest          # 全 example 往返自检

答案的来源按优先级：`--solution 解.json` > **解存档** > `--solve` 现场求解。
解存档是 GUI 维护的 `%APPDATA%/IceLom/solutions.json`（键=题面内容指纹，与文件路径
无关；界面里求出唯一解时自动写入）：存档里已有这道题的解就直接拿来当答案
（`--no-archive` 关掉这一步，`--archive 路径` 换一份存档）。存档解**不会**被自动
验证——它来自求解器的"唯一解"结论，与现场求解同源；要人工复核就开链接点 Check。

界面里同一件事有**原生入口**（工具条「导出 Penpa+ 链接」/ 菜单「文件 → 导出 Penpa+
链接…」）：`icelom_gui.py` 直接 import 本模块当链接引擎（`penpa_url` 支持"题面是一道题、
答案按另一道题的盘面算"），所以界面导出的链接与本工具**逐字节相同**；
`tests/gui_logic_test.py` 的导出用例钉住这条一致性。

只有标准库依赖（`zlib` / `base64` / `json` / `hashlib`；`--solve` 另外要仓库根的
`icelom_solver.exe`），导出本身不需要联网。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLVER = os.path.join(ROOT, "icelom_solver.exe")     # `--solve` 用；必须在仓库根
# 解存档（GUI 的 icelom_gui.py 维护同一份文件；键=题面内容指纹，见 puzzle_key()）
ARCHIVE_FILE = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "IceLom", "solutions.json")

URL_BASE = "https://swaroopg92.github.io/penpa-edit/"
DEFAULT_SIZE = 38          # penpa 的格宽（像素），官方链接常用 38
MARGIN = 1                 # 题面四周的留白格数
VERSION = [3, 2, 4]        # penpa-edit 版本号（抬头第 10 行，仅记账）

SURFACE_ICE = 5            # 冰格底色（set_surface_style case 5 = #c0e0ff 浅蓝）
LINE_BLUE = 9              # 冰道描边与题面外框（set_line_style case 9 = 淡蓝粗线）
LINE_BLACK = 2             # 线段标记
LINE_GREEN = 3             # 作答层默认笔 = 绿普通线
# `a` 载荷里答案的样式号，同时决定抬头第 7 行开哪个判定开关。
#
# 用**精确**那一套（`sol_loopline_exact`）+ 9 号淡蓝，与官方 `example/README.md` 里
# 11 号题面的链接完全同构。为什么不用"只比形状"的 `sol_loopline`：页面判定是拿它自己算出的
# `make_solution()` 与 `a` 载荷**逐字节比**（`text === this.solution`），而两套开关下
# 它算出来的样式号不一样：
#   * `sol_loopline_exact`：照原样记玩家线的样式号 ⇒ 答案里写几号，页面就用几号笔画（写 9）；
#   * `sol_loopline`：把线归一化成 1，却**只把 3 号绿线算进线路槽** ⇒ 写 3 时两侧对不上
#     （玩家画 3 → 得 1 ≠ 键里的 3），写 1 时又根本认不出线（0 条）。
# 无头 Chrome 实测（2026-09-18，每条链接都在全新 Chrome 里跑）：精确 + 键 9 + 玩家 9 →
# `sol_flag=1`；其余组合（松模式 + 键 1/3、精确 + 键 1/3）全部 `sol_flag=0`。
ANSWER_STYLE = LINE_BLUE
ANSWER_STYLE_EXACT = LINE_BLUE
WALL = 2                   # 墙标记（黑粗线）
ARROW_STYLE = "arrow_N_B"  # 细黑箭头
ARROW_DIR = {"L": 1, "U": 3, "R": 5, "D": 7}   # 1=西 3=北 5=东 7=南
OPPOSITE = {"L": "R", "R": "L", "U": "D", "D": "U"}
SIDES = ("R", "D", "L", "U")

# 判定开关（抬头第 7 行）：键名与顺序抄自 penpa 自己导出的链接，键就是页面上复选框的 id。
SOLCHECK_KEYS = (
    "sol_surface_exact", "sol_surface", "sol_number",
    "sol_loopline_exact", "sol_loopline", "sol_ignoreloopline",
    "sol_loopedge_exact", "sol_loopedge", "sol_ignoreborder",
    "sol_wall", "sol_square", "sol_circle", "sol_tri", "sol_arrow",
    "sol_math", "sol_battleship", "sol_tent", "sol_star", "sol_akari", "sol_mine",
)

# penpa-edit 自己的字段压缩表（class_p.js: COMPRESS_SUB，顺序必须一致）：
# 压缩时按顺序把 `\"键\"` 换成短记号，解压时倒着换回来。
COMPRESS_SUB = [
    ("z", "zZ"),
    ('"qa"', "z9"),
    ('"pu_q"', "zQ"),
    ('"pu_a"', "zA"),
    ('"grid"', "zG"),
    ('"edit_mode"', "zM"),
    ('"surface"', "zS"),
    ('"line"', "zL"),
    ('"lineE"', "zE"),
    ('"wall"', "zW"),
    ('"cage"', "zC"),
    ('"number"', "zN"),
    ('"symbol"', "zY"),
    ('"special"', "zP"),
    ('"board"', "zB"),
    ('"command_redo"', "zR"),
    ('"command_undo"', "zU"),
    ('"command_replay"', "z8"),
    ('"numberS"', "z1"),
    ('"freeline"', "zF"),
    ('"freelineE"', "z2"),
    ('"thermo"', "zT"),
    ('"arrows"', 'z3'),
    ('"direction"', "zD"),
    ('"squareframe"', "z0"),
    ('"polygon"', "z5"),
    ('"deletelineE"', "z4"),
    ('"killercages"', "z6"),
    ('"nobulbthermo"', "z7"),
    ('"__a"', "z_"),
    ("null", "zO"),
]

DEFAULT_RULES = """从 IN 进入、OUT 离开，画一条不分叉、不重叠的单一线路。
白格可以转弯但至多经过一次，所有白格都必须被线路经过。
冰格（浅蓝格）可以交叉但不能转弯，冰格不必全部经过。
IN/OUT 落在冰格上时，冰上进入/离开同样必须直行。
线路必须按升序经过所有编号格：已知数字 v 必须落在第 v 个经过的编号格上。
"?" 是数字未知的特殊编号格，两次经过同一个 "?" 可以分别代表不同数字。
格间箭头：线路必须按箭头方向经过该边。"""


# --------------------------------------------------------------------------
# 坐标
# --------------------------------------------------------------------------
class Board:
    """penpa-edit 方阵棋盘的点号换算（配 `MARGIN` 格留白）。"""

    def __init__(self, w: int, h: int, margin: int = MARGIN):
        self.w = w
        self.h = h
        self.margin = margin
        self.nx = w + 2 * margin
        self.ny = h + 2 * margin
        self.nx0 = self.nx + 4
        self.ny0 = self.ny + 4
        self.S = self.nx0 * self.ny0
        self.off = 2 + margin          # 题面格 (0,0) 的下标偏移

    # 格 (x,y) 的下标
    def _ij(self, x: int, y: int) -> int:
        return (x + self.off) + (y + self.off) * self.nx0

    def cell(self, x: int, y: int) -> int:
        """格点号。"""
        return self._ij(x, y)

    def hedge(self, x: int, y: int) -> int:
        """格 (x,y) 下边（横边）的点号。"""
        return 2 * self.S + self._ij(x, y)

    def vedge(self, x: int, y: int) -> int:
        """格 (x,y) 右边（竖边）的点号。"""
        return 3 * self.S + self._ij(x, y)

    def vertex(self, cx: int, cy: int) -> int:
        """格点 (cx,cy)（格 (cx,cy) 的左上角）的点号。"""
        return self.S + (cx - 1) + (cy - 1) * self.nx0

    def edge(self, x: int, y: int, side: str) -> int:
        """icelom-v1 的边 {x,y,side} → 边点号（内部边按「下边存上格、右边存左格」规范化）。"""
        if side == "D":
            return self.hedge(x, y)
        if side == "R":
            return self.vedge(x, y)
        if side == "U":
            return self.hedge(x, y - 1)
        if side == "L":
            return self.vedge(x - 1, y)
        raise ValueError("非法 side: %r（只认 R/D/L/U）" % (side,))

    def edge_vertices(self, x: int, y: int, side: str) -> tuple:
        """边 {x,y,side} 两端的格点号（用来画 lineE / wall）。"""
        cx, cy = x + self.off, y + self.off       # 该格左上角的格点坐标
        if side == "D":
            return (self.vertex(cx, cy + 1), self.vertex(cx + 1, cy + 1))
        if side == "U":
            return (self.vertex(cx, cy), self.vertex(cx + 1, cy))
        if side == "R":
            return (self.vertex(cx + 1, cy), self.vertex(cx + 1, cy + 1))
        if side == "L":
            return (self.vertex(cx, cy), self.vertex(cx, cy + 1))
        raise ValueError("非法 side: %r" % (side,))

    def neighbor(self, x: int, y: int, side: str) -> tuple:
        """沿 side 走一步的格坐标（可能落在留白圈里）。"""
        if side == "D":
            return (x, y + 1)
        if side == "U":
            return (x, y - 1)
        if side == "R":
            return (x + 1, y)
        return (x - 1, y)

    def edge_cell(self, x: int, y: int, side: str) -> int:
        """格 (x,y) 沿 side 走一步那个格的点号（那个格可能落在画布外一格）。

        为什么不能直接 `cell(*neighbor(...))`：penpa 的点号是「区段 + `i + j*nx0`」，
        棋盘右/下边界往外走一步得到的下标 `i == nx0` 会**折进下一行**（变成左边缘那格），
        负下标同理折回末尾 —— 答案里就凭空多出一条横穿整个盘面的线。
        所以走到画布外时把**行内偏移**挪一格（`i`/`j` 各加减 `nx0`），点号仍然落在"画布外
        那一格"上：penpa 把它画在画布之外，看不见、也不碍判定。
        """
        nx_, ny_ = self.neighbor(x, y, side)
        if not 0 <= nx_ < self.nx0:
            nx_ += self.nx0 if nx_ < 0 else -self.nx0
        if not 0 <= ny_ < self.ny0:
            ny_ += self.nx0 * self.nx0 if ny_ < 0 else -self.nx0 * self.nx0
        return self.cell(nx_, ny_)

    def outer_edge(self, x: int, y: int, side: str) -> int:
        """边框 IN/OUT 的文字位置：沿 side 走到留白圈最外那条格线上。

        （写在最外的格线上而不是留白格中央，留白格才空着给"线路画出界"那一段。）
        """
        m = self.margin
        if side == "R":
            return self.vedge(x + m, y)
        if side == "L":
            return self.vedge(x - m - 1, y)
        if side == "D":
            return self.hedge(x, y + m)
        if side == "U":
            return self.hedge(x, y - m - 1)
        raise ValueError("非法 side: %r" % (side,))

    def centerlist(self) -> list:
        """可用格清单（题面区域，行主序）；penpa 用它画粗外框。"""
        return [self.cell(x, y) for y in range(self.h) for x in range(self.w)]

    def search_center(self) -> int:
        """复刻 `Puzzle::search_center`：取整个内部区域中心最近的点（同距取点号小的）。"""
        size = 1
        cx = self.nx0 / 2.0 * size
        cy = self.ny0 / 2.0 * size
        best, best_d = 0, None
        for k in range(4 * self.S):          # 只扫格/格点/横边/竖边四类；四角与罗盘点不会重合
            i, j = k % self.nx0, k // self.nx0
            if k < self.S:
                x, y = (i + 0.5) * size, (j + 0.5) * size
            elif k < 2 * self.S:
                x, y = (i + 1) * size, (j + 1) * size
            elif k < 3 * self.S:
                x, y = (i + 0.5) * size, (j + 1) * size
            else:
                x, y = (i + 1) * size, (j + 0.5) * size
            d = (x - cx) ** 2 + (y - cy) ** 2
            if best_d is None or d < best_d:
                best, best_d = k, d
        return best


def diff_encode(seq: list) -> list:
    """penpa 的可用格清单是差分编码（加载时逐项累加还原）。"""
    out = []
    prev = 0
    for k in seq:
        out.append(k - prev)
        prev = k
    return out


# --------------------------------------------------------------------------
# 载荷
# --------------------------------------------------------------------------
def _escape(text: str) -> str:
    """抬头里的规则文本按 penpa 的约定转义（换行/逗号/&/=）。"""
    return (text.replace("\n", "%2D").replace(",", "%2C")
                .replace("&", "%2E").replace("=", "%2F"))


def empty_pu() -> dict:
    """空的问题层对象：键必须与 penpa 导出的完全一致。"""
    return {
        "command_redo": {"__a": []},
        "command_undo": {"__a": []},
        "command_replay": {"__a": []},
        "surface": {},
        "number": {},
        "numberS": {},
        "symbol": {},
        "thermo": [],
        "arrows": [],
        "direction": [],
        "squareframe": [],
        "polygon": {},
        "line": {},
        "lineE": {},
        "wall": {},
        "cage": {},
        "deletelineE": {},
        "killercages": [],
        "nobulbthermo": [],
    }


def build_question(puz: dict, board: Board, frame: bool = True) -> dict:
    """把 icelom-v1 题面写成 penpa 的 `pu_q` 对象。"""
    w, h = puz["w"], puz["h"]
    pu = empty_pu()

    # 冰格底色，以及"冰道"外轮廓：冰区边界（含被冰围住的白洞）用淡蓝粗线描一圈，
    # 冰格才会连成一条道，而不是一堆各自描边的小方格（与官方题面的画法一致）。
    cells = puz.get("cells") or []
    for y in range(h):
        for x in range(w):
            if cells[y * w + x] != "i":
                continue
            pu["surface"][str(board.cell(x, y))] = SURFACE_ICE
            for side in SIDES:
                nx_, ny_ = board.neighbor(x, y, side)
                if 0 <= nx_ < w and 0 <= ny_ < h and cells[ny_ * w + nx_] == "i":
                    continue
                a, b = board.edge_vertices(x, y, side)
                pu["lineE"]["%d,%d" % (min(a, b), max(a, b))] = LINE_BLUE

    # 数字格与 "?" 格
    for item in puz.get("numbers") or []:
        x, y, n = int(item["x"]), int(item["y"]), int(item["n"])
        pu["number"][str(board.cell(x, y))] = ["?" if n < 0 else n, 1, "1"]

    # 格间标记
    for item in puz.get("edges") or []:
        x, y = int(item["x"]), int(item["y"])
        side = item["side"]
        kind = item.get("kind", "segment")
        if kind == "arrow":
            pu["symbol"][str(board.edge(x, y, side))] = [ARROW_DIR[item["dir"]], ARROW_STYLE, 2]
        elif kind == "segment":
            a, b = board.edge_vertices(x, y, side)
            pu["lineE"]["%d,%d" % (min(a, b), max(a, b))] = LINE_BLACK
        elif kind == "wall":
            a, b = board.edge_vertices(x, y, side)
            pu["wall"]["%d,%d" % (min(a, b), max(a, b))] = WALL
        else:
            raise ValueError("非法 kind: %r（只认 segment/arrow/wall）" % (kind,))

    # IN/OUT：文字 + 入框/出框边上的同向箭头
    for key, name in (("in", "IN"), ("out", "OUT")):
        pos = puz.get(key)
        if not pos:
            raise ValueError("题面缺少 %r" % (key,))
        x, y = int(pos["x"]), int(pos["y"])
        side = pos.get("side")
        if side in SIDES:                      # 边框上的 IN/OUT
            pu["number"][str(board.outer_edge(x, y, side))] = [name, 1, "6"]
            pu["symbol"][str(board.edge(x, y, side))] = [
                ARROW_DIR[side if key == "out" else OPPOSITE[side]], ARROW_STYLE, 2]
        elif side is None:                     # 内部 IN/OUT：文字写在格心
            pu["number"][str(board.cell(x, y))] = [name, 1, "6"]
        else:
            raise ValueError("%s.side 非法: %r（R/D/L/U 或省略）" % (key, side))

    # 题面外框（画在题面边界上，与 penpa 自己的粗外框重合，只是换成淡蓝）
    if frame:
        x0, y0 = board.off, board.off
        for k in range(w):
            for cy in (y0, y0 + h):
                a, b = board.vertex(x0 + k, cy), board.vertex(x0 + k + 1, cy)
                pu["lineE"]["%d,%d" % (a, b)] = LINE_BLUE
        for k in range(h):
            for cx in (x0, x0 + w):
                a, b = board.vertex(cx, y0 + k), board.vertex(cx, y0 + k + 1)
                pu["lineE"]["%d,%d" % (a, b)] = LINE_BLUE
    return pu


def jdump(obj) -> str:
    """penpa 用 `JSON.stringify` 序列化，分隔符不带空格——保持一致便于逐字节比对。"""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def solcheck_json() -> str:
    """抬头第 7 行：只开"线路（精确）"这一项判定（其余开关全部关掉）。

    精确判定是**唯一在真机上判得过**的一套（原因见 ANSWER_STYLE 处的说明）：它比的是
    `make_solution()` 与 `a` 载荷的**逐字节相等**，而那一套下 `make_solution()` 照原样
    记玩家线的样式号 —— 所以答案里写 9（淡蓝），玩家就得用 9 号笔。
    """
    flags = dict.fromkeys(SOLCHECK_KEYS, False)
    flags["sol_loopline_exact"] = True
    return jdump(flags)


def answer_segments(puz: dict, path, board: Board, style: int = ANSWER_STYLE) -> dict:
    """解路径 + 进出框那两段 → `pu_a.line` 的键值表（"点号,点号" → 样式）。

    路径是**逐格序列**（冰格被十字交叉时会在两个不同位置各出现一次），相邻两格给一段；
    边框上的 IN/OUT 再各补一段连到留白圈的格，与官方题面链接的做法一致。
    """
    segs = {}
    ids = [board.cell(int(p[0]), int(p[1])) for p in path]
    for a, b in zip(ids, ids[1:]):
        if a == b:                                  # 同一格连着出现两次（不该有）直接跳过
            continue
        segs["%d,%d" % (min(a, b), max(a, b))] = style
    for key in ("in", "out"):
        pos = puz.get(key) or {}
        side = pos.get("side")
        if side in SIDES:
            x, y = int(pos["x"]), int(pos["y"])
            # 走一步必须是 `edge_cell`（折回公式），不能是 `cell(*neighbor(…))`：
            # 后者在棋盘右/下边界会折成对侧那一格（见 Board.edge_cell）
            a, b = board.cell(x, y), board.edge_cell(x, y, side)
            segs["%d,%d" % (min(a, b), max(a, b))] = style
    return segs


def build_answer(puz: dict, path, board: Board, style: int = ANSWER_STYLE) -> str:
    """`a` 参数的内容：`make_solution()` 的输出（只填线条槽位，其余留空）。

    条目按 JS 的字典序 sort() 排过 —— penpa 在判定时也会对自己的作答层排序，
    所以两边都与画线顺序无关。
    """
    entries = sorted("%s,%d" % (k, v) for k, v in answer_segments(puz, path, board, style).items())
    return jdump([[], entries, [], [], [], []])


def load_solution(path: str):
    """读一份解：求解器输出的 JSON Lines、`{"path": ...}` 记录、或它们的列表都认。"""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    objs = []
    try:
        parsed = json.loads(text)
        objs = parsed if isinstance(parsed, list) else [parsed]
    except ValueError:                              # JSON Lines
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{"):
                objs.append(json.loads(line))
    for obj in objs:
        if isinstance(obj, dict) and obj.get("path"):
            return [(int(p[0]), int(p[1])) for p in obj["path"]]
    raise ValueError("%s 里找不到带 path 的解记录" % (path,))


def puzzle_key(puz: dict) -> str:
    """icelom-v1 题面 → 内容指纹 (SHA-256 hex)。

    与 GUI（`icelom_gui.py::puzzle_key`）是**同一套规则的两份实现**：只取题面语义字段，
    数字/标记排序后编码，与键序和 `format`/`options`/`limits` 无关。
    一致性由 `tests/test_penpa_export.py`（全 example 与 GUI 逐题比对）钉住——
    改这里必须同步那边，否则 GUI 存的解链接生成时找不到。
    """
    nums = sorted((int(n["x"]), int(n["y"]), int(n["n"]))
                  for n in puz.get("numbers") or [])
    edges = sorted((int(e["x"]), int(e["y"]), e["side"], e.get("kind", "segment"),
                    e.get("dir")) for e in puz.get("edges") or [])

    def pt(d):
        if not d:
            return None
        return [int(d.get("x")), int(d.get("y")), d.get("side")]

    core = {
        "w": int(puz["w"]), "h": int(puz["h"]),
        "cells": [c for c in (puz.get("cells") or [])],
        "numbers": nums, "edges": edges,
        "in": pt(puz.get("in")), "out": pt(puz.get("out")),
    }
    text = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def archive_solution(puz: dict, archive_path: str = None):
    """解存档里这道题的解（`[[x,y],…]`）；没存过/存档损坏 → None。

    存档由 GUI 维护（求出唯一解时自动写入），这里只读不改。
    """
    try:
        with open(archive_path or ARCHIVE_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        rec = (d.get("solutions") or {}).get(puzzle_key(puz))
    except Exception:
        return None
    if not isinstance(rec, dict) or not rec.get("path"):
        return None
    try:
        return [(int(x), int(y)) for x, y in rec["path"]]
    except Exception:
        return None


def solve_puzzle(puz: dict, time_limit_ms: int = 120000, mode: str = "first"):
    """跑一次仓库根的 `icelom_solver.exe` 拿一个解（`--solve` 用）。"""
    if not os.path.exists(SOLVER):
        raise ValueError("找不到 %s（改 .cpp 后要先 `taskset.ps1 build`）" % (SOLVER,))
    req = dict(puz)
    req["limits"] = {"mode": mode, "max_solutions": 1, "time_limit_ms": int(time_limit_ms)}
    data = json.dumps(req, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run([SOLVER], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=time_limit_ms / 1000.0 + 30)
    done, err = None, None
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("type") == "solution":
            return [(int(p[0]), int(p[1])) for p in obj["path"]]
        if obj.get("type") == "done":
            done = obj
        elif obj.get("type") == "error":
            err = obj
    raise ValueError("求解器没给出解：%s" % (err or done or "无输出",))


def build_text(puz: dict, *, size: int = DEFAULT_SIZE, margin: int = MARGIN,
               title: str = None, author: str = "", source: str = "",
               rules: str = None, frame: bool = True,
               has_answer: bool = False) -> str:
    """拼出 penpa 的题面文本（未压缩）。"""
    w, h = int(puz["w"]), int(puz["h"])
    board = Board(w, h, margin)
    if not (1 <= w <= 60 and 1 <= h <= 60):
        raise ValueError("盘面尺寸超出 penpa 方阵上限（1..60）：%dx%d" % (w, h))
    if title is None:
        title = "IceLom %dx%d" % (w, h)
    if rules is None:
        rules = DEFAULT_RULES

    header = ",".join([
        "square", str(board.nx), str(board.ny), str(size), "0", "1", "1",
        str((board.nx + 1) * size), str((board.ny + 1) * size),
        str(board.search_center()), str(board.search_center()),
        "0", "0", "0", "0",
        "Title: " + title.replace(",", "%2C"),
        "Author: " + author.replace(",", "%2C"),
        source, _escape(rules), "ON", "false", "",
    ])

    lines = [
        header,
        jdump([0, 0, 0, 0]),                          # space
        jdump(["2", "2", "1"]),                       # 虚线网格 / 不画格点 / 画外框
        jdump(build_question(puz, board, frame)),
        "",                                           # pu_a（求解模式的答案层）
        jdump(diff_encode(board.centerlist())),
        "[]",                                         # 标签页设置
        solcheck_json() if has_answer else "",         # 判定设置（只有带答案时才写）
        "", "", jdump(VERSION), "", "", "",           # 计时/竞赛/版本/主题/配色 占位
        "", "", "", "[]",                             # 自定义配色层、OR 判定、genre 标签
        "",
    ]
    return "\n".join(lines)


def compress(text: str) -> str:
    """penpa 的载荷编码：字段压缩表 → raw deflate → base64。"""
    for plain, short in COMPRESS_SUB:
        text = text.replace(plain, short)
    data = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = data.compress(text.encode("utf-8")) + data.flush()
    return base64.b64encode(raw).decode("ascii")


def decompress(payload: str) -> str:
    """compress() 的逆运算（自检与测试用）。"""
    raw = zlib.decompress(base64.b64decode(payload), -15).decode("utf-8")
    for plain, short in reversed(COMPRESS_SUB):
        raw = raw.replace(short, plain)
    return raw


def make_url(puz: dict, solution=None, **kw) -> str:
    """icelom-v1 题面 → Penpa+ 链接（给了解路径就再加 `a` 参数，页面即可自动判定）。"""
    margin = kw.get("margin", MARGIN)
    url = URL_BASE + "#m=solve&p=" + compress(
        build_text(puz, has_answer=solution is not None, **kw))
    if solution is not None:
        board = Board(int(puz["w"]), int(puz["h"]), margin)
        url += "&a=" + compress(build_answer(puz, solution, board))
    return url


def url_answer(url: str):
    """从链接里取回 `a` 载荷（解出的 `make_solution()` 结构），没有就返回 None。"""
    if "&a=" not in url:
        return None
    return json.loads(decompress(url.split("&a=", 1)[1]))


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def load_puzzle(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        puz = json.load(fh)
    for key in ("w", "h", "cells", "in", "out"):
        if key not in puz:
            raise ValueError("%s 不是 icelom-v1 题面：缺 %r" % (path, key))
    if len(puz["cells"]) != puz["w"] * puz["h"]:
        raise ValueError("%s 的 cells 长度与 w*h 不符" % (path,))
    return puz


def describe(puz: dict) -> str:
    ice = sum(1 for c in puz["cells"] if c == "i")
    nums = puz.get("numbers") or []
    qs = sum(1 for n in nums if int(n["n"]) < 0)
    kinds = {}
    for e in puz.get("edges") or []:
        kinds[e.get("kind", "segment")] = kinds.get(e.get("kind", "segment"), 0) + 1
    return "%dx%d, 冰格 %d, 数字 %d(含 ? %d), 标记 %s" % (
        puz["w"], puz["h"], ice, len(nums), qs,
        ", ".join("%s×%d" % (k, v) for k, v in sorted(kinds.items())) or "无")


def selftest(example_dir: str) -> int:
    """往返自检：解压链接 → 题面元素必须与输入 JSON 一一对应。"""
    names = sorted(n for n in os.listdir(example_dir) if n.endswith(".json"))
    if not names:
        print("找不到示例题面：%s" % example_dir)
        return 1
    bad = 0
    for name in names:
        path = os.path.join(example_dir, name)
        puz = load_puzzle(path)
        url = make_url(puz)
        payload = url.split("&p=", 1)[1]
        text = decompress(payload)
        lines = text.split("\n")
        pu = json.loads(lines[3])
        board = Board(puz["w"], puz["h"])
        # 冰格
        want_ice = {board.cell(x, y)
                    for y in range(puz["h"]) for x in range(puz["w"])
                    if puz["cells"][y * puz["w"] + x] == "i"}
        got_ice = {int(k) for k, v in pu["surface"].items() if v == SURFACE_ICE}
        # 数字 + IN/OUT 文字
        want_num = {}
        for item in puz.get("numbers") or []:
            n = int(item["n"])
            want_num[board.cell(int(item["x"]), int(item["y"]))] = "?" if n < 0 else n
        for key, label in (("in", "IN"), ("out", "OUT")):
            pos = puz[key]
            if pos.get("side") in SIDES:
                want_num[board.outer_edge(int(pos["x"]), int(pos["y"]), pos["side"])] = label
            else:
                want_num[board.cell(int(pos["x"]), int(pos["y"]))] = label
        got_num = {int(k): v[0] for k, v in pu["number"].items()}
        # 箭头
        want_arrow = {}
        for item in puz.get("edges") or []:
            if item.get("kind") == "arrow":
                want_arrow[board.edge(int(item["x"]), int(item["y"]), item["side"])] = \
                    ARROW_DIR[item["dir"]]
        got_arrow = {int(k): v[0] for k, v in pu["symbol"].items()}
        want_arrow_inout = {}
        for key in ("in", "out"):
            pos = puz[key]
            if pos.get("side") in SIDES:
                d = pos["side"] if key == "out" else OPPOSITE[pos["side"]]
                want_arrow_inout[board.edge(int(pos["x"]), int(pos["y"]), pos["side"])] = ARROW_DIR[d]
        ok = (want_ice == got_ice and want_num == got_num
              and {k: v for k, v in got_arrow.items() if k not in want_arrow_inout} == want_arrow
              and all(got_arrow.get(k) == v for k, v in want_arrow_inout.items())
              and len(lines) == 19 and lines[0].startswith("square,"))
        # 带答案的链接：a 载荷必须解回「路径段 + 进出框那两段」，且判定开关只开线路一项
        if name == names[0]:
            sample = [(0, 0), (1, 0), (1, 1)]
            a_url = make_url(puz, sample)
            a_sol = url_answer(a_url)
            want_seg = {"%d,%d" % (min(board.cell(*a), board.cell(*b)), max(board.cell(*a), board.cell(*b)))
                        for a, b in zip(sample, sample[1:])}
            for key in ("in", "out"):
                pos = puz[key]
                if pos.get("side") in SIDES:
                    p0 = (int(pos["x"]), int(pos["y"]))
                    a, b = board.cell(*p0), board.edge_cell(p0[0], p0[1], pos["side"])
                    want_seg.add("%d,%d" % (min(a, b), max(a, b)))
            got_seg = {s.rsplit(",", 1)[0] for s in a_sol[1]}
            a_lines = decompress(a_url.split("&p=", 1)[1].split("&a=")[0]).split("\n")
            checks = json.loads(a_lines[7])
            ok = ok and got_seg == want_seg and len(a_sol) == 6 \
                and all(s.endswith(",%d" % ANSWER_STYLE) for s in a_sol[1]) \
                and checks["sol_loopline_exact"] and not checks["sol_loopline"] \
                and a_sol[0] == [] and a_sol[2:] == [[], [], [], []]
            if got_seg != want_seg:
                print("   答案差集 %s / %s" % (got_seg ^ want_seg, want_seg))
        print("%-28s %-42s %s" % (name, describe(puz), "OK" if ok else "失败"))
        if not ok:
            bad += 1
            print("   冰格差集 %s / 数字差集 %s / 箭头差集 %s" % (
                want_ice ^ got_ice, set(want_num.items()) ^ set(got_num.items()),
                set(want_arrow.items()) ^ {k: v for k, v in got_arrow.items()
                                           if k not in want_arrow_inout}))
    print("自检：%d 个示例，失败 %d 个" % (len(names), bad))
    return 1 if bad else 0


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap = argparse.ArgumentParser(
        description="icelom-v1 题面 JSON → Penpa+ 链接",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("puzzle", nargs="?", help="icelom-v1 题面 JSON")
    ap.add_argument("--selftest", action="store_true", help="对 example/ 全部题面做往返自检")
    ap.add_argument("--out", help="把链接写入文件（默认打印到 stdout）")
    ap.add_argument("--stats", action="store_true", help="额外打印题面与链接统计")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE, help="penpa 格宽像素（默认 %d）" % DEFAULT_SIZE)
    ap.add_argument("--margin", type=int, default=MARGIN, help="题面四周留白格数（默认 %d）" % MARGIN)
    ap.add_argument("--title", default=None, help="标题（默认 IceLom <w>x<h>）")
    ap.add_argument("--author", default="", help="作者")
    ap.add_argument("--source", default="", help="来源 URL")
    ap.add_argument("--rules", default=None, help="规则文本（默认内置 IceLom 规则）")
    ap.add_argument("--rules-file", default=None, help="从文件读规则文本")
    ap.add_argument("--no-frame", action="store_true", help="不画题面外框")
    ap.add_argument("--solution", help="用这份解做答案（求解器输出 / {\"path\": ...} 都认）")
    ap.add_argument("--solve", action="store_true", help="现场用 icelom_solver.exe 求一个解做答案")
    ap.add_argument("--no-archive", action="store_true",
                    help="不读解存档（默认存档里有这道题的解就直接当答案，优先于 --solve）")
    ap.add_argument("--archive", default=None,
                    help="解存档路径（默认 %%APPDATA%%/IceLom/solutions.json）")
    ap.add_argument("--time-limit", type=int, default=120000, help="--solve 的时限（毫秒，默认 120000）")
    ap.add_argument("--open", action="store_true", help="生成后直接在浏览器打开")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest(os.path.join(root, "example"))
    if not args.puzzle:
        ap.print_help()
        return 2
    if args.solution and args.solve:
        print("--solution 与 --solve 只能选一个", file=sys.stderr)
        return 2

    rules = args.rules
    if args.rules_file:
        with open(args.rules_file, "r", encoding="utf-8") as fh:
            rules = fh.read().rstrip("\n")
    puz = load_puzzle(args.puzzle)
    # 答案来源优先级: --solution > 解存档 > --solve（--no-archive 可跳过存档这一级）
    path = load_solution(args.solution) if args.solution else None
    src = "solution" if path is not None else None
    if path is None and not args.no_archive:
        path = archive_solution(puz, args.archive)
        if path is not None:
            src = "archive"
    if path is None and args.solve:
        path = solve_puzzle(puz, args.time_limit)
        src = "solve"
    url = make_url(puz, path, size=args.size, margin=args.margin,
                   title=args.title, author=args.author, source=args.source, rules=rules,
                   frame=not args.no_frame)

    if args.stats:
        board = Board(puz["w"], puz["h"], args.margin)
        print("题面: %s" % describe(puz), file=sys.stderr)
        print("棋盘: %dx%d 格（题面四周各留 %d 格），格宽 %d，画布 %dx%d" % (
            board.nx, board.ny, args.margin, args.size,
            (board.nx + 1) * args.size, (board.ny + 1) * args.size), file=sys.stderr)
        print("链接: %d 字符（题面载荷 %d）" % (len(url), len(url.split("&p=", 1)[1].split("&a=")[0])),
              file=sys.stderr)
        if path is None:
            print("答案: 无（未开自动判定；加 --solve 或 --solution 即可带上）", file=sys.stderr)
        else:
            if src == "archive":
                print("答案来源: 解存档（--no-archive 忽略, --solve 强制现场求解）",
                      file=sys.stderr)
            segs = answer_segments(puz, path, board)
            print("答案: 路径 %d 格 → %d 段（判定：精确，样式 %d —— 页面上要用同色号画才判得过）" % (
                len(path), len(segs), ANSWER_STYLE), file=sys.stderr)

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(url + "\n")
        print("已写入 %s" % args.out, file=sys.stderr)
    else:
        print(url)
    if args.open:
        import webbrowser
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
