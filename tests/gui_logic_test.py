# -*- coding: utf-8 -*-
"""GUI 逻辑测试 (无头): 示例列表 / 求解模式 / 箭头交互 / IN-OUT / 撤销 / 做题校验 / URL导入。"""
import json
import os
import subprocess as sp
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk

import icelom_gui as g
import verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

# --- 测试 1b: IN/OUT 边框箭头几何 (关于框线镜像: 必须等长) ---
app.cs, app.offx, app.offy = 46, 46, 46
app.redraw()
root.update_idletasks()


def arrow_len(tag, side):
    xs, ys = [], []
    for it in app.canvas.find_withtag(tag):
        b = app.canvas.bbox(it)
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    if not xs:
        return None
    return (max(ys) - min(ys)) if side in ("U", "D") else (max(xs) - min(xs))


lin = arrow_len("inout_in", app.puz.fin["side"])
lout = arrow_len("inout_out", app.puz.fout["side"])
report("IN/OUT 箭头等长 (镜像对称)", lin is not None and lout is not None
       and abs(lin - lout) <= 2, (lin, lout, app.cs))
report("IN/OUT 箭头长度合理 (≈0.72cs+线宽)",
       all(v is not None and 0.6 * app.cs <= v <= 1.0 * app.cs for v in (lin, lout)),
       (lin, lout, app.cs))

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
