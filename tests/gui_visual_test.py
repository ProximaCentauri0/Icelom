# -*- coding: utf-8 -*-
"""GUI 可视化测试: 编辑模式截图 / 求解截图 / 内部IN-OUT截图 / 做题模式截图 / 小窗口缩放。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk

import icelom_gui as g

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, "example")

root = tk.Tk()
app = g.App(root)
root.geometry("1100x760+60+40")


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


def shot(name):
    # 置顶窗口, 防止被其它窗口遮挡 (ImageGrab 按屏幕坐标抓取)
    root.attributes("-topmost", True)
    root.lift()
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    root.update_idletasks()
    root.update()
    time.sleep(0.6)                     # 等窗口管理器完成置顶
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(os.path.join(HERE, name))
    root.attributes("-topmost", False)
    print("saved", name, "root at", x, y)


# 1. 编辑模式: 经典 9x9 + 三种边标记
app.load_example_file(os.path.join(EX, "01_经典9x9.json"))
app._edge_from_cells(1, 2, 1, 1, "arrow")
app._edge_from_cells(4, 4, 5, 4, "seg")
app._edge_from_cells(5, 0, 5, 1, "wall")
root.update()
time.sleep(0.3)
shot("gui_shot_marks.png")
app.on_solve()
pump()
root.update()
time.sleep(0.3)
shot("gui_shot_solved.png")
print("marks solved:", len(app.solutions), "|", app.status.cget("text"))

# 2. 内部 IN/OUT 演示 (求解显示)
app.load_example_file(os.path.join(EX, "09_内部INOUT演示.json"))
app.on_solve()
pump()
root.update()
time.sleep(0.3)
shot("gui_shot_internal_inout.png")
print("internal solved:", len(app.solutions))

# 3. 角冰格 IN/OUT 演示
app.load_example_file(os.path.join(EX, "10_角冰格INOUT演示.json"))
root.update()
time.sleep(0.2)
shot("gui_shot_corner_inout.png")
app.on_solve()
pump()
root.update()
time.sleep(0.2)
shot("gui_shot_corner_solved.png")
print("corner solved:", len(app.solutions))

# 4. 做题模式: 画一段线路 (部分正确) + 从别处另起一段 (多段线段) + IN 处画出界外
app.load_example_file(os.path.join(EX, "02_博客8x8.json"))
app.mode.set("play")


def release():
    app.on_release(type("E", (), {"x": 0, "y": 0})())


f = app.puz.fin
if f.get("side"):
    dx, dy = g.DIRS[f["side"]]
    app._play_press(f["x"] + dx, f["y"] + dy)      # 从界外一格起笔 …
    app._play_motion(f["x"], f["y"])               # … 拖进 IN 格 …
    app._play_motion(f["x"] - dx, f["y"] - dy)     # … 再沿入界方向深入一格
    release()
    print("stub drawn over IN:", f, "|", app.status.cget("text"))
app._play_press(0, 1)
for xy in [(0, 2), (0, 3), (1, 3)]:
    app._play_motion(*xy)
release()
app._play_press(6, 6)                              # 另起一段 (多段作画)
app._play_motion(6, 7)
release()
root.update()
time.sleep(0.3)
shot("gui_shot_play.png")
print("play edges:", sorted(sorted(map(list, e)) for e in app.play_edges),
      "|", app.status.cget("text"))

# 5. 边做题边求解 → 显示解(只看答案) / 对照解 / 检查解 (抄解即完成, 绿色)
app.mode.set("edit")
app.solve_mode.set("unique")
app.on_solve()
pump()
print("solve-while-play:", len(app.solutions), "sols, show_sol =", app.show_sol.get())
root.update()
time.sleep(0.2)
shot("gui_shot_play_solving.png")
if app.solutions:
    app.mode.set("play")
    app.play_edges = g.path_to_edges(app.solutions[0])
    f = app.puz.fin
    if f.get("side"):
        dx, dy = g.DIRS[f["side"]]
        app.play_edges.add(frozenset({(f["x"], f["y"]), (f["x"] + dx, f["y"] + dy)}))
    f = app.puz.fout
    if f.get("side"):
        dx, dy = g.DIRS[f["side"]]
        app.play_edges.add(frozenset({(f["x"], f["y"]), (f["x"] + dx, f["y"] + dy)}))
    app._refresh_play_state()
    root.update()
    app.redraw()
    root.update()
    time.sleep(0.3)
    shot("gui_shot_play_complete.png")
    print("play complete:", app.status.cget("text"))
    app.on_check_rules()
    print("check rules:", app.status.cget("text"))
    app.on_check_solution()
    print("check solution:", app.status.cget("text"))
    app.mode.set("edit")
app.on_toggle_show_sol()
root.update()
time.sleep(0.2)
shot("gui_shot_play_showsol.png")
print("show solution toggled:", app.show_sol.get(),
      "| play items on canvas:", len(root.winfo_children()) and 1)

# 6. 大窗口: 盘面放大不设低上限 (旧版被 56px 卡住)
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
bw, bh = min(sw - 60, 1500), min(sh - 120, 1000)
root.geometry(f"{bw}x{bh}+20+20")
root.update()
time.sleep(0.3)
shot("gui_shot_large.png")
print("large window:", bw, "x", bh, "cs =", app.cs)
assert app.cs > 56, "大窗口下盘面应能超过旧 56px 上限"

# 7. 小窗口: 验证网格随窗口缩放并居中
root.geometry("680x460+60+40")
root.update()
time.sleep(0.3)
shot("gui_shot_small.png")
print("small window: cs =", app.cs,
      "| grid centered at", round(app.offx), round(app.offy))
assert app.cs < 40, "cs should shrink in a smaller window"

root.destroy()
print("VISUAL TEST DONE")
