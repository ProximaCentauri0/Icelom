# IceLom 求解性能基准

用 **puzz.link 数据库**（[puzz.link/db](https://puzz.link/db/)）收录的真实 Icelom 题面
检验 `icelom_solver.exe` 的求解性能。所有题面均来自真实作者公开发布的谜题
（日文博客 / Twitter），经官方 pzprjs 库解码，可溯源。

## 题面收集

- 数据源：`https://puzz.link/db/api/pzvs_anon?type=in.("icelom")&generated=eq.false&tags_filter=not.cs.{broken}`
  （PostgREST 风格 API，匿名可读，`Prefer: count=exact` 返回总数）
- 共 **68 条**记录（2026-09 快照），剔除：
  - **3 条 `v:/` 变体模式**（非标准规则）→ `manifest.json` 记 `skipped_variant`。
- **65 条标准题**全部解码成功；其中 db034（2 个）与 db039（4 个）含 **"?" 格**
  （pzpr 的 `qnum <= -2`，即**数字未知的编号格**；用 `tools/scan_marks.js` 可复核统计），
  求解器按**位次规则**判定（见 README「规则 4」：编号格访问依次占位次，已知数字 `v`
  必须落在第 `v` 位；"?" 冰格允许被十字交叉穿越两次、两次可为两个不同的数）。
- 解码管线：`tools/pzprurl2json.js`（官方 pzprjs 库），与 GUI「导入 URL」完全一致；
  **数字保持题面原值**（跳号如 1,3,5,… 是题面信息的一部分，不再重编号）。

| 文件 | 说明 |
| --- | --- |
| `db_icelom_raw.json` | puzz.link/db API 原始记录（68 条，含来源/日期/URL） |
| `decode_all.js`      | 批量解码驱动：URL → `puzzles/*.json` + `manifest.json` |
| `puzzles/*.json`     | 65 个标准题面（icelom-v1 格式，可直接喂求解器） |
| `manifest.json`      | 题面清单：id、来源、原文链接、发表日期、尺寸、编号格/冰格/边标记数 |
| `run_benchmark.py`   | 基准工具：计时、解数、节点数、独立验证器核对、生成报告 |
| `compare_solver.py` | 两份二进制交替对照，覆盖单线程及指定线程数；独立验证完整解集 |
| `optimization_results.json` / `OPTIMIZATION.md` | 2026-09-20 单线程与并行优化的独立原始数据及报告，包含 65 道基准和两道 everyday 难题 |
| `results.json`       | 最近一次基准的完整明细（含各次重复计时）——**数字的唯一出处** |
| `REPORT.md`          | 汇总报告（总览表 / 与旧求解器对比 / 明细表 / 最难 10 题）——**数字的唯一出处** |
| `solutions/*.json`   | `tools/long_solve.py` 的产物：长时间/不限时单题求解一旦找到解就立即落盘（含 `label` / `transform` / `puzzle` / `path` / `cells` / `verify` / `elapsed_s`）；默认写本目录，可用第二个位置参数改写路径 |

> 曾经放在这里的 `benchmark_run.log` **已删除**：它是更早引擎的一次性运行日志，
> 内容与当前求解器无关，且与 `results.json` / `REPORT.md` 重复。要看耗时与结论请直接读那两份文件。

## 运行

```
python benchmark/run_benchmark.py --reps 3 --time-limit-ms 60000 --max-solutions 5000
python benchmark/run_benchmark.py --filter 14x14      # 只跑 id 含 14x14 的题
python benchmark/run_benchmark.py --report-only       # 不重新求解, 用现有 results.json 重写 REPORT.md
python tests/audit_benchmark.py                       # 65 题再用独立模型交叉核对(推荐定期跑)
```

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `--reps N` | 3 | 每题跑 N 遍，取**最优**墙钟作为该题成绩；注意首遍自带进程启动开销 |
| `--time-limit-ms MS` | 60000 | 单遍求解时限（传给求解器的 `limits.time_limit_ms`，即整次求解的时限） |
| `--max-solutions N` | 5000 | 解数量上限，达到即 `aborted`（状态记 `capped`） |
| `--filter 子串` | 无 | 只跑 id 含该子串的题（例如 `14x14`、`db039`） |
| `--report-only` | 关 | 不重新求解，直接用现有 `results.json` 重写 `REPORT.md` |

规则：官方规则（覆盖所有白格）；每题跑 `--reps` 遍取最优计时；
解数达到 `--max-solutions` 提前终止（记 `capped`）；单遍超时记 `timeout_*`。

**`symmetry_retry` 已是死开关**：求解器只有**一颗搜索树 + 一个确定性的分支选格**
（规则传播 + 单边试连接推到不动点，剩下的按两级打分选格：合法配置数最少优先、
平手看未定边邻居的平均配置数），不再有换扫描序/换朝向重试，
`run_benchmark.py` 也不再发送该选项。`--time-limit-ms` 就是整次求解的时限。

## 当前结果

**本节不复制数字**。权威且始终最新的成绩在由脚本生成的
[`REPORT.md`](REPORT.md) 与 [`results.json`](results.json) 里 —— 两者都由
`python benchmark/run_benchmark.py` 重新生成（`REPORT.md` 也可用 `--report-only` 从
`results.json` 重写），**机器/参数一变数字就变，手抄进 README 必然过期**。
需要引用具体数值时，请直接读这两份文件（或附上当时的运行命令与输出）。

以最近一次运行（`python benchmark/run_benchmark.py --reps 3 --time-limit-ms 60000
--max-solutions 5000`，即默认参数）为例说明**怎么看**：
`REPORT.md` 开头是总览（65 题分类计数 + 正常求解题的最快/中位/最慢墙钟），
中段是"与历史版本对比"（逐格 DFS 与路径段模型的数字是历史记录，不再重测），
后面是明细表（按耗时降序，前后各 25）与最难 10 题。

几条**不会随运行时间变化**的结论：

- **65 道标准题全部唯一解、0 超时**，且绝大多数题**一个搜索分支都没用**（`nodes = 0`，
  纯推理推完）；全部解都通过独立验证器 `tests/verify.py`，结论另有独立走廊收缩模型
  （`tests/indep_solver.py`）交叉核对。
- **db039**（13×13、23 冰、4 个 "?"、数字 1,3,…,17）的解已求得：
  171 格线路、位次恰为 `1,?(2),3,?(4),…,?(16),17`（"?" 补的正是 2,4,…,16），
  经官方 pzprjs 引擎判定 **PASS**（`python tools/official_check.py db039` 可现场重解并判定）。
  它与"把作者提示作为强制边"求得的解**逐格完全相同**（两条独立路径互证）。
  **它不再是难例**：任何朝向都是 0 分支节点、毫秒级出解（回归见 `tests/run_tests.py` T16）。
- 含 "?" 格的 **db034**（10×7、2 个 "?"）也解得唯一解，且官方引擎判定 PASS。

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `unique` | 恰有 1 解（出版题的预期形态） |
| `solved` | 多解，但全部枚举完成 |
| `capped` | 解数达到上限被截断 |
| `unsat`  | 搜索完整走完确认无解（**出现即需高度警惕**：先跑 `tests/audit_benchmark.py` 用独立模型复核。历史上曾因不可靠剪枝把 db042 误报无解） |
| `timeout_unsat` / `timeout_partial` | 触达时限：没找到解（可解性未知）/ 找到但未枚举完 |
| `error` / `no_done` / `invalid_solutions` | 求解器管线异常（bug 信号） |

每个找到的解都经过 `tests/verify.py`（独立实现的验证器）逐格核对。

## 数据来源致谢

题面版权归原作者所有，仅用于本地求解器性能测试。来源包括
bachelor seal、bakpao、ihnn puzzles、qpinemarch323、pancakepuzzles、
puzzleblog542、kiiroipazuru 等（完整列表见 `manifest.json` 的
`source_name` / `source_url` 字段）。
