"""Differential regression for private search states, shared limits and cancellation.

python -X utf8 tests/parallel_solver_test.py [solver.exe]
"""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys

import verify

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "icelom_solver.exe"


def run(puzzle, threads, mode="all", cap=10000, ms=30000, exe=EXE):
    p = copy.deepcopy(puzzle)
    p["limits"] = dict(threads=threads, mode=mode, max_solutions=cap, time_limit_ms=ms)
    if threads == "default":
        del p["limits"]["threads"]
    proc = subprocess.run([str(exe)], input=json.dumps(p), text=True,
                          capture_output=True, timeout=ms / 1000 + 15)
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines()]
    assert lines and lines[-1]["type"] == "done", lines
    solutions = [line for line in lines if line["type"] == "solution"]
    assert [s["index"] for s in solutions] == list(range(len(solutions)))
    paths = [tuple(map(tuple, s["path"])) for s in solutions]
    assert len(set(paths)) == len(paths), "duplicate solution"
    for path in paths:
        assert not verify.check(p, path), (p, path, verify.check(p, path))
    return set(paths), lines[-1]


def base(w=4, h=4):
    return dict(w=w, h=h, cells=["w"] * (w * h), numbers=[], edges=[],
                **{"in": dict(x=0, y=0, side="U"),
                   "out": dict(x=w-1, y=h-1, side="D")},
                options=dict(cover_all_whites=False))


def main():
    rng = random.Random(20260920)
    puzzles = [base(), base(3, 3), base(1, 5), base(5, 1)]
    for _ in range(60):
        p = base(rng.randint(2, 4), rng.randint(2, 4))
        p["cells"] = [rng.choice(["w", "w", "i"]) for _ in p["cells"]]
        p["options"]["cover_all_whites"] = rng.choice([False, True])
        # Internal ice endpoints exercise direction variants and global caps.
        if rng.random() < .5:
            p["in"].pop("side")
        if rng.random() < .5:
            p["out"].pop("side")
        if rng.random() < .5:
            c = rng.randrange(len(p["cells"]))
            p["numbers"] = [dict(x=c % p["w"], y=c // p["w"], n=rng.choice([1, -2]))]
        if rng.random() < .5:
            p["edges"] = [dict(x=0, y=0, side="R", kind=rng.choice(["wall", "segment", "arrow"]), dir="R")]
        puzzles.append(p)
    for file in sorted((ROOT / "benchmark/puzzles").glob("*.json")):
        puzzles.append(json.loads(file.read_text(encoding="utf-8")))
    for i, p in enumerate(puzzles):
        expected, serial = run(p, 1)
        if len(sys.argv) > 2:
            original, original_done = run(p, 1, exe=Path(sys.argv[2]).resolve())
            assert not original_done["aborted"] and original == expected, (i, "baseline mismatch")
        assert not serial["aborted"], (i, serial)
        for threads in (2, 4, 0):
            actual, done = run(p, threads)
            assert not done["aborted"] and actual == expected, (i, threads, serial, done)
            assert done["count"] == len(expected), (i, threads, done)
        if len(expected) > 1:
            for threads in (1, 4):
                paths, done = run(p, threads, cap=2)
                assert len(paths) == done["count"] == 2 and done["aborted"], (i, threads, done)
                assert paths <= expected
        if i % 25 == 0:
            print(f"Matched complete solution sets: {i+1}/{len(puzzles)}", flush=True)
    # Stress concurrent publication/early stop; output count must never overshoot.
    for repeat in range(12):
        for mode, cap, count, aborted in (("first", 99, 1, False), ("unique", 99, 2, False),
                                          ("all", 1, 1, True), ("all", 7, 7, True)):
            paths, done = run(base(), 8, mode, cap)
            assert len(paths) == count and done["count"] == count and done["aborted"] == aborted, done
    for threads in (1, 2, 8, 0):
        for mode in ("unique", "all", "first"):
            _, done = run(base(7, 7), threads, mode, ms=1)
            assert done["aborted"] or (mode == "first" and done["count"] == 1) or (mode == "unique" and done["count"] == 2), done
    variants = base(3, 3)
    variants["cells"][4] = "i"
    variants["in"] = dict(x=1, y=1)
    # There are 14 paths across direction variants. The old remaining-vs-total
    # comparison stopped at 4 when asked for 5 or 7.
    for threads in (1, 2, 8, 64):
        for cap in (5, 7):
            paths, done = run(variants, threads, cap=cap)
            assert len(paths) == done["count"] == cap and done["aborted"], done
    for invalid in (-1, 65, 1.5, "4", True, None):
        p = base()
        p["limits"] = dict(threads=invalid)
        r = subprocess.run([str(EXE)], input=json.dumps(p), text=True, capture_output=True, timeout=5)
        assert json.loads(r.stdout)["type"] == "error", (invalid, r.stdout)
    print(f"PASS: {len(puzzles)} complete-set comparisons, concurrent caps, cancellation, invalid inputs")


if __name__ == "__main__":
    main()
