# -*- coding: utf-8 -*-
"""make_release.py — 生成**最小、自解释、自包含**的发布版到 release/。

发布版只放"拿来就能跑"的东西 + 文档 + 题面；**源码、测试、基准、构建脚本都不进包**
（它们在 GitHub 仓库里，包内 README 给出仓库地址）。产出（release/ 可整体拷走或打包分发）:

    IceLom/
    ├─ README.md                  唯一的入口文档: 怎么跑、有哪些功能、依赖什么、许可
    ├─ icelom_solver.exe          **静态链接**求解器（单文件，不需要任何 DLL）
    ├─ icelom_gui.py              图形界面（tkinter，只用标准库 + 可选 Pillow）
    ├─ icelom_render.py           离屏 PNG 渲染（需要 Pillow）
    ├─ assets/icelom.ico          图标（GUI 的窗口/任务栏图标）
    ├─ example/*.json             GUI 示例下拉框数据源（11 道题面）
    └─ tools/
        ├─ pzprurl2json.js        puzz.link URL → icelom-v1 JSON（GUI「导入 URL」用它）
        ├─ make_shortcut.py       建带图标的快捷方式（GUI 首启动/菜单会调它）
        └─ pzprjs/                官方引擎（vendored，离线可用；MIT，附 LICENSE.txt）

**不放进去的**：求解器源码与 build.py（仓库里有）、tests/、benchmark/、analysis/、docs/、
规则推导器（tools/deduce*）、独立验证器与官方判定命令行（tools/verify*、official_check.js）、
pzprjs 重建脚本（build_concat.js，包内没有源码树，带了也没用）、
MinGW 运行时 DLL（静态链接后不需要）。

用法:
    python -X utf8 tools/make_release.py [--out release] [--zip] [--force] [--no-smoke]
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

VERSION = "1.0.1"
REPO_URL = "https://github.com/ProximaCentauri0/Icelom"

# (源, 目标目录) —— 目标目录 "" 表示发布版根目录
FILES = [
    ("icelom_gui.py", ""),
    ("icelom_render.py", ""),
    ("assets/icelom.ico", "assets"),
    ("tools/pzprurl2json.js", "tools"),
    ("tools/make_shortcut.py", "tools"),
    ("tools/pzprjs/pzpr.concat.js", "tools/pzprjs"),
    ("tools/pzprjs/pzpr-variety/icebarn.js", "tools/pzprjs/pzpr-variety"),
    ("tools/pzprjs/LICENSE.txt", "tools/pzprjs"),
]
# 目录内除 .md 外的所有文件（示例题面）
# 注意: 这里是**白名单** —— 只有 `example/` 会被整目录分发；
# `release/`、`tests/`、`docs/`、`benchmark/` 都不在清单里, 因此不会进发布包。
DIRS = [("example", "example", (".json",))]

# 冒烟用例：无数字、解唯一，静态 exe 必须能解出 1 个解
SMOKE_PUZZLE = "example/03_入门5x5.json"
# URL 导入冒烟用例（puzz.link 的 icelom 题，8x8，博客题 02 的来源 URL）
SMOKE_URL = "https://puzz.link/p?icelom/a/8/8/4e40040c4g004i6r3k7k5w4i2g1q/0/15"

README = """# 冰宫巡游 IceLom 通用求解器 %(version)s

IceLom（アイスローム）谜题的**图形界面 + 求解器**：画题面、一键求解、显示解、像
[puzz.link](https://puzz.link) 那样做题并实时校验，也能导入 puzz.link 的题目 URL。
Windows 免安装：解压后 `python icelom_gui.py` 即可，**不需要编译、不需要联网**。

- **前端**：Python 3 + tkinter（只用标准库；导出 PNG 需要 Pillow，可选）
- **后端**：C++ 单文件求解器 `icelom_solver.exe`（静态链接，**单文件无 DLL 依赖**）
- **仓库（源码、测试、基准、算法文档）**：<%(repo)s>

## 规则

1. 从 **IN** 进、**OUT** 出，画一条**不分叉、不重叠**的单一线路，线路走格子中心，横竖相连。
2. **白格**：至多经过一次，可转弯；默认要求**所有白格都被经过**（界面可勾选关闭）。
3. **冰格（蓝格）**：不能转弯（进入后必须直行穿出），**允许垂直交叉**
   （每格横、竖各最多一次，禁止同轴重叠）；冰格不必全部经过。
   IN/OUT 也可以放在冰格上（冰上 IN 出发后必须直行）。
4. **编号格**：线路按**升序**经过编号格，已知数字 `v` 必须正好落在第 `v` 位
   （等价于"线上数字不跳跃、必须连续"）。**"?" 格**是**数字未知**的编号格，
   "?" 冰格允许被**十字交叉穿过两次**，每次穿越各占一个编号位次。
5. **格间标记**：线段 = 必经（方向任意）；箭头 = 按箭头方向必经；墙 = 禁止经过。

> 玩法在官方引擎 pzprjs 里的 id 是 **`icelom`**（与 `icebarn`、`icelom2` 同一变体家族）。

## 跑起来

```
python icelom_gui.py
```

### 想要任务栏图标 / 桌面快捷方式（Windows）

用 `python icelom_gui.py` 启动时进程是 **python.exe**，Windows 任务栏默认按进程取图标，
所以任务栏按钮可能显示成 python 的图标（窗口标题栏的图标是对的，那是两回事）。
**第一次运行时界面会弹一句提示，顺手建好带图标的快捷方式**——只问一次：

- 选「是」→ 在桌面建；桌面写不进去就自动退到程序目录里建一个；
- 选「否」→ 直接在程序目录里建 `IceLom 冰宫巡游.lnk`，不再打扰；
- 之后随时可以用菜单 **文件 → 创建桌面快捷方式（带图标）**，或
  `python tools/make_shortcut.py --desktop`。

快捷方式的目标是 `pythonw -X utf8 icelom_gui.py`、图标是 `assets/icelom.ico`，
并且带上了与程序一致的 AppUserModelID，任务栏据此把窗口和快捷方式配对显示 IceLom 图标；
同时会生成 `tools/launch_icelom.cmd`（不想用快捷方式时双击它也行）。

界面顶部：**示例**下拉框（内置 11 道题）、新建 / 打开 / 保存 / **导入 URL**；
**编辑**模式涂白/冰、放数字与 "?"、放 IN/OUT、画线段/箭头/墙；
**做题**模式按住拖动即可画线（可分段、可从任意格起笔、可在 IN/OUT 处画出界外），
「检查解」按规则实时判定，「显示解 / 隐藏解」对照答案，「对照解」只看当前线路是不是解的一部分。

求解在后台静默进行（不会弹控制台黑窗）。题面**无解**时，求解器会把"最深现场盘面"写到
**诊断通道** stderr 上 —— 界面不会因此报错，想看就点 **查看 → 求解器诊断…**（**Ctrl+D**）。

## 依赖

| 需要什么 | 用途 | 没有它会怎样 |
| --- | --- | --- |
| Python 3.8+（含 tkinter） | 图形界面 | 界面无法启动 |
| `icelom_solver.exe`（已随包，静态链接） | 求解 | 界面能开，但求解报"未找到求解器" |
| Node.js | 导入 puzz.link URL | URL 导入不可用，其余功能正常 |
| Pillow | "导出解为图片" | 该按钮提示 `pip install pillow` |

## 命令行工具

```
node   tools/pzprurl2json.js "https://puzz.link/p?icelom/a/8/8/..../3/12"   # URL → 题面 JSON
python tools/make_shortcut.py --desktop                            # 桌面快捷方式（带图标）
```

求解器本身是 stdin/stdout 的 JSON 管道（界面就是这么调它的）：

```
{"format":"icelom-v1","w":5,"h":5,"cells":[...],"numbers":[...],
 "in":{"x":2,"y":0,"side":"U"},"out":{"x":0,"y":0,"side":"U"},
 "limits":{"mode":"unique"}}
```

喂给它这个 JSON（读满 stdin 后开始求解），stdout 会逐行吐 JSON：
`{"type":"solution",...}` 与结尾的 `{"type":"done","count":1,...}`。

## 目录里都是什么

| 文件 | 说明 |
| --- | --- |
| `icelom_gui.py` | 图形界面（编辑 + 做题 + 求解桥） |
| `icelom_render.py` | 离屏 PNG 渲染器（Nikoli 纸面风格；需要 Pillow） |
| `icelom_solver.exe` | 已编译的求解器（必须与本目录的 `icelom_gui.py` 同级） |
| `assets/icelom.ico` | 图标：一道真实 2×2 题（右上角冰格带 "?"，其余三格 2/3/4） |
| `example/*.json` | GUI 示例下拉框的数据源（放新的 `NN_名称.json` 即出现在下拉框里） |
| `tools/pzprurl2json.js` | puzz.link URL → 题面 JSON（共用 `tools/pzprjs` 官方解码库） |
| `tools/make_shortcut.py` | 生成带图标的快捷方式 / 启动器 |
| `tools/pzprjs/` | 官方 pzprjs 引擎（**MIT**，见其内 `LICENSE.txt`），只用于 URL 解码 |

最小冒烟用例（解唯一）：

```
python icelom_gui.py                      # 打开后在「示例」里选 03_入门5x5
python tools/make_shortcut.py --help      # 工具可用性
node   tools/pzprurl2json.js "%(smoke_url)s"
```

题面文件格式（`icelom-v1`，纯 JSON，UTF-8）：

```json
{"format": "icelom-v1", "w": 5, "h": 5,
 "cells": ["w", "i", ...],              // 长度 w*h, 按行优先; "w"=白格 "i"=冰格
 "numbers": [{"x": 2, "y": 0, "n": 3}], // n = -2 表示 "?" 格
 "in": {"x": 2, "y": 0, "side": "U"},   // side ∈ R/D/L/U
 "out": {"x": 0, "y": 0, "side": "U"},
 "edges": [{"x": 1, "y": 2, "side": "R", "kind": "arrow", "dir": "D"}],
 "options": {"cover_all_whites": true}}
```

`kind` ∈ `segment`（必经）/ `arrow`（定向必经，带 `dir`）/ `wall`（禁止经过）。

## 许可与来源

- 本项目代码以 **MIT** 许可发布，见仓库的 `LICENSE`。
- `tools/pzprjs/` 是官方引擎 [pzprjs](https://github.com/robx/pzprjs) 的构建产物
  （**MIT**：© 2011, 2014 Kobayashi, Daisuke (sabo2)；© 2019 Vollmert, Robert and contributors），
  随包附 MIT 全文于 `tools/pzprjs/LICENSE.txt`。
- `example/` 里的题面是各作者**公开发布**的 Icelom 题目（经 puzz.link 收录，逐题可溯源到
  原作者与原始链接）；题目版权归各作者，这里只作求解器的示例输入。玩法名称
  アイスローム/IceLom 与规则归 Nikoli 所有，本项目未复制其规则文本或插图。
"""


def find_gxx():
    """复用仓库根的 build.py（不要在这里重复一份编译器发现逻辑）。"""
    import build as buildmod  # noqa: E402  (ROOT 已进 sys.path)
    return buildmod.find_gxx()


def build_static_exe(dest):
    """把求解器编译成**静态链接**的单文件 exe 放进发布版。

    返回 (是否成功, 说明文本)。静态版不需要 MinGW 运行时 DLL，
    已在 65 道基准 + 11 道示例上与动态版逐条输出比对一致。
    """
    gxx = find_gxx()
    if not gxx:
        return False, "找不到 g++"
    src = os.path.join(ROOT, "icelom_solver.cpp")
    cmd = [gxx, "-O2", "-std=c++17", "-Wall",
           "-static-libgcc", "-static-libstdc++", "-o", dest, src]
    print("编译(静态):", " ".join('"%s"' % c if " " in c else c for c in cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0 or not os.path.exists(dest):
        return False, "编译失败（exit %d）" % r.returncode
    return True, "%.2f MB 单文件" % (os.path.getsize(dest) / 1024 / 1024)


def smoke_test(pkg):
    """在**打包后的裸目录**里验证：求解器能解题、URL 解码器能跑。"""
    pz = os.path.join(pkg, SMOKE_PUZZLE)
    exe = os.path.join(pkg, "icelom_solver.exe")
    payload = open(pz, "r", encoding="utf-8-sig").read()
    p = subprocess.run([exe], input=payload.encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    counts = [l for l in p.stdout.decode("utf-8", "replace").splitlines() if '"done"' in l]
    if not counts or '"count":1' not in counts[-1].replace(" ", ""):
        return False, "求解冒烟失败: %s" % (counts[-1] if counts else "<无输出>")

    node = shutil.which("node")
    if not node:
        return True, "求解 OK；未找到 node，跳过 URL 解码"
    u = subprocess.run([node, os.path.join(pkg, "tools", "pzprurl2json.js"), SMOKE_URL],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = u.stdout.decode("utf-8", "replace")
    if u.returncode != 0 or "icelom-v1" not in out:
        return False, "URL 解码冒烟失败: %s" % (u.stderr.decode("utf-8", "replace")[:200] or out[:200])
    return True, "求解 OK；URL 解码 OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "release"), help="输出目录（默认 release/）")
    ap.add_argument("--zip", action="store_true", help="额外打成 zip")
    ap.add_argument("--force", action="store_true", help="目标已存在时先删掉")
    ap.add_argument("--no-smoke", action="store_true", help="跳过打包后的冒烟测试")
    args = ap.parse_args()

    dest = os.path.abspath(args.out)
    pkg = os.path.join(dest, "IceLom")
    if os.path.exists(dest):
        if not args.force:
            raise SystemExit("%s 已存在；加 --force 覆盖（会先删除该目录）" % dest)
        shutil.rmtree(dest)
    os.makedirs(pkg)

    cpp = os.path.join(ROOT, "icelom_solver.cpp")
    if not os.path.exists(cpp):
        raise SystemExit("缺少 icelom_solver.cpp")

    copied, missing = [], []
    for rel, sub in FILES:
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.exists(src):
            missing.append(rel)
            continue
        dst = os.path.join(pkg, sub, os.path.basename(rel)) if sub \
            else os.path.join(pkg, os.path.basename(rel))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(os.path.relpath(dst, dest).replace("\\", "/"))

    # 1. 求解器：编译静态单文件版（编译不了才退回"动态 exe + 运行时 DLL"）
    exe_dst = os.path.join(pkg, "icelom_solver.exe")
    ok, note = build_static_exe(exe_dst)
    if ok:
        copied.append("IceLom/icelom_solver.exe")
        print("求解器: 静态单文件（%s）" % note)
    else:
        root_exe = os.path.join(ROOT, "icelom_solver.exe")
        if not os.path.exists(root_exe):
            raise SystemExit("静态编译失败（%s）且仓库根没有 icelom_solver.exe —— 先跑 python build.py" % note)
        if os.path.getmtime(root_exe) < os.path.getmtime(cpp):
            raise SystemExit("icelom_solver.exe 比 icelom_solver.cpp 旧 —— 先重新编译")
        shutil.copy2(root_exe, exe_dst)
        copied.append("IceLom/icelom_solver.exe")
        print("[警告] 静态编译不可用（%s），退回动态 exe + 运行时 DLL" % note)
        for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll"):
            for d in (ROOT, r"C:\mingw64\bin"):
                p = os.path.join(d, dll)
                if os.path.exists(p):
                    shutil.copy2(p, os.path.join(pkg, dll))
                    copied.append("IceLom/" + dll)
                    break

    # 2. 目录（示例题面）
    for srcdir, sub, exts in DIRS:
        src = os.path.join(ROOT, srcdir)
        for fn in sorted(os.listdir(src)):
            if exts and not fn.lower().endswith(exts):
                continue
            dst = os.path.join(pkg, sub, fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(src, fn), dst)
            copied.append(os.path.relpath(dst, dest).replace("\\", "/"))

    # 3. README
    with open(os.path.join(pkg, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(README % {"version": VERSION, "repo": REPO_URL, "smoke_url": SMOKE_URL})
    copied.append("IceLom/README.md")

    # 4. 清单
    manifest = sorted(copied)
    with open(os.path.join(dest, "MANIFEST.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("IceLom %s 发布版内容清单（由 tools/make_release.py 生成）\n" % VERSION)
        f.write("共 %d 个文件\n\n" % len(manifest))
        for c in manifest:
            size = os.path.getsize(os.path.join(dest, c.replace("/", os.sep)))
            f.write("%9d  %s\n" % (size, c))

    total = sum(os.path.getsize(os.path.join(dp, fn))
                for dp, _, fns in os.walk(pkg) for fn in fns)
    nfiles = sum(len(fns) for _, _, fns in os.walk(pkg))
    print("发布版: %s (%d 个文件, %.2f MB)" % (pkg, nfiles, total / 1024 / 1024))
    for c in manifest:
        print("  " + c)
    if missing:
        print("\n[警告] 以下文件在仓库里不存在, 已跳过: %s" % ", ".join(missing))

    # 5. 冒烟（在这个裸目录里，而不是开发仓库里）
    if not args.no_smoke:
        good, msg = smoke_test(pkg)
        print("冒烟: %s" % msg)
        if not good:
            raise SystemExit("发布版冒烟失败，已中止")

    if args.zip:
        zpath = os.path.join(dest, "IceLom-%s-win64.zip" % VERSION)
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for dp, _, fns in os.walk(pkg):
                for fn in fns:
                    full = os.path.join(dp, fn)
                    z.write(full, os.path.relpath(full, dest).replace("\\", "/"))
        print("\n打包: %s (%.2f MB)" % (zpath, os.path.getsize(zpath) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
