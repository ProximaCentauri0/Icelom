# -*- coding: utf-8 -*-
"""Penpa+ 导出测试: `tools/json2penpa.py` 生成的链接必须能被解回原题面。

两道闸门：
1. **外部基准**：`example/README.md` 里留着 11 号题面（箭头方向回归题）**官方 Penpa+ 链接**，
   把本工具为同一道题生成的载荷与它逐元素比对（冰格/数字/箭头/描边/可用格清单/抬头几何）。
   那份载荷是 penpa-edit 自己产出的，等于"格式长什么样"的第三方判据。
2. **往返**：12 个示例逐个生成链接 → 用测试里独立写的解码（base64 → raw inflate → 反替换表）
   解回题面，再把点号反算回格坐标，与源 JSON 的冰格、数字、"?"、箭头、IN/OUT 一一对齐。
"""
import base64
import json
import os
import re
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import json2penpa as P  # noqa: E402

ok = True
# 措辞黑名单用转义写：文档口径要求「指向具体人员的词」在全仓自查里为空，
# 所以连测试里也不留这些字面量（黑名单见 AGENTS/文档口径那一节）。
FORBIDDEN = re.compile("\u7528\u6237|\u4f60|\u60a8|\u672c\u4eba|\u62a5\u969c")


def report(name, cond, detail=""):
    global ok
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  " + detail) if detail else ""))
    ok = ok and cond


def decode_url(url):
    """独立实现：base64 → raw deflate → 反替换表（替换表本身由第 1 道闸门校验）。"""
    payload = url.split("&p=", 1)[1].split("&a=")[0]      # 带答案的链接另有 a 参数
    text = zlib.decompress(base64.b64decode(payload), -15).decode("utf-8")
    for plain, short in reversed(P.COMPRESS_SUB):
        text = text.replace(short, plain)
    return text.split("\n")


def elements(pu, board):
    """载荷 → (冰格坐标集合, 数字{点号:值}, 文字{点号:值}, 箭头{点号:方向号})。"""
    nx0, S, off = board.nx0, board.S, board.off

    def cell_xy(pid):
        return (pid % nx0 - off, pid // nx0 - off)

    ice = {cell_xy(int(k)) for k in pu["surface"] if pu["surface"][k] == P.SURFACE_ICE}
    nums = {int(k): v[0] for k, v in pu["number"].items() if v[2] == "1"}
    texts = {int(k): v[0] for k, v in pu["number"].items() if v[2] != "1"}
    arrows = {int(k): v[0] for k, v in pu["symbol"].items()}
    return ice, nums, texts, arrows


# --- 1. 与官方 Penpa+ 链接（11 号题面的来源）逐元素比对 ----------------------
readme = open(os.path.join(ROOT, "example", "README.md"), encoding="utf-8").read()
m = re.search(r"https://swaroopg92\.github\.io/penpa-edit/\?m=solve&p=\S+", readme)
report("11 号题面的官方 Penpa+ 来源链接仍在 example/README.md 里", bool(m))
if m:
    puz11 = P.load_puzzle(os.path.join(ROOT, "example", "11_20260909_9x9.json"))
    ref_lines = decode_url(m.group(0))
    mine_lines = P.build_text(puz11).split("\n")
    ref_q, mine_q = json.loads(ref_lines[3]), json.loads(mine_lines[3])
    report("导出载荷与官方同为 19 行", len(ref_lines) == len(mine_lines) == 19)
    report("抬头棋盘几何一致（棋盘类型/宽高/格宽/朝向/画布/中心点）",
           ref_lines[0].split(",")[:15] == mine_lines[0].split(",")[:15],
           "官方 %s / 本工具 %s" % (",".join(ref_lines[0].split(",")[:4]),
                                    ",".join(mine_lines[0].split(",")[:4])))
    report("可用格清单（差分编码）一致", ref_lines[5] == mine_lines[5],
           "官方 %s / 本工具 %s" % (ref_lines[5][:24], mine_lines[5][:24]))
    report("pu_q 键集合一致", sorted(ref_q) == sorted(mine_q))
    report("冰格底色一致", ref_q["surface"] == mine_q["surface"],
           "官方 %d 项 / 本工具 %d 项" % (len(ref_q["surface"]), len(mine_q["surface"])))
    report("IN/OUT 文字位置一致", ref_q["number"] == mine_q["number"],
           "官方 %s / 本工具 %s" % (sorted(ref_q["number"]), sorted(mine_q["number"])))
    report("箭头位置与方向一致",
           {k: v[:2] for k, v in ref_q["symbol"].items()} ==
           {k: v[:2] for k, v in mine_q["symbol"].items()},
           "官方 %d 支 / 本工具 %d 支" % (len(ref_q["symbol"]), len(mine_q["symbol"])))
    report("冰道描边 + 题面外框一致", ref_q["lineE"] == mine_q["lineE"],
           "官方 %d 段 / 本工具 %d 段" % (len(ref_q["lineE"]), len(mine_q["lineE"])))
    report("墙/线段/角标不被误用",
           not any(ref_q[k] for k in ("wall", "line", "numberS")) and
           not any(mine_q[k] for k in ("wall", "line", "numberS")))

# --- 2. 全部示例的往返 ------------------------------------------------------
names = sorted(n for n in os.listdir(os.path.join(ROOT, "example")) if n.endswith(".json"))
report("示例目录至少 12 道题", len(names) >= 12, "%d 道" % len(names))
for name in names:
    puz = P.load_puzzle(os.path.join(ROOT, "example", name))
    w, h = int(puz["w"]), int(puz["h"])
    board = P.Board(w, h)
    lines = decode_url(P.make_url(puz))
    ice, nums, texts, arrows = elements(json.loads(lines[3]), board)

    want_ice = {(x, y) for y in range(h) for x in range(w)
                if puz["cells"][y * w + x] == "i"}
    want_num, want_text, want_arrow = {}, {}, {}
    want_seg, want_wall = set(), set()
    for item in puz.get("numbers") or []:
        n = int(item["n"])
        want_num[board.cell(int(item["x"]), int(item["y"]))] = "?" if n < 0 else n
    for item in puz.get("edges") or []:
        kind = item.get("kind", "segment")
        x, y, side = int(item["x"]), int(item["y"]), item["side"]
        a, b = board.edge_vertices(x, y, side)
        key = "%d,%d" % (min(a, b), max(a, b))
        if kind == "arrow":
            want_arrow[board.edge(x, y, side)] = P.ARROW_DIR[item["dir"]]
        elif kind == "segment":
            want_seg.add(key)
        elif kind == "wall":
            want_wall.add(key)
        else:
            report("非法标记类型 %r（%s）" % (kind, name), False)
    for key, label in (("in", "IN"), ("out", "OUT")):
        pos = puz[key]
        x, y, side = int(pos["x"]), int(pos["y"]), pos.get("side")
        if side in P.SIDES:
            want_text[board.outer_edge(x, y, side)] = label
            want_arrow[board.edge(x, y, side)] = P.ARROW_DIR[
                side if key == "out" else P.OPPOSITE[side]]
        else:
            want_text[board.cell(x, y)] = label

    rules = lines[0].split(",")[18]
    bad = FORBIDDEN.findall(rules)
    got_q = json.loads(lines[3])
    cond = (ice == want_ice and nums == want_num and texts == want_text
            and arrows == want_arrow
            and want_seg <= set(got_q["lineE"]) and want_wall <= set(got_q["wall"])
            and not bad and len(lines) == 19)
    detail = "冰格%d 数字%d 箭头%d 文字%d" % (len(ice), len(nums), len(arrows), len(texts))
    if not cond:
        detail += (" 差集: 冰%s 数字%s 文字%s 箭头%s 线段%s 墙%s 禁用词%s 段数%d"
                   % (want_ice ^ ice, set(want_num.items()) ^ set(nums.items()),
                      set(want_text.items()) ^ set(texts.items()),
                      set(want_arrow.items()) ^ set(arrows.items()),
                      want_seg - set(got_q["lineE"]), want_wall - set(got_q["wall"]),
                      bad, len(lines)))
    report("往返 %-24s %s" % (name, detail), cond)

# --- 3. 带答案的链接（`a` 参数：页面可以自动判定）-----------------------------
sys.path.insert(0, HERE)
import verify                                  # noqa: E402

for name in ("03_入门5x5.json", "01_经典9x9.json"):
    puz = P.load_puzzle(os.path.join(ROOT, "example", name))
    w, h = int(puz["w"]), int(puz["h"])
    board = P.Board(w, h)
    try:
        path = P.solve_puzzle(puz, time_limit_ms=30000)
    except Exception as exc:                   # 求解器缺失/超时都算环境问题，明确报出来
        report("答案 %-24s 求解" % name, False, str(exc))
        continue
    errs = verify.check(puz, [tuple(p) for p in path], cover_all=True)
    report("答案 %-24s 路径过独立验证器（%d 格）" % (name, len(path)), not errs, str(errs[:2]))

    url = P.make_url(puz, path)
    sol = P.url_answer(url)
    lines = decode_url(url)
    want = set()
    for a, b in zip(path, path[1:]):
        ids = sorted((board.cell(*a), board.cell(*b)))
        want.add("%d,%d" % (ids[0], ids[1]))
    stubs = set()
    for key in ("in", "out"):
        pos = puz[key]
        if pos.get("side") in P.SIDES:
            p0 = (int(pos["x"]), int(pos["y"]))
            # 用 `edge_cell`（画布外那一格）而不是 `cell(*neighbor(...))`：后者在下/右边界
            # 会把点号折回对侧，答案里就多一条横穿盘面的线（正是 board.neighbor 那个坑）。
            ids = sorted((board.cell(*p0), board.edge_cell(p0[0], p0[1], pos["side"])))
            stubs.add("%d,%d" % (ids[0], ids[1]))
    got = {s.rsplit(",", 1)[0] for s in sol[1]}
    checks = json.loads(lines[7])
    # 段表里出现的格：必须覆盖全部白格（含编号格），并含进出框那两个留白格
    cells = set()
    for s in sol[1]:
        a, b = (int(t) for t in s.split(",")[:2])
        cells.update((a, b))
    white = {board.cell(x, y) for y in range(h) for x in range(w)
             if puz["cells"][y * w + x] == "w"}
    stub_cells = {int(s.split(",")[1]) for s in stubs} | {int(s.split(",")[0]) for s in stubs}
    report("答案 %-24s 段表 = 路径段 + 进出框短边（%d 段）" % (name, len(sol[1])),
           got == want | stubs and len(sol[1]) == len(want | stubs))
    report("答案 %-24s 覆盖全部白格且含留白格" % name,
           white <= cells and stub_cells <= cells, "留白格 %s" % sorted(stub_cells))
    # 每条线段的两端点号必须**相邻**：先各自减去所在区段（`S0 = nx0*ny0` 的整数倍），
    # 再比"同区段内差 ±1（左右）/ ±nx0（上下）"（跨区段的边界格按环形邻接算）。
    # 差得离谱说明点号被公式折回了别的行/列（历史缺陷：从棋盘右边界往外走一步
    # 折成了左边缘那一格，答案里凭空多出一条横穿盘面的线）。
    S0 = board.nx0 * board.ny0

    def _adjacent(p, q):
        p, q = p % S0, q % S0                       # 只看第一节里的格点号
        d = abs(p - q)
        return d in (1, board.nx0) or (d + 1) % board.nx0 == 0

    _bad = [s for s in sol[1]
            if not _adjacent(*[int(t) for t in s.split(",")[:2]])]
    report("答案 %-24s 每条线段两端点号都相邻（没有折回对侧的假线段）" % name,
           not _bad, str(_bad[:3]))
    report("答案 %-24s 条目排序 + 答案样式 + 判定开关" % name,
           sol[1] == sorted(sol[1]) and all(s.endswith(",%d" % P.ANSWER_STYLE) for s in sol[1])
           and sol[0] == [] and sol[2:] == [[], [], [], []]
           and checks["sol_loopline_exact"] and not checks["sol_loopline"]
           and not any(checks[k] for k in checks if k not in ("sol_loopline_exact",)),
           "开关 %s" % [k for k, v in checks.items() if v])

# 答案样式号 = 页面里"用哪号笔才判得过"：本工具统一记 9（淡蓝）, 与上头 9 号风格一致。
# 判定是**逐字节比** `make_solution()` 与 `a` 载荷, 所以样式号写错页面就永远判不过
# （无头 Chrome 实测: 精确 + 9 → sol_flag 1; 松模式 + 1/3、精确 + 1/3 → 0）。
report("答案样式号 = %d（页面要用同号笔画才判得过）" % P.ANSWER_STYLE,
       P.ANSWER_STYLE == P.ANSWER_STYLE_EXACT == P.LINE_BLUE == 9,
       str((P.ANSWER_STYLE, P.ANSWER_STYLE_EXACT)))

# --- 4. 解存档: GUI 求出唯一解时自动写入, 生成链接时优先读它当答案 -----------------
import tempfile                                  # noqa: E402
sys.path.insert(0, ROOT)
import icelom_gui as G                           # noqa: E402  (只借 puzzle_key/存档函数, 不建 Tk)

_key_bad = []
for name in names:
    q = P.load_puzzle(os.path.join(ROOT, "example", name))
    if G.puzzle_key(q) != P.puzzle_key(q):
        _key_bad.append(name)
report("解存档键: 与 GUI 的 puzzle_key 全示例一致（%d 道）" % len(names), not _key_bad, _key_bad)

puz03 = P.load_puzzle(os.path.join(ROOT, "example", "03_入门5x5.json"))
try:
    path03 = P.solve_puzzle(puz03, time_limit_ms=30000)
except Exception as exc:                       # 求解器缺失/超时都算环境问题，明确报出来
    report("存档答案 03_入门5x5 求解", False, str(exc))
else:
    tmpdir = tempfile.mkdtemp(prefix="icelom_penpa_")
    arch = os.path.join(tmpdir, "solutions.json")
    report("存档: GUI 写入 → 工具按内容指纹读回同一条解",
           G.archive_save_solution(puz03, path03, archive_path=arch) is None
           and P.archive_solution(puz03, arch) == path03)
    board03 = P.Board(int(puz03["w"]), int(puz03["h"]))
    want03 = P.answer_segments(puz03, path03, board03)

    def _run(args, out):
        rc = P.main(args + ["--out", out])
        with open(out, encoding="utf-8") as fh:
            return rc, fh.read().strip()

    # 存档命中: 不带 --solve/--solution 也自动把存档解写成 a 答案
    rc, url_a = _run(["--archive", arch, os.path.join(ROOT, "example", "03_入门5x5.json")],
                     os.path.join(tmpdir, "a.txt"))
    sol_a = P.url_answer(url_a) if "&a=" in url_a else None
    got_a = ({s.rsplit(",", 1)[0]: int(s.rsplit(",", 1)[1]) for s in sol_a[1]}
             if sol_a else None)
    report("存档命中: 链接自动带答案, 段表与存档解一致", rc == 0 and sol_a is not None
           and got_a == want03, str((rc, None if got_a is None else len(got_a))))
    # --no-archive: 回到"无答案"的普通链接
    rc, url_b = _run(["--no-archive", os.path.join(ROOT, "example", "03_入门5x5.json")],
                     os.path.join(tmpdir, "b.txt"))
    report("--no-archive: 不读存档, 链接不带答案", rc == 0 and "&a=" not in url_b, rc)
    # 显式 --solution 优先级高于存档
    fake = os.path.join(tmpdir, "fake.json")
    with open(fake, "w", encoding="utf-8") as fh:
        json.dump({"path": [[0, 0], [1, 0]]}, fh)
    rc, url_c = _run(["--solution", fake, "--archive", arch,
                      os.path.join(ROOT, "example", "03_入门5x5.json")],
                     os.path.join(tmpdir, "c.txt"))
    sol_c = P.url_answer(url_c) if "&a=" in url_c else None
    want_c = P.answer_segments(puz03, [(0, 0), (1, 0)], board03)
    got_c = ({s.rsplit(",", 1)[0]: int(s.rsplit(",", 1)[1]) for s in sol_c[1]}
             if sol_c else None)
    report("--solution 优先于存档", rc == 0 and got_c == want_c,
           str((rc, "got=want" if got_c == want_c else "mismatch")))

print()
print("PENPA EXPORT ALL PASS" if ok else "PENPA EXPORT SOME FAILED")
sys.exit(0 if ok else 1)
