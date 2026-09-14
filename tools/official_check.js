// official_check.js — 用**未经修改的官方 pzprjs 引擎**判定一个 icelom-v1 题面的解。
//
// 用法: node tools/official_check.js <题面.json> [解.json]
//   题面: icelom-v1（w/h/cells/numbers/in/out/edges）
//   解  : {"path":[[x,y],…]} 或直接 [[x,y],…]；省略则读题面同目录的 icon_solution.json 同级命名：
//         优先 <题面名>_solution.json，其次题面 JSON 里的 "solution" 字段
// 输出: `官方判定: PASS` 或官方报出的 failcode 列表（非 0 退出码 = 不通过）
//
// 为什么不用 URL
// --------------
// 官方 pzprjs 只在浏览器侧把 URL 解码成盘面（`Puzzle.open`），"题面 JSON → URL"这条方向
// 官方没有可用的命令行入口。所以这里换一条更稳的路：**先开一张同尺寸的空盘，
// 再按 icelom-v1 直接设置格子的属性与边框**，最后调官方 `check()`。
// 盘面对象、规则实现、判定逻辑全部来自 vendored 的官方引擎，本文件只做数据搬运。
//
// 覆盖范围: 冰/白格、数字、"?（qnum = -2）"、IN/OUT（含内部与角冰格）、箭头（qdir）。
//   「墙」是本项目的本地扩展（官方规则里没有），官方 `check()` 不校验它；
//   带墙的题面请用独立验证器（`python tools/verify_solution.py`）核对约束后再看官方结论。
"use strict";
const path = require("path");
const fs = require("fs");
const PZ = path.join(__dirname, "..", "tools", "pzprjs");
const pzpr = require(path.join(PZ, "pzpr.concat.js"));
const variety = require(path.join(PZ, "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

const DIRV = { R: [1, 0], D: [0, 1], L: [-1, 0], U: [0, -1] };
const ID6 = "0123456789abcdefghijklmnopqrstuvwxyz";

/** 空盘 URL：只用来让官方引擎按 w×h 建好盘面，题面内容随后直接设置。 */
function bootUrl(w, h) {
    const n = w * h;
    const ice = "0".repeat(Math.ceil(n / 5));
    const idoffset = 2 * w * h - w - h;
    const inId = 1, outId = 2;
    const borders = "0".repeat(2 * w * h - 2 * w - 2 * h + 2);
    const body = [ice, "", inId, outId, borders].join("/");
    return "https://puzz.link/p?icelom/a/" + w + "/" + h + "/" + body;
}

function edgeKey(x, y, side, w, h) {
    const [dx, dy] = DIRV[side];
    const nx = x + dx, ny = y + dy;
    if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
        if (side === "R") return [x, y, "R"];
        if (side === "L") return [x - 1, y, "R"];
        if (side === "D") return [x, y, "D"];
        return [x, y - 1, "D"];
    }
    return [x, y, side];
}

function borderXY(x, y, side) {
    if (side === "U") return [2 * x + 1, 2 * y];
    if (side === "D") return [2 * x + 1, 2 * y + 2];
    if (side === "L") return [2 * x, 2 * y + 1];
    return [2 * x + 2, 2 * y + 1];
}

function main() {
    const puzFile = process.argv[2];
    if (!puzFile) {
        console.log("用法: node tools/official_check.js <题面.json> [解.json]");
        process.exit(2);
    }
    const puz = JSON.parse(fs.readFileSync(puzFile, "utf8"));
    const W = puz.w, H = puz.h;

    // 解：命令行 > 同目录 <题面名>_solution.json > 题面内联 "solution"
    let solFile = process.argv[3];
    if (!solFile) {
        const guess = puzFile.replace(/\.json$/i, "_solution.json");
        if (fs.existsSync(guess)) solFile = guess;
    }
    let cellPath = null;
    if (solFile) {
        const raw = JSON.parse(fs.readFileSync(solFile, "utf8"));
        cellPath = Array.isArray(raw) ? raw : raw.path;
    } else if (puz.solution) {
        cellPath = puz.solution;
    }
    if (!cellPath) {
        console.log("找不到解（命令行没给，也没有 " + puzFile.replace(/\.json$/i, "_solution.json") + "）");
        process.exit(2);
    }

    const p = new pzpr.Puzzle();
    p.open(bootUrl(W, H), () => {
        const bd = p.board;
        if (bd.cols !== W || bd.rows !== H) {
            console.log("官方引擎建出的盘面尺寸不符: " + bd.cols + "×" + bd.rows);
            process.exit(1);
        }
        const cells = Array.from(bd.cell);
        const borders = Array.from(bd.border);
        const C = (x, y) => cells[y * W + x];
        const B = (bx, by) => borders.find((b) => b.bx === bx && b.by === by);

        // ---- 题面：冰格 / 数字 / "?" ----
        for (let y = 0; y < H; y++) {
            for (let x = 0; x < W; x++) {
                const c = C(x, y);
                c.ques = 0;
                c.qnum = -1;
                if (puz.cells[y * W + x] === "i") c.ques = 6;
            }
        }
        for (const n of puz.numbers || []) C(n.x, n.y).qnum = n.n;

        // ---- 题面：边标记（箭头 = 官方 qdir；墙 = 官方没有, 跳过并计数） ----
        let nArrow = 0, nWall = 0, nSeg = 0;
        for (const e of puz.edges || []) {
            const [kx, ky, side] = edgeKey(e.x, e.y, e.side, W, H);
            const [bx, by] = borderXY(kx, ky, side);
            const b = B(bx, by);
            if (!b) continue;
            if (e.kind === "arrow" && e.dir) {
                const [dx, dy] = DIRV[e.dir];
                const vert = bx % 2 === 0;
                b.setArrow(vert ? (dy < 0 ? 1 : 2) : (dx < 0 ? 1 : 2));
                nArrow++;
            } else if (e.kind === "wall") {
                nWall++;
            } else if (e.kind === "segment") {
                nSeg++;
            }
        }

        // ---- IN / OUT（含内部与角冰格）----
        const [ibx, iby] = borderXY(puz.in.x, puz.in.y, puz.in.side);
        const [obx, oby] = borderXY(puz.out.x, puz.out.y, puz.out.side);
        const inB = B(ibx, iby), outB = B(obx, oby);
        if (!inB || !outB) {
            console.log("IN/OUT 边框不存在: " + ibx + "," + iby + " / " + obx + "," + oby);
            process.exit(1);
        }
        bd.arrowin.input(inB);
        bd.arrowout.input(outB);

        // ---- 解：画线（IN/OUT 自身所在边框也算一条线）----
        const toSet = new Set([inB.bx + "," + inB.by, outB.bx + "," + outB.by]);
        for (let i = 1; i < cellPath.length; i++) {
            const [x0, y0] = cellPath[i - 1], [x1, y1] = cellPath[i];
            let bx, by;
            if (x1 === x0 + 1) { bx = 2 * x0 + 2; by = 2 * y0 + 1; }
            else if (x1 === x0 - 1) { bx = 2 * x0; by = 2 * y0 + 1; }
            else if (y1 === y0 + 1) { bx = 2 * x0 + 1; by = 2 * y0 + 2; }
            else if (y1 === y0 - 1) { bx = 2 * x0 + 1; by = 2 * y0; }
            else {
                console.log("解里出现非相邻步: " + JSON.stringify([x0, y0]) + "→" + JSON.stringify([x1, y1]));
                process.exit(1);
            }
            toSet.add(bx + "," + by);
        }
        let nLine = 0;
        for (const k of toSet) {
            const [bx, by] = k.split(",").map(Number);
            const b = B(bx, by);
            if (!b) {
                console.log("边框不存在: " + k);
                process.exit(1);
            }
            b.setLineVal(1);
            nLine++;
        }

        const res = p.check();
        const verdict = res.complete ? "PASS" : Array.from(res).join(",");
        console.log("题面: " + W + "×" + H + "  冰格 " + (puz.cells.filter(c => c === "i").length) +
            "  编号格 " + (puz.numbers || []).length +
            "  箭头 " + nArrow + "  线段 " + nSeg + "  墙 " + nWall);
        console.log("画线边框数: " + nLine);
        console.log("官方判定: " + verdict);
        if (nWall) console.log("注: 墙是本项目的本地扩展, 官方规则不校验(已跳过 " + nWall + " 条)");
        process.exit(res.complete ? 0 : 1);
    });
}

main();
