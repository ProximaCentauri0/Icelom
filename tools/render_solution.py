# -*- coding: utf-8 -*-
"""把某个解画成 PNG (与界面「导出解为图片」同一高保真渲染器 icelom_render)。

用法: python tools/render_solution.py <谜题.json> <解.json> <输出.png> [格边长] [标题]
解 JSON 支持 {"path":[[x,y],...]} 或直接 [[x,y],...]。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import icelom_render


def main():
    puz = json.load(open(sys.argv[1], encoding="utf-8"))
    raw = json.load(open(sys.argv[2], encoding="utf-8"))
    out = sys.argv[3]
    cell = int(sys.argv[4]) if len(sys.argv) > 4 else 64
    title = sys.argv[5] if len(sys.argv) > 5 else ""
    path = [tuple(p) for p in (raw["path"] if isinstance(raw, dict) else raw)]
    scale = max(2, min(8, int(round(256.0 / max(8, cell)))))
    size = icelom_render.render_to_file(puz, path, out, cell=cell, scale=scale,
                                        title=title)
    print("saved", out, size)


if __name__ == "__main__":
    main()
