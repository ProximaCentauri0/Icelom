// dump_cells_url.js — 用官方引擎打印某个题的每格 qnum / ques(核对 "?" 格与冰格)
const path = require("path");
const ROOT = path.join(__dirname, "..", "tools", "pzprjs");
const pzpr = require(path.join(ROOT, "pzpr.concat.js"));
const variety = require(path.join(ROOT, "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

const url = process.argv[2];
const p = new pzpr.Puzzle();
p.open(url, () => {
    const bd = p.board;
    const out = [];
    for (let i = 0; i < bd.cell.length; i++) {
        const c = bd.cell[i];
        if (c.qnum !== -1 || c.ques === 6) {
            out.push(`(${c.bx !== undefined ? "" : ""}${c.bx},${c.by}) qnum=${c.qnum} ques=${c.ques} isNum=${c.isNum()}`);
        }
    }
    console.log("size:", bd.cols, "x", bd.rows);
    console.log("编号格/冰格:");
    for (const l of out) console.log("  ", l);
    console.log("qnum<=-2 的格数:", bd.cell.filter(c => c.qnum <= -2).length);
});
