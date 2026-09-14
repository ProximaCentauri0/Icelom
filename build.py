# -*- coding: utf-8 -*-
"""build.py — 编译 C++ 求解器（发布版/开发仓库通用）。

用法:
    python build.py                 # 自动找 g++（PATH → ICELOM_GXX → 常见安装位置）
    python build.py --gxx <路径>    # 指定编译器
    python build.py --static        # 静态链接（产物不依赖 MinGW 运行时 DLL）

产物 `icelom_solver.exe` **必须**与本脚本同目录（`icelom_gui.py` 用 `__file__` 定位它）。
编译参数与 `tools/taskset.ps1 build` 一致: `-O2 -std=c++17 -Wall`。
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "icelom_solver.cpp")
OUT = os.path.join(HERE, "icelom_solver.exe")
CANDIDATES = [
    r"C:\mingw64\bin\g++.exe",
    r"C:\msys64\mingw64\bin\g++.exe",
    r"C:\Program Files\mingw-w64\mingw64\bin\g++.exe",
    "/usr/bin/g++",
]


def find_gxx(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("ICELOM_GXX"):
        return os.environ["ICELOM_GXX"]
    found = shutil.which("g++")
    if found:
        return found
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gxx", default=None, help="g++ 路径（默认自动查找 / 环境变量 ICELOM_GXX）")
    ap.add_argument("--static", action="store_true",
                    help="静态链接 libgcc/libstdc++（单文件分发，不需要额外 DLL）")
    args = ap.parse_args()

    if not os.path.exists(SRC):
        raise SystemExit("找不到 %s" % SRC)
    gxx = find_gxx(args.gxx)
    if not gxx:
        raise SystemExit("找不到 g++。装 MinGW-w64 后用 --gxx 指定，或设 ICELOM_GXX 环境变量。")

    cmd = [gxx, "-O2", "-std=c++17", "-Wall"]
    if os.name != "nt":
        cmd.append("-pthread")
    if args.static:
        cmd += ["-static-libgcc", "-static-libstdc++"]
    cmd += ["-o", OUT, SRC]
    print("编译:", " ".join('"%s"' % c if " " in c else c for c in cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("编译失败（exit %d）" % r.returncode)
    print("OK -> %s (%d 字节)" % (os.path.basename(OUT), os.path.getsize(OUT)))
    if not args.static:
        need = []
        for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll"):
            if not os.path.exists(os.path.join(HERE, dll)) and not shutil.which(dll):
                need.append(dll)
        if need:
            print("提示: 动态链接的产物需要 %s；发布给别人时把这些 DLL 一起放过来，"
                  "或改用 python build.py --static。" % ", ".join(need))
    return 0


if __name__ == "__main__":
    sys.exit(main())
