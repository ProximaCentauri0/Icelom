// decode_all.js — 批量把 puzz.link/db 收集的 icelom 题面 URL 解码为求解器 JSON
// 用法: node benchmark/decode_all.js
// 读取 benchmark/db_icelom_raw.json (puzz.link/db API 拉取的原始记录),
// 输出 benchmark/puzzles/<id>.json 与 benchmark/manifest.json
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const HERE = __dirname;
const ROOT = path.join(HERE, "..");
const URL_TOOL = path.join(ROOT, "tools", "pzprurl2json.js");
const RAW = path.join(HERE, "db_icelom_raw.json");
const PUZZLE_DIR = path.join(HERE, "puzzles");
fs.mkdirSync(PUZZLE_DIR, { recursive: true });

const raw = JSON.parse(fs.readFileSync(RAW, "utf8"));

// 变体题 (URL 带 v:/) 采用非标准规则, 本地管线按官方标准规则求解不公平 → 剔除但记录
function isVariant(e) {
    return /icelom\/v:\//.test(e.url) || (e.tags_default || []).includes("variant");
}

function slug(s) {
    return String(s).toLowerCase()
        .replace(/^https?:\/\//, "")
        .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "src";
}

// 从 URL 提取尺寸: .../icelom/a/W/H/...  (icelom2 同构)
function sizeOf(url) {
    const m = url.match(/icelom2?\/a\/(\d+)\/(\d+)\//);
    return m ? { w: +m[1], h: +m[2] } : { w: null, h: null };
}

const entries = [];
const seen = new Set();
for (const e of raw) {
    if (seen.has(e.url)) continue;
    seen.add(e.url);
    const { w, h } = sizeOf(e.url);
    const variant = isVariant(e);
    const id = `db${String(entries.length + 1).padStart(3, "0")}_${w}x${h}_${slug(e.source_name)}`;
    entries.push({
        id, url: e.url, w, h, variant,
        source_name: e.source_name,
        source_type: e.source_type,
        source_url: e.source_url,
        published_at: e.published_at,
        db_type: e.type,
        file: null, decode: "pending", decode_msg: "",
        n_numbers: 0, n_qmark: 0, n_ice: 0, n_edges: 0,
    });
}

let ok = 0, fail = 0, skipped = 0;
for (const e of entries) {
    if (e.variant) {
        e.decode = "skipped_variant";
        e.decode_msg = "pzprjs 变体模式 (v:/), 非标准规则";
        skipped++;
        console.log(`[SKIP] ${e.id} variant`);
        continue;
    }
    const out = path.join(PUZZLE_DIR, e.id + ".json");
    try {
        execFileSync("node", [URL_TOOL, e.url, out], { timeout: 120000, stdio: "ignore" });
        const puz = JSON.parse(fs.readFileSync(out, "utf8"));
        if (puz.format !== "icelom-v1") throw new Error("bad format " + puz.format);
        if (e.w && (puz.w !== e.w || puz.h !== e.h)) throw new Error(`size mismatch url=${e.w}x${e.h} json=${puz.w}x${puz.h}`);
        if (!puz.in || !puz.out) throw new Error("missing IN/OUT");
        // 数字保持题面原值(作者可能跳号, 且 "?" 格的位次要靠原值判断), 不再按位次重编号。
        // n = -2 表示 "?" 格(数字未知的编号格), 与已知数字一起参与"位次"规则。
        const known = puz.numbers.filter(n => n.n > 0).map(n => n.n);
        const qmarks = puz.numbers.filter(n => n.n === -2).length;
        if (new Set(known).size !== known.length) throw new Error("duplicate numbers " + JSON.stringify(known));
        puz.numbers.sort((a, b) => (b.n - a.n) || (a.y - b.y) || (a.x - b.x));
        fs.writeFileSync(out, JSON.stringify(puz));
        e.file = path.relative(ROOT, out).replace(/\\/g, "/");
        e.w = puz.w; e.h = puz.h;
        e.n_numbers = known.length;
        e.n_qmark = qmarks;
        e.n_ice = puz.cells.filter(c => c === "i").length;
        e.n_edges = (puz.edges || []).length;
        e.decode = "ok";
        ok++;
        console.log(`[OK]   ${e.id} (${e.w}x${e.h}, nums=${e.n_numbers}, qmark=${e.n_qmark}, ice=${e.n_ice}, edges=${e.n_edges})`);
    } catch (err) {
        // 解码器失败时会把 {"type":"error",...} 写进输出文件(沙箱下无法用管道取输出)
        let msg = String((err && err.message) || err).slice(0, 300);
        try {
            const o = JSON.parse(fs.readFileSync(out, "utf8"));
            if (o && o.type === "error" && o.message) msg = o.message;
        } catch (_) { /* 文件不存在或不是错误 JSON */ }
        e.decode = "error";
        e.decode_msg = msg;
        fail++;
        console.log(`[FAIL] ${e.id}: ${e.decode_msg}`);
    }
}

fs.writeFileSync(path.join(HERE, "manifest.json"), JSON.stringify(entries, null, 1));
console.log(`\ndone: ok=${ok} fail=${fail} skipped_variant=${skipped} total=${entries.length}`);
