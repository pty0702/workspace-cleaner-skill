#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描项目目录，按「可删 / 需确认 / 必留」三类输出清单和体积。

用法：
    python scan.py [目录]              # 默认当前目录
    python scan.py [目录] --json       # 输出 JSON（给程序读）
    python scan.py [目录] --top 20     # 只显示体积最大的 20 项
"""
import fnmatch
import json
import os
import sys

# ---------------- 规则 ----------------
REVERSE_DIRS = {"_probe", "samples", "captures", "dump", "dumps", "js", "_samples", "scraped"}
REVERSE_FILES = ["*.html", "*_payload.json", "*_export.json", "*_dump.json", "nuxt_goods.json"]

CACHE_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", "dist", "build",
    ".next", "target", ".cache", ".tox", ".ruff_cache", "*.egg-info",
}
CACHE_FILES = ["*.pyc", "*.pyo", "*.class", "*.o"]

LOG_DIRS = {"logs", "log", "tmp", "temp"}
LOG_FILES = ["*.log", "*.tmp", "*.out", "*.err"]

SCRIPT_PATTERNS = [
    "probe_*", "compare_*", "peek_*", "tmp_*", "_*.py", "*_old.*", "*.bak", "*.orig",
    "verify_*", "check_*.ps1", "*.py.orig",
]

CONFIRM_FILES = ["*.db", "*.sqlite", "*.sqlite3", "config.json", "*.conf", ".env", ".env.*",
                 "credentials*", "*.pem", "*.key", "secrets*",
                 "*config*.json", "*settings*.json", "filters.json", "*.ini", "*.toml"]
CONFIRM_DIRS = {"data", "db", "storage"}

KEEP_DIRS = {".git", "keys", "deploy", "docs", "tests", "test", "migrations"}
KEEP_FILES = ["README*", "LICENSE*", "*.md", "run*.bat", "start*.sh", "*.service", "Dockerfile",
              "requirements.txt", "package.json", "pyproject.toml", "setup.py", "Makefile",
              "*_ed25519", "id_rsa*", "*.pub"]


def match_any(name, patterns):
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns)


def dir_size(path):
    total = 0
    count = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except OSError:
                pass
    return total, count


def classify(root):
    """返回 {'deletable': [...], 'confirm': [...], 'keep': [...]}"""
    result = {"deletable": [], "confirm": [], "keep": []}
    root = os.path.abspath(root)

    for entry in sorted(os.listdir(root)):
        if entry == ".git":
            continue
        full = os.path.join(root, entry)
        is_dir = os.path.isdir(full)
        size, count = dir_size(full) if is_dir else (os.path.getsize(full), 1)

        item = {"name": entry, "path": full, "dir": is_dir, "size": size, "files": count,
                "reason": "", "category": ""}

        # keep 优先
        if is_dir and entry in KEEP_DIRS:
            item.update(category="keep", reason="核心目录")
            result["keep"].append(item)
            continue
        if not is_dir and match_any(entry, KEEP_FILES):
            item.update(category="keep", reason="文档/配置/启动文件")
            result["keep"].append(item)
            continue

        # confirm（数据库、配置、凭证）
        if is_dir and entry in CONFIRM_DIRS:
            item.update(category="confirm", reason="可能含历史数据")
            result["confirm"].append(item)
            continue
        if not is_dir and match_any(entry, CONFIRM_FILES):
            item.update(category="confirm", reason="可能含数据或凭证")
            result["confirm"].append(item)
            continue

        # deletable
        if is_dir and (entry in REVERSE_DIRS or match_any(entry, CACHE_DIRS)):
            cat = "逆向/抓取产物" if entry in REVERSE_DIRS else "构建缓存"
            item.update(category="deletable", reason=cat)
            result["deletable"].append(item)
            continue
        if is_dir and entry in LOG_DIRS:
            item.update(category="deletable", reason="运行日志")
            result["deletable"].append(item)
            continue
        if not is_dir:
            if match_any(entry, CACHE_FILES):
                item.update(category="deletable", reason="构建缓存")
                result["deletable"].append(item)
                continue
            if match_any(entry, LOG_FILES):
                item.update(category="deletable", reason="运行日志")
                result["deletable"].append(item)
                continue
            if match_any(entry, REVERSE_FILES):
                item.update(category="deletable", reason="抓取样本")
                result["deletable"].append(item)
                continue
            if match_any(entry, SCRIPT_PATTERNS):
                item.update(category="deletable", reason="一次性脚本")
                result["deletable"].append(item)
                continue

        # 其余归「必留」（无法识别的一律不动）
        item.update(category="keep", reason="未识别，默认保留")
        result["keep"].append(item)

    for key in result:
        result[key].sort(key=lambda x: -x["size"])
    return result


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else "."
    want_json = "--json" in sys.argv
    top = 50
    if "--top" in sys.argv:
        try:
            top = int(sys.argv[sys.argv.index("--top") + 1])
        except (ValueError, IndexError):
            pass

    if not os.path.isdir(root):
        print("目录不存在: %s" % root)
        return 2

    data = classify(root)

    if want_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    total_all = sum(i["size"] for k in data for i in data[k])
    total_del = sum(i["size"] for i in data["deletable"])
    total_conf = sum(i["size"] for i in data["confirm"])

    print("=" * 78)
    print("工作区扫描: %s" % os.path.abspath(root))
    print("总大小 %s | 可删 %s (%.0f%%) | 需确认 %s | 必留 %s"
          % (human(total_all), human(total_del),
             100.0 * total_del / total_all if total_all else 0,
             human(total_conf), human(total_all - total_del - total_conf)))
    print("=" * 78)

    def show(title, items, mark):
        print("\n%s %s（%d 项, %s）" % (mark, title, len(items),
                                       human(sum(i["size"] for i in items))))
        print("-" * 78)
        for it in items[:top]:
            print("  %-42s %-6s %s" % (
                (it["name"] + ("/" if it["dir"] else ""))[:42],
                human(it["size"]),
                it["reason"],
            ))
        if len(items) > top:
            print("  ... 还有 %d 项（用 --top 调整）" % (len(items) - top))

    show("可删（垃圾）", data["deletable"], "✅")
    show("需确认（先问人）", data["confirm"], "⚠️ ")
    show("必留", data["keep"], "🔒")

    print("\n下一步：")
    print("  1) 把「需确认」的逐条问用户（数据库别处有没有副本？配置删了要不要重配？）")
    print("  2) python clean.py --dry-run --all          先演练")
    print("  3) python clean.py --all --backup           真删（自动备份需确认项）")
    print("  4) 删完校验：compileall / pytest / git status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
