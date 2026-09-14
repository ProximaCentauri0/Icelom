#requires -Version 5.1
<#
    tools/taskset.ps1 — IceLom 项目标准任务入口（Windows / PowerShell）

    常用：
        powershell -NoProfile -File tools/taskset.ps1 build   # 编译 C++ 求解器
        powershell -NoProfile -File tools/taskset.ps1 test    # 核心回归（tests/run_tests.py）
        powershell -NoProfile -File tools/taskset.ps1 check   # 仓库一致性自检
        powershell -NoProfile -File tools/taskset.ps1 help

    设计原则：这里是"标准命令"的唯一出处；README.md / docs 只描述、不另立命令。
    每个任务都从仓库根目录执行（脚本自己定位根目录，可从任意 cwd 调用）。
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Task = 'help',

    # 透传给具体脚本的额外参数
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'                 # 所有 python 子进程用 UTF-8 输出，避免中文乱码

$Root = Split-Path -Parent $PSScriptRoot
$Gxx  = if ($env:ICELOM_GXX) { $env:ICELOM_GXX } else { 'C:\mingw64\bin\g++.exe' }

function Invoke-Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "$Name 失败（exit $LASTEXITCODE）"
    }
}

function Invoke-Py {
    param([string]$Script, [string[]]$ScriptArgs = @())
    $path = Join-Path $Root $Script
    if (-not (Test-Path $path)) { throw "找不到脚本: $Script" }
    & python -X utf8 $path @ScriptArgs
}

function Task-Build {
    if (-not (Test-Path $Gxx)) {
        throw "找不到 g++（$Gxx）。请安装 MinGW-w64，或用 `$env:ICELOM_GXX 指定路径。"
    }
    Invoke-Step "编译 icelom_solver.cpp -> icelom_solver.exe" {
        & $Gxx -O2 -std=c++17 -Wall -o (Join-Path $Root 'icelom_solver.exe') (Join-Path $Root 'icelom_solver.cpp')
    }
}

function Task-BuildPzpr {
    $pzpr = Join-Path $Root 'tools\pzprjs'
    if (-not (Test-Path (Join-Path $pzpr 'src\pzpr.js'))) {
        throw "缺少 vendored 源码树 tools\pzprjs\src（见 docs/资源与官方判别器.md）"
    }
    Invoke-Step "重建 pzpr.concat.js（官方 pzprjs 解码/判定引擎）" {
        & node (Join-Path $Root 'tools\build_concat.js')
    }
    Invoke-Step "把重建产物覆盖到运行时位置" {
        Copy-Item (Join-Path $pzpr 'dist\js\pzpr.concat.js') (Join-Path $pzpr 'pzpr.concat.js') -Force
        Copy-Item (Join-Path $pzpr 'dist\js\pzpr-variety') (Join-Path $pzpr 'pzpr-variety') -Recurse -Force
    }
    Write-Host "提示：重建后请跑 'test-all' 与 'python tools/official_check.py db039' 确认行为未变。" -ForegroundColor Yellow
}

function Task-Test {
    Invoke-Step "核心回归 tests/run_tests.py" { Invoke-Py 'tests/run_tests.py' }
}

function Task-TestAll {
    Task-Test
    Invoke-Step "接口回归 tests/solver_newapi_test.py" { Invoke-Py 'tests/solver_newapi_test.py' }
    Invoke-Step "并行求解回归 tests/parallel_solver_test.py" { Invoke-Py 'tests/parallel_solver_test.py' }
    Invoke-Step "自适应线程回归 tests/adaptive_solver_test.py" { Invoke-Py 'tests/adaptive_solver_test.py' }
    Invoke-Step "GUI 无头逻辑 tests/gui_logic_test.py"  { Invoke-Py 'tests/gui_logic_test.py' }
    Invoke-Step "URL 导入 tests/test_url_import.py"     { Invoke-Py 'tests/test_url_import.py' }
    Invoke-Step "Penpa+ 导出 tests/test_penpa_export.py" { Invoke-Py 'tests/test_penpa_export.py' }
    Invoke-Step "规则引擎 vs 官方 tests/check_engine_pzprjs.py" { Invoke-Py 'tests/check_engine_pzprjs.py' }
    Invoke-Step "规则引擎 vs 示例 tests/check_engine_examples.py" { Invoke-Py 'tests/check_engine_examples.py' }
    Invoke-Step "规则推导器回归 tests/deduce_test.py"  { Invoke-Py 'tests/deduce_test.py' }
    Invoke-Step "一致性模糊测试 tests/fuzz_diff.py 150" { Invoke-Py 'tests/fuzz_diff.py' @('150') }
    Invoke-Step "仓库一致性自检 tests/check_workspace.py" { Invoke-Py 'tests/check_workspace.py' }
}

function Task-Penpa {
    if ($Rest.Count -lt 1) { throw "用法: taskset.ps1 penpa <题.json> [json2penpa.py 的其余参数...]" }
    Invoke-Step "导出 Penpa+ 链接 tools/json2penpa.py" { Invoke-Py 'tools/json2penpa.py' $Rest }
}

function Task-Deduce {
    if ($Rest.Count -lt 1) { throw "用法: taskset.ps1 deduce <题.json> [deduce_report.py 的其余参数...]" }
    Invoke-Step "规则推导报告 tools/deduce_report.py" { Invoke-Py 'tools/deduce_report.py' $Rest }
}

function Task-Gui {
    Invoke-Step "启动 GUI" { Invoke-Py 'icelom_gui.py' $Rest }
}

function Task-Selftest {
    Invoke-Step "GUI 冒烟自测" { Invoke-Py 'icelom_gui.py' @('--selftest') }
}

function Task-Benchmark {
    Invoke-Step "性能基准 benchmark/run_benchmark.py" { Invoke-Py 'benchmark/run_benchmark.py' $Rest }
}

function Task-Audit {
    Invoke-Step "基准独立审计 tests/audit_benchmark.py" { Invoke-Py 'tests/audit_benchmark.py' $Rest }
}

function Task-Check {
    Invoke-Step "仓库一致性自检 tests/check_workspace.py" { Invoke-Py 'tests/check_workspace.py' $Rest }
}

function Task-Clean {
    $targets = @('__pycache__', 'tools\__pycache__', 'tests\__pycache__', 'benchmark\__pycache__',
                 'tools\pzprjs\dist')
    foreach ($t in $targets) {
        $p = Join-Path $Root $t
        if (Test-Path $p) { Write-Host "删除 $t"; Remove-Item $p -Recurse -Force }
    }
    Get-ChildItem -Path $Root -Recurse -File -Include '_fz_*.json', '_t.log' -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host ("删除 " + $_.FullName.Substring($Root.Length + 1)); Remove-Item $_.FullName -Force }
}

function Task-Help {
    @'
IceLom 标准任务（tools/taskset.ps1）
  调用: powershell -NoProfile -File tools/taskset.ps1 <任务> [参数...]

  build            编译 C++ 求解器 -> icelom_solver.exe
  build-pzpr       用 tools/pzprjs 的精简源码树重建官方 pzprjs 引擎
  test             核心回归测试（求解器 T1–T16 + 独立验证器）
  test-all         build 后的全套回归：接口/GUI 逻辑/URL 导入/规则引擎差分/模糊测试/自检
  gui [args...]    启动图形界面（透传参数；支持 --puzzle/--state/--shot）
  selftest         GUI 冒烟自测
  deduce <题.json> [--solution 解.json --png 图.png ...]  规则级推导报告(推到推无可推)
  penpa <题.json> [--out 链接.txt --solve --stats ...]  导出 Penpa+ 链接（--solve 带答案 ⇒ 页面可自动判定）
  benchmark [args] 全量性能基准（benchmark/run_benchmark.py）
  audit [secs]     基准题全量独立审计（独立走廊收缩模型交叉验证）
  check            仓库一致性自检（文档引用/二进制新鲜度/编码/关键入口）
  clean            清理 __pycache__、pzprjs/dist 与临时文件

环境变量：
  ICELOM_GXX       指定 g++ 路径（默认 C:\mingw64\bin\g++.exe）
'@ | Write-Host
}

Push-Location $Root
try {
    switch ($Task.ToLowerInvariant()) {
        'build'      { Task-Build }
        'build-pzpr' { Task-BuildPzpr }
        'test'       { Task-Test }
        'test-all'   { Task-TestAll }
        'gui'        { Task-Gui }
        'selftest'   { Task-Selftest }
        'deduce'     { Task-Deduce }
        'penpa'      { Task-Penpa }
        'benchmark'  { Task-Benchmark }
        'audit'      { Task-Audit }
        'check'      { Task-Check }
        'clean'      { Task-Clean }
        'help'       { Task-Help }
        default {
            Write-Host "未知任务: $Task" -ForegroundColor Red
            Task-Help
            exit 2
        }
    }
}
finally {
    Pop-Location
}
