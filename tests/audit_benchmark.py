# -*- coding: utf-8 -*-
"""benchmark 全量独立审计: 每题同时用
  ① 当前求解器 (枚举解 + 独立验证器核对每个解)
  ② 独立走廊收缩模型 (完全不同实现思路, 见 tests/indep_solver.py)
交叉核对"有解/无解"结论是否一致, 用于发现主求解器的完备性缺陷。

用法: python -X utf8 tests/audit_benchmark.py [单题时限秒]
输出: 控制台表格 + analysis/audit_report.txt
"""
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import verify
from indep_solver import solve as indep_solve

LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 60
SOLVER = os.path.join(ROOT, "icelom_solver.exe")
REPORT = os.path.join(ROOT, "analysis", "audit_report.txt")


def run_v2(puz):
    p = dict(puz)
    # 保留题面自带的 options(例如 symmetry_retry); 只覆盖求解上限与时限。
    opts = dict(p.get("options") or {})
    opts.setdefault("cover_all_whites", True)
    p["options"] = opts
    p["limits"] = {"max_solutions": 5000, "time_limit_ms": int(LIMIT * 1000)}
    r = subprocess.run([SOLVER], input=json.dumps(p).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=LIMIT + 120)
    sols, done = [], None
    for line in r.stdout.decode("utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o["type"] == "solution":
            sols.append(o)
        elif o["type"] == "done":
            done = o
    return sols, done


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "benchmark", "puzzles", "*.json")))
    rows, disagree = [], 0
    for i, fn in enumerate(files, 1):
        puz = json.load(open(fn, encoding="utf-8"))
        puz.setdefault("options", {})["cover_all_whites"] = True
        name = os.path.basename(fn)
        sols, done = run_v2(puz)
        bad = sum(1 for s in sols
                  if verify.check(puz, [tuple(t) for t in s["path"]], cover_all=True))
        indep_sol, indep_msg = indep_solve(puz, LIMIT)
        v2_has = done["count"] > 0
        indep_has = indep_sol is not None
        skipped = indep_msg is not None and ("unsupported" in indep_msg or "skipped" in indep_msg)
        if skipped:
            verdict = "skip"
        elif done.get("aborted"):
            verdict = "v2-timeout"
        elif indep_msg is not None and indep_msg.startswith("timeout"):
            verdict = "indep-timeout"
        elif v2_has == indep_has:
            verdict = "AGREE"
        else:
            verdict = "*** DISAGREE ***"
            disagree += 1
        rows.append((name, done["count"], bad, verdict, indep_msg or "solution-found", done["ms"]))
        print(f"[{i:2d}/{len(files)}] {name:44s} v2count={done['count']:<4d} bad={bad} indep={verdict}")
    print()
    print("=" * 90)
    for name, cnt, bad, verdict, msg, ms in rows:
        if verdict != "AGREE" or bad:
            print(f"{verdict:18s} {name:44s} v2count={cnt} bad={bad} indep={msg}")
    print(f"total={len(rows)} disagrees={disagree} invalid_solutions={sum(r[2] for r in rows)}")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(" | ".join(str(x) for x in r) + "\n")
    print("report  ->", os.path.relpath(REPORT, ROOT))
    return 0 if disagree == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
