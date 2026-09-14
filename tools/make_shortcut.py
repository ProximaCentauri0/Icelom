# -*- coding: utf-8 -*-
"""make_shortcut.py — 给 IceLom 建"带图标"的 Windows 快捷方式 / 启动器。

为什么需要这个
--------------
用 `python icelom_gui.py` 启动时, 进程是 **python.exe**：Windows 任务栏默认按进程取图标,
于是任务栏显示 python.exe 的图标 —— 窗口里设 `iconbitmap` 改不了它。
让任务栏显示 IceLom 图标的做法是"让启动它的东西带图标":
    * 快捷方式(.lnk) 自带 IconLocation，且目标进程设置了同一个 AppUserModelID
      （`icelom_gui.py` 的 `_set_app_user_model_id()`）⇒ 任务栏用 .lnk 的图标;
    * 顺带也就有了"快捷打开方式"（桌面 / 开始菜单 / 项目根三选一）。

用法:
    python -X utf8 tools/make_shortcut.py                 # 桌面 + 开始菜单 + 项目根
    python -X utf8 tools/make_shortcut.py --desktop       # 只要桌面
    python -X utf8 tools/make_shortcut.py --start-menu    # 只要开始菜单
    python -X utf8 tools/make_shortcut.py --here          # 只要项目根的那个

产物（可随时重建/删除）：上述 .lnk，以及 `tools/launch_icelom.cmd`（没有快捷方式也能双击启动）。
桌面/开始菜单写不进去时（受限环境）脚本不会失败，只提示手动跑一次那两条命令。
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUI = os.path.join(ROOT, "icelom_gui.py")
ICON = os.path.join(ROOT, "assets", "icelom.ico")
# 必须与 icelom_gui.py 里的 APP_ID 一致 —— 两边一样, 任务栏才会把窗口与快捷方式配上对
APP_ID = "Icelom.Solver.GUI"
LNK_NAME = "IceLom 冰宫巡游.lnk"
CMD = os.path.join(HERE, "launch_icelom.cmd")

CMD_BODY = """@echo off
rem launch_icelom.cmd — 双击即可启动 IceLom 界面（比敲 python 命令行省事）
rem 任务栏图标见 tools/make_shortcut.py 的说明
setlocal
cd /d "%~dp0.."
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw -X utf8 "icelom_gui.py" %*
) else (
    python -X utf8 "icelom_gui.py" %*
)
"""

# 给 .lnk 写入 AppUserModelID（= icelom_gui.py 里 _set_app_user_model_id 用的值）。
# 这是"任务栏认出该用快捷方式图标"的关键：Windows 按 AppUserModelID 把窗口与快捷方式配对，
# 配上了就用 .lnk 的 IconLocation，配不上就去翻进程可执行文件(python.exe)的图标。
# 模板用 @@X@@ 占位符替换（PS 里全是 {} 和 $，不适合用 str.format）。
PS_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
$lnk = '@@LNK@@'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = '@@TARGET@@'
$s.Arguments = '@@ARGS@@'
$s.WorkingDirectory = '@@WORKDIR@@'
$s.IconLocation = '@@ICON@@,0'
$s.Description = 'IceLom 冰宫巡游通用求解器'
$s.Save()

if (-not ('PropStore' -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class PropStore {
  [StructLayout(LayoutKind.Sequential, Pack=4)]
  public struct PROPERTYKEY { public Guid fmtid; public uint pid; }
  [StructLayout(LayoutKind.Explicit)]
  public struct PROPVARIANT {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr p;
  }
  [DllImport("shell32.dll", CharSet=CharSet.Unicode)]
  public static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr pbc,
      int flags, ref Guid riid, out IntPtr ppv);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)]
  public delegate int SetValueDelegate(IntPtr self, ref PROPERTYKEY key, ref PROPVARIANT value);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)]
  public delegate int CommitDelegate(IntPtr self);
  public static int SetAppId(string path, string value) {
    Guid iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
    IntPtr ps;
    int hr = SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out ps);
    if (hr != 0) return hr;
    var key = new PROPERTYKEY();
    key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
    key.pid = 5;
    var pv = new PROPVARIANT();
    pv.vt = 31;
    pv.p = Marshal.StringToCoTaskMemUni(value);
    IntPtr vtbl = Marshal.ReadIntPtr(ps);
    IntPtr setAddr = Marshal.ReadIntPtr(vtbl, 6 * IntPtr.Size);
    var set = (SetValueDelegate)Marshal.GetDelegateForFunctionPointer(setAddr, typeof(SetValueDelegate));
    hr = set(ps, ref key, ref pv);
    IntPtr commitAddr = Marshal.ReadIntPtr(vtbl, 7 * IntPtr.Size);
    var commit = (CommitDelegate)Marshal.GetDelegateForFunctionPointer(commitAddr, typeof(CommitDelegate));
    if (hr == 0) hr = commit(ps);
    Marshal.FreeCoTaskMem(pv.p);
    Marshal.Release(ps);
    return hr;
  }
}
"@
}
$hr = [PropStore]::SetAppId($lnk, '@@APPID@@')
# S_OK(0) = 写入成功; S_FALSE(1) = 值已经在里面了(重复运行时会这样) —— 都算成功
if ($hr -eq 0 -or $hr -eq 1) { Write-Output 'OK' }
else { Write-Output ("APPID_WARN 0x{0:X8}" -f $hr) }
"""


def powershell_exe():
    from shutil import which
    for exe in ("powershell.exe", "pwsh.exe"):
        found = which(exe)
        if found:
            return found
    return None


def make_lnk(lnk_path, python_exe, use_pythonw=True):
    """建一个快捷方式（Target 指向 python/pythonw, 参数指向 icelom_gui.py）。

    返回实际使用的 target；目录/文件不可写时抛 PermissionError 让调用方决定怎么提示。
    """
    parent = os.path.dirname(lnk_path)
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as e:
        raise PermissionError("目录不可写 (%s)" % e)
    target = python_exe
    if use_pythonw:
        candi = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
        if os.path.exists(candi):
            target = candi
    ps = (PS_TEMPLATE
          .replace("@@LNK@@", lnk_path)
          .replace("@@TARGET@@", target)
          .replace("@@ARGS@@", '-X utf8 "%s"' % GUI)
          .replace("@@WORKDIR@@", ROOT)
          .replace("@@ICON@@", ICON)
          .replace("@@APPID@@", APP_ID))
    # PS 单引号字符串里的单引号要写成两个（路径里正常不会出现, 保险起见）
    ps = ps.replace("''", "'")
    exe = powershell_exe()
    if not exe:
        raise RuntimeError("找不到 powershell.exe / pwsh.exe，无法创建快捷方式")
    r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", ps],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0 or not os.path.exists(lnk_path):
        if "Unable to save shortcut" in out or "UnauthorizedAccess" in out:
            raise PermissionError("没有写权限")
        raise RuntimeError("创建快捷方式失败: %s" % out[:300])
    if "APPID_WARN" in out:
        print("  （AppUserModelID 写入失败: %s —— 快捷方式仍可用, 只是任务栏可能不认它）"
              % out.strip().splitlines()[-1])
    return target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desktop", action="store_true", help="在桌面建快捷方式")
    ap.add_argument("--start-menu", action="store_true", help="在开始菜单建快捷方式")
    ap.add_argument("--here", action="store_true", help="在项目目录建快捷方式")
    args = ap.parse_args()
    if not (args.desktop or args.start_menu or args.here):
        args.desktop = args.start_menu = args.here = True

    if sys.platform != "win32":
        raise SystemExit("这个脚本只用于 Windows（其它系统请直接 python icelom_gui.py）")
    for need in (GUI, ICON):
        if not os.path.exists(need):
            raise SystemExit("缺少 %s（先跑 tools/make_icon.py 生成图标）" % need)

    # 1. 启动器.cmd（没有快捷方式也能双击启动；它启动的仍是 python, 但少了敲命令的麻烦）
    with open(CMD, "w", encoding="utf-8", newline="\r\n") as f:   # .cmd 用 CRLF 更稳
        f.write(CMD_BODY)
    print("WROTE", os.path.relpath(CMD, ROOT))

    # 2. 快捷方式（桌面/开始菜单优先，程序目录里那个一定建得成，受限环境下也能用）
    targets = []
    if args.here:
        targets.append(os.path.join(ROOT, LNK_NAME))
    if args.desktop:
        targets.append(os.path.join(os.path.expanduser("~"), "Desktop", LNK_NAME))
    if args.start_menu:
        targets.append(os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                    "Microsoft", "Windows", "Start Menu", "Programs", LNK_NAME))
    blocked = []
    for lnk in targets:
        try:
            used = make_lnk(lnk, sys.executable)
        except PermissionError as e:
            blocked.append((lnk, str(e)))
            continue
        print('WROTE %s\n      → "%s" -X utf8 "%s"   (icon: %s)'
              % (lnk, used, GUI, os.path.relpath(ICON, ROOT)))

    for lnk, why in blocked:
        print("[跳过] %s —— %s" % (lnk, why))
    if blocked:
        print("\n桌面/开始菜单那两个请在**普通命令行**里自己跑一次（受限环境写不进去）：")
        print("    cd /d %s" % ROOT)
        print("    python -X utf8 tools\\make_shortcut.py --desktop --start-menu")
    print("\n任务栏图标由**快捷方式**提供：请从快捷方式或 tools\\launch_icelom.cmd 启动。")
    print("直接敲 `python icelom_gui.py` 时进程是 python.exe，任务栏可能仍用它的图标兜底。")
    print("改过 assets/icelom.ico 后重跑本脚本即可让快捷方式指向新图标。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
