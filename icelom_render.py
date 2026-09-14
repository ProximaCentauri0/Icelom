# -*- coding: utf-8 -*-
"""IceLom 题面/解 的高保真 PNG 渲染器 (Pillow, 超采样抗锯齿)。

风格对齐 Nikoli 纸面印刷风 (样张实测参数, 比例相对格边长 cs):
  * 白底; 内部网格 = 灰色细虚线 (线宽 0.03cs, 长 0.125cs 空 0.078cs),
    画在冰格蓝底**之上**(冰格共享边的虚线可见);
  * 冰格 = 浅蓝 (192,224,255) 填充; 冰**区域外缘**描加粗黑边 (0.095cs, 居中于格线,
    相邻冰格共享边不描 → 视觉上合并成一大块);
  * 外边框 = 加粗黑实线 (0.11cs), 连续无缺口, 线路/箭头直接压过;
  * 解线路 = 深粉红 (255,24,158) 粗线 (0.11cs), 直角尖角,
    IN 端与 OUT 端都向框外伸 0.30cs(停在箭头三角头底下, 不露头);
  * IN/OUT = 黑色实心三角箭头 + 细杆压在粉线上 (长度 = 1 个格子, 关于外框线对称 ⇒
    箭头中心就在边界格那条边的中点上, IN 与 OUT 必然等长), 标签黑色大字 (字高 0.58cs)
    放在箭头**正后方**(与外框垂直的那条轴上, 居中对齐);
  * 格间标记 = 线段(黑, 垂直穿过该边) / 箭头(黑, 杆+实心三角头, 沿行进方向) /
    墙(红, 平行于该边); 线段与箭头也长 1 格 —— 两端正好是两侧格心, 中心 = 所穿过边的中点;
  * 数字/"?" = 大号黑字 (字高 0.83cs), 画在线路之上。

被两处共用:
  * icelom_gui.py 的「导出解为图片」(高分辨率重绘, 替代旧的屏幕截图);
  * tools/render_solution.py (命令行把某个解渲染成 PNG)。

用法:
    render_puzzle(puz_dict, path=None, cell=64, scale=4, title="") -> PIL.Image
    render_to_file(puz_dict, path, out_png, cell=64, scale=4, title="")
"""
from PIL import Image, ImageDraw, ImageFont

# ---- 调色板 ----
INK = (0, 0, 0)
GRID = (127, 127, 127)
ICE_FILL = (192, 224, 255)
PINK = (255, 24, 158)
WALL = (211, 47, 47)

# ---- 风格比例 (相对 cs) ----
FRAME_W = 0.11     # 外框线宽
GRID_W = 0.032     # 虚线线宽
DASH_ON = 0.125    # 虚线段长
DASH_OFF = 0.078   # 虚线空长
ICE_BW = 0.095     # 冰格外缘黑边宽
PATH_W = 0.11      # 线路线宽
NUM_EM = 0.75      # 数字字号的 em (YaHei 数字墨高 ≈0.77em → 墨高≈0.58cs, 同样张)
OV_IN = 0.30       # IN 端粉线伸出框外的距离(从框外缘起算)
OV_OUT = 0.30      # OUT 端粉线伸出框外的距离 —— 两端取同一个值, 且要**停在箭头三角头底下**
                   # (0.30 + 框宽/2 ≈ 0.36cs < 箭头外端 0.5cs, 否则头尖外会露出一小截粉线)
# ---- 标记几何 (相对 cs) ----
# 线段 / 箭头 / IN-OUT 箭头 **共用一套比例**: 总长恒为 1 个格子, 且关于"边中点"对称 ——
#   格间标记: 两端正好落在两侧的格心上 (格心 → 格心);
#   IN/OUT 箭头: 关于外框线对称 ⇒ 一端是边界格格心、另一端是界外一格的虚拟格心,
#                箭头中心正好在"边界格那条边的中点"上, IN 与 OUT 长度必然相等。
# 这套数字必须与 icelom_gui.py 的 App._draw_edges / _draw_inout_all 保持一致,
# 屏幕与导出图才长得一样(见 docs/算法说明.md §6.3 / §6.5)。
MARK_HALF = 0.50   # 标记半长 (总长 = 1 格)
MARK_HEAD = 0.30   # 实心三角头沿行进方向的长度
MARK_HW = 0.19     # 三角头半宽
MARK_W = 0.045     # 杆半宽
LABEL_GAP = 0.12   # IN/OUT 标签与箭头尾端之间的空隙
LABEL_EM = 0.50    # IN/OUT 标签字号的 em

DIRS = {"R": (1, 0), "D": (0, 1), "L": (-1, 0), "U": (0, -1)}
OPP = {"R": "L", "L": "R", "U": "D", "D": "U"}

_FONT_CACHE = {}


def _font(em):
    """按 em 像素取字体 (优先日文/中文黑体, 数字字形接近样张)。"""
    em = max(6, int(round(em)))
    f = _FONT_CACHE.get(em)
    if f is None:
        for p in (r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msyh.ttc",
                  r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
            try:
                f = ImageFont.truetype(p, em)
                break
            except Exception:
                continue
        if f is None:
            f = ImageFont.load_default()
        _FONT_CACHE[em] = f
    return f


def _draw_board(dr, puz, cs, ox, oy, w, h, ice, is_ice):
    """题面底图: 冰格蓝底 + 灰虚线网格 + 冰区外缘黑边 + 外框 (渲染器内部共用)。"""
    def rect(x0, y0, x1, y1, **kw):
        dr.rectangle([ox + x0, oy + y0, ox + x1, oy + y1], **kw)

    def cx(x):
        return (x + 0.5) * cs

    def cy(y):
        return (y + 0.5) * cs

    fw = FRAME_W * cs
    # ---- 1. 冰格蓝底 ----
    for y in range(h):
        for x in range(w):
            if ice[y][x]:
                rect(x * cs, y * cs, (x + 1) * cs, (y + 1) * cs, fill=ICE_FILL)
    # ---- 2. 灰色虚线网格 ----
    gw = GRID_W * cs
    on, off = DASH_ON * cs, DASH_OFF * cs
    for i in range(1, w):
        y = 0.0
        while y < h * cs:
            y2 = min(y + on, h * cs)
            rect(i * cs - gw / 2, y, i * cs + gw / 2, y2, fill=GRID)
            y = y2 + off
    for j in range(1, h):
        x = 0.0
        while x < w * cs:
            x2 = min(x + on, w * cs)
            rect(x, j * cs - gw / 2, x2, j * cs + gw / 2, fill=GRID)
            x = x2 + off
    # ---- 3. 冰区外缘黑边 ----
    bw = ICE_BW * cs
    for y in range(h):
        for x in range(w):
            if not ice[y][x]:
                continue
            if not is_ice(x - 1, y):
                rect(x * cs - bw / 2, y * cs - bw / 2, x * cs + bw / 2,
                     (y + 1) * cs + bw / 2, fill=INK)
            if not is_ice(x + 1, y):
                rect((x + 1) * cs - bw / 2, y * cs - bw / 2,
                     (x + 1) * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)
            if not is_ice(x, y - 1):
                rect(x * cs - bw / 2, y * cs - bw / 2,
                     (x + 1) * cs + bw / 2, y * cs + bw / 2, fill=INK)
            if not is_ice(x, y + 1):
                rect(x * cs - bw / 2, (y + 1) * cs - bw / 2,
                     (x + 1) * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)
    # ---- 4. 加粗黑外框 ----
    rect(-fw / 2, -fw / 2, w * cs + fw / 2, fw / 2, fill=INK)
    rect(-fw / 2, h * cs - fw / 2, w * cs + fw / 2, h * cs + fw / 2, fill=INK)
    rect(-fw / 2, -fw / 2, fw / 2, h * cs + fw / 2, fill=INK)
    rect(w * cs - fw / 2, -fw / 2, w * cs + fw / 2, h * cs + fw / 2, fill=INK)


def edge_segment(x, y, side, cs):
    """把"左格 R / 上格 D"式边键换算成 (x0,y0,x1,y1) 线段(格心到格心)。"""
    dx, dy = DIRS[side]
    return ((x + 0.5) * cs, (y + 0.5) * cs, (x + 0.5 + dx) * cs, (y + 0.5 + dy) * cs)


def mark_geometry(mid, dv, cs):
    """标记(线段 / 格间箭头 / IN-OUT 箭头)的关键点:
    (杆尾 tail, 三角头底边中点 base, 头尖 tip, 头的横向单位向量 spread)。

    三条硬约束 (也是 tests/gui_logic_test.py 里的回归断言):
      * **总长恒为 1 个格子**(MARK_HALF 的两倍), 且 tail 与 tip 关于 mid 对称
        ⇒ 标记的中心就落在 mid 上;
      * 三角头的底边必须沿**垂直于 dv** 的方向铺开 —— 用 dv 自身会让三个顶点共线,
        图上就只剩一根杆、看不到箭头头了(历史缺陷);
      * 头只占 dv 方向末端 MARK_HEAD 那一段。
    """
    dx, dy = dv
    tail = (mid[0] - dx * MARK_HALF * cs, mid[1] - dy * MARK_HALF * cs)
    tip = (mid[0] + dx * MARK_HALF * cs, mid[1] + dy * MARK_HALF * cs)
    base = (tip[0] - dx * MARK_HEAD * cs, tip[1] - dy * MARK_HEAD * cs)
    return tail, base, tip, (dy, -dx)


def _bar(p0, p1, half):
    """轴对齐粗线段的外接矩形 (两端平头, 不沿轴向额外外扩)。

    与 tkinter 的 `create_line(..., width=2*half, capstyle="butt")` 等价 ——
    标记的墨迹范围因此严格等于两个端点之间, 屏幕上与导出图里都**关于边中点对称**。
    """
    if abs(p1[0] - p0[0]) >= abs(p1[1] - p0[1]):
        return [min(p0[0], p1[0]), min(p0[1], p1[1]) - half,
                max(p0[0], p1[0]), max(p0[1], p1[1]) + half]
    return [min(p0[0], p1[0]) - half, min(p0[1], p1[1]),
            max(p0[0], p1[0]) + half, max(p0[1], p1[1])]


def _draw_mark(dr, ox, oy, mid, dv, cs, head=True, color=INK):
    """画一个标记: 粗杆 + (可选)实心三角头。杆长 1 格(半长 MARK_HALF), 中心 = mid。"""
    tail, base, tip, pv = mark_geometry(mid, dv, cs)
    rect = _bar(tail, base, MARK_W * cs)
    dr.rectangle([ox + rect[0], oy + rect[1], ox + rect[2], oy + rect[3]], fill=color)
    if not head:
        return
    hw = MARK_HW * cs
    dr.polygon([(ox + tip[0], oy + tip[1]),
                (ox + base[0] - pv[0] * hw, oy + base[1] - pv[1] * hw),
                (ox + base[0] + pv[0] * hw, oy + base[1] + pv[1] * hw)], fill=color)


def _draw_inout_mark(dr, ox, oy, f, label, cs, w, h, scale=1):
    """画一个 IN/OUT: 边框格 = 关于外框线对称的黑色箭头(1 格长) + 正后方的标签;
    内部格 = 格内衬底 + IN/OUT 字样(线路以格心为起/终点, 无箭头)。

    标签锚在箭头**正后方**(与外框垂直的那条轴上, 居中对齐), 位置只由箭头长度 + 字号决定。
    """
    x, y = f["x"], f["y"]
    s = f.get("side")
    cxx, cyy = (x + 0.5) * cs, (y + 0.5) * cs
    if not s:
        half_w, half_h = 0.46 * cs, 0.27 * cs
        dr.rectangle([ox + cxx - half_w, oy + cyy - half_h,
                      ox + cxx + half_w, oy + cyy + half_h],
                     fill=(255, 251, 232), outline=(141, 110, 99), width=max(1, scale))
        dr.text((ox + cxx, oy + cyy), label, font=_font(0.40 * cs), fill=INK, anchor="mm")
        return
    if s == "L":
        bpt = (0.0, cyy)
    elif s == "R":
        bpt = (w * cs, cyy)
    elif s == "U":
        bpt = (cxx, 0.0)
    else:
        bpt = (cxx, h * cs)
    ov = DIRS[s]                                  # 向外
    trav = (-ov[0], -ov[1]) if label == "IN" else ov      # IN 指向盘内 / OUT 指向盘外
    _draw_mark(dr, ox, oy, bpt, trav, cs)
    # 标签: 在箭头正后方(尾端之外), 沿"与外框垂直"的轴居中
    off = (MARK_HALF + LABEL_GAP) * cs
    f_lab = _font(LABEL_EM * cs)
    if s == "U":
        dr.text((ox + bpt[0], oy + bpt[1] - off), label, font=f_lab, fill=INK, anchor="mb")
    elif s == "D":
        dr.text((ox + bpt[0], oy + bpt[1] + off), label, font=f_lab, fill=INK, anchor="mt")
    elif s == "L":
        dr.text((ox + bpt[0] - off, oy + bpt[1]), label, font=f_lab, fill=INK, anchor="rm")
    else:
        dr.text((ox + bpt[0] + off, oy + bpt[1]), label, font=f_lab, fill=INK, anchor="lm")


def render_state(puz, state, cell=48, scale=3, title="", out_png=None):
    """渲染"推导状态"图: 已确定边(深粉红粗线) + 仍未定边(浅灰细线) + 每格候选数。

    state 由 `tools/deduce.py --out` 生成(键 `determined` / `possible` / `cell_table`)。
    只画格心到格心的内部边; 边框 IN/OUT 边不画(它们恒为确定)。
    """
    w, h = puz["w"], puz["h"]
    cs = float(cell) * scale
    cells = puz["cells"]
    numbers = {(n["x"], n["y"]): n["n"] for n in puz.get("numbers", [])}
    fin = puz.get("in") or {}
    fout = puz.get("out") or {}

    mL = mR = mU = mD = 0.35 * cs
    for f in (fin, fout):
        if f.get("x") is None or not f.get("side"):
            continue
        need = 2.0 * cs
        if f["side"] == "L":
            mL = max(mL, need)
        elif f["side"] == "R":
            mR = max(mR, need)
        elif f["side"] == "U":
            mU = max(mU, need)
        else:
            mD = max(mD, need)
    if title:
        mU = max(mU, 0.9 * cs)
        W_est = mL + w * cs + mR
        need = _font(0.42 * cs).getlength(title) + 0.4 * cs
        if need > W_est:                  # 标题比盘面宽: 加宽留白, 别让字被裁掉
            mR += need - W_est
    W = int(round(mL + w * cs + mR))
    H = int(round(mU + h * cs + mD))
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    ox, oy = mL, mU

    def rect(x0, y0, x1, y1, **kw):
        dr.rectangle([ox + x0, oy + y0, ox + x1, oy + y1], **kw)

    ice = [[cells[y * w + x] == "i" for x in range(w)] for y in range(h)]

    def is_ice(x, y):
        return 0 <= x < w and 0 <= y < h and ice[y][x]

    _draw_board(dr, puz, cs, ox, oy, w, h, ice, is_ice)

    def draw_edge(key, color, width, dash=None):
        x, y, s = key
        if s not in ("R", "D"):        # 只画规范化边(左格 R / 上格 D)
            return
        x0, y0, x1, y1 = edge_segment(x, y, s, cs)
        if dash:
            # 手工短划线(与网格一致的画法, 避免不同 Pillow 版本的 dash 表现差异)
            import math
            total = math.hypot(x1 - x0, y1 - y0)
            ux, uy = (x1 - x0) / total, (y1 - y0) / total
            t = 0.0
            while t < total:
                t2 = min(t + dash[0] * cs, total)
                dr.line([ox + x0 + ux * t, oy + y0 + uy * t,
                         ox + x0 + ux * t2, oy + y0 + uy * t2],
                        fill=color, width=width)
                t = t2 + dash[1] * cs
        else:
            dr.line([ox + x0, oy + y0, ox + x1, oy + y1], fill=color, width=width)

    # ---- 仍未定边(浅灰细虚线), 再画已确定边(深粉红粗线)压在上面 ----
    for key in state.get("possible", []):
        if tuple(key[2:]) and len(key) == 3:
            draw_edge(tuple(key), (168, 168, 168), max(2, int(0.035 * cs)),
                      dash=(0.10, 0.10))
    for key in state.get("determined", []):
        if len(key) == 3:
            draw_edge(tuple(key), PINK, max(3, int(0.10 * cs)))

    # ---- 数字 / "?" ----
    f_num = _font(NUM_EM * cs)
    for (x, y), v in numbers.items():
        dr.text((ox + (x + 0.5) * cs, oy + (y + 0.5) * cs),
                ("?" if v < 0 else str(v)), font=f_num, fill=INK, anchor="mm")

    # ---- 每格"剩余候选边数"(>2 才画; 可选, 图小的时候容易糊) ----
    if state.get("show_avail", True) and cell >= 40:
        f_small = _font(0.30 * cs)
        for row in state.get("cell_table", []):
            x, y, av = row["x"], row["y"], row["avail"]
            if (x, y) in numbers or av <= 2:
                continue
            dr.text((ox + (x + 0.50) * cs, oy + (y + 0.80) * cs), str(av),
                    font=f_small, fill=(150, 175, 215), anchor="mm")

    # ---- IN/OUT 箭头与标签 (与 render_puzzle 共用同一套几何) ----
    for f, label in ((fin, "IN"), (fout, "OUT")):
        if f.get("x") is None:
            continue
        _draw_inout_mark(dr, ox, oy, f, label, cs, w, h, scale=scale)

    if title:
        dr.text((ox, oy - 0.62 * cs), title, font=_font(0.42 * cs),
                fill=(90, 90, 90), anchor="lm")

    out = im.resize((max(1, int(round(W / scale))), max(1, int(round(H / scale)))),
                    Image.LANCZOS)
    if out_png:
        out.save(out_png)
    return out


def render_puzzle(puz, path=None, cell=64, scale=4, title=""):
    """把谜题(可选带解)渲染成 PIL.Image。

    puz: icelom-v1 JSON dict; path: [[x,y],...] 解线路 (可含冰格重复穿越)。
    cell: 每格边长(输出像素); scale: 超采样倍数 (先放大画再缩小, 抗锯齿)。
    """
    w, h = puz["w"], puz["h"]
    cs = float(cell) * scale
    cells = puz["cells"]
    numbers = {(n["x"], n["y"]): n["n"] for n in puz.get("numbers", [])}
    fin = puz.get("in") or {}
    fout = puz.get("out") or {}

    # ---- 画布与留白 (有 IN/OUT 标签的一侧留大) ----
    mL = mR = mU = mD = 0.35 * cs
    for f in (fin, fout):
        if f.get("x") is None or not f.get("side"):
            continue
        need = 2.0 * cs
        if f["side"] == "L":
            mL = max(mL, need)
        elif f["side"] == "R":
            mR = max(mR, need)
        elif f["side"] == "U":
            mU = max(mU, need)
        else:
            mD = max(mD, need)
    if title:
        mU = max(mU, 0.9 * cs)
    W = int(round(mL + w * cs + mR))
    H = int(round(mU + h * cs + mD))
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)

    ox, oy = mL, mU

    def rect(x0, y0, x1, y1, **kw):
        dr.rectangle([ox + x0, oy + y0, ox + x1, oy + y1], **kw)

    def cx(x):
        return (x + 0.5) * cs

    def cy(y):
        return (y + 0.5) * cs

    fw = FRAME_W * cs
    ice = [[cells[y * w + x] == "i" for x in range(w)] for y in range(h)]

    def is_ice(x, y):
        return 0 <= x < w and 0 <= y < h and ice[y][x]

    # ---- 1. 冰格蓝底 ----
    for y in range(h):
        for x in range(w):
            if ice[y][x]:
                rect(x * cs, y * cs, (x + 1) * cs, (y + 1) * cs, fill=ICE_FILL)

    # ---- 2. 灰色虚线网格 (内部线; 画在蓝底之上, 共享边虚线可见) ----
    gw = GRID_W * cs
    on, off = DASH_ON * cs, DASH_OFF * cs
    for i in range(1, w):
        y = 0.0
        while y < h * cs:
            y2 = min(y + on, h * cs)
            rect(i * cs - gw / 2, y, i * cs + gw / 2, y2, fill=GRID)
            y = y2 + off
    for j in range(1, h):
        x = 0.0
        while x < w * cs:
            x2 = min(x + on, w * cs)
            rect(x, j * cs - gw / 2, x2, j * cs + gw / 2, fill=GRID)
            x = x2 + off

    # ---- 3. 冰区域外缘黑边 (相邻冰格共享边不描, 端头各外延 bw/2 补直角) ----
    bw = ICE_BW * cs
    for y in range(h):
        for x in range(w):
            if not ice[y][x]:
                continue
            if not is_ice(x - 1, y):
                rect(x * cs - bw / 2, y * cs - bw / 2, x * cs + bw / 2,
                     (y + 1) * cs + bw / 2, fill=INK)
            if not is_ice(x + 1, y):
                rect((x + 1) * cs - bw / 2, y * cs - bw / 2,
                     (x + 1) * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)
            if not is_ice(x, y - 1):
                rect(x * cs - bw / 2, y * cs - bw / 2,
                     (x + 1) * cs + bw / 2, y * cs + bw / 2, fill=INK)
            if not is_ice(x, y + 1):
                rect(x * cs - bw / 2, (y + 1) * cs - bw / 2,
                     (x + 1) * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)

    # ---- 4. 加粗黑外框 ----
    rect(-fw / 2, -fw / 2, w * cs + fw / 2, fw / 2, fill=INK)
    rect(-fw / 2, h * cs - fw / 2, w * cs + fw / 2, h * cs + fw / 2, fill=INK)
    rect(-fw / 2, -fw / 2, fw / 2, h * cs + fw / 2, fill=INK)
    rect(w * cs - fw / 2, -fw / 2, w * cs + fw / 2, h * cs + fw / 2, fill=INK)

    # ---- 5. 边标记 (线段/箭头=垂直于边, 墙=平行于边; 边框上的往盘内挪) ----
    for e in sorted(puz.get("edges", []), key=lambda e: (e["y"], e["x"], e["side"])):
        x, y, s, kind = e["x"], e["y"], e["side"], e["kind"]
        if s in ("R", "L"):
            bx = (x + 1) * cs if s == "R" else x * cs
            mid = [bx, cy(y)]
            para = (0.0, 1.0)
        else:
            by = (y + 1) * cs if s == "D" else y * cs
            mid = [cx(x), by]
            para = (1.0, 0.0)
        perp = (para[1], para[0])
        on_frame = not (0 <= x + DIRS[s][0] < w and 0 <= y + DIRS[s][1] < h)
        if on_frame:
            iv = DIRS[OPP[s]]
            offi = fw * 0.5 + 0.16 * cs
            mid[0] += iv[0] * offi
            mid[1] += iv[1] * offi
        if kind == "wall":
            hl = 0.44 * cs
            rect(*_bar((mid[0] - para[0] * hl, mid[1] - para[1] * hl),
                       (mid[0] + para[0] * hl, mid[1] + para[1] * hl), 0.05 * cs),
                 fill=WALL)
        else:
            # 线段 / 箭头: 1 格长(两侧格心 ↔ 格心), 关于所穿过边的中点对称
            dv = DIRS[e["dir"]] if kind == "arrow" else perp
            _draw_mark(dr, ox, oy, mid, dv, cs, head=(kind == "arrow"))

    # ---- 6. 解线路 (直角尖角: 逐段画矩形, 端头各外延 pw/2; 边框 IN/OUT 端伸出框外) ----
    if path:
        pts = []
        if fin.get("x") is not None and fin.get("side"):
            dx, dy = DIRS[fin["side"]]
            ext = cs / 2 + fw / 2 + OV_IN * cs
            pts.append((cx(fin["x"]) + dx * ext, cy(fin["y"]) + dy * ext))
        pts += [(cx(x), cy(y)) for x, y in path]
        if fout.get("x") is not None and fout.get("side"):
            dx, dy = DIRS[fout["side"]]
            ext = cs / 2 + fw / 2 + OV_OUT * cs
            pts.append((cx(fout["x"]) + dx * ext, cy(fout["y"]) + dy * ext))
        ded = [pts[0]]
        for q in pts[1:]:
            if q != ded[-1]:
                ded.append(q)
        pw = PATH_W * cs
        r = pw / 2
        for (x0, y0), (x1, y1) in zip(ded, ded[1:]):
            if abs(x0 - x1) < 0.5:      # 竖直段
                rect(x0 - r, min(y0, y1) - r, x0 + r, max(y0, y1) + r, fill=PINK)
            elif abs(y0 - y1) < 0.5:    # 水平段
                rect(min(x0, x1) - r, y0 - r, max(x0, x1) + r, y0 + r, fill=PINK)

    # ---- 7. 数字 / "?" (画在线路之上) ----
    f_num = _font(NUM_EM * cs)
    for (x, y), v in numbers.items():
        dr.text((ox + cx(x), oy + cy(y)), ("?" if v < 0 else str(v)),
                font=f_num, fill=INK, anchor="mm")

    # ---- 8. IN/OUT 黑色箭头 + 标签 (内部 IN/OUT = 衬底 + 文字; 与 render_state 共用) ----
    for f, label in ((fin, "IN"), (fout, "OUT")):
        if f.get("x") is None:
            continue
        _draw_inout_mark(dr, ox, oy, f, label, cs, w, h, scale=scale)

    # ---- 9. 可选标题 ----
    if title:
        dr.text((ox, oy - 0.62 * cs), title, font=_font(0.42 * cs), fill=(90, 90, 90),
                anchor="lm")

    out = im.resize((max(1, int(round(W / scale))), max(1, int(round(H / scale)))),
                    Image.LANCZOS)
    return out


def render_to_file(puz, path, out_png, cell=64, scale=4, title=""):
    img = render_puzzle(puz, path=path, cell=cell, scale=scale, title=title)
    img.save(out_png)
    return img.size
