# -*- coding: utf-8 -*-
"""**推导器可靠性全量审计**: 在整批真实题面上核对"试连接 + 路径检查"这套推理。

对每道题:
  1. 用 C++ 求解器求出**首解**(超时/无解则跳过, 记录原因);
  2. 用 `tools/deduce.py` 推到不动点(规则 + 逐格逐方向试连接, 可 `--no-probe` 对照);
  3. 逐条核对:
     * **没推错**: 每条"确定边"(USED)都必须出现在真解里;
     * **没推过头**: 每条"被排除边"(FORBID)都不许出现在真解里;
     * 传播不许在没有真解被驳回的前提下报矛盾(`alive=False` ⇒ 一定有问题, 因为该题有解)。
  4. 汇总成表, 写进 `analysis/deduce_audit.txt`。

用法:
    python -X utf8 tools/audit_deduce.py [单题时限秒] [--no-probe] [--limit N]
产物: `analysis/deduce_audit.txt`(报告) + stdout 表格。
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from deduce import (Board, Deduce, UNKNOWN, USED, FORBID,  # noqa: E402
                    path_to_edge_states, deduced_path)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify                                       # noqa: E402


def solve(puz, ms):
    p = json.loads(json.dumps(puz))
    p["options"] = {"cover_all_whites": True}
    p["limits"] = {"max_solutions": 1, "time_limit_ms": ms}
    t0 = time.time()
    r = subprocess.run([os.path.join(ROOT, "icelom_solver.exe")],
                       input=json.dumps(p).encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
    lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    sols = [json.loads(l) for l in lines if '"solution"' in l]
    done = [json.loads(l) for l in lines if '"done"' in l]
    dt = time.time() - t0
    if not sols:
        why = done[-1].get("reason", "超时/未出结论") if done else "无输出"
        return None, dt, why
    return [tuple(q) for q in sols[0]["path"]], dt, ""


def main():
    ap = argparse.ArgumentParser(description="推导器可靠性全量审计")
    ap.add_argument("time_limit", nargs="?", type=float, default=20.0, help="单题求解时限(秒)")
    ap.add_argument("--no-probe", action="store_true", help="只跑规则(对照)")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题(调试用)")
    args = ap.parse_args()

    pdir = os.path.join(ROOT, "benchmark", "puzzles")
    files = sorted(f for f in os.listdir(pdir) if f.endswith(".json"))
    if args.limit:
        files = files[:args.limit]

    out = []
    out.append("推导器可靠性审计: 规则%s + 逐格逐方向试连接" % ("" if not args.no_probe
                                                              else "(不启用, 对照用)"))
    out.append("单题求解时限 %.1f s; 判据: 确定边 ⊂ 真解, 被排除边 ∩ 真解 = ∅, 有解题不得报矛盾"
               % args.time_limit)
    out.append("")
    out.append("%-42s %6s %6s %6s %6s %6s  %s"
               % ("题面", "确定", "禁", "未定", "推错", "误禁", "结论"))
    out.append("-" * 100)
    bad = 0
    n_solved = n_skip = 0
    t_all = time.time()
    for f in files:
        puz = json.load(open(os.path.join(pdir, f), encoding="utf-8"))
        # 优先用手边已有的落盘解(难例 db039 求解器在题面朝向下搜不出来,
        # 但它的权威解在 analysis/db039_solution.json 里)
        pid = f.split("_")[0]
        cached = os.path.join(ROOT, "analysis", "%s_solution.json" % pid)
        if os.path.exists(cached):
            path = [tuple(q) for q in json.load(open(cached, encoding="utf-8"))["path"]]
            dt, why = 0.0, ""
            src = "(落盘解)"
        else:
            path, dt, why = solve(puz, int(args.time_limit * 1000))
            src = ""
        if path is None:
            n_skip += 1
            out.append("%-42s %s" % (f, "跳过(求解器: %s, %.1fs)" % (why, dt)))
            continue
        n_solved += 1
        b = Board(puz)
        b.build_stems()
        d = Deduce(b)
        d.fixpoint(probe=not args.no_probe)
        det = [e for e in range(len(b.edges)) if not b.edges[e]["frame"] and d.used[e] == USED]
        forb = [e for e in range(len(b.edges)) if not b.edges[e]["frame"] and d.used[e] == FORBID]
        und = [e for e in range(len(b.edges)) if not b.edges[e]["frame"] and d.used[e] == UNKNOWN]
        sol = path_to_edge_states(b, path)
        wrong = [b.edges[e]["key"] for e in det if e not in sol]
        over = [b.edges[e]["key"] for e in forb if e in sol]
        dead = (not d.alive)
        verdict = "OK"
        extra = ""
        if not und and not dead:
            # 整条线路都推完了: 还原成格子序列, 交给**独立验证器**核对
            p2 = deduced_path(b, d)
            errs = verify.check(puz, p2) if p2 else ["无法还原线路"]
            if errs:
                verdict = "*** 还原线路不合法 ***"
                bad += 1
                extra = "  独立验证器: %s" % (errs[:2],)
            else:
                extra = "  (整条线路推完, 独立验证器通过)"
        if wrong or over or dead:
            verdict = "*** 不可靠 ***"
            bad += 1
        out.append("%-42s %6d %6d %6d %6d %6d  %s%s"
                   % (f, len(det), len(forb), len(und), len(wrong), len(over),
                      verdict, extra + ("  " + src if src else "")))
        if wrong:
            out.append("      推错的边: %s" % (wrong[:6],))
        if over:
            out.append("      误禁的边: %s" % (over[:6],))
        if dead:
            out.append("      报了矛盾(但该题有解): %s"
                       % ([e[1] for e in d.events[-3:]],))

    out.append("-" * 100)
    out.append("共 %d 题: 拿到真解 %d 题(跳过 %d 题); 不可靠 %d 题; 总用时 %.1f s"
               % (len(files), n_solved, n_skip, bad, time.time() - t_all))
    text = "\n".join(out)
    print(text)
    dst = os.path.join(ROOT, "analysis", "deduce_audit.txt")
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print("\n报告: analysis/deduce_audit.txt")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
