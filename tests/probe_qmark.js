// probe_qmark.js — 用 pzprjs 官方引擎判定"某个解是否被官方接受"。
// 用法: node tests/probe_qmark.js <题目URL> <解JSON路径>
//   解 JSON: {"path":[[x,y],...]} 或直接 [[x,y],...]
// 输出: PASS / 失败原因列表 / ERROR
const path = require("path");
const fs = require("fs");
const ROOT = path.join(__dirname, "..", "tools", "pzprjs");
const pzpr = require(path.join(ROOT, "pzpr.concat.js"));
const variety = require(path.join(ROOT, "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

function B(bd, bx, by) {
    for (let i = 0; i < bd.border.length; i++) {
        const b = bd.border[i];
        if (b.bx === bx && b.by === by) return b;
    }
    return null;
}

// 格 (x,y) 与它的邻居之间那条边在 pzpr 里的边框坐标
function edgeBetween(a, b) {
    const [x0, y0] = a, [x1, y1] = b;
    if (x1 === x0 + 1 && y1 === y0) return [2 * x0 + 2, 2 * y0 + 1]; // 右
    if (x1 === x0 - 1 && y1 === y0) return [2 * x0, 2 * y0 + 1];     // 左
    if (y1 === y0 + 1 && x1 === x0) return [2 * x0 + 1, 2 * y0 + 2]; // 下
    if (y1 === y0 - 1 && x1 === x0) return [2 * x0 + 1, 2 * y0];     // 上
    throw new Error("非相邻步: " + JSON.stringify(a) + "->" + JSON.stringify(b));
}

function sideBorder(x, y, side) {
    if (side === "U") return [2 * x + 1, 2 * y];
    if (side === "D") return [2 * x + 1, 2 * y + 2];
    if (side === "L") return [2 * x, 2 * y + 1];
    return [2 * x + 2, 2 * y + 1];
}

const url = process.argv[2];
const solPath = process.argv[3];
const raw = JSON.parse(fs.readFileSync(solPath, "utf8"));
const cellPath = Array.isArray(raw) ? raw : raw.path;
const meta = raw.puzzle ? JSON.parse(fs.readFileSync(path.join(__dirname, "..", raw.puzzle), "utf8")) : null;

const p = new pzpr.Puzzle();
p.open(url, () => {
    try {
        const bd = p.board;
        const inB = bd.arrowin.getb(), outB = bd.arrowout.getb();
        const toSet = new Set();
        const key = (c) => c[0] + "," + c[1];
        toSet.add(key([inB.bx, inB.by]));
        toSet.add(key([outB.bx, outB.by]));
        for (let i = 1; i < cellPath.length; i++) toSet.add(key(edgeBetween(cellPath[i - 1], cellPath[i])));
        let n = 0;
        for (const k of toSet) {
            const [bx, by] = k.split(",").map(Number);
            const b = B(bd, bx, by);
            if (!b) throw new Error("边框不存在: " + k);
            b.setLineVal(1);
            n++;
        }
        const res = p.check();
        const verdict = res.complete ? "PASS" : Array.from(res).join(",");
        console.log("画线边框数:", n, " 官方判定:", verdict);
        // 额外: 报告官方认为每个编号格在第几位(仅诊断用)
        process.exit(0);
    } catch (e) {
        console.log("ERROR", e.message);
        process.exit(1);
    }
});
