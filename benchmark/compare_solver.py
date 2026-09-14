"""Reproducible, alternating baseline/single/parallel measurements; never overwrites existing reports."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import verify


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, default=ROOT / "icelom_solver.exe")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4, 8])
    ap.add_argument("--puzzles", type=Path, nargs="+")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    puzzles = args.puzzles or (sorted((ROOT / "benchmark/puzzles").glob("*.json")) +
                               [ROOT / f"everyday_puzzle/202609{d}.json" for d in (15, 16)])
    result = dict(platform=platform.platform(), processor=platform.processor(), reps=args.reps, cases=[])
    result["executables"] = {
        name: dict(path=str(exe), sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
        for name, exe in (("baseline", args.baseline), ("candidate", args.candidate))
    }
    configs = [("baseline", args.baseline, 1)] + [(f"threads_{n}", args.candidate, n) for n in args.threads]
    for file in puzzles:
        p = json.loads(file.read_text(encoding="utf-8"))
        case = dict(puzzle=str(file.relative_to(ROOT) if file.is_absolute() else file), runs={})
        expected = None
        for rep in range(args.reps):
            # Reverse alternate rounds to reduce ordering / thermal bias.
            for label, exe, n in (configs if rep % 2 == 0 else configs[::-1]):
                p["limits"] = dict(mode="all", max_solutions=10000, time_limit_ms=120000, threads=n)
                start = time.perf_counter()
                r = subprocess.run([str(exe.resolve())], input=json.dumps(p), text=True,
                                   capture_output=True, timeout=140)
                wall = (time.perf_counter() - start) * 1000
                assert r.returncode == 0, r.stderr
                lines = [json.loads(line) for line in r.stdout.splitlines()]
                done = lines[-1]
                assert done["type"] == "done" and not done["aborted"], (file, label, done)
                paths = [tuple(map(tuple, x["path"])) for x in lines if x["type"] == "solution"]
                assert len(paths) == len(set(paths)) == done["count"]
                for path in paths:
                    assert not verify.check(p, path), (file, label)
                if expected is None:
                    expected = set(paths)
                assert set(paths) == expected, (file, label, "solution set mismatch")
                case["runs"].setdefault(label, []).append(dict(**done, wall_ms=round(wall, 3)))
        result["cases"].append(case)
        print(file.name, {k: round(statistics.median(r["ms"] for r in v), 1) for k, v in case["runs"].items()}, flush=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
