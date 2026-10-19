#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读递归扫描与批量报告；仅使用标准库，兼容 Python 3.8。"""
import argparse
import fnmatch
import hashlib
import html
import json
import os
import stat
import sys
import time
from pathlib import Path

BUCKETS = ("deletable", "confirm", "keep")
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules",
              ".next", ".cache", ".tox", ".ruff_cache", "*.egg-info"}
CACHE_FILES = {"*.pyc", "*.pyo", "*.class", "*.o"}
LOG_DIRS = {"logs", "log", "tmp", "temp"}
LOG_FILES = {"*.log", "*.tmp", "*.out", "*.err"}
REVERSE_DIRS = {"_probe", "samples", "captures", "dump", "dumps", "js", "_samples", "scraped"}
REVERSE_FILES = {"*.html", "*_payload.json", "*_export.json", "*_dump.json"}
SCRIPT_PATTERNS = {"probe_*", "compare_*", "peek_*", "tmp_*", "_*.py",
                   "*_old.*", "*.bak", "*.orig", "verify_*", "check_*.ps1"}
CONFIRM_FILES = {"*.db", "*.sqlite", "*.sqlite3", "*.fdb", "*.gdb", "*.mdb",
                 "*.accdb", "*.pem", "*.key", ".env", ".env.*", "credentials*",
                 "secrets*", "*config*.json", "*settings*.json", "*.conf", "*.ini", "*.toml"}
CONFIRM_DIRS = {"data", "db", "storage", ".venv", "venv", "dist", "build", "target"}
KEEP_DIRS = {".git", "keys", "docs", "tests", "test", "deploy", "migrations"}
KEEP_FILES = {"README*", "LICENSE*", "*.md", "run*.bat", "start*.sh", "*.service",
              "Dockerfile", "requirements.txt", "package.json", "pyproject.toml",
              "setup.py", "Makefile", "__init__.py", "__main__.py", "conftest.py",
              "id_rsa*", "*_ed25519", "*.pub"}
PRIVATE_FILES = {"id_rsa*", "id_ed25519*", "*_ed25519", "id_ecdsa*", "id_dsa*"}
SOURCE_SUFFIXES = {".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".java", ".smali", ".go", ".rs"}
SOURCE_DIRS = {"src", "source", "sources", "lib", "libs", "docs", "tests", "test", "deploy", "migrations"}
PACKAGED_DIRS = {"payload", "{app}", "release", "releases", "dist-app", "app.asar.unpacked"}
WINDOWS_DEVICES = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {prefix + str(number) for prefix in ("com", "lpt") for number in range(1, 10)}

def is_device(path):
    name = os.path.basename(os.fspath(path)).rstrip(" .").split(".", 1)[0].lower()
    return os.name == "nt" and name in WINDOWS_DEVICES

def match_any(name, patterns):
    return any(fnmatch.fnmatchcase(name.lower(), pattern.lower()) for pattern in patterns)

def is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & REPARSE)

def human(size):
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return "%.2f %s" % (value, unit)
        value /= 1024

def _error(state, path, exc):
    state["errors"].append({"path": str(path), "error": str(exc)})

def _entries(state, path):
    try:
        with os.scandir(path) as entries:
            return sorted(entries, key=lambda entry: entry.name.casefold())
    except OSError as exc:
        _error(state, path, exc)
        return []

def _stat(state, path):
    if is_device(path):
        state["skipped"].append({"path": str(path), "reason": "Windows 保留设备名"})
        return None
    try:
        info = os.lstat(path)
        if state.get("progress"):
            state["progress"](str(path))
        return info
    except OSError as exc:
        _error(state, path, exc)
        return None

def _inventory(path, state):
    """一次遍历完成体积、文件数、重要资产检查和元数据指纹；不读文件内容。"""
    digest = hashlib.sha256()
    result = {"size": 0, "files": 0, "protected": False,
              "important": False, "source": False, "blocked": False}
    error_start = len(state["errors"])
    def visit(current):
        info = _stat(state, current)
        if info is None:
            result["blocked"] = True
            return
        name = os.path.basename(current).lower()
        relative = os.path.relpath(current, path)
        record = (relative, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino)
        digest.update(repr(record).encode("utf-8", errors="surrogatepass"))
        if is_link(info):
            state["skipped"].append({"path": current, "reason": "链接或重解析点"})
            result["blocked"] = True
            return
        if name == ".git":
            state["skipped"].append({"path": current, "reason": "Git 元数据"})
            result["protected"] = True
            return
        if name == "keys" or name.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")) or name.endswith("_ed25519"):
            result["protected"] = True
        if stat.S_ISDIR(info.st_mode):
            for entry in _entries(state, current):
                visit(entry.path)
        elif stat.S_ISREG(info.st_mode):
            result["size"] += info.st_size
            result["files"] += 1
            if not result["important"] and match_any(name, CONFIRM_FILES):
                result["important"] = True
            if not result["source"] and (Path(name).suffix in SOURCE_SUFFIXES or match_any(name, KEEP_FILES)):
                result["source"] = True
        else:
            result["blocked"] = True
            state["skipped"].append({"path": current, "reason": "非常规文件"})
    visit(str(path))
    result["blocked"] |= len(state["errors"]) > error_start
    result["signature"] = digest.hexdigest()
    return result

def snapshot(path):
    state = {"errors": [], "skipped": []}
    result = _inventory(str(path), state)
    result.update(errors=state["errors"], skipped=state["skipped"])
    return result

def _context(path, root):
    parts = [Path(root).name.lower()] + [part.lower() for part in Path(os.path.relpath(path, root)).parts]
    source = any(part in SOURCE_DIRS or part.startswith("smali") for part in parts[:-1])
    browser = any("profile" in part or "leveldb" in part or "indexeddb" in part
                  or part in {"local storage", "session storage", "webstorage", "user-data", "userdata"}
                  for part in parts)
    packaged = any(part in PACKAGED_DIRS or part.startswith("dist-") for part in parts[:-1])
    return source, browser, packaged

def _rule(path, directory, root):
    name = os.path.basename(path).lower()
    source, browser, packaged = _context(path, root)
    if name == "keys" or match_any(name, PRIVATE_FILES):
        return "keep", "core", "密钥资产，保留"
    if browser:
        return "confirm", "data", "浏览器持久化数据或数据库日志"
    if directory:
        if match_any(name, CACHE_DIRS):
            return ("confirm", "cache", "打包程序内的依赖，需核实") if packaged else ("deletable", "cache", "缓存或可重建依赖")
        if name in CONFIRM_DIRS:
            return "confirm", "data", "数据、环境或交付产物，需核实"
        if name in LOG_DIRS:
            return ("keep", "source", "源码命名空间内的 log/temp") if source else ("deletable", "logs", "日志或临时目录候选")
        if name in REVERSE_DIRS:
            return ("keep", "source", "源码或测试资源") if source else ("confirm", "reverse", "样本目录名称命中，需核实用途")
        return "walk", "unknown", ""
    if match_any(name, KEEP_FILES):
        return "keep", "core", "文档、源码入口或核心文件"
    if match_any(name, CONFIRM_FILES):
        return "confirm", "data", "数据库、配置或凭证"
    if match_any(name, CACHE_FILES):
        return ("confirm", "cache", "打包程序内的编译文件") if packaged else ("deletable", "cache", "编译缓存候选")
    if source:
        return "keep", "source", "源码、部署或测试文件"
    if match_any(name, LOG_FILES):
        return ("confirm", "logs", "输出或打包资源，需核实") if packaged or name.endswith((".out", ".err")) else ("deletable", "logs", "日志或临时文件候选")
    if match_any(name, REVERSE_FILES):
        return "confirm", "reverse", "HTML 或导出文件，可能仍被项目使用"
    if match_any(name, SCRIPT_PATTERNS):
        return "confirm", "scripts", "脚本或备份，需核实是否仍在使用"
    return "keep", "unknown", "未识别，保留"

def _item(path, category, kind, reason, info, directory):
    return {"name": os.path.basename(path), "path": path, "dir": directory,
            "category": category, "kind": kind, "reason": reason,
            "size": info["size"], "files": info["files"],
            "signature": info.get("signature"), "blocked": info.get("blocked", False) or info.get("protected", False)}

def classify(root, progress=None, targets=None):
    root = os.path.abspath(os.fspath(root))
    if not os.path.isdir(root):
        raise ValueError("目录不存在：" + root)
    state = {"errors": [], "skipped": [], "progress": progress}
    root_info = os.lstat(root)
    def visit(path, info):
        if is_link(info) or os.path.basename(path).lower() == ".git":
            _inventory(path, state)
            return []
        directory = stat.S_ISDIR(info.st_mode)
        category, kind, reason = _rule(path, directory, root)
        if directory and category == "walk":
            children = []
            for entry in _entries(state, path):
                child_info = _stat(state, entry.path)
                if child_info is not None:
                    children.extend(visit(entry.path, child_info))
            if children and all(item["category"] == "keep" for item in children):
                totals = {"size": sum(item["size"] for item in children),
                          "files": sum(item["files"] for item in children),
                          "blocked": any(item["blocked"] for item in children)}
                return [_item(path, "keep", "unknown", "普通源码及项目文件", totals, True)]
            return children
        inventory = _inventory(path, state)
        if inventory["blocked"] or inventory["protected"]:
            category, reason = "keep", "含受保护资产、链接或无法读取的内容，禁止整体删除"
        elif category == "deletable" and kind == "logs" and (inventory["important"] or inventory["source"]):
            category, reason = "confirm", "日志或临时项内含数据库、配置、源码或文档"
        elif category == "deletable" and inventory["important"]:
            category, reason = "confirm", "缓存候选内含数据库、配置或凭证"
        return [_item(path, category, kind, reason, inventory, directory)]
    if is_link(root_info):
        _inventory(root, state)
        items = []
    else:
        items = []
        paths = [entry.path for entry in _entries(state, root)] if targets is None else [os.path.abspath(os.fspath(path)) for path in targets]
        for path in paths:
            if os.path.commonpath([root, path]) != root or path == root:
                raise ValueError("扫描目标必须是项目内的具体条目：" + path)
            if targets is not None:
                for parent in Path(os.path.relpath(path, root)).parents:
                    ancestor = os.path.join(root, str(parent))
                    if is_link(os.lstat(ancestor)):
                        raise ValueError("扫描目标的父路径含链接：" + ancestor)
            info = _stat(state, path)
            if info is not None:
                items.extend(visit(path, info))
    result = {"root": root}
    for bucket in BUCKETS:
        result[bucket] = sorted((item for item in items if item["category"] == bucket),
                                key=lambda item: item["size"], reverse=True)
    result["errors"], result["skipped"] = state["errors"], state["skipped"]
    result["summary"] = {"size": sum(item["size"] for item in items),
                         "files": sum(item["files"] for item in items)}
    for bucket in BUCKETS:
        result["summary"][bucket] = sum(item["size"] for item in result[bucket])
    return result

def _reports(data):
    return data["projects"] if "projects" in data else [data]

def write_report(data, output):
    """JSON 保留完整清单；HTML 可逐项目展开，不执行任何脚本。"""
    target = Path(output)
    if target.suffix.lower() == ".json":
        text = json.dumps(data, ensure_ascii=False, indent=2)
    elif target.suffix.lower() == ".html":
        esc = html.escape
        parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>工作区扫描报告</title><style>body{font:15px/1.6 sans-serif;max-width:1400px;margin:30px auto;padding:0 18px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ddd;text-align:left;overflow-wrap:anywhere}details{padding:12px;margin:12px 0;border:1px solid #ccc}summary{cursor:pointer}small{color:#555}</style><h1>工作区只读扫描报告</h1><p>按逻辑大小统计；排除 Git 元数据、链接和无法读取的内容。候选项仍需核实用途，实际释放空间可能不同。未执行清理。</p>']
        projects = _reports(data)
        parts.append("<table><tr><th>目录</th><th>扫描大小</th><th>可清理候选</th><th>需确认</th><th>保留</th><th>读取错误</th></tr>")
        for report in projects:
            summary = report["summary"]
            parts.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td></tr>" % (
                esc(report["root"]), human(summary["size"]), human(summary["deletable"]),
                human(summary["confirm"]), human(summary["keep"]), len(report["errors"])))
        parts.append("</table>")
        if "projects" in data and data.get("skipped"):
            parts.append("<h2>父目录中排除的入口</h2>")
            for entry in data["skipped"]:
                parts.append("<p>%s：%s</p>" % (esc(entry["path"]), esc(entry["reason"])))
        for report in projects:
            parts.append("<details><summary>%s</summary>" % esc(report["root"]))
            for bucket, title in (("deletable", "可清理候选"), ("confirm", "需确认"), ("keep", "保留")):
                parts.append("<h2>%s</h2><table><tr><th>相对路径</th><th>大小</th><th>判据</th></tr>" % title)
                for item in report[bucket]:
                    parts.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                        esc(os.path.relpath(item["path"], report["root"])), human(item["size"]), esc(item["reason"])))
                parts.append("</table>")
            for entry in report["errors"] + report["skipped"]:
                parts.append("<p>%s：%s</p>" % (esc(entry["path"]), esc(entry.get("error", entry.get("reason", "")))))
            parts.append("</details>")
        text = "".join(parts) + "</html>"
    else:
        raise ValueError("报告后缀必须为 .json 或 .html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="项目目录或批量扫描的父目录")
    parser.add_argument("--batch", action="store_true", help="逐个扫描父目录下的一级文件夹")
    parser.add_argument("--json", action="store_true", help="标准输出使用 JSON")
    parser.add_argument("--top", type=int, default=50, help="每类显示的最多条目数")
    parser.add_argument("--output", help="保存 .html 或 .json 报告")
    args = parser.parse_args(argv)
    if args.top < 1:
        parser.error("--top 必须大于 0")
    if args.output and Path(args.output).suffix.lower() not in {".json", ".html"}:
        parser.error("--output 后缀必须为 .json 或 .html")
    last = [time.monotonic()]
    def progress(path):
        if time.monotonic() - last[0] >= 20:
            print("正在扫描：" + path, file=sys.stderr, flush=True)
            last[0] = time.monotonic()
    try:
        root = os.path.abspath(args.root)
        if not os.path.isdir(root):
            raise ValueError("目录不存在：" + root)
        if args.batch:
            if is_link(os.lstat(root)):
                raise ValueError("批量扫描根目录不能是链接或目录联接")
            roots, skipped = [], []
            with os.scandir(root) as handle:
                for entry in handle:
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if is_link(info) or entry.name.lower() == ".git":
                            skipped.append({"path": entry.path, "reason": "Git 元数据、链接或重解析点"})
                        elif stat.S_ISDIR(info.st_mode):
                            roots.append(entry.path)
                    except OSError as exc:
                        roots.append(entry.path)
            roots.sort(key=str.casefold)
            projects = []
            for index, path in enumerate(roots, 1):
                print("扫描 %d/%d：%s" % (index, len(roots), path), file=sys.stderr, flush=True)
                try:
                    projects.append(classify(path, progress))
                except (OSError, ValueError) as exc:
                    failed = {"root": path, "errors": [{"path": path, "error": str(exc)}], "skipped": []}
                    failed.update({bucket: [] for bucket in BUCKETS})
                    failed["summary"] = {key: 0 for key in ("size", "files") + BUCKETS}
                    projects.append(failed)
            data = {"batch_root": root, "projects": projects, "skipped": skipped}
            data["summary"] = {key: sum(project["summary"][key] for project in projects)
                               for key in ("size", "files") + BUCKETS}
        else:
            data = classify(root, progress)
        if args.output:
            write_report(data, args.output)
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            for report in _reports(data):
                print("\n目录：%s；扫描大小：%s；文件：%d" % (report["root"], human(report["summary"]["size"]), report["summary"]["files"]))
                for bucket, title in (("deletable", "可清理候选"), ("confirm", "需确认"), ("keep", "保留")):
                    print("%s：%d 项，%s" % (title, len(report[bucket]), human(report["summary"][bucket])))
                    for item in report[bucket][:args.top]:
                        print("  %s  %s  %s" % (human(item["size"]), os.path.relpath(item["path"], report["root"]), item["reason"]))
                print("读取错误：%d；排除/跳过：%d" % (len(report["errors"]), len(report["skipped"])))
            if args.output:
                print("报告：" + os.path.abspath(args.output))
            if data.get("skipped") and "projects" in data:
                print("父目录排除的 Git/链接入口：%d 项" % len(data["skipped"]))
        return 1 if any(report["errors"] for report in _reports(data)) else 0
    except (OSError, ValueError) as exc:
        print("扫描失败：" + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
