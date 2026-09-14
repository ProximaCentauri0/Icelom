# -*- coding: utf-8 -*-
"""puzz.link URL 导入测试: 官方 pzprjs 解码 → JSON → 与已知答案比对 → 求解验证。"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import verify
from run_tests import solve

URL_TOOL = os.path.join(ROOT, "tools", "pzprurl2json.js")

ok = True


def report(name, cond, detail=""):
    global ok
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  " + detail) if detail else ""))
    ok = ok and cond


def decode(url):
    r = subprocess.run(["node", URL_TOOL, url], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=90)
    out = r.stdout.decode("utf-8", "replace").strip()
    return json.loads(out.splitlines()[-1])


# --- 8x8 博客题 ---
d8 = decode("https://puzz.link/p?icelom/a/8/8/4e40040c4g004i6r3k7k5w4i2g1q/0/15")
ice8 = {(i % 8, i // 8) for i, c in enumerate(d8["cells"]) if c == "i"}
nums8 = {(n["x"], n["y"]): n["n"] for n in d8["numbers"]}
exp_ice = {(2, 0), (6, 0), (7, 0), (0, 1), (4, 1), (3, 3), (4, 4), (5, 4), (5, 5), (2, 5), (6, 7)}
exp_nums = {(3, 0): 6, (0, 2): 3, (6, 2): 7, (4, 3): 5, (6, 5): 4, (4, 6): 1, (2, 6): 2}
report("URL导入 8x8 冰格与转录一致", ice8 == exp_ice)
report("URL导入 8x8 数字与转录一致", nums8 == exp_nums)
report("URL导入 8x8 IN/OUT", d8["in"] == {"x": 0, "y": 0, "side": "U"}
       and d8["out"] == {"x": 7, "y": 7, "side": "D"})

sols, done, err, _ = solve(d8, cover_all=True)
report("URL导入 8x8 求解 = 1 解", err is None and done and done["count"] == 1,
       f"count={done['count'] if done else '?'}")
if sols:
    errs = verify.check(d8, [tuple(t) for t in sols[0]["path"]], cover_all=True)
    report("URL导入 8x8 解通过验证器", not errs, str(errs[:3]))

# --- 6x6 pzprjs 官方测试题 ---
d6 = decode("https://puzz.link/p?icelom/a/6/6/9e50an10i3zl2g1i/15/4")
ice6 = {(i % 6, i // 6) for i, c in enumerate(d6["cells"]) if c == "i"}
nums6 = {(n["x"], n["y"]): n["n"] for n in d6["numbers"]}
exp_ice6 = {(1, 0), (4, 0), (0, 1), (1, 1), (2, 1), (0, 2), (2, 2), (3, 3), (5, 3),
            (1, 4), (3, 4), (4, 4), (5, 4), (4, 5)}
exp_nums6 = {(3, 0): 3, (0, 5): 2, (2, 5): 1}
report("URL导入 6x6 冰格与官方测试一致", ice6 == exp_ice6)
report("URL导入 6x6 数字与官方测试一致", nums6 == exp_nums6)
report("URL导入 6x6 IN/OUT", d6["in"] == {"x": 0, "y": 3, "side": "L"}
       and d6["out"] == {"x": 4, "y": 0, "side": "U"})
# 注: 该 6x6 是 pzprjs 官方 debug 库的 open/失败样例测试 URL, 本身不可解
# (经 pzprjs check() 探针验证: 起终点冰格必须直行, 该题无论 in/out 方向都无覆盖解)。

# --- 含 "?" 格的真题 (pzpr 的 qnum=-2: 格子确定是白/冰, 只是数字未知) ---
# db034: 10x7, 2 个 "?" 格(白格) + 已知数字 1,3,4,5,6,7,8; 数字呈跳号排列。
d34 = decode("https://puzz.link/p?icelom/a/10/7/007g4g4m7g0000z.h35n17t8k4h.n6h/24/7")
nums34 = {(n["x"], n["y"]): n["n"] for n in d34["numbers"]}
known34 = {k: v for k, v in nums34.items() if v > 0}
q34 = [k for k, v in nums34.items() if v < 0]
report("URL导入 db034 \"?\" 格解析为 n=-2", len(q34) == 2 and all(nums34[k] == -2 for k in q34),
       f"qmark={sorted(q34)}")
report("URL导入 db034 已知数字保持原值(不重编号)",
       sorted(known34.values()) == [1, 3, 4, 5, 6, 7, 8], f"known={sorted(known34.values())}")
sols34, done34, err34, _ = solve(d34, cover_all=True)
report("URL导入 db034 求解 = 1 解", err34 is None and done34 and done34["count"] == 1,
       f"count={done34['count'] if done34 else '?'} ms={done34['ms'] if done34 else '?'}")
if sols34:
    errs = verify.check(d34, [tuple(t) for t in sols34[0]["path"]], cover_all=True)
    report("URL导入 db034 解通过验证器(含 \"?\" 填数判定)", not errs, str(errs[:3]))

print()
print("URL IMPORT ALL PASS" if ok else "URL IMPORT SOME FAILED")
sys.exit(0 if ok else 1)
