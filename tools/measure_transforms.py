# -*- coding: utf-8 -*-
"""measure_transforms.py — 测量"盘面朝向/搜索序"对求解耗时的影响。

用法:
  # 单题: 各朝向各测一次首解耗时(默认 5 个常用朝向, --all-d4 测全 8 个)
  python tools/measure_transforms.py <谜题.json> [--all-d4] [--time-limit-ms MS]
         [--mode first|unique|all] [--solver 路径]

  # 全基准矩阵: 每题 × 每个朝向(8 个)的耗时"
  python tools/measure_transforms.py --benchmark-matrix [--filter db03] [--time-limit-ms 6000]

输出:
  - 单题模式: stdout 一张表(朝向 / 墙钟 ms / 求解器 ms / 节点数 / 是否找到解 / 是否到时限)
  - 矩阵模式: 逐题一行 + 汇总(每题最慢/最快比、各朝向总计), JSON 落盘
    analysis/transform_matrix.json（按需生成, 不入库）

用途: 当年它用来量"方向敏感性" —— 旧引擎(路径段并查集 + MRV 搜索)在 db039 上换个朝向
可以差 20 倍以上(flip-y 5.52M 节点出解, none/flip-x 60 s 内搜不出)。**那套机制已删除**
(现在是规则传播 + 试连接 + 固定顺序, 见 docs/算法说明.md §3.12), 当前引擎各朝向都是
毫秒级; 这个工具保留为**对照与排查手段**（怀疑"某朝向特别慢"时用它定位）。
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
from long_solve import transform  # noqa: E402

SOLVER = os.path.join(ROOT, "icelom_solver.exe")   # 可用 --solver 覆盖(实验副本)
# 朝向名 -> 基础变换的组合(基础变换都是自逆, 组合即"依次施加")
KIND_COMPOSE = {
    "none": [],
    "flip-x": ["flip-x"],
    "flip-y": ["flip-y"],
    "rot180": ["flip-x", "flip-y"],
    "transpose": ["transpose"],
    "rot90": ["transpose", "flip-x"],              # 顺时针 90° (= 求解器的 kind 5)
    "rot270": ["transpose", "flip-y"],             # 逆时针 90° (= kind 6)
    "anti-t": ["transpose", "flip-x", "flip-y"],   # 反对角镜像 (= kind 7)
}
COMMON = ["none", "flip-x", "flip-y", "rot180", "transpose"]
ALL_TRANSFORMS = list(KIND_COMPOSE)


def apply_kind(puz, name):
    for k in KIND_COMPOSE[name]:
        puz = transform(puz, k)
    return puz


def run_one(puz, kind, mode, time_limit_ms, solver):
    tpuz = apply_kind(puz, kind)
    tpuz.setdefault("options", {})["cover_all_whites"] = True
    tpuz["limits"] = {"mode": mode, "time_limit_ms": time_limit_ms}
    if mode == "first":
        tpuz["limits"]["max_solutions"] = 1
    data = json.dumps(tpuz, ensure_ascii=False).encode("utf-8")
    t0 = time.perf_counter()
    try:
        p = subprocess.run([solver], input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=time_limit_ms / 1000 + 30)
    except subprocess.TimeoutExpired:
        return None
    wall = (time.perf_counter() - t0) * 1000
    nsol, done, first_sol = 0, None, None
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "solution":
            nsol += 1
            if first_sol is None:
                first_sol = (time.perf_counter() - t0) * 1000
        elif obj.get("type") == "done":
            done = obj
    return {
        "transform": kind,
        "wall_ms": round(wall, 1),
        "first_sol_ms": round(first_sol, 1) if first_sol is not None else None,
        "solver_ms": done.get("ms") if done else None,
        "nodes": done.get("nodes") if done else None,
        "count": done.get("count") if done else None,
        "aborted": done.get("aborted") if done else None,
        "found": nsol > 0,
    }


def print_row(r):
    print(f"{r['transform']:<10} {r['wall_ms']:>10.1f} "
          f"{(r['first_sol_ms'] if r['first_sol_ms'] is not None else -1):>10.1f} "
          f"{(r['solver_ms'] if r['solver_ms'] is not None else -1):>10.1f} "
          f"{(r['nodes'] if r['nodes'] is not None else -1):>12} "
          f"{str(r['found']):>5} {str(r['aborted']):>7}", flush=True)


def single(args):
    with open(args.puzzle, encoding="utf-8") as f:
        puz = json.load(f)
    kinds = ALL_TRANSFORMS if args.all_d4 else COMMON
    print(f"{os.path.basename(args.puzzle)}: mode={args.mode} "
          f"limit={args.time_limit_ms}ms solver={os.path.basename(args.solver)}", flush=True)
    print(f"{'transform':<10} {'wall_ms':>10} {'首解ms':>10} {'求解ms':>10} "
          f"{'nodes':>12} {'found':>5} {'aborted':>7}", flush=True)
    for kind in kinds:
        r = run_one(puz, kind, args.mode, args.time_limit_ms, args.solver)
        if r is None:
            print(f"{kind:<10} {'(python 侧超时)':>10}")
        else:
            print_row(r)
    return 0


def benchmark_matrix(args):
    man = json.load(open(os.path.join(ROOT, "benchmark", "manifest.json"), encoding="utf-8"))
    entries = [e for e in man if e.get("decode") == "ok"]
    if args.filter:
        entries = [e for e in entries if args.filter in e["id"]]
    out = {}
    print(f"基准矩阵: {len(entries)} 题 × {len(ALL_TRANSFORMS)} 朝向, "
          f"limit={args.time_limit_ms}ms", flush=True)
    for i, e in enumerate(entries, 1):
        puz = json.load(open(os.path.join(ROOT, e["file"]), encoding="utf-8"))
        row = {}
        for k in ALL_TRANSFORMS:
            row[k] = run_one(puz, k, args.mode, args.time_limit_ms, args.solver)
        out[e["id"]] = row
        tm = " ".join(f"{k[:5]}={(row[k]['wall_ms'] if row[k] else -1):8.1f}"
                      for k in ALL_TRANSFORMS)
        print(f"[{i:>2}/{len(entries)}] {e['id']:<40} {tm}", flush=True)
    path = os.path.join(ROOT, "analysis", "transform_matrix.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n== 方向敏感度排行(最慢/最快 之比; 有未出解的朝向时按限时计) ==")
    rows = []
    for pid, row in out.items():
        ts = {k: (row[k] or {}).get("wall_ms", args.time_limit_ms) for k in ALL_TRANSFORMS}
        lo = max(min(ts.values()), 1e-9)
        rows.append((max(ts.values()) / lo, pid, ts))
    for ratio, pid, ts in sorted(rows, reverse=True)[:10]:
        print(f"{pid:<40} ratio={ratio:6.2f}  " +
              " ".join(f"{k[:5]}={ts[k]:7.0f}" for k in ALL_TRANSFORMS))
    print(f"\n== 各朝向总计 ==")
    for k in ALL_TRANSFORMS:
        tot = sum((out[p][k] or {}).get("wall_ms", args.time_limit_ms) for p in out)
        nf = sum(1 for p in out if (out[p][k] or {}).get("found"))
        print(f"{k:<10} 总计={tot:9.1f}ms 找到解={nf}/{len(out)}")
    print(f"\n矩阵已写入 {path}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle", nargs="?", help="单题模式: 谜题 JSON 路径")
    ap.add_argument("--benchmark-matrix", action="store_true",
                    help="矩阵模式: 对 benchmark/manifest.json 全部题 × 全部朝向测量")
    ap.add_argument("--filter", default=None, help="矩阵模式: 只跑 id 含该子串的题")
    ap.add_argument("--time-limit-ms", type=int, default=60000)
    ap.add_argument("--mode", default="first", choices=["first", "unique", "all"])
    ap.add_argument("--all-d4", action="store_true", help="单题模式: 测全部 8 个朝向")
    ap.add_argument("--solver", default=SOLVER, help="求解器路径(默认仓库根 icelom_solver.exe)")
    args = ap.parse_args()
    if args.benchmark_matrix:
        return benchmark_matrix(args)
    if not args.puzzle:
        ap.error("需要 <谜题.json> 或 --benchmark-matrix")
    return single(args)


if __name__ == "__main__":
    sys.exit(main())
