#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按类别清理工作区垃圾，支持演练、分类选择、自动备份。

用法：
    python clean.py --dry-run --all                  # 演练，只打印不删
    python clean.py --all                            # 删「可删」三类
    python clean.py --reverse --scripts              # 只删逆向产物和一次性脚本
    python clean.py --all --backup                   # 删前把「需确认」项打包到工作区外
    python clean.py --all --backup --confirm         # 连「需确认」的一起删（危险，必须加 --confirm）

类别参数：
    --reverse   逆向/抓取产物（_probe、samples、js、*.html 样本…）
    --cache     构建缓存（__pycache__、node_modules、dist…）
    --logs      运行日志（logs/、*.log）
    --scripts   一次性脚本（probe_*、compare_*、_*.py…）
    --all       以上全部
    --confirm   额外处理「需确认」项（数据库、配置、凭证）——必须显式加
"""
import os
import shutil
import sys
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan as scanner  # noqa: E402


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def backup_items(root, items):
    """把要删的项打包到工作区外的 zip，返回备份路径。"""
    if not items:
        return None
    parent = os.path.dirname(os.path.abspath(root))
    name = os.path.basename(os.path.abspath(root)) or "workspace"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(parent, "_backup_%s_%s.zip" % (name, stamp))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for it in items:
            path = it["path"]
            if it["dir"]:
                for cur, dirs, files in os.walk(path):
                    dirs[:] = [d for d in dirs if d != ".git"]
                    for f in files:
                        full = os.path.join(cur, f)
                        try:
                            zf.write(full, os.path.relpath(full, root))
                        except OSError:
                            pass
            else:
                try:
                    zf.write(path, os.path.relpath(path, root))
                except OSError:
                    pass
    return zip_path


def remove_item(it):
    path = it["path"]
    try:
        if it["dir"]:
            shutil.rmtree(path, ignore_errors=False)
        else:
            os.remove(path)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main():
    root = None
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            root = a
            break
    root = root or "."

    if not os.path.isdir(root):
        print("目录不存在: %s" % root)
        return 2

    dry = "--dry-run" in sys.argv
    do_backup = "--backup" in sys.argv
    with_confirm = "--confirm" in sys.argv

    want = set()
    if "--all" in sys.argv:
        want |= {"reverse", "cache", "logs", "scripts"}
    if "--reverse" in sys.argv:
        want.add("reverse")
    if "--cache" in sys.argv:
        want.add("cache")
    if "--logs" in sys.argv:
        want.add("logs")
    if "--scripts" in sys.argv:
        want.add("scripts")

    if not want and not with_confirm:
        print(__doc__)
        return 1

    data = scanner.classify(root)

    # 按 reason 把 deletable 再细分，方便按 --reverse 之类筛选
    def pick():
        chosen = []
        for it in data["deletable"]:
            r = it["reason"]
            if r == "逆向/抓取产物" and "reverse" in want:
                chosen.append(it)
            elif r == "构建缓存" and "cache" in want:
                chosen.append(it)
            elif r == "运行日志" and "logs" in want:
                chosen.append(it)
            elif r in ("一次性脚本", "抓取样本") and "scripts" in want:
                chosen.append(it)
        return chosen

    targets = pick()
    confirm_targets = data["confirm"] if with_confirm else []

    total = sum(i["size"] for i in targets + confirm_targets)
    print("=" * 78)
    print("目标目录: %s" % os.path.abspath(root))
    print("模式    : %s" % ("演练（不会真删）" if dry else "真删"))
    print("范围    : %s%s" % (", ".join(sorted(want)) or "（无）",
                              "  + 需确认项" if with_confirm else ""))
    print("待处理  : %d 项 / %s" % (len(targets + confirm_targets), human(total)))
    print("=" * 78)

    for it in targets + confirm_targets:
        tag = "⚠️ " if it in confirm_targets else "  "
        print("%s%-46s %-8s %s" % (tag, (it["name"] + ("/" if it["dir"] else ""))[:46],
                                   human(it["size"]), it["reason"]))

    if dry:
        print("\n演练结束。去掉 --dry-run 才会真删。")
        return 0

    if not targets and not confirm_targets:
        print("\n没有需要处理的东西。")
        return 0

    # 备份（需确认项）
    if do_backup and confirm_targets:
        zp = backup_items(root, confirm_targets)
        if zp:
            print("\n已备份到: %s（%s）" % (zp, human(os.path.getsize(zp))))

    # 真删
    ok = fail = 0
    freed = 0
    print()
    for it in targets + confirm_targets:
        good, err = remove_item(it)
        if good:
            ok += 1
            freed += it["size"]
            print("  ✅ 删除 %s" % it["name"])
        else:
            fail += 1
            print("  ❌ 失败 %s -> %s" % (it["name"], err[:80]))

    print("\n完成：成功 %d，失败 %d，释放 %s" % (ok, fail, human(freed)))
    if fail:
        print("失败的通常是「进程占用句柄」（Windows）或权限不足，关掉相关程序后重试。")
    print("\n下一步：")
    print("  1) 校验：python -m compileall -q <包名> / pytest / npm run build")
    print("  2) git status --short 看删了什么")
    print("  3) git add -A && git commit -m \"清理工作区垃圾\"")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
