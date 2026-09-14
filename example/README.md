# example/ — GUI 示例库

本目录的 JSON 是 **GUI「示例」下拉框的数据源**：`icelom_gui.py` 用
`_scan_examples()` 扫描 `example/*.json`（`EXAMPLE_DIR = <仓库根>/example`），
按**文件名排序**取出去掉 `.json` 的 stem 作为下拉项；选中时用 `load_example_file()` 载入。
所以**新增一个示例 = 往本目录放一个新的 `NN_名称.json`**，不需要改任何代码。

> ⚠️ **本目录只放"能解、给玩家看的示例"**。下拉框按文件名排序、界面**启动时默认加载第一项**，
> 所以往这里丢一个临时文件/无解题会立刻改变界面启动题面，还会被 `--selftest`（冒烟要求
> `solutions >= 1`）和 `tools/make_release.py`（发布包会把本目录整个打进 `example/`）带上。

目录里 11 个示例的 `_note` 字段（一行一个）如下。**这个字段会显示在界面状态栏**：
加载示例时它出现在状态栏，所以只写"这道题演示什么、该注意什么"，
**不写文件名/内部路径/开发史**（例如"源自某个已删除的脚本"这类信息对解题的人毫无用处）。

| 文件 | 演示什么 |
| --- | --- |
| `01_经典9x9.json` | 经典 9x9：9 个数字，覆盖全部白格，解唯一 |
| `02_博客8x8.json` | 8x8 入门：7 个数字，解**不经过任何冰格** |
| `03_入门5x5.json` | 5x5 入门：无数字，解是一条穿过 9 个冰格的冰廊 |
| `04_冰迷宫5x7.json` | 5x7 冰迷宫：无数字，17 个冰格 |
| `05_进阶8x8.json` | 8x8 进阶：数字与冰格混排，覆盖全部白格 |
| `06_进阶9x9.json` | 9x9 进阶：冰格密集，需要冰上十字交叉 |
| `07_挑战10x10.json` | 10x10 挑战：32 个冰格，无数字 |
| `08_问号格10x7.json` | 10x7「?」格演示：2 个数字未知的编号格（`n = -2`） |
| `09_内部INOUT演示.json` | **IN/OUT 位于盘面内部**（线路以格心为起/终点，无入出界箭头；IN=(1,1)、OUT=(3,3)） |
| `10_角冰格INOUT演示.json` | **IN/OUT 位于角上的冰格**（需点击相邻格指定入/出界方向；IN=(0,0) 冰格 `side=L`、OUT=(5,4) 冰格 `side=R`，含 15 条箭头强制边） |
| `11_20260909_9x9.json` | **箭头方向回归题**（9×9、26 冰、10 条箭头，唯一解）：最右上角冰格 `(6,1)` 的上边/右边两条箭头所在的强制分量**不与 IN/OUT 相连**，专门钉住"孤立强制边分量也必须校验箭头方向"（见 [`../docs/算法说明.md`](../docs/算法说明.md) §3.9） |

### `11_20260909_9x9.json` 的来源 URL

题面出自 **Penpa+（penpa-edit）**：

```
https://swaroopg92.github.io/penpa-edit/?m=solve&p=zVZRc9M4EH7Pr2D8iuaQLMuWMsNDS3scDAQK7fXAk+m4iUsCbgxOAh134LfzrbShsRM47u0msfX5k7z6dldraflpXTSlUIr+2gopgERiUn8pFftL8u90vqrK4b0nk/KyaBbiYL2a1c3w3l/lzVyI16tiMS2a6ab7XrOuyuUf4sVIXBXVshRP37w/PPpw8OX44J8H5q3WZ6Or+++PTs7eT8//Vidy/qCRo8ounr88OqzuP27fPp8dfC6Py/Tlsp7MqrKYFu3b86c31eJP+252pR49nT2yV8VCLj/ZU/f58OThw0HOSseDPIoj4S8Vjb+1z77lAMKNB7ftq+FtezHMx19Fe3YH7R18PbyN0iQaGhGlJjRpaJxvstBY5RsXRrow0oWRzoYmjFRShlaFV5TS3IaXVBxsqHjzHKyoOJhRMdvRbCfhcWbT8jjD41IaB09G8CRzcTTMoxdnpxFSG6XRGNJlRtyT0YbCWDW8xf0N3jAScnItoqJp6i8Xo4vDSMR4y6hdXhGv4Vae7fLpfj6VkL2HzxLIzqF/h6d5uzzpySgfORzoj3c0757xlI49461EuHs8jbcU7h09CNIp1olotb8f+bv0d+Pvz3wgjxHI2GQiptw4LEVjgSHAYydiyhHhVAJDsMcKGOnyOAbGOvFYAyMIHifACKDHBhjiPU5FTEuSsIUdWomEXSo0rTtgtELT2iIcg0+YT8Ab5lH3OmM+o48C8xbfBBn4RMofWDsHHHzRzgo8M86Ag++aNDgsOY8NMNt0CXDwRTsNHHzULgYOvuuM7ISYaMQEz6wZPMdKa/AJ8wq8Zl6CV4GPLXjJsc0QW8s85Shj3kK/5JhniG3GMcwQ84xjniEXGeeCsGUfJfQrxgp2FMdBOcSc4xNLaGN/NcZr9lcjDtt8wnYS2EnYTgI7hu0Y2DEcf43YbnCMfGmOrQQf83pw4GmRe81YJ1Qg3l+sQ8frEFhT4ft3oYeK1L+LuRhriTGKNUiKFWuTFNtNHIBjjn+M+GvOiwZvmDfgDefXwF/D8xrMS0Xtcw37PzDlmu0TtmzHwo5lOxZ2LNuxsGNZcwb9G2yw9jLWn1AMmY/B08fH5ws8fYc9D5v0bd5gzRqwU2rN2mLKHdd1hhqn3WGDeQ2jBd6sGYo520Qta65lj/ldtNDMelDjAeOjcu4/LY/8PfH31H9yMtq4BoMc64X27+1f9v9isDNjD46WdXWxXDdXxaS8KG+KySoahkPCdk+HW6yvL8umQ1V1/bGaL35YWDXrXk9n+Pzdom7KvV1EltN3+7RsuvaYuqybaU/Sl6Kquq74A1aHmsybSdWlVs288+w3nA5zXaxmHeKyWOEwtpzNP3YtlYteLFdFV2LxoejNdn0Xjq+D6CbyF/b5WCR0XnLD9kC0j3Fe2DpSifYEB6bnw/YZnZfyKBIGO+b1ulrNJ3VVY0risLtiO/RHLw14HKADPPf92GWxmj2pJPAIOPVnklc0xRs8dvfk9uUwb09FRL2H3gTB6Lr+DA+8Hf88qa8v4WMeUTiWfvJouZ7WH9Y8ym/jBz0P6CzwCw9INntAzgQPCPU9ACapPfVk6T+q38rxrgtu/DVkS/7mmTacB7dPer9/lPnXb88NF3Xd/KKu7zr79J7qBtsv8P29+/ifFPNWb5/fqVwSu1u8YPfUL9h+CYParWKQO4UM7ie1TFb75Uyq+hVNU+0UNU21Xdf5ePAd&a=RZPbDcMwDAN36bc/QsevzFJ0/zV6gmgHKKADK5GyA3+/v/L96FKRRnk+BV5F1/NyvZN10aOXazfHbH252gdN2rM33F6uy9xgZ5EvzWQyVd1PPVnU4x/cLjOzdc/CzXuiqXk3MtW8D5lq9r/Z+XZPcLP/Tf/t3YK7Z9HUPUu+uncj82SRo+4zkqO2e2Jn++On4R78jg9VfffA02dE0/S5Oufa/sHTuWjq3jl4emc0DftQNexD1XQWu2h4lnpyyTz++Gn67FRN70zdPm2Vli7QyHyEkVP9Kj2zoZHTCCNney2+ZWjk90TwLXFJviPImyL4rii+HUKdRnEGNHMCwWnQyjMiOA1admF7TzzFdwGtdEZY6UzoSr+5dgb05DkQnBF/5WwE5MSqZWUf9OQGIeR5iXIGAfFEA8M3bSj7nYaSnVHSm7KfayhpjnO+SV79+/v9AQ==&sessionid=
```

这是 **Penpa+ 自己的编码**（不是 puzz.link 的 `p?icelom/...` 编码），`tools/pzprurl2json.js` 解不了它 ——
所以 `tools/make_examples.py` 里把这道题的题面与 10 条箭头**直接内联**（用 `(起点格, 终点格)` 表示箭头方向），
而不是像 `03`–`08` 那样从 `benchmark/puzzles/` 里取。

## 从哪来、怎么重生成

- 全部由 `python tools/make_examples.py` 生成：`01` 是原 9x9 夹具、`02` 是 8x8 博客题，
  `03`–`08` 从 `benchmark/puzzles/` 精选（逐题先跑一遍求解器 `mode="unique"` 断言恰 1 解再落盘），
  `09`/`10` 是"内部 IN/OUT""角冰格 IN/OUT"两个新特性演示（沿一条骨架路径**贪心加箭头直到唯一解**），
  `11` 是**箭头方向回归题**（作者 Hexi，题面来自 Penpa+；题面与 10 条箭头**内联在脚本里**，同样断言恰 1 解；
  来源 URL 见上一节）。
- 脚本会**整体重写**这 11 个文件（含 `_note`），所以不要手工改这些 JSON ——
  要改就改 `tools/make_examples.py`（这也意味着 `_note` 的文字只在生成时写一次，
  与本题面后来的求解结论可能不再同步）。
  （`01` 在仓库里是 LF 换行、其余是脚本写出的 CRLF；跑一次脚本会把 `01` 也变成 CRLF，
  内容不变，只是字节不同。）

## 哪些测试按文件名依赖它们

| 测试 | 依赖的示例 |
| --- | --- |
| `tests/check_engine_examples.py` | **全量**：扫描 `example/*.json`，每题求解后要求独立验证器通过、规则引擎判 `complete`（补上 IN/OUT 出界短边后仍须 `complete`） |
| `tests/run_tests.py` | `11_20260909_9x9.json`（T14.6：恰 1 解 + 独立验证器） |
| `tests/gui_visual_test.py` | `01_经典9x9.json`（边标记截图）、`02_博客8x8.json`、`09_内部INOUT演示.json`、`10_角冰格INOUT演示.json` |
| `tests/gui_logic_test.py` | `02_博客8x8.json`（示例扫描与加载、求解 = 1 解、求解模式）、`09_内部INOUT演示.json`、`10_角冰格INOUT演示.json`；另有断言要求"扫描到的示例 ≥ 8 个"（`len(app.examples) >= 8`） |

也就是说：**删掉或重命名上表点名的 5 个文件会直接让对应用例失败**，
新增示例则只需保证文件名排序稳定、并且题目本身可解（`check_engine_examples.py` 会全量跑一遍）。
