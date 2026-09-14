# everyday_puzzle/ — 每日题里的高难度样本

每日发布的 IceLom（アイスローム）题面中，对求解器压力最大的两道被留下来，
作为 65 题标准基准之外的**补充测量题**：

| 文件 | 盘面 | 特点 |
| --- | --- | --- |
| `20260915.json` | 25×7 | 3 个 `"?"` 格；旧版 `mode=unique` 需 30 万分支节点 / 约 1 分钟 |
| `20260916.json` | 17×13 | 87 个冰格、3 个 `"?"` 格；约束传播落地后仍是最耗时的一题 |

用途：

- [`benchmark/OPTIMIZATION.md`](../benchmark/OPTIMIZATION.md)（单线程与并行优化测量）
  以「65 道标准题 + 这两题」共 67 题为测量集，原始数据在
  [`benchmark/optimization_results.json`](../benchmark/optimization_results.json)；
- [`tests/adaptive_solver_test.py`](../tests/adaptive_solver_test.py) 用 `20260916.json`
  验证自适应线程策略（1 秒阈值后升到 8 线程）在难题上的行为；
- [`benchmark/compare_solver.py`](../benchmark/compare_solver.py) 默认加载这两题做新旧版本对照。

`20260915.txt` 是该题面的原始 Penpa+ 链接（出处留存）。题面版权归原题目作者，
本目录仅作求解器的测量输入（见 [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)）。
