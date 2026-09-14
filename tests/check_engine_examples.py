# -*- coding: utf-8 -*-
"""一致性检查: 规则引擎 (check_play_rules) vs 求解器答案 + 独立验证器 verify.py。

对 example/ 里的每道示例求解, 然后:
  1. 求解器答案必须通过独立验证器 verify.check;
  2. 同一答案 (线段化) 交给规则引擎必须判 complete;
  3. 额外补上 IN/OUT 出界短边后仍必须判 complete (出界线是可选装饰)。

用法: python tests/check_engine_examples.py
"""
import json
import os
import subprocess as sp
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import icelom_gui as g
import verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EX = os.path.join(ROOT, "example")


def main():
    fail = 0
    checked = 0
    for fn in sorted(os.listdir(EX)):
        if not fn.endswith(".json"):
            continue
        puz = g.Puzzle.from_json(json.load(open(os.path.join(EX, fn), encoding="utf-8")))
        q = puz.to_json()
        q["options"]["cover_all_whites"] = True
        q["limits"] = {"mode": "first", "time_limit_ms": 60000}
        r = sp.run([g.SOLVER], input=json.dumps(q).encode(),
                   stdout=sp.PIPE, stderr=sp.PIPE, timeout=120)
        lines = [l for l in r.stdout.decode("utf-8", "replace").strip().splitlines() if l]
        sols = [json.loads(l) for l in lines if json.loads(l).get("type") == "solution"]
        if not sols:
            print(f"[SKIP] {fn}: 无解 ({lines[-1][:80] if lines else 'no output'})")
            continue
        checked += 1
        path = [tuple(pt) for pt in sols[0]["path"]]
        v_errs = verify.check(json.loads(json.dumps(puz.to_json())), path)
        edges = g.path_to_edges(path)
        errs, inc, complete, route, redges = g.check_play_rules(puz, edges)
        stubs = set()
        for f in (puz.fin, puz.fout):
            if f.get("side"):
                dx, dy = g.DIRS[f["side"]]
                stubs.add(frozenset(((f["x"], f["y"]), (f["x"] + dx, f["y"] + dy))))
        errs2, inc2, complete2, _, _ = g.check_play_rules(puz, edges | stubs)
        ok = (not v_errs) and complete and not errs and not inc \
            and complete2 and not errs2 and not inc2
        if not ok:
            fail += 1
        print(f"[{'OK  ' if ok else 'FAIL'}] {fn}: verify={v_errs[:2]} "
              f"engine={complete} errs={errs[:2]} inc={inc[:2]} "
              f"stub_ok={complete2 and not errs2 and not inc2}")

    print(f"\n检查 {checked} 道示例: " +
          ("全部一致" if fail == 0 else f"{fail} 道不一致"))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
