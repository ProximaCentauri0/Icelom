# IceLom 求解器性能基准报告

- 求解器: `icelom_solver.exe` (g++ -O2; **规则传播 + 单边试连接**推理到不动点, 剩下的分支按**行主序固定顺序**枚举; 数字按位次规则判定, 支持跳号与 "?" 格)
- 题面来源: [puzz.link/db](https://puzz.link/db/) 收录的真实 Icelom 题 (共 65 题进入基准; 仅 `v:/` 变体题被剔除 —— 见 `manifest.json` 的 `decode` 字段与 `tools/scan_marks.js`)。其中 db034(2 个 "?")与 db039(4 个 "?")含数字未知的编号格。
- 规则: 官方 (覆盖所有白格); 计时: 每题 3 遍取最优; 解数量上限 5000; 单遍限时 60000 ms
- 全部解均经独立验证器 `tests/verify.py` 核对; 结论另用独立走廊收缩模型（`tests/indep_solver.py`）交叉核对
- 总耗时: 1.6 s
- **首解 ms** = 从启动到第一个 `solution` 行的墙钟(无解为 `—`): 这是"能不能解出来、多快解出来"的真实代价。枚举模式下的"求解 ms/墙钟"还受解数量上限与时限支配。
- **节点数 = 0** 表示整条线路完全由推理(规则 + 试连接)推出来, 一次搜索分支都没用上; 本次运行里 65 题中有 35 题如此。

## 总览

| 状态 | 题数 | 说明 |
| --- | ---: | --- |
| unique | 65 | 恰有 1 解 (正常出版题) |

正常求解的 65 题: 最快 19.2 ms, 中位 21.1 ms, 最慢 226.1 ms, 总节点 2,308

## 与历史版本对比

| 版本 | 题数 | 唯一解 | 多解 | 无解 | 超时/未判定 | 总耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 旧（逐格 DFS） | 63 | 57 | 1 | 0 | 7 | 594.7 s |
| 路径段并查集 + MRV 选格（**已删除**） | 65 | 64 | 0 | 0 | 1 | 61.5 s ~ 184.4 s |
| **当前（规则传播 + 单边试连接, 固定顺序枚举）** | 65 | 65 | 0 | 0 | 0 | 1.6 s |

> 旧求解器只支持数字恰好为 `1..K` 的题面，db034/db039（数字呈跳号排列、含 "?" 格）无法求解，故最早那行数据仅覆盖 63 题。
>
> **当前版本把 `tools/deduce.py` 的确定性推理搬进了求解器核心**：每条规则（格内配置、冰格直行、连通/无环/可达、相邻已知数字、"?" 位次模型）加上**逐格逐方向试连接 + 路径检查**一路推到不动点，剩下的才交给搜索；分支顺序是**行主序固定顺序**（不做 MRV 选格、不换扫描序/换朝向重试）。
>
> **db039 不再是难例**：13×13、146 白格 + 23 冰格、9 个已知数字 + 4 个 "?" 冰格（位次规则的计数推论要求 4 个 "?" 各被十字交叉穿越两次，正好补齐 2,4,…,16）。旧求解器在题面朝向下 300 s 搜不出、换朝向才 2~12 s；现在**任何朝向都是 0 分支节点、毫秒级推完整条线路**（回归见 `tests/run_tests.py` T16）。
>
> 该解为 171 格线路，编号位次恰为 `1,?(2),3,?(4),…,?(16),17`，独立验证器通过，并用 pzpr 官方引擎 `check()` 判定为 **PASS**（`tools/official_check.py`）；与"把作者提示作为强制边"求得的解**逐格完全相同**。产物见 `analysis/db039_solution.json`、`analysis/db039_solution.png`、`analysis/db039_report.txt`。

## 明细 (按耗时降序, 前后各 25)

| # | 题号 | 尺寸 | 编号格 | 冰 | 解数 | 节点 | 首解 ms | 求解 ms | 墙钟 ms | 状态 | 来源 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `db048_11x9_ihnnpuzzles` | 11×9 | 10 | 22 | 1 | 2092 | 121 | 206.1 | 226.1 | unique | ihnnpuzzles |
| 2 | `db019_10x10_bakpao-puz` | 10×10 | 12 | 32 | 1 | 43 | 20 | 9.6 | 29.1 | unique | bakpao_puz |
| 3 | `db049_9x9_tckmn` | 9×9 | 10 | 10 | 1 | 66 | 24 | 8.3 | 28.3 | unique | tckmn |
| 4 | `db039_13x13_0vanillaice0` | 13×13 | 13 | 23 | 1 | 0 | 22 | 3.0 | 24.7 | unique | 0vanillaice0 |
| 5 | `db060_9x9_kiiroipazuru-blog-fc2-com` | 9×9 | 10 | 32 | 1 | 4 | 20 | 1.0 | 23.5 | unique | http://kiiroipazuru.blo… |
| 6 | `db016_9x9_dj-puzzles` | 9×9 | 10 | 9 | 1 | 20 | 21 | 2.0 | 23.4 | unique | dj-puzzles |
| 7 | `db056_9x13_0vanillaice0` | 9×13 | 10 | 44 | 1 | 9 | 20 | 3.0 | 22.8 | unique | 0vanillaice0 |
| 8 | `db003_9x8_bachelor-seal` | 9×8 | 7 | 15 | 1 | 0 | 20 | 0.0 | 22.5 | unique | bachelor seal |
| 9 | `db035_8x8_bakpao-puz` | 8×8 | 6 | 20 | 1 | 10 | 20 | 1.0 | 22.3 | unique | bakpao_puz |
| 10 | `db022_4x6_atraingrooveryy` | 4×6 | 0 | 14 | 1 | 0 | 20 | 0.0 | 22.2 | unique | AtrainGrooverYY |
| 11 | `db065_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 9 | 18 | 1 | 2 | 20 | 1.0 | 22.2 | unique | http://puzzleblog542.bl… |
| 12 | `db001_9x9_bachelor-seal` | 9×9 | 5 | 16 | 1 | 1 | 20 | 0.0 | 22.0 | unique | bachelor seal |
| 13 | `db015_8x8_bachelor-seal` | 8×8 | 7 | 26 | 1 | 0 | 20 | 0.0 | 22.0 | unique | bachelor seal |
| 14 | `db008_8x8_bachelor-seal` | 8×8 | 5 | 22 | 1 | 1 | 20 | 1.0 | 21.9 | unique | bachelor seal |
| 15 | `db018_9x4_takmu53` | 9×4 | 0 | 15 | 1 | 0 | 18 | 0.0 | 21.9 | unique | takmu53 |
| 16 | `db023_6x7_udop` | 6×7 | 0 | 21 | 1 | 0 | 20 | 1.0 | 21.9 | unique | udoP_ |
| 17 | `db037_12x13_bakpao-puz` | 12×13 | 15 | 68 | 1 | 2 | 19 | 1.0 | 21.9 | unique | bakpao_puz |
| 18 | `db010_8x8_bachelor-seal` | 8×8 | 5 | 19 | 1 | 0 | 19 | 0.0 | 21.7 | unique | bachelor seal |
| 19 | `db021_12x4_pawakun` | 12×4 | 0 | 21 | 1 | 0 | 20 | 0.0 | 21.7 | unique | pawakun |
| 20 | `db045_14x14_nu-n-notami` | 14×14 | 2 | 61 | 1 | 6 | 19 | 1.0 | 21.7 | unique | nu_n_notami |
| 21 | `db068_6x6_puzzleblog542-blog-fc2-com` | 6×6 | 3 | 6 | 1 | 0 | 20 | 0.0 | 21.7 | unique | http://puzzleblog542.bl… |
| 22 | `db004_8x8_bachelor-seal` | 8×8 | 5 | 13 | 1 | 0 | 20 | 0.0 | 21.6 | unique | bachelor seal |
| 23 | `db017_5x7_ericfox53` | 5×7 | 0 | 17 | 1 | 0 | 18 | 0.0 | 21.6 | unique | EricFox53 |
| 24 | `db011_8x8_bachelor-seal` | 8×8 | 5 | 20 | 1 | 0 | 18 | 0.0 | 21.5 | unique | bachelor seal |
| 25 | `db002_8x8_bachelor-seal` | 8×8 | 6 | 14 | 1 | 1 | 20 | 0.0 | 21.4 | unique | bachelor seal |
| … | | | | | | | | | | |
| 41 | `db014_8x8_bachelor-seal` | 8×8 | 6 | 9 | 1 | 0 | 19 | 0.0 | 20.7 | unique | bachelor seal |
| 42 | `db052_6x6_qpinemarch323` | 6×6 | 6 | 9 | 1 | 0 | 19 | 0.0 | 20.7 | unique | qpinemarch323 |
| 43 | `db029_11x11_menderbug` | 11×11 | 4 | 60 | 1 | 2 | 19 | 1.0 | 20.6 | unique | menderbug |
| 44 | `db040_6x6_qpinemarch323` | 6×6 | 4 | 12 | 1 | 0 | 19 | 0.0 | 20.5 | unique | qpinemarch323 |
| 45 | `db026_10x6_chebunanntoka` | 10×6 | 0 | 32 | 1 | 0 | 19 | 0.0 | 20.4 | unique | chebunanntoka |
| 46 | `db032_6x6_ericfox53` | 6×6 | 4 | 8 | 1 | 0 | 18 | 0.0 | 20.4 | unique | EricFox53 |
| 47 | `db013_8x8_bachelor-seal` | 8×8 | 7 | 18 | 1 | 0 | 19 | 0.0 | 20.3 | unique | bachelor seal |
| 48 | `db033_8x8_bakpao-puz` | 8×8 | 7 | 19 | 1 | 3 | 18 | 1.5 | 20.3 | unique | bakpao_puz |
| 49 | `db041_6x6_qpinemarch323` | 6×6 | 4 | 9 | 1 | 0 | 19 | 0.0 | 20.3 | unique | qpinemarch323 |
| 50 | `db058_8x8_hotatenohontate` | 8×8 | 8 | 28 | 1 | 0 | 19 | 1.0 | 20.3 | unique | hotatenohontate |
| 51 | `db034_10x7_pancakepuzzles` | 10×7 | 9 | 14 | 1 | 3 | 18 | 1.0 | 20.2 | unique | pancakepuzzles |
| 52 | `db031_6x6_jonnjonn69` | 6×6 | 5 | 8 | 1 | 2 | 18 | 0.0 | 20.1 | unique | jonnjonn69 |
| 53 | `db053_5x5_qpinemarch323` | 5×5 | 5 | 7 | 1 | 0 | 17 | 0.0 | 20.1 | unique | qpinemarch323 |
| 54 | `db062_6x6_kiiroipazuru-blog-fc2-com` | 6×6 | 4 | 10 | 1 | 0 | 18 | 0.0 | 20.1 | unique | http://kiiroipazuru.blo… |
| 55 | `db025_10x4_chebunanntoka` | 10×4 | 0 | 18 | 1 | 0 | 18 | 1.0 | 20.0 | unique | chebunanntoka |
| 56 | `db046_6x6_ihnnpuzzles` | 6×6 | 4 | 6 | 1 | 2 | 18 | 0.5 | 20.0 | unique | ihnnpuzzles |
| 57 | `db059_8x8_usbe-puz` | 8×8 | 7 | 23 | 1 | 3 | 18 | 1.0 | 20.0 | unique | USBe_puz |
| 58 | `db067_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 5 | 20 | 1 | 4 | 18 | 1.0 | 20.0 | unique | http://puzzleblog542.bl… |
| 59 | `db024_4x6_chebunanntoka` | 4×6 | 0 | 8 | 1 | 0 | 18 | 0.0 | 19.7 | unique | chebunanntoka |
| 60 | `db030_7x7_takmu73` | 7×7 | 5 | 11 | 1 | 2 | 18 | 1.0 | 19.6 | unique | takmu73 |
| 61 | `db061_6x6_kiiroipazuru-blog-fc2-com` | 6×6 | 0 | 16 | 1 | 0 | 18 | 0.0 | 19.6 | unique | http://kiiroipazuru.blo… |
| 62 | `db055_6x6_daikichi-3141` | 6×6 | 5 | 18 | 1 | 0 | 18 | 1.0 | 19.4 | unique | Daikichi_3141 |
| 63 | `db063_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 5 | 0 | 1 | 0 | 18 | 0.0 | 19.4 | unique | http://puzzleblog542.bl… |
| 64 | `db054_8x8_potechi1104` | 8×8 | 8 | 19 | 1 | 0 | 18 | 0.0 | 19.3 | unique | potechi1104 |
| 65 | `db028_19x5_pancakepuzzles` | 19×5 | 0 | 49 | 1 | 1 | 18 | 0.0 | 19.2 | unique | pancakepuzzles |

## 最难的 10 题

| 题号 | 尺寸 | 解数 | 节点 | 墙钟 ms | 来源 |
| --- | --- | ---: | ---: | ---: | --- |
| `db048_11x9_ihnnpuzzles` | 11×9 | 1 | 2092 | 226.1 | ihnnpuzzles |
| `db019_10x10_bakpao-puz` | 10×10 | 1 | 43 | 29.1 | bakpao_puz |
| `db049_9x9_tckmn` | 9×9 | 1 | 66 | 28.3 | tckmn |
| `db039_13x13_0vanillaice0` | 13×13 | 1 | 0 | 24.7 | 0vanillaice0 |
| `db060_9x9_kiiroipazuru-blog-fc2-com` | 9×9 | 1 | 4 | 23.5 | http://kiiroipazuru.blog.fc… |
| `db016_9x9_dj-puzzles` | 9×9 | 1 | 20 | 23.4 | dj-puzzles |
| `db056_9x13_0vanillaice0` | 9×13 | 1 | 9 | 22.8 | 0vanillaice0 |
| `db003_9x8_bachelor-seal` | 9×8 | 1 | 0 | 22.5 | bachelor seal |
| `db035_8x8_bakpao-puz` | 8×8 | 1 | 10 | 22.3 | bakpao_puz |
| `db022_4x6_atraingrooveryy` | 4×6 | 1 | 0 | 22.2 | AtrainGrooverYY |
