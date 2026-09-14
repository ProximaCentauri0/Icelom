# -*- coding: utf-8 -*-
"""仓库一致性自检（不需要求解器跑题，秒级返回）。

检查项:
  1. 关键入口文件是否齐全（求解器/界面/渲染器/各目录 README/文档）；
  2. 二进制新鲜度: icelom_solver.exe 是否比 icelom_solver.cpp 旧；
  3. 文档里的**反引号路径引用**是否存在（防止文档指向已删除的文件）；
  4. 代码/脚本里是否残留硬编码绝对路径（D:\\code\\... / C:\\Users\\...）；
  5. 文本文件编码是否为 UTF-8（.ps1 例外: Windows PowerShell 5.1 需要 BOM）；
  6. vendor 的 pzprjs 引擎与解码器是否可用（不联网，只做 require 冒烟）。
用法: python -X utf8 tests/check_workspace.py
退出码: 0 = 全部通过(可能带 warning), 1 = 有 error
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

errors = []
warnings = []
notes = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


# ---------------------------------------------------------------- 1. 关键文件
REQUIRED = [
    "README.md", ".gitignore",
    "icelom_solver.cpp", "icelom_gui.py", "icelom_render.py", "build.py",
    "docs/算法说明.md", "docs/求解器协议.md", "docs/项目架构.md", "docs/测试与验证.md",
    "docs/资源与官方判别器.md",
    "tests/run_tests.py", "tests/verify.py", "tests/indep_solver.py", "tests/fuzz_diff.py",
    "tests/audit_benchmark.py", "tests/solver_newapi_test.py", "tests/gui_logic_test.py",
    "tests/gui_visual_test.py", "tests/check_engine_pzprjs.py", "tests/check_engine_examples.py",
    "tests/test_url_import.py", "tests/probe_rules.js", "tests/probe_qmark.js",
    "tests/engine_diff_probe.js", "tests/dump_cells_url.js",
    "tools/taskset.ps1", "tools/pzprurl2json.js", "tools/official_check.py",
    "tools/official_check.js", "tools/verify_solution.py",
    "tools/long_solve.py", "tools/render_solution.py", "tools/make_examples.py",
    "tools/make_icon.py", "tools/make_release.py", "tools/make_shortcut.py",
    "tools/build_concat.js", "tools/dump_cells.js", "tools/scan_marks.js",
    "tools/pzprjs/pzpr.concat.js", "tools/pzprjs/pzpr-variety/icebarn.js",
    "assets/icelom.ico", "assets/icon_puzzle.json",
    "benchmark/run_benchmark.py", "benchmark/manifest.json", "benchmark/results.json",
    "benchmark/REPORT.md", "benchmark/decode_all.js", "benchmark/db_icelom_raw.json",
    "example/README.md",
]

for rel in REQUIRED:
    if not os.path.exists(os.path.join(ROOT, rel)):
        err("缺少关键文件: " + rel)

n_puzzles = len([f for f in os.listdir(os.path.join(ROOT, "benchmark", "puzzles"))
                 if f.endswith(".json")])
n_examples = len([f for f in os.listdir(os.path.join(ROOT, "example"))
                  if f.endswith(".json")])
notes.append("基准题面 %d 道, 示例 %d 道" % (n_puzzles, n_examples))

# ---------------------------------------------------- 2. 二进制新鲜度 / 存在性
cpp = os.path.join(ROOT, "icelom_solver.cpp")
exe = os.path.join(ROOT, "icelom_solver.exe")
if not os.path.exists(exe):
    err("icelom_solver.exe 不存在 —— 先跑 tools/taskset.ps1 build")
elif os.path.getmtime(exe) < os.path.getmtime(cpp):
    err("icelom_solver.exe 比 icelom_solver.cpp 旧 —— 源码改过但没重编译")
else:
    notes.append("求解器二进制比源码新 ✓")

# --------------------------------------------------- 3. 文档里的路径引用是否悬空
DOCS = ["README.md"] + ["docs/" + f for f in os.listdir(os.path.join(ROOT, "docs"))
                         if f.endswith(".md")]
PATH_RE = re.compile(r"`([A-Za-z0-9_./\\\u4e00-\u9fff-]+\.(?:py|js|cpp|exe|json|md|png|txt|ps1))`")
# 文档里"有意提及但不在仓库里"的文件名：系统自带的解释器/编译器、
# 以及文档中作为示例或占位出现的名字（不是本仓库的文件）。
ALLOW = {"icelom.exe", "icelom.cpp", "icelom_solver_v1.cpp", "_solver_v1.exe",
         "icelom_solver_new.exe", "puzzle.json", "orig_paths.json", "gui_smoke.png",
         # 系统自带的解释器（文档里在讲"快捷方式的目标写什么", 不是本仓库的文件）
         "pythonw.exe", "python.exe", "g++.exe",
         "benchmark_run.log", "results.json", "package.json",
         "analyze_orig.py", "replicate_orig.py", "check_orig_paths.py", "compare_sets.py",
         "orig_traced.cpp", "orig_traced.exe", "orig_out.txt", "icebarn_src.js",
         "import6.json", "import8.json", "icelom4_grid.png", "zone_a.png", "zone_b.png",
         "pzpr.js", "icebarn.js", "_t.log", "_audit_report.txt",
         "candle.js", "node_modules/pzpr-canvas/dist/candle.js",
         "db039_solution_retry.json", "db039_solution_unaided.json", "db039_solution_weakened.json",
         "_exp_totals.py", "_exp_grid.py", "_exp_grid.json", "_exp_prune_scan.py", "_hist.py",
         "_mk_puzzle.py", "_rm_p1p2.py", "_run.py", "_slot_verify.py", "_bench_cmp.py",
         "_bench_qprobe0.json", "_bench_qprobe1.json", "_stats_none.txt", "_stats_antit.txt",
         "_tests_out.txt", "_db039_none.json", "_db039_anti-t.json", "_db039_flip-y.json",
         "_db039_rot270.json",
         "transform_matrix.json", "db039_weakened.json",
         "db034_10x7_pancakepuzzles_solution.json", "db039_13x13_0vanillaice0_solution.json",
         "db039_13x13_0vanillaice0_flip-y.json", "db039_方向敏感性分析.md",
         # 2026-09 被 official_check.js 方案取代的两个探针文件(见 §13)
         "probe_grid.js", "pzprjs_url.js",
         # 2026-09-18 清理轮删除的 db039 分析产物与专项脚本(见 §21,
         # 文档里作为"按需重生成"命令与历史记录提及, 文件本身不再保留)
         "db039_solution.json", "db039_report.txt", "db039_solution.png",
         "db039_deduce.json", "db039_deduce.png", "db039_deduce_gui.png",
         "deduce_audit.txt", "audit_report.txt",
         "db039_hint_solve.py", "db039_solution_report.py", "db039_unaided.py",
         "01_unsat.json",
         # 2026-09-21 清理轮删除的名字(见 历史与回归基线 §22,
         # 文档里作为"删除史/历史记录"提及, 文件本身不再保留)
         "improvement.md", "260920.json", "20260917.json", "20260918.json",
         "v1.0.0.md", "v1.0.1.md", "v1.0.2.md"}
# 全仓文件名索引（含子目录），文档里写裸文件名或目录/文件名简写都能命中
FILENAME_INDEX = set()
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "node_modules", ".git")]
    for fn in filenames:
        FILENAME_INDEX.add(fn.lower())

missing_refs = {}
for doc in DOCS:
    p = os.path.join(ROOT, doc)
    if not os.path.exists(p):
        continue
    text = open(p, encoding="utf-8").read()
    for m in PATH_RE.finditer(text):
        ref = m.group(1).replace("\\", "/").lstrip("./")
        base = os.path.basename(ref)
        if base.lower() in ALLOW or ref.startswith("...") or "<" in ref:
            continue
        if os.path.exists(os.path.join(ROOT, ref)) or base.lower() in FILENAME_INDEX:
            continue
        missing_refs.setdefault(ref, []).append(doc)
for ref, docs in sorted(missing_refs.items()):
    warn("文档引用了不存在的文件: %s (%s)" % (ref, ", ".join(sorted(set(docs)))))

# --------------------------------------------------- 4. 硬编码绝对路径
ABS_RE = re.compile(r"[A-Za-z]:\\\\(?:code|Users|projects)\\\\", re.IGNORECASE)
SELF = os.path.abspath(__file__)
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "node_modules", ".git")]
    for fn in filenames:
        if not fn.endswith((".py", ".js", ".ps1", ".cpp")):
            continue
        fp = os.path.join(dirpath, fn)
        if os.path.abspath(fp) == SELF:
            continue                      # 本检查脚本自身的规则描述里含示例路径
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if ABS_RE.search(line) and "ICELOM_GXX" not in line and "default" not in line:
                warn("硬编码绝对路径 %s:%d: %s" % (os.path.relpath(fp, ROOT), i, line.strip()[:90]))

# --------------------------------------------------- 5. 编码
# 约定: 文本文件一律 UTF-8（BOM 可有可无; `benchmark/README.md` 历史上带 BOM, 保留无害）;
#       `.ps1` **必须**带 BOM —— Windows PowerShell 5.1 会把无 BOM 的脚本按 GBK 解析而报语法错。
BOM_REQUIRED = {"tools/taskset.ps1"}
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "node_modules", ".git")]
    for fn in filenames:
        if not fn.endswith((".py", ".js", ".md", ".ps1", ".cpp", ".json", ".txt")):
            continue
        fp = os.path.join(dirpath, fn)
        rel = os.path.relpath(fp, ROOT).replace("\\", "/")
        if rel.startswith("tools/pzprjs/"):
            continue                      # vendored 第三方产物不检查
        raw = open(fp, "rb").read()
        has_bom = raw[:3] == b"\xef\xbb\xbf"
        try:
            raw.decode("utf-8")
            ok = True
        except UnicodeDecodeError:
            ok = False
        if not ok:
            err("不是合法 UTF-8: " + rel)
        elif not has_bom and rel in BOM_REQUIRED:
            err(".ps1 缺少 UTF-8 BOM（PowerShell 5.1 会按 GBK 解析而报错）: " + rel)

# --------------------------------------------------- 6. vendored 引擎可用性
import subprocess
pzpr = os.path.join(ROOT, "tools", "pzprjs", "pzpr.concat.js")
icebarn = os.path.join(ROOT, "tools", "pzprjs", "pzpr-variety", "icebarn.js")
if os.path.exists(pzpr) and os.path.exists(icebarn):
    code = ("const p=require(%r);p.classmgr.makeCustom(...require(%r));"
            "const z=new p.Puzzle();console.log('pzpr ok');" % (pzpr, icebarn))
    try:
        r = subprocess.run(["node", "-e", code], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        if b"pzpr ok" in r.stdout:
            notes.append("vendored pzprjs 引擎可加载 ✓")
        else:
            warn("vendor pzprjs 加载异常: " + r.stderr.decode("utf-8", "replace").strip()[:160])
    except FileNotFoundError:
        warn("找不到 node —— URL 导入与官方判定不可用")
    except subprocess.TimeoutExpired:
        warn("node 加载 pzprjs 超时")

# --------------------------------------------------- 输出
for n in notes:
    print("[ok]   " + n)
for w in warnings:
    print("[warn] " + w)
for e in errors:
    print("[ERR]  " + e)
print()
print("check_workspace: %d 个错误, %d 个警告" % (len(errors), len(warnings)))
return_code = 1 if errors else 0
sys.exit(return_code)
