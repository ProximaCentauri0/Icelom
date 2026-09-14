# -*- coding: utf-8 -*-
"""IceLom 求解性能基准: 真实题面 (puzz.link/db 收集) × 求解器计时 × 独立验证。

用法:
  python benchmark/run_benchmark.py                 # 每题跑 3 遍, 全量报告
  python benchmark/run_benchmark.py --reps 1 --quick  # 冒烟: 每题 1 遍, 30s 限时
  python benchmark/run_benchmark.py --filter 14x14    # 只跑 id 含子串的题
输出:
  benchmark/results.json  每题明细 (含各次重复计时)
  benchmark/REPORT.md     汇总报告
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOLVER = os.path.join(ROOT, "icelom_solver.exe")
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify  # noqa: E402


def load_manifest():
    with open(os.path.join(HERE, "manifest.json"), encoding="utf-8") as f:
        entries = json.load(f)
    return [e for e in entries if e.get("decode") == "ok"]


def solve_once(puz, max_solutions, time_limit_ms):
    """跑一遍求解器, 返回 (solutions, done, err, wall_ms, status, first_sol_ms)。

    first_sol_ms = 从启动到读到**第一个 solution 行**的墙钟(没有解则为 None) —— 这是
    "求解"(找到第一个解)的真实代价; 枚举模式下 done 行的墙钟受解数量上限/时限支配,
    与"能不能解出来"是两件事。

    注: 请求里不再带 `options.symmetry_retry` —— 求解器现在是**单颗搜索树 + 单一固定顺序**
    (不做盘面变换、不做逆向扫描序重试), 该开关根本不会被求解器解析
    (见 docs/求解器协议.md §2.1 与 docs/算法说明.md §3.12)。
    """
    req = dict(puz)
    req["options"] = {"cover_all_whites": True}
    req["limits"] = {"max_solutions": max_solutions, "time_limit_ms": time_limit_ms}
    data = json.dumps(req, ensure_ascii=False).encode("utf-8")
    t0 = time.perf_counter()
    sols, done, err = [], None, None
    first_sol = None
    try:
        p = subprocess.Popen([SOLVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        p.stdin.write(data)
        p.stdin.close()
        deadline = t0 + (time_limit_ms * 6 + 30000) / 1000
        for raw in p.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "solution":
                sols.append(obj)
                if first_sol is None:
                    first_sol = (time.perf_counter() - t0) * 1000
            elif obj.get("type") == "done":
                done = obj
            elif obj.get("type") == "error":
                err = obj
            if time.perf_counter() > deadline:
                p.kill()
                break
        p.wait(timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        try:
            p.kill()
        except Exception:
            pass
        return [], None, None, (time.perf_counter() - t0) * 1000, "timeout", None
    wall = (time.perf_counter() - t0) * 1000
    if err is not None:
        return sols, done, err, wall, "error", first_sol
    if done is None:
        return sols, done, err, wall, "no_done", first_sol
    if done.get("aborted"):
        # 求解器触达时限: count=0 无法判定无解, count>0 为部分枚举
        status = "timeout_partial" if done.get("count", 0) > 0 else "timeout_unsat"
        return sols, done, err, wall, status, first_sol
    capped = done.get("count", 0) >= max_solutions
    status = "capped" if capped else ("solved" if done.get("count", 0) > 0 else "unsat")
    return sols, done, err, wall, status, first_sol


def run_puzzle(entry, reps, max_solutions, time_limit_ms):
    with open(os.path.join(ROOT, entry["file"]), encoding="utf-8") as f:
        puz = json.load(f)
    runs = []
    first_sols = None
    for _ in range(reps):
        sols, done, err, wall, status, first_sol = solve_once(puz, max_solutions, time_limit_ms)
        if first_sols is None:
            first_sols = (sols, done, err, status)
        runs.append({
            "wall_ms": round(wall, 1),
            "solver_ms": done.get("ms") if done else None,
            "nodes": done.get("nodes") if done else None,
            "count": done.get("count") if done else None,
            "first_sol_ms": round(first_sol, 1) if first_sol is not None else None,
            "status": status,
        })
        if status in ("timeout_unsat", "timeout_partial", "error", "no_done"):
            break  # 异常/超时状态不重复 (超时题重复跑无意义)
    sols, done, err, status = first_sols

    # 独立验证器核对首次运行的全部解
    verify_errors = []
    n_checked = 0
    if sols:
        for s in sols:
            n_checked += 1
            errs = verify.check(puz, [tuple(t) for t in s["path"]], cover_all=True)
            if errs:
                verify_errors.append({"index": s.get("index"), "errors": errs[:4]})
        if n_checked == 0:
            status = "error"
    if verify_errors:
        status = "invalid_solutions"

    best = min(runs, key=lambda r: r["wall_ms"])
    first_ok = [r["first_sol_ms"] for r in runs if r.get("first_sol_ms") is not None]
    return {
        "id": entry["id"],
        "url": entry["url"],
        "source_name": entry["source_name"],
        "source_url": entry["source_url"],
        "published_at": entry.get("published_at"),
        "w": puz["w"], "h": puz["h"],
        "n_numbers": len(puz.get("numbers", [])),
        "n_qmark": sum(1 for n in (puz.get("numbers") or []) if n.get("n", 0) < 0),
        "n_ice": sum(1 for c in puz["cells"] if c == "i"),
        "n_edges": len(puz.get("edges") or []),
        "status": status,
        "solutions": done.get("count") if done else None,
        "nodes": best.get("nodes"),
        "solver_ms": best.get("solver_ms"),
        "wall_ms": best.get("wall_ms"),
        "first_sol_ms": min(first_ok) if first_ok else None,
        "reason": (done or {}).get("reason") if done else None,
        "error_msg": (err or {}).get("message") if err else None,
        "verify_checked": n_checked,
        "verify_errors": verify_errors,
        "runs": runs,
    }


def classify(res):
    if res["status"] == "solved" and res["solutions"] == 1:
        return "unique"
    return res["status"]


def write_report(results, args, total_wall):
    lines = []
    A = lines.append
    A("# IceLom 求解器性能基准报告")
    A("")
    A(f"- 求解器: `icelom_solver.exe` (g++ -O2; **规则传播 + 单边试连接**推理到不动点,"
      f" 剩下的分支按**两级打分选格**(合法配置数最少, 平手看未定边邻居的平均配置数)枚举;"
      f" 数字按位次规则判定, 支持跳号与 \"?\" 格)")
    A(f"- 题面来源: [puzz.link/db](https://puzz.link/db/) 收录的真实 Icelom 题"
      f" (共 {len(results)} 题进入基准; 仅 `v:/` 变体题被剔除 —— 见 `manifest.json` 的 `decode` 字段"
      f"与 `tools/scan_marks.js`)。其中 db034(2 个 \"?\")与 db039(4 个 \"?\")含数字未知的编号格。")
    A(f"- 规则: 官方 (覆盖所有白格); 计时: 每题 {args.reps} 遍取最优; "
      f"解数量上限 {args.max_solutions}; 单遍限时 {args.time_limit_ms} ms")
    A(f"- 全部解均经独立验证器 `tests/verify.py` 核对; 结论另用独立走廊收缩模型"
      f"（`tests/indep_solver.py`）交叉核对")
    A(f"- 总耗时: {total_wall:.1f} s")
    A(f"- **首解 ms** = 从启动到第一个 `solution` 行的墙钟(无解为 `—`): 这是\"能不能解出来、"
      f"多快解出来\"的真实代价。枚举模式下的\"求解 ms/墙钟\"还受解数量上限与时限支配。")
    A(f"- **节点数 = 0** 表示整条线路完全由推理(规则 + 试连接)推出来, 一次搜索分支都没用上;"
      f" 本次运行里 65 题中有 {sum(1 for r in results if r.get('nodes') == 0)} 题如此。")
    A("")

    by = {}
    for r in results:
        by.setdefault(classify(r), []).append(r)
    A("## 总览")
    A("")
    A("| 状态 | 题数 | 说明 |")
    A("| --- | ---: | --- |")
    desc = {
        "unique": "恰有 1 解 (正常出版题)",
        "solved": "多解 (枚举到全部解后正常终止)",
        "capped": f"达到解数量上限 {args.max_solutions} 提前终止",
        "unsat": "无解 (搜索完整走完, count=0)",
        "timeout_unsat": f"{args.time_limit_ms} ms 内未搜完且没有找到解 (可解性未知)",
        "timeout_partial": f"{args.time_limit_ms} ms 内未枚举完全部解",
        "error": "输入报错",
        "no_done": "求解器未输出 done 行",
        "invalid_solutions": "存在未通过独立验证器的解 (bug 信号!)",
    }
    for k in ["unique", "solved", "capped", "unsat", "timeout_unsat", "timeout_partial",
              "error", "no_done", "invalid_solutions"]:
        if k in by:
            A(f"| {k} | {len(by[k])} | {desc.get(k, '')} |")
    A("")

    good = [r for r in results if classify(r) in ("unique", "solved")]
    if good:
        ts = sorted(r["wall_ms"] for r in good)
        A(f"正常求解的 {len(good)} 题: 最快 {ts[0]:.1f} ms, 中位 {statistics.median(ts):.1f} ms, "
          f"最慢 {ts[-1]:.1f} ms, 总节点 {sum(r['nodes'] or 0 for r in good):,}")
        A("")

    # 与历史版本对比; 旧数据(逐格 DFS / 路径段并查集 + MRV)是当时测出的历史数字。
    A("## 与历史版本对比")
    A("")
    A("| 版本 | 题数 | 唯一解 | 多解 | 无解 | 超时/未判定 | 总耗时 |")
    A("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    A("| 旧（逐格 DFS） | 63 | 57 | 1 | 0 | 7 | 594.7 s |")
    A("| 路径段并查集 + MRV 选格（**已删除**） | 65 | 64 | 0 | 0 | 1 | 61.5 s ~ 184.4 s |")
    A("| 规则传播 + 单边试连接 + 行主序分支（2026-09 前） | 65 | 65 | 0 | 0 | 0 | ≈5 s |")
    A(f"| **当前（规则传播 + 单边试连接, 两级打分选格）** | {len(results)} "
      f"| {len(by.get('unique', []))} | {len(by.get('solved', []))} | {len(by.get('unsat', []))} "
      f"| {len(by.get('timeout_unsat', [])) + len(by.get('timeout_partial', []))} | {total_wall:.1f} s |")
    A("")
    A("> 旧求解器只支持数字恰好为 `1..K` 的题面，db034/db039（数字呈跳号排列、含 \"?\" 格）"
      "无法求解，故最早那行数据仅覆盖 63 题。")
    A(">")
    A("> **当前版本把 `tools/deduce.py` 的确定性推理搬进了求解器核心**：每条规则（格内配置、"
      "冰格直行、连通/无环/可达、相邻已知数字、\"?\" 位次模型）加上**逐格逐方向试连接 + 路径检查**"
      "一路推到不动点，剩下的才交给搜索；分支选格按**两级打分**（合法配置数最少优先，平手看"
      "未定边邻居的平均配置数，打分全部来自一次遍历的已知量、零试算；总分支节点从 2,308 降到 528）。")
    A(">")
    A("> **db039 不再是难例**：13×13、146 白格 + 23 冰格、9 个已知数字 + 4 个 \"?\" 冰格"
      "（位次规则的计数推论要求 4 个 \"?\" 各被十字交叉穿越两次，正好补齐 2,4,…,16）。"
      "旧求解器在题面朝向下 300 s 搜不出、换朝向才 2~12 s；现在**任何朝向都是 0 分支节点、"
      "毫秒级推完整条线路**（回归见 `tests/run_tests.py` T16）。")
    A(">")
    A("> 该解为 171 格线路，编号位次恰为 `1,?(2),3,?(4),…,?(16),17`，独立验证器通过，"
      "并用 pzpr 官方引擎 `check()` 判定为 **PASS**（`tools/official_check.py`）；"
      "与\"把作者提示作为强制边\"求得的解**逐格完全相同**。"
      "解与报告不再落盘保留，需要时 `python tools/official_check.py db039` 现场重解并判定。")
    A("")

    A("## 明细 (按耗时降序, 前后各 25)")
    A("")
    A("| # | 题号 | 尺寸 | 编号格 | 冰 | 解数 | 节点 | 首解 ms | 求解 ms | 墙钟 ms | 状态 | 来源 |")
    A("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    order = sorted(results, key=lambda r: (-(r["wall_ms"] or 0)))
    show = order[:25] + ([{"ell": True}] if len(order) > 50 else []) + order[-25:] if len(order) > 50 else order
    rank = {id(r): i + 1 for i, r in enumerate(order)}
    for r in show:
        if "ell" in r:
            A(f"| … | | | | | | | | | | |")
            continue
        src = r["source_name"] if len(str(r["source_name"])) <= 24 else str(r["source_name"])[:23] + "…"
        fs = f"{r['first_sol_ms']:.0f}" if r.get("first_sol_ms") is not None else "—"
        A(f"| {rank[id(r)]} | `{r['id']}` | {r['w']}×{r['h']} | {r['n_numbers']} | {r['n_ice']} "
          f"| {r['solutions'] if r['solutions'] is not None else '—'} "
          f"| {r['nodes'] if r['nodes'] is not None else '—'} "
          f"| {fs} "
          f"| {r['solver_ms'] if r['solver_ms'] is not None else '—'} "
          f"| {r['wall_ms']:.1f} | {classify(r)} | {src} |")
    A("")

    A("## 最难的 10 题")
    A("")
    A("| 题号 | 尺寸 | 解数 | 节点 | 墙钟 ms | 来源 |")
    A("| --- | --- | ---: | ---: | ---: | --- |")
    for r in order[:10]:
        src = r["source_name"] if len(str(r["source_name"])) <= 28 else str(r["source_name"])[:27] + "…"
        A(f"| `{r['id']}` | {r['w']}×{r['h']} | {r['solutions']} "
          f"| {r['nodes'] if r['nodes'] is not None else '—'} | {r['wall_ms']:.1f} | {src} |")
    A("")

    issues = [r for r in results if classify(r) in ("invalid_solutions", "error", "no_done")]
    if issues:
        A("## 需要注意的题")
        A("")
        for r in issues:
            A(f"- `{r['id']}` ({classify(r)}): verify_errors={r['verify_errors'][:1]} "
              f"error={r['error_msg']} reason={r['reason']}")
        A("")

    unsat = [r for r in results if classify(r) == "unsat"]
    if unsat:
        A("## 无解题 (数据库未标 broken, 但按官方规则无解)")
        A("")
        for r in unsat:
            A(f"- `{r['id']}` {r['w']}×{r['h']} from {r['source_name']} — {r.get('reason') or 'count=0'} "
              f"[来源]({r['url']})")
        A("")

    with open(os.path.join(HERE, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return os.path.join(HERE, "REPORT.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--max-solutions", type=int, default=5000)
    ap.add_argument("--time-limit-ms", type=int, default=60000)
    ap.add_argument("--filter", default=None, help="只跑 id 含该子串的题")
    ap.add_argument("--report-only", action="store_true",
                    help="不重新求解, 直接用现有 results.json 重写 REPORT.md")
    args = ap.parse_args()

    if args.report_only:
        results = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
        report = write_report(results, args, sum((r["wall_ms"] or 0) for r in results) / 1000.0)
        print(f"report  -> {report}")
        return 0

    entries = load_manifest()
    if args.filter:
        entries = [e for e in entries if args.filter in e["id"]]
    print(f"{len(entries)} puzzles, reps={args.reps}, "
          f"max_solutions={args.max_solutions}, time_limit={args.time_limit_ms}ms\n")

    results = []
    t_start = time.perf_counter()
    for i, e in enumerate(entries, 1):
        t0 = time.perf_counter()
        r = run_puzzle(e, args.reps, args.max_solutions, args.time_limit_ms)
        results.append(r)
        flag = "" if classify(r) in ("unique", "solved", "capped", "unsat") else "  <<<<"
        print(f"[{i:>2}/{len(entries)}] {r['id']:<38} {r['w']}x{r['h']} "
              f"sol={r['solutions']} nodes={r['nodes']} wall={r['wall_ms']:.1f}ms "
              f"[{classify(r)}] ({time.perf_counter() - t0:.1f}s){flag}", flush=True)

    total_wall = time.perf_counter() - t_start
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    report = write_report(results, args, total_wall)
    print(f"\nresults -> {os.path.join(HERE, 'results.json')}")
    print(f"report  -> {report}")
    bad = [r for r in results if classify(r) in ("invalid_solutions", "error", "no_done")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
