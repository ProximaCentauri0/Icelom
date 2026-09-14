// scan_marks.js — 扫描 benchmark/manifest.json 中每题 URL 的题面要素统计:
// 冰格 / 已知数字 / "?" 格(qnum<=-2, 数字未知的编号格) / 非白非冰格 / 边标记。
// "?" 格现已支持(写入 JSON 时 n = -2), 这里只做统计与体检。
// 用法: node scan_marks.js
const path = require("path");
const fs = require("fs");
const ROOT = path.join(__dirname, "..");
const pzpr = require(path.join(ROOT, "tools", "pzprjs", "pzpr.concat.js"));
const variety = require(path.join(ROOT, "tools", "pzprjs", "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "benchmark", "manifest.json"), "utf8"));
const entries = manifest.filter(e => e.decode === "ok" && e.url);

let pending = entries.length;
const results = [];
entries.forEach((e) => {
    const p = new pzpr.Puzzle();
    p.open(e.url, () => {
        const bd = p.board;
        const W = bd.cols, H = bd.rows;
        let ice = 0, known = 0;
        const qmarks = [];
        const weird = [];
        for (let y = 0; y < H; y++) {
            for (let x = 0; x < W; x++) {
                const c = bd.cell[y * W + x];
                if (c.ques === 6) ice++;
                if (c.isNum() && c.qnum >= 0) known++;
                if (c.qnum <= -2) qmarks.push([x, y, c.ques === 6 ? "ice" : "white"]);
                if (c.ques !== 0 && c.ques !== 6) weird.push([x, y, "ques=" + c.ques]);
            }
        }
        results.push({ id: e.id, w: W, h: H, ice, known, qmarks, weird });
        if (--pending === 0) report();
    });
    p.on("fail-open", () => { results.push({ id: e.id, error: "open failed" }); if (--pending === 0) report(); });
});

function report() {
    const withQ = results.filter(r => r.qmarks && r.qmarks.length);
    const bad = results.filter(r => (r.weird && r.weird.length) || r.error);
    console.log("扫描题数:", results.length);
    console.log("含 \"?\" 格的题:", withQ.length);
    for (const r of withQ) {
        console.log(`  ${r.id}  ${r.w}x${r.h}  冰=${r.ice} 数字=${r.known}  "?"=${r.qmarks.length}`);
        console.log("     ?格位置:", JSON.stringify(r.qmarks));
    }
    console.log("含非白非冰格的题:", bad.length);
    for (const r of bad) {
        console.log("  " + r.id);
        if (r.error) console.log("     error:", r.error);
        if (r.weird && r.weird.length) console.log("     非白非冰格:", JSON.stringify(r.weird));
    }
    if (!bad.length) console.log("全部题目都只含 白格/冰格/已知数字/\"?\" 格 —— 与求解器数据模型一致");
}
