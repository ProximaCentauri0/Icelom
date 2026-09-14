// icelom_solver.cpp — 冰宫巡游 (IceLom) 通用求解器后端 v2
//
// 规则（Nikoli IceLom / アイスローム，本实现采用的扩展，与 v1 相同）：
//   1. 从 IN 进入、OUT 离开，画一条不分叉、不重叠的单一线路，线路走格子中心。
//   2. 白格：线路至多经过一次，格内可以转弯；默认要求所有白格都必须经过（可关闭）。
//   3. 冰格（蓝格）：不能转弯（进入后必须直行穿出），不允许同轴重叠；
//      只有冰格上允许线路交叉（每格至多横、竖各一次）。冰格不必全部经过。
//   4. 编号格：线路按**升序**经过，每个编号格恰好经过一次（数字可放白格或冰格；
//      冰上编号格只直行通过一次、不可被交叉）。数字**不必连续**（题面可跳号 1,3,5,…），
//      并支持 **"?" 格**：数字未知的编号格（格子确定是白/冰，只是没印数字）。
//      判定方式：只要**存在**一种给 "?" 填数字的方案，使线上数字严格递增即可 ——
//      等价于：把线路上的编号格（已知数字 + "?"）依次记为第 1,2,3,… 位，已知数字 v
//      在第 p 位时记 d = v - p，则沿线路 d 单调不减、且起点侧首个 d >= 0
//      （即"两数之差 > 两数之间的问号个数"）。所有编号格（含 "?"）都必须被经过。
//   5. 格间标记（相邻两格公共边，或外边框）：
//      - 线段 segment：线路必须经过这条边（方向任意）；
//      - 箭头 arrow：线路必须按箭头方向经过这条边；
//      - 墙 wall：线路禁止经过这条边。
//      外边框上的标记只有 IN/OUT 所在边可被满足（线路只能从 IN 进、OUT 出）。
//
// 求解算法 —— **规则级约束传播 + 单边试连接（推到不动点）+ 固定顺序枚举**
// （stdin/stdout 协议与历史版本完全一致；算法细节见 docs/算法说明.md §3.4–3.13）：
//   - 唯一状态：每条内部边一个三态 est[e] ∈ {未定, 必用, 禁用}（墙与推理结论都记在这里），
//     全部改动走回溯轨迹 trail。
//   - 节点模型：白格 1 个节点；冰格横/竖两轴各 1 个节点（交叉两侧互不连通）。
//     IN/OUT 的入框/出框边（内部 IN/OUT 为虚拟边）也算该格一条连接 ⇒
//     "穿越次数 = 连接总数/2"。格内合法性见 configLegal()：白格总连接 2（或 0/2 可跳过）、
//     冰格每轴 0 或 2、已知数字恰穿越一次、"?" 一或两次（计数强制时必须两次）。
//   - 推理（propagate() 推到不动点）：ruleCells（格内配置枚举：共有边⇒必用、
//     都不含⇒禁用、无配置⇒矛盾）/ ruleNums / ruleCycles / ruleReach / ruleComponents /
//     ruleProbe（逐格逐方向试连接：试"用"走不通⇒必禁、试"禁"没走法⇒必用、剩下的走法
//     共有的边⇒必用）。行走与路径检查见 stepNext/walkDir/buildChain/chainOK
//     （冰格必直行、白格沿已定边或唯一可用边、数字位次、箭头方向、IN/OUT 端点）。
//     这一层与 tools/deduce.py 的推理逐条对应 —— 65 题基准里 35 题被它在根节点推完。
//   - 分支（推理推不动时才用）：行主序固定顺序选格，分支 = 决定该格的最终连接集合
//     （4 条边按配置置为必用/禁用）。不做 MRV、不换扫描序、不换盘面朝向。
//   - 完解判定：buildAndCheckPath() 从 IN 沿已用边重建整条线路，逐条校验步法/度数/
//     编号位次/箭头/覆盖/无游离边 —— 剪枝不足只影响速度，不影响正确性。
//   - 枚举：mode=first 找一个即停；mode=all 枚举（受 max_solutions 限制）；
//     mode=unique 最多找两个（穷尽后只有一个才是"唯一"，被时限截断则保守报 count=2）。
//
// 输入（stdin，UTF-8 JSON）:
// {
//   "w":9, "h":9,
//   "cells":["w","i",...],                    // 长度 w*h, 行主序 index=y*w+x; "w"=白 "i"=冰
//   "numbers":[{"x":0,"y":0,"n":8}, ...],     // n>0 已知数字(可跳号, 不可重复); n=-2 = "?" 格
//   "in" :{"x":0,"y":4,"side":"L"},           // 边框侧, 进入方向 = side 的反方向;
//   "out":{"x":8,"y":4,"side":"R"},           // side 缺省/null = 内部 IN/OUT(线路以该格为起/终点);
//                                             //   内部冰格可另加 "dir" 指定滑行方向(缺省枚举全部可能)
//   "edges":[{"x":2,"y":4,"side":"R","kind":"arrow","dir":"R"}, ...],
//                                             // side 只能是 R/D/L/U(内部边会规范化为左格 R / 上格 D)
//   "options":{"cover_all_whites":true,"symmetry_retry":false},
//   "limits" :{"mode":"first|unique|all","max_solutions":20,"time_limit_ms":120000}
//                                             // mode: first=只求解一个; unique=判断唯一性;
//                                             //       all=枚举(缺省, 兼容旧协议: max_solutions==1 时=unique)
// }
// 输出（stdout，JSON Lines）:
//   {"type":"solution","index":i,"path":[[x,y],...]}   // path 含冰格重复经过
//   {"type":"done","count":N,"nodes":M,"ms":T,"aborted":false}
//   {"type":"error","message":"..."}                   // 输入/校验错误

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include <array>
#include <algorithm>
#include <chrono>
#if defined(__x86_64__) || defined(_M_X64)
#include <x86intrin.h>
#define ICELOM_RDTSC() __rdtsc()
#else
#define ICELOM_RDTSC() 0ULL
#endif

using namespace std;

// ---------------- 极简 JSON 解析 ----------------
struct JV {
    int t = 0; // 0 null, 1 bool, 2 num, 3 str, 4 arr, 5 obj
    bool b = false;
    double num = 0;
    string str;
    vector<JV> arr;
    vector<pair<string, JV>> obj;
    const JV* get(const string& k) const {
        if (t != 5) return nullptr;
        for (auto& p : obj) if (p.first == k) return &p.second;
        return nullptr;
    }
};

struct JParser {
    const char* p;
    const char* e;
    bool fail = false;
    void ws() { while (p < e && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) p++; }
    JV parse() {
        JV v; ws();
        if (p >= e) { fail = true; return v; }
        char c = *p;
        if (c == '{') {
            v.t = 5; p++; ws();
            if (p < e && *p == '}') { p++; return v; }
            while (p < e) {
                ws();
                string k = parseStr();
                ws();
                if (fail || p >= e || *p != ':') { fail = true; return v; }
                p++;
                JV val = parse();
                if (fail) return v;
                v.obj.push_back({ k, move(val) });
                ws();
                if (p < e && *p == ',') { p++; continue; }
                if (p < e && *p == '}') { p++; return v; }
                fail = true; return v;
            }
            fail = true; return v;
        }
        if (c == '[') {
            v.t = 4; p++; ws();
            if (p < e && *p == ']') { p++; return v; }
            while (p < e) {
                JV val = parse();
                if (fail) return v;
                v.arr.push_back(move(val));
                ws();
                if (p < e && *p == ',') { p++; continue; }
                if (p < e && *p == ']') { p++; return v; }
                fail = true; return v;
            }
            fail = true; return v;
        }
        if (c == '"') { v.t = 3; v.str = parseStr(); return v; }
        if (c == 't' && e - p >= 4 && !strncmp(p, "true", 4)) { v.t = 1; v.b = true; p += 4; return v; }
        if (c == 'f' && e - p >= 5 && !strncmp(p, "false", 5)) { v.t = 1; v.b = false; p += 5; return v; }
        if (c == 'n' && e - p >= 4 && !strncmp(p, "null", 4)) { v.t = 0; p += 4; return v; }
        char* endp = nullptr;
        double d = strtod(p, &endp);
        if (endp == p) { fail = true; return v; }
        v.t = 2; v.num = d; p = endp;
        return v;
    }
    string parseStr() {
        string s;
        ws();
        if (p >= e || *p != '"') { fail = true; return s; }
        p++;
        while (p < e) {
            char c = *p++;
            if (c == '"') return s;
            if (c == '\\') {
                if (p >= e) break;
                char x = *p++;
                switch (x) {
                case '"': s += '"'; break;
                case '\\': s += '\\'; break;
                case '/': s += '/'; break;
                case 'b': s += '\b'; break;
                case 'f': s += '\f'; break;
                case 'n': s += '\n'; break;
                case 'r': s += '\r'; break;
                case 't': s += '\t'; break;
                case 'u': {
                    if (e - p >= 4) {
                        unsigned cp = (unsigned)strtoul(string(p, p + 4).c_str(), nullptr, 16);
                        p += 4;
                        if (cp < 0x80) s += (char)cp;
                        else if (cp < 0x800) { s += (char)(0xC0 | (cp >> 6)); s += (char)(0x80 | (cp & 0x3F)); }
                        else { s += (char)(0xE0 | (cp >> 12)); s += (char)(0x80 | ((cp >> 6) & 0x3F)); s += (char)(0x80 | (cp & 0x3F)); }
                    }
                    break;
                }
                default: break;
                }
            }
            else s += c;
        }
        fail = true;
        return s;
    }
};

static bool getInt(const JV* v, long long& out) {
    if (!v || v->t != 2) return false;
    out = (long long)llround(v->num);
    return true;
}
static bool getBool(const JV* v, bool def) {
    if (!v) return def;
    if (v->t == 1) return v->b;
    if (v->t == 2) return v->num != 0;
    return def;
}

// ---------------- 方向 ----------------
// 0=R(+x) 1=D(+y) 2=L(-x) 3=U(-y)
static const int DX[4] = { 1, 0, -1, 0 };
static const int DY[4] = { 0, 1, 0, -1 };
static const char* DIRNAME[4] = { "R", "D", "L", "U" };
static int dirFromName(const string& s) {
    for (int i = 0; i < 4; i++) if (s == DIRNAME[i]) return i;
    return -1;
}
static inline int opp(int d) { return (d + 2) & 3; }

// JSON 字符串转义(错误信息/无解原因可能含引号等字符, 必须转义才不破坏协议行)
static string jsonEsc(const string& s) {
    string o;
    for (unsigned char ch : s) {
        switch (ch) {
        case '"': o += "\\\""; break;
        case '\\': o += "\\\\"; break;
        case '\n': o += "\\n"; break;
        case '\r': o += "\\r"; break;
        case '\t': o += "\\t"; break;
        default:
            if (ch < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", ch); o += b; }
            else o += (char)ch;
        }
    }
    return o;
}

// ---------------- 求解器 ----------------
// 盘面对称变换的点映射(定义在文件末尾, 这里前置声明供 Solver::printSol 使用)
void mapPoint(int kind, int W, int H, int& x, int& y);
void mapPointInv(int kind, int W, int H, int& x, int& y);

struct Solver {
    // ================= 盘面（load 填充, 只读） =================
    int W = 0, H = 0, N = 0, NN = 0;
    vector<int> ctype;      // 0 白 1 冰
    vector<int> numId;      // 0 无数字; >0 已知数字; -2 = "?" 格(数字未知的编号格)
    int inCell = -1, inSide = -1, outCell = -1, outSide = -1;
    int inDir = -1, outDir = -1;
    bool inInternal = false, outInternal = false;   // 内部 IN/OUT(无入/出框边)
    vector<int> inDirCands, outDirCands;            // 内部冰格 IN/OUT 的方向枚举(逐个变体求解)
    int nE = 0, nV = 0;
    vector<int> eKind;      // 0 无 1 线段 2 箭头 3 墙
    vector<int> eDir;       // 箭头绝对行进方向
    vector<int> ea, eb;
    vector<array<int, 4>> incE;
    bool coverAll = true;
    bool startIceFree = false;  // 已废弃: 旧实验开关, 解析但完全不参与判定
    int solveMode = 0;          // 0=枚举所有解 1=只求解一个 2=判断唯一性
    long long maxSols = 2000000;
    double timeLimitMs = 120000;
    string unsatReason;
    string errorMsg;
    int outKind = 0;            // 输出时把坐标变换回原题(见 transformInput)

    // ================= 边状态（唯一真源） =================
    // 每条内部边只有三个状态: 未定 / 必用(已用) / 禁用。墙与推理推出来的"禁用"统一记在这里,
    // 不再需要额外的 walledE / usedE 两份账本(历史版本两者并存, 是"假矛盾"类 bug 的温床)。
    enum { ST_UNKNOWN = 0, ST_USED = 1, ST_FORBID = 2 };
    vector<unsigned char> est;
    vector<pair<int, unsigned char>> trail;   // 回溯轨迹: (边号, 旧状态)
    bool alive = true;                        // 传播中是否已经出现矛盾

    // ---- "?" 位次模型(只依赖题面, 与状态无关) ----
    vector<char> knownVal;      // [1..] 该数字是否印在题面上
    vector<char> slotQ;         // [1..qSlotMax] 该位次是否必须是 "?" 穿越
    int qVmax = 0, qGap = 0, qNQ = 0, qNQI = 0, qNQW = 0, qSlotMax = 0;
    vector<char> qmarkNeed2;    // "?" 冰格是否被计数强制为"必须穿越两次"
    int qmarkNeed2Count = 0;    // 被强制穿越两次的 "?" 冰格个数(报告用)

    // ---- 统计 / 时间 ----
    long long nodes = 0, sols = 0;
    bool timeUp = false, aborted = false, stopAll = false;
    vector<int> pathBuf;
    long long doneCount = 0;
    chrono::steady_clock::time_point t0;
    long long curMaxSols = 1;

    // ---- 无解诊断: 记录探索最深的现场 ----
    int bestSnapDepth = -1;
    int bestSnapStatus = 0;         // 1 = 传播判死 / 2 = 线路还原校验不过
    vector<unsigned char> snapEst;

    // ---- 工作区(热路径零分配) ----
    vector<int> chainL, chainR, chainBuf, chainRev;
    vector<pair<int, unsigned char>> assumed;   // 试连接里的临时假设(不写 trail)
    vector<int> walkStamp;      // 节点访问标记(行走环检测)
    int walkCur = 0;
    vector<int> okStamp;        // 路径检查的白格重复标记
    int okCur = 0;
    vector<int> ufTmp;          // 并查集工作区
    vector<int> compMark, compIdx, compRep;   // 已用分量的根标记 -> 分量号 -> 代表边
    int compCur = 0;
    vector<int> pathCellVis, pathAxisVis;
    vector<int> qposBuf;        // 路径检查里 "?" 穿越在链内的局部序号
    int chainSk = 0, chainEk = 0;

    bool ok() const { return errorMsg.empty(); }

    // ================= 基本工具 =================
    inline bool hasNumMark(int c) const { return numId[c] != 0; }
    inline int axisOfEdge(int e) const { return e < nV ? 0 : 1; }
    inline int cellNode(int c, int ax) const { return ctype[c] ? c + ax * N : c; }
    inline int nodeCell(int nd) const { return nd < N ? nd : nd - N; }
    inline int otherCellOf(int e, int c) const { return ea[e] == c ? eb[e] : ea[e]; }
    inline int dirFromTo(int from, int e) const {
        if (e < nV) return (ea[e] == from) ? 0 : 2;
        return (ea[e] == from) ? 1 : 3;
    }
    inline int edgeBetween(int c1, int c2) const {
        int dx = (c2 % W) - (c1 % W), dy = (c2 / W) - (c1 / W);
        if (dx == 1 && dy == 0) return incE[c1][0];
        if (dx == 0 && dy == 1) return incE[c1][1];
        if (dx == -1 && dy == 0) return incE[c1][2];
        if (dx == 0 && dy == -1) return incE[c1][3];
        return -1;
    }
    inline int ufFind(int x) { while (ufTmp[x] != x) x = ufTmp[x] = ufTmp[ufTmp[x]]; return x; }

    // IN/OUT 的"入框/出框轴": 边框 IN/OUT 由 side 决定; 内部 IN/OUT 由本变体的 dir 决定
    // (内部白格 IN/OUT 无轴概念, 返回 -1)。
    inline int inAxis() const {
        if (!inInternal) return inSide & 1;
        return inDir < 0 ? -1 : (inDir & 1);
    }
    inline int outAxis() const {
        if (!outInternal) return outSide & 1;
        return outDir < 0 ? -1 : (outDir & 1);
    }
    // 格的边框连接数(IN/OUT 各算一条; 内部 IN/OUT 用"虚拟边框边"补齐, 见 configLegal)
    inline int frameConns(int c) const {
        return (c == inCell ? 1 : 0) + (c == outCell ? 1 : 0);
    }
    inline int frameConnsAxis(int c, int ax) const {
        int n = 0;
        if (c == inCell && inAxis() == ax) n++;
        if (c == outCell && outAxis() == ax) n++;
        return n;
    }
    inline int countUsed() const {
        int n = 0;
        for (int e = 0; e < nE; e++) if (est[e] == ST_USED) n++;
        return n;
    }
    // 该格是否"必须在线路上"(编号格必经; 端点格必经; 覆盖模式下的白格必经)
    inline bool mustVisit(int c) const {
        if (numId[c] != 0) return true;
        if (c == inCell || c == outCell) return true;
        return ctype[c] == 0 && coverAll;
    }

    // ================= 格内合法性(与 tools/deduce.py 的 cell_configs 同一套判据) =================
    // 判据只用"节点度数"这一件事, 因此边框边、内部 IN/OUT 的虚拟边、冰格两轴可以统一处理:
    //   * 白格: 在线路上 ⇒ 总连接数(含边框边) == 2; 不在线路上 ⇒ 0 或 2(绝不出现半条);
    //   * 冰格: 每条轴的总连接数 == 0 或 2(IN/OUT 轴 = 边框边 + 1 条格内边; 十字交叉 = 两轴各 2);
    //   * 编号格: 穿越次数 = 总连接数/2。已知数字格必须恰好 1 次;
    //     "?" 格至少 1 次、至多 2 次, 被计数强制时必须正好 2 次(十字交叉)。
    // mask 的 4 位对应 incE[c] 的 4 个方向(R,D,L,U); 未被 mask 选中的边在该格里就是"不用"。
    bool configLegal(int c, unsigned char mask) const {
        int used = 0;
        for (int k = 0; k < 4; k++) if ((mask >> k) & 1) used++;
        int total = used + frameConns(c);
        if (ctype[c] == 0) {
            if (mustVisit(c)) return total == 2;
            return total == 0 || total == 2;
        }
        for (int ax = 0; ax < 2; ax++) {
            int n = frameConnsAxis(c, ax);
            for (int k = ax; k < 4; k += 2) if ((mask >> k) & 1) n++;
            if (n != 0 && n != 2) return false;
        }
        int visits = total / 2;
        if (numId[c] > 0) return visits == 1;
        if (numId[c] == -2) {
            if (visits < 1 || visits > 2) return false;
            if (qmarkNeed2[c] && visits != 2) return false;
        }
        return true;
    }
    // 枚举该格在当前状态(可带一条"假设状态"覆盖)下的全部合法配置。返回配置个数(≤ 16);
    // firstOnly = true 时找到一个就返回 1(只判存在性)。cap 限制写回 out 的个数。
    int enumCellConfigs(int c, unsigned char* out, int cap, bool firstOnly,
                        int overE = -1, int overSt = -1) const {
        unsigned char usedM = 0, freeM = 0;
        for (int k = 0; k < 4; k++) {
            int e = incE[c][k];
            if (e < 0) continue;
            unsigned char s = (e == overE) ? (unsigned char)overSt : est[e];
            if (s == ST_USED) usedM |= (unsigned char)(1u << k);
            else if (s == ST_UNKNOWN) freeM |= (unsigned char)(1u << k);
        }
        int cnt = 0;
        unsigned char sub = freeM;
        for (;;) {
            unsigned char mask = (unsigned char)(usedM | sub);
            if (configLegal(c, mask)) {
                if (out && cnt < cap) out[cnt] = mask;
                cnt++;
                if (firstOnly) return cnt;
            }
            if (sub == 0) break;
            sub = (unsigned char)((sub - 1) & freeM);
        }
        return cnt;
    }
    bool cellHasConfig(int c, int overE = -1, int overSt = -1) const {
        return enumCellConfigs(c, nullptr, 0, true, overE, overSt) > 0;
    }

    // ---- 状态写入 / 回溯 ----
    bool setEdge(int e, int st) {          // 返回是否真的改了状态; 冲突时 alive = false
        if (est[e] == (unsigned char)st) return false;
        if (est[e] != ST_UNKNOWN) { alive = false; return false; }
        trail.push_back(make_pair(e, est[e]));
        est[e] = (unsigned char)st;
        return true;
    }
    void undoTo(size_t mark) {
        while (trail.size() > mark) {
            est[trail.back().first] = trail.back().second;
            trail.pop_back();
        }
    }
    // 试连接里的临时假设: 只在 buildChain 内部使用, 调用方负责还原(不写 trail)。
    bool assumeEdge(int e, vector<pair<int, unsigned char>>& saved) {
        if (est[e] == ST_USED) return true;
        if (est[e] == ST_FORBID) return false;
        saved.push_back(make_pair(e, est[e]));
        est[e] = ST_USED;
        return true;
    }

    // ================= 位次模型 =================
    // 官方判定(icebarn checkNumberOrder / getTraceInfo): 沿线第 p 次"编号格穿越"上的数字必须 == p。
    //   ⇒ 已知数字 v 必须落在第 v 位; 没被已知数字占用的位次只能由 "?" 穿越填。
    inline bool slotAllows(int p, int nv) const {
        if (nv > 0) return p == nv;
        return p >= 1 && p <= qSlotMax && slotQ[p] != 0;
    }

    // 建立位次表; 返回 false = 计数上就不可能(已设 unsatReason)。
    bool initQmarkModel() {
        int maxNum = 0, nKnown = 0;
        qNQ = qNQI = qNQW = 0;
        for (int c = 0; c < N; c++) {
            if (numId[c] > 0) { maxNum = max(maxNum, numId[c]); nKnown++; }
            else if (numId[c] == -2) { qNQ++; if (ctype[c] == 1) qNQI++; else qNQW++; }
        }
        qVmax = maxNum;
        qGap = maxNum - nKnown;                       // 位次 1..Vmax 中空出来的位数
        knownVal.assign((size_t)max(1001, maxNum + 2), 0);
        for (int c = 0; c < N; c++) if (numId[c] > 0) knownVal[numId[c]] = 1;
        if (qGap > qNQW + 2 * qNQI) {
            unsatReason = "数字空缺数超过问号可提供的位次数";
            return false;
        }
        int tail = qNQW + 2 * qNQI - qGap;            // Vmax 之后还允许的 "?" 穿越数
        qSlotMax = qVmax + tail;
        slotQ.assign((size_t)qSlotMax + 2, 0);
        for (int p = 1; p <= qSlotMax; p++) slotQ[p] = (p > qVmax || !knownVal[p]) ? 1 : 0;
        if (inInternal && ctype[inCell] == 1 && inDir < 0) { unsatReason = "内部冰格 IN 缺少方向"; return false; }
        if (outInternal && ctype[outCell] == 1 && outDir < 0) { unsatReason = "内部冰格 OUT 缺少方向"; return false; }
        return true;
    }

    // 计数推论: 线路上第 1..Vmax 位必须被填满, 已知数字占 K 个 ⇒ 空缺 qGap 个位次只能由 "?" 穿越填。
    // 每个 "?" 白格最多 1 次、每个 "?" 冰格最多 2 次穿越 ⇒ 只有"修满上限也刚好够"时才能断定
    // 每个 "?" 冰格都必须十字交叉两次(此时 qGap == qNQW + 2*qNQI)。余量 > 0 时不能逐个断定。
    void initQmarkNeeds() {
        qmarkNeed2.assign(N, 0);
        qmarkNeed2Count = 0;
        if (qNQI == 0) return;
        if (qGap < qNQW + 2 * qNQI) return;           // 还有余量 ⇒ 推不出"每个都两次"
        for (int c = 0; c < N; c++)
            if (numId[c] == -2 && ctype[c] == 1) { qmarkNeed2[c] = 1; qmarkNeed2Count++; }
    }

    // ================= 滑行行走 + 路径检查 =================
    // 与 tools/deduce.py 的 _terminus/_step/_walk_dir/_chain_ok 逐条对应:
    //   冰格必须直行 ⇒ 接着冰格的那条边"必被用"(即使它还没定);
    //   白格沿已定的边走, 只剩唯一一条可用边时那条也必被用, 否则去路未定 ⇒ 自由端。
    //
    // 线路端点判定: 0 自由 / 1 IN / 2 OUT。
    // 白质 IN/OUT 格一进入就是端点; **冰质 IN/OUT 格只有"沿入框/出框轴"进入那一次才是端点**,
    // 垂直进入时继续直行(冰质 OUT 被垂直穿过再折返出框是官方允许的走法)。
    inline int terminusKind(int cur, int prev) const {
        if (prev < 0) return 0;
        int py = prev / W, y = cur / W;
        int ax = (py != y) ? 1 : 0;
        if (cur == inCell) {
            if (ctype[cur] == 0) return 1;
            int a = inAxis();
            if (a < 0 || ax == a) return 1;
        }
        if (cur == outCell) {
            if (ctype[cur] == 0) return 2;
            int a = outAxis();
            if (a < 0 || ax == a) return 2;
        }
        return 0;
    }

    // 从 prev 走到 cur 之后的必经下一步。返回 false = 撞死(不可行); nxt < 0 = 自由端。
    bool stepNext(int cur, int prev, int& nxt, int& ne,
                  vector<pair<int, unsigned char>>& saved) {
        nxt = -1; ne = -1;
        int eIn = edgeBetween(prev, cur);
        if (eIn < 0) return false;
        if (ctype[cur] == 1) {
            int d = dirFromTo(prev, eIn);
            int e2 = incE[cur][d];
            if (e2 < 0 || e2 == eIn) return false;              // 走出盘面(非 OUT 终点)
            if (est[e2] == ST_FORBID) return false;
            if (est[e2] != ST_USED) {
                if (!cellHasConfig(cur, e2, ST_USED)) return false;   // 该格已经不能再穿
                if (!assumeEdge(e2, saved)) return false;
            }
            int nb = otherCellOf(e2, cur);
            if (!cellHasConfig(nb, e2, ST_USED)) return false;  // 对面格不可连接
            nxt = nb; ne = e2;
            return true;
        }
        if (!cellHasConfig(cur)) return false;                  // 这个白格已经凑不齐度数
        int usedNext = -1, freeCnt = 0, freeE = -1;
        for (int k = 0; k < 4; k++) {
            int e2 = incE[cur][k];
            if (e2 < 0 || e2 == eIn) continue;
            if (est[e2] == ST_FORBID) continue;
            if (est[e2] == ST_USED) { usedNext = e2; break; }
            freeCnt++; freeE = e2;
        }
        if (usedNext >= 0) { nxt = otherCellOf(usedNext, cur); ne = usedNext; return true; }
        if (freeCnt != 1) return true;                          // 去路未定(或已无路) ⇒ 自由端
        if (!cellHasConfig(cur, freeE, ST_USED)) return false;
        if (!assumeEdge(freeE, saved)) return false;
        int nb = otherCellOf(freeE, cur);
        if (!cellHasConfig(nb, freeE, ST_USED)) return false;
        nxt = nb; ne = freeE;
        return true;
    }

    // 从 cell 沿"离开 other 的方向"一直走到头(全程确定性、无搜索)。
    bool walkDir(int cell, int other, vector<int>& out, int& kind,
                 vector<pair<int, unsigned char>>& saved) {
        out.clear();
        out.push_back(cell);
        int prev = other, cur = cell;
        for (int guard = 0; guard <= 2 * N + 8; guard++) {
            int tk = terminusKind(cur, prev);
            if (tk) { kind = tk; return true; }
            int nxt = -1, ne = -1;
            if (!stepNext(cur, prev, nxt, ne, saved)) return false;
            if (nxt < 0) { kind = 0; return true; }
            int nd = cellNode(nxt, axisOfEdge(ne));
            if (walkStamp[nd] == walkCur) return false;         // 同一格同一条轴被走两次 ⇒ 成环
            walkStamp[nd] = walkCur;
            out.push_back(nxt);
            prev = cur; cur = nxt;
        }
        return false;
    }

    // 在"边 e 被使用"的假设下构造整条候选链(含冰格直行、唯一剩余可用边所必经的未定边)。
    // cells = 从一侧远端到另一侧远端; startKind/endKind ∈ {0 自由, 1 IN, 2 OUT}。
    bool buildChain(int e, vector<int>& cells, int& startKind, int& endKind) {
        if (est[e] == ST_FORBID) return false;
        int a = ea[e], b = eb[e];
        assumed.clear();
        if (!assumeEdge(e, assumed)) return false;
        int kL = 0, kR = 0;
        bool okL, okR = false;
        walkCur++;
        walkStamp[cellNode(a, axisOfEdge(e))] = walkCur;
        okL = walkDir(a, b, chainL, kL, assumed);
        if (okL) {
            walkCur++;
            walkStamp[cellNode(b, axisOfEdge(e))] = walkCur;
            okR = walkDir(b, a, chainR, kR, assumed);
        }
        for (size_t i = assumed.size(); i-- > 0;) est[assumed[i].first] = assumed[i].second;
        assumed.clear();
        if (!okL || !okR) return false;
        cells.clear();
        for (size_t i = chainL.size(); i-- > 0;) cells.push_back(chainL[i]);
        for (size_t i = 0; i < chainR.size(); i++) cells.push_back(chainR[i]);
        startKind = kL; endKind = kR;
        return true;
    }

    // **路径检查**(与官方 checkNumberOrder 同一条规则): 存在满足条件的 "?" 赋值 ⇒ true。
    //   * 链上所有已知数字的 (v − 局部序号) 必须一致(数字必须一个个递增, 不能跳跃);
    //   * "?" 的位次必须落在"空缺位次 ∪ Vmax 之后"里;
    //   * 起点是 IN ⇒ 第一个位次必须是 1; 终点是 OUT ⇒ 到 OUT 时位次必须已经走到 Vmax;
    //   * 链上箭头边必须与该朝向的行进方向一致。
    bool chainOK(const vector<int>& cells, int startKind, int endKind) {
        if (startKind == 2 || endKind == 1) return false;   // OUT 只能是终点, IN 只能是起点
        okCur++;
        int n = 0;                 // 链上的编号穿越次数
        bool hasP1 = false;
        int p1 = 0;
        for (size_t i = 0; i < cells.size(); i++) {
            int c = cells[i];
            if (i > 0) {
                int e = edgeBetween(cells[i - 1], c);
                if (e < 0) return false;
                if (eKind[e] == 2 && eDir[e] != dirFromTo(cells[i - 1], e)) return false;
            }
            if (ctype[c] == 0) {                       // 白格不能被重复经过
                if (okStamp[c] == okCur) return false;
                okStamp[c] = okCur;
            }
            if (numId[c] != 0) {
                n++;
                if (numId[c] > 0) {
                    int q = numId[c] - n + 1;
                    if (!hasP1) { hasP1 = true; p1 = q; }
                    else if (p1 != q) return false;
                }
            }
        }
        if (startKind == 1) {                           // 起点是 IN ⇒ 第一个位次必须是 1
            if (hasP1 && p1 != 1) return false;
            hasP1 = true; p1 = 1;
        }
        int lo = 1, hi = qSlotMax - n + 1;
        if (endKind == 2) lo = max(lo, qVmax - n + 1);  // 到 OUT 时位次必须已经走到 Vmax
        if (lo > hi) return false;
        if (hasP1) {
            if (p1 < lo || p1 > hi) return false;
            lo = hi = p1;
        }
        bool anyQ = false;
        for (size_t i = 0; i < cells.size(); i++) if (numId[cells[i]] == -2) { anyQ = true; break; }
        if (!anyQ) return true;
        // 逐个试链首位次 q: "?" 的第 idx 次穿越落在 q+idx-1, 该位次不能被已知数字占用。
        qposBuf.clear();
        {
            int idx = 0;
            for (size_t i = 0; i < cells.size(); i++) {
                if (numId[cells[i]] == 0) continue;
                idx++;
                if (numId[cells[i]] == -2) qposBuf.push_back(idx);
            }
        }
        for (int q = lo; q <= hi; q++) {
            bool good = true;
            for (size_t j = 0; j < qposBuf.size(); j++) {
                int p = q + qposBuf[j] - 1;
                if (p >= 1 && p <= qVmax && knownVal[p]) { good = false; break; }
            }
            if (good) return true;
        }
        return false;
    }

    // ================= 推理规则 =================
    // R1 格内配置: 某格一条合法配置都没有 ⇒ 矛盾; 所有配置共有的边 ⇒ 必用; 任何配置都不含的边 ⇒ 禁用。
    bool ruleCells() {
        bool ch = false;
        for (int c = 0; c < N; c++) {
            unsigned char cfgs[16];
            int n = enumCellConfigs(c, cfgs, 16, false);
            if (n == 0) { alive = false; return false; }
            unsigned char inter = 0xFF, uni = 0;
            for (int i = 0; i < n; i++) { inter &= cfgs[i]; uni |= cfgs[i]; }
            for (int k = 0; k < 4; k++) {
                int e = incE[c][k];
                if (e < 0 || est[e] != ST_UNKNOWN) continue;
                if ((inter >> k) & 1) { if (setEdge(e, ST_USED)) ch = true; }
                else if (!((uni >> k) & 1)) { if (setEdge(e, ST_FORBID)) ch = true; }
                if (!alive) return false;
            }
        }
        return ch;
    }

    // R2 相邻的已知数字必须连续: 两者直接相连 ⇒ 位次差只能是 1。
    bool ruleNums() {
        bool ch = false;
        for (int c = 0; c < N; c++) {
            if (numId[c] <= 0) continue;
            for (int k = 0; k < 4; k++) {
                int e = incE[c][k];
                if (e < 0 || est[e] != ST_UNKNOWN) continue;
                int nb = otherCellOf(e, c);
                if (numId[nb] <= 0) continue;
                if (abs(numId[nb] - numId[c]) != 1) { if (setEdge(e, ST_FORBID)) ch = true; }
                if (!alive) return false;
            }
        }
        return ch;
    }

    // R3 连通/无环(节点级): 已用边成环 ⇒ 矛盾; 未定边两端已被已用边连通 ⇒ 禁用。
    //    冰格的两条轴是两个独立节点, 因此十字交叉不会被误判成"成环"。
    bool ruleCycles() {
        for (int i = 0; i < NN; i++) ufTmp[i] = i;
        for (int e = 0; e < nE; e++) {
            if (est[e] != ST_USED) continue;
            int x = ufFind(cellNode(ea[e], axisOfEdge(e)));
            int y = ufFind(cellNode(eb[e], axisOfEdge(e)));
            if (x == y) { alive = false; return false; }        // 已用边成环
            ufTmp[x] = y;
        }
        bool ch = false;
        for (int e = 0; e < nE; e++) {
            if (est[e] != ST_UNKNOWN) continue;
            int x = ufFind(cellNode(ea[e], axisOfEdge(e)));
            int y = ufFind(cellNode(eb[e], axisOfEdge(e)));
            if (x == y) { if (setEdge(e, ST_FORBID)) ch = true; }
            if (!alive) return false;
        }
        return ch;
    }

    // R4 可达性(格级并查集 = 节点级连通的**放宽**, 因此只用来推"必然到不了"):
    //    线路上的每一格都必须同时能到 IN 与 OUT; 到不了 ⇒ 该格所有边禁用(已用则矛盾)。
    bool ruleReach() {
        for (int i = 0; i < N; i++) ufTmp[i] = i;
        for (int e = 0; e < nE; e++) {
            if (est[e] == ST_FORBID) continue;
            int x = ufFind(ea[e]), y = ufFind(eb[e]);
            if (x != y) ufTmp[x] = y;
        }
        int ri = ufFind(inCell), ro = ufFind(outCell);
        bool ch = false;
        for (int c = 0; c < N; c++) {
            int r = ufFind(c);
            if (r == ri && r == ro) continue;
            for (int k = 0; k < 4; k++) {
                int e = incE[c][k];
                if (e < 0) continue;
                if (est[e] == ST_USED) { alive = false; return false; }
                if (est[e] == ST_UNKNOWN) { if (setEdge(e, ST_FORBID)) ch = true; }
                if (!alive) return false;
            }
        }
        return ch;
    }

    // R5 已用分量的路径检查: 每条已用边都必然落在线路上, 因此分量本身必须能通过路径检查
    //    (方向/编号位次/端点类型)。分量含 IN 或 OUT 时朝向被钉死(由 terminusKind 自动体现)。
    bool ruleComponents() {
        for (int i = 0; i < NN; i++) ufTmp[i] = i;
        int anyUsed = 0;
        for (int e = 0; e < nE; e++) {
            if (est[e] != ST_USED) continue;
            anyUsed = 1;
            int x = ufFind(cellNode(ea[e], axisOfEdge(e)));
            int y = ufFind(cellNode(eb[e], axisOfEdge(e)));
            if (x != y) ufTmp[x] = y;
        }
        if (!anyUsed) return false;
        compCur++;
        int nc = 0;
        for (int e = 0; e < nE; e++) {
            if (est[e] != ST_USED) continue;
            int r = ufFind(cellNode(ea[e], axisOfEdge(e)));
            if (compMark[r] != compCur) {
                compMark[r] = compCur;
                compIdx[r] = nc;
                compRep[nc] = e;
                nc++;
            }
        }
        for (int i = 0; i < nc; i++) {
            if (!buildChain(compRep[i], chainBuf, chainSk, chainEk)) { alive = false; return false; }
            if (chainOK(chainBuf, chainSk, chainEk)) continue;
            chainRev.assign(chainBuf.rbegin(), chainBuf.rend());
            if (chainOK(chainRev, chainEk, chainSk)) continue;
            alive = false;
            return false;
        }
        return false;
    }

    // R6 单边试连接(主算法, 与 tools/deduce.py 的 close_by_probe 一致):
    //    逐格扫、逐方向试"用"与试"禁", 一有更新就整轮重来, 直到一整轮没有任何更新。
    //      * 试"用"不可行(顺方向走撞死 / 路径检查不过) ⇒ 这条边必禁;
    //      * 试"禁"不可行(禁掉它该格就没走法了) ⇒ 这条边必用;
    //      * 该格剩下的合法走法(每条边要么已用、要么试连可行)里所有走法都含的边 ⇒ 必用。
    bool tryUse(int e) {
        int a = ea[e], b = eb[e];
        if (!cellHasConfig(a, e, ST_USED)) return false;
        if (!cellHasConfig(b, e, ST_USED)) return false;
        if (!buildChain(e, chainBuf, chainSk, chainEk)) return false;
        if (chainOK(chainBuf, chainSk, chainEk)) return true;
        chainRev.assign(chainBuf.rbegin(), chainBuf.rend());
        return chainOK(chainRev, chainEk, chainSk);
    }
    bool tryForbid(int e) {
        if (!cellHasConfig(ea[e], e, ST_FORBID)) return false;
        if (!cellHasConfig(eb[e], e, ST_FORBID)) return false;
        return true;
    }
    bool ruleProbe() {
        bool ch = false;
        for (int c = 0; c < N; c++) {
            int es[4], n = 0;
            for (int k = 0; k < 4; k++) {
                int e = incE[c][k];
                if (e >= 0 && est[e] == ST_UNKNOWN) es[n++] = e;
            }
            if (n == 0) continue;
            if (!cellHasConfig(c)) { alive = false; return false; }
            bool okUse[4];
            for (int i = 0; i < n; i++) okUse[i] = tryUse(es[i]);
            for (int i = 0; i < n; i++)
                if (!okUse[i] && est[es[i]] == ST_UNKNOWN) { if (setEdge(es[i], ST_FORBID)) ch = true; }
            if (!alive) return false;
            for (int i = 0; i < n; i++) {
                if (est[es[i]] != ST_UNKNOWN) continue;
                if (!tryForbid(es[i])) { if (setEdge(es[i], ST_USED)) ch = true; }
                if (!alive) return false;
            }
            unsigned char cfgs[16];
            int nc = enumCellConfigs(c, cfgs, 16, false);
            unsigned char inter = 0xFF;
            int nv = 0;
            for (int i = 0; i < nc; i++) {
                bool viable = true;
                for (int k = 0; k < 4 && viable; k++) {
                    if (!((cfgs[i] >> k) & 1)) continue;
                    int e = incE[c][k];
                    if (est[e] == ST_USED) continue;
                    bool good = false;
                    for (int j = 0; j < n; j++) if (es[j] == e && okUse[j]) { good = true; break; }
                    if (!good) viable = false;
                }
                if (viable) { inter &= cfgs[i]; nv++; }
            }
            if (nv == 0) { alive = false; return false; }
            for (int k = 0; k < 4; k++) {
                if (!((inter >> k) & 1)) continue;
                int e = incE[c][k];
                if (e < 0 || est[e] != ST_UNKNOWN) continue;
                if (setEdge(e, ST_USED)) ch = true;
                if (!alive) return false;
            }
        }
        return ch;
    }

    // 推到不动点。返回 false = 当前状态已经矛盾(或已到时限, 调用方按"本轮无结论"处理)。
    bool propagate() {
        for (int round = 0; round < 500; round++) {
            checkTime();
            if (timeUp) return false;          // 大棋盘上单轮传播也可能超时, 别卡在传播里
            bool ch = false;
            ch = ruleCells() || ch;
            if (!alive) return false;
            ch = ruleNums() || ch;
            if (!alive) return false;
            ch = ruleCycles() || ch;
            if (!alive) return false;
            ch = ruleReach() || ch;
            if (!alive) return false;
            ch = ruleComponents() || ch;
            if (!alive) return false;
            ch = ruleProbe() || ch;
            if (!alive) return false;
            if (!ch) break;
        }
        return alive;
    }

    // ================= 解的还原与校验 =================
    // 从 IN 出发沿**已用边**重建整条线路并逐条校验(这是最后一道闸门, 与剪枝强度无关):
    //   ① 每步都必须走已用边; 白格恰有 1 条去路; 冰格沿进入轴直行;
    //   ② 白格只经过一次; 冰格同一条轴只穿越一次; 已知数字格只穿越一次; "?" 格至多两次;
    //   ③ 编号位次: 已知数字 v 必须落在第 v 位; "?" 每次穿越必须落在允许的位次上;
    //   ④ 箭头边必须按箭头方向经过; ⑤ 所有已用边都必须在这条线路上(不许有游离段/环);
    //   ⑥ 编号格全部被经过; coverAll 时白格全部被经过。
    bool buildAndCheckPath(vector<int>& path) {
        path.clear();
        pathCellVis.assign(N, 0);
        pathAxisVis.assign(NN, 0);
        int numIdx = 0;
        int usedWalked = 0;
        int cur = inCell;
        int arrDir = inDir;                       // 起点: 沿入框方向离开(内部白格 IN 为 -1)
        int arrAxis = inAxis();
        path.push_back(cur);
        for (int guard = 0; guard <= 2 * N + 8; guard++) {
            // --- 本次访问登记 ---
            int vc = ++pathCellVis[cur];
            if (ctype[cur] == 0) {
                if (vc > 1) return false;         // 白格不能重复经过
            } else {
                if (arrAxis < 0) return false;
                int nd = cur + arrAxis * N;
                if (++pathAxisVis[nd] > 1) return false;    // 冰格同一条轴被穿越两次
                if (vc > 2) return false;
            }
            if (numId[cur] != 0) {
                numIdx++;
                if (numId[cur] > 0) {
                    if (numId[cur] != numIdx) return false;   // 已知数字必须落在第 v 位
                } else if (!slotAllows(numIdx, -2)) {
                    return false;
                }
            }
            // --- 终点判定 ---
            bool atOut = false;
            if (cur == outCell) {
                if (ctype[cur] == 0) atOut = true;
                else if (arrAxis >= 0 && arrAxis == outAxis()) atOut = true;
            }
            if (atOut) break;
            // --- 找出口 ---
            int e = -1;
            if (ctype[cur] == 0) {
                int eIn = (path.size() >= 2) ? edgeBetween(path[path.size() - 2], cur) : -1;
                for (int k = 0; k < 4; k++) {
                    int e2 = incE[cur][k];
                    if (e2 < 0 || e2 == eIn) continue;
                    if (est[e2] != ST_USED) continue;
                    if (e != -1) return false;    // 白格出现两条去路(不应发生: 局部规则已挡住)
                    e = e2;
                }
                if (e < 0) return false;
            } else {
                if (arrDir < 0) return false;
                e = incE[cur][arrDir];
                if (e < 0) return false;          // 冰格直行走出盘面(不是 OUT 出框) ⇒ 非法
                if (est[e] != ST_USED) return false;
            }
            int d = dirFromTo(cur, e);
            if (eKind[e] == 2 && eDir[e] != d) return false;      // 逆箭头
            usedWalked++;
            cur = otherCellOf(e, cur);
            arrDir = d;
            arrAxis = axisOfEdge(e);
            path.push_back(cur);
        }
        if (cur != outCell) return false;
        if (usedWalked != countUsed()) return false;             // 有游离的已用边 ⇒ 不是一条线
        for (int c = 0; c < N; c++) {
            if (numId[c] != 0 && pathCellVis[c] == 0) return false;        // 编号格必须被经过
            if (numId[c] > 0 && pathCellVis[c] != 1) return false;         // 已知数字只穿越一次
            if (numId[c] == -2 && pathCellVis[c] > 2) return false;
            if (ctype[c] == 0 && coverAll && pathCellVis[c] == 0) return false;
        }
        return true;
    }

    // ================= 搜索（固定顺序, 无排序优化） =================
    // 选格: 先按行主序找"必须在线路上"的格(白格/编号格/端点格), 没有就按行主序找任意可分支格。
    // 固定顺序、不变量打分、不做 MRV —— 推理已经把盘面推得足够狠, 排序不再重要。
    int pickBranchCell() const {
        unsigned char cfgs[16];
        for (int pass = 0; pass < 2; pass++) {
            for (int c = 0; c < N; c++) {
                if (pass == 0 && !mustVisit(c)) continue;
                int n = enumCellConfigs(c, cfgs, 16, false);
                if (n >= 2) return c;
            }
        }
        return -1;
    }

    void noteDead(int status) {
        int d = countUsed();
        if (d <= bestSnapDepth) return;
        bestSnapDepth = d;
        bestSnapStatus = status;
        snapEst = est;
    }

    void checkTime() {
        double ms = chrono::duration<double, milli>(chrono::steady_clock::now() - t0).count();
        if (ms > timeLimitMs) { timeUp = true; aborted = true; }
    }

    void dfs() {
        while (!stopAll && !timeUp) {
            if (!propagate()) { noteDead(1); break; }
            int c = pickBranchCell();
            if (c < 0) {
                if (buildAndCheckPath(pathBuf)) emitSolution();
                else noteDead(2);
                break;
            }
            nodes++;
            if ((nodes & 255) == 0) checkTime();
            if (timeUp) break;
            unsigned char cfgs[16];
            int n = enumCellConfigs(c, cfgs, 16, false);
            if (n < 2) break;      // 防御: 选格与枚举之间状态未变, 正常不会发生
            for (int i = 0; i < n; i++) {
                size_t mk = trail.size();
                bool aliveSave = alive;
                for (int k = 0; k < 4; k++) {
                    int e = incE[c][k];
                    if (e < 0) continue;
                    setEdge(e, ((cfgs[i] >> k) & 1) ? ST_USED : ST_FORBID);
                }
                if (alive) dfs();
                undoTo(mk);
                alive = aliveSave;
                if (stopAll || timeUp) break;
            }
            break;
        }
    }

    // ================= 初始化 =================
    bool initState() {
        trail.clear();
        alive = true;
        est.assign(nE, ST_UNKNOWN);
        bestSnapDepth = -1;
        bestSnapStatus = 0;
        snapEst.clear();
        walkStamp.assign(NN, 0);
        walkCur = 0;
        okStamp.assign(N, 0);
        okCur = 0;
        ufTmp.assign(NN, 0);
        compMark.assign(NN, 0);
        compIdx.assign(NN, 0);
        compRep.assign(NN, 0);
        compCur = 0;
        for (int e = 0; e < nE; e++) {
            if (eKind[e] == 3) est[e] = ST_FORBID;                    // 墙
            else if (eKind[e] == 1 || eKind[e] == 2) est[e] = ST_USED; // 线段/箭头: 强制边
        }
        if (!initQmarkModel()) return false;
        initQmarkNeeds();
        return propagate();
    }

    // ================= 解的重建与输出 =================
    void printSol(long long idx, const vector<int>& p) {
        string s = "{\"type\":\"solution\",\"index\":";
        char buf[64];
        snprintf(buf, sizeof buf, "%lld", idx);
        s += buf;
        s += ",\"path\":[";
        for (size_t i = 0; i < p.size(); i++) {
            if (i) s += ",";
            int c = p[i];
            int px = c % W, py = c / W;
            if (outKind) mapPointInv(outKind, W, H, px, py);   // 变换回原题坐标(旋转需用逆映射)
            snprintf(buf, sizeof buf, "[%d,%d]", px, py);
            s += buf;
        }
        s += "]}\n";
        fwrite(s.data(), 1, s.size(), stdout);
        fflush(stdout);
    }

    void emitSolution() {
        if (getenv("ICELOM_DEBUG_SLOTS")) {
            fprintf(stderr, "[dbg] path slots:");
            int slot = 0;
            for (size_t i = 0; i < pathBuf.size(); i++) {
                int c = pathBuf[i];
                if (numId[c] == 0) continue;
                slot++;
                fprintf(stderr, " i=%d(%d,%d)v=%d->slot%d", (int)i, c % W, c / W, numId[c], slot);
            }
            fprintf(stderr, "\n");
        }
        printSol(sols, pathBuf);
        sols++;
        if (solveMode == 1) { stopAll = true; return; }        // 只求解: 找到一个即停
        if (sols >= curMaxSols) {
            stopAll = true;
            if (solveMode != 2) { timeUp = true; aborted = true; }   // 达到解数量上限 ⇒ 截断
        }
    }

    void emitDone() {
        double ms = chrono::duration<double, milli>(chrono::steady_clock::now() - t0).count();
        string s = "{\"type\":\"done\",\"count\":";
        char buf[128];
        snprintf(buf, sizeof buf, "%lld", doneCount); s += buf;
        s += ",\"nodes\":"; snprintf(buf, sizeof buf, "%lld", nodes); s += buf;
        s += ",\"ms\":"; snprintf(buf, sizeof buf, "%.1f", ms); s += buf;
        s += ",\"aborted\":"; s += aborted ? "true" : "false";
        if (doneCount == 0 && !unsatReason.empty()) { s += ",\"reason\":\"" + jsonEsc(unsatReason) + "\""; }
        s += "}\n";
        fwrite(s.data(), 1, s.size(), stdout);
        fflush(stdout);
    }

    // 把某份边状态快照渲染成 ASCII 盘面(人工判断用)
    void renderState(const vector<unsigned char>& st) {
        auto cellChar = [&](int c) -> char {
            if (c == inCell) return 'S';
            if (c == outCell) return 'G';
            if (numId[c] == -2) return '?';
            if (numId[c] > 0) return numId[c] <= 9 ? (char)('0' + numId[c]) : '+';
            return ctype[c] == 1 ? '#' : '.';
        };
        for (int y = 0; y < H; y++) {
            string line;
            for (int x = 0; x < W; x++) {
                int c = y * W + x;
                line += cellChar(c);
                if (x < W - 1) {
                    int e = incE[c][0];
                    line += (e >= 0 && e < (int)st.size() && st[e] == ST_USED) ? '-' : ' ';
                }
            }
            fprintf(stderr, "  %s\n", line.c_str());
            if (y < H - 1) {
                string line2;
                for (int x = 0; x < W; x++) {
                    int c = y * W + x;
                    int e = incE[c][1];
                    line2 += (e >= 0 && e < (int)st.size() && st[e] == ST_USED) ? '|' : ' ';
                    line2 += ' ';
                }
                fprintf(stderr, "  %s\n", line2.c_str());
            }
        }
    }

    // 无解诊断: 最深现场 + 盘面
    void printUnsatDiagnostics() {
        if (bestSnapDepth < 0) return;
        fprintf(stderr, "[unsat-diag] 完整搜索无解。最深探索: %d 条已用边, 状态=%s\n",
                bestSnapDepth,
                bestSnapStatus == 1 ? "传播判死(某格无合法配置 / 路径检查不过)" : "线路还原校验不过");
        fprintf(stderr, "[unsat-diag] 最深现场盘面 (S=IN G=OUT 数字=数字格 #=冰 .=白, -=| =线路):\n");
        renderState(snapEst);
        fprintf(stderr, "[unsat-diag] 开放端点(deg=1):");
        for (int nd = 0; nd < NN; nd++) {
            int c = nodeCell(nd), ax = nd < N ? 0 : 1;
            int d = frameConnsAxis(c, ax);
            for (int k = ax; k < 4; k += 2) {
                int e = incE[c][k];
                if (e >= 0 && e < (int)snapEst.size() && snapEst[e] == ST_USED) d++;
            }
            if (d == 1) fprintf(stderr, " (%d,%d)%s", c % W, c / W, nd < N ? "" : "/冰竖轴");
        }
        fprintf(stderr, "\n");
        if (getenv("ICELOM_DUMP")) {
            fprintf(stderr, "[unsat-diag] edges=%s", "[");
            bool first = true;
            for (int e = 0; e < nE && e < (int)snapEst.size(); e++)
                if (snapEst[e] == ST_USED) {
                    fprintf(stderr, "%s[%d,%d,%d,%d]", first ? "" : ",", min(ea[e], eb[e]) % W, min(ea[e], eb[e]) / W,
                            max(ea[e], eb[e]) % W, max(ea[e], eb[e]) / W);
                    first = false;
                }
            fprintf(stderr, "]\n");
        }
    }

    // ================= 主入口 =================
    void solve() {
        t0 = chrono::steady_clock::now();
        nodes = 0; sols = 0; doneCount = 0;
        timeUp = false; aborted = false; stopAll = false;
        if (!unsatReason.empty()) { emitDone(); return; }
        long long maxSols0 = maxSols;
        bool lastAttempt = false;
        string keepReason;
        for (size_t ii = 0; ii < inDirCands.size(); ii++) {
            for (size_t oi = 0; oi < outDirCands.size(); oi++) {
                lastAttempt = (ii + 1 == inDirCands.size() && oi + 1 == outDirCands.size());
                if (stopAll || timeUp) break;
                inDir = inDirCands[ii];
                outDir = outDirCands[oi];
                unsatReason.clear();
                if (solveMode == 1) curMaxSols = 1;                                  // 只求解: 一个就够
                else if (solveMode == 2) curMaxSols = 2;                             // 唯一性: 最多找两个
                else curMaxSols = max<long long>(1, maxSols0 - sols);                // 枚举: 剩余额度
                if (initState()) dfs();
                // 变体循环会清 unsatReason, 因此记住最后一次"结构性无解"的原因;
                // 只有最终一个解都没有时才会把它写回 done.reason(那时它才真的适用于整题)。
                if (!unsatReason.empty()) keepReason = unsatReason;
                if (solveMode == 1 && sols >= 1) break;
                if (solveMode == 2 && sols >= 2) break;
            }
            if (stopAll || timeUp) break;
            if (solveMode == 1 && sols >= 1) break;
            if (solveMode == 2 && sols >= 2) break;
        }
        if (solveMode == 2) {
            // 唯一性: 穷尽搜索后恰好一个解 ⇒ 唯一; 两个 ⇒ 不唯一; 被时限截断 ⇒ 保守报"不唯一"
            if (sols == 0) doneCount = 0;
            else if (sols >= 2) doneCount = 2;
            else doneCount = aborted ? 2 : 1;
        } else {
            doneCount = sols;
        }
        if (doneCount == 0 && unsatReason.empty()) unsatReason = keepReason;
        if (doneCount == 0 && lastAttempt) {
            if (!aborted || getenv("ICELOM_DIAG_ON_ABORT")) printUnsatDiagnostics();
        }
        emitDone();
    }

    // ================= 载入（与 v1 协议一致） =================
    bool getIntAt(const JV* v, int& x, int& y) {
        long long a, b;
        if (!v || !getInt(v->get("x"), a) || !getInt(v->get("y"), b)) return false;
        x = (int)a; y = (int)b;
        return true;
    }

    void load(const JV& root) {
        long long w, h;
        if (!getInt(root.get("w"), w) || !getInt(root.get("h"), h)) { errorMsg = "缺少 w/h"; return; }
        if (w < 1 || h < 1 || w > 64 || h > 64) { errorMsg = "盘面尺寸须在 1..64"; return; }
        W = (int)w; H = (int)h; N = W * H; NN = 2 * N;
        ctype.assign(N, 0);
        numId.assign(N, 0);
        const JV* cells = root.get("cells");
        if (!cells || cells->t != 4 || (int)cells->arr.size() != N) { errorMsg = "cells 长度须为 w*h"; return; }
        for (int i = 0; i < N; i++) {
            const JV& c = cells->arr[i];
            if (c.t != 3 || (c.str != "w" && c.str != "i")) { errorMsg = "cells 取值须为 \"w\"/\"i\""; return; }
            ctype[i] = (c.str == "i") ? 1 : 0;
        }
        const JV* jin = root.get("in");
        const JV* jout = root.get("out");
        if (!jin || !jout) { errorMsg = "缺少 in/out"; return; }
        auto onFrame = [&](int c, int s) {
            int cx = c % W, cy = c / W;
            if (s == 0) return cx == W - 1;
            if (s == 1) return cy == H - 1;
            if (s == 2) return cx == 0;
            return cy == 0;
        };
        int x, y;
        // side 缺省/null = 内部 IN/OUT: 线路以该格为起/终点, 不经过任何边框边。
        if (!getIntAt(jin, x, y)) { errorMsg = "in 格式错误"; return; }
        const JV* jinSide = jin->get("side");
        inSide = (jinSide && jinSide->t == 3) ? dirFromName(jinSide->str) : -1;
        if (x < 0 || y < 0 || x >= W || y >= H) { errorMsg = "in 位置非法"; return; }
        inCell = y * W + x;
        inInternal = (inSide < 0);
        inDir = inInternal ? -1 : opp(inSide);
        if (!inInternal && !onFrame(inCell, inSide)) { errorMsg = "IN 不在对应边框上"; return; }
        if (!getIntAt(jout, x, y)) { errorMsg = "out 格式错误"; return; }
        const JV* joutSide = jout->get("side");
        outSide = (joutSide && joutSide->t == 3) ? dirFromName(joutSide->str) : -1;
        if (x < 0 || y < 0 || x >= W || y >= H) { errorMsg = "out 位置非法"; return; }
        outCell = y * W + x;
        outInternal = (outSide < 0);
        outDir = outInternal ? -1 : outSide;
        if (!outInternal && !onFrame(outCell, outSide)) { errorMsg = "OUT 不在对应边框上"; return; }
        // 内部 IN/OUT 在冰格上时, 起始滑行方向(=所站轴)是搜索的一部分:
        //   IN: 起点格中心出发沿 dir 直行滑到落点白格; OUT: 线路沿 dir 同轴抵达终点格即停。
        //   未显式给 dir 时把所有可能作为变体在 solve() 里逐个枚举。
        int inDirOpt = -1, outDirOpt = -1;
        if (inInternal) {
            const JV* jd = jin->get("dir");
            inDirOpt = (jd && jd->t == 3) ? dirFromName(jd->str) : -1;
            if (ctype[inCell] == 0) inDirCands.assign(1, -1);          // 白格: 出发方向不受限
            else if (inDirOpt >= 0) inDirCands.assign(1, inDirOpt);
            else inDirCands = { 0, 1, 2, 3 };
        }
        else inDirCands.assign(1, opp(inSide));
        if (outInternal) {
            const JV* jd = jout->get("dir");
            outDirOpt = (jd && jd->t == 3) ? dirFromName(jd->str) : -1;
            if (ctype[outCell] == 0) outDirCands.assign(1, -1);        // 白格: 抵达方向不受限
            else if (outDirOpt >= 0) outDirCands.assign(1, outDirOpt);
            else outDirCands = { 0, 1 };                               // 两个轴各一个代表方向
        }
        else outDirCands.assign(1, outSide);
        const JV* nums = root.get("numbers");
        if (nums && nums->t == 4) {
            vector<int> seen;
            for (const JV& nm : nums->arr) {
                long long n;
                if (!getIntAt(&nm, x, y) || !getInt(nm.get("n"), n)) { errorMsg = "numbers 格式错误"; return; }
                if (x < 0 || y < 0 || x >= W || y >= H) { errorMsg = "数字位置越界"; return; }
                // n = -2 表示 "?" 格(与 pzpr 的 qnum 编码一致): 格子确定是白/冰, 数字未知。
                if (n != -2 && (n < 1 || n > 1000)) { errorMsg = "数字须为 1..1000，问号格写 -2"; return; }
                if (numId[y * W + x]) { errorMsg = "同一格放了多个数字"; return; }
                numId[y * W + x] = (int)n;
                if (n > 0) seen.push_back((int)n);
            }
            vector<int> sortedSeen = seen;
            sort(sortedSeen.begin(), sortedSeen.end());
            for (int i = 1; i < (int)sortedSeen.size(); i++) {
                if (sortedSeen[i] == sortedSeen[i - 1]) { errorMsg = "同一数字出现了两次"; return; }
            }
        }
        nV = (W - 1) * H;
        int nH = W * (H - 1);
        nE = nV + nH;
        eKind.assign(nE, 0);
        eDir.assign(nE, -1);
        ea.assign(nE, -1);
        eb.assign(nE, -1);
        incE.assign(N, { -1, -1, -1, -1 });
        for (int cy = 0; cy < H; cy++) {
            for (int cx = 0; cx < W; cx++) {
                int c = cy * W + cx;
                if (cx < W - 1) { int e = cy * (W - 1) + cx; incE[c][0] = e; ea[e] = c; eb[e] = c + 1; }
                if (cy < H - 1) { int e = nV + cy * W + cx; incE[c][1] = e; ea[e] = c; eb[e] = c + W; }
                if (cx > 0) { incE[c][2] = cy * (W - 1) + (cx - 1); }
                if (cy > 0) { incE[c][3] = nV + (cy - 1) * W + cx; }
            }
        }
        const JV* edges = root.get("edges");
        if (edges && edges->t == 4) {
            for (const JV& em : edges->arr) {
                int ex, ey;
                if (!getIntAt(&em, ex, ey)) { errorMsg = "edges 格式错误"; return; }
                int s = dirFromName(em.get("side") ? em.get("side")->str : string(""));
                string kind = em.get("kind") ? em.get("kind")->str : string("");
                if (ex < 0 || ey < 0 || ex >= W || ey >= H || s < 0) { errorMsg = "edge 位置非法"; return; }
                int c = ey * W + ex;
                int nb = c + DY[s] * W + DX[s];
                bool inside = (nb >= 0 && nb < N) && !(s == 0 && (c % W) == W - 1) && !(s == 2 && (c % W) == 0);
                int e;
                if (inside) {
                    e = incE[c][s];
                }
                else {
                    if (!onFrame(c, s)) { errorMsg = "edge 标记方向指向盘面内部却没有相邻格"; return; }
                    bool isInEdge = (c == inCell && s == inSide);
                    bool isOutEdge = (c == outCell && s == outSide);
                    if (kind == "wall") {
                        if (isInEdge) { unsatReason = "墙堵住了 IN 入口"; }
                        else if (isOutEdge) { unsatReason = "墙堵住了 OUT 出口"; }
                        continue;
                    }
                    if (kind == "segment") {
                        if (!isInEdge && !isOutEdge) { unsatReason = "边框上的线段无法被线路经过（线路只能从 IN 进、OUT 出）"; }
                        continue;
                    }
                    if (kind == "arrow") {
                        int d = dirFromName(em.get("dir") ? em.get("dir")->str : string(""));
                        if (d < 0) { errorMsg = "arrow 缺少方向"; return; }
                        if (isInEdge && d == inDir) continue;
                        if (isOutEdge && d == outDir) continue;
                        unsatReason = "边框上的箭头无法被线路按该方向经过";
                        continue;
                    }
                    errorMsg = "edge kind 须为 segment/arrow/wall";
                    return;
                }
                if (kind != "segment" && kind != "arrow" && kind != "wall") { errorMsg = "edge kind 须为 segment/arrow/wall"; return; }
                if (eKind[e] != 0) {
                    int k2 = (kind == "segment") ? 1 : (kind == "arrow") ? 2 : 3;
                    bool same = (eKind[e] == k2) && (k2 != 2 || (eDir[e] == dirFromName(em.get("dir") ? em.get("dir")->str : string(""))));
                    if (!same) { errorMsg = "同一条边被标记了两种不同含义"; return; }
                    continue;
                }
                if (kind == "segment") eKind[e] = 1;
                else if (kind == "wall") eKind[e] = 3;
                else {
                    int d = dirFromName(em.get("dir") ? em.get("dir")->str : string(""));
                    if (d < 0) { errorMsg = "arrow 缺少方向"; return; }
                    bool horiz = (s == 0 || s == 2);
                    if (horiz != (d == 0 || d == 2)) { errorMsg = "箭头方向必须与所在边垂直相交（沿行进轴）"; return; }
                    eKind[e] = 2;
                    eDir[e] = d;
                }
            }
        }
        const JV* opt = root.get("options");
        if (opt) {
            coverAll = getBool(opt->get("cover_all_whites"), true);
            startIceFree = getBool(opt->get("start_ice_free"), false);
        }
        const JV* lim = root.get("limits");
        if (lim) {
            long long ms;
            if (getInt(lim->get("max_solutions"), ms) && ms > 0) maxSols = ms;
            long long tms;
            if (getInt(lim->get("time_limit_ms"), tms) && tms > 0) timeLimitMs = (double)tms;
            const JV* jm = lim->get("mode");
            if (jm && jm->t == 3) {
                if (jm->str == "first") solveMode = 1;
                else if (jm->str == "unique") solveMode = 2;
                else if (jm->str == "all") solveMode = 0;
            }
            else if (maxSols == 1) solveMode = 2;   // 兼容旧协议: max_solutions==1 即唯一性判定
        }
    }
};

// ================= 盘面对称变换(回归/对照用) =================
// 规则对下面这些对称变换不变, 变换后的题与原题可解性等价、解一一对应。
// 求解器**不再**用"换朝向重试"碰运气; 这组变换现在只服务
// ICELOM_FORCE_KIND 的回归(T15 坐标往返 / T16 db039 各朝向纯推理)。
//
// kind 覆盖正方形的**完整对称群 D4(8 个元素)** —— 缺任何一个, 回归就没法覆盖该类变换的
// 正/逆坐标映射(尤其 5/6 两个 90° 旋转不是对合):
//   0 不变 | 1 左右镜像 | 2 上下镜像 | 3 旋转 180° | 4 转置(主对角线镜像)
//   5 顺时针 90°(=左右镜像∘转置) | 6 逆时针 90°(=上下镜像∘转置) | 7 反对角镜像(=旋转180°∘转置)
// 其中 0/1/2/3/4/7 是对合(自逆), 5/6 是一对互逆的旋转(求逆见 mapPointInv)。
// kind >= 4 的三个(以及 5/6/7)会把 W/H 互换。
void mapPoint(int kind, int W, int H, int& x, int& y) {
    if (kind == 1) x = W - 1 - x;
    else if (kind == 2) y = H - 1 - y;
    else if (kind == 3) { x = W - 1 - x; y = H - 1 - y; }
    else if (kind == 4) { int t = x; x = y; y = t; }
    else if (kind == 5) { int t = x; x = H - 1 - y; y = t; }        // 顺时针 90°
    else if (kind == 6) { int t = x; x = y; y = W - 1 - t; }        // 逆时针 90°
    else if (kind == 7) { int t = x; x = H - 1 - y; y = W - 1 - t; } // 反对角镜像
}
// 逆映射(W,H 为**当前所在盘面**的尺寸, 结果写回另一侧的坐标系)。
// 对合类直接复用 mapPoint; 两个 90° 旋转互逆。
void mapPointInv(int kind, int W, int H, int& x, int& y) {
    if (kind == 5) mapPoint(6, W, H, x, y);
    else if (kind == 6) mapPoint(5, W, H, x, y);
    else mapPoint(kind, W, H, x, y);
}

// 方向名(R/D/L/U)在变换后的名字
string mapSideName(int kind, const string& s) {
    static const char* n1[4] = { "L", "D", "R", "U" };   // flip-x: 左右互换
    static const char* n2[4] = { "R", "U", "L", "D" };   // flip-y: 上下互换
    static const char* n3[4] = { "L", "U", "R", "D" };   // rot180
    static const char* n4[4] = { "D", "R", "U", "L" };   // transpose
    static const char* n5[4] = { "D", "L", "U", "R" };   // 顺时针 90°
    static const char* n6[4] = { "U", "R", "D", "L" };   // 逆时针 90°
    static const char* n7[4] = { "U", "L", "D", "R" };   // 反对角镜像
    int i = -1;
    if (s == "R") i = 0; else if (s == "D") i = 1; else if (s == "L") i = 2;
    else if (s == "U") i = 3;
    if (i < 0) return s;
    if (kind == 1) return n1[i];
    if (kind == 2) return n2[i];
    if (kind == 3) return n3[i];
    if (kind == 4) return n4[i];
    if (kind == 5) return n5[i];
    if (kind == 6) return n6[i];
    if (kind == 7) return n7[i];
    return s;
}

JV transformInput(const JV& in, int kind) {
    if (kind == 0) return in;
    long long w = 0, h = 0;
    const JV* jw = in.get("w"); const JV* jh = in.get("h");
    if (!jw || !jh || jw->t != 2 || jh->t != 2) return in;
    w = (long long)jw->num; h = (long long)jh->num;
    JV out = in;
    int nw = (kind >= 4) ? (int)h : (int)w;   // 4/5/6/7 带转置, 尺寸互换
    int nh = (kind >= 4) ? (int)w : (int)h;
    for (auto& kv : out.obj) {
        if (kv.first == "w") { kv.second.t = 2; kv.second.num = nw; }
        else if (kv.first == "h") { kv.second.t = 2; kv.second.num = nh; }
    }
    const JV* cells = in.get("cells");
    if (cells && cells->t == 4) {
        JV nc; nc.t = 4;
        nc.arr.assign((size_t)nw * nh, JV());
        for (int y = 0; y < nh; y++)
            for (int x = 0; x < nw; x++) {
                int sx = x, sy = y;
                mapPointInv(kind, nw, nh, sx, sy);   // 新盘坐标 -> 原盘坐标
                size_t idx = (size_t)sy * (size_t)w + (size_t)sx;
                if (idx < cells->arr.size()) nc.arr[(size_t)y * nw + x] = cells->arr[idx];
            }
        for (auto& kv : out.obj) if (kv.first == "cells") kv.second = nc;
    }
    for (const char* key : { "numbers", "edges" }) {
        const JV* arr = in.get(key);
        if (!arr || arr->t != 4) continue;
        JV na; na.t = 4;
        for (const JV& it : arr->arr) {
            JV e = it;
            long long x = 0, y = 0;
            const JV* jx = it.get("x"); const JV* jy = it.get("y");
            if (!jx || !jy || jx->t != 2 || jy->t != 2) { na.arr.push_back(e); continue; }
            x = (long long)jx->num; y = (long long)jy->num;
            int nx = (int)x, ny = (int)y;
            mapPoint(kind, (int)w, (int)h, nx, ny);
            for (auto& kv : e.obj) {
                if (kv.first == "x") { kv.second.t = 2; kv.second.num = nx; }
                else if (kv.first == "y") { kv.second.t = 2; kv.second.num = ny; }
                else if (kv.first == "side" || kv.first == "dir") {
                    kv.second.t = 3; kv.second.str = mapSideName(kind, kv.second.str);
                }
            }
            na.arr.push_back(e);
        }
        for (auto& kv : out.obj) if (kv.first == key) kv.second = na;
    }
    for (const char* key : { "in", "out" }) {
        const JV* it = in.get(key);
        if (!it || it->t != 5) continue;
        const JV* jx = it->get("x"); const JV* jy = it->get("y");
        if (!jx || !jy || jx->t != 2 || jy->t != 2) continue;
        JV e = *it;
        int nx = (int)jx->num, ny = (int)jy->num;
        mapPoint(kind, (int)w, (int)h, nx, ny);
        for (auto& kv : e.obj) {
            if (kv.first == "x") { kv.second.t = 2; kv.second.num = nx; }
            else if (kv.first == "y") { kv.second.t = 2; kv.second.num = ny; }
            else if (kv.first == "side" || kv.first == "dir") {
                kv.second.t = 3; kv.second.str = mapSideName(kind, kv.second.str);
            }
        }
        for (auto& kv : out.obj) if (kv.first == key) kv.second = e;
    }
    return out;
}

int main() {
    string input;
    {
        char buf[65536];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, stdin)) > 0) input.append(buf, n);
    }
    JParser jp{ input.data(), input.data() + input.size() };
    JV root = jp.parse();
    if (jp.fail || root.t != 5) {
        printf("{\"type\":\"error\",\"message\":\"输入不是合法的 JSON 对象\"}\n");
        fflush(stdout);
        return 0;
    }
    // ================= 单颗搜索树 + 单一固定顺序 =================
    // 求解只跑一颗搜索树、一个坐标系、一个固定的扫描/分支顺序:
    //   * 不做盘面 D4 变换重试、不做多序探测择优、不做"超时后换逆向扫描序再试"——
    //     抗方向敏感性靠**推理本身**(见 docs/算法说明.md 第 3 节), 不靠换序碰运气。
    //   * options.symmetry_retry 仍然被接受(旧请求不报错), 但**完全不参与判定**。
    //
    // 调试/回归开关: ICELOM_FORCE_KIND=k 用第 k 个 D4 变换后的盘面求解(工具/测试用,
    // 见 docs/求解器协议.md §1 与 tests/run_tests.py T15)。
    int kind = 0;
    if (const char* fk = getenv("ICELOM_FORCE_KIND")) {
        int k = atoi(fk);
        if (k >= 0 && k <= 7) kind = k;
    }
    JV in2 = transformInput(root, kind);
    Solver S;
    S.outKind = kind;
    S.load(in2);
    if (!S.ok()) {
        string s = "{\"type\":\"error\",\"message\":\"" + jsonEsc(S.errorMsg) + "\"}\n";
        fwrite(s.data(), 1, s.size(), stdout);
        fflush(stdout);
        return 0;
    }
    S.solve();
    return 0;
}
