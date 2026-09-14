#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冰宫巡游 (IceLom) 通用求解器 — 图形界面
=======================================
前端: Python tkinter;  后端: icelom_solver.exe (C++, 高速求解)

规则要点:
  * 从 IN 进、OUT 出, 一条不分叉、不重叠的单一线路, 线路走格子中心;
  * 白格: 至多经过一次, 可转弯; 默认要求所有白格都被经过(可勾选关闭);
  * 冰格(蓝格): 不可转弯(直行穿出), 允许垂直交叉(每格横/竖各一次), 不必全经过;
  * 数字格: 按 1..K 升序经过, 各恰好一次; 可放白格或冰格(冰上数字不可被交叉);
  * 格间标记: 线段=必经(方向任意), 箭头=按方向必经, 墙=禁止经过;
  * IN/OUT: 通常放在边框上(显示入/出界箭头); 也支持放在盘面内部
    (线路以该格格心为起/终点, 格内显示 IN/OUT 衬底字样);
    IN/OUT 恰好位于角上的冰格时, 入/出界方向不唯一, 需点击相邻格指定。

主要功能:
  * 示例: 从 example/ 文件夹下拉加载;
  * 求解模式: 只求解 / 判断唯一性 / 求出所有解(可设解数量上限, 默认 20);
  * 推理预算: 求解时限(秒)可直接输入, 默认 120 秒, 记在 %APPDATA%/IceLom/gui.json;
  * 解存档: 求出**唯一解**时自动把解存进 %APPDATA%/IceLom/solutions.json
    (键=题面内容指纹, 与文件路径无关); 再打开同一道题时自动载入存档解,
    可直接「显示解」; 此时再点「求解」会先问是否重新求解;
    同一条记录里还留一份**该题的 Penpa+ 链接**(题面链接 + 带本题答案的链接);
  * 导出 Penpa+ 链接: 菜单「文件 → 导出 Penpa+ 链接…」/ 工具条同名按钮, 先弹一个
    配置窗(要不要对照答案、答案用本题的解 / 本题存档解 / **自己手动画一条线**),
    再给链接(可复制/存文件/直接打开); 手动绘制时盘面回到空题面, 画完点「完成」即出链接
    (那条线原样当对照答案, 不做验证);
  * 做题模式: 像 puzz.link 一样自由画线——可画多段线路、可从任意格起笔、
    可在 IN/OUT 处垂直画出界外; 拖过已有线段=擦除, 拖回上一步=回退;
    「检查解」用规则引擎(参照 pzprjs 做题引擎)判定是否已成解;
  * 边做题边求解: 做题中途求解不覆盖做题界面, 用「显示解/隐藏解」切换对照;
    「对照解」验证当前线路是解的一部分(无错误连接, 不比较方向与起终点);
  * 撤回: Ctrl+Z 或「撤回」按钮, 求解中撤回会先打断求解。

用法: python icelom_gui.py             (需同目录下有 icelom_solver.exe)
      python icelom_gui.py --selftest  (自动测试模式)
"""
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

APP_TITLE = "冰宫巡游 Icelom 通用求解器"
HERE = os.path.dirname(os.path.abspath(__file__))
SOLVER = os.path.join(HERE, "icelom_solver.exe")
URL_TOOL = os.path.join(HERE, "tools", "pzprurl2json.js")
EXAMPLE_DIR = os.path.join(HERE, "example")
ICON = os.path.join(HERE, "assets", "icelom.ico")
APP_ID = "Icelom.Solver.GUI"        # Windows 任务栏的身份标识(见 _set_app_user_model_id)
SHORTCUT_TOOL = os.path.join(HERE, "tools", "make_shortcut.py")
PENPA_TOOL = os.path.join(HERE, "tools", "json2penpa.py")   # Penpa+ 链接生成器(见 penpa_module)
CFG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "IceLom")
CFG_FILE = os.path.join(CFG_DIR, "gui.json")     # 只记"要不要再问建快捷方式"这类小事
ARCHIVE_FILE = os.path.join(CFG_DIR, "solutions.json")   # 解存档(键=题面内容指纹, 见 archive_*)
DEFAULT_TIME_LIMIT_S = 120                      # 推理预算默认值(秒)
LNK_NAME = "IceLom 冰宫巡游.lnk"
_APP_ID_SET = False


def _no_console():
    """子进程静默启动参数（Windows 下不弹控制台黑窗）。

    为什么需要: 界面通常由 `pythonw`/带图标的快捷方式启动，**进程自身没有控制台**。
    这时用 Popen/run 拉起控制台程序（`icelom_solver.exe` / `node` / `python`），
    Windows 会为子进程**新开一个黑窗**（求解一次闪一个，很难看）。
    `CREATE_NO_WINDOW` 让子进程不建控制台；stdin/stdout 管道不受影响，JSON 协议照常走。

    非 Windows 上返回空字典（`CREATE_NO_WINDOW` 只在 Windows 存在）。
    """
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _set_app_user_model_id():
    """给本进程一个自己的 Windows AppUserModelID（只做一次, 非 Windows 上直接跳过）。

    为什么需要: 用 `python icelom_gui.py` 启动时, 进程是 **python.exe**, Windows 任务栏
    默认按进程去取图标 → 显示白纸/蟒蛇图标, 跟窗口设的 iconbitmap 无关。
    显式设置 AppUserModelID 之后, 任务栏把这个进程当成一个独立应用,
    再配上**带图标的快捷方式/启动器**(tools/make_shortcut.py 生成)就能稳定显示 IceLom 图标。
    """
    global _APP_ID_SET
    if _APP_ID_SET or not sys.platform.startswith("win"):
        return
    _APP_ID_SET = True
    if os.environ.get("ICELOM_NO_APPID"):        # 诊断用: 关掉看看任务栏回退成什么图标
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def _cfg():
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _center_on_parent(win, parent):
    """把弹出的 Toplevel 摆到父窗口中间(几何算不出来时静默留在系统默认位置)。"""
    try:
        parent.update_idletasks()
        win.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - win.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - win.winfo_height()) // 3)
        win.geometry("+%d+%d" % (x, y))
    except Exception:
        pass


def _cfg_set(key, value):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        d = _cfg()
        d[key] = value
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


# ---- 解存档 (%APPDATA%/IceLom/solutions.json) ----
# 设计: 键 = 题面**内容指纹**(puzzle_key), 与文件路径无关 —— 同一道题改名/挪目录/
# 从 URL 导入都算同一题; `tools/json2penpa.py` 按同一套规则查这份存档, 生成带答案的
# Penpa+ 链接时直接复用存档解(两边各自实现, 一致性由 tests/test_penpa_export.py 钉住)。
def puzzle_key(puz_obj):
    """icelom-v1 题面 dict → 内容指纹 (SHA-256 hex)。

    只取题面语义字段(w/h/cells/numbers/edges/in/out), 与键序、`format`/`options`/
    `limits` 等非语义字段无关; 数字与标记先排序再编码, 同一题面的任何等价表示
    (存盘文件、Puzzle.to_json()、URL 解码结果)都得到同一个键。
    """
    nums = sorted((int(n["x"]), int(n["y"]), int(n["n"]))
                  for n in puz_obj.get("numbers") or [])
    edges = sorted((int(e["x"]), int(e["y"]), e["side"], e.get("kind", "segment"),
                    e.get("dir")) for e in puz_obj.get("edges") or [])

    def pt(d):
        if not d:
            return None
        return [int(d.get("x")), int(d.get("y")), d.get("side")]

    core = {
        "w": int(puz_obj["w"]), "h": int(puz_obj["h"]),
        "cells": [c for c in (puz_obj.get("cells") or [])],
        "numbers": nums, "edges": edges,
        "in": pt(puz_obj.get("in")), "out": pt(puz_obj.get("out")),
    }
    text = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def archive_read(path=None):
    """读整份存档; 缺失/损坏一律返回 {} (存档永远不能把界面卡住)。"""
    try:
        with open(path or ARCHIVE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def archive_lookup(puz_obj, path=None):
    """这道题在存档里的解记录; 没存过/记录损坏 → None。"""
    sols = archive_read(path).get("solutions")
    rec = sols.get(puzzle_key(puz_obj)) if isinstance(sols, dict) else None
    if isinstance(rec, dict) and rec.get("path"):
        return rec
    return None


def archive_link(puz_obj, key="puzzle", path=None):
    """存档里留的 Penpa+ 链接; 没有这一份 → None。

    `key`: "puzzle" = 不带答案的题面链接, "answer" = 带本题答案的链接。

    这两份**每次按存档里的题面与解现算**(记录自带题面, 见 archive_puzzle): 存下来的
    字符串只是"当时算得出来"的证据, 拿现算的才不会把旧格式/旧画法的链接喂出去。
    带答案时解本身在记录里, 现算与存档值必然一致。
    """
    rec = archive_lookup(puz_obj, path)
    links = (rec or {}).get("links")
    if not isinstance(links, dict):
        return None
    if key == "puzzle":
        return penpa_link(puz_obj)
    if key == "answer":
        pts = archive_path(rec)
        return penpa_link(puz_obj, pts) if pts else None
    return links.get(key) or None


def archive_puzzle(rec):
    """解记录里那份**题面**(icelom-v1 dict); 老记录(没存题面) → None。

    存档自解释的关键: 有题面才能按它把题面/答案链接现算出来, 光有尺寸与路径画不出来。
    """
    p = (rec or {}).get("puzzle")
    if not isinstance(p, dict) or not p.get("cells") or not p.get("in") or not p.get("out"):
        return None
    return p


def archive_path(rec):
    """解记录里的路径 → [(x,y), …]; 缺字段/损坏 → None(不抛异常)。"""
    try:
        pts = [(int(p[0]), int(p[1])) for p in (rec or {}).get("path") or []]
    except Exception:
        return None
    return pts or None


# ---- Penpa+ 链接 (真源是 tools/json2penpa.py, 这里只按路径 import 它) ----
# 为什么是 import 而不是"再实现一份": 链接的编码(字段压缩表/坐标/答案段表)与题目画法
# 强耦合, 两份实现一定会腐化。json2penpa.py 是**纯标准库**模块, import 它不引入任何依赖
# (Pillow 那条"可选依赖"的理由在这里不成立), 而且它就在本文件的同级目录 tools/ 下 ——
# 发布版也按同样布局带上它(见 tools/make_release.py 的 FILES)。
_PENPA = None


def penpa_module():
    """按需 import tools/json2penpa.py; 没有这个文件就抛 ValueError(带人话提示)。"""
    global _PENPA
    if _PENPA is not None:
        return _PENPA
    if not os.path.exists(PENPA_TOOL):
        raise ValueError("找不到 %s (Penpa+ 导出需要它)" % PENPA_TOOL)
    import importlib.util
    spec = importlib.util.spec_from_file_location("json2penpa", PENPA_TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _PENPA = mod
    return mod


def penpa_link(puz_obj, path=None, frame=True, **kw):
    """icelom-v1 题面 dict → Penpa+ 链接(给了解路径就带 `a` 答案参数)。

    `path` 既可以是求解器给的解, 也可以是**手动画出来的一条线**(它不必是合法解) ——
    链接里只记"哪些相邻格对连了线", 不做任何验证。
    判定口径只有一种(精确比对 + 答案样式 9, 见 `tools/json2penpa.py:ANSWER_STYLE`)。

    题面不合格(尺寸超 penpa 上限 / 缺 IN/OUT / side 非法)时抛 ValueError 并把
    json2penpa 的说明原样带出来 —— 调用方照原样显示即可。
    """
    return penpa_module().make_url(puz_obj, None if path is None else list(path),
                                   frame=frame, **kw)


def archive_save_solution(puz_obj, path, source="icelom_gui", file_path=None,
                          archive_path=None):
    """把一份解写进存档(先写临时文件再 os.replace, 避免半截 JSON)。

    记录里同时留**两份 Penpa+ 链接**(`links.puzzle` 题面 / `links.answer` 带本题答案)
    与**题面本身**(`puzzle`, 见 archive_puzzle) —— 存档因此是自解释的, 读取时能按同一份
    题面与解把链接现算出来。链接生成失败只是少一份链接, **不影响解本身入档**。

    返回 None=成功; 出错返回错误字符串 —— 存档失败只影响提示, 绝不抛异常打断求解。
    """
    p = archive_path or ARCHIVE_FILE
    try:
        d = archive_read(p)
        sols = d.get("solutions") if isinstance(d.get("solutions"), dict) else {}
        links = {"puzzle": penpa_link(puz_obj)}
        try:
            links["answer"] = penpa_link(puz_obj, list(path))
        except Exception:
            pass                       # 答案编码不了(题面缺 IN/OUT 等) → 只留题面链接
        sols[puzzle_key(puz_obj)] = {
            "path": [[int(x), int(y)] for x, y in path],
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "file": file_path or "",
            "w": int(puz_obj.get("w") or 0), "h": int(puz_obj.get("h") or 0),
            # 记录自带题面: 存档才是自解释的(读回时能按它把链接现算出来, 见 archive_link)
            "puzzle": puz_obj,
            "links": links,
        }
        d["version"] = 1
        d["solutions"] = sols
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return None
    except Exception as e:
        return str(e)


DIRS = {"R": (1, 0), "D": (0, 1), "L": (-1, 0), "U": (0, -1)}
OPP = {"R": "L", "L": "R", "U": "D", "D": "U"}
MOVE_OF = {(1, 0): "R", (-1, 0): "L", (0, 1): "D", (0, -1): "U"}
# 边的轴向: 0 = 横轴(R/L), 1 = 竖轴(D/U)。冰格允许"垂直交叉"(横竖两轴各穿一次),
# 所以"同一个冰格上的 IN 与 OUT"必须落在**互相垂直**的两条边上(见 App._share_side);
# 做题规则引擎判定"冰格转弯"时也用这个轴判据。
AXIS = {"R": 0, "L": 0, "D": 1, "U": 1}


def cell_line(a, b):
    """格 a → 格 b 的"格心连线"经过的格子序列(含两端), 每次只走 4 邻接的一格。

    拖动涂抹用: 相邻两次鼠标事件之间可能跨了好几格(快速拖动 / 系统合并移动),
    只处理"当前那一格"就会漏格。走法 = 主轴优先的阶梯, 与做题拖动的补齐一致。
    """
    x0, y0 = a
    x1, y1 = b
    out = [(x0, y0)]
    while (x0, y0) != (x1, y1):
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) >= abs(dy):
            x0 += (dx > 0) - (dx < 0)
        else:
            y0 += (dy > 0) - (dy < 0)
        out.append((x0, y0))
    return out

# ---- 配色 (与 icelom_render.py / Nikoli 纸面样张对齐; 比例相对格边长 cs) ----
COL_ICE = "#c0e0ff"        # 冰格浅蓝
COL_GRID = "#7f7f7f"       # 内部虚线网格灰
COL_INK = "#000000"        # 外框 / 冰格黑边 / 数字 / IN-OUT 箭头
COL_PATH = "#ff189e"       # 解线路深粉红
COL_PLAY = "#1565c0"       # 做题线路蓝
COL_PLAY_OK = "#2e7d32"    # 做题完成绿
COL_PLAY_ERR = "#e65100"   # 做题违规橙 (与解线路粉红明显区分)
COL_SEG = "#000000"        # 线段标记
COL_ARROW = "#000000"      # 箭头标记
COL_WALL = "#d32f2f"       # 墙标记(红, 与纸面黑/粉/蓝区分语义)
COL_ARMED = "#fff59d"      # 边标记起点格高亮
COL_PENDING = "#b2ebf2"    # IN/OUT 等待指定方向高亮
COL_PLATE = "#fffbe8"      # 内部 IN/OUT 衬底
COL_NUMBER = "#000000"
COL_CAND = "#5b8def"         # 推导状态: 仍未定的候选边 / 每格候选数 (浅蓝)
# 重复的已知数字 (题面无效): 整格铺黄警告。白格用 COL_DUP_BG, 冰格用偏暖的 COL_DUP_ICE
# (蓝底上盖浅黄会发灰, 用暖黄底才看得出"这格有问题")。
COL_DUP_BG = "#ffe9a8"
COL_DUP_ICE = "#f7d98a"
NUM_FONT = "Microsoft YaHei UI"   # 数字/标签字体 (缺失时 tkinter 自动回退)
UI_FONT = (NUM_FONT, 10)
MONO_FONT = ("Consolas", 9)       # 求解器诊断窗口: 现场盘面/边集是等宽对齐的, 必须等宽字体


# ============================================================
# 谜题模型
# ============================================================
class Puzzle:
    """谜题数据模型。cells[y][x] ∈ {"w","i"}; numbers[(x,y)]=n;
    edge[(x,y,side)]={"kind":"segment/arrow/wall","dir":...} (内部边规范存 R/D 侧);
    fin/fout={"x","y","side"} — side 为 None 表示 IN/OUT 位于盘面内部(无入/出界边)。"""

    def __init__(self, w=9, h=9):
        self.w = w
        self.h = h
        self.cells = [["w"] * w for _ in range(h)]
        self.numbers = {}
        self.edge = {}
        self.fin = {"x": None, "y": None, "side": None}
        self.fout = {"x": None, "y": None, "side": None}

    # ---- 序列化 ----
    def to_json(self):
        nums = sorted(self.numbers.items(), key=lambda kv: (kv[1], kv[0]))
        edges = []
        for (x, y, s), mk in sorted(self.edge.items()):
            e = {"x": x, "y": y, "side": s, "kind": mk["kind"]}
            if mk["kind"] == "arrow":
                e["dir"] = mk["dir"]
            edges.append(e)
        return {
            "format": "icelom-v1",
            "w": self.w, "h": self.h,
            "cells": [c for row in self.cells for c in row],
            "numbers": [{"x": x, "y": y, "n": n} for (x, y), n in nums],
            "in": self._pt(self.fin), "out": self._pt(self.fout),
            "edges": edges,
            "options": {"cover_all_whites": True},
        }

    @staticmethod
    def _pt(f):
        d = {"x": f["x"], "y": f["y"]}
        if f.get("side") is not None:
            d["side"] = f["side"]
        return d

    @staticmethod
    def from_json(obj):
        p = Puzzle(obj["w"], obj["h"])
        for i, c in enumerate(obj["cells"]):
            p.cells[i // p.w][i % p.w] = "i" if c == "i" else "w"
        for nm in obj.get("numbers", []):
            p.numbers[(nm["x"], nm["y"])] = nm["n"]
        for attr, key in (("fin", "in"), ("fout", "out")):
            o = dict(obj.get(key) or {"x": None, "y": None, "side": None})
            o.setdefault("x", None)
            o.setdefault("y", None)
            o.setdefault("side", None)
            setattr(p, attr, o)
        for e in obj.get("edges", []):
            mk = {"kind": e["kind"]}
            if e["kind"] == "arrow":
                mk["dir"] = e["dir"]
            p.edge[(e["x"], e["y"], e["side"])] = mk
        return p

    # ---- 边规范键 ----
    def edge_key(self, x, y, side):
        """点击格子 (x,y) 的 side 侧 → 规范边键。"""
        nx, ny = x + DIRS[side][0], y + DIRS[side][1]
        if 0 <= nx < self.w and 0 <= ny < self.h:
            if side == "R":
                return (x, y, "R")
            if side == "L":
                return (x - 1, y, "R")
            if side == "D":
                return (x, y, "D")
            if side == "U":
                return (x, y - 1, "D")
        return (x, y, side)  # 边框

    def is_frame_key(self, key):
        x, y, s = key
        return not (0 <= x + DIRS[s][0] < self.w and 0 <= y + DIRS[s][1] < self.h)

    def boundary_sides(self, x, y):
        """格子 (x,y) 朝向盘面外侧的边(可能 0/1/2 个)。"""
        out = []
        if x == 0:
            out.append("L")
        if x == self.w - 1:
            out.append("R")
        if y == 0:
            out.append("U")
        if y == self.h - 1:
            out.append("D")
        return out

    def is_boundary(self, x, y):
        return bool(self.boundary_sides(x, y))

    def in_dir(self):
        """线路在 IN 格的行进方向 (内部 IN / 白格不受限时无意义)。"""
        s = self.fin.get("side")
        return OPP[s] if s else None

    def out_dir(self):
        s = self.fout.get("side")
        return s if s else None

    def renumber(self):
        """把已知数字按大小压缩重排为 1..K（"?" 格 n=-2 保持不动）。
        注意: 这会把跳号题面的间隔信息抹掉, 界面的数字工具**不会**自动调用它。"""
        ks = [k for k in self.numbers if self.numbers[k] > 0]
        for i, k in enumerate(sorted(ks, key=lambda k: self.numbers[k])):
            self.numbers[k] = i + 1

    def known_count(self):
        return sum(1 for v in self.numbers.values() if v > 0)

    def qmark_count(self):
        return sum(1 for v in self.numbers.values() if v < 0)

    def dup_numbers(self):
        """题面里**出现两次以上的已知数字** → {数字: [(x,y), …]}（按数字升序）。

        已知数字必须各出现恰好一次（每个数字只能占一个位次），所以重复即题面无效；
        界面会把重复的数字标黄警告。注意跳号（1,3,5…）是合法的, 不算问题。
        """
        seen = {}
        for pos, v in self.numbers.items():
            if v > 0:
                seen.setdefault(v, []).append(pos)
        return {v: sorted(ps, key=lambda t: (t[1], t[0]))
                for v, ps in sorted(seen.items()) if len(ps) > 1}

    def dup_positions(self):
        """重复数字所在格的集合 {(x,y), …}（重绘时用来标黄）。"""
        return {pos for ps in self.dup_numbers().values() for pos in ps}

    def next_free_number(self, start=1, used=None, limit=999):
        """从 start 起找第一个**题面里还没有**的已知数字（"?" 不计入占用）。"""
        if used is None:
            used = {v for v in self.numbers.values() if v > 0}
        n = max(1, int(start))
        while n in used and n < limit:
            n += 1
        return n

    def max_known(self):
        known = [v for v in self.numbers.values() if v > 0]
        return max(known) if known else 0

    def resize(self, w, h):
        old = self.to_json()
        np = Puzzle(w, h)
        src = Puzzle.from_json(old)
        for (x, y), n in list(src.numbers.items()):
            if x < w and y < h:
                np.numbers[(x, y)] = n
        for (x, y, s), mk in src.edge.items():
            if x < w and y < h:
                np.edge[(x, y, s)] = mk
        for y in range(min(h, src.h)):
            for x in range(min(w, src.w)):
                np.cells[y][x] = src.cells[y][x]
        for f in ("fin", "fout"):
            o = getattr(src, f)
            if o["x"] is not None and o["x"] < w and o["y"] < h:
                setattr(np, f, dict(o))
        self.__dict__.update(np.__dict__)


# ============================================================
# 做题模式规则引擎 (线段集合模型; 判定语义参照 pzprjs 官方 icelom 的
# AnsCheck 清单, 与求解器/verify.py 相互独立)
# ============================================================
def path_to_edges(path):
    """格序列 → 无向边集合 {frozenset({(x1,y1),(x2,y2)})}。
    端点允许出界一格 (做题模式在 IN/OUT 处垂直画出界外的短边)。"""
    out = set()
    for a, b in zip(path, path[1:]):
        a, b = tuple(a), tuple(b)
        if a != b:
            out.add(frozenset((a, b)))
    return out


def check_play_rules(puz, edges, cover_all=True):
    """对做题线段集做完整规则判定。线段 = 格中心→相邻格中心的无向连线,
    可伸出界外一格。返回 (errors, incompletes, complete, route, route_edges):
      errors       硬性违规 (画错): 分叉/白格交叉/冰格转弯/穿墙/逆箭头/
                   越出边框/数字位次/冰上数字重走/多余游离线段;
      incompletes  尚未满足的题面要求 (正常做题过程中的提示, 不算画错);
      complete     线路合法且满足全部要求;
      route        从 IN 出发沿线路行进的格序列 (盘内; 冰格交叉会重复出现);
      route_edges  线路占用的边 (含 IN/OUT 出界短边)。

    与 pzprjs icebarn.js AnsCheck 的对应关系:
      lnBranch / lnCrossExIce / lnCurveOnIce → 局部检查(分叉/白格交叉/冰格转弯)
      stNoLine        → IN 处未画线 (incomplete)
      lrDeadEnd       → 线路中断未到 OUT (incomplete)
      lrOffField      → 从非 OUT 处越出边框 (error)
      lrReverse       → 逆箭头 (error)
      lrOrder         → 数字位次 (error)
      lnPlLine        → 未连入线路的多余线段 (线路已成解时为 error)
      cuNoLine/nmUnpass → 白格/编号格未经过 (incomplete)"""
    w, h = puz.w, puz.h
    errors, incompletes = [], []

    adj = {}
    for e in edges:
        a, b = tuple(e)
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

    def inside(p):
        return 0 <= p[0] < w and 0 <= p[1] < h

    if not edges:
        return [], ["空线路: 从 IN 格拖动开始画线"], False, [], set()

    # ---- 同格 IN/OUT (冰上垂直交叉) ----
    # IN 与 OUT 可以落在同一个**角冰格**的两条互相垂直的外边框上: 该格被横竖各穿一次。
    # 玩家画了出界短边时它就是个普通的度数 4 冰格; 没画短边时格内只剩两条互相垂直的格内边
    # —— 那不是"冰格转弯"(冰上本来就不许转弯), 而是交叉缺了那两条短边。
    fin0, fout0 = puz.fin, puz.fout
    shared_cell = None
    if fin0["x"] is not None and fout0["x"] is not None \
            and (fin0["x"], fin0["y"]) == (fout0["x"], fout0["y"]) \
            and AXIS.get(fin0.get("side")) is not None \
            and AXIS.get(fout0.get("side")) is not None \
            and AXIS[fin0["side"]] != AXIS[fout0["side"]]:
        shared_cell = (fin0["x"], fin0["y"])

    def shared_cross(x, y, ns):
        """同格 IN/OUT 的"未画出界短边"形式: 两条格内边必须一条落在 IN 轴、一条落在 OUT 轴。"""
        if shared_cell != (x, y) or len(ns) != 2:
            return False
        ax = {0 if q[1] == y else 1 for q in ns}          # 0 = 横向格内边, 1 = 竖向格内边
        return ax == {AXIS[fin0["side"]], AXIS[fout0["side"]]}

    # ---- 局部检查: 分叉 / 白格交叉 / 冰格转弯 ----
    # (IN/OUT 所在的冰格允许度数 3: 起点/终点边 + 之后的一次垂直交叉)
    inout_cells = {(fin0["x"], fin0["y"]), (fout0["x"], fout0["y"])}
    for y in range(h):
        for x in range(w):
            ns = adj.get((x, y))
            if not ns:
                continue
            d = len(ns)
            if puz.cells[y][x] == "i":
                if d == 3 and (x, y) not in inout_cells:
                    errors.append(f"冰格 ({x},{y}) 线路分叉")
                elif d == 2 and (ns[0][0] - x) * (ns[1][0] - x) + \
                        (ns[0][1] - y) * (ns[1][1] - y) != -1 and not shared_cross(x, y, ns):
                    errors.append(f"冰格 ({x},{y}) 转弯")
            elif d == 3:
                errors.append(f"白格 ({x},{y}) 线路分叉")
            elif d >= 4:
                errors.append(f"白格 ({x},{y}) 十字交叉 (只有冰格允许交叉)")

    if puz.fin["x"] is None or puz.fout["x"] is None:
        incompletes.append("题面尚未放置 IN/OUT")
        return errors, incompletes, False, [], set()

    fin, fout = puz.fin, puz.fout
    in_cell = (fin["x"], fin["y"])
    out_cell = (fout["x"], fout["y"])

    def stub_of(f):
        if not f.get("side"):
            return None
        dx, dy = DIRS[f["side"]]
        return frozenset(((f["x"], f["y"]), (f["x"] + dx, f["y"] + dy)))

    in_stub, out_stub = stub_of(fin), stub_of(fout)
    route, route_edges = [], set()

    # ---- 起点 (stNoLine): 边框 IN 画了入界线 → 从界外进入; 未画入界线时
    #      线路可以直接从 IN 格出发 (与"照抄解不必画出界线"一致); 内部 IN 同理。
    #      IN 在冰格上时, 除出发边外还允许被垂直交叉一次 (度数 3);
    #      IN/OUT 同格(未画出界短边)时该格度数正好 2 (横竖各一条格内边) ----
    ice_in = puz.cells[in_cell[1]][in_cell[0]] == "i"
    dirv = None
    if in_stub is not None and in_stub in edges:
        route_edges.add(in_stub)
        dx, dy = DIRS[OPP[fin["side"]]]
        dirv = (dx, dy)
        in_ok = True
    else:
        d_in = len(adj.get(in_cell, ()))
        if d_in == 0:
            incompletes.append("IN 处未画线")
            in_ok = False
        elif not (d_in == 1 or (ice_in and d_in in (2, 3))):
            errors.append("IN 格线路应终止于起点 (不得直线穿过)")
            in_ok = False
        else:
            in_ok = True

    # ---- 终点声明: 内部 OUT 须终止于终点 (冰格上额外允许一次垂直交叉 / 同格 IN 的交叉形式) ----
    if out_stub is None:
        d_out = len(adj.get(out_cell, ()))
        ice_out = puz.cells[out_cell[1]][out_cell[0]] == "i"
        if d_out >= 2 and not (ice_out and d_out in (2, 3)):
            errors.append("OUT 格线路应终止于终点 (不得直线穿过)")

    reached_out = False
    if in_ok:
        cur = in_cell
        route.append(cur)
        if dirv is None:
            start_forced = tuple(DIRS[OPP[fin["side"]]]) if (ice_in and fin.get("side")) else None
            if start_forced is not None:
                # 冰格上的入界边已经定死了格内行进方向(冰上必须直行): 不能靠画出的边去猜 ——
                # IN/OUT 同格时该格有两条互相垂直的格内边, 猜不出哪条是起点那条。
                nb = (cur[0] + start_forced[0], cur[1] + start_forced[1])
                if frozenset((cur, nb)) not in edges:
                    errors.append("IN 冰格未沿入界方向直行")
            else:
                # 从 IN 格出发: 取它的出发边 (冰格度数 3 时取"独边", 成对的一轴是交叉)
                ns = adj[in_cell]
                if len(ns) == 1:
                    nb = ns[0]
                else:
                    by_axis = {}
                    for q2 in ns:
                        by_axis.setdefault("h" if q2[1] == cur[1] else "v", []).append(q2)
                    nb = next(lst[0] for lst in by_axis.values() if len(lst) == 1)
            dirv = (nb[0] - cur[0], nb[1] - cur[1])
            if in_stub is not None and ice_in and dirv != tuple(DIRS[OPP[fin["side"]]]):
                errors.append("IN 冰格未沿入界方向直行")
        elif not ice_in:
            # 经入界线进入白格 IN: 到达即转弯 (走向唯一的内部出线)
            out_cell_off = (in_cell[0] + DIRS[fin["side"]][0],
                            in_cell[1] + DIRS[fin["side"]][1])
            out_ns = [q2 for q2 in adj.get(in_cell, ()) if q2 != out_cell_off]
            if len(out_ns) == 1:
                nb = out_ns[0]
                dirv = (nb[0] - cur[0], nb[1] - cur[1])
        entered_dir = dirv
        guard = 0
        while True:
            guard += 1
            if guard > 8 * w * h + 64:      # 防御: 线路理论上不会成环
                errors.append("线路异常成环")
                break
            nxt = (cur[0] + dirv[0], cur[1] + dirv[1])
            e = frozenset((cur, nxt))
            if e not in edges:
                break                       # 线路在此中断 (lrDeadEnd → 未完成)
            mv = MOVE_OF[dirv]
            if inside(cur):                 # 墙 / 箭头 (lrReverse)
                mk = puz.edge.get(puz.edge_key(cur[0], cur[1], mv))
                if mk:
                    if mk["kind"] == "wall":
                        errors.append(f"穿墙: ({cur[0]},{cur[1]})-({nxt[0]},{nxt[1]})")
                    elif mk["kind"] == "arrow" and mk.get("dir") != mv:
                        errors.append(f"逆箭头: ({cur[0]},{cur[1]})-({nxt[0]},{nxt[1]})"
                                      f" 需要 {mk.get('dir')}")
            route_edges.add(e)
            if not inside(nxt):             # 越过边框 (lrOffField)
                if out_stub is not None and e == out_stub:
                    reached_out = True      # 恰好从 OUT 出界 → 线路完成
                else:
                    errors.append("线路从非 OUT 处越出边框")
                break
            route.append(nxt)
            entered_dir = dirv
            # 白格且恰好两条线 → 跟随线路转弯; 冰格必须直行 (转弯已由局部检查报错)
            if puz.cells[nxt[1]][nxt[0]] != "i" and len(adj[nxt]) == 2:
                a, b = adj[nxt]
                nb2 = b if a == cur else a
                dirv = (nb2[0] - nxt[0], nb2[1] - nxt[1])
            cur = nxt

        # ---- 终点判定: 从 OUT 出界, 或线路沿正确方向终止于 OUT 格均可 ----
        ended_at_out = bool(route) and route[-1] == out_cell
        if reached_out:
            pass
        elif ended_at_out:
            if out_stub is not None and puz.cells[out_cell[1]][out_cell[0]] == "i" \
                    and entered_dir != tuple(DIRS[fout["side"]]):
                errors.append("冰上 OUT 未沿出界方向直行穿出")
            # 其余: 线路终止于 OUT 格 (出界线可省) = 到达终点
        else:
            incompletes.append("线路尚未到达 OUT")

    # ---- 数字位次 (lrOrder) / 冰上数字重复 ----
    visit = {}
    slot = 0
    order_broken = False
    for p in route:
        visit[p] = visit.get(p, 0) + 1
        n = puz.numbers.get(p)
        if n is not None:
            slot += 1
            if n > 0 and n != slot and not order_broken:
                order_broken = True
                errors.append(f"数字位次错误: ({p[0]},{p[1]}) 的 {n} 位于第 {slot} 位")
    for (x, y), v in visit.items():
        if v > 1 and puz.cells[y][x] == "i" and puz.numbers.get((x, y), 0) > 0:
            errors.append(f"冰上数字格 ({x},{y}) 被多次经过")

    # ---- 游离线段 (lnPlLine) ----
    stray = edges - route_edges
    if stray:
        done = reached_out or (route and route[-1] == out_cell)
        if done:
            errors.append(f"存在未连入线路的多余线段 ({len(stray)} 段)")
        else:
            incompletes.append(f"另有 {len(stray)} 段线未与线路连接")

    # ---- 覆盖要求 (cuNoLine / nmUnpass / 强制标记) ----
    if route:
        rset = set(route)
        for (x, y), n in sorted(puz.numbers.items(), key=lambda kv: (kv[1], kv[0])):
            if (x, y) not in rset:
                incompletes.append(f"编号格未经过 ({x},{y})" +
                                   ("(\"?\")" if n < 0 else f"({n})"))
        for (x, y, s), mk in sorted(puz.edge.items()):
            if mk["kind"] in ("segment", "arrow") and not puz.is_frame_key((x, y, s)):
                dx, dy = DIRS[s]
                if frozenset(((x, y), (x + dx, y + dy))) not in route_edges:
                    incompletes.append(f"强制标记未经过 ({x},{y},{s})")
        if cover_all:
            for yy in range(h):
                for xx in range(w):
                    if puz.cells[yy][xx] == "w" and (xx, yy) not in rset:
                        incompletes.append(f"白格未经过 ({xx},{yy})")

    complete = not errors and not incompletes
    return errors, incompletes, complete, route, route_edges


# ============================================================
# GUI
# ============================================================
class App:
    TOOLS = [
        ("cell", "白/冰"),
        ("num", "数字"),
        ("qmark", "?格"),
        ("in", "IN"),
        ("out", "OUT"),
        ("seg", "线段"),
        ("arrow", "箭头"),
        ("wall", "墙"),
        ("erase", "橡皮"),
    ]
    SOLVE_MODES = [
        ("first", "只求解"),
        ("unique", "判断唯一性"),
        ("all", "求出所有解"),
    ]

    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.minsize(860, 560)
        self.puz = Puzzle(9, 9)
        self.undo_stack = []
        self.mode = tk.StringVar(value="edit")          # edit / play
        self.tool = tk.StringVar(value="cell")
        self.cover_all = tk.BooleanVar(value=True)
        self.solve_mode = tk.StringVar(value="unique")   # 默认"判断唯一性"(见 README「求解」节)
        self.max_sols = tk.IntVar(value=20)
        self.show_sol = tk.BooleanVar(value=False)
        self.cs = 46            # 格子像素
        self.offx = 46          # 网格原点(画布坐标)
        self.offy = 46
        self.solutions = []
        self.sol_idx = -1
        self._sol_from_archive = False   # 当前解是否来自存档(决定「求解」要不要先问一次)
        self.proc = None
        self.q = queue.Queue()
        self.solving = False
        self._stopped = False
        self._solver_diag = ""       # 求解器 stderr 诊断文本(不属于协议, 只按需展示)
        self._reader_done = True     # stdout/stderr 读取线程是否已排空
        self._flush_wait = 0         # `done` 后等待 stderr 收尾的轮数上限保护
        self._finished = False       # 本次求解是否已拿到结论(done/error/退出码), 跨轮询保持
        self.file_path = None
        self._paint_val = None       # 拖涂目标 ("i"/"w"/"erase")
        self._paint_last = None      # 拖涂上一次事件所在格 (补齐中间跨过的格子用)
        self._edge_start = None      # 边标记起点格 (x, y)
        self._edge_dirty = False     # 本次手势是否创建过标记 (松开时据此清空选择)
        self._inout_pending = None   # (which, (x, y)) 等待指定方向
        self.play_edges = set()      # 做题线段: frozenset({(x1,y1),(x2,y2)}), 可含出界端点
        self._check_after_solve = False  # 对照解: 等求解完成后自动比对
        self._drag_hist = None       # 做题手势: 经过格序列 (None = 无手势)
        self._drag_mode = None       # 做题手势模式: None/"add"/"del" (首个跨越边决定)
        self._drag_trail = []        # 做题手势操作记录: (edge, True/False) 或 None
        self._drag_undo_pushed = True    # 本次手势是否已压入撤销栈
        self._play_errors = []
        self._play_incomplete = []
        self._play_complete = False
        self._play_route = []            # 最近一次规则检查得到的线路 (盘内格序列)
        self._play_route_edges = set()
        self.deduce_state = None         # 规则推导状态(见 load_deduce_state): 叠加显示用
        self.deduce_path = None
        self._dup_nums = {}              # {数字: [格, …]} 重复的已知数字(整格标黄警告用)
        self._dup_positions = set()      # 上面那些格的集合(重绘时直接铺黄)
        self._puz_key = None             # 当前题面的内容指纹缓存(题面一变就清, 见 _cur_key)
        self._manual_answer = None       # 手动绘制核验解模式的状态(见 _start_manual_answer)
        self._num_pick_guard = False     # 在程序改数字选择器的值时不要再触发它自己的回调
        self.examples = self._scan_examples()
        self._set_window_icon()
        self._build_ui()
        self._bind_keys()
        if self.examples:
            self._on_example_selected()
        else:
            self._on_configure()
        self.root.after(60, lambda: self._on_configure())
        self.root.after(900, self._maybe_offer_shortcut)

    # ---------- 首次运行: 问一次要不要建带图标的快捷方式 ----------
    def _desktop_lnk(self):
        return os.path.join(os.path.expanduser("~"), "Desktop", LNK_NAME)

    def _here_lnk(self):
        return os.path.join(HERE, LNK_NAME)

    def _run_shortcut_tool(self, *flags):
        """调 tools/make_shortcut.py, 返回 (是否成功, 输出文本)。"""
        if not os.path.exists(SHORTCUT_TOOL):
            return False, "找不到 tools/make_shortcut.py"
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", SHORTCUT_TOOL, *flags],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
                               **_no_console())
        except Exception as e:
            return False, str(e)
        return r.returncode == 0, r.stdout.decode("utf-8", "replace").strip()

    def _maybe_offer_shortcut(self):
        """**只问一次**要不要建带图标的快捷方式；拒绝就在程序目录里建一个，不再打扰。

        为什么要有快捷方式: 用 `python icelom_gui.py` 启动时进程是 python.exe，
        Windows 任务栏按进程取图标，所以按钮可能显示成 python 的图标；
        从一个带图标的快捷方式启动才会稳定显示 IceLom 图标（.lnk 里写了图标路径 +
        与程序一致的 AppUserModelID，任务栏据此配对）。

        流程: 桌面已有 → 什么都不做; 没问过 → 问一次(记在 %APPDATA%/IceLom/gui.json);
              拒绝 → 在程序目录里建一个（不是每次问, 而是给一个能用的）; 建哪里都失败 → 静默。
        """
        if not sys.platform.startswith("win") or not os.path.exists(SHORTCUT_TOOL):
            return
        if not os.path.exists(ICON):
            return
        if os.path.exists(self._desktop_lnk()) or os.path.exists(self._here_lnk()):
            return                                     # 已经有一个了, 不再打扰
        cfg = _cfg()
        if cfg.get("shortcut_asked"):
            return                                     # 问过了: 不再问, 也不再建
        _cfg_set("shortcut_asked", True)               # 先记下"问过了", 保证只问一次
        if messagebox.askyesno(
                APP_TITLE,
                "要不要在桌面建一个带图标的快捷方式？\n\n"
                "直接敲 python 命令启动时，Windows 任务栏显示的是 python 的图标；\n"
                "从带图标的快捷方式启动就会显示 IceLom 图标。\n\n"
                "选「否」的话，我会在程序目录里放一个同样的快捷方式。\n"
                "（只问这一次；菜单「文件 → 创建桌面快捷方式」里随时可以再建）"):
            ok, out = self._run_shortcut_tool("--desktop", "--here")
            if ok and os.path.exists(self._desktop_lnk()):
                self.set_status("已创建桌面快捷方式: 以后从它启动, 任务栏会显示 IceLom 图标")
                return
            # 桌面写不进去(权限/受限环境) → 退到程序目录那个, 不弹报错骚扰
            ok2, _ = self._run_shortcut_tool("--here")
            self.set_status("桌面建不了快捷方式, 已在程序目录放了一个: " + LNK_NAME
                            if ok2 else "创建快捷方式失败: " + out[-120:])
            return
        ok, out = self._run_shortcut_tool("--here")
        if ok:
            self.set_status("已在程序目录创建快捷方式: " + LNK_NAME)
        else:
            self.set_status("创建快捷方式失败: " + out[-120:])

    # ---------- 窗口 / 任务栏图标 ----------
    def _set_window_icon(self):
        """把 assets/icelom.ico 设为窗口图标（缺失或平台不支持时静默跳过）。

        题面来自 assets/icon_puzzle.json（一道真实 2×2 题）, 由 tools/make_icon.py 生成;
        没有这个文件不影响任何功能, 只是窗口用系统默认图标。

        **注意**: `iconbitmap` 只负责"窗口标题栏 + 任务栏按钮"的外观, 而 Windows 任务栏按钮
        还会用到**进程**的图标 —— 用 `python icelom_gui.py` 启动时那个进程是 python.exe,
        所以光设 iconbitmap 任务栏仍可能是空白/蟒蛇图标。真正的修法有两步（都在这条链上）:
          1. `_set_app_user_model_id()`: 给进程一个自己的 AppUserModelID（见该函数);
          2. 让**快捷方式/启动器**带上这个图标（否则 Windows 仍拿 python.exe 的图标兜底）——
             见 `tools/make_shortcut.py`。
        注: `iconbitmap` 是 Windows/X11 的能力, macOS 上会抛 TclError —— 直接忽略。
        """
        _set_app_user_model_id()
        if not os.path.exists(ICON):
            return
        try:
            self.root.iconbitmap(default=ICON)
        except tk.TclError:
            pass

    # ---------- 示例列表 ----------
    @staticmethod
    def _scan_examples():
        if not os.path.isdir(EXAMPLE_DIR):
            return []
        out = []
        for fn in sorted(os.listdir(EXAMPLE_DIR)):
            if fn.lower().endswith(".json"):
                out.append(fn[:-5])
        return out

    def _on_example_selected(self, event=None):
        sel = self.example_var.get()
        path = os.path.join(EXAMPLE_DIR, sel + ".json")
        if os.path.exists(path):
            self.load_example_file(path)

    # ---------- 规则推导状态(tools/deduce.py 的产物)叠加显示 ----------
    def load_deduce_state(self, path):
        """载入规则推导器输出的状态 JSON, 叠加显示"已确定边 / 仍未定边"。

        显示约定(见 docs/算法说明.md §3.11):
          * 深粉红粗线  = 规则推导**确定**要走的边;
          * 浅蓝虚线    = 仍未定、但规则尚未排除的候选边(每条都还有可能);
          * 格内浅蓝小字 = 该格"候选边数"(>2 才显示, 2 表示该格已别无选择)。
        """
        try:
            obj = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"推导状态载入失败: {e}")
            return False
        puzfile = obj.get("puzzle")
        if puzfile and os.path.exists(puzfile):
            try:
                self._install_puzzle(Puzzle.from_json(
                    json.load(open(puzfile, encoding="utf-8"))), file_path=puzfile)
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"题面载入失败: {e}")
                return False
        self.deduce_state = obj
        self.deduce_path = path
        self.show_sol.set(False)
        n_det = len(obj.get("determined", []))
        n_und = len(obj.get("possible", []))
        self.redraw()
        self.set_status(f"推导状态: 确定边 {n_det} 条 / 仍未定 {n_und} 条 "
                        f"({os.path.basename(path)})")
        return True

    def on_open_deduce(self):
        path = filedialog.askopenfilename(
            title="打开推导状态 JSON (规则推导器输出的状态文件)",
            initialdir=HERE,
            filetypes=[("推导状态 JSON", "*.json"), ("全部文件", "*.*")])
        if path:
            self.load_deduce_state(path)

    def _draw_deduce_overlay(self, cv, ox, oy):
        """把推导状态画在盘面上: 候选边虚线 → 确定边实线 → 格内候选数。"""
        st = self.deduce_state
        if not st:
            return
        cs = self.cs
        pw_und = max(2, round(cs * 0.055))
        pw_det = max(3, round(cs * 0.11))
        for key in st.get("possible", []):
            if len(key) != 3 or key[2] not in ("R", "D"):
                continue
            x, y, s = key
            dx, dy = DIRS[s]
            cv.create_line(ox((x + 0.5) * cs), oy((y + 0.5) * cs),
                           ox((x + 0.5 + dx) * cs), oy((y + 0.5 + dy) * cs),
                           fill=COL_CAND, width=pw_und, dash=(max(2, round(cs * 0.12)),
                                                             max(2, round(cs * 0.10))),
                           tags="deduce_cand")
        for key in st.get("determined", []):
            if len(key) != 3 or key[2] not in ("R", "D"):
                continue
            x, y, s = key
            dx, dy = DIRS[s]
            cv.create_line(ox((x + 0.5) * cs), oy((y + 0.5) * cs),
                           ox((x + 0.5 + dx) * cs), oy((y + 0.5 + dy) * cs),
                           fill=COL_PATH, width=pw_det, capstyle="round",
                           tags="deduce_det")
        if cs >= 16:
            f = (UI_FONT, -max(7, int(round(cs * 0.30))))
            for row in st.get("cell_table", []):
                if row.get("avail", 0) <= 2:
                    continue
                cv.create_text(ox((row["x"] + 0.5) * cs), oy((row["y"] + 0.80) * cs),
                               text=str(row["avail"]), fill=COL_CAND, font=f,
                               tags="deduce_avail")

    def load_example_file(self, path):
        try:
            obj = json.load(open(path, encoding="utf-8"))
            p = Puzzle.from_json(obj)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"示例加载失败: {e}")
            return
        self.push_undo()
        self._install_puzzle(p, file_path=None)
        # 同步示例下拉框显示 (避免"显示的示例名与实际题面不一致")
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in self.examples:
            self.example_var.set(stem)
        note = obj.get("_note", "")
        msg = f"已加载示例 {stem}"
        if note:
            msg += f" — {note}"
        self._status_with_archive_note(msg)

    # ---------- UI 构建 ----------
    def _build_ui(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", font=UI_FONT)
        style.configure("TFrame", padding=1)
        style.configure("Tool.TLabelframe", padding=(6, 3))
        style.configure("Bar.TFrame", background="#eceff4")
        style.configure("TButton", padding=(8, 2))
        style.configure("TRadiobutton", padding=(4, 2))
        style.configure("TCheckbutton", padding=(4, 2))

        # 菜单栏: "文件"放两件不属于画题的事(建带图标的快捷方式、退出);
        # "查看"放求解器诊断(stderr 不属于协议, 只在需要时打开看, 见 on_show_diag)
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="新建", command=self.on_new, accelerator="Ctrl+N")
        filemenu.add_command(label="打开…", command=self.on_open, accelerator="Ctrl+O")
        filemenu.add_command(label="保存", command=self.on_save, accelerator="Ctrl+S")
        filemenu.add_command(label="另存为…", command=self.on_save_as, accelerator="Ctrl+Shift+S")
        filemenu.add_separator()
        filemenu.add_command(label="导出 Penpa+ 链接…", command=self.on_export_penpa)
        filemenu.add_separator()
        filemenu.add_command(label="创建桌面快捷方式（带图标）", command=self.on_make_shortcut)
        filemenu.add_separator()
        filemenu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=filemenu)
        viewmenu = tk.Menu(menubar, tearoff=0)
        viewmenu.add_command(label="求解器诊断…", command=self.on_show_diag,
                             accelerator="Ctrl+D")
        menubar.add_cascade(label="查看", menu=viewmenu)
        self.diag_menu = viewmenu
        try:
            self.root.config(menu=menubar)
        except tk.TclError:
            pass

        top = ttk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 2))
        ttk.Label(top, text="模式:").pack(side=tk.LEFT)
        for val, label in (("edit", "编辑"), ("play", "做题")):
            ttk.Radiobutton(top, text=label, value=val, variable=self.mode,
                            command=self._on_mode_change).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(top, text="示例:").pack(side=tk.LEFT)
        self.example_var = tk.StringVar()
        self.example_cb = ttk.Combobox(top, textvariable=self.example_var, width=22,
                                       state="readonly", values=list(self.examples))
        if self.examples:
            self.example_cb.current(0)
        self.example_cb.pack(side=tk.LEFT, padx=(2, 2))
        self.example_cb.bind("<<ComboboxSelected>>", self._on_example_selected)
        ttk.Button(top, text="新建", command=self.on_new).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="打开", command=self.on_open).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="保存", command=self.on_save).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="导入 URL", command=self.on_import_url).pack(side=tk.LEFT, padx=2)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(top, text="行").pack(side=tk.LEFT)
        self.sp_h = ttk.Spinbox(top, from_=1, to=30, width=3)
        self.sp_h.delete(0, "end"); self.sp_h.insert(0, "9")
        self.sp_h.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(top, text="列").pack(side=tk.LEFT)
        self.sp_w = ttk.Spinbox(top, from_=1, to=30, width=3)
        self.sp_w.delete(0, "end"); self.sp_w.insert(0, "9")
        self.sp_w.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="调整大小", command=self.on_resize).pack(side=tk.LEFT, padx=2)

        bar2 = ttk.Frame(self.root)
        bar2.pack(side=tk.TOP, fill=tk.X, padx=6, pady=2)
        ttk.Label(bar2, text="工具:").pack(side=tk.LEFT)
        self.tool_btns = []
        for val, label in self.TOOLS:
            rb = ttk.Radiobutton(bar2, text=label, value=val, variable=self.tool,
                                 command=self._on_tool_change)
            rb.pack(side=tk.LEFT, padx=2)
            self.tool_btns.append(rb)
        ttk.Separator(bar2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        # 数字工具要放的数字: 可直接输入, 也可用上下箭头选(上下箭头会跳过盘面上已有的数字)
        ttk.Label(bar2, text="数字").pack(side=tk.LEFT)
        self.num_pick = ttk.Spinbox(bar2, from_=1, to=999, width=4)
        self.num_pick.set("1")
        self.num_pick.pack(side=tk.LEFT, padx=(2, 2))
        self.num_pick.bind("<Up>", lambda e: self._step_number_pick(+1))
        self.num_pick.bind("<Down>", lambda e: self._step_number_pick(-1))
        self.num_pick.bind("<Return>", lambda e: self._on_number_pick_typed())
        self.num_pick.bind("<FocusOut>", lambda e: self._on_number_pick_typed())
        ttk.Separator(bar2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self.btn_clear_play = ttk.Button(bar2, text="清除线路", command=self.on_clear_play,
                                         state=tk.DISABLED)
        self.btn_clear_play.pack(side=tk.LEFT, padx=2)

        bar3 = ttk.Frame(self.root)
        bar3.pack(side=tk.TOP, fill=tk.X, padx=6, pady=2)
        ttk.Checkbutton(bar3, text="必须经过所有白格",
                        variable=self.cover_all).pack(side=tk.LEFT)
        ttk.Separator(bar3, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(bar3, text="求解:").pack(side=tk.LEFT)
        for val, label in self.SOLVE_MODES:
            rb = ttk.Radiobutton(bar3, text=label, value=val, variable=self.solve_mode,
                                 command=self._on_solve_mode_change)
            rb.pack(side=tk.LEFT, padx=2)
        ttk.Label(bar3, text="解数量上限").pack(side=tk.LEFT, padx=(8, 2))
        self.sp_max = ttk.Spinbox(bar3, from_=1, to=1000000, width=6,
                                  textvariable=self.max_sols, state=tk.DISABLED)
        self.sp_max.pack(side=tk.LEFT)
        ttk.Separator(bar3, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        # 推理预算 = 本次求解的时限(秒), 直接输入; 记在 gui.json, 下次启动照旧
        _budget = DEFAULT_TIME_LIMIT_S
        try:
            _budget = int(_cfg().get("time_limit_s", DEFAULT_TIME_LIMIT_S))
        except Exception:
            pass
        _budget = min(max(_budget, 1), 86400)
        ttk.Label(bar3, text="推理预算(秒)").pack(side=tk.LEFT)
        self.sp_time = ttk.Spinbox(bar3, from_=1, to=86400, width=6)
        self.sp_time.set(str(_budget))
        self.sp_time.pack(side=tk.LEFT, padx=(2, 0))

        bar4 = ttk.Frame(self.root)
        bar4.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 2))
        self.btn_solve = ttk.Button(bar4, text="求解", command=self.on_solve)
        self.btn_solve.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(bar4, text="停止", command=self.on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(4, 0))
        ttk.Separator(bar4, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(bar4, text="撤回 (Ctrl+Z)", command=self.on_undo).pack(side=tk.LEFT)
        ttk.Separator(bar4, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(bar4, text="◀", width=3, command=lambda: self.nav(-1)).pack(side=tk.LEFT)
        self.sol_label = ttk.Label(bar4, text="解: -/-", width=10, anchor=tk.CENTER)
        self.sol_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(bar4, text="▶", width=3, command=lambda: self.nav(1)).pack(side=tk.LEFT)
        self.btn_show_sol = ttk.Button(bar4, text="显示解", command=self.on_toggle_show_sol,
                                       state=tk.DISABLED)
        self.btn_show_sol.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(bar4, text="检查解", command=self.on_check_rules).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar4, text="对照解", command=self.on_check_solution).pack(
            side=tk.LEFT, padx=(6, 0))
        self.btn_export_image = ttk.Button(bar4, text="导出解为图片",
                                           command=self.on_export_image)
        self.btn_export_image.pack(side=tk.LEFT, padx=(10, 0))
        self.btn_export_penpa = ttk.Button(bar4, text="导出 Penpa+ 链接",
                                           command=self.on_export_penpa)
        self.btn_export_penpa.pack(side=tk.LEFT, padx=(6, 0))
        self.btn_open_deduce = ttk.Button(bar4, text="打开推导状态",
                                          command=self.on_open_deduce)
        self.btn_open_deduce.pack(side=tk.LEFT, padx=(6, 0))

        # 手动绘制核验解时的操作条(平时 pack_forget 藏着, 见 _sync_manual_ui)
        self.bar_manual = ttk.Frame(self.root)
        ttk.Label(self.bar_manual, text="手动绘制答案:", font=UI_FONT).pack(side=tk.LEFT)
        ttk.Button(self.bar_manual, text="完成手动绘制",
                   command=self._finish_manual_answer).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(self.bar_manual, text="取消", command=self._cancel_manual_answer).pack(
            side=tk.LEFT, padx=2)
        ttk.Label(self.bar_manual, text="（画什么、画成什么样都行；那条线原样当 Penpa+ 的对照答案）",
                  foreground="#555555").pack(side=tk.LEFT, padx=(8, 0))

        self.canvas = tk.Canvas(self.root, bg="#fdfdfd", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(2, 0))
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Configure>", self._on_configure)

        self.status = tk.Label(self.root, text="就绪", anchor="w",
                               font=UI_FONT, bg="#eceff4", padx=8, pady=3)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self._on_tool_change()
        self._on_solve_mode_change()
        self._update_diag_menu()     # 还没求解过 → 「求解器诊断」先置灰

    def _bind_keys(self):
        self.root.bind("<Control-z>", lambda e: self.on_undo())
        self.root.bind("<Control-o>", lambda e: self.on_open())
        self.root.bind("<Control-s>", lambda e: self.on_save())
        self.root.bind("<Control-Shift-S>", lambda e: self.on_save_as())
        self.root.bind("<Control-n>", lambda e: self.on_new())
        self.root.bind("<Control-d>", lambda e: self.on_show_diag())
        self.root.bind("<Escape>", lambda e: self._cancel_pending())

    # ---------- 求解器诊断 (stderr) ----------
    def _update_diag_menu(self):
        """没有诊断文本时把「查看 → 求解器诊断」置灰。"""
        try:
            self.diag_menu.entryconfig(0, state=(tk.NORMAL if self._solver_diag.strip()
                                                 else tk.DISABLED))
        except Exception:
            pass

    def on_show_diag(self):
        """打开一个**非模态**只读窗口, 显示最近一次求解的 stderr 诊断。

        求解器把 stderr 当诊断通道用（`docs/求解器协议.md` §1 明确"不属于协议"）：
        - 搜遍全树仍无解 → `[unsat-diag]` 打印最深现场盘面与开放端点；
        - `ICELOM_DIAG_ON_ABORT=1` → 超时中止时也打印现场；
        - `ICELOM_DUMP=1` → 追加最深现场的边集 JSON。

        这些都是**正常输出**，用来回答"为什么无解/搜到哪一步"。旧版本把它们当成
        "求解器异常输出"弹模态错误框，于是每次遇到无解的题面都会糊一脸 ASCII 盘面并卡住界面。
        现在改成按需查看（Ctrl+D）。
        """
        text = self._solver_diag.rstrip()
        if not text:
            self.set_status("最近一次求解没有诊断输出（无解时的 [unsat-diag] 会出现在这里）")
            return
        win = tk.Toplevel(self.root)
        win.title("求解器诊断 (stderr)")
        win.geometry("820x560")
        win.transient(self.root)
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))
        vbar = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        hbar = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
        txt = tk.Text(frame, wrap=tk.NONE, font=MONO_FONT, height=20,
                      yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.config(command=txt.yview)
        hbar.config(command=txt.xview)
        txt.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        txt.insert("1.0", text)
        txt.config(state=tk.DISABLED)        # 只读, 但仍可选中复制
        ttk.Label(win, text="求解器的 stderr 是诊断信息（不属于求解协议），"
                            "不影响求解结论。", foreground="#555555").pack(
            side=tk.TOP, anchor="w", padx=8, pady=(4, 0))
        ttk.Button(win, text="关闭", command=win.destroy).pack(
            side=tk.BOTTOM, anchor="e", padx=8, pady=6)
        win.bind("<Escape>", lambda e: win.destroy())

    # ---------- 快捷方式（任务栏图标） ----------
    def on_make_shortcut(self):
        """菜单项: 建桌面快捷方式; 桌面写不进去就退到程序目录里那个。

        任务栏图标靠带图标的快捷方式（详见 tools/make_shortcut.py 的说明）。
        """
        if not os.path.exists(SHORTCUT_TOOL):
            messagebox.showerror(APP_TITLE, "找不到 tools/make_shortcut.py")
            return
        ok, out = self._run_shortcut_tool("--desktop", "--here")
        made = [l.strip() for l in out.splitlines() if l.strip().startswith("WROTE")]
        if ok and os.path.exists(self._desktop_lnk()):
            messagebox.showinfo(APP_TITLE, "已创建桌面快捷方式（图标来自 assets/icelom.ico）:\n"
                                + "\n".join(made)
                                + "\n\n以后从它启动，任务栏就会显示 IceLom 图标。")
        elif os.path.exists(self._here_lnk()):
            messagebox.showinfo(APP_TITLE, "桌面建不了快捷方式（权限/受限环境），"
                                "已在程序目录放了一个：\n" + self._here_lnk()
                                + "\n\n从它启动同样会显示 IceLom 图标。")
        else:
            messagebox.showwarning(APP_TITLE, "没能创建快捷方式:\n\n" + out[-600:])

    # ---------- 布局(随窗口缩放, 网格居中) ----------
    def _on_configure(self, event=None):
        if event is not None and event.widget is not self.canvas:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 50 or ch < 50:
            return
        w, h = self.puz.w, self.puz.h
        # 放大不设低上限 (全屏时盘面尽量占满窗口); 预留 IN/OUT 箭头/标签/出界线的边距。
        # 边距按"真的有边框 IN/OUT 的那一侧"算: 箭头长 1 格 ⇒ 外伸 0.5cs, 标签在其正后方
        # (U/D 侧标签只占字高; L/R 侧是横排文字, 按字号估宽)。
        pad_x = pad_y = 1.2
        for f, lab in ((self.puz.fin, "IN"), (self.puz.fout, "OUT")):
            if f["x"] is None or not f.get("side"):
                continue
            if f["side"] in ("L", "R"):
                pad_x = max(pad_x, 0.5 + 0.12 + 0.36 * len(lab) + 0.2)
            else:
                pad_y = max(pad_y, 0.5 + 0.12 + 0.55 + 0.2)
        cs = min((cw - 24) / (w + 2 * pad_x), (ch - 24) / (h + 2 * pad_y), 200)
        self.cs = max(int(cs), 12)
        self.offx = (cw - w * self.cs) / 2
        self.offy = (ch - h * self.cs) / 2
        self.redraw()

    # ---------- 状态/撤销 ----------
    def push_undo(self, entry=None):
        if entry is None:
            entry = {"kind": "puz", "json": json.dumps(self.puz.to_json(), ensure_ascii=False)}
        self.undo_stack.append(entry)
        if len(self.undo_stack) > 500:
            self.undo_stack.pop(0)

    def on_undo(self):
        if not self.undo_stack:
            self.set_status("没有可撤回的操作")
            return
        entry = self.undo_stack.pop()
        kind = entry.get("kind")
        if self._manual_active():
            # 手动绘制模式下撤回 = 先退出这个模式(丢掉半截的线), 再按记录的语义继续
            self._manual_answer = None
            self._clear_play_edges(silent=True)
            self._sync_manual_ui(False)
        if kind == "solve":
            # 撤回「求解」: 打断正在进行的求解, 并清掉解显示
            if self.solving:
                self._kill_solver()
                self.set_status("已打断求解", "err")
            else:
                self.set_status("已撤回求解结果")
            self.clear_solution()
            return
        if kind == "play":
            self.play_edges = {frozenset((tuple(a), tuple(b))) for a, b in entry["edges"]}
            self._refresh_play_state()
            self.redraw()
            self.set_status("已撤回线路操作")
            return
        # kind == puz
        obj = json.loads(entry["json"])
        self.puz = Puzzle.from_json(obj)
        self._puz_key = None                # 撤回也换了题面 → 指纹缓存作废
        if self._manual_active():
            self._manual_answer = None      # 撤回换了题面 → 手动绘制模式作废
            self._sync_manual_ui(False)
        self._sync_size_spin()
        self.play_edges = set()
        self._play_route = []
        self._play_route_edges = set()
        self.clear_solution()
        self.redraw()
        self.set_status("已撤销")

    def _sync_size_spin(self):
        self.sp_w.delete(0, "end"); self.sp_w.insert(0, str(self.puz.w))
        self.sp_h.delete(0, "end"); self.sp_h.insert(0, str(self.puz.h))

    def set_status(self, text, kind="info"):
        color = {"info": "#000000", "solving": "#1565c0",
                 "ok": "#2e7d32", "err": "#c62828"}.get(kind, "#000000")
        self.status.config(text=text, fg=color)

    # ---------- 模式切换 ----------
    def _on_mode_change(self):
        play = self.mode.get() == "play"
        for rb in self.tool_btns:
            rb.configure(state=(tk.DISABLED if play else tk.NORMAL))
        self.btn_clear_play.configure(state=(tk.NORMAL if play else tk.DISABLED))
        self._cancel_pending()
        if play:
            if self.play_edges:
                self._refresh_play_state()      # 题面可能被编辑过, 重新判定一次
            else:
                self.set_status("做题模式: 按住拖动画线 (可画多段/可从任意格起笔/"
                                "可在 IN·OUT 处画出界外); 拖过已有线段=擦除, "
                                "拖回上一步=回退; 右键清除线路; "
                                "「检查解」按规则判定, 「对照解」与答案比对")
        else:
            self.set_status("编辑模式: " + self._tool_hint())
        self.redraw()

    def _on_solve_mode_change(self):
        is_all = self.solve_mode.get() == "all"
        self.sp_max.configure(state=(tk.NORMAL if is_all else tk.DISABLED))

    def _cancel_pending(self):
        changed = False
        if self._edge_start is not None:
            self._edge_start = None
            changed = True
        if self._inout_pending is not None:
            self._inout_pending = None
            changed = True
            self.set_status("已取消方向指定")
        if changed:
            self.redraw()

    # ---------- 工具提示 ----------
    def _tool_hint(self):
        return {
            "cell": "点击/拖动 涂 白格或冰格 (IN/OUT 也可以放在冰格上)",
            "num": "点击空格放置「数字」框里的数(可直接输入或按 ↑↓ 选, ↑↓ 会跳过已有的数字); "
                   "放完自动跳到下一个可用数字; 点击已有数字的格删除。数字重复会标黄警告",
            "qmark": "点击格子放置/取消 \"?\" 格 (数字未知的编号格, 冰格上也可放; "
                     "\"?\" 冰格允许被十字交叉穿越两次, 两次可以是两个不同的数)",
            "in": "点击格子放置 IN: 内部格=线路起点(格内显示 IN); 边界格=入界箭头; "
                  "角上冰格需再点击相邻格指定入界方向",
            "out": "点击格子放置 OUT: 内部格=线路终点(格内显示 OUT); 边界格=出界箭头; "
                   "角上冰格需再点击相邻格指定出界方向",
            "seg": "点击起点格再点击相邻格 (或直接拖动) → 强制线段(必经); 重复创建同一线段取消",
            "arrow": "点击起点格再点击相邻格 (或直接拖动) → 箭头(定向必经); "
                     "重复创建同一箭头清除; 每次创建后不保留选择",
            "wall": "点击起点格再点击相邻格 (或直接拖动) → 墙(禁止经过); 重复创建同一墙取消",
            "erase": "点击/拖动 清除格子内容; 点边缘清除边标记 (右键=橡皮)",
        }.get(self.tool.get(), "")

    def _on_tool_change(self):
        self._edge_start = None
        if self._inout_pending is not None:
            self._inout_pending = None
        self.set_status(self._tool_hint())
        self.redraw()

    # ---------- 命中测试 ----------
    def _hit_test(self, ex, ey, allow_out=False):
        """返回 (x, y, side); side=靠近的边('R/D/L/U')或 None(格子中央)。
        allow_out=True 时允许返回出界一格的坐标 (做题模式画 IN/OUT 出界短边)。"""
        cs = self.cs
        cx = self.canvas.canvasx(ex) - self.offx
        cy = self.canvas.canvasy(ey) - self.offy
        x, y = int(cx // cs), int(cy // cs)
        lim = 1 if allow_out else 0
        if not (-lim <= x < self.puz.w + lim and -lim <= y < self.puz.h + lim):
            return None
        lx, ly = cx - x * cs, cy - y * cs
        bz = max(7, cs * 0.22)
        cands = []
        if lx < bz:
            cands.append(("L", lx))
        if lx > cs - bz:
            cands.append(("R", cs - lx))
        if ly < bz:
            cands.append(("U", ly))
        if ly > cs - bz:
            cands.append(("D", cs - ly))
        cands.sort(key=lambda t: t[1])
        return x, y, (cands[0][0] if cands else None)

    def on_right_click(self, ev):
        if self.mode.get() == "play":
            self.on_clear_play()
            return
        saved = self.tool.get()
        self.tool.set("erase")
        self.on_press(ev)
        self.tool.set(saved)

    @staticmethod
    def _adjacent(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    # ---- 按下 ----
    def on_press(self, ev):
        if self.solving:
            return
        play = self.mode.get() == "play"
        hit = self._hit_test(ev.x, ev.y, allow_out=play)
        if not hit:
            return
        x, y, side = hit
        if play:
            self._play_press(x, y)
            return
        tool = self.tool.get()
        p = self.puz

        # IN/OUT 等待指定方向 (角上冰格)
        if self._inout_pending is not None:
            which, (px, py) = self._inout_pending
            if self._adjacent((px, py), (x, y)):
                self._finish_inout_direction(px, py, x, y, which)
            else:
                self._inout_pending = None
                self.set_status("已取消方向指定")
                self.redraw()
            return

        if tool in ("seg", "arrow", "wall"):
            if self._edge_start == (x, y):
                self._edge_start = None   # 再点同格 → 取消
                self._edge_dirty = False
                self.redraw()
                return
            if self._edge_start and self._adjacent(self._edge_start, (x, y)):
                self._edge_from_cells(self._edge_start[0], self._edge_start[1], x, y, tool)
                # 从新格继续(本次按下可能演变为拖动), 松开鼠标时清空
                self._edge_start = (x, y)
                self._edge_dirty = True
            else:
                self._edge_start = (x, y)
                self._edge_dirty = False
                self.set_status("已选起点格: 再点击相邻格或拖动生成标记 (Esc 取消)")
                self.redraw()
            return

        if tool == "in":
            self._place_inout(x, y, "fin", side)
            return
        if tool == "out":
            self._place_inout(x, y, "fout", side)
            return

        if tool in ("cell", "erase"):
            self.push_undo()
            if tool == "cell":
                self._paint_val = "i" if p.cells[y][x] == "w" else "w"
                p.cells[y][x] = self._paint_val
                self.clear_solution()
            else:
                self._paint_val = "erase"
                self._erase_at(x, y, side)
            self._paint_last = (x, y)      # 拖动涂抹的补齐起点(见 _paint_drag)
            self.redraw()
            return

        if tool == "num":
            # 数字不必连续, 因此放置/删除都**不改动其它数字**(避免把跳号题面悄悄改写成 1..K)
            self._toggle_number(x, y)
            return

        if tool == "qmark":
            self._toggle_number(x, y, qmark=True)
            return

    # ---- IN/OUT 放置 ----
    @staticmethod
    def _axis(side):
        """边的轴向 (0 横 / 1 竖); side=None(内部 IN/OUT) 无轴 → None。"""
        return AXIS.get(side) if side else None

    def _share_side(self, x, y, which):
        """同格共存的另一端点已存在时, 新端点该放在哪条外边框上 (None = 不能共存)。

        冰格允许被**垂直交叉**穿过两次(横竖各一次), 因此 IN 与 OUT 可以落在同一个角冰格的
        两条互相垂直的外边框上: 一条入界、一条出界, 该格被横竖各穿一次
        (pzprjs 官方引擎判 PASS; 求解器/验证器/规则引擎都按"两轴各 2 条连接"建模)。
        角上冰格只有两条外边框, 另一端点占了其中一条 ⇒ 新端点只能放在剩下那条上(方向唯一),
        所以这里直接给出 side, 不用再走"点击相邻格指定方向"。
        """
        p = self.puz
        other = p.fout if which == "fin" else p.fin
        if other["x"] != x or other["y"] != y or other["x"] is None:
            return None
        if p.cells[y][x] != "i":
            return None                    # 白格至多经过一次 ⇒ IN/OUT 不能同格
        left = [s for s in p.boundary_sides(x, y) if s != other.get("side")]
        if len(left) != 1:
            return None
        a, b = self._axis(left[0]), self._axis(other.get("side"))
        return left[0] if (a is not None and b is not None and a != b) else None

    def _set_inout(self, which, x, y, side):
        """写入端点。同格已占着另一端点时: 冰格 + 两条边**互相垂直** ⇒ 两者共存
        (冰上垂直交叉); 其余情况仍是旧行为 —— 顶掉同格的另一端点。"""
        p = self.puz
        kept = False
        other = p.fout if which == "fin" else p.fin
        if (other["x"], other["y"]) == (x, y) and other["x"] is not None:
            a, b = self._axis(side), self._axis(other.get("side"))
            if p.cells[y][x] == "i" and a is not None and b is not None and a != b:
                kept = True
            else:
                setattr(p, "fout" if which == "fin" else "fin",
                        {"x": None, "y": None, "side": None})
        setattr(p, which, {"x": x, "y": y, "side": side})
        return kept

    def _place_inout(self, x, y, which, side=None):
        p = self.puz
        cur = getattr(p, which)
        if (cur["x"], cur["y"]) == (x, y) and cur["x"] is not None:
            # 再点同格 → 取消
            self.push_undo()
            setattr(p, which, {"x": None, "y": None, "side": None})
            self.clear_solution()
            self.redraw()
            return
        name = "IN" if which == "fin" else "OUT"
        shared = self._share_side(x, y, which)          # 同一角冰格的另一条边
        if shared is not None:
            self.push_undo()
            self._set_inout(which, x, y, shared)
            self.clear_solution()
            self.redraw()
            self.set_status(f"已放置{name}于 ({x},{y}) {shared} 侧: "
                            f"与另一端点同格, 冰上垂直交叉各穿一次")
            return
        sides = p.boundary_sides(x, y)
        # 角上冰格(两条外边框互相垂直): 方向不唯一, 进入"指定方向"流程。
        # 两条外边框同轴的情形(1 行 / 1 列的盘面)由 side 只按点击位置选, 不走这个流程 ——
        # 那种格子上"点击相邻格"给不出同轴方向, 会一直被拒绝。
        if len(sides) == 2 and p.cells[y][x] == "i" and self._axis(sides[0]) != self._axis(sides[1]):
            self._inout_pending = (which, (x, y))
            self._edge_start = None
            dir_word = "入界(线路去的方向)" if which == "fin" else "出界(线路来的方向)"
            self.set_status(f"{name} 在角上的冰格: 请点击相邻格指定{dir_word} (Esc 取消)")
            self.redraw()
            return
        self.push_undo()
        # 方向唯一时: 点击靠近哪条外边框就放哪条, 否则取第一条(内部格: side=None)
        side = side if side in sides else (sides[0] if sides else None)
        kept = self._set_inout(which, x, y, side)
        self.clear_solution()
        self.redraw()
        if side is None:
            self.set_status(f"已放置{name}于内部格 "
                            f"({x},{y}): 线路以该格为起/终点")
        else:
            self.set_status(f"已放置{'IN' if which == 'fin' else 'OUT'}于边界格 "
                            f"({x},{y}) {side} 侧, 方向自动生成")

    def _finish_inout_direction(self, px, py, cx_, cy_, which):
        """角上冰格 IN/OUT: 根据点击的相邻格确定入/出界方向。
        IN: 线路去向 = pending格→点击格, 入界 side 为其反向;
        OUT: 线路来向 = 点击格→pending格, 出界 side 即该方向(冰格直行出界)。"""
        p = self.puz
        d_cell_to_click = MOVE_OF.get((cx_ - px, cy_ - py))
        self._inout_pending = None
        if d_cell_to_click is None:
            self.redraw()
            return
        travel = d_cell_to_click if which == "fin" else OPP[d_cell_to_click]
        side = OPP[travel] if which == "fin" else travel
        if side not in p.boundary_sides(px, py):
            self.set_status("该方向不是此角的出界方向, 已取消", "err")
            self.redraw()
            return
        self.push_undo()
        kept = self._set_inout(which, px, py, side)
        self.clear_solution()
        self.redraw()
        self.set_status(f"已放置{'IN' if which == 'fin' else 'OUT'}于角格 "
                        f"({px},{py}) {side} 侧" +
                        ("(与另一端点同格, 冰上垂直交叉各穿一次)" if kept else ""))

    # ---- 拖动 ----
    def on_motion(self, ev):
        if self.solving:
            return
        play = self.mode.get() == "play"
        hit = self._hit_test(ev.x, ev.y, allow_out=play)
        if not hit:
            return
        x, y, side = hit
        if play:
            self._play_motion(x, y)
            return
        tool = self.tool.get()

        if self._paint_val is not None:
            self._paint_drag(x, y, side)
            return

        if self._edge_start and tool in ("seg", "arrow", "wall"):
            if (x, y) != self._edge_start and self._adjacent(self._edge_start, (x, y)):
                self._edge_from_cells(self._edge_start[0], self._edge_start[1], x, y, tool)
                self._edge_start = (x, y)
                self._edge_dirty = True
                self.redraw()

    def _paint_drag(self, x, y, side):
        """拖动涂抹: 把上一次事件到本次事件之间跨过的格子**全部**补上。

        鼠标事件不保证逐格(快速拖动一次可能跨好几格, 系统还会合并移动), 只处理"当前那一格"
        就会漏格。这里按格心连线一格格补齐 —— 不新增任何鼠标监听, 仍然只处理已有的 motion
        事件, 并且整次事件最多重绘一次(所以比逐格重绘更快)。
        """
        p = self.puz
        val = self._paint_val
        last = self._paint_last if self._paint_last else (x, y)
        self._paint_last = (x, y)
        if val == "erase" and side is not None:
            # 靠近外边框的那一次 = 擦边标记: 只擦当前这一条边, 不做补齐
            self._erase_at(x, y, side)
            self.redraw()
            return
        changed = False
        if val == "erase":
            for (bx, by) in cell_line(last, (x, y)):
                changed = self._erase_at(bx, by, None) or changed
        else:
            for (bx, by) in cell_line(last, (x, y)):
                if p.cells[by][bx] != val:
                    p.cells[by][bx] = val
                    changed = True
            if changed:
                self.clear_solution()
        if changed:
            self.redraw()

    def on_release(self, ev):
        self._paint_val = None
        self._paint_last = None
        # 结束做题手势 (一次手势 = 一条撤销记录, 在首次实际修改时入栈)
        if self._drag_hist is not None:
            self._drag_hist = None
            self._drag_mode = None
            self._drag_trail = []
            self._drag_undo_pushed = True
        # 本次按下手势创建过标记 → 松开时清空选择 (创建箭头后不保留任何选择状态);
        # 仅点击选中起点(未创建)时保留选择, 供"点击起点→点击相邻格"流程使用。
        if self._edge_dirty:
            self._edge_dirty = False
            if self._edge_start is not None:
                self._edge_start = None
                self.redraw()

    # ---- 边标记 ----
    def _edge_from_cells(self, x1, y1, x2, y2, tool):
        """在相邻两格 (x1,y1)->(x2,y2) 之间放置/取消 标记。方向 = 行进方向。
        返回操作结果: "created"/"removed"/None。"""
        p = self.puz
        if x2 == x1 + 1:
            key, travel = (x1, y1, "R"), "R"
        elif x2 == x1 - 1:
            key, travel = (x2, y2, "R"), "L"
        elif y2 == y1 + 1:
            key, travel = (x1, y1, "D"), "D"
        else:
            key, travel = (x2, y2, "D"), "U"
        cur = p.edge.get(key)
        self.push_undo()
        self.clear_solution()
        res = None
        if tool == "seg":
            if cur and cur["kind"] == "segment":
                del p.edge[key]
                res = "removed"
            else:
                p.edge[key] = {"kind": "segment"}
                res = "created"
        elif tool == "wall":
            if cur and cur["kind"] == "wall":
                del p.edge[key]
                res = "removed"
            else:
                p.edge[key] = {"kind": "wall"}
                res = "created"
        else:  # arrow
            if cur and cur["kind"] == "arrow" and cur.get("dir") == travel:
                del p.edge[key]           # 从头再创建相同箭头 → 清除
                res = "removed"
            else:
                p.edge[key] = {"kind": "arrow", "dir": travel}
                res = "created"
        self.redraw()
        return res

    def _erase_at(self, x, y, side):
        """擦掉 (x,y) 的 side 侧边标记 / 整格内容。返回是否真的改动了题面
        (拖动涂抹按这个返回值决定要不要重绘, 空扫一片不重绘)。"""
        p = self.puz
        changed = False
        if side:
            key = p.edge_key(x, y, side)
            if key in p.edge:
                del p.edge[key]
                changed = True
            if (p.fin["x"], p.fin["y"], p.fin.get("side")) == (x, y, side):
                p.fin = {"x": None, "y": None, "side": None}
                changed = True
            if (p.fout["x"], p.fout["y"], p.fout.get("side")) == (x, y, side):
                p.fout = {"x": None, "y": None, "side": None}
                changed = True
        else:
            if p.numbers.pop((x, y), None) is not None:
                changed = True
            if p.cells[y][x] != "w":
                p.cells[y][x] = "w"
                changed = True
            if (p.fin["x"], p.fin["y"]) == (x, y):
                p.fin = {"x": None, "y": None, "side": None}
                changed = True
            if (p.fout["x"], p.fout["y"]) == (x, y):
                p.fout = {"x": None, "y": None, "side": None}
                changed = True
            if changed:
                p.renumber()
        if changed:
            self.clear_solution()
        return changed

    def _toggle_number(self, x, y, qmark=False):
        """数字 / "?格" 工具的核心操作(点击与测试共用)。

        数字工具放的是**数字选择器里的值**(而不是"接着最大编号 +1"): 选择器可以手动输入,
        也能用上下箭头选(上下箭头会跳过盘面上已有的数字); 放完一个数字后选择器自动跳到
        下一个"还没被占用"的数字, 于是连续点击就是 1,2,3… 而且不会手滑放重。
        "?格" 工具不受选择器影响, 只放/取消 n = -2。
        """
        p = self.puz
        self.push_undo()
        msg = None
        if qmark:
            if p.numbers.get((x, y)) == -2:
                del p.numbers[(x, y)]
            else:
                p.numbers[(x, y)] = -2
            msg = "已放置 \"?\" 格 (数字未知的编号格)"
        elif (x, y) in p.numbers:
            del p.numbers[(x, y)]           # 再点同一格 = 删除, 不动选择器
            msg = "已删除该格的数字"
        else:
            n = self.pick_number()
            p.numbers[(x, y)] = n
            nxt = p.next_free_number(n + 1)
            self._set_number_pick(nxt)      # 自动跳下一个可用数字
            msg = f"已放置 {n}; 数字选择器跳到 {nxt}"
        self.clear_solution()
        self._refresh_dup_numbers()
        self.redraw()
        self.set_status(msg + self._dup_status_suffix())

    # ---------- 数字选择器 (数字工具放哪个数) ----------
    def pick_number(self):
        """读取选择器当前的值(非法/空 → 1)。"""
        w = getattr(self, "num_pick", None)
        if w is None:
            return 1
        try:
            return max(1, int(str(w.get()).strip()))
        except (ValueError, AttributeError):
            return 1

    def _set_number_pick(self, n):
        self._num_pick_guard = True
        try:
            self.num_pick.set(str(int(n)))
        finally:
            self._num_pick_guard = False

    def _step_number_pick(self, delta):
        """上下箭头: 走到上/下一个**盘面上还没有的**数字; 走到 1 就停住。

        （"跳过已有数字"是有意为之: 连续点就是 1,2,3…, 不会手滑放重。若下方全被占满
        就停在 1 —— 想放重复的数字请直接手输。）
        """
        if self._num_pick_guard:
            return "break"
        used = {v for v in self.puz.numbers.values() if v > 0}
        n = self.pick_number()
        for _ in range(500):
            nxt = n + delta
            if nxt < 1:                      # 到端点就停, 不要落成 0 或负数
                break
            n = nxt
            if n not in used:
                break
        self._set_number_pick(n)
        return "break"                       # 自己处理, 不要 Spinbox 再走一遍

    def _on_number_pick_typed(self):
        """手动输入: 原样保留(允许故意输入重复数字), 只提示冲突。"""
        if self._num_pick_guard:
            return
        n = self.pick_number()
        self._set_number_pick(n)
        if n in {v for v in self.puz.numbers.values() if v > 0}:
            self.set_status(f"注意: 数字 {n} 盘面上已经有了 —— 再放一次会让题面无效")
        else:
            self.set_status(f"数字工具将放置 {n}; 点击格子放置, 放完自动跳到下一个可用数字")

    def on_number_step(self, event=None):
        """上下箭头事件(供 Spinbox 直接绑定, 也便于测试)。"""
        return self._step_number_pick(+1)

    def _refresh_dup_numbers(self):
        """重算"重复的已知数字"及其所在格（重绘时整格铺黄用）。"""
        self._dup_nums = self.puz.dup_numbers()
        self._dup_positions = {pos for ps in self._dup_nums.values() for pos in ps}
        return self._dup_nums

    def _sync_number_pick(self):
        """题面换了/被裁过之后: 重算重复数字, 并把选择器对齐到"第一个还没用的数字"。"""
        self._refresh_dup_numbers()
        used = {v for v in self.puz.numbers.values() if v > 0}
        cur = getattr(self, "num_pick", None)
        if cur is not None and self._num_pick_guard is False:
            if self.pick_number() in used:          # 选择器指着一个已占用的数字 → 让开
                self._set_number_pick(self.puz.next_free_number(1))

    def _dup_status_suffix(self):
        """重复数字的警告后缀(没有重复时返回空串)。"""
        dups = getattr(self, "_dup_nums", None)
        if not dups:
            return ""
        items = "、".join("%d(%s)" % (v, "/".join("(%d,%d)" % pos for pos in ps))
                        for v, ps in list(dups.items())[:4])
        return "  ⚠ 题目无效: 数字重复 %s" % items

    # ---------- 做题模式 (pzprjs 风格: 多段线段, 拖过=擦除, 拖回=回退) ----------
    def _inside(self, p):
        return 0 <= p[0] < self.puz.w and 0 <= p[1] < self.puz.h

    def _edges_ser(self):
        """线段集 → 可序列化列表 (撤销栈用)。"""
        return sorted(sorted([list(p) for p in e]) for e in self.play_edges)

    def on_clear_play(self):
        if not self.play_edges:
            return
        self.push_undo({"kind": "play", "edges": self._edges_ser()})
        self.play_edges = set()
        self._refresh_play_state()
        self.redraw()
        self.set_status("已清除线路")

    def _play_press(self, x, y):
        """按下: 仅为手势定位; 第一个跨越的已有线决定本手势是 加线 还是 擦除
        (与 puzz.link 一致)。可在任意格起笔另起新段。"""
        self._drag_hist = [(x, y)]
        self._drag_mode = None
        self._drag_trail = []
        self._drag_undo_pushed = False

    def _play_step(self, p, q):
        """手势中从格 p 迈到相邻格 q: 加线 / 擦除 / 拖回上一步回退。"""
        hist = self._drag_hist
        e = frozenset((p, q))
        if len(hist) >= 2 and q == hist[-2]:
            # 拖回上一步 → 撤销上一个操作
            op = self._drag_trail.pop() if self._drag_trail else None
            if op is not None:
                prev_e, added = op
                if added:
                    self.play_edges.discard(prev_e)
                else:
                    self.play_edges.add(prev_e)
                self._refresh_play_state()
                self.redraw()
            hist.pop()
            return
        if abs(p[0] - q[0]) + abs(p[1] - q[1]) != 1 or \
                not (self._inside(p) or self._inside(q)):
            return                          # 只允许 盘内↔出界一格 的相邻格
        if self._drag_mode is None:
            self._drag_mode = "del" if e in self.play_edges else "add"
        changed = False
        if self._drag_mode == "add" and e not in self.play_edges:
            if not self._drag_undo_pushed:   # 首次实际修改 → 压入手势前状态
                self.push_undo({"kind": "play", "edges": self._edges_ser()})
                self._drag_undo_pushed = True
            self.play_edges.add(e)
            self._drag_trail.append((e, True))
            changed = True
        elif self._drag_mode == "del" and e in self.play_edges:
            if not self._drag_undo_pushed:
                self.push_undo({"kind": "play", "edges": self._edges_ser()})
                self._drag_undo_pushed = True
            self.play_edges.discard(e)
            self._drag_trail.append((e, False))
            changed = True
        else:
            self._drag_trail.append(None)    # 状态已符合模式 → 无操作 (记录占位)
        hist.append(q)
        if changed:
            self._refresh_play_state()
            self.redraw()

    def _play_motion(self, x, y):
        if self._drag_hist is None:
            return
        t = (x, y)
        for _ in range(64):                 # 快速甩鼠标时逐格补齐中间步
            p = self._drag_hist[-1]
            if t == p:
                return
            before = tuple(self._drag_hist)
            dx, dy = t[0] - p[0], t[1] - p[1]
            if abs(dx) + abs(dy) == 1:
                self._play_step(p, t)
            else:
                sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
                nxt = (p[0] + sx, p[1]) if abs(dx) >= abs(dy) else (p[0], p[1] + sy)
                self._play_step(p, nxt)
            if tuple(self._drag_hist) == before:
                return                      # 该步无效 (出界/原地) → 停止推进

    def _refresh_play_state(self):
        errs, inc, complete, route, redges = check_play_rules(
            self.puz, self.play_edges, cover_all=bool(self.cover_all.get()))
        self._play_errors = errs
        self._play_incomplete = inc
        self._play_complete = complete
        self._play_route = route
        self._play_route_edges = redges
        if self._manual_active():
            # 手动绘制核验解: 只报"画了多少", **不做规则判定**(那条线不必是合法解)
            n = len(self._path_from_play_edges())
            self.set_status("手动绘制答案: 已画 %d 格 —— 画完点「完成手动绘制」（不做规则检查）" % n)
        elif errs:
            extra = f" (共 {len(errs)} 处违规)" if len(errs) > 1 else ""
            self.set_status(f"✗ {errs[0]}{extra}", "err")
        elif complete:
            self.set_status("🎉 完成! 线路满足全部要求, 恭喜通关!", "ok")
        elif inc:
            self.set_status(f"做题中: 还差 {len(inc)} 项 — {inc[0]}")

    def on_check_rules(self):
        """检查解: 用规则引擎判定当前线路是否已构成满足题面要求的解 (不依赖求解器)。"""
        if not self.play_edges:
            self.set_status("检查解: 尚未画线 — 按住拖动开始画线", "err")
            return
        self._refresh_play_state()
        errs, inc, complete = self._play_errors, self._play_incomplete, self._play_complete
        if errs:
            extra = f" (共 {len(errs)} 处)" if len(errs) > 1 else ""
            self.set_status(f"检查解: 不是解 ✗ {errs[0]}{extra}", "err")
        elif complete:
            self.set_status("检查解: 正确 ✓ 这就是满足要求的解, 恭喜通关!", "ok")
        else:
            self.set_status(f"检查解: 线路还没有完成 ({len(inc)} 项) — {inc[0]}")

    # ---------- 文件 ----------
    def _install_puzzle(self, p, file_path=None, reset_number_pick=False):
        self.puz = p
        self.file_path = file_path
        self._puz_key = None                # 换了题面 → 内容指纹缓存作废(见 _cur_key)
        if getattr(self, "_manual_answer", None) is not None:
            self._manual_answer = None      # 换题面 = 退出手动绘制模式(半截的线也丢掉)
            self._sync_manual_ui(False)
        self._archive_note = None           # 本次载入是否附带"存档解已载入"的提示(调用方拼进状态栏)
        self.play_edges = set()
        self._play_route = []
        self._play_route_edges = set()
        self._sync_size_spin()
        if reset_number_pick:
            self._set_number_pick(1)        # 新建的空白盘面 → 数字选择器回到 1
        self._sync_number_pick()            # 载入的题面可能带重复数字, 选择器也要重新对齐
        self.clear_solution()
        self._load_archived_solution()      # 存过解的题打开即可「显示解」, 不必再求一遍
        self._on_configure()

    def _load_archived_solution(self):
        """存档里有这道题的解 → 直接当作当前解载入 (键=内容指纹, 与文件路径无关)。"""
        self._sol_from_archive = False
        try:
            rec = archive_lookup(self.puz.to_json())
        except Exception:
            rec = None
        if not rec:
            return
        try:
            path = [(int(x), int(y)) for x, y in rec["path"]]
        except Exception:
            return
        if not path:
            return
        self.solutions = [path]
        self.sol_idx = 0
        self._sol_from_archive = True
        self._archive_note = "已从存档载入上次保存的解 (可点「显示解」; 再求解会先询问)"
        self.sol_label.config(text="解: 1/1 (存档)")
        self.show_sol.set(not self.play_edges)
        self._update_show_sol_btn()
        self.set_status(self._archive_note)

    def _status_with_archive_note(self, text):
        """调用方安装完题面要写自己的状态栏 → 把存档提示接在后面, 不让它被盖掉。"""
        note = getattr(self, "_archive_note", None)
        self.set_status(f"{text}；{note}" if note else text)

    def on_resize(self):
        try:
            h = int(self.sp_h.get())
            w = int(self.sp_w.get())
        except ValueError:
            return
        if not (1 <= w <= 30 and 1 <= h <= 30):
            messagebox.showwarning(APP_TITLE, "尺寸需在 1..30")
            return
        self.push_undo()
        self.puz.resize(w, h)
        self._puz_key = None                # 盘面变了 → 指纹必然变, 缓存作废
        self._manual_answer = None          # 换盘面 = 退出手动绘制模式
        self._sync_manual_ui(False)
        self.play_edges = set()             # 盘面尺寸变化后旧线段可能指向界外, 一并清除
        self._play_route = []
        self._play_route_edges = set()
        self._set_number_pick(1)            # 换尺寸 = 重新出题, 数字选择器同样从 1 起
        self._sync_number_pick()
        self.clear_solution()
        self._on_configure()

    def on_new(self):
        if not messagebox.askyesno(APP_TITLE, "新建空白谜题?"):
            return
        self.push_undo()
        self._install_puzzle(Puzzle(self.puz.w, self.puz.h), reset_number_pick=True)
        self.set_status("已新建空白谜题 (数字选择器已重置为 1)")

    def on_open(self):
        fn = filedialog.askopenfilename(filetypes=[("Icelom 谜题", "*.json"), ("所有文件", "*.*")])
        if not fn:
            return
        try:
            obj = json.load(open(fn, encoding="utf-8"))
            p = Puzzle.from_json(obj)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"打开失败: {e}")
            return
        self.push_undo()
        self._install_puzzle(p, file_path=fn)
        self._status_with_archive_note(f"已打开 {os.path.basename(fn)}")

    def on_save(self):
        """保存: 已经有文件名(打开/另存为过)就直接写回那份文件, 否则先问路径。"""
        if self.file_path:
            self._save_to(self.file_path)
            return
        self.on_save_as()

    def on_save_as(self):
        """另存为: 每次都问路径, 之后「保存」就写这份新文件(与"打开的文件"解绑)。"""
        initial = os.path.splitext(os.path.basename(self.file_path or ""))[0] or "puzzle"
        fn = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Icelom 谜题", "*.json")],
            initialdir=os.path.dirname(self.file_path) if self.file_path else HERE,
            initialfile=initial + ".json")
        if not fn:
            return
        self._save_to(fn)

    def _save_to(self, fn):
        """把当前题面写到 `fn`(保存与另存为共用)。

        写入前先清掉自己那一段"存档解已载入"的提示: 题面已经落盘, 状态栏该说保存的事,
        不该还挂着上一条载入消息的尾巴。
        """
        try:
            obj = self.puz.to_json()
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=1)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"保存失败: {e}")
            return
        self.file_path = fn
        self._archive_note = None
        self.set_status(f"已保存 {os.path.basename(fn)}", "ok")

    # ---------- puzz.link URL 导入 ----------
    def on_import_url(self):
        url = simpledialog.askstring(
            "导入 puzz.link URL",
            "粘贴 puzz.link / pzv.jp 的 icelom 谜题 URL:\n"
            "(例如 https://puzz.link/p?icelom/a/8/8/.../0/15)\n"
            "(需要安装 Node.js 才能解码)", parent=self.root)
        if not url:
            return
        url = url.strip()
        if not os.path.exists(URL_TOOL):
            messagebox.showerror(APP_TITLE, "未找到 URL 解码器 tools/pzprurl2json.js\n(需要 Node.js)")
            return
        try:
            r = subprocess.run(["node", URL_TOOL, url], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=60, **_no_console())
            out = r.stdout.decode("utf-8", "replace").strip()
            if not out:
                raise RuntimeError(r.stderr.decode("utf-8", "replace")[:400] or "无输出")
            obj = json.loads(out.splitlines()[-1])
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"导入失败: {e}\n(URL 解码需要 Node.js)")
            return
        if obj.get("type") == "error":
            messagebox.showerror(APP_TITLE, f"导入失败: {obj.get('message')}")
            return
        try:
            p = Puzzle.from_json(obj)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"解析结果异常: {e}")
            return
        if p.fin["x"] is None or p.fout["x"] is None:
            messagebox.showerror(APP_TITLE, "该 URL 中没有 IN/OUT")
            return
        # 题面数字保持原样: 数字可以跳号, "?" 格(n=-2)表示"数字未知的编号格",
        # 求解器按"位次"规则判定, 不再按排位重编号。
        self.push_undo()
        self._install_puzzle(p, file_path=None)
        extra = f", 其中 {p.qmark_count()} 个 ? 格" if p.qmark_count() else ""
        self._status_with_archive_note(
            f"已导入 puzz.link URL ({p.w}×{p.h}, {p.known_count()} 个数字{extra})")

    # ---------- 导出图片 ----------
    def on_export_image(self):
        """高保真导出: 用 icelom_render 按纸面风格重绘(优先当前解, 其次做题线路)。"""
        try:
            import icelom_render
        except Exception:
            messagebox.showerror(APP_TITLE, "需要 Pillow 库 (pip install pillow)")
            return
        fn = filedialog.asksaveasfilename(defaultextension=".png",
                                          filetypes=[("PNG 图片", "*.png")])
        if not fn:
            return
        path = None
        if self.show_sol.get() and 0 <= self.sol_idx < len(self.solutions):
            path = [list(pt) for pt in self.solutions[self.sol_idx]]
        elif self._play_route:
            path = [list(pt) for pt in self._play_route]
        try:
            img = icelom_render.render_puzzle(self.puz.to_json(), path=path,
                                              cell=64, scale=4)
            img.save(fn)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"导出失败: {e}")
            return
        self.set_status(f"已导出图片 {os.path.basename(fn)} ({img.width}×{img.height})", "ok")

    # ---------- 导出 Penpa+ 链接 ----------
    def _cur_answer(self):
        """当前显示的那份解(没有就返回 None)。"""
        if 0 <= self.sol_idx < len(self.solutions):
            return [(int(x), int(y)) for x, y in self.solutions[self.sol_idx]]
        return None

    def _archived_answer(self):
        """存档里本题的解(打开本题时自动载入的那份); 没存过 → None。"""
        return archive_path(archive_lookup(self.puz.to_json()))

    def _cur_key(self):
        """当前题面的内容指纹(算一次记一次, 存档读写都靠它)。"""
        if self._puz_key is None:
            self._puz_key = puzzle_key(self.puz.to_json())
        return self._puz_key

    def _prefer_answer_key(self):
        """默认用哪种答案: 本题当前的解 > 本题的存档解 > 不带答案。

        （"手动绘制"不给默认: 它要切到画线模式, 得显式选。）
        """
        if self._cur_answer():
            return "cur"
        if self._archived_answer():
            return "arch"
        return "none"

    def on_export_penpa(self):
        """菜单/工具条入口: 先弹配置窗(要不要对照答案 / 答案从哪来), 再导出链接。"""
        if self.puz.fin["x"] is None or self.puz.fout["x"] is None:
            messagebox.showwarning(APP_TITLE, "请先放置 IN 和 OUT —— Penpa+ 链接要把入/出口画在框外")
            return
        opt = self._penpa_options_dialog()
        if opt is None:
            return
        if opt.get("key") == "manual":
            # 配置窗已经自己关了: 切到画线模式, 画完点「完成」再出链接
            self._start_manual_answer()
            return
        self._penpa_export_dialog(opt)

    # ---------- 手动绘制核验解 (自己画一条线当 Penpa+ 的对照答案) ----------
    def _manual_active(self):
        return getattr(self, "_manual_answer", None) is not None

    def _start_manual_answer(self):
        """切到"手动画答案"模式: 盘面回到空题面, 自己画一条线, 画完点「完成」。

        画出来的线**原样**当 Penpa+ 的对照答案(不验证、不要求是解), 于是"我认为答案是
        这样, 拿它去核验"这件事可以在页面上做。进入时先清掉当前显示的解与既有线路
        —— 起点就是一张空题面; 点「取消」原样还原(解、线路都还在)。
        """
        if self._manual_active():
            return
        self.push_undo({"kind": "solve"})       # 撤回顾问: 万一忘了取消, Ctrl+Z 能还原解显示
        self._manual_answer = {}
        self._clear_play_edges(silent=True)     # 空题面: 清掉解显示与既有线路
        self._sync_manual_ui(True)
        self.set_status("手动绘制答案: 在盘面上画出要核验的线路（可自由画线，不必是合法解），"
                        "画完点「完成手动绘制」")

    def _cancel_manual_answer(self):
        """取消手动绘制: 丢弃这次画的线, 回到原来的显示。"""
        if not self._manual_active():
            return
        self._manual_answer = None
        self._clear_play_edges(silent=True)
        self._sync_manual_ui(False)
        self.set_status("已取消手动绘制")

    def _finish_manual_answer(self):
        """完成: 把画好的线当对照答案, 出 Penpa+ 链接。"""
        if not self._manual_active():
            return
        opt = self._manual_answer
        path = self._path_from_play_edges()
        if not path:
            messagebox.showwarning(APP_TITLE, "还没有画线 —— 在盘面上画出要核验的线路再点「完成」")
            return
        self._manual_answer = None
        self._sync_manual_ui(False)
        self.set_status("已用手动绘制的线路当对照答案 (%d 格)" % len(path))
        self._penpa_export_dialog({"key": "manual", "path": path})

    def _clear_play_edges(self, silent=False):
        """清掉做题线路 + 解显示(手动绘制/取消时用); `silent` = 只清不写状态栏。"""
        self.play_edges = set()
        self._play_route = []
        self._play_route_edges = set()
        self._play_errors = []
        self._play_incomplete = []
        self._play_complete = False
        self.clear_solution()
        if not silent:
            self.set_status("已清除线路")

    def _path_from_play_edges(self):
        """画好的线段集合 → 逐格序列(给 Penpa+ 当答案)。

        线段本身不带顺序, 所以每段自己排成一条链(从哪端起都行), 再把各段首尾接起来
        —— penpa 的答案只比"有哪些相邻格对", 顺序与分段都无所谓, 这样拼就够了。
        出界的端点(在 IN/OUT 处画出框外那一步)丢掉: 链接自己会补进出框那两段。

        走法要**不回退、不重复用边**: 只按"上一条边"防回退是不够的 —— 一个格子挂 3 条边
        (交叉/分叉)时会拐回走过的那条, 于是原地绕圈(历史上这里死过一次循环)。
        """
        edges = set()
        for a, b in self.play_edges:
            if self._inside(a) and self._inside(b):
                edges.add(frozenset((a, b)))
        path = []
        while edges:
            # 起步: 取"排序后最小"的那条边的小端点(哪端起笔都行, 结果只影响顺序)
            a, b = sorted(min(edges, key=lambda e: sorted(e)))
            cur, prev, seg = a, None, [a]
            while True:                          # 顺着没走过的边一路走下去
                nxt = None
                for e in sorted(edges, key=lambda e: sorted(e)):
                    if cur not in e:
                        continue
                    x, y = sorted(e)
                    other = y if x == cur else x
                    if prev is not None and other == prev:
                        continue                 # 不走回头路(那条边已经用掉了)
                    nxt = other
                    break
                if nxt is None:
                    break
                edges.discard(frozenset((cur, nxt)))
                seg.append(nxt)
                prev, cur = cur, nxt
            path.extend(seg)
        return path

    def _sync_manual_ui(self, on):
        """手动绘制模式下把界面切成"只有画线相关的东西能用"。"""
        if on:
            self.bar_manual.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 2),
                                 before=self.canvas)
        else:
            self.bar_manual.pack_forget()
        for w, state in ((self.btn_solve, tk.DISABLED if on else tk.NORMAL),
                         (self.btn_clear_play, tk.NORMAL if on else tk.DISABLED),
                         (self.btn_export_penpa, tk.DISABLED if on else tk.NORMAL),
                         (self.btn_export_image, tk.DISABLED if on else tk.NORMAL),
                         (self.btn_open_deduce, tk.DISABLED if on else tk.NORMAL)):
            w.config(state=state)
        if on and self.mode.get() != "play":
            self.mode.set("play")
            self._on_mode_change()
        self.redraw()

    def _penpa_options_dialog(self):
        """Penpa+ 导出的配置窗 → {"key"}（选"手动绘制"时调用方接手切模式）；取消返回 None。

        两件事在这里定: ① 要不要**对照答案**(链接里带 `a` 参数, 页面画完点 Check 自动判定);
        ② 答案从哪来 —— 本题当前的解 / 本题存档解 / **自己手动画一条线** / 不带答案。
        选"手动绘制"时本窗口直接关掉(调用方接手切到画线模式)。
        """
        cur = self._cur_answer()
        arch = self._archived_answer()

        win = tk.Toplevel(self.root)
        win.title("导出 Penpa+ 链接")
        win.transient(self.root)
        win.resizable(False, False)
        body = ttk.Frame(win)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="答案（链接里带 `a` 参数时，页面画完点 Check 会对照答案自动判定）：",
                  font=UI_FONT).grid(row=0, column=0, sticky="w", pady=(0, 4))
        var_key = tk.StringVar(value=self._prefer_answer_key())
        ttk.Radiobutton(body, text="用本题当前的解（%s）" % ("%d 格" % len(cur) if cur else "还没有解"),
                        value="cur", variable=var_key,
                        state=(tk.NORMAL if cur else tk.DISABLED)).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(body, text="用本题的存档解（%s）" % ("%d 格" % len(arch) if arch else "存档里没有"),
                        value="arch", variable=var_key,
                        state=(tk.NORMAL if arch else tk.DISABLED)).grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(body, text="手动绘制核验解（回到空题面，自己画一条线，画完点「完成」）",
                        value="manual", variable=var_key).grid(row=3, column=0, sticky="w",
                                                              pady=(2, 0))
        ttk.Radiobutton(body, text="不带答案（只导出题面）", value="none", variable=var_key).grid(
            row=4, column=0, sticky="w", pady=(2, 0))

        ttk.Separator(body, orient=tk.HORIZONTAL).grid(row=5, column=0, sticky="ew", pady=6)
        ttk.Label(body, text="带答案的链接打开后页头显示 “Solver Mode (Answer Checking Enabled)”，"
                            "在页面上用 %d 号笔（那排颜色的第 6 个，淡蓝）把线画完，"
                            "点 Check 就会判定。" % penpa_module().ANSWER_STYLE,
                  foreground="#555555", wraplength=470, justify="left").grid(
            row=6, column=0, sticky="w")
        ttk.Label(body, text="手动绘制时画什么、画成什么样都行 —— 那条线原样当对照答案，不做验证。",
                  foreground="#555555", wraplength=470, justify="left").grid(
            row=7, column=0, sticky="w", pady=(6, 0))

        bar = ttk.Frame(win)
        bar.pack(fill=tk.X, padx=10, pady=(0, 8))
        result = {}

        def _ok(key=None):
            k = key or var_key.get()
            result["key"] = k
            win.destroy()

        ttk.Button(bar, text="取消", command=win.destroy).pack(side=tk.RIGHT)
        btn_ok = ttk.Button(bar, text="确定", command=_ok)
        btn_ok.pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(bar, text="不带答案并导出", command=lambda: _ok("none")).pack(side=tk.LEFT)
        win.bind("<Return>", lambda e: _ok())
        win.bind("<Escape>", lambda e: win.destroy())
        btn_ok.focus_set()
        _center_on_parent(win, self.root)
        win.grab_set()
        self.root.wait_window(win)
        return result or None

    def _penpa_link(self, key=None, path=None):
        """造一条 Penpa+ 链接(本模块里唯一真正做导出这件事的地方; 不弹任何窗口)。

        `key`: "puzzle" 只要题面 / "cur" 本题当前的解 / "arch" 本题存档解 /
        "manual" 用传进来的 `path`(手动绘制的核验解) / "none" 不要答案;
        省略 = `_prefer_answer_key()`。
        会带答案时顺手把链接存进存档(下次导出同一种就直接用)。
        题面不合格 → ValueError(json2penpa 的说明原样带出), 由调用方显示。
        """
        if self.puz.fin["x"] is None or self.puz.fout["x"] is None:
            raise ValueError("题面还没有 IN/OUT —— Penpa+ 链接要把入/出口画在框外")
        if key is None:
            key = self._prefer_answer_key()
        given_path = path
        puzzle = self.puz.to_json()          # 题面永远是**当前**这道题
        if key == "cur":
            path = self._cur_answer() if path is None else path
            if not path:
                raise ValueError("当前没有解 —— 先「求解」或切到有解的显示, 或改用存档解")
        elif key == "arch":
            path = self._archived_answer() if path is None else path
            if not path:
                raise ValueError("存档里没有本题的解 —— 先求出唯一解自动入档, 或改用本题当前的解")
        elif key == "manual":
            path = [(int(x), int(y)) for x, y in (path or [])]
            if not path:
                raise ValueError("手动绘制的答案是空的 —— 先在盘面上画一条线")
        elif key in ("puzzle", "none"):
            path = None
        else:
            raise ValueError("不认识的答案来源: %r（只认 puzzle/cur/arch/manual/none）" % (key,))
        url = penpa_link(puzzle, path)
        # 只有"这道题自己的解"才写回存档: 手动绘制那种是**一次性的核验草稿**, 不存在存档里
        # (否则下次导出会把随手画的线当成这道题的解); 显式传 path 的调用方同理。
        if path is not None and given_path is None and key in ("cur", "arch"):
            err = archive_save_solution(puzzle, path, source="icelom_gui",
                                        file_path=self.file_path)
            if err:
                self.set_status(f"链接已生成, 但写入存档失败: {err}", "err")
        return url

    def _penpa_export_dialog(self, opt):
        """把造好的链接给出来: 复制 / 存成 .txt / 用浏览器打开（打开即已复制到剪贴板）。"""
        try:
            url = self._penpa_link(key=opt.get("key", "none"), path=opt.get("path"))
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"导出 Penpa+ 链接失败: {e}")
            return
        src = {"puzzle": "不带答案（只导出题面）", "none": "不带答案（只导出题面）",
               "cur": "答案 = 本题当前的解", "arch": "答案 = 本题的存档解",
               "manual": "答案 = 手动绘制的核验解"}.get(opt.get("key"), "")
        win = tk.Toplevel(self.root)
        win.title("Penpa+ 链接")
        win.geometry("760x300")
        win.transient(self.root)
        ttk.Label(win, text=f"{src}；链接长度 {len(url)} 字符。"
                            "页面画完点 Check 即可自动判定。",
                  foreground="#555555").pack(anchor="w", padx=8, pady=(6, 0))
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        txt = tk.Text(frame, wrap=tk.CHAR, height=6, font=MONO_FONT)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=txt.yview)
        txt.config(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.insert("1.0", url)
        txt.focus_set()
        bar = ttk.Frame(win)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))

        def _copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.set_status("Penpa+ 链接已复制到剪贴板", "ok")

        def _save():
            fn = filedialog.asksaveasfilename(defaultextension=".txt",
                                              filetypes=[("文本文件", "*.txt")],
                                              initialfile="penpa_link.txt")
            if not fn:
                return
            try:
                with open(fn, "w", encoding="utf-8", newline="\n") as f:
                    f.write(url + "\n")
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"写入失败: {e}")
                return
            self.set_status(f"Penpa+ 链接已写入 {os.path.basename(fn)}", "ok")

        def _open():
            import webbrowser
            webbrowser.open(url)

        ttk.Button(bar, text="关闭", command=win.destroy).pack(side=tk.RIGHT)
        ttk.Button(bar, text="在浏览器打开", command=_open).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(bar, text="存为文件…", command=_save).pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Button(bar, text="复制链接", command=_copy).pack(side=tk.LEFT)
        _copy()                       # 打开就给一份在剪贴板里, 最常见的就是粘到浏览器
        win.bind("<Escape>", lambda e: win.destroy())
        _center_on_parent(win, self.root)
        win.grab_set()
        self.root.wait_window(win)

    # ---------- 求解 ----------
    def _time_budget_s(self):
        """读「推理预算(秒)」输入框: 非整数/越界都收敛回合法值并写回输入框。"""
        raw = str(self.sp_time.get()).strip()
        try:
            n = int(raw)
        except ValueError:
            n = DEFAULT_TIME_LIMIT_S
        n = min(max(n, 1), 86400)
        if str(n) != raw:
            self.sp_time.set(str(n))
        return n

    def build_solver_input(self):
        obj = self.puz.to_json()
        obj["options"]["cover_all_whites"] = bool(self.cover_all.get())
        # symmetry_retry: 旧引擎的"换逆向扫描序再试"开关, **当前求解器已不解析它**
        # (现在是单颗搜索树 + 单一固定顺序, 见 docs/算法说明.md §3.12)。
        # 这里仍然照发, 只为兼容旧求解器二进制。
        obj["options"]["symmetry_retry"] = True
        limits = {"mode": self.solve_mode.get(),
                  "time_limit_ms": self._time_budget_s() * 1000}
        if self.solve_mode.get() == "all":
            limits["max_solutions"] = int(self.max_sols.get() or 20)
        obj["limits"] = limits
        return obj

    def on_solve(self):
        if self.solving:
            return
        if self._manual_active():
            self.set_status("正在手动绘制核验解 —— 先点「完成手动绘制」或「取消」，再求解", "err")
            return
        if not os.path.exists(SOLVER):
            messagebox.showerror(APP_TITLE, "未找到 icelom_solver.exe\n请先用 g++ 编译 (见 README.md)")
            return
        p = self.puz
        if p.fin["x"] is None or p.fout["x"] is None:
            messagebox.showwarning(APP_TITLE, "请先放置 IN 和 OUT")
            return
        # 存档里已有这道题的解(打开时自动载入的那份) → 先问一句, 避免白白重解
        if self._sol_from_archive and self.solutions and archive_lookup(p.to_json()):
            if not messagebox.askyesno(
                    APP_TITLE,
                    "存档中已保存本题的解（打开时已自动载入, 可点「显示解」查看）。\n要重新求解吗?"):
                self.set_status("已保留存档解, 未重新求解")
                return
        budget = self._time_budget_s()
        _cfg_set("time_limit_s", budget)    # 记住这次的预算, 下次启动沿用
        self.push_undo({"kind": "solve"})     # 撤回栈记录「求解」: 撤回时打断求解
        self.clear_solution()
        self.solutions = []
        self._sol_from_archive = False
        data = json.dumps(self.build_solver_input(), ensure_ascii=False).encode("utf-8")
        try:
            self.proc = subprocess.Popen([SOLVER], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         **_no_console())
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"启动求解器失败: {e}")
            return
        self.solving = True
        self._stopped = False
        self._solver_diag = ""        # stderr 诊断文本(不属于协议, 见 docs/求解器协议.md §1)
        self._reader_done = False
        self._flush_wait = 0
        self._finished = False
        while True:                   # 丢弃上一次求解残留的消息(如未排空的 stderr)
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.btn_solve.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        mode_name = dict(self.SOLVE_MODES)[self.solve_mode.get()]
        self.set_status(f"求解中[{mode_name}, 预算{budget}秒]...", "solving")
        threading.Thread(target=self._feed_stdin, args=(self.proc, data), daemon=True).start()
        threading.Thread(target=self._read_stdout, args=(self.proc,), daemon=True).start()
        self.root.after(60, self._poll)

    @staticmethod
    def _feed_stdin(proc, data):
        try:
            proc.stdin.write(data)
            proc.stdin.close()
        except Exception:
            pass

    def _read_stdout(self, proc):
        try:
            for line in proc.stdout:
                line = line.decode("utf-8", "replace").strip()
                if line:
                    self.q.put(line)
            err = proc.stderr.read().decode("utf-8", "replace")
            if err.strip():
                self.q.put(json.dumps({"type": "stderr", "text": err}))
        except Exception:
            pass
        finally:
            # 让 _poll 知道 stderr 已经排空: 判"求解器意外退出"时要等这一步,
            # 否则可能在诊断文本入队之前就下结论(拿不到 stderr)。
            self._reader_done = True

    def _poll(self):
        if not self.solving and self.q.empty():
            return                     # 没有求解在跑也没有待处理消息: 结束轮询链
        try:
            while True:
                line = self.q.get_nowait()
                obj = json.loads(line)
                t = obj.get("type")
                if t == "solution":
                    self.solutions.append([tuple(pt) for pt in obj["path"]])
                    if self.sol_idx == -1:
                        self.sol_idx = 0
                    self.sol_label.config(text=f"解: {self.sol_idx+1}/{len(self.solutions)}")
                    self.set_status(f"求解中... 已找到 {len(self.solutions)} 个解", "solving")
                elif t == "done":
                    self._on_solver_done(obj)
                    self._finished = True
                elif t == "error":
                    messagebox.showerror(APP_TITLE, f"求解器错误: {obj.get('message')}")
                    self.set_status("求解失败", "err")
                    self._finished = True
                elif t == "stderr":
                    # 求解器的 stderr 是**诊断信息, 不属于协议**(docs/求解器协议.md §1):
                    # 正常"无解"时会打印 `[unsat-diag]` 现场盘面, ICELOM_DUMP=1 等调试开关
                    # 也都走 stderr。所以这里**只收集、绝不弹模态错误框**
                    # (旧行为: 每次搜到无解都在界面上刷一大片 ASCII 盘面、把界面卡住),
                    # 文本留给「查看 → 求解器诊断」按需阅读。
                    self._solver_diag += obj.get("text") or ""
        except queue.Empty:
            pass
        # `_finished` 必须**粘住**(不能只当本次调用的局部变量): `done` 是 stdout 的最后一行,
        # 读取线程随后才排空 stderr (见 _read_stdout), 所以常常要跨两次轮询才收尾。
        # 若用局部变量, 收尾那次会看不到"已经拿到 done", 把成功的求解误报成"求解器意外退出"。
        if self._finished and not self._reader_done and self._flush_wait < 250:
            self._flush_wait += 1
            self.root.after(20, self._poll)
            return
        if not self._finished and self.solving and self.proc is not None:
            # 一个 done/error 记录都没收到, 而进程已经退出且 stderr 也排空了 → 真出事了
            if self.proc.poll() is not None and self.q.empty() and self._reader_done:
                rc = self.proc.returncode
                if self._stopped:
                    self.set_status("已停止", "err")
                elif rc:
                    # 真正的异常: 非零退出码(崩溃/被系统杀掉) —— 只有这种才值得弹错误框
                    tail = self._solver_diag.strip()[-800:]
                    messagebox.showerror(
                        APP_TITLE,
                        f"求解器异常退出 (退出码 {rc})" + (f"\n\n{tail}" if tail else ""))
                    self.set_status("求解器异常退出", "err")
                else:
                    self.set_status("求解器意外退出", "err")
                self._finished = True
        if self._finished and self.solving:
            self.solving = False
            self.btn_solve.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            if self.solutions:
                self.sol_idx = 0
                self.sol_label.config(text=f"解: 1/{len(self.solutions)}")
            # 做题中不直接显示解, 交给「显示解」按钮
            self.show_sol.set(not self.play_edges)
            self._update_show_sol_btn()
            self._update_diag_menu()
            self.redraw()
            if self._check_after_solve:
                self._do_check_compare()   # 对照解: 求解完成即比对并报告对/错
        elif self._finished:
            pass                           # 已定稿(求解可能已被再次启动), 不再重复处理
        else:
            self.root.after(60, self._poll)

    def _on_solver_done(self, obj):
        mode = self.solve_mode.get()
        count = obj.get("count", 0)
        extra = f"，原因: {obj['reason']}" if obj.get("reason") else ""
        tail = "【已达上限或超时中止】" if obj.get("aborted") else ""
        saved_note = ""
        # 唯一性已证(mode=unique/all 且 count==1 且未中途截断) → 解自动入档:
        # "只求解"模式无法证明唯一, 不入档(存的必须是可以直接当答案用的解)。
        if (count == 1 and not obj.get("aborted") and mode in ("unique", "all")
                and self.solutions):
            err = archive_save_solution(self.puz.to_json(), self.solutions[0],
                                        source="icelom_gui", file_path=self.file_path)
            saved_note = "，唯一解已存入存档" if err is None else f"，存档写入失败: {err}"
        if mode == "first":
            msg = (f"已求得一个解 ({obj['nodes']} 节点, {obj['ms']}ms)" if count else
                   f"无解{extra} {tail}")
        elif mode == "unique":
            if count == 1:
                msg = f"解是唯一的 ✓ ({obj['nodes']} 节点, {obj['ms']}ms)"
            elif count >= 2 and obj.get("aborted") and len(self.solutions) < 2:
                # 求解器约定: 截断时**保守虚报 count=2**(icelom_solver.cpp:1187) ——
                # 不是真的找到了第 2 个解。如实说"没证完", 别断言不唯一吓人。
                msg = (f"推理预算内未能证完穷尽, 保守按不唯一处理 (已找到 {len(self.solutions)} 个解, "
                       f"{obj['nodes']} 节点, {obj['ms']}ms; 调大「推理预算」可给出确定结论)")
            elif count >= 2:
                msg = f"解不唯一: 至少 {count} 个解 (已列出 {len(self.solutions)} 个)"
            else:
                msg = f"无解{extra} {tail}"
        else:
            msg = f"完成: 共 {count} 个解, {obj['nodes']} 节点, {obj['ms']}ms{extra} {tail}"
        self.set_status((msg + saved_note).strip(), "ok" if (mode != "unique" or count == 1) else
                        ("solving" if count else "err"))

    def _kill_solver(self):
        self._stopped = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.solving = False
        self.btn_solve.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def on_stop(self):
        self._kill_solver()
        self.set_status("已停止", "err")

    def nav(self, d):
        if not self.solutions:
            return
        if not self.show_sol.get():
            self.show_sol.set(True)
            self._update_show_sol_btn()
        self.sol_idx = (self.sol_idx + d) % len(self.solutions)
        self.sol_label.config(text=f"解: {self.sol_idx+1}/{len(self.solutions)}")
        self.redraw()

    def clear_solution(self):
        self.solutions = []
        self.sol_idx = -1
        self.show_sol.set(False)
        self.sol_label.config(text="解: -/-")
        self._update_show_sol_btn()

    def on_toggle_show_sol(self):
        if not self.solutions:
            return
        self.show_sol.set(not self.show_sol.get())
        self._update_show_sol_btn()
        self.redraw()
        if self.show_sol.get():
            self.set_status("已显示解 (做题线路已暂时隐藏); 点击「隐藏解」回到"
                            + ("做题界面" if self.play_edges else "题面"))
        else:
            self.set_status("已隐藏解, 回到" + ("做题界面" if self.play_edges else "题面"))

    def on_check_solution(self):
        """对照解: 把当前做题线路与求解器的答案比对, 只报告对/错, 不提示具体位置。"""
        if self.solving:
            return
        if not self.play_edges:
            self.set_status("对照解: 请先在做题模式画出线路", "err")
            return
        if not self.solutions:
            # 还没有答案: 静默求解一次, 完成后自动比对
            self._check_after_solve = True
            self.on_solve()
            return
        self._do_check_compare()

    def _do_check_compare(self):
        self._check_after_solve = False
        if not self.solutions:
            self.set_status("对照解: 本题无解, 无从对照", "err")
            return
        # 验证语义: 当前线路是解的"一部分"(没有画出错误连接) 即为正确 ——
        # 不比较方向与起终点; IN/OUT 处的出界短边是线路自动具有的, 不参与比对。
        drawn = {e for e in self.play_edges if all(self._inside(p) for p in e)}
        if not drawn:
            self.set_status("对照解: 请先在做题模式画出线路", "err")
            return

        def sol_edges(sol):
            return {frozenset((tuple(a), tuple(b))) for a, b in zip(sol, sol[1:])}

        hit = any(drawn <= sol_edges(sol) for sol in self.solutions)
        if hit:
            self.set_status("对照解: 正确 ✓ 当前线路是解的一部分 (无错误连接)", "ok")
        else:
            self.set_status("对照解: 错误 ✗ 存在与答案冲突的连接", "err")

    def _update_show_sol_btn(self):
        if not self.solutions:
            self.btn_show_sol.configure(text="显示解", state=tk.DISABLED)
        else:
            self.btn_show_sol.configure(
                text=("隐藏解" if self.show_sol.get() else "显示解"), state=tk.NORMAL)

    # ---------- 绘制 ----------
    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        p = self.puz
        cs = self.cs
        cw = max(cv.winfo_width(), 10)
        ch = max(cv.winfo_height(), 10)
        cv.configure(scrollregion=(0, 0, cw, ch))

        def ox(v):
            return self.offx + v

        def oy(v):
            return self.offy + v

        # 数字重复的格: **整格铺黄**警告(题面无效); 画在最底层, 冰格蓝底/网格线都盖在它上面
        dup_pos = getattr(self, "_dup_positions", None) or set()
        for (dx_, dy_) in dup_pos:
            cv.create_rectangle(ox(dx_ * cs), oy(dy_ * cs),
                                ox((dx_ + 1) * cs), oy((dy_ + 1) * cs),
                                fill=COL_DUP_BG, outline="")
        # 冰格蓝底 (先铺底, 虚线画在其上 → 相邻冰格共享边的虚线可见)
        for y in range(p.h):
            for x in range(p.w):
                if p.cells[y][x] == "i":
                    cv.create_rectangle(ox(x * cs), oy(y * cs),
                                        ox((x + 1) * cs), oy((y + 1) * cs),
                                        fill=(COL_ICE if not (x, y) in dup_pos else COL_DUP_ICE),
                                        outline="")
        # 高亮 (边标记起点 / IN-OUT 方向指定)
        if self._edge_start:
            ex, ey = self._edge_start
            cv.create_rectangle(ox(ex * cs) + 2, oy(ey * cs) + 2,
                                ox((ex + 1) * cs) - 2, oy((ey + 1) * cs) - 2,
                                fill=COL_ARMED, outline="")
        if self._inout_pending:
            px, py = self._inout_pending[1]
            cv.create_rectangle(ox(px * cs) + 2, oy(py * cs) + 2,
                                ox((px + 1) * cs) - 2, oy((py + 1) * cs) - 2,
                                fill=COL_PENDING, outline="#00838f", width=2)
        # 内部虚线网格 (手工画短段: tk 的 dash 参数在不同 DPI 下表现不一)
        gw = max(1, round(cs * 0.032))
        on = max(3, round(cs * 0.125))
        off = max(2, round(cs * 0.078))

        def dashed_h(y0, x_len):
            x = 0.0
            while x < x_len:
                x2 = min(x + on, x_len)
                cv.create_line(ox(x), oy(y0), ox(x2), oy(y0), fill=COL_GRID, width=gw)
                x = x2 + off

        def dashed_v(x0, y_len):
            y = 0.0
            while y < y_len:
                y2 = min(y + on, y_len)
                cv.create_line(ox(x0), oy(y), ox(x0), oy(y2), fill=COL_GRID, width=gw)
                y = y2 + off

        for i in range(1, p.w):
            dashed_v(i * cs, p.h * cs)
        for j in range(1, p.h):
            dashed_h(j * cs, p.w * cs)
        # 冰区域外缘黑边 (相邻冰格共享边不描 → 合并成一大块; 端头外延半宽补直角)
        bw = max(2, round(cs * 0.095))

        def is_ice(x, y):
            return 0 <= x < p.w and 0 <= y < p.h and p.cells[y][x] == "i"

        for y in range(p.h):
            for x in range(p.w):
                if not is_ice(x, y):
                    continue
                e = bw / 2.0
                if not is_ice(x - 1, y):
                    cv.create_line(ox(x * cs), oy(y * cs - e),
                                   ox(x * cs), oy((y + 1) * cs + e),
                                   fill=COL_INK, width=bw)
                if not is_ice(x + 1, y):
                    cv.create_line(ox((x + 1) * cs), oy(y * cs - e),
                                   ox((x + 1) * cs), oy((y + 1) * cs + e),
                                   fill=COL_INK, width=bw)
                if not is_ice(x, y - 1):
                    cv.create_line(ox(x * cs - e), oy(y * cs),
                                   ox((x + 1) * cs + e), oy(y * cs),
                                   fill=COL_INK, width=bw)
                if not is_ice(x, y + 1):
                    cv.create_line(ox(x * cs - e), oy((y + 1) * cs),
                                   ox((x + 1) * cs + e), oy((y + 1) * cs),
                                   fill=COL_INK, width=bw)
        # 加粗黑外框
        cv.create_rectangle(ox(0), oy(0), ox(p.w * cs), oy(p.h * cs),
                            outline=COL_INK, width=max(2, round(cs * 0.11)))
        # 线路: 显示解时只画解(隐藏做题内容); 否则画做题线路
        if self.show_sol.get() and 0 <= self.sol_idx < len(self.solutions):
            self._draw_path(cv, ox, oy)
        elif self.play_edges:
            self._draw_play_path(cv, ox, oy)
        # 边标记
        self._draw_edges(cv, ox, oy)
        # 推导状态叠加(确定边 / 候选边 / 每格候选数)
        self._draw_deduce_overlay(cv, ox, oy)
        # 数字 (画在线路之上, 与纸面一致不加衬底); "?" 格画问号
        # 重复的已知数字 = 题面无效 ⇒ 整格已经铺成黄底(见上面), 这里只保证字是黑的
        num_font = (NUM_FONT, -max(9, int(round(cs * 0.77))))
        num_font_small = (NUM_FONT, -max(8, int(round(cs * 0.44))))
        for (x, y), n in sorted(p.numbers.items(), key=lambda kv: (kv[1], kv[0])):
            has_internal_inout = any(
                f["x"] == x and f["y"] == y and f.get("side") is None
                for f in (p.fin, p.fout))
            if has_internal_inout:
                # 与内部 IN/OUT 文字同格: 数字挪到左上角
                cv.create_text(ox((x + 0.26) * cs), oy((y + 0.24) * cs),
                               text=("?" if n < 0 else str(n)),
                               font=num_font_small, fill=COL_NUMBER)
            else:
                cv.create_text(ox((x + 0.5) * cs), oy((y + 0.5) * cs),
                               text=("?" if n < 0 else str(n)),
                               font=num_font, fill=COL_NUMBER)
        # IN/OUT (最后画, 衬底防覆盖)
        self._draw_inout_all(cv, ox, oy)

    def _draw_path(self, cv, ox, oy):
        """解线路: 深粉红粗线, 直角尖角, 边框 IN/OUT 端伸出框外。"""
        cs = self.cs
        p = self.puz
        path = self.solutions[self.sol_idx]
        pw = max(3, round(cs * 0.11))
        # 出界端: 刚好停在箭头三角头底下(伸得太远会在头尖外露出一小截粉线)
        ext_in = ext_out = cs * 0.5 + pw / 2 + cs * 0.30
        pts = []
        if p.fin["x"] is not None and p.fin.get("side"):
            dx, dy = DIRS[p.fin["side"]]
            pts.append((ox((p.fin["x"] + 0.5) * cs + dx * ext_in),
                        oy((p.fin["y"] + 0.5) * cs + dy * ext_in)))
        pts += [(ox((x + 0.5) * cs), oy((y + 0.5) * cs)) for x, y in path]
        if p.fout["x"] is not None and p.fout.get("side"):
            dx, dy = DIRS[p.fout["side"]]
            pts.append((ox((p.fout["x"] + 0.5) * cs + dx * ext_out),
                        oy((p.fout["y"] + 0.5) * cs + dy * ext_out)))
        ded = [pts[0]]
        for q in pts[1:]:
            if q != ded[-1]:
                ded.append(q)
        if len(ded) >= 2:
            cv.create_line(*[c for q in ded for c in q],
                           fill=COL_PATH, width=pw,
                           joinstyle=tk.MITER, capstyle="round", tags="solpath")

    def _draw_play_path(self, cv, ox, oy):
        """做题线路: 蓝色圆头线段 (可多段, IN/OUT 处可伸出界外一格);
        违规橙 / 完成绿; 不画端点圆点 (与 puzz.link 一致)。"""
        cs = self.cs
        if not self.play_edges:
            return
        errs = getattr(self, "_play_errors", [])
        complete = getattr(self, "_play_complete", False)
        color = COL_PLAY
        if errs:
            color = COL_PLAY_ERR
        elif complete:
            color = COL_PLAY_OK
        pw = max(3, round(cs * 0.13))
        for e in self.play_edges:
            (x1, y1), (x2, y2) = sorted(e)
            cv.create_line(ox((x1 + 0.5) * cs), oy((y1 + 0.5) * cs),
                           ox((x2 + 0.5) * cs), oy((y2 + 0.5) * cs),
                           fill=color, width=pw, capstyle="round", tags="playpath")

    def _draw_edges(self, cv, ox, oy):
        """边标记: 线段/箭头 = 垂直于边的黑粗线(箭头带实心三角头), 墙 = 平行于边的红粗线。"""
        cs = self.cs
        p = self.puz
        lw = max(3, round(cs * 0.09))
        for (x, y, s), mk in sorted(p.edge.items()):
            kind = mk["kind"]
            if p.is_frame_key((x, y, s)):
                continue   # 边框上不再放置手工标记 (IN/OUT 自动管理)
            if s in ("R", "L"):
                bx = (x + 1) * cs if s == "R" else x * cs
                mid = [bx, (y + 0.5) * cs]
                para = (0.0, 1.0)      # 平行于边的方向
            else:
                by = (y + 1) * cs if s == "D" else y * cs
                mid = [(x + 0.5) * cs, by]
                para = (1.0, 0.0)

            def P(px, py):
                return (ox(px), oy(py))

            if kind == "wall":
                hl = cs * 0.44
                cv.create_line(P(mid[0] - para[0] * hl, mid[1] - para[1] * hl),
                               P(mid[0] + para[0] * hl, mid[1] + para[1] * hl),
                               fill=COL_WALL, width=max(3, round(cs * 0.10)),
                               capstyle="butt", tags=("edgemark",))
                continue
            dv = DIRS[mk["dir"]] if kind == "arrow" else (para[1], para[0])
            pv = (dv[1], -dv[0])
            # 线段 / 箭头: 长度 = 1 个格子(两侧格心 ↔ 格心), 关于所穿过边的中点对称
            # (比例与 icelom_render.py 的 MARK_HALF / MARK_HEAD / MARK_HW / MARK_W 一致)
            tail = (mid[0] - dv[0] * cs * 0.50, mid[1] - dv[1] * cs * 0.50)
            tip = (mid[0] + dv[0] * cs * 0.50, mid[1] + dv[1] * cs * 0.50)
            if kind == "arrow":
                base = (tip[0] - dv[0] * cs * 0.30, tip[1] - dv[1] * cs * 0.30)
                cv.create_line(P(*tail), P(*base), fill=COL_ARROW, width=lw,
                               capstyle="butt", tags=("edgemark",))
                hw = cs * 0.19
                cv.create_polygon(P(*tip),
                                  P(base[0] - pv[0] * hw, base[1] - pv[1] * hw),
                                  P(base[0] + pv[0] * hw, base[1] + pv[1] * hw),
                                  fill=COL_ARROW, outline="", tags=("edgemark",))
            else:
                cv.create_line(P(*tail), P(*tip), fill=COL_SEG, width=lw, capstyle="butt",
                               tags=("edgemark",))

    def _draw_inout_all(self, cv, ox, oy):
        """IN/OUT:
           * 边框格: 黑色实心三角箭头压在框线上(随粉线进出方向), 标签画在框外,
             位置避开箭头与线路;
           * 内部格: 格内衬底 + IN/OUT 字样 (线路以该格为起/终点, 无箭头)。"""
        p = self.puz
        cs = self.cs
        fw = max(2, round(cs * 0.11))

        def P(px, py):
            return (ox(px), oy(py))

        for f, label, inward in ((p.fin, "IN", True), (p.fout, "OUT", False)):
            if f["x"] is None:
                continue
            which = "in" if inward else "out"
            tag = ("inout", "inout_mark_" + which)          # 箭头 / 内部衬底
            lab_tag = ("inout", "inout_label_" + which)     # 框外标签
            x, y = f["x"], f["y"]
            s = f.get("side")
            cx_ = (x + 0.5) * cs
            cy_ = (y + 0.5) * cs
            if s is None:
                # ---- 内部 IN/OUT: 衬底 + 文字 ----
                half_w = cs * 0.46
                half_h = cs * 0.27
                cv.create_rectangle(P(cx_ - half_w, cy_ - half_h),
                                    P(cx_ + half_w, cy_ + half_h),
                                    fill=COL_PLATE, outline="#8d6e63", width=1,
                                    tags=tag)
                cv.create_text(P(cx_, cy_), text=label, fill=COL_INK,
                               font=(NUM_FONT, -max(8, int(round(cs * 0.34))), "bold"),
                               tags=tag)
                continue
            # ---- 边框 IN/OUT: 箭头长度 = 1 个格子, 关于外框线对称 ⇒ 箭头中心正好落在
            #      "边界格那条边的中点"上; IN 指向盘内 / OUT 指向盘外, 两者必然等长。
            #      (比例与 icelom_render.py 的 MARK_HALF / MARK_HEAD / MARK_HW 一致)
            if s == "L":
                bpt = (0.0, cy_)
            elif s == "R":
                bpt = (p.w * cs, cy_)
            elif s == "U":
                bpt = (cx_, 0.0)
            else:
                bpt = (cx_, p.h * cs)
            ov = DIRS[s]                      # 向外
            trav = (-ov[0], -ov[1]) if inward else ov       # 箭头指向 (IN 进盘 / OUT 出盘)
            tail = (bpt[0] - trav[0] * cs * 0.50, bpt[1] - trav[1] * cs * 0.50)
            tip = (bpt[0] + trav[0] * cs * 0.50, bpt[1] + trav[1] * cs * 0.50)
            base = (tip[0] - trav[0] * cs * 0.30, tip[1] - trav[1] * cs * 0.30)
            halfw = cs * 0.19
            sw = max(2, round(cs * 0.09))
            cv.create_line(P(*tail), P(*base), fill=COL_INK, width=sw, capstyle="butt",
                           tags=tag)
            px_, py_ = -trav[1], trav[0]
            cv.create_polygon(P(*tip),
                              P(base[0] - px_ * halfw, base[1] - py_ * halfw),
                              P(base[0] + px_ * halfw, base[1] + py_ * halfw),
                              fill=COL_INK, outline="", tags=tag)
            # 标签: 放在箭头**正后方**(尾端之外, 沿与外框垂直的轴居中), 不左右/上下偏
            lab_font = (NUM_FONT, -max(8, int(round(cs * 0.50))), "bold")
            off = cs * (0.50 + 0.12)
            if s == "U":
                lc, anc = (cx_, -off), "s"
            elif s == "D":
                lc, anc = (cx_, p.h * cs + off), "n"
            elif s == "L":
                lc, anc = (-off, cy_), "e"
            else:
                lc, anc = (p.w * cs + off, cy_), "w"
            cv.create_text(P(*lc), text=label, fill=COL_INK, font=lab_font, anchor=anc,
                           tags=lab_tag)


# ---------------- 自测 ----------------
def selftest():
    global ARCHIVE_FILE
    # 自测会真的求解一次(默认 unique 模式, 恰为唯一解) → 会触发"自动入档";
    # 把存档指到临时文件, 免得自测把正式存档污染掉。
    ARCHIVE_FILE = os.path.join(HERE, "tests", "_selftest_solutions.json")
    root = tk.Tk()
    app = App(root)
    root.geometry("1100x760+60+40")

    def step_solve():
        app.on_solve()

    def poll_and_capture(tries=0):
        if app.solving and tries < 300:
            root.after(100, poll_and_capture, tries + 1)
            return
        root.attributes("-topmost", True)
        root.lift()
        root.update_idletasks()
        root.update()
        root.after(400, do_capture)

    def do_capture():
        root.update()
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        w = root.winfo_width()
        h = root.winfo_height()
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            # 开发仓库里截图进 tests/（便于与历史截图对比）; 发布版没有 tests/, 就放当前目录
            shotdir = os.path.join(HERE, "tests")
            if not os.path.isdir(shotdir):
                shotdir = HERE
            img.save(os.path.join(shotdir, "gui_smoke.png"))
        except Exception as e:
            print("SCREENSHOT FAIL", e)
        print(f"SELFTEST solutions={len(app.solutions)} status={app.status.cget('text')}")
        root.destroy()

    root.after(300, step_solve)
    root.after(400, poll_and_capture)
    root.mainloop()
    try:                                   # 自测产生的存档用完即清
        os.remove(ARCHIVE_FILE)
    except OSError:
        pass
    return 0


def main():
    """命令行:
      python icelom_gui.py                            打开空界面
      python icelom_gui.py --puzzle <题面.json>        打开指定题面
      python icelom_gui.py --state <推导状态.json>      打开题面并叠加规则推导器的推导状态
      python icelom_gui.py --shot <out.png>            (配合上面两个)自动截图后退出, 用于无头验收
    """
    argv = sys.argv[1:]
    if "--selftest" in argv:
        sys.exit(selftest())

    def opt(name):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None

    state_file = opt("--state")
    puzzle_file = opt("--puzzle")
    shot = opt("--shot")
    root = tk.Tk()
    app = App(root)
    root.geometry("1100x760+60+40")
    if puzzle_file:
        try:
            app._install_puzzle(Puzzle.from_json(
                json.load(open(puzzle_file, encoding="utf-8"))), file_path=puzzle_file)
            # _install_puzzle 不碰状态栏(由调用方负责, 见 on_open / load_example_file)。
            # 这里必须自己说一句: 否则 `--puzzle` 打开的是 A 题, 状态栏却还写着启动时默认加载的
            # 那道示例(无头验收 `--puzzle ... --shot` 时最容易把人带偏)。
            app._status_with_archive_note(f"已打开 {os.path.basename(puzzle_file)}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"题面载入失败: {e}")
    if state_file:
        app.load_deduce_state(state_file)

    if shot:
        def do_shot():
            # 截图要点: 必须先把窗口抬到最前并成为焦点窗口, 否则 ImageGrab 抓到的
            # 是"当前活动窗口"(开发机上常常是别的程序 —— 真实踩过)。
            try:
                root.attributes("-topmost", True)
                root.deiconify()
                root.lift()
                root.focus_force()
                root.update_idletasks()
                root.update()
                app._on_configure()
                app.redraw()
                root.update()
            except Exception:
                pass
            try:
                from PIL import ImageGrab
                x, y = root.winfo_rootx(), root.winfo_rooty()
                w, h = root.winfo_width(), root.winfo_height()
                ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(shot)
                print(f"SHOT OK {shot} ({w}x{h})")
            except Exception as e:      # 无可见桌面时退化为"只画盘面"的离线渲染
                print("SHOT FAIL", e)
                try:
                    import icelom_render
                    icelom_render.render_state(app.puz.to_json(), app.deduce_state or {},
                                               out_png=shot)
                    print(f"SHOT OK(离屏) {shot}")
                except Exception as e2:
                    print("SHOT FAIL2", e2)
            root.destroy()
        root.after(700, do_shot)
    root.mainloop()


if __name__ == "__main__":
    main()
