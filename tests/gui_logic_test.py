# -*- coding: utf-8 -*-
"""GUI 逻辑测试 (无头): 示例列表 / 求解模式 / 箭头交互 / IN-OUT / 撤销 / 做题校验 / URL导入。"""
import base64
import json
import os
import subprocess as sp
import sys
import tempfile
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import tkinter as tk

import icelom_gui as g
import icelom_render as R          # 导出渲染器 (箭头几何回归; 需要 Pillow)
import json2penpa as JP            # Penpa+ 链接 (导出用例的独立判据: 自己解回载荷)
import verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 解存档指到临时文件: 后面的求解用例(默认 unique 模式)会触发"唯一解自动入档",
# 不能把正式存档 (%APPDATA%/IceLom/solutions.json) 污染掉。
_TEST_TMP = tempfile.mkdtemp(prefix="icelom_gui_test_")
g.ARCHIVE_FILE = os.path.join(_TEST_TMP, "solutions.json")
# 「求解」遇到存档解会先问"是否重新求解" → 无头环境默认答"是", 个别用例再覆盖
_ASK_CALLS = []
_orig_askyesno = g.messagebox.askyesno


def _auto_yes(title, message, *a, **k):
    _ASK_CALLS.append(str(message))
    return True


g.messagebox.askyesno = _auto_yes
# on_solve 会把这次用的预算记进正式 gui.json → 测试里记到内存就行
_CFG_SET_CALLS = []
_orig_cfg_set = g._cfg_set
g._cfg_set = lambda key, value: _CFG_SET_CALLS.append((key, value))

ok = True
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def report(name, cond, detail=""):
    global ok
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  " + str(detail))[:200] if detail else ""))
    ok = ok and cond


class FakeEvent:
    def __init__(self, x, y):
        self.x, self.y = x, y


root = tk.Tk()
root.withdraw()
app = g.App(root)


def pump(timeout_s=30):
    t0 = time.time()
    while app.solving and time.time() - t0 < timeout_s:
        try:
            root.update()
        except Exception:
            break
        app._poll()
        root.update_idletasks()
        time.sleep(0.01)


def click_cell(x, y):
    """模拟在格子 (x,y) 中心按下+松开。"""
    cs = app.cs
    px = app.offx + (x + 0.5) * cs
    py = app.offy + (y + 0.5) * cs
    app.on_press(FakeEvent(px, py))
    app.on_release(FakeEvent(px, py))


# --- 测试 1: 示例列表扫描与加载 ---
report("扫描 example/ 文件夹 (>=8 个示例)", len(app.examples) >= 8, app.examples)
ex02 = os.path.join(ROOT_DIR, "example", "02_博客8x8.json")
report("示例文件存在", os.path.exists(ex02))
app.load_example_file(ex02)
report("加载示例 8x8", app.puz.w == 8 and app.puz.h == 8 and len(app.puz.numbers) == 7,
       (app.puz.w, app.puz.h))
app.on_solve()
pump()
report("示例 8x8 求解 = 1 解", len(app.solutions) == 1, f"got {len(app.solutions)}")
if app.solutions:
    errs = verify.check(json.loads(json.dumps(app.puz.to_json())), app.solutions[0])
    report("示例 8x8 解通过验证器", not errs, str(errs[:3]))
# 做题未开始 → 求解后直接显示解
report("非做题状态求解后自动显示解", app.show_sol.get() is True)

# --- 测试 1b: IN/OUT 箭头几何 (长度 = 1 格 / 中心在边界格边的中点 / 标签在正后方) ---
app.cs, app.offx, app.offy = 46, 46, 46
app.redraw()
root.update_idletasks()


def tag_bbox(tag):
    xs, ys = [], []
    for it in app.canvas.find_withtag(tag):
        b = app.canvas.bbox(it)
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def mark_axis(tag, side):
    """(轴向下标, 杆尾坐标, 头尖坐标): 用图元的真实坐标 —— bbox 会被线宽撑大, 量不准长度。"""
    ln = [i for i in app.canvas.find_withtag(tag) if app.canvas.type(i) == "line"]
    pg = [i for i in app.canvas.find_withtag(tag) if app.canvas.type(i) == "polygon"]
    if not ln or not pg:
        return None
    ax = 1 if side in ("U", "D") else 0
    return ax, app.canvas.coords(ln[0])[ax], app.canvas.coords(pg[0])[ax]


fin_side, fout_side = app.puz.fin["side"], app.puz.fout["side"]
bin_ = tag_bbox("inout_mark_in")
mlen = []
for tag, side in (("inout_mark_in", fin_side), ("inout_mark_out", fout_side)):
    ax, tail, tip = mark_axis(tag, side)
    mlen.append(abs(tip - tail))
report("IN/OUT 箭头等长 (镜像对称)", abs(mlen[0] - mlen[1]) <= 1, (mlen, app.cs))
report("IN/OUT 箭头长度 = 一个格子长度",
       all(abs(v - app.cs) <= 1 for v in mlen), (mlen, app.cs))
# 箭头中心必须落在"边界格那条边的中点"上 (即外框线上该格的中段)
f_in, f_out = app.puz.fin, app.puz.fout
ax, tail, tip = mark_axis("inout_mark_in", fin_side)
cen_in = (tail + tip) / 2.0
if ax == 1:
    want_in = app.offy + (0 if fin_side == "U" else app.puz.h * app.cs)
else:
    want_in = app.offx + (0 if fin_side == "L" else app.puz.w * app.cs)
report("IN 箭头中心 = 边界格边的中点", abs(cen_in - want_in) <= 1.0, (cen_in, want_in))
# 标签: 在箭头正后方 —— 与箭头同轴(垂直方向不偏), 且在箭头之外
blab = tag_bbox("inout_label_in")
if ax == 1:
    same_axis = abs((blab[0] + blab[2]) / 2.0 - (bin_[0] + bin_[2]) / 2.0) <= 1.5
else:
    same_axis = abs((blab[1] + blab[3]) / 2.0 - (bin_[1] + bin_[3]) / 2.0) <= 1.5
report("IN 标签在箭头正后方 (与外框垂直的轴上居中, 不偏上/偏下)", same_axis, (blab, bin_))
if fin_side == "U":
    behind = blab[3] <= bin_[1] + 1
elif fin_side == "D":
    behind = blab[1] >= bin_[3] - 1
elif fin_side == "L":
    behind = blab[2] <= bin_[0] + 1
else:
    behind = blab[0] >= bin_[2] - 1
report("IN 标签落在箭头之外 (不是压在箭头上)", behind, (blab, bin_))

# --- 测试 2: 箭头交互 (创建后不保留选择 / 相同箭头清除 / 反向需从头) ---
app.puz.edge.clear()
app.tool.set("arrow")
click_cell(2, 1)                       # 选中起点
report("点击起点进入选择状态", app._edge_start == (2, 1), app._edge_start)
click_cell(3, 1)                       # 点击相邻格 → 创建 (2,1)->(3,1)
mk = app.puz.edge.get((2, 1, "R"))
report("创建箭头 R", mk is not None and mk.get("dir") == "R", mk)
report("创建后不保留选择状态", app._edge_start is None, app._edge_start)
click_cell(2, 1)                       # 重新选 (2,1)
click_cell(3, 1)                       # 从头创建相同箭头 → 清除
report("从头创建相同箭头清除该箭头", (2, 1, "R") not in app.puz.edge and app._edge_start is None)
click_cell(3, 1)                       # 选 (3,1)
click_cell(2, 1)                       # 点击 (2,1) → 反向箭头 (3,1)->(2,1)
mk = app.puz.edge.get((2, 1, "R"))
report("从头创建相反箭头才反向", mk is not None and mk.get("dir") == "L", mk)
report("反向创建后仍无残留选择", app._edge_start is None)
app._edge_from_cells(2, 1, 2, 2, "seg")     # 向下 → 线段
report("竖向线段生成", app.puz.edge.get((2, 1, "D"), {}).get("kind") == "segment")
app._edge_from_cells(2, 2, 2, 1, "wall")    # 反向创建墙 → 覆盖
mk = app.puz.edge.get((2, 1, "D"))
report("墙覆盖其它标记", mk is not None and mk.get("kind") == "wall", mk)

# --- 测试 3: 边标记写入求解器输入 ---
app.puz.edge.clear()
app._edge_from_cells(2, 1, 3, 1, "arrow")   # (2,1)->(3,1) → 边 (2,1,R) 箭头 R
app._edge_from_cells(2, 1, 2, 2, "wall")
obj = app.build_solver_input()
kinds = {(e["x"], e["y"], e["side"]): (e["kind"], e.get("dir")) for e in obj["edges"]}
report("边标记写入求解器输入", kinds.get((2, 1, "R")) == ("arrow", "R")
       and kinds.get((2, 1, "D")) == ("wall", None), str(obj["edges"]))

# --- 测试 3b: 数字选择器在「新建 / 调整大小」后重置为 1 ---
# 规则: 空白盘面从 1 开始编号, 所以**新建**之后选择器不该还停在上一次用到的数字上。
app.load_example_file(ex02)
app._set_number_pick(9)
report("数字选择器: 载入题面时保持原样(不被新建规则波及)", app.pick_number() == 9,
       app.pick_number())
app.sp_w.delete(0, "end"); app.sp_w.insert(0, "8")
app.sp_h.delete(0, "end"); app.sp_h.insert(0, "8")
app.on_resize()
# 调整大小走的是"重新出题"这条路, 但题面里的数字仍然留着 —— 所以选择器不是硬回到 1,
# 而是回到**第一个还没被占用的数字**(8x8 示例已有 1..7, 于是是 8)。
report("数字选择器: 调整大小后回到第一个空闲数字(不从 242 那样的值上接着用)",
       app.pick_number() == 8 and app.pick_number() == app.puz.next_free_number(1),
       (app.pick_number(), app.puz.next_free_number(1)))
app._set_number_pick(242)
app.on_new()                                # askyesno 已在文件头替换为"总是答是"
report("数字选择器: 新建后重置为 1", app.pick_number() == 1, app.pick_number())
report("数字选择器: 新建的状态栏说明了重置",
       "选择器" in app.status.cget("text"), app.status.cget("text"))
for _pos in ((0, 0), (1, 0), (2, 0)):       # 重置后连点应得到 1,2,3
    app._toggle_number(*_pos)
report("数字选择器: 重置后可立即连点出 1,2,3",
       [app.puz.numbers[p] for p in ((0, 0), (1, 0), (2, 0))] == [1, 2, 3],
       sorted(app.puz.numbers.items()))

# --- 测试 3c: 保存 / 另存为 ---
# 「保存」写回打开的那份文件; 「另存为」每次问路径, 之后「保存」跟着写到新文件(与旧文件解绑)。
_save_tmp = tempfile.mkdtemp(prefix="icelom_save_")
f1 = os.path.join(_save_tmp, "a.json")
f2 = os.path.join(_save_tmp, "b.json")
_orig_saveas = g.filedialog.asksaveasfilename
app._install_puzzle(g.Puzzle(3, 3), file_path=f1)
app._set_number_pick(1)
app._toggle_number(0, 0)
app.on_save()                               # 有文件名 → 不弹窗, 直接写回
report("保存: 直接写回已打开的文件(不弹路径窗)",
       os.path.exists(f1) and json.load(open(f1, encoding="utf-8"))["numbers"]
       == [{"x": 0, "y": 0, "n": 1}], os.path.exists(f1))
g.filedialog.asksaveasfilename = lambda **k: f2
try:
    app.on_save_as()
finally:
    g.filedialog.asksaveasfilename = _orig_saveas
report("另存为: 写到新文件且切换当前文件", os.path.exists(f2) and app.file_path == f2,
       app.file_path)
report("另存为: 状态栏报的是新文件名",
       os.path.basename(f2) in app.status.cget("text"), app.status.cget("text"))
os.remove(f2)
app._set_number_pick(2)
app._toggle_number(1, 0)
app.on_save()                               # 另存为之后「保存」写的是新文件, 不再碰 f1
report("另存为后「保存」跟着写新文件(旧文件不再被改)",
       json.load(open(f2, encoding="utf-8"))["numbers"]
       == [{"x": 0, "y": 0, "n": 1}, {"x": 1, "y": 0, "n": 2}]
       and len(json.load(open(f1, encoding="utf-8"))["numbers"]) == 1,
       json.load(open(f1, encoding="utf-8"))["numbers"])
g.filedialog.asksaveasfilename = lambda **k: ""      # 取消路径窗 → 什么都不做
try:
    app.on_save_as()
finally:
    g.filedialog.asksaveasfilename = _orig_saveas
report("另存为: 取消路径窗不写文件也不改当前文件", app.file_path == f2)

# --- 测试 4: 求解模式与解上限 ---
report("求解模式默认 = unique(判断唯一性)", app.solve_mode.get() == "unique", app.solve_mode.get())
report("默认模式下解上限输入框禁用", str(app.sp_max.cget("state")) == "disabled",
       app.sp_max.cget("state"))
app.solve_mode.set("first")
lim = app.build_solver_input()["limits"]
report("mode=first 不带解上限", lim.get("mode") == "first" and "max_solutions" not in lim, lim)
app.solve_mode.set("unique")
lim = app.build_solver_input()["limits"]
report("mode=unique", lim.get("mode") == "unique", lim)
app.solve_mode.set("all")
lim = app.build_solver_input()["limits"]
report("mode=all 默认解上限 20", lim.get("mode") == "all" and lim.get("max_solutions") == 20, lim)
app.max_sols.set(5)
lim = app.build_solver_input()["limits"]
report("mode=all 可修改解上限", lim.get("max_solutions") == 5, lim)

# --- 测试 5: 撤销 (题面 / 求解打断) ---
before = json.dumps(app.puz.to_json(), sort_keys=True)
app.push_undo()
app.puz.edge[(0, 0, "R")] = {"kind": "wall"}
app.on_undo()
after = json.dumps(app.puz.to_json(), sort_keys=True)
report("撤销恢复题面状态", after == before)
app.solve_mode.set("first")
app.solutions = [[[0, 0], [1, 0]]]
app.sol_idx = 0
app.push_undo({"kind": "solve"})
app.on_undo()
report("撤回求解清空解", app.solutions == [] and app.sol_idx == -1)

# --- 测试 6: IN/OUT 放置 (内部 / 边界 / 角冰格) ---
p = g.Puzzle(4, 4)
app._install_puzzle(p)
app.tool.set("in")
click_cell(1, 1)                            # 内部白格
report("内部 IN: side=None", app.puz.fin == {"x": 1, "y": 1, "side": None}, app.puz.fin)
app.tool.set("out")
click_cell(2, 2)
report("内部 OUT: side=None", app.puz.fout == {"x": 2, "y": 2, "side": None}, app.puz.fout)
obj = app.build_solver_input()
report("内部 IN/OUT 序列化省略 side", obj["in"] == {"x": 1, "y": 1}
       and obj["out"] == {"x": 2, "y": 2}, (obj["in"], obj["out"]))
click_cell(1, 1)                            # 再点同格 → 取消
report("再点同格取消 IN", app.puz.fin["x"] is None)
app.tool.set("in")
click_cell(0, 2)                            # 左边界非角 → side=L 自动
report("边界 IN: side 自动生成", app.puz.fin == {"x": 0, "y": 2, "side": "L"}, app.puz.fin)
app.tool.set("out")
click_cell(3, 1)                            # 右边界非角 → side=R
report("边界 OUT: side 自动生成", app.puz.fout == {"x": 3, "y": 1, "side": "R"}, app.puz.fout)
# 角上白格: 自动取一个边
app.tool.set("in")
click_cell(0, 0)
report("角上白格 IN 自动方向", app.puz.fin == {"x": 0, "y": 0, "side": "L"}, app.puz.fin)
app.tool.set("erase")
click_cell(0, 0)
# 角上冰格: 进入方向指定流程
app.puz.cells[0][0] = "i"
app.tool.set("in")
click_cell(0, 0)
report("角冰格 IN 进入方向指定流程", app._inout_pending == ("fin", (0, 0)), app._inout_pending)
click_cell(1, 0)                            # 点击右侧格 → 向右进入 → side=L
report("角冰格 IN 方向=向右(side=L)", app.puz.fin == {"x": 0, "y": 0, "side": "L"}
       and app._inout_pending is None, (app.puz.fin, app._inout_pending))
app.tool.set("out")
click_cell(3, 3)                            # 右下角是白格 → 自动
report("角上白格 OUT 自动方向", app.puz.fout["side"] in ("R", "D"), app.puz.fout)
app.tool.set("erase")
click_cell(3, 3)
app.puz.cells[3][3] = "i"
app.tool.set("out")
click_cell(3, 3)
report("角冰格 OUT 进入方向指定流程", app._inout_pending == ("fout", (3, 3)), app._inout_pending)
click_cell(3, 2)                            # 点击上邻格 → 线路从上来 → side=D
report("角冰格 OUT 方向=向下出界(side=D)", app.puz.fout == {"x": 3, "y": 3, "side": "D"},
       app.puz.fout)

# --- 测试 6b: 同格 IN/OUT (角冰格的两条互相垂直外边框 = 冰上垂直交叉) ---
p = g.Puzzle(3, 3)
p.cells[0][0] = "i"
p.cells[1][1] = "i"
app._install_puzzle(p)
app.tool.set("in")
click_cell(0, 0)                            # 角冰格 → 方向指定流程
click_cell(1, 0)                            # 线路去向=右 → 入界 side=L
report("同格: IN 放在角冰格 L 侧", app.puz.fin == {"x": 0, "y": 0, "side": "L"}, app.puz.fin)
app.tool.set("out")
click_cell(0, 0)                            # 同格另一端点 → 方向唯一(另一条边), 不再问方向
report("同格: OUT 落在另一条垂直边上, IN 不被顶掉",
       app.puz.fout == {"x": 0, "y": 0, "side": "U"} and app.puz.fin["side"] == "L",
       (app.puz.fin, app.puz.fout))
report("同格: 不走方向指定流程", app._inout_pending is None, app._inout_pending)
obj = app.build_solver_input()
report("同格: IN/OUT 各带自己的 side 序列化",
       obj["in"] == {"x": 0, "y": 0, "side": "L"} and obj["out"] == {"x": 0, "y": 0, "side": "U"},
       (obj["in"], obj["out"]))
app.on_solve()
pump()
report("同格: 题面求解 = 1 解", len(app.solutions) == 1, len(app.solutions))
if app.solutions:
    sol_path = [tuple(q) for q in app.solutions[0]]
    errs = verify.check(json.loads(json.dumps(app.puz.to_json())), sol_path)
    report("同格: 解通过独立验证器", not errs, str(errs[:3]))
    stubs = set()
    for f in (app.puz.fin, app.puz.fout):
        dx, dy = g.DIRS[f["side"]]
        stubs.add(frozenset({(f["x"], f["y"]), (f["x"] + dx, f["y"] + dy)}))
    base_edges = g.path_to_edges(sol_path)
    errs, inc, complete, route, redges = g.check_play_rules(app.puz, base_edges | stubs)
    report("同格: 规则引擎(画了出界短边) complete", complete and not errs and not inc,
           (errs[:2], inc[:2]))
    errs, inc, complete, route, redges = g.check_play_rules(app.puz, base_edges)
    report("同格: 规则引擎(不画出界短边) 也 complete", complete and not errs and not inc,
           (errs[:2], inc[:2]))
    report("同格: 交叉格被走了两次", list(route).count((0, 0)) == 2, route)
# 白格不允许同格共存 (至多经过一次): 仍然顶掉另一端点
app._install_puzzle(g.Puzzle(1, 3))
app.tool.set("in")
click_cell(0, 1)                            # 1 格宽: 中间格有 L/R 两条外边框 → 取第一条 L
report("同格: 1 格宽的白格 IN 取第一条外边框", app.puz.fin == {"x": 0, "y": 1, "side": "L"},
       app.puz.fin)
app.tool.set("out")
click_cell(0, 1)
report("同格: 白格仍顶掉另一端点 (白格至多经过一次)",
       app.puz.fin["x"] is None and app.puz.fout == {"x": 0, "y": 1, "side": "L"},
       (app.puz.fin, app.puz.fout))
# 1 格宽的冰格: 两条外边框同轴 → 不走方向指定流程, 点哪条边就放哪条边
app._install_puzzle(g.Puzzle(1, 3))
for yy in range(3):
    app.puz.cells[yy][0] = "i"
app.tool.set("in")
click_cell(0, 1)
report("同轴两条外边框: 不走方向指定流程", app._inout_pending is None, app._inout_pending)
report("同轴两条外边框: 默认第一条", app.puz.fin == {"x": 0, "y": 1, "side": "L"}, app.puz.fin)
app.tool.set("out")
cs0 = app.cs
px = app.offx + cs0 - 3                     # 贴近右边框点击
py = app.offy + 1.5 * cs0
app.on_press(FakeEvent(px, py))
app.on_release(FakeEvent(px, py))
report("同轴两条外边框: 点右边框就放 R 侧", app.puz.fout == {"x": 0, "y": 1, "side": "R"},
       app.puz.fout)

# --- 测试 6c: 拖动涂抹补齐 (快速拖动不漏格, 仍是一笔一条撤销记录) ---
app._install_puzzle(g.Puzzle(8, 3))
app.tool.set("cell")
n_undo = len(app.undo_stack)
app.on_press(FakeEvent(app.offx + 0.5 * app.cs, app.offy + 0.5 * app.cs))     # 起笔 (0,0)
app.on_motion(FakeEvent(app.offx + 6.5 * app.cs, app.offy + 0.5 * app.cs))    # 一步跨 6 格
report("拖动涂抹: 一次事件跨过的格子全部涂到",
       all(app.puz.cells[0][xx] == "i" for xx in range(7)) and app.puz.cells[0][7] == "w",
       "".join(app.puz.cells[0]))
app.on_motion(FakeEvent(app.offx + 6.5 * app.cs, app.offy + 2.5 * app.cs))    # 竖直跨 2 格
report("拖动涂抹: 竖向跨格也补齐",
       all(app.puz.cells[yy][6] == "i" for yy in range(3)), ["".join(r) for r in app.puz.cells])
app.on_release(FakeEvent(0, 0))
report("拖动涂抹: 整笔只压一条撤销记录", len(app.undo_stack) == n_undo + 1,
       len(app.undo_stack) - n_undo)
app.on_undo()
report("拖动涂抹: 撤掉整笔 (回到全白)", all(c == "w" for row in app.puz.cells for c in row),
       ["".join(r) for r in app.puz.cells])
# 斜向拖动 = 4 邻接阶梯, 不允许跳格
app.on_press(FakeEvent(app.offx + 0.5 * app.cs, app.offy + 0.5 * app.cs))
app.on_motion(FakeEvent(app.offx + 5.5 * app.cs, app.offy + 2.5 * app.cs))
line = g.cell_line((0, 0), (5, 2))
report("拖动涂抹: 斜向拖动按阶梯补齐 (每步 4 邻接)",
       all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(line, line[1:]))
       and all(app.puz.cells[yy][xx] == "i" for xx, yy in line),
       ["".join(r) for r in app.puz.cells])
app.on_release(FakeEvent(0, 0))
# 性能: 一次事件涂多格只重绘一次; 空扫已涂过的格子不重绘
calls = []
orig_redraw = app.redraw


def counting_redraw(*a, **k):
    calls.append(1)
    return orig_redraw(*a, **k)


app.redraw = counting_redraw
app.on_press(FakeEvent(app.offx + 0.5 * app.cs, app.offy + 1.5 * app.cs))     # (0,1) 还是白的
calls.clear()
app.on_motion(FakeEvent(app.offx + 4.5 * app.cs, app.offy + 1.5 * app.cs))    # 一次涂 5 格
n_calls = len(calls)
calls.clear()
app.on_motion(FakeEvent(app.offx + 5.5 * app.cs, app.offy + 1.5 * app.cs))    # 空格 → 无改动
app.on_release(FakeEvent(0, 0))
app.redraw = orig_redraw
report("拖动涂抹: 一次事件涂 5 格只重绘 1 次 (不是每格一次)", n_calls == 1, n_calls)
report("拖动涂抹: 涂到已涂过的格不重绘", len(calls) == 0, len(calls))
# 橡皮拖动: 同样补齐 (空扫不重绘)
app.tool.set("erase")
app.on_press(FakeEvent(app.offx + 0.5 * app.cs, app.offy + 1.5 * app.cs))
app.on_motion(FakeEvent(app.offx + 4.5 * app.cs, app.offy + 1.5 * app.cs))
report("橡皮拖动: 跨过的格子全部擦除",
       all(app.puz.cells[1][xx] == "w" for xx in range(5)), "".join(app.puz.cells[1]))
app.on_release(FakeEvent(0, 0))

# --- 测试 6d: 边标记 / IN-OUT 箭头几何 (长度 = 1 格, 中心落在边的中点上, 三角头不得退化) ---
app._install_puzzle(g.Puzzle(3, 3))
app.cs, app.offx, app.offy = 46, 46, 46
app.puz.fin = {"x": 0, "y": 0, "side": "L"}
app.puz.fout = {"x": 2, "y": 2, "side": "R"}
app.puz.edge[(1, 0, "R")] = {"kind": "arrow", "dir": "R"}
app.redraw()
root.update_idletasks()
items = app.canvas.find_withtag("edgemark")
polys = [i for i in items if app.canvas.type(i) == "polygon"]
lines = [i for i in items if app.canvas.type(i) == "line"]
report("边标记: 箭头 = 杆 + 实心三角头 (各一个图元)",
       len(polys) == 1 and len(lines) == 1, (lines, polys))
if polys and lines:
    co = app.canvas.coords(polys[0])
    head_area = abs((co[2] - co[0]) * (co[5] - co[1]) - (co[4] - co[0]) * (co[3] - co[1])) / 2.0
    report("边标记: 三角头不退化成一条线 (三点不共线)", head_area > 0.02 * app.cs ** 2, head_area)
    ln = app.canvas.coords(lines[0])
    mid_x = app.offx + 2 * app.cs                  # 边 (1,0,R) 的中点
    cen = (ln[0] + co[0]) / 2.0                    # 杆尾 ↔ 头尖
    report("边标记: 箭头中心落在所穿过边的中点上", abs(cen - mid_x) <= 1.0, (cen, mid_x))
    report("边标记: 箭头长度 = 一个格子长度", abs((co[0] - ln[0]) - app.cs) <= 1.0,
           (co[0] - ln[0], app.cs))
    report("边标记: 两端正好是两侧格心 (格心 ↔ 格心)",
           abs(ln[0] - (app.offx + 1.5 * app.cs)) <= 1.0
           and abs(co[0] - (app.offx + 2.5 * app.cs)) <= 1.0,
           (ln[0], co[0], app.offx, app.cs))
# 导出渲染器: 同一套比例 (mark_geometry), 且图上真的能看见三角头
for dv, name in (((1, 0), "R"), ((-1, 0), "L"), ((0, 1), "D"), ((0, -1), "U")):
    tail, base, tip, pv = R.mark_geometry((100.0, 50.0), dv, 64.0)
    hw = R.MARK_HW * 64.0
    a = abs((base[0] - pv[0] * hw - tip[0]) * (base[1] + pv[1] * hw - tip[1])
            - (base[0] + pv[0] * hw - tip[0]) * (base[1] - pv[1] * hw - tip[1])) / 2.0
    report(f"渲染器标记几何 {name}: 中心 = 边中点, 总长 = 1 格",
           abs((tail[0] + tip[0]) / 2.0 - 100.0) < 1e-6
           and abs((tail[1] + tip[1]) / 2.0 - 50.0) < 1e-6
           and abs(abs(tip[0] - tail[0]) + abs(tip[1] - tail[1]) - 64.0) < 1e-6,
           (tail, tip))
    report(f"渲染器标记几何 {name}: 三角头不退化成线", a > 20.0, a)
# 端到端: 渲染一张带箭头的图, 在像素上量墨迹范围 (IN 在 L 侧 ⇒ 左边距 = 2cs)
puz_arrow = {"format": "icelom-v1", "w": 3, "h": 3, "cells": ["w"] * 9, "numbers": [],
             "in": {"x": 0, "y": 0, "side": "L"}, "out": {"x": 2, "y": 2, "side": "R"},
             "edges": [{"x": 1, "y": 0, "side": "R", "kind": "arrow", "dir": "R"}],
             "options": {"cover_all_whites": True}}
img = R.render_puzzle(puz_arrow, cell=64, scale=1)
pxs = img.load()
mid_x = int(round(2.0 * 64)) + 2 * 64                       # 边 (1,0,R) 的中点 (输出像素)
ink = [(xx, yy) for xx in range(mid_x - 40, mid_x + 40)
       for yy in range(int(round(0.35 * 64)) + 13, int(round(0.35 * 64)) + 51)
       if all(c < 100 for c in pxs[xx, yy][:3])]
report("导出图: 箭头有墨迹", bool(ink), len(ink))
if ink:
    xs = [t[0] for t in ink]
    thick = {}
    for xx, yy in ink:
        thick[xx] = thick.get(xx, 0) + 1
    report("导出图: 箭头墨迹中心 = 边中点", abs((min(xs) + max(xs)) / 2.0 - mid_x) <= 1.5,
           ((min(xs) + max(xs)) / 2.0, mid_x))
    report("导出图: 箭头墨迹长度 = 一个格子", abs((max(xs) - min(xs)) - 64) <= 3,
           (max(xs) - min(xs), 64))
    report("导出图: 三角头的宽度明显大于杆 (头画出来了)",
           max(thick.values()) >= int(0.30 * 64), max(thick.values()))
# 导出图里的 IN/OUT: 标签必须在箭头正后方 (与外框垂直的轴上居中, 而不是偏上/偏下)
puz_io = {"format": "icelom-v1", "w": 3, "h": 3, "cells": ["w"] * 9, "numbers": [],
          "in": {"x": 0, "y": 1, "side": "L"}, "out": {"x": 0, "y": None, "side": None},
          "edges": [], "options": {"cover_all_whites": True}}
puz_io["out"] = {"x": None, "y": None, "side": None}
img2 = R.render_puzzle(puz_io, cell=64, scale=1)
p2 = img2.load()
oy = int(round(0.35 * 64))
ox = int(round(2.0 * 64))
row_c = oy + 1.5 * 64
lab = [(xx, yy) for xx in range(0, ox - 32)
       for yy in range(img2.size[1]) if all(c < 100 for c in p2[xx, yy][:3])]
report("导出图: IN 标签在箭头正后方 (存在墨迹)", bool(lab), len(lab))
if lab:
    ys = [t[1] for t in lab]
    xs2 = [t[0] for t in lab]
    report("导出图: IN 标签与外框垂直的轴上居中 (不再偏上/偏下)",
           abs((min(ys) + max(ys)) / 2.0 - row_c) <= 2.0,
           ((min(ys) + max(ys)) / 2.0, row_c))
    report("导出图: IN 标签落在箭头之外 (箭头外端在 x=%d)" % (ox - 32), max(xs2) < ox - 32,
           max(xs2))

# --- 测试 7: 做题规则引擎 (线段集合模型, 判定语义参照 pzprjs AnsCheck) ---
p2 = g.Puzzle.from_json(json.load(open(ex02, encoding="utf-8")))
q = dict(p2.to_json())
q["limits"] = {"mode": "first", "time_limit_ms": 30000}
r = sp.run([g.SOLVER], input=json.dumps(q).encode(),
           stdout=sp.PIPE, stderr=sp.PIPE, timeout=60)
sol = json.loads(r.stdout.decode().strip().splitlines()[0])["path"]
errs, inc, complete, route, redges = g.check_play_rules(p2, g.path_to_edges(sol))
report("规则引擎: 完整解 complete", complete and not errs and not inc,
       (errs[:2], inc[:2]))
errs, inc, complete, route, redges = g.check_play_rules(
    p2, g.path_to_edges(list(reversed(sol))))
report("规则引擎: 反向画解仍 complete (无方向性)", complete and not errs, errs[:2])
# 未完成: 去掉最后一格 → 只报未完成项, 不算画错
trunc = g.path_to_edges([tuple(pt) for pt in sol[:-1]])
errs, inc, complete, route, redges = g.check_play_rules(p2, trunc)
report("规则引擎: 未完成线路只报未完成", not errs and not complete and len(inc) > 0,
       (errs[:2], inc[:2]))
# 游离线段: 线路已成解 (3x3 中行直通, 不要求覆盖) + 一条不接触线路的线段 → 报"多余线段"
p4 = g.Puzzle(3, 3)
p4.fin = {"x": 0, "y": 1, "side": "L"}
p4.fout = {"x": 2, "y": 1, "side": "R"}
done_edges = g.path_to_edges([(-1, 1), (0, 1), (1, 1), (2, 1), (3, 1)])
errs, inc, complete, route, redges = g.check_play_rules(p4, done_edges, cover_all=False)
report("规则引擎: 3x3 直通线路 complete", complete and not errs and not inc, (errs, inc))
errs, inc, complete, route, redges = g.check_play_rules(
    p4, done_edges | {frozenset({(0, 0), (1, 0)})}, cover_all=False)
report("规则引擎: 游离线段报违规", any("多余" in e for e in errs), errs[:3])
# 冰格转弯: 3x3 冰格 (1,1) 拐弯穿过 → 报错
p3 = g.Puzzle(3, 3)
p3.cells[1][1] = "i"
p3.fin = {"x": 0, "y": 1, "side": "L"}
p3.fout = {"x": 2, "y": 1, "side": "R"}
errs, inc, complete, route, redges = g.check_play_rules(
    p3, g.path_to_edges([(0, 1), (1, 1), (1, 0), (2, 0), (2, 1)]))
report("规则引擎: 冰格转弯报错", any("冰格" in e and "转弯" in e for e in errs), errs)
# IN/OUT 出界短边端到端: 界外一格接入边框箭头 → complete, route 为盘内格序列
ok_edges = g.path_to_edges([(-1, 1), (0, 1), (1, 1), (2, 1), (3, 1)])
errs, inc, complete, route, redges = g.check_play_rules(p3, ok_edges, cover_all=False)
report("规则引擎: 出界短边进出 complete", complete and not errs and not inc,
       (errs, inc))
report("规则引擎: route 为盘内格序列", route == [(0, 1), (1, 1), (2, 1)], route)

# --- 测试 8: 做题拖动手势 (多段线段 / 拖回回退 / 拖过=擦除 / 撤销) ---
app._install_puzzle(g.Puzzle.from_json(json.load(open(ex02, encoding="utf-8"))))
app.mode.set("play")
app.play_edges = set()
app._play_press(0, 0)                  # IN 格起笔
for nxt in [(1, 0), (2, 0), (3, 0)]:
    app._play_motion(*nxt)
expect = {frozenset({(0, 0), (1, 0)}), frozenset({(1, 0), (2, 0)}),
          frozenset({(2, 0), (3, 0)})}
report("做题: 拖动延伸生成线段", app.play_edges == expect, app.play_edges)
app._play_motion(2, 0)                 # 拖回上一步 → 回退
report("做题: 拖回回退", app.play_edges == expect - {frozenset({(2, 0), (3, 0)})},
       app.play_edges)
app.on_release(FakeEvent(0, 0))
# 从空白格另起一段 (多段作画)
app._play_press(0, 1)
app._play_motion(1, 1)
app.on_release(FakeEvent(0, 0))
report("做题: 可另起一段 (多段线段)", frozenset({(0, 1), (1, 1)}) in app.play_edges,
       app.play_edges)
report("做题: 游离段归入未完成而非违规",
       app._play_errors == [] and any("未与线路连接" in s for s in app._play_incomplete),
       (app._play_errors[:2], app._play_incomplete[:2]))
# 拖过已有线段 → 擦除
app._play_press(0, 1)
app._play_motion(1, 1)
app.on_release(FakeEvent(0, 0))
report("做题: 拖过已有线段=擦除", frozenset({(0, 1), (1, 1)}) not in app.play_edges,
       app.play_edges)
app.on_clear_play()
report("做题: 清除线路", app.play_edges == set())
report("做题: 清除可撤销", app.undo_stack[-1]["kind"] == "play")
app.on_undo()
report("做题: 撤销恢复线段集",
       app.play_edges == expect - {frozenset({(2, 0), (3, 0)})}, app.play_edges)
# 无效手势 (两端都在盘外) 不产生撤销记录
n_undo = len(app.undo_stack)
app._play_press(-1, -1)
app._play_motion(-1, 0)
app.on_release(FakeEvent(0, 0))
report("做题: 无效手势不压撤销栈", len(app.undo_stack) == n_undo,
       (n_undo, len(app.undo_stack)))
# add 模式下压过"已存在的线段" = 无操作, 整笔只压一条撤销记录
app.play_edges = g.path_to_edges([(1, 0), (2, 0)])
app.undo_stack.clear()
app._play_press(0, 0)
app._play_motion(1, 0)                 # 空边 → 进入 add 模式并加线
app._play_motion(2, 0)                 # 已有线 → add 模式无操作
app.on_release(FakeEvent(0, 0))
report("做题: add 模式压过已有线无操作, 整笔仅一条撤销记录",
       app.play_edges == g.path_to_edges([(0, 0), (1, 0), (2, 0)])
       and len(app.undo_stack) == 1, (app.play_edges, len(app.undo_stack)))
app.mode.set("edit")

# --- 测试 9: 边做题边求解 → 显示解/隐藏解 (互斥显示) ---
app.load_example_file(ex02)
app.mode.set("play")
app.play_edges = g.path_to_edges([(0, 0), (1, 0), (2, 0)])
app.mode.set("edit")
app.on_solve()
pump()
report("边做题求解: 有解且不自动显示", len(app.solutions) >= 1 and app.show_sol.get() is False,
       (len(app.solutions), app.show_sol.get()))
app.on_toggle_show_sol()
root.update()
report("显示解: 进入解视图", app.show_sol.get() is True)
report("显示解时隐藏做题线路", not app.canvas.find_withtag("playpath")
       and len(app.canvas.find_withtag("solpath")) >= 1)
app.on_toggle_show_sol()
root.update()
report("隐藏解回到做题界面", app.show_sol.get() is False and len(app.play_edges) == 2
       and len(app.canvas.find_withtag("playpath")) >= 1
       and not app.canvas.find_withtag("solpath"))

# --- 测试 9b: 对照解 (验证"是解的一部分/无错误连接", 无方向性; 只报对/错) ---
app.solve_mode.set("first")
sol0 = [tuple(pt) for pt in app.solutions[0]]
sol0e = g.path_to_edges(sol0)
wrong = None
for yy in range(app.puz.h):
    for xx in range(app.puz.w):
        for ddx, ddy in ((1, 0), (0, 1)):
            nb = (xx + ddx, yy + ddy)
            if nb[0] < app.puz.w and nb[1] < app.puz.h:
                e = frozenset({(xx, yy), nb})
                if e not in sol0e:
                    wrong = e
                    break
        if wrong:
            break
    if wrong:
        break
report("对照解: 找到一条解外线段", wrong is not None)
app.on_check_solution()                    # 已有解 → 立即比对
app.play_edges = sol0e | {wrong}
app.on_check_solution()
report("对照解: 含错误连接报错", "错误" in app.status.cget("text"), app.status.cget("text"))
app.play_edges = set(sol0e)
app.on_check_solution()
report("对照解: 完整照抄解报对 (方向/起终点无关)", "正确" in app.status.cget("text"),
       app.status.cget("text"))
app.play_edges = g.path_to_edges(sol0[:max(2, len(sol0) // 2)])
app.on_check_solution()
report("对照解: 部分解 (是解的一部分) 报对", "正确" in app.status.cget("text"),
       app.status.cget("text"))
# IN/OUT 处的出界短边不参与比对
stubs = set()
for f in (app.puz.fin, app.puz.fout):
    if f.get("side"):
        ddx, ddy = g.DIRS[f["side"]]
        stubs.add(frozenset({(f["x"], f["y"]), (f["x"] + ddx, f["y"] + ddy)}))
app.play_edges = sol0e | stubs
app.on_check_solution()
report("对照解: 含出界短边仍报对", "正确" in app.status.cget("text"),
       app.status.cget("text"))
# 检查解 (规则引擎按钮): 完整解 → 正确
app.play_edges = sol0e
app.on_check_rules()
report("检查解: 完整解报正确", "正确" in app.status.cget("text"), app.status.cget("text"))
app.play_edges = g.path_to_edges(sol0[:max(2, len(sol0) // 2)])
app.on_check_rules()
report("检查解: 未完成线路报未完成", "完成" in app.status.cget("text")
       and "错误" not in app.status.cget("text"), app.status.cget("text"))
# 清空解 → 走"静默求解后比对"的异步路径
app.play_edges = sol0e
app.clear_solution()
app.on_check_solution()
pump()
report("对照解: 无解时静默求解再比对", not app.solving and "正确" in app.status.cget("text"),
       (len(app.solutions), app.status.cget("text")))
report("对照解: 不显示解内容", app.show_sol.get() is False
       and not app.canvas.find_withtag("solpath"))
app.play_edges = set()
app.on_check_solution()
report("对照解: 空线路提示先画线", "先" in app.status.cget("text"), app.status.cget("text"))

# --- 测试 10: 内部 IN/OUT 与角冰格示例端到端 ---
ex09 = os.path.join(ROOT_DIR, "example", "09_内部INOUT演示.json")
app.load_example_file(ex09)
report("内部 IN/OUT 示例加载", app.puz.fin.get("side") is None
       and app.puz.fout.get("side") is None, (app.puz.fin, app.puz.fout))
app.on_solve()
pump()
report("内部 IN/OUT 示例求解 = 1 解", len(app.solutions) == 1, len(app.solutions))
if app.solutions:
    errs = verify.check(json.loads(json.dumps(app.puz.to_json())), app.solutions[0])
    report("内部 IN/OUT 解通过验证器", not errs, str(errs[:3]))
    app.on_toggle_show_sol()
    report("内部 IN/OUT 显示解后可隐藏", app.show_sol.get() is False)

ex10 = os.path.join(ROOT_DIR, "example", "10_角冰格INOUT演示.json")
app.load_example_file(ex10)
app.on_solve()
pump()
report("角冰格示例求解 = 1 解", len(app.solutions) == 1, len(app.solutions))

# --- 测试 11: 求解模式端到端 (unique / all / first) ---
app.load_example_file(ex02)
app.solve_mode.set("unique")
app.on_solve()
pump()
report("端到端 unique: 博客8x8 解唯一", app.status.cget("text").find("唯一") >= 0
       and len(app.solutions) == 1, app.status.cget("text"))
app.solve_mode.set("first")
app.on_solve()
pump()
report("端到端 first: 恰好 1 解", len(app.solutions) == 1, len(app.solutions))
app.solve_mode.set("all")
app.max_sols.set(20)
app.on_solve()
pump()
report("端到端 all(上限20): 正常完成", len(app.solutions) <= 20 and not app.solving,
       (len(app.solutions), app.status.cget("text")))

# --- 测试 12: 数字选择器 + 数字 / "?" 格工具 ---
app._install_puzzle(g.Puzzle(3, 3))
app.puz.numbers = {(0, 0): 5, (1, 1): 9}
app.tool.set("num")

# 12.1 手动输入: 放的就是选择器里的数(不再"接着最大编号 +1"), 且放完自动跳到下一个可用数字
app._set_number_pick(12)
app._toggle_number(2, 2)
report("手动输入 12 → 放置 12", app.puz.numbers.get((2, 2)) == 12, app.puz.numbers)
report("放完自动跳到下一个可用数字 13", app.pick_number() == 13, app.pick_number())

# 12.2 连点: 一直放"下一个可用数字", 且跳过已有的 5 / 9 / 12
app._set_number_pick(1)
for pos in ((2, 0), (2, 1), (0, 1), (0, 2)):
    app._toggle_number(*pos)
report("连点自动跳号(跳过 5/9/12)", [app.puz.numbers[p] for p in
                                ((2, 0), (2, 1), (0, 1), (0, 2))] == [1, 2, 3, 4],
       [(p, app.puz.numbers[p]) for p in ((2, 0), (2, 1), (0, 1), (0, 2))])

# 12.3 上下箭头: 跳过盘面上已有的数字(此时 1,2,3,4,5,9,12 已被占用)
app._set_number_pick(4)
app._step_number_pick(+1)
report("↑ 跳过已有的 5 → 6", app.pick_number() == 6, app.pick_number())
app._set_number_pick(11)                    # 11 空闲 → 直接相邻; 10 也空闲
app._step_number_pick(-1)
report("↓ 空闲时就是相邻数 10", app.pick_number() == 10, app.pick_number())
app._set_number_pick(6)
app._step_number_pick(-1)                   # 6 以下全被占用 → 落到地板 1(不落 0/负数)
report("↓ 下方全被占用时停在 1", app.pick_number() == 1, app.pick_number())
app._step_number_pick(-1)
report("↓ 已在 1 时不再往下", app.pick_number() == 1, app.pick_number())
app._set_number_pick(504)                   # 远远超过盘面上最大数字 → 直接相邻
app._step_number_pick(-1)
report("↓ 到没被占用的 503", app.pick_number() == 503, app.pick_number())

# 12.4 手动输入重复数字 → 该数字的每一格都进"重复"清单(界面标黄警告)
app._install_puzzle(g.Puzzle(3, 3))
app.tool.set("num")
app._set_number_pick(3)
app._toggle_number(0, 0)                    # (0,0) = 3
app._set_number_pick(1)
app._toggle_number(2, 2)                    # (2,2) = 1
app._set_number_pick(3)                     # 再次手动输入 3 → 故意重复
app._toggle_number(1, 1)                    # (1,1) = 3
dups = app._refresh_dup_numbers()
report("重复数字进警告清单",
       set(dups) == {3} and app.puz.dup_positions() == {(0, 0), (1, 1)},
       {v: ps for v, ps in dups.items()})
report("状态栏给出无效提示", "题目无效" in app._dup_status_suffix(), app._dup_status_suffix())

# 12.5 再点同一格 = 删除(不动选择器); 删掉重复的那一格后警告消失
app._set_number_pick(7)
app._toggle_number(1, 1)
dup_after = app._refresh_dup_numbers()
report("点已有数字=删除, 选择器不变",
       (1, 1) not in app.puz.numbers and app.pick_number() == 7,
       (app.puz.numbers.get((1, 1)), app.pick_number()))
report("删掉重复格后警告消失", dup_after == {}, dup_after)

# 12.6 "?格" 工具: 不受选择器影响, 只放/取消 n = -2
app.tool.set("qmark")
app._toggle_number(0, 1, qmark=True)
report("\"?格\" 工具放置 n=-2", app.puz.numbers.get((0, 1)) == -2)
app._toggle_number(0, 1, qmark=True)
report("\"?格\" 工具再点取消", (0, 1) not in app.puz.numbers)

# 12.7 载入题面时自动对齐: 重复数字会被识别, 选择器不会停在已占用的数字上
app._install_puzzle(g.Puzzle(2, 2))
app.puz.numbers = {(0, 0): 2, (1, 1): 2}
app._set_number_pick(7)
app._sync_number_pick()
report("载入即识别重复数字", set(app._dup_nums) == {2}, app._dup_nums)
report("选择器空闲时保持不动", app.pick_number() == 7, app.pick_number())
app._set_number_pick(2)                     # 2 已被占用 → 同步时应让开
app._sync_number_pick()
report("选择器避开已占用数字", app.pick_number() == 1, app.pick_number())

# --- 测试 13: URL 导入管线 ---
try:
    r = sp.run(["node", g.URL_TOOL,
                "https://puzz.link/p?icelom/a/8/8/4e40040c4g004i6r3k7k5w4i2g1q/0/15"],
               stdout=sp.PIPE, stderr=sp.PIPE, timeout=90)
    obj = json.loads(r.stdout.decode().strip().splitlines()[-1])
    imported = g.Puzzle.from_json(obj)
    report("导入管线解析 8x8", imported.w == 8 and imported.h == 8
           and imported.numbers[(3, 0)] == 6
           and imported.fin == {"x": 0, "y": 0, "side": "U"})
    app._install_puzzle(imported)
    app.on_solve()
    pump()
    report("导入 8x8 求解 = 1 解", len(app.solutions) == 1)
except Exception as e:
    report("URL 导入管线", False, repr(e))

# --- 测试 14: 求解器 stderr 只是诊断, 不是错误 ---
# 求解器把 stderr 当**诊断通道**用（docs/求解器协议.md §1 明确 "stderr: 诊断信息, 不属于协议"）:
# 搜遍全树仍无解时打印 `[unsat-diag]` 最深现场盘面, ICELOM_DUMP=1 / ICELOM_DIAG_ON_ABORT=1
# 等调试开关也都走 stderr。旧版本把**任何** stderr 都当"求解器异常输出"弹模态错误框,
# 于是只要题面无解, 每次点「求解」都会被糊一脸 ASCII 盘面并卡住界面 —— 这里钉住新行为:
# 诊断只收集 (「查看 → 求解器诊断」按需看), 只有**非零退出码**才是真错误。
diag_dialogs = []


def _catch_dialog(kind):
    def f(title, message, *a, **k):
        diag_dialogs.append((kind, str(message)))
        return None
    return f


def _find_texts(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, tk.Text):
            out.append(c)
        out.extend(_find_texts(c))
    return out


_saved_dialogs = (g.messagebox.showerror, g.messagebox.showwarning, g.messagebox.showinfo)
app.load_example_file(os.path.join(ROOT_DIR, "example", "01_经典9x9.json"))
app.solve_mode.set("unique")
app.on_solve()
pump()
report("原始示例 01 求解 = 1 解 (改题前的基线)", len(app.solutions) == 1, len(app.solutions))

app.puz.cells[3][1] = "w"      # (x=1,y=3) 冰格→白格: 已知会搜遍全树且无解
app.clear_solution()
diag_dialogs.clear()
g.messagebox.showerror = _catch_dialog("error")
g.messagebox.showwarning = _catch_dialog("warning")
g.messagebox.showinfo = _catch_dialog("info")
try:
    app.on_solve()
    pump()
finally:
    (g.messagebox.showerror, g.messagebox.showwarning,
     g.messagebox.showinfo) = _saved_dialogs
report("无解题面: 求解不弹任何对话框", diag_dialogs == [], diag_dialogs)
report("无解题面: 状态=无解 (不是报错)",
       app.status.cget("text") == "无解" and not app.solutions,
       (app.status.cget("text"), len(app.solutions)))
report("无解题面: [unsat-diag] 被收进诊断 (信息不丢)",
       "[unsat-diag]" in app._solver_diag and "开放端点" in app._solver_diag,
       repr(app._solver_diag[:70]))
report("无解题面: 队列已排空 (诊断不会残留给下一次求解)", app.q.empty())
report("无解题面: 「求解器诊断」菜单可用",
       str(app.diag_menu.entrycget(0, "state")) == "normal",
       app.diag_menu.entrycget(0, "state"))

app.on_show_diag()                       # 非模态只读窗口
root.update()
_tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
_txts = _find_texts(_tops[0]) if _tops else []
report("诊断窗口: 打开且为只读、内容即诊断",
       len(_tops) == 1 and len(_txts) == 1
       and "[unsat-diag]" in _txts[0].get("1.0", "end")
       and str(_txts[0].cget("state")) == "disabled",
       (len(_tops), len(_txts)))
for _t in _tops:
    _t.destroy()
root.update()

# 可解题面: 没有诊断 → 菜单置灰; 点菜单只给状态栏提示, 不开窗不弹框
app.load_example_file(os.path.join(ROOT_DIR, "example", "01_经典9x9.json"))
app.on_solve()
pump()
report("可解题面: 1 解且无诊断文本", len(app.solutions) == 1 and app._solver_diag.strip() == "",
       (len(app.solutions), repr(app._solver_diag[:40])))
report("可解题面: 诊断菜单置灰",
       str(app.diag_menu.entrycget(0, "state")) == "disabled",
       app.diag_menu.entrycget(0, "state"))
_n_before = len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)])
app.on_show_diag()
root.update()
report("空诊断: 只提示状态栏, 不开窗",
       len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]) == _n_before
       and "没有诊断输出" in app.status.cget("text"), app.status.cget("text"))

# 非零退出码 = 真错误: 这时才该弹框 (并带上 stderr 尾巴)
class _DeadProc:
    """假的"已退出"进程: 只提供 _poll 需要的 poll()/returncode。"""

    def __init__(self, rc):
        self.returncode = rc

    def poll(self):
        return self.returncode


def _fake_exit(rc, diag):
    app.proc = _DeadProc(rc)
    app.solving = True
    app._reader_done = True
    app._stopped = False
    app._solver_diag = diag
    app._flush_wait = 0
    app._finished = False
    while not app.q.empty():
        app.q.get_nowait()
    app._poll()


diag_dialogs.clear()
g.messagebox.showerror = _catch_dialog("error")
try:
    _fake_exit(3, "boom-on-stderr\n")
finally:
    g.messagebox.showerror = _saved_dialogs[0]
report("求解器崩溃(退出码 3): 才弹错误框",
       any(d[0] == "error" for d in diag_dialogs), diag_dialogs)
report("求解器崩溃: 错误框带上 stderr 尾巴",
       any("boom-on-stderr" in d[1] for d in diag_dialogs), diag_dialogs)
report("求解器崩溃: 状态=异常退出", "异常退出" in app.status.cget("text"),
       app.status.cget("text"))
diag_dialogs.clear()
g.messagebox.showerror = _catch_dialog("error")
try:
    _fake_exit(0, "")            # 退出码 0 = 正常, 但没给 done 记录 → 不算错误框
finally:
    g.messagebox.showerror = _saved_dialogs[0]
report("退出码 0 但没 done 记录: 不弹框, 只报意外退出",
       diag_dialogs == [] and "意外退出" in app.status.cget("text"),
       (diag_dialogs, app.status.cget("text")))

# 收尾竞态: `done` 是 stdout 最后一行, 读取线程随后才排空 stderr, 所以要跨两次轮询才定稿。
# 必须确认第二趟不会因为"这次没读到 done"就把成功的求解误报成"求解器意外退出"。
app.proc = _DeadProc(0)          # 进程已退出(退出码 0)
app.solving = True
app._stopped = False
app._reader_done = False         # stderr 还没排空
app._solver_diag = ""
app._flush_wait = 0
app._finished = False
while not app.q.empty():
    app.q.get_nowait()
app.q.put(json.dumps({"type": "done", "count": 2, "nodes": 5, "ms": 1.0, "aborted": False}))
app.solve_mode.set("all")
app._poll()                      # 第 1 趟: 拿到 done, 但 stderr 未排空 → 推迟定稿
_st1 = app.status.cget("text")
report("done 已到但 stderr 未排空: 推迟定稿且不误报",
       app.solving is True and app._flush_wait == 1 and "意外退出" not in _st1,
       (_st1, app.solving, app._flush_wait))
app._reader_done = True          # 读取线程收尾
app._poll()                      # 第 2 趟: 按 done 的结论定稿, 不能改成"意外退出"
report("收尾后按 done 结论定稿 (不覆盖成'求解器意外退出')",
       app.solving is False and "意外退出" not in app.status.cget("text")
       and "完成" in app.status.cget("text"),
       (app.solving, app.status.cget("text")))

# unique 模式截断: 求解器**保守虚报 count=2**(icelom_solver.cpp:1187, 只找到 1 个解就超时
# 也报 2)。界面必须如实说"未证完穷尽", 不能断言"解不唯一" —— 20260915(25x7, 唯一解,
# 120s 证不完)就曾被这个虚报误判成"解不唯一"。
app.proc = _DeadProc(0)
app.solving = True
app._stopped = False
app._reader_done = True
app._solver_diag = ""
app._flush_wait = 0
app._finished = False
while not app.q.empty():
    app.q.get_nowait()
app.solutions = [[(0, 1), (1, 1)]]       # 只真正找到 1 个解
app.q.put(json.dumps({"type": "done", "count": 2, "nodes": 9, "ms": 120000.0,
                      "aborted": True}))
app.solve_mode.set("unique")
app._poll()
root.update()
report("unique 截断(保守虚报 count=2): 状态说「未能证完穷尽」并提示调大预算, 不说「解不唯一」",
       "证完穷尽" in app.status.cget("text")
       and "解不唯一" not in app.status.cget("text")
       and "推理预算" in app.status.cget("text"),
       app.status.cget("text"))

# --- 测试 14b: 解存档 (自动入档/自动载入/求解询问) + 推理预算 ---
ex01 = os.path.join(ROOT_DIR, "example", "01_经典9x9.json")
# 存档键 = 题面内容指纹: 等价表示(键序/format/options/limits 无关)同键, 改一格就换键
_base02 = json.load(open(ex02, encoding="utf-8"))
_shuffled = {k: _base02[k] for k in sorted(_base02, reverse=True)}
_k02 = g.puzzle_key(_base02)
report("存档键: 等价表示同键 (键序/format/options 无关)", _k02 == g.puzzle_key(_shuffled))
_mut = json.loads(json.dumps(_base02))
_mut["cells"][0] = "i" if _mut["cells"][0] == "w" else "w"
report("存档键: 题面一变键就变", g.puzzle_key(_mut) != _k02)

# 模块函数读写: 存 → 查得到; 题面一变 → 查不到; 存档损坏 → 查不到且不抛异常
_arch = os.path.join(tempfile.mkdtemp(prefix="icelom_arch_"), "solutions.json")
_p02 = g.Puzzle.from_json(_base02)
report("存档: 写入返回 None(成功)",
       g.archive_save_solution(_p02.to_json(), [[0, 0], [1, 0]],
                               source="test", file_path="x.json", archive_path=_arch) is None)
_rec = g.archive_lookup(_p02.to_json(), path=_arch)
report("存档: 写后能按内容指纹查到", _rec is not None and _rec["path"] == [[0, 0], [1, 0]], _rec)
report("存档: 同一道题的解记成 answer 链接(不是 other), 不写 answer_key",
       "answer" in (_rec.get("links") or {}) and "other" not in (_rec.get("links") or {})
       and "answer_key" not in _rec, sorted(_rec.get("links") or {}))
report("存档: 题面链接与工具现算的一致(不留过期链接)",
       _rec["links"]["puzzle"] == JP.make_url(_p02.to_json()))
report("存档: 题面变了就查不到", g.archive_lookup(_mut, path=_arch) is None)
with open(_arch, "w", encoding="utf-8") as _f:
    _f.write("{broken")
report("存档: 损坏文件查不到也不抛异常", g.archive_lookup(_p02.to_json(), path=_arch) is None)

# GUI: 存档里已有解的题, 打开(示例/文件/URL 同一条 _install_puzzle 路径)即自动载入
_p3 = g.Puzzle(3, 3)
_p3.fin = {"x": 0, "y": 1, "side": "L"}
_p3.fout = {"x": 2, "y": 1, "side": "R"}
app._install_puzzle(g.Puzzle.from_json(_p3.to_json()))
report("无存档: 打开后无解可选", app.solutions == [] and app._sol_from_archive is False)
g.archive_save_solution(_p3.to_json(), [[0, 1], [1, 1], [2, 1]], archive_path=g.ARCHIVE_FILE)
app._install_puzzle(g.Puzzle.from_json(_p3.to_json()))
report("存档解自动载入", len(app.solutions) == 1 and app._sol_from_archive is True
       and app.solutions[0] == [(0, 1), (1, 1), (2, 1)], app.solutions)
report("载入即可点「显示解」, 解计数标注存档", str(app.btn_show_sol.cget("state")) == "normal"
       and "存档" in app.sol_label.cget("text"), app.sol_label.cget("text"))
report("无做题线路时存档解直接显示", app.show_sol.get() is True
       and len(app.canvas.find_withtag("solpath")) >= 1,
       (app.show_sol.get(), len(app.canvas.find_withtag("solpath"))))
app.on_toggle_show_sol()
root.update()
report("存档解也可以隐藏", app.show_sol.get() is False
       and not app.canvas.find_withtag("solpath"))

# 求解询问: 存档解在手上时, 答「否」= 不求解; 答「是」= 重解并自动入档(覆盖旧解)
_ASK_CALLS.clear()


def _ask_no(title, message, *a, **k):
    _ASK_CALLS.append(str(message))
    return False


_orig = g.messagebox.askyesno
g.messagebox.askyesno = _ask_no
try:
    app.on_solve()
finally:
    g.messagebox.askyesno = _orig
report("求解询问答「否」: 弹了询问、不求解、保留存档解",
       len(_ASK_CALLS) == 1 and not app.solving and len(app.solutions) == 1
       and app._sol_from_archive is True and "保留存档解" in app.status.cget("text"),
       (_ASK_CALLS, app.solving, app.status.cget("text")))
# 答「是」用已知恰有一解的示例 01 (3x3 全白覆盖线路按奇偶性不存在, 不能拿来重解)
app.load_example_file(ex01)
report("重开存过解的示例: 再次自动载入", app._sol_from_archive is True and len(app.solutions) == 1)
app.solve_mode.set("unique")
app.on_solve()
pump()
report("求解询问答「是」: 重新求解且成功", len(app.solutions) == 1 and not app.solving,
       (len(app.solutions), app.status.cget("text")))
_rec2 = g.archive_lookup(app.puz.to_json(), path=g.ARCHIVE_FILE)
report("唯一解自动入档 (存档记录 = 本次解, source=icelom_gui)",
       _rec2 is not None and [list(pt) for pt in app.solutions[0]] == _rec2["path"]
       and _rec2.get("source") == "icelom_gui", _rec2)
report("重解后当前解不再标记为「来自存档」", app._sol_from_archive is False)
report("自动入档的状态栏有提示", "存档" in app.status.cget("text"), app.status.cget("text"))

# --- 测试 14c: 存档里留 Penpa+ 链接 / GUI 原生导出 + 配置窗的三种答案来源 ---
def _url_lines(url):
    """独立解回链接(不走 json2penpa 的 decompress): 题面文本各行 + 答案载荷。"""
    body = url.split("&p=", 1)[1]
    p_payload, _, a_payload = body.partition("&a=")
    text = zlib.decompress(base64.b64decode(p_payload), -15).decode("utf-8")
    for plain, short in reversed(JP.COMPRESS_SUB):
        text = text.replace(short, plain)
    ans = (json.loads(zlib.decompress(base64.b64decode(a_payload), -15).decode("utf-8"))
           if a_payload else None)
    return text.split("\n"), ans


_rec01 = g.archive_lookup(app.puz.to_json(), path=g.ARCHIVE_FILE)
# 入档时顺手生成的题面链接 = 现场重算(不留过期链接)
report("存档: 记录里带 Penpa+ 链接(题面 + 本题答案)",
       isinstance(_rec01.get("links"), dict)
       and _rec01["links"].get("puzzle") == JP.make_url(app.puz.to_json())
       and "&a=" in (_rec01["links"].get("answer") or ""), sorted(_rec01.get("links") or {}))
_lines, _ans = _url_lines(_rec01["links"]["answer"])
_want_ans = JP.answer_segments(app.puz.to_json(), app.solutions[0], JP.Board(9, 9))
report("存档: 带答案的链接开着精确判定、答案是本题的解、样式 = 页面认可的那一号",
       json.loads(_lines[7])["sol_loopline_exact"] is True
       and json.loads(_lines[7])["sol_loopline"] is False
       and {s.rsplit(",", 1)[0]: int(s.rsplit(",", 1)[1]) for s in _ans[1]} == _want_ans
       and all(s.endswith(",%d" % JP.ANSWER_STYLE) for s in _ans[1]),
       (_ans[1][:1], [k for k, v in json.loads(_lines[7]).items() if v]))

# 三种答案来源各导一条; 不带答案那条必须与题面链接逐字节相同
_u_none = app._penpa_link(key="none")
_u_cur = app._penpa_link(key="cur")
report("导出: 不带答案 = 存档里的题面链接(逐字节)",
       _url_lines(_u_none)[1] is None and _u_none == _rec01["links"]["puzzle"])
report("导出: 用本题当前的解", _url_lines(_u_cur)[1] is not None
       and _u_cur == _rec01["links"]["answer"])
report("导出: 判定口径只有一种(精确 + 样式 9), 与工具现算逐字节一致",
       _u_cur == JP.make_url(app.puz.to_json(), app.solutions[0])
       and all(s.endswith(",%d" % JP.ANSWER_STYLE) for s in _ans[1]))

# 手动绘制核验解: 进模式 → 盘面回到空题面 → 自己画 → 点「完成」出链接(不做规则判定)
report("导出: 默认答案来源 = 优先本题当前的解", app._prefer_answer_key() == "cur",
       app._prefer_answer_key())
_sol_before = list(app.solutions[0])
app._start_manual_answer()
report("手动绘制: 进入模式后盘面是空的(解与既有线路都清掉)",
       app._manual_active() and app.solutions == [] and not app.play_edges
       and app.mode.get() == "play", (app.solutions, app.play_edges, app.mode.get()))
report("手动绘制: 操作条出现、求解与两个导出按钮置灰",
       bool(app.bar_manual.winfo_manager())
       and str(app.btn_solve.cget("state")) == "disabled"
       and str(app.btn_export_penpa.cget("state")) == "disabled", app.bar_manual.winfo_manager())
_orig_showwarning = g.messagebox.showwarning
_warned = []
g.messagebox.showwarning = lambda *a, **k: _warned.append(a)
try:
    app._finish_manual_answer()
finally:
    g.messagebox.showwarning = _orig_showwarning
report("手动绘制: 空盘面点「完成」→ 提示先画线, 仍留在模式里",
       _warned and app._manual_active(), (_warned, app._manual_active()))

# 画一条"角尺"形(不追求是解): (0,0)-(1,0)-(1,1)-(2,1)
for _a, _b in (((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (2, 1))):
    app._play_press(*_a)
    app._play_step(_a, _b)
    app._play_motion(*_b)
_manual_path = app._path_from_play_edges()
report("手动绘制: 画出来的线段还原成一条逐格序列",
       _manual_path == [(0, 0), (1, 0), (1, 1), (2, 1)], _manual_path)
report("手动绘制: 中途不做规则判定(状态栏只说画了多少)",
       "手动绘制" in app.status.cget("text") and "手动绘制答案: 已画" in app.status.cget("text"),
       app.status.cget("text"))
_u_manual = app._penpa_link(key="manual", path=_manual_path)
_want_manual = JP.answer_segments(app.puz.to_json(), _manual_path, JP.Board(9, 9))
report("手动绘制: 那条线原样进链接(不验证、不必是解)",
       {s.rsplit(",", 1)[0]: int(s.rsplit(",", 1)[1]) for s in _url_lines(_u_manual)[1][1]}
       == _want_manual and len(_want_manual) >= 3, _want_manual)
report("手动绘制: 不写回存档(一次性草稿, 免得下次被当成这道题的解)",
       (g.archive_lookup(app.puz.to_json(), path=g.ARCHIVE_FILE) or {}).get("links", {})
       .get("answer") == _rec01["links"].get("answer"),
       sorted((g.archive_lookup(app.puz.to_json(), path=g.ARCHIVE_FILE) or {}).get("links") or {}))
report("手动绘制: 取消 → 丢线、退出模式、按钮恢复",
       app._cancel_manual_answer() is None and not app._manual_active()
       and not app.play_edges and not app.bar_manual.winfo_manager()
       and str(app.btn_export_penpa.cget("state")) == "normal")

# 画在**别的盘面尺寸**上也要按那个尺寸编码(手工线一样是逐格坐标)
_p5 = g.Puzzle.from_json(json.load(open(os.path.join(ROOT_DIR, "example", "03_入门5x5.json"),
                                        encoding="utf-8")))
_path5 = [(2, 0), (2, 1), (1, 1), (0, 1), (0, 0)]
_u5 = g.penpa_link(_p5.to_json(), _path5)
report("手动绘制: 换一道 5x5 题画线, 答案按 5x5 的盘面编码",
       {s.rsplit(",", 1)[0] for s in JP.url_answer(_u5)[1]}
       == set(JP.answer_segments(_p5.to_json(), _path5, JP.Board(5, 5))),
       sorted(JP.url_answer(_u5)[1])[:2])

# 题面还不能导出时要报人话(而不是抛 traceback)
app._install_puzzle(g.Puzzle(3, 3))         # 空白盘面: 没有 IN/OUT
try:
    app._penpa_link(key="none")
    _bad_msg = None
except Exception as _e:
    _bad_msg = str(_e)
report("导出: 缺 IN/OUT 的题面报人话", _bad_msg is not None and "IN/OUT" in _bad_msg, _bad_msg)
app.load_example_file(ex02)                 # 8x8 有 IN/OUT, 但先清掉解
app.solutions = []
app.sol_idx = -1
try:
    app._penpa_link(key="cur")
    _cur_msg = None
except Exception as _e:
    _cur_msg = str(_e)
report("导出: 没有解时「用当前的解」报人话", _cur_msg is not None and "解" in _cur_msg, _cur_msg)

# 推理预算: 默认 120 秒; 可手动输入; 非法输入回退默认; 越界收敛
report("推理预算: 默认 120 秒", app.build_solver_input()["limits"]["time_limit_ms"] == 120000,
       app.build_solver_input()["limits"])
app.sp_time.set("5")
report("推理预算: 手动输入 5 秒 → 5000ms",
       app.build_solver_input()["limits"]["time_limit_ms"] == 5000)
app.sp_time.set("abc")
report("推理预算: 非法输入回退默认并写回",
       app.build_solver_input()["limits"]["time_limit_ms"] == 120000
       and app.sp_time.get() == "120", app.sp_time.get())
app.sp_time.set("999999")
report("推理预算: 越界收敛到 86400 秒上限",
       app.build_solver_input()["limits"]["time_limit_ms"] == 86400000
       and app.sp_time.get() == "86400", app.sp_time.get())
app.sp_time.set("120")
report("求解把这次预算记进配置", any(k == "time_limit_s" and v == 120
                                     for k, v in _CFG_SET_CALLS), _CFG_SET_CALLS[-3:])

# --- 测试 15: 子进程静默启动 (Windows 不弹控制台黑窗) ---
# 界面由 pythonw/快捷方式启动时自身没有控制台, 拉起控制台程序
# (icelom_solver.exe / node / python) 会被 Windows **新开一个黑窗**。
# 所有子进程都必须带 CREATE_NO_WINDOW。
report("_no_console(): Windows 上给出 CREATE_NO_WINDOW",
       g._no_console() == ({"creationflags": g.subprocess.CREATE_NO_WINDOW}
                           if os.name == "nt" else {}), g._no_console())
import inspect  # noqa: E402  (只为本用例读取源码, 不参与运行路径)
_src = inspect.getsource(g.App.on_solve) + inspect.getsource(g.App.on_import_url) \
    + inspect.getsource(g.App._run_shortcut_tool)
report("三处子进程启动都带了 _no_console()", _src.count("_no_console()") == 3,
       _src.count("_no_console()"))

root.destroy()
print()
print("GUI LOGIC ALL PASS" if ok else "GUI LOGIC SOME FAILED")
sys.exit(0 if ok else 1)
