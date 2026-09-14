// pzprurl2json.js — 用官方 pzprjs 库把 puzz.link icelom URL 解码为 JSON
// 用法: node pzprurl2json.js "<url>" [out.json]
const path = require("path");
const ROOT = path.join(__dirname, "pzprjs");
const pzpr = require(path.join(ROOT, "pzpr.concat.js"));
const variety = require(path.join(ROOT, "pzpr-variety", "icebarn.js"));
pzpr.classmgr.makeCustom(variety[0], variety[1]);

const url = process.argv[2];
if (!url) {
    console.error("usage: node pzprurl2json.js <url> [out.json]");
    process.exit(2);
}

const puzzle = new pzpr.Puzzle();
puzzle.on("fail-open", () => {
    console.log(JSON.stringify({ type: "error", message: "pzprjs 无法打开该 URL" }));
    process.exit(1);
});

puzzle.open(url, function () {
    try {
        const bd = puzzle.board;
        const w = bd.cols, h = bd.rows;
        const cells = [];
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                cells.push(bd.cell[y * w + x].ques === 6 ? "i" : "w");
            }
        }
        const numbers = [];
        let nQ = 0;
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const c = bd.cell[y * w + x];
                // qnum >= 0: 已知数字; qnum <= -2 是 pzpr 的 "?" 标记(URL 数据里的 '?'):
                // 格子确定是白/冰, 只是上面的数字未知 —— 求解器用 n = -2 表示这种编号格。
                if (c.isNum() && c.qnum >= 0) numbers.push({ x, y, n: c.qnum });
                else if (c.qnum <= -2) { numbers.push({ x, y, n: -2 }); nQ++; }
            }
        }
        // arrowin/arrowout: 边框 Address (bx,by 半格坐标)
        // 横边线: by 偶数 (0=顶框, 2h=底框), bx 奇数 = 格 x
        // 竖边线: bx 偶数 (0=左框, 2w=右框), by 奇数 = 格 y
        function borderInfo(addr) {
            const bx = addr.bx, by = addr.by;
            if (by === 0) return { x: (bx - 1) / 2, y: 0, side: "U" };
            if (by === 2 * h) return { x: (bx - 1) / 2, y: h - 1, side: "D" };
            if (bx === 0) return { x: 0, y: (by - 1) / 2, side: "L" };
            if (bx === 2 * w) return { x: w - 1, y: (by - 1) / 2, side: "R" };
            return null;
        }
        const fin = borderInfo(bd.arrowin) || {};
        const fout = borderInfo(bd.arrowout) || {};
        // 内部边箭头
        const DIRS = {};
        DIRS[bd.border[0].UP] = "U";
        DIRS[bd.border[0].DN] = "D";
        DIRS[bd.border[0].LT] = "L";
        DIRS[bd.border[0].RT] = "R";
        const edges = [];
        for (let i = 0; i < bd.border.length; i++) {
            const b = bd.border[i];
            if (!b.qdir || !b.inside) continue;
            const bx = b.bx, by = b.by;
            let key, dir;
            if (b.isHorz()) {
                const x = (bx - 1) / 2, y = by / 2; // (x, y-1)-(x, y) 之间的边
                if (y < 1 || y > h - 1) continue;
                key = { x, y: y - 1, side: "D" };
            } else {
                const x = bx / 2, y = (by - 1) / 2; // (x-1, y)-(x, y) 之间的边
                if (x < 1 || x > w - 1) continue;
                key = { x: x - 1, y, side: "R" };
            }
            dir = DIRS[b.qdir];
            if (!dir) continue;
            edges.push({ x: key.x, y: key.y, side: key.side, kind: "arrow", dir });
        }
        const out = {
            format: "icelom-v1",
            w, h, cells, numbers, n_qmark: nQ,
            in: Object.keys(fin).length ? fin : null,
            out: Object.keys(fout).length ? fout : null,
            edges,
            options: { cover_all_whites: true },
        };
        const text = JSON.stringify(out);
        if (process.argv[3]) {
            require("fs").writeFileSync(process.argv[3], text);
            console.log("WROTE " + process.argv[3]);
        } else {
            console.log(text);
        }
    } catch (e) {
        console.log(JSON.stringify({ type: "error", message: "解析失败: " + e.message }));
        process.exit(1);
    }
});
