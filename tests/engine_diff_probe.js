// engine_diff_probe.js — 用 pzprjs 官方 icelom check() 判定一组状态, 供差分测试比对。
// 用法: node engine_diff_probe.js <states.json>
// states.json: [{name, pid?, w, h, ice:[cellIndex...], numbers:{cellIndex: n},
//                in:[bx,by], out:[bx,by], arrows:[[bx,by,1|2|3|4]...], lines:[[bx,by]...]}, ...]
//   arrows 的 1/2/3/4 = UP/DN/LT/RT; **含箭头时必须用 pid "icebarn"** —— pzprjs 的
//   `checkFollowArrow@icebarn`/`checkAllArrow@icebarn` 会按 pzpr.util.checkpid("icebarn", pid)
//   过滤, pid = "icelom" 时这两项被判为"不适用"而整条剔除, 于是官方引擎对 icelom 完全不校验箭头。
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "tools", "pzprjs");
const pzpr = require(path.join(ROOT, "pzpr.concat.js"));
const variety = require(path.join(ROOT, "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

const states = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

function B(bd, bx, by) {
    for (let i = 0; i < bd.border.length; i++) {
        const b = bd.border[i];
        if (b.bx === bx && b.by === by) return b;
    }
    return null;
}

(async () => {
    const out = [];
    for (const st of states) {
        const res = await new Promise((resolve) => {
            const p = new pzpr.Puzzle();
            p.open("?" + (st.pid || "icelom") + "/" + st.w + "/" + st.h, () => {
                try {
                    const bd = p.board;
                    for (const c of st.ice) bd.cell[c].setQues(6);
                    for (const [idx, n] of Object.entries(st.numbers)) {
                        bd.cell[+idx].setNum(n);
                    }
                    bd.arrowin.input(B(bd, st.in[0], st.in[1]));
                    bd.arrowout.input(B(bd, st.out[0], st.out[1]));
                    for (const [bx, by, dir] of st.arrows || []) {
                        const b = B(bd, bx, by);
                        if (!b) throw new Error("border not found: " + bx + "," + by);
                        b.setArrow(dir);
                    }
                    for (const [bx, by] of st.lines) {
                        const b = B(bd, bx, by);
                        if (!b) throw new Error("border not found: " + bx + "," + by);
                        b.setLineVal(1);
                    }
                    // check(true) = 完整判定 (累积全部 failcode); 不带参数是只报首要原因的快速判定
                    const r = p.check(true);
                    resolve({
                        complete: !!r.complete,
                        codes: Array.from(r).map(String),
                        lastcode: r.lastcode === undefined ? null : String(r.lastcode),
                        text: r.text === undefined ? null : String(r.text),
                    });
                } catch (e) {
                    resolve({ error: String((e && e.message) || e) });
                }
            });
        });
        out.push(Object.assign({ name: st.name }, res));
    }
    console.log(JSON.stringify(out));
})();
