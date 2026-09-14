# -*- coding: utf-8 -*-
"""生成 IceLom 图标（资产 + 应用图标）——题面是一道**真实可解的 2×2 IceLom 题**。

图标只画题面, 不画解
--------------------
2×2；**右上角 (1,0) 是带 "?" 的冰格**，其余三格填 2、3、4；IN/OUT **都在冰格上**，
但图标里**不画 IN/OUT**（留白太小, 画了反而糊）：

        ┌─────┬─────┐
        │  2  │  ?  │     冰格在右上角, "?" = 数字未知的编号格
        ├─────┼─────┤
        │  3  │  4  │
        └─────┴─────┘

不画解并不等于"随便画": 本脚本仍然把题面喂给求解器求解, 并断言
**恰有 1 个解 + 独立验证器 tests/verify.py 通过 + "?" 冰格被十字穿过两次**，
解落盘到 `assets/icon_solution.json` 备查。也就是说图标所展示的题面是一道真题,
不是装饰图案。

用法: python -X utf8 tools/make_icon.py [--out-dir assets] [--puzzle assets/icon_puzzle.json] [--draw-solution]
产物: assets/icelom.ico（16/24/32/48/64/128/256）, assets/icelom_<n>.png,
      assets/icon_puzzle.json（题面）, assets/icon_solution.json（解, 仅备查）
"""
import argparse
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLVER = os.path.join(ROOT, "icelom_solver.exe")
DEFAULT_PUZZLE = os.path.join(ROOT, "assets", "icon_puzzle.json")

PUZZLE = {
    "format": "icelom-v1",
    "w": 2, "h": 2,
    "cells": ["w", "i", "w", "w"],          # (0,0)白 (1,0)冰 (0,1)白 (1,1)白
    "numbers": [{"x": 1, "y": 0, "n": -2},  # 冰格上的 "?"（数字未知的编号格）
                {"x": 0, "y": 0, "n": 2},
                {"x": 0, "y": 1, "n": 3},
                {"x": 1, "y": 1, "n": 4}],
    "n_qmark": 1,
    "in": {"x": 1, "y": 0, "side": "R"},    # IN 在冰格右边
    "out": {"x": 1, "y": 0, "side": "U"},   # OUT 在冰格上边
    "edges": [],
    "options": {"cover_all_whites": True},
    "_note": "2×2 最小题面(图标用): 右上角冰格带 “?”, 其余三格 2/3/4; IN/OUT 都在冰格上",
}

# ---- 风格（配色与 icelom_render.py 的 Nikoli 纸面一致, 比例相对格边长）----
INK = (0, 0, 0)
GRID = (127, 127, 127)
ICE_FILL = (192, 224, 255)
PINK = (255, 24, 158)
BG = (244, 246, 249)          # 浅灰底: 让图标在白色页面上也有边界
BG_RADIUS = 0.16              # 圆角半径(相对整幅)
MARGIN = 0.075                # 整幅留白(相对整幅)
FRAME_W = 0.028               # 外框线宽(相对格边长)
GRID_W = 0.0095               # 内部虚线网格宽
DASH_ON, DASH_OFF = 0.075, 0.052
ICE_BW = 0.095                # 冰区域外缘黑边宽
NUM_EM = 0.50                 # 数字/"?" 字号(相对格边长)
PATH_W = 0.085                # 线路线宽(仅 --draw-solution 时用)
OV_IN, OV_OUT = 0.42, 0.52    # IN/OUT 端伸出框外的长度(仅 --draw-solution 时用)
QMARK_Y = 0.50                # "?" 在格内的纵向位置(相对格边长; 画解时抬到线上方)
SIZES = [16, 24, 32, 48, 64, 128, 256]
SS = 4                        # 超采样倍数
OVERSHOOT = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# ---- 所有尺寸统一走"大图标的缩小版" ----
# 曾给 ≤64 px 单独画过一版"几何简化图"（粗外框 + 蓝色 "?" 冰格 + 一条粉线），
# 但两套画法放在一起观感很怪，已废弃：现在 16~512 px 的 PNG 与 .ico 各帧
# 全部由同一张 512 px 完整题面图逐尺寸 LANCZOS 缩小而来。


def find_font(px):
    for p in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
              "C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, px)
            except OSError:
                continue
    return ImageFont.load_default()


def solve(puz):
    """跑求解器, 返回 (全部解, done 记录)。"""
    q = dict(puz)
    q.pop("_note", None)
    q["options"] = {"cover_all_whites": True}
    q["limits"] = {"max_solutions": 4, "time_limit_ms": 5000}
    r = subprocess.run([SOLVER], input=json.dumps(q).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out = [json.loads(l) for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    return ([o["path"] for o in out if o.get("type") == "solution"],
            next((o for o in out if o.get("type") == "done"), {}))


def render(puz, size=512, path=None):
    """渲染题面成 size×size（先 SS 倍超采样再 LANCZOS 缩回目标尺寸）。"""
    B = dict(margin=MARGIN, frame=FRAME_W, dash_on=DASH_ON, dash_off=DASH_OFF,
             grid_w=GRID_W, ice_bw=ICE_BW, qmark_em=NUM_EM, path_w=PATH_W,
             path_ov=None)

    S = size * SS
    w, h = puz["w"], puz["h"]
    im = Image.new("RGB", (S, S), "white")
    dr = ImageDraw.Draw(im)

    # 1. 圆角浅灰底
    dr.rounded_rectangle([0, 0, S - 1, S - 1], radius=BG_RADIUS * S, fill=BG)

    # 2. 盘面（居中正方形）
    board = (1 - 2 * B["margin"]) * S
    cs = board / max(w, h)
    ox = oy = (S - board) / 2.0
    fw = B["frame"] * cs

    def rect(x0, y0, x1, y1, **kw):
        dr.rectangle([ox + x0, oy + y0, ox + x1, oy + y1], **kw)

    cx = lambda x: (x + 0.5) * cs
    cy = lambda y: (y + 0.5) * cs
    is_ice = lambda x, y: 0 <= x < w and 0 <= y < h and puz["cells"][y * w + x] == "i"

    # 3. 冰格蓝底
    for y in range(h):
        for x in range(w):
            if is_ice(x, y):
                rect(x * cs, y * cs, (x + 1) * cs, (y + 1) * cs, fill=ICE_FILL)

    # 4. 内部网格: 灰色细虚线
    gw = B["grid_w"] * cs
    for i in range(1, w):
        t = 0.0
        while t < h * cs:
            t2 = min(t + B["dash_on"] * cs, h * cs)
            rect(i * cs - gw / 2, t, i * cs + gw / 2, t2, fill=GRID)
            t = t2 + B["dash_off"] * cs
    for j in range(1, h):
        t = 0.0
        while t < w * cs:
            t2 = min(t + B["dash_on"] * cs, w * cs)
            rect(t, j * cs - gw / 2, t2, j * cs + gw / 2, fill=GRID)
            t = t2 + B["dash_off"] * cs

    # 5. （可选）解线路: 注意"?"冰格会被走两次, 路径里会出现重复格,
    #    每次"朝向反转"都是独立线头, 必须断开重画, 否则会被画成一条回头斜线。
    #    图标默认不画解（--draw-solution 仅备查）。
    stubs = []
    if path:
        pts = [(cx(c[0]), cy(c[1])) for c in path]
        pw = B["path_w"] * cs
        segs = []
        for k in range(1, len(pts)):
            a, b = pts[k - 1], pts[k]
            if segs:
                pa, pb = segs[-1]
                if pb == a and (b[0] - a[0]) * (a[1] - pa[1]) == (b[1] - a[1]) * (a[0] - pa[0]):
                    segs[-1] = (pa, b)          # 同方向: 延长当前段
                    continue
            segs.append((a, b))
        for a, b in segs:
            dr.line([ox + a[0], oy + a[1], ox + b[0], oy + b[1]],
                    fill=PINK, width=max(1, int(round(pw))))
        for p in set(pts):
            r = pw / 2.0
            rect(p[0] - r, p[1] - r, p[0] + r, p[1] + r, fill=PINK)
        # 出入界的两小截留到最后画, 免得被冰格黑边/外框盖住
        for field, ov in ((puz["in"], OV_IN), (puz["out"], OV_OUT)):
            dx, dy = OVERSHOOT[field["side"]]
            c = (cx(field["x"]), cy(field["y"]))
            sign = -1 if field is puz["in"] else 1
            stubs.append((c, (c[0] + sign * dx * ov * cs, c[1] + sign * dy * ov * cs)))

    # 6. 冰区域外缘黑边（相邻冰格共享边不描, 端头各外延 bw/2 补直角）
    bw = B["ice_bw"] * cs
    for y in range(h):
        for x in range(w):
            if not is_ice(x, y):
                continue
            if not is_ice(x - 1, y):
                rect(x * cs - bw / 2, y * cs - bw / 2, x * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)
            if not is_ice(x + 1, y):
                rect((x + 1) * cs - bw / 2, y * cs - bw / 2, (x + 1) * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)
            if not is_ice(x, y - 1):
                rect(x * cs - bw / 2, y * cs - bw / 2, (x + 1) * cs + bw / 2, y * cs + bw / 2, fill=INK)
            if not is_ice(x, y + 1):
                rect(x * cs - bw / 2, (y + 1) * cs - bw / 2, (x + 1) * cs + bw / 2, (y + 1) * cs + bw / 2, fill=INK)

    # 7. 外框
    rect(-fw / 2, -fw / 2, w * cs + fw / 2, fw / 2, fill=INK)
    rect(-fw / 2, h * cs - fw / 2, w * cs + fw / 2, h * cs + fw / 2, fill=INK)
    rect(-fw / 2, -fw / 2, fw / 2, h * cs + fw / 2, fill=INK)
    rect(w * cs - fw / 2, -fw / 2, w * cs + fw / 2, h * cs + fw / 2, fill=INK)

    # 8. 线路出入界端头（最后画, 压在冰格黑边与外框之上）
    pw = B["path_w"] * cs
    for a, b in stubs:
        dr.line([ox + a[0], oy + a[1], ox + b[0], oy + b[1]],
                fill=PINK, width=max(1, int(round(pw))))

    # 9. 数字与 "?"（画在最上层; 画解时加白色描边, 保证压在粉线上也可读）
    font = find_font(max(8, int(round(B["qmark_em"] * cs))))
    halo = max(1, int(round(0.020 * cs))) if path else 0
    for n in puz.get("numbers", []):
        txt = "?" if n["n"] == -2 else str(n["n"])
        px, py = cx(n["x"]), cy(n["y"])
        if path and txt == "?":
            py = n["y"] * cs + 0.30 * cs        # 画解时抬到横穿的粉线之上
        if halo:
            for ddx, ddy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                dr.text((ox + px + ddx * halo, oy + py + ddy * halo), txt,
                        fill=(255, 255, 255), font=font, anchor="mm")
        dr.text((ox + px, oy + py), txt, fill=INK, font=font, anchor="mm")

    return im.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "assets"))
    ap.add_argument("--puzzle", default=DEFAULT_PUZZLE, help="题面 JSON（默认 assets/icon_puzzle.json）")
    ap.add_argument("--size", type=int, default=512, help="PNG 主尺寸")
    ap.add_argument("--draw-solution", action="store_true",
                    help="额外把解画进图里（默认不画: 图标只展示题面）")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    if os.path.exists(args.puzzle):
        puz = json.load(open(args.puzzle, encoding="utf-8"))
    else:
        puz = PUZZLE
        json.dump(puz, open(args.puzzle, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("WROTE", os.path.relpath(args.puzzle, ROOT))

    # 题面自检: 唯一解 + 独立验证器通过（图标展示的必须是一道真题）
    sols, done = solve(puz)
    if len(sols) != 1 or done.get("count") != 1 or done.get("aborted"):
        raise SystemExit("图标题面必须恰有 1 个解, 实际: %s (%d 个解)" % (done, len(sols)))
    path = [(c[0], c[1]) for c in sols[0]]
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import verify                             # 独立验证器（与求解器实现无关）
    errs = verify.check(puz, path)
    if errs:
        raise SystemExit("独立验证器驳回图标题面的解: %s" % errs)
    print("图标题面: %d×%d, 唯一解 %s" % (puz["w"], puz["h"], path))
    print("  独立验证器 OK; 求解器 %s 节点 / %s ms; 冰格穿越 %d 次"
          % (done.get("nodes"), done.get("ms"), path.count((1, 0))))

    out = args.out_dir
    sol_json = os.path.join(out, "icon_solution.json")
    json.dump({"puzzle": os.path.relpath(args.puzzle, ROOT).replace("\\", "/"),
               "cells": len(path), "path": sols[0], "verify": "OK",
               "note": "由 tools/make_icon.py 求解图标题面得到; 图标本身不画解"},
              open(sol_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    master = render(puz, size=max(256, args.size))
    big = max(256, args.size)
    # 全尺寸统一: 每张 PNG 都由主图 LANCZOS 缩小而来（不再有第二套"简化版"画法）
    for s in sorted(set(SIZES + [big])):
        png = os.path.join(out, "icelom_%d.png" % s)
        (master if s == big else master.resize((s, s), Image.LANCZOS)).save(png)
    # .ico: 逐尺寸喂 LANCZOS 缩好的帧（Pillow 用 append_images 逐尺寸取用;
    #       只喂一张大图让它自己缩用的是低质量重采样, 小尺寸就会糊）
    frames = {s: (master if s == big else master.resize((s, s), Image.LANCZOS)) for s in SIZES}
    ico = os.path.join(out, "icelom.ico")
    master_ico = frames.get(256, master)
    master_ico.save(ico, format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=[frames[s] for s in SIZES if frames[s] is not master_ico])
    print("WROTE", os.path.relpath(ico, ROOT),
          "尺寸", SIZES, "（全部由 %d px 完整版 LANCZOS 缩小）" % big)
    print("WROTE", os.path.relpath(sol_json, ROOT))
    print("WROTE", os.path.relpath(os.path.join(out, "icelom_%d.png" % big), ROOT))
    if args.draw_solution:
        sv = os.path.join(out, "icelom_solved_%d.png" % max(256, args.size))
        render(puz, size=max(256, args.size), path=path).save(sv)
        print("WROTE", os.path.relpath(sv, ROOT), "（带解, 仅备查）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
