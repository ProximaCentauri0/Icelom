"""Real-clock regression: unfinished solves switch from 1 to 8 threads at 1 s.

python -X utf8 tests/adaptive_solver_test.py [solver.exe]
"""
import json

from parallel_solver_test import ROOT, base, run


def main():
    easy = base(3, 3)
    for threads in ("default", 0):
        for mode, cap in (("first", 100), ("unique", 100), ("all", 1), ("all", 100)):
            expected, serial = run(easy, 1, mode, cap)
            paths, done = run(easy, threads, mode, cap)
            assert paths == expected and done["count"] == serial["count"], done
            assert done["aborted"] == serial["aborted"], done
            assert done["threads"] == 1 and "parallel_after_ms" not in done, done
    print("PASS: easy puzzles retain serial ordering and all three mode semantics", flush=True)

    hard = json.loads((ROOT / "everyday_puzzle/20260916.json").read_text(encoding="utf-8"))
    expected, reference = run(hard, 8)
    assert not reference["aborted"] and len(expected) == 1, reference
    for threads, mode in (("default", "first"), ("default", "unique"),
                          ("default", "all"), (0, "unique")):
        paths, done = run(hard, threads, mode)
        assert paths == expected and done["count"] == 1 and not done["aborted"], done
        assert done["threads"] == 8 and 1000 <= done["parallel_after_ms"] < done["ms"], done
        if mode != "first":
            assert done["nodes"] == reference["nodes"], (reference, done)
        print(f"PASS: {threads}/{mode}: {done}", flush=True)

    paths, done = run(hard, "default", "all", cap=1)
    assert paths == expected and done["count"] == 1 and done["aborted"], done
    assert done["threads"] == 8 and done["parallel_after_ms"] >= 1000, done
    print("PASS: all-mode cap remains global after promotion", flush=True)

    for ms, expected_threads in ((200, 1), (1300, 8)):
        paths, done = run(hard, 0, "unique", ms=ms)
        assert done["aborted"] and done["threads"] == expected_threads, done
        assert done["count"] == (2 if paths else 0), done
        assert ("parallel_after_ms" in done) == (expected_threads == 8), done
    print("PASS: timeout before/after promotion preserves the original shared deadline", flush=True)

    # This board yields solutions immediately but cannot finish enumeration in
    # one second. Promotion must still happen AFTER output has already started.
    many = base(6, 6)
    prefix, first = run(many, 1, cap=8)
    assert first["ms"] < 1000 and len(prefix) == 8, first
    paths, done = run(many, "default", cap=1000000, ms=1300)
    assert done["aborted"] and done["threads"] == 8, done
    assert 1000 <= done["parallel_after_ms"] < done["ms"], done
    assert prefix < paths and done["count"] == len(paths), done
    # run() additionally checks consecutive indices, no duplicate paths, and
    # independently validates every solution, including the serial prefix.
    print(f"PASS: promotion after emitting solutions: {done}", flush=True)
    _, done = run(hard, 1, "unique", ms=1300)
    assert done["aborted"] and done["threads"] == 1 and "parallel_after_ms" not in done, done
    print("ADAPTIVE SOLVER ALL PASS")


if __name__ == "__main__":
    main()
