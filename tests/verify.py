# -*- coding: utf-8 -*-
"""独立的 IceLom 解验证器 — 与 C++ 求解器完全独立的规则实现，用于交叉验证。

输入: puzzle dict (与求解器输入相同格式) + 解路径 [(x,y), ...]
输出: 违规列表（空列表 = 合法解）
"""
import json


def check(puz, path, cover_all=None):
    errs = []
    w, h = puz["w"], puz["h"]
    cells = puz["cells"]  # 长度 w*h, index=y*w+x, "w"/"i"
    nums = {(n["x"], n["y"]): n["n"] for n in puz.get("numbers", [])}
    K = len(nums)
    IN, OUT = puz["in"], puz["out"]
    if cover_all is None:
        cover_all = puz.get("options", {}).get("cover_all_whites", True)

    DIRV = {"R": (1, 0), "D": (0, 1), "L": (-1, 0), "U": (0, -1)}

    # 归一化边 key: V 边存 (x,y,"R")(左格), H 边存 (x,y,"D")(上格); 边框边存边框格的外向 side
    def edge_key(x, y, side):
        dx, dy = DIRV[side]
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h:
            # 内部边: 规范化
            if side == "R":
                return (x, y, "R")
            if side == "L":
                return (x - 1, y, "R")
            if side == "D":
                return (x, y, "D")
            if side == "U":
                return (x, y - 1, "D")
        else:
            return (x, y, side)
        raise AssertionError("bad edge")

    marks = {}
    for e in puz.get("edges", []):
        k = edge_key(e["x"], e["y"], e["side"])
        marks[k] = (e["kind"], e.get("dir"))

    if not path:
        return ["空路径"]
    # 1. 起终点
    if (path[0][0], path[0][1]) != (IN["x"], IN["y"]):
        errs.append(f"起点不是 IN: {path[0]}")
    if (path[-1][0], path[-1][1]) != (OUT["x"], OUT["y"]):
        errs.append(f"终点不是 OUT: {path[-1]}")
    # 1.5 IN 冰格的入界直行 (仅有显式 side 时; 内部 IN/OUT side=None 不约束)
    def cell_kind(x, y):
        return cells[y * w + x]
    if (IN.get("side") and cell_kind(IN["x"], IN["y"]) == "i" and len(path) >= 2):
        d0 = (path[1][0] - path[0][0], path[1][1] - path[0][1])
        if DIRV.get(OPP[IN["side"]]) != d0:
            errs.append(f"IN 冰格未沿入界方向直行: 首步方向 {d0}")
    # 2. 逐步检查
    used_edges = set()
    visit_count = {}
    ice_axis = {}  # (x,y) -> set of "h"/"v"
    seq = []
    moves = []  # 每步的行进方向名
    for i, (x, y) in enumerate(path):
        if not (0 <= x < w and 0 <= y < h):
            errs.append(f"越界: {(x,y)}")
            return errs
        visit_count[(x, y)] = visit_count.get((x, y), 0) + 1
        if (x, y) in nums:
            seq.append(nums[(x, y)])
        if i == 0:
            continue
        px, py = path[i - 1]
        dxx, dyy = x - px, y - py
        if abs(dxx) + abs(dyy) != 1:
            errs.append(f"第{i}步不相邻: {path[i-1]}->{(x,y)}")
            moves.append("?")
            continue
        mv = {(1, 0): "R", (-1, 0): "L", (0, 1): "D", (0, -1): "U"}[(dxx, dyy)]
        moves.append(mv)
        # 冰格不可转弯: 进入方向必须等于离开方向
        if i >= 2 and cells[py * w + px] == "i" and moves[i - 1] != mv:
            errs.append(f"冰格转弯: {path[i-1]} 进入{moves[i-1]} 离开{mv} (第{i}步)")
        # 边 key
        if dxx == 1:
            k = (px, py, "R"); axis = "h"; mv = "R"
        elif dxx == -1:
            k = (x, y, "R"); axis = "h"; mv = "L"
        elif dyy == 1:
            k = (px, py, "D"); axis = "v"; mv = "D"
        else:
            k = (x, y, "D"); axis = "v"; mv = "U"
        # 3. 边规则
        if k in used_edges:
            errs.append(f"边重复经过: {k} (第{i}步)")
        used_edges.add(k)
        mk = marks.get(k)
        # 边框边: 只有 IN/OUT 边可被经过（普通步进不会产生边框边，防御性检查）
        def is_frame(kk):
            x0, y0, s0 = kk
            dx0, dy0 = DIRV[s0]
            return not (0 <= x0 + dx0 < w and 0 <= y0 + dy0 < h)
        if is_frame(k):
            if k == (IN["x"], IN["y"], IN["side"]):
                pass  # 起点进入, 实际上路径不会"经过"该边, 由起点检查覆盖
            elif k == (OUT["x"], OUT["y"], OUT["side"]):
                pass
            else:
                errs.append(f"线路越出边框: {k}")
        if mk:
            kind, mdir = mk
            if kind == "wall":
                errs.append(f"穿墙: {k} (第{i}步)")
            elif kind == "arrow" and mdir != mv:
                errs.append(f"逆箭头经过: {k} 需要{mdir} 实际{mv} (第{i}步)")
        # 4. 格规则
        if cells[y * w + x] == "w":
            if (x, y) == (IN["x"], IN["y"]) and i == 0:
                pass
            elif visit_count[(x, y)] > 1:
                errs.append(f"白格重复: {(x,y)} (第{i}步)")
        else:  # ice: 每轴至多一次; 已知数字的冰格整体只许经过一次; "?" 冰格可交叉穿越
            axs = ice_axis.setdefault((x, y), set())
            if axis in axs:
                errs.append(f"冰格同轴二次经过: {(x,y)} (第{i}步)")
            axs.add(axis)
            if (x, y) in nums and nums[(x, y)] > 0 and visit_count[(x, y)] > 1:
                errs.append(f"冰上数字格被多次经过: {(x,y)}")
    # 5. 编号格位次 (与 pzpr 官方 checkNumberOrder 一致):
    #    线路上的编号格访问依次占第 1,2,3… 位 —— 已知数字格每次经过算 1 位,
    #    "?" 格的**每一次穿越**各算 1 位(同一 "?" 冰格被交叉穿过两次 = 两个数)。
    #    已知数字 v 必须正好出现在第 v 位。所有编号格都必须被经过。
    slot = 0
    seen_num = set()
    for (x, y) in path:
        if (x, y) not in nums:
            continue
        seen_num.add((x, y))
        v = nums[(x, y)]
        slot += 1
        if v > 0 and v != slot:
            errs.append(f"数字位次错误: {(x,y)} 上的 {v} 出现在第 {slot} 位"
                        f"（\"?\" 格每次穿越各占一位）")
    for (k, v) in sorted(nums.items(), key=lambda kv: (kv[1], kv[0])):
        if k not in seen_num:
            errs.append(f"编号格未被经过: {k}" + ("(\"?\")" if v < 0 else f"({v})"))
    # 5.5 冰上 OUT: 最后一步必须沿出框方向进入（直行穿出; 白质 OUT 可转弯, 无此限制;
    #     内部 OUT (side=None) 止于格心, 不约束方向）
    if (OUT.get("side") and cell_kind(OUT["x"], OUT["y"]) == "i"
            and len(moves) >= 1 and moves[-1] != "?"):
        if moves[-1] != OUT["side"]:
            errs.append(f"冰上 OUT 未沿出框方向进入: 最后一步 {moves[-1]}, 应为 {OUT['side']}")
    # 6. 覆盖所有白格
    if cover_all:
        visited_cells = set(visit_count)
        for yy in range(h):
            for xx in range(w):
                if cells[yy * w + xx] == "w" and (xx, yy) not in visited_cells:
                    errs.append(f"白格未经过: {(xx,yy)}")
    # 7. 未被经过的强制边
    for k, (kind, mdir) in marks.items():
        if kind in ("segment", "arrow") and k not in used_edges:
            # IN/OUT 边框标记自动满足
            def is_frame(kk):
                x0, y0, s0 = kk
                dx0, dy0 = DIRV[s0]
                return not (0 <= x0 + dx0 < w and 0 <= y0 + dy0 < h)
            if is_frame(k):
                continue
            errs.append(f"强制边未被经过: {k} {kind}{mdir or ''}")
    return errs


OPP = {"R": "L", "L": "R", "U": "D", "D": "U"}

if __name__ == "__main__":
    import sys
    puz = json.load(open(sys.argv[1], encoding="utf-8"))
    sol = json.load(open(sys.argv[2], encoding="utf-8"))
    path = [tuple(p) for p in sol["path"]]
    errs = check(puz, path)
    print("OK" if not errs else "\n".join(errs))
