// probe_rules.js — 用 pzprjs 官方 check() 探明 icelom 边界语义
const path = require("path");
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

function probe(name, size, ice, lines, inb, outb) {
    return new Promise((resolve) => {
        const p = new pzpr.Puzzle();
        p.open("?icelom/" + size, () => {
            try {
                const bd = p.board;
                for (const c of ice) bd.cell[c].setQues(6);
                bd.arrowin.input(B(bd, inb[0], inb[1]));
                bd.arrowout.input(B(bd, outb[0], outb[1]));
                for (const [bx, by] of lines) B(bd, bx, by).setLineVal(1);
                const res = p.check();
                const verdict = res.complete ? "PASS" : Array.from(res).join(",");
                console.log(name.padEnd(40), "=>", verdict);
                resolve();
            } catch (e) {
                console.log(name.padEnd(40), "=> ERROR", e.message);
                resolve();
            }
        });
    });
}

(async () => {
    // T1 基础: 2x1 全白, IN 上(0,0), OUT 右(1,0)
    await probe("T1 基础白格直线(应PASS)", "2/1", [],
        [[1, 0], [2, 1], [4, 1]], [1, 0], [4, 1]);

    // T2 冰起点直行: 2x2, (0,0)冰, IN 上(0,0) 向下入→下→右→右框出
    await probe("T2 冰起点直行(应PASS)", "2/2", [0],
        [[1, 0], [1, 2], [2, 3], [3, 2], [4, 1]], [1, 0], [4, 1]);

    // T3 冰起点转弯: 3x2, (0,0)冰, IN 上(0,0) 向下入→出发向右(转弯)
    //    (0,0)->(1,0)->(2,0)->(2,1)->(1,1)->(0,1)->左框出
    await probe("T3 冰起点转弯(违反?)", "3/2", [0],
        [[1, 0], [2, 1], [4, 1], [5, 2], [4, 3], [2, 3], [0, 3]], [1, 0], [0, 3]);

    // T4 冰终点直行: 2x1, (1,0)冰, (0,0)->(1,0)->右框出 (直行)
    await probe("T4 冰终点直行(应PASS)", "2/1", [1],
        [[1, 0], [2, 1], [4, 1]], [1, 0], [4, 1]);

    // T5 冰终点转弯: 3x2, (2,1)冰, IN 上(0,0), OUT 右(2,1)
    //    (0,0)->(0,1)->(1,1)->(1,0)->(2,0)->(2,1)->右框出 (进入向下, 出框向右 = 转弯)
    await probe("T5 冰终点转弯(违反?)", "3/2", [5],
        [[1, 0], [1, 2], [2, 3], [3, 2], [4, 1], [5, 2], [6, 3]], [1, 0], [6, 3]);

    // T7 白格转弯(对照, 应PASS): 2x2, IN 上(0,0), OUT 左(0,1)
    await probe("T7 白格转弯对照(应PASS)", "2/2", [],
        [[1, 0], [2, 1], [3, 2], [2, 3], [0, 3]], [1, 0], [0, 3]);
})();
