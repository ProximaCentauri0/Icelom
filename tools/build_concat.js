// build_concat.js — 从 vendored pzprjs 源码重建 dist/js/pzpr.concat.js
//
// 背景: 官方 grunt 构建会派生子进程(受限环境下不可用), 这里只复刻 "concat + 模板替换" 两步。
// 输入: tools/pzprjs 下的精简源码树(src/ + src-ui/res/ + package.json + node_modules/pzpr-canvas)
// 输出: tools/pzprjs/dist/js/pzpr.concat.js 与 dist/js/pzpr-variety/*.js
//       —— 运行时用的是 tools/pzprjs/pzpr.concat.js 与 tools/pzprjs/pzpr-variety/,
//          重建后请把 dist/js 下的产物覆盖到上层两份文件(见 tools/taskset.ps1 build-pzpr)。
//
// 用法: node tools/build_concat.js
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "pzprjs");
const OUT = path.join(ROOT, "dist", "js");
const files = require(path.join(ROOT, "src", "pzpr.js")).files;

function readJSON(p, def) {
    try { return JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf-8")); }
    catch (e) { return def; }
}
const tmplData = {
    git: readJSON("git.json", { hash: "dev" }),
    pkg: readJSON("package.json", {}),
    langs: {
        p_en: readJSON("src-ui/res/p.en.json", {}),
        p_ja: readJSON("src-ui/res/p.ja.json", {}),
        failcode_en: readJSON("src/res/failcode.en.json", {}),
        failcode_ja: readJSON("src/res/failcode.ja.json", {}),
    },
};
tmplData.grunt = { template: { today: () => new Date().toISOString().slice(0, 10) } };

function processTpl(text) {
    if (!text.includes("<%")) return text;
    const keys = Object.keys(tmplData);
    const fn = new Function(...keys, "return `" + text.replace(/<%=([\s\S]*?)%>/g, (m, e) => "${" + e + "}").replace(/`/g, "\\`") + "`;");
    return fn(...keys.map(k => tmplData[k]));
}

const out = [];
for (const f of files) {
    let p = path.join(ROOT, f);
    if (!p.endsWith(".js")) p += ".js";
    out.push("// ==== " + f + " ====\n" + processTpl(fs.readFileSync(p, "utf-8")));
}
fs.mkdirSync(path.join(OUT, "pzpr-variety"), { recursive: true });
fs.writeFileSync(path.join(OUT, "pzpr.concat.js"), out.join("\n"));
const vsrc = path.join(ROOT, "src", "variety");
for (const f of fs.readdirSync(vsrc)) {
    fs.copyFileSync(path.join(vsrc, f), path.join(OUT, "pzpr-variety", f));
}
console.log("CONCAT OK", out.length, "files ->", path.relative(process.cwd(), OUT));
