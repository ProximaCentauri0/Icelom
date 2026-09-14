# 第三方组件与数据来源

本仓库自己的代码以 [MIT](LICENSE) 发布。下面列出**它用到/分发**的第三方内容及其许可。

## 1. pzprjs（官方谜题引擎）— MIT

- 位置：`tools/pzprjs/`
  （`pzpr.concat.js`、`pzpr-variety/icebarn.js`、`node_modules/pzpr-canvas/dist/candle.js`、
  `package.json`、`LICENSE.txt`，以及重建所需的精简源码树 `src/`、`src-ui/res/`）
- 来源：<https://github.com/robx/pzprjs>（上游 <https://github.com/sabo2/pzprjs>），MIT：
  © 2011, 2014 Kobayashi, Daisuke (sabo2)；© 2019 Vollmert, Robert and contributors
- 完整许可全文：`tools/pzprjs/LICENSE.txt`（**随本仓库与发布版一同分发**）
- 用途：① puzz.link URL → 题面 JSON 的解码（`tools/pzprurl2json.js`）；
  ② **未经修改的官方 `check()`** 作为独立判据交叉验证本项目求出的解
  （`tools/official_check.js`、`tools/official_check.py`、`tests/check_engine_pzprjs.py`）
- 本仓库**未修改** pzprjs 的任何代码。`pzpr.concat.js` 可用 `node tools/build_concat.js`
  从精简源码树逐字节重建。
- 发行包（`release/IceLom/`）只带 `pzpr.concat.js` + `pzpr-variety/icebarn.js` + `LICENSE.txt`，
  不带重建脚本与源码树

> pzprjs 的 README 另有一条声明：某些玩法用到的 emoji 图像来自 **noto-emoji（SIL OFL 1.1）**。
> 已核查本仓库实际分发的内容不涉及该条：`pzpr.concat.js` 是**逐文件拼接的纯 JavaScript**
> （没有内嵌任何图像或 base64 资源 —— 全文件搜不到 `data:image/png;base64` / `iVBORw0KGgo`），
> 拼接所需的文件清单只含 `.js` 模块；`tools/pzprjs/` 的源码树也已精简为
> "重建 `pzpr.concat.js` 所需的最小集合"（`src/` JS 模块 + `src-ui/res/` 语言包 +
> `node_modules/pzpr-canvas/dist/candle.js`），**不含**上游的 `src-ui/img/*.png` 玩法缩略图，
> 也没有任何 emoji 图像文件。若将来把上游图像资源加进来，需一并遵守 SIL OFL 1.1 的再分发条件。

## 2. 题面数据（`benchmark/puzzles/`、`example/`、`assets/icon_puzzle.json`）

- 来源：**各作者公开发布**的 アイスローム（IceLom）题目，经 [puzz.link/db](https://puzz.link/db/)
  收录（`benchmark/db_icelom_raw.json` 保留原始记录，含原作者、原链接、发布日期；
  `benchmark/manifest.json` 是逐题清单）。`example/11_20260909_9x9.json` 来自 Penpa+
  （作者 Hexi），来源 URL 记在 `example/README.md`。
- **版权归各作者**。本仓库把它们作为求解器的输入/验收数据，不做再授权；
  题目作者如希望移除，请开 issue。
- 本仓库**不含** Nikoli 出版物的题目数据。

## 3. 玩法名称与规则

- アイスローム / IceLom（pzprjs pid `icelom`）是 Nikoli 体系的铅笔谜题，**规则版权归 Nikoli**。
  本仓库与发布版中的规则说明均为**自行撰写**，未复制 Nikoli 的规则文本或插图。
- 本项目与 Nikoli 无任何关联，非官方作品。
