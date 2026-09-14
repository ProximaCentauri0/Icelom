# -*- coding: utf-8 -*-
"""verify_solution.py — 解一道 icelom-v1 题面，并用两层独立判据核对结论。

用法:
    python -X utf8 tools/verify_solution.py <题面.json> [解.json] [--limit-ms N] [--official] [--all]

    不给解文件时先用自己的求解器求解；给了就只核对这个解。
    --official  额外用**官方 pzprjs 引擎**判定（需要 Node.js；调用 tools/official_check.js）
    --all       求解时枚举全部解（否则只要第一个）

两层判据（互相独立）:
  1. `tools/verify.py`  —— 本项目**独立实现**的规则验证器（与 C++ 求解器无共享代码），
     逐格核对：白格覆盖 / 冰格直行 / 交叉 / 编号位次 / "?" 格 / 箭头 / 墙；
  2. `tools/official_check.js` —— **未经修改的官方 pzprjs 引擎** `check()`
     （第三方判据；官方规则里没有"墙"，带墙题面只由第 1 层把关）。

用法示例:
    python -X utf8 tools/verify_solution.py example/03_入门5x5.json --official
    python -X utf8 tools/verify_solution.py assets/icon_puzzle.json assets/icon_solution.json --official
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOLVER = os.path.join(ROOT, "icelom_solver.exe")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests"))

# 独立验证器: 开发仓库里在 tests/verify.py, 发布版里与它同目录(发布版没有 tests/)
try:
    import verify                      # noqa: E402
except ImportError:                    # pragma: no cover
    verify = None
if verify is None:
    raise SystemExit("找不到独立验证器 verify.py（应在 tests/ 或 tools/ 下）")


def solve(puz, limit_ms, want_all):
    q = dict(puz)
    q.pop("_note", None)
    q["options"] = {"cover_all_whites": True}
    q["limits"] = {"max_solutions": 5000 if want_all else 1, "time_limit_ms": limit_ms}
    r = subprocess.run([SOLVER], input=json.dumps(q).encode(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    sols, done = [], {}
    for l in lines:
        try:
            o = json.loads(l)
        except ValueError:
            continue
        if o.get("type") == "solution":
            sols.append(o["path"])
        elif o.get("type") == "done":
            done = o
    return sols, done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle")
    ap.add_argument("solution", nargs="?")
    ap.add_argument("--limit-ms", type=int, default=60000)
    ap.add_argument("--official", action="store_true", help="额外用官方 pzprjs 引擎判定")
    ap.add_argument("--all", action="store_true", help="求解时枚举全部解")
    args = ap.parse_args()

    if not os.path.exists(SOLVER):
        raise SystemExit("找不到求解器 %s（先跑 python build.py 编译）" % SOLVER)
    puz = json.load(open(args.puzzle, encoding="utf-8"))
    print("题面: %s  (%d×%d, 冰格 %d, 编号格 %d, 边标记 %d)"
          % (os.path.basename(args.puzzle), puz["w"], puz["h"],
             sum(1 for c in puz["cells"] if c == "i"), len(puz.get("numbers", [])),
             len(puz.get("edges", []))))

    if args.solution:
        raw = json.load(open(args.solution, encoding="utf-8"))
        paths = [raw if isinstance(raw, list) else raw["path"]]
        paths = [[(c[0], c[1]) for c in p] for p in paths]
        print("解来源: %s" % args.solution)
        done = {}
    else:
        sols, done = solve(puz, args.limit_ms, args.all)
        if not sols:
            extra = ("，原因: " + done["reason"]) if done.get("reason") else ""
            print("求解: 没有解%s  (%s)" % (extra, done or "无 done 输出"))
            return 1
        paths = [[(c[0], c[1]) for c in p] for p in sols]
        print("求解: 找到 %d 个解%s  (nodes=%s, ms=%s)"
              % (len(paths), "（已达上限/超时）" if done.get("aborted") else "",
                 done.get("nodes"), done.get("ms")))

    # ---- 判据 1: 独立验证器 ----
    ok = True
    for i, p in enumerate(paths):
        errs = verify.check(puz, p)
        tag = "OK" if not errs else "FAIL"
        print("  [%s] 解 #%d: %d 格  %s" % (tag, i, len(p), "" if not errs else errs[:4]))
        ok = ok and not errs

    # ---- 判据 2: 官方引擎 ----
    if args.official:
        js = os.path.join(HERE, "official_check.js")
        if not os.path.exists(js):
            print("  [跳过] 官方判定需要 tools/official_check.js")
        else:
            tmp = os.path.join(ROOT, "_verify_tmp_solution.json")
            json.dump({"path": paths[0]}, open(tmp, "w", encoding="utf-8"))
            try:
                r = subprocess.run(["node", js, args.puzzle, tmp], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
                for line in r.stdout.decode("utf-8", "replace").strip().splitlines():
                    print("  [官方] " + line)
                ok = ok and r.returncode == 0
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    print("\n结论: " + ("全部判据通过 ✓" if ok else "存在未通过的判据 ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
