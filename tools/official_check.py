# -*- coding: utf-8 -*-
"""用 pzprjs 官方引擎判定解是否被接受(端到端官方规则核对)。

用法: python tools/official_check.py <题目id前缀> [解JSON] [时限秒]
  - 不给解文件时先用本求解器求解; 解会被规范化成 {"path": ...} 再交给官方引擎。
  - 判定链路: benchmark/puzzles/<id>.json + manifest 里的 URL
              → tests/probe_qmark.js 用**未经修改的官方 pzprjs 引擎** check()
              → 打印 PASS 或官方报出的 failcode。
"""
import json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUZDIR = os.path.join(ROOT, "benchmark", "puzzles")


def load_manifest():
    m = json.load(open(os.path.join(ROOT, "benchmark", "manifest.json"), encoding="utf-8"))
    entries = m["entries"] if isinstance(m, dict) and "entries" in m else m
    return {e["id"]: e for e in entries}


def main():
    key = sys.argv[1]
    solfile = sys.argv[2] if len(sys.argv) > 2 else None
    secs = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    man = load_manifest()
    ids = [i for i in man if key in i]
    if not ids:
        raise SystemExit("找不到题目: " + key)
    pid = ids[0]
    url = man[pid]["url"]
    puzfile = os.path.join(PUZDIR, pid + ".json")
    print("题目:", pid, "\nURL:", url)
    if solfile is None:
        puz = json.load(open(puzfile, encoding="utf-8"))
        # 求解器是单颗搜索树 + 单一固定顺序(见 docs/算法说明.md §3.12), 没有需要打开的开关。
        puz["options"] = {"cover_all_whites": True}
        puz["limits"] = {"max_solutions": 1, "time_limit_ms": int(secs * 1000)}
        t0 = time.time()
        r = subprocess.run([os.path.join(ROOT, "icelom_solver.exe")],
                           input=json.dumps(puz).encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
        lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
        sols = [json.loads(l) for l in lines if '"solution"' in l]
        print("求解:", lines[-1][:120] if lines else "?", f"wall={time.time()-t0:.1f}s")
        if not sols:
            raise SystemExit("没有解, 无法做官方核对")
        solfile = os.path.join(ROOT, "analysis", pid + "_solution.json")
        os.makedirs(os.path.dirname(solfile), exist_ok=True)
        json.dump({"path": sols[0]["path"], "cells": len(sols[0]["path"])},
                  open(solfile, "w", encoding="utf-8"), ensure_ascii=False)
    print("解文件:", solfile)
    out = subprocess.run(["node", os.path.join(ROOT, "tests", "probe_qmark.js"), url, solfile],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("官方引擎判定:", out.stdout.decode("utf-8", "replace").strip())


if __name__ == "__main__":
    main()
