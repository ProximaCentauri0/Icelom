# -*- coding: utf-8 -*-
"""db039 原题(无提示)在新剪枝下的求解: 计数强制每个 "?" 都被交叉穿越两次。"""
import json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify

puz = json.load(open(os.path.join(ROOT, "benchmark", "puzzles",
                                  "db039_13x13_0vanillaice0.json"), encoding="utf-8"))
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
q = json.loads(json.dumps(puz))
q["options"] = {"cover_all_whites": True}
q["limits"] = {"max_solutions": 3, "time_limit_ms": int(secs * 1000)}
t0 = time.time()
r = subprocess.run([os.path.join(ROOT, "icelom_solver.exe")], input=json.dumps(q).encode(),
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
sols = [json.loads(l) for l in lines if '"solution"' in l]
for l in lines:
    if '"solution"' not in l:
        print(l[:200])
print(f"墙钟 {time.time()-t0:.1f}s  解数={len(sols)}")
for s in sols[:2]:
    path = [tuple(t) for t in s["path"]]
    errs = verify.check(puz, path, cover_all=True)
    print(f"  解#{s['index']}: {len(path)} 格 verify={'OK' if not errs else errs[:3]}")
    if not errs:
        outp = os.path.join(ROOT, "analysis", "db039_solution_unaided.json")
        json.dump({"path": s["path"], "cells": len(path), "verify": "OK"},
                  open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  已保存:", outp)
if r.stderr.strip():
    err = r.stderr.decode("utf-8", "replace").strip().splitlines()
    print("stderr 末行:", err[-1][:200])
