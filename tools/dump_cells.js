// dump_cells.js — 用官方 pzprjs 加载 URL, 打印每个格子的原始属性(ques/qnum/qdir 等)
// 用法: node dump_cells.js "<url>"
const path = require("path");
const ROOT = path.join(__dirname, "..", "tools", "pzprjs");
const pzpr = require(path.join(ROOT, "pzpr.concat.js"));
const variety = require(path.join(ROOT, "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

const url = process.argv[2];
const p = new pzpr.Puzzle();
p.open(url, () => {
    const bd = p.board;
    const W = bd.cols, H = bd.rows;
    console.log("size:", W + "x" + H);
    const byQues = {};
    let unknown = [];
    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const c = bd.cell[y * W + x];
            const key = `ques=${c.ques},qnum=${c.qnum},qdir=${c.qdir},qans=${c.qans},qsub=${c.qsub}`;
            byQues[key] = (byQues[key] || 0) + 1;
            if (c.ques !== 0 && c.ques !== 6) unknown.push([x, y, c.ques, c.qnum]);
        }
    }
    console.log("格子属性分布:");
    for (const k of Object.keys(byQues)) console.log("   " + k + "  x" + byQues[k]);
    if (unknown.length) {
        console.log("非白非冰(ques != 0/6)的格子:", JSON.stringify(unknown));
    } else {
        console.log("所有格子都是 白(ques=0) 或 冰(ques=6)");
    }
    // 冰格数量与数字
    let ice = 0, nums = [];
    for (let y = 0; y < H; y++)
        for (let x = 0; x < W; x++) {
            const c = bd.cell[y * W + x];
            if (c.ques === 6) ice++;
            if (c.qnum >= 0 && c.qnum !== -1) nums.push([x, y, c.qnum]);
        }
    console.log("冰格:", ice, "| 数字:", JSON.stringify(nums));
    console.log("IN :", bd.arrowin ? `(${bd.arrowin.bx},${bd.arrowin.by})` : "(none)");
    console.log("OUT:", bd.arrowout ? `(${bd.arrowout.bx},${bd.arrowout.by})` : "(none)");
    // 边框标记
    const marks = [];
    for (const b of bd.border) {
        if (b.qdir || b.qnum || b.ques) marks.push([b.bx, b.by, "qdir=" + b.qdir, "ques=" + b.ques, "qnum=" + b.qnum]);
    }
    console.log("边框标记:", JSON.stringify(marks));
});
