# analysis/ — 生成物目录（分析产物）

本目录里的东西**几乎全部是脚本生成的产物**，不是源码：

- **真值来源** = `benchmark/puzzles/` 里的题面 JSON + `tools/` 里的脚本；
- 这里的 JSON / TXT / PNG 都可以随时重生成，**不要手工编辑**，也不要当成"手工维护的数据"；
- 与他人分享结论时请给出**重生成命令**（见下表），而不是只给产物。

## 文件清单

| 文件 | 是什么 | 生成命令 |
| --- | --- | --- |
| `db039_solution.json` | **db039 的权威解**：171 格线路（`"cells": 171`）、17 个编号位次（`number_slots`）、4 个 "?" 格各自代表的数（`qmark_values`）、`"verify": "OK"`（`tests/verify.py` 独立验证器结论）、`source` 记录它来自"作者提示弱化版搜索" | `python tools/db039_hint_solve.py`（弱化版先得解）→ 解按原题坐标写回本文件 |
| `db039_report.txt` | 该解的人工核对报告：位次表（每次穿越代表的数字）、线路格子序列、ASCII 编号地图、独立验证器结论 | `python tools/db039_solution_report.py` |
| `db039_solution.png` | 该解的高保真渲染图（`icelom_render.py` 离屏渲染，Nikoli 纸面风格） | `python tools/render_solution.py benchmark/puzzles/db039_13x13_0vanillaice0.json analysis/db039_solution.json analysis/db039_solution.png` |
| `db039_deduce.json` | db039 的**推理状态**（`tools/deduce.py --out`）：`determined` = 推理唯一确定的边（**170 条 = 整条 171 格线路全推完**）、`possible` = 仍未排除的候选边（**0 条**）、`slots` = "?" 位次模型结论（4 个 "?" 必须各穿越两次、只能代表 2,4,…,16）、`cell_table` = 每格候选边数。给 GUI 叠加显示用（`--state`）。只用规则（`--no-probe`）时是 24 条确定（4 个 "?" 各一个十字 = 16 条 + 四个角 8 条） | `python tools/deduce.py benchmark/puzzles/db039_13x13_0vanillaice0.json --solution analysis/db039_solution.json --out analysis/db039_deduce.json` |
| `db039_deduce.png` | 上述推理状态的盘面图：粉线 = 推理确定要走的边（db039 上就是完整解），灰虚线 = 仍未排除的候选边 | `python tools/deduce_report.py benchmark/puzzles/db039_13x13_0vanillaice0.json --solution analysis/db039_solution.json --id db039 --png analysis/db039_deduce.png` |
| `db039_deduce_gui.png` | 同一状态在 **tkinter 界面里**的样子（GUI 的"推导状态"叠加层 + 状态栏），可与自己的手工推导逐格对照 | `python icelom_gui.py --state analysis/db039_deduce.json --shot analysis/db039_deduce_gui.png` |
| `deduce_audit.txt` | **推理器全量可靠性审计**（`tools/audit_deduce.py`）：65 道基准题逐题"求出真解 → 推不动点 → 核对确定边 ⊂ 真解、被排除边 ∩ 真解 = ∅、有解题不得报矛盾"，整条线路推完的题还会把线路还原出来交给独立验证器。当前结论：**0 题推错、0 题误禁、0 题假矛盾；33 题整条线路推完且验证通过** | `python tools/audit_deduce.py 8`（单题求解时限 8 s，全量约 20 s） |
| `audit_report.txt` | `tests/audit_benchmark.py` 的全量独立审计报告：65 题同时跑主求解器与独立走廊收缩模型、交叉核对"有解/无解"、逐解验证。出现 `*** DISAGREE ***` 才是必须查的问题；`skip` 行是独立模型的能力边界（冰质 OUT / 内部 IN-OUT 不支持），另有几题是独立模型侧超时。主求解器侧 65 题全部有解、逐解通过验证器（`disagrees=0 invalid_solutions=0`） | `python tests/audit_benchmark.py [单题时限秒]`（默认 60 s/题，全量约 3–5 min） |

## 关于 db039 的权威性

- `analysis/db039_solution.json` 是 **db039 的唯一权威解**：171 格线路、`verify.py` 判定 OK、
  编号位次恰为 `1,?(2),3,?(4),…,?(16),17`（"?" 格补齐偶数），
  并且用**未经修改的官方 pzprjs 引擎** end-to-end 判定为 **PASS**。
- 官方判定命令（复用已落盘的解，秒级返回）：

  ```
  python tools/official_check.py db039 analysis/db039_solution.json
  # -> 官方引擎判定: 画线边框数: 172  官方判定: PASS
  ```

  注意：`python tools/official_check.py db039`（不带解文件）会先用主求解器重新求解 ——
  db039 现在是**毫秒级纯推理出解**（0 分支节点），直接跑即可。
- 需要时重跑对应脚本即可再生成（`tools/official_check.py` 会把解写回 `analysis/<题目id>_solution.json`）。
- `db039_solution.png` / `db039_report.txt` 都只由上面的解与题面派生，没有独立信息。
- `db039_deduce.json` / `db039_deduce.png` / `db039_deduce_gui.png` 是**推理**的产物
  （不是求解结果）：它们回答"按规则 + 逐格逐方向试连推，能推到哪一步"。db039 的答案是：
  **整条 171 格线路被推完**（170 条确定边 / 142 条排除 / 0 条未定），
  与 `db039_solution.json` 逐边一致、通过独立验证器；只用规则时是 24 条确定
  （每个 "?" 冰格的十字 4 条 ×4 = 16 条，加四个角各 2 条 = 8 条）；"?" 的数字集合由计数推论
  唯一确定为 `2,4,6,8,10,12,14,16`（详见 [`../docs/算法说明.md`](../docs/算法说明.md) §3.11）。
  同一套机制在 db042（10×10）上同样把整条线路 84 条边**全部**推完。

## 一次性重生成全部内容

```
python tools/db039_hint_solve.py                                   # db039 的弱化版求解（不落盘中间产物时自行清理）
python tools/db039_solution_report.py                              # db039_report.txt（并把 qmark_values 写回解文件）
python tools/render_solution.py benchmark/puzzles/db039_13x13_0vanillaice0.json analysis/db039_solution.json analysis/db039_solution.png
python tools/deduce.py benchmark/puzzles/db039_13x13_0vanillaice0.json --solution analysis/db039_solution.json --out analysis/db039_deduce.json
python tools/deduce_report.py benchmark/puzzles/db039_13x13_0vanillaice0.json --solution analysis/db039_solution.json --id db039 --png analysis/db039_deduce.png
python tools/audit_deduce.py 8                                      # deduce_audit.txt（65 题可靠性审计，约 20 s）
python tests/audit_benchmark.py                                    # audit_report.txt（全量审计，较慢）
```

渲染那一步需要 Pillow；`audit_benchmark.py` 无额外依赖，但全量耗时为分钟级。
若只是复核结论，优先跑 `python tests/run_tests.py` 与
`python tests/solver_newapi_test.py`（后者默认用仓库根的 `icelom_solver.exe`）。
