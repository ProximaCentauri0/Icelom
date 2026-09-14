# IceLom 求解器性能基准报告

- 求解器: `icelom_solver.exe` (g++ -O2; **规则传播 + 单边试连接**推理到不动点, 剩下的分支按**两级打分选格**(合法配置数最少, 平手看未定边邻居的平均配置数)枚举; 数字按位次规则判定, 支持跳号与 "?" 格)
- 题面来源: [puzz.link/db](https://puzz.link/db/) 收录的真实 Icelom 题 (共 65 题进入基准; 仅 `v:/` 变体题被剔除 —— 见 `manifest.json` 的 `decode` 字段与 `tools/scan_marks.js`)。其中 db034(2 个 "?")与 db039(4 个 "?")含数字未知的编号格。
- 规则: 官方 (覆盖所有白格); 计时: 每题 3 遍取最优; 解数量上限 5000; 单遍限时 60000 ms
- 全部解均经独立验证器 `tests/verify.py` 核对; 结论另用独立走廊收缩模型（`tests/indep_solver.py`）交叉核对
- 总耗时: 1.5 s
- **首解 ms** = 从启动到第一个 `solution` 行的墙钟(无解为 `—`): 这是"能不能解出来、多快解出来"的真实代价。枚举模式下的"求解 ms/墙钟"还受解数量上限与时限支配。
- **节点数 = 0** 表示整条线路完全由推理(规则 + 试连接)推出来, 一次搜索分支都没用上; 本次运行里 65 题中有 35 题如此。

## 总览

| 状态 | 题数 | 说明 |
| --- | ---: | --- |
| unique | 65 | 恰有 1 解 (正常出版题) |

正常求解的 65 题: 最快 20.9 ms, 中位 23.0 ms, 最慢 42.9 ms, 总节点 528

## 与历史版本对比

| 版本 | 题数 | 唯一解 | 多解 | 无解 | 超时/未判定 | 总耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 旧（逐格 DFS） | 63 | 57 | 1 | 0 | 7 | 594.7 s |
| 路径段并查集 + MRV 选格（**已删除**） | 65 | 64 | 0 | 0 | 1 | 61.5 s ~ 184.4 s |
| 规则传播 + 单边试连接 + 行主序分支（2026-09 前） | 65 | 65 | 0 | 0 | 0 | ≈5 s |
| **当前（规则传播 + 单边试连接, 两级打分选格）** | 65 | 65 | 0 | 0 | 0 | 1.5 s |

> 旧求解器只支持数字恰好为 `1..K` 的题面，db034/db039（数字呈跳号排列、含 "?" 格）无法求解，故最早那行数据仅覆盖 63 题。
>
> **当前版本把 `tools/deduce.py` 的确定性推理搬进了求解器核心**：每条规则（格内配置、冰格直行、连通/无环/可达、相邻已知数字、"?" 位次模型）加上**逐格逐方向试连接 + 路径检查**一路推到不动点，剩下的才交给搜索；分支选格按**两级打分**（合法配置数最少优先，平手看未定边邻居的平均配置数，打分全部来自一次遍历的已知量、零试算；总分支节点从 2,308 降到 528）。
>
> **db039 不再是难例**：13×13、146 白格 + 23 冰格、9 个已知数字 + 4 个 "?" 冰格（位次规则的计数推论要求 4 个 "?" 各被十字交叉穿越两次，正好补齐 2,4,…,16）。旧求解器在题面朝向下 300 s 搜不出、换朝向才 2~12 s；现在**任何朝向都是 0 分支节点、毫秒级推完整条线路**（回归见 `tests/run_tests.py` T16）。
>
> 该解为 171 格线路，编号位次恰为 `1,?(2),3,?(4),…,?(16),17`，独立验证器通过，并用 pzpr 官方引擎 `check()` 判定为 **PASS**（`tools/official_check.py`）；与"把作者提示作为强制边"求得的解**逐格完全相同**。解与报告不再落盘保留，需要时 `python tools/official_check.py db039` 现场重解并判定。

## 明细 (按耗时降序, 前后各 25)

| # | 题号 | 尺寸 | 编号格 | 冰 | 解数 | 节点 | 首解 ms | 求解 ms | 墙钟 ms | 状态 | 来源 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `db048_11x9_ihnnpuzzles` | 11×9 | 10 | 22 | 1 | 278 | 38 | 21.7 | 42.9 | unique | ihnnpuzzles |
| 2 | `db049_9x9_tckmn` | 9×9 | 10 | 10 | 1 | 86 | 22 | 6.0 | 29.8 | unique | tckmn |
| 3 | `db056_9x13_0vanillaice0` | 9×13 | 10 | 44 | 1 | 43 | 19 | 8.8 | 29.2 | unique | 0vanillaice0 |
| 4 | `db039_13x13_0vanillaice0` | 13×13 | 13 | 23 | 1 | 0 | 21 | 2.0 | 27.0 | unique | 0vanillaice0 |
| 5 | `db019_10x10_bakpao-puz` | 10×10 | 12 | 32 | 1 | 12 | 22 | 2.9 | 26.7 | unique | bakpao_puz |
| 6 | `db004_8x8_bachelor-seal` | 8×8 | 5 | 13 | 1 | 0 | 23 | 0.0 | 25.5 | unique | bachelor seal |
| 7 | `db016_9x9_dj-puzzles` | 9×9 | 10 | 9 | 1 | 35 | 21 | 2.9 | 25.4 | unique | dj-puzzles |
| 8 | `db006_8x8_bachelor-seal` | 8×8 | 5 | 18 | 1 | 0 | 21 | 0.0 | 24.9 | unique | bachelor seal |
| 9 | `db017_5x7_ericfox53` | 5×7 | 0 | 17 | 1 | 0 | 22 | 0.0 | 24.8 | unique | EricFox53 |
| 10 | `db058_8x8_hotatenohontate` | 8×8 | 8 | 28 | 1 | 0 | 22 | 1.0 | 24.8 | unique | hotatenohontate |
| 11 | `db029_11x11_menderbug` | 11×11 | 4 | 60 | 1 | 2 | 22 | 1.0 | 24.6 | unique | menderbug |
| 12 | `db023_6x7_udop` | 6×7 | 0 | 21 | 1 | 0 | 21 | 0.0 | 24.5 | unique | udoP_ |
| 13 | `db024_4x6_chebunanntoka` | 4×6 | 0 | 8 | 1 | 0 | 22 | 0.0 | 24.4 | unique | chebunanntoka |
| 14 | `db036_9x9_qpinemarch323` | 9×9 | 11 | 23 | 1 | 5 | 21 | 1.0 | 24.3 | unique | qpinemarch323 |
| 15 | `db003_9x8_bachelor-seal` | 9×8 | 7 | 15 | 1 | 0 | 20 | 0.0 | 24.1 | unique | bachelor seal |
| 16 | `db025_10x4_chebunanntoka` | 10×4 | 0 | 18 | 1 | 0 | 21 | 0.0 | 24.1 | unique | chebunanntoka |
| 17 | `db061_6x6_kiiroipazuru-blog-fc2-com` | 6×6 | 0 | 16 | 1 | 0 | 20 | 0.0 | 23.9 | unique | http://kiiroipazuru.blo… |
| 18 | `db009_8x8_bachelor-seal` | 8×8 | 5 | 24 | 1 | 1 | 20 | 0.0 | 23.8 | unique | bachelor seal |
| 19 | `db037_12x13_bakpao-puz` | 12×13 | 15 | 68 | 1 | 2 | 20 | 2.0 | 23.8 | unique | bakpao_puz |
| 20 | `db022_4x6_atraingrooveryy` | 4×6 | 0 | 14 | 1 | 0 | 20 | 0.0 | 23.7 | unique | AtrainGrooverYY |
| 21 | `db060_9x9_kiiroipazuru-blog-fc2-com` | 9×9 | 10 | 32 | 1 | 6 | 20 | 1.5 | 23.7 | unique | http://kiiroipazuru.blo… |
| 22 | `db063_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 5 | 0 | 1 | 0 | 21 | 0.0 | 23.7 | unique | http://puzzleblog542.bl… |
| 23 | `db015_8x8_bachelor-seal` | 8×8 | 7 | 26 | 1 | 0 | 20 | 0.8 | 23.6 | unique | bachelor seal |
| 24 | `db020_6x6_pawakun` | 6×6 | 0 | 18 | 1 | 0 | 20 | 0.0 | 23.6 | unique | pawakun |
| 25 | `db008_8x8_bachelor-seal` | 8×8 | 5 | 22 | 1 | 1 | 20 | 0.0 | 23.5 | unique | bachelor seal |
| … | | | | | | | | | | |
| 41 | `db064_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 8 | 20 | 1 | 1 | 19 | 0.0 | 22.7 | unique | http://puzzleblog542.bl… |
| 42 | `db047_8x8_ihnnpuzzles` | 8×8 | 4 | 19 | 1 | 1 | 20 | 1.0 | 22.6 | unique | ihnnpuzzles |
| 43 | `db057_6x6_3892myamya` | 6×6 | 4 | 11 | 1 | 2 | 20 | 1.0 | 22.6 | unique | 3892myamya |
| 44 | `db066_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 7 | 28 | 1 | 0 | 19 | 0.0 | 22.6 | unique | http://puzzleblog542.bl… |
| 45 | `db065_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 9 | 18 | 1 | 2 | 19 | 1.0 | 22.5 | unique | http://puzzleblog542.bl… |
| 46 | `db002_8x8_bachelor-seal` | 8×8 | 6 | 14 | 1 | 2 | 20 | 0.0 | 22.4 | unique | bachelor seal |
| 47 | `db043_8x8_kjry0` | 8×8 | 5 | 24 | 1 | 1 | 19 | 0.0 | 22.4 | unique | KJRY0 |
| 48 | `db067_8x8_puzzleblog542-blog-fc2-com` | 8×8 | 5 | 20 | 1 | 4 | 19 | 1.5 | 22.3 | unique | http://puzzleblog542.bl… |
| 49 | `db068_6x6_puzzleblog542-blog-fc2-com` | 6×6 | 3 | 6 | 1 | 0 | 19 | 0.0 | 22.3 | unique | http://puzzleblog542.bl… |
| 50 | `db032_6x6_ericfox53` | 6×6 | 4 | 8 | 1 | 0 | 18 | 0.0 | 22.2 | unique | EricFox53 |
| 51 | `db045_14x14_nu-n-notami` | 14×14 | 2 | 61 | 1 | 6 | 19 | 0.0 | 22.2 | unique | nu_n_notami |
| 52 | `db010_8x8_bachelor-seal` | 8×8 | 5 | 19 | 1 | 0 | 19 | 0.0 | 22.1 | unique | bachelor seal |
| 53 | `db018_9x4_takmu53` | 9×4 | 0 | 15 | 1 | 0 | 19 | 0.0 | 22.1 | unique | takmu53 |
| 54 | `db027_5x5_wand-125` | 5×5 | 0 | 9 | 1 | 0 | 19 | 0.0 | 22.1 | unique | wand_125 |
| 55 | `db031_6x6_jonnjonn69` | 6×6 | 5 | 8 | 1 | 2 | 19 | 1.0 | 22.1 | unique | jonnjonn69 |
| 56 | `db038_9x9_xoned72` | 9×9 | 6 | 26 | 1 | 1 | 19 | 0.0 | 22.1 | unique | xoned72 |
| 57 | `db028_19x5_pancakepuzzles` | 19×5 | 0 | 49 | 1 | 1 | 19 | 0.0 | 22.0 | unique | pancakepuzzles |
| 58 | `db055_6x6_daikichi-3141` | 6×6 | 5 | 18 | 1 | 0 | 19 | 0.0 | 21.9 | unique | Daikichi_3141 |
| 59 | `db012_8x8_bachelor-seal` | 8×8 | 7 | 11 | 1 | 4 | 18 | 1.0 | 21.8 | unique | bachelor seal |
| 60 | `db052_6x6_qpinemarch323` | 6×6 | 6 | 9 | 1 | 0 | 18 | 0.0 | 21.8 | unique | qpinemarch323 |
| 61 | `db001_9x9_bachelor-seal` | 9×9 | 5 | 16 | 1 | 1 | 18 | 0.0 | 21.5 | unique | bachelor seal |
| 62 | `db013_8x8_bachelor-seal` | 8×8 | 7 | 18 | 1 | 0 | 18 | 0.0 | 21.4 | unique | bachelor seal |
| 63 | `db040_6x6_qpinemarch323` | 6×6 | 4 | 12 | 1 | 0 | 19 | 0.0 | 21.4 | unique | qpinemarch323 |
| 64 | `db053_5x5_qpinemarch323` | 5×5 | 5 | 7 | 1 | 0 | 18 | 1.0 | 21.3 | unique | qpinemarch323 |
| 65 | `db041_6x6_qpinemarch323` | 6×6 | 4 | 9 | 1 | 0 | 18 | 0.0 | 20.9 | unique | qpinemarch323 |

## 最难的 10 题

| 题号 | 尺寸 | 解数 | 节点 | 墙钟 ms | 来源 |
| --- | --- | ---: | ---: | ---: | --- |
| `db048_11x9_ihnnpuzzles` | 11×9 | 1 | 278 | 42.9 | ihnnpuzzles |
| `db049_9x9_tckmn` | 9×9 | 1 | 86 | 29.8 | tckmn |
| `db056_9x13_0vanillaice0` | 9×13 | 1 | 43 | 29.2 | 0vanillaice0 |
| `db039_13x13_0vanillaice0` | 13×13 | 1 | 0 | 27.0 | 0vanillaice0 |
| `db019_10x10_bakpao-puz` | 10×10 | 1 | 12 | 26.7 | bakpao_puz |
| `db004_8x8_bachelor-seal` | 8×8 | 1 | 0 | 25.5 | bachelor seal |
| `db016_9x9_dj-puzzles` | 9×9 | 1 | 35 | 25.4 | dj-puzzles |
| `db006_8x8_bachelor-seal` | 8×8 | 1 | 0 | 24.9 | bachelor seal |
| `db017_5x7_ericfox53` | 5×7 | 1 | 0 | 24.8 | EricFox53 |
| `db058_8x8_hotatenohontate` | 8×8 | 1 | 0 | 24.8 | hotatenohontate |
