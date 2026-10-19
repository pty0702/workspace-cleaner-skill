#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""默认演练；真正删除必须 --apply，需确认项必须逐项 --include --confirm。"""
import argparse
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import scan as scanner

def _no_links(path, allow_missing=False):
    if any(scanner.is_device(part) for part in Path(path).parts):
        raise ValueError("路径含 Windows 保留设备名：" + str(path))
    absolute = Path(os.path.abspath(path))
    for part in list(reversed(absolute.parents)) + [absolute]:
        try:
            info = os.lstat(str(part))
        except FileNotFoundError:
            if allow_missing:
                continue
            raise
        if scanner.is_link(info):
            raise ValueError("路径含链接或目录联接：" + str(part))
    return absolute

def safe_target(root, path):
    """删除和备份共用边界检查；根目录、Git 元数据和密钥不可选中。"""
    root = _no_links(root).resolve(strict=True)
    target = _no_links(path).resolve(strict=True)
    if root == root.parent or root.name.lower() in {".git", "keys"}:
        raise ValueError("不能以磁盘根、Git 元数据或密钥目录为清理根")
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise ValueError("目标越出清理根目录：" + str(target))
    if not relative.parts:
        raise ValueError("不能删除清理根目录本身")
    if any(part.lower() in {".git", "keys"} for part in relative.parts) or scanner.match_any(target.name, scanner.PRIVATE_FILES):
        raise ValueError("目标是受保护资产：" + str(target))
    return target

def check_current(root, item):
    path = safe_target(root, item["path"])
    if item["blocked"] or item["category"] == "keep":
        raise ValueError("条目不可删除：" + str(path))
    current = scanner.snapshot(path)
    if current["blocked"] or current["protected"] or current["errors"]:
        raise ValueError("目标含受保护资产、链接或读取错误：" + str(path))
    if current["signature"] != item["signature"]:
        raise ValueError("目标在扫描后发生变化，请重新扫描确认：" + str(path))
    return path

def _backup_paths(root, path):
    path = safe_target(root, path)
    if not path.is_dir():
        yield path
        return
    def fail(exc):
        raise exc
    for current, dirs, files in os.walk(str(path), followlinks=False, onerror=fail):
        yield safe_target(root, current)
        for name in dirs + files:
            safe_target(root, os.path.join(current, name))
        for name in files:
            yield safe_target(root, os.path.join(current, name))

def backup_items(root, items, backup_dir=None):
    """所有成员成功写入、CRC 校验及状态复核后，才发布完整备份。"""
    if not items:
        return None
    root = Path(root).resolve(strict=True)
    backup_dir = Path(backup_dir).absolute() if backup_dir else root.parent / "_workspace-cleaner-backups"
    _no_links(backup_dir, allow_missing=True)
    resolved = backup_dir.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("备份目录必须位于清理根目录外")
    for item in items:
        check_current(root, item)
    backup_dir.mkdir(parents=True, exist_ok=True)
    _no_links(backup_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = backup_dir / ("%s-%s-%s.zip" % (root.name, stamp, uuid4().hex[:8]))
    partial = archive_path.with_suffix(".zip.partial")
    expected = set()
    with zipfile.ZipFile(str(partial), "x", zipfile.ZIP_DEFLATED) as archive:
        for item in items:
            for path in _backup_paths(root, item["path"]):
                name = path.relative_to(root).as_posix()
                if path.is_dir():
                    name += "/"
                archive.write(str(path), name)
                expected.add(name)
    with zipfile.ZipFile(str(partial), "r") as archive:
        if set(archive.namelist()) != expected or archive.testzip() is not None:
            raise ValueError("备份校验失败，禁止删除：" + str(partial))
    for item in items:
        check_current(root, item)
    os.replace(str(partial), str(archive_path))
    return archive_path

def remove_item(item, root):
    path = check_current(root, item)
    if path.is_dir():
        shutil.rmtree(str(path))
    else:
        path.unlink()

def _select(data, args):
    kinds = {name for name in ("cache", "logs", "reverse", "scripts") if getattr(args, name)}
    selected = [item for item in data["deletable"] if args.all or item["kind"] in kinds]
    lookup = {os.path.normcase(os.path.abspath(item["path"])): item
              for bucket in scanner.BUCKETS for item in data[bucket]}
    for relative in args.include:
        if os.path.isabs(relative):
            raise ValueError("--include 必须使用相对路径：" + relative)
        target = safe_target(data["root"], os.path.join(data["root"], relative))
        item = lookup.get(os.path.normcase(str(target)))
        if item is None:
            scoped = scanner.classify(data["root"], targets=[target])
            if scoped["errors"] or scoped["skipped"]:
                raise ValueError("选中条目不能完整扫描：" + relative)
            scoped_items = [entry for bucket in scanner.BUCKETS for entry in scoped[bucket]]
            item = next((entry for entry in scoped_items if entry["path"] == str(target)), None)
            if item is None:
                raise ValueError("此目录不能整体选中，请逐项指定其中的候选或需确认项：" + relative)
        if item["category"] == "keep" or item["blocked"]:
            raise ValueError("不能选择保留项：" + relative)
        if item["category"] == "confirm" and not args.confirm:
            raise ValueError("需确认项还须显式 --confirm：" + relative)
        selected.append(item)
    unique = {os.path.normcase(item["path"]): item for item in selected}
    selected = sorted(unique.values(), key=lambda item: item["path"])
    paths = set(unique)
    for item in selected:
        parent = Path(item["path"]).parent
        while parent != parent.parent:
            if os.path.normcase(str(parent)) in paths:
                raise ValueError("清理条目存在父子重叠")
            parent = parent.parent
    return selected

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="单个项目目录")
    for name, help_text in (("all", "全部可清理候选，不包含需确认项"),
                            ("cache", "缓存候选"), ("logs", "日志候选"),
                            ("reverse", "逆向类型候选；歧义项仍需逐项指定"),
                            ("scripts", "脚本类型候选；歧义项仍需逐项指定")):
        parser.add_argument("--" + name, action="store_true", help=help_text)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="执行实际删除")
    mode.add_argument("--dry-run", action="store_true", help="只演练（默认）")
    parser.add_argument("--include", action="append", default=[], metavar="相对路径", help="从扫描清单逐项选择，可重复")
    parser.add_argument("--confirm", action="store_true", help="仅确认 --include 明确指定的需确认项")
    parser.add_argument("--backup", action="store_true", help="删除前备份全部选中项；需确认项始终强制备份")
    parser.add_argument("--backup-dir", help="备份目录，必须在项目外")
    args = parser.parse_args(argv)
    if args.confirm and not args.include:
        parser.error("--confirm 不能批量放行，必须同时逐项 --include")
    if not (args.all or args.cache or args.logs or args.reverse or args.scripts or args.include):
        parser.error("请使用 --all、分类参数或逐项 --include")
    try:
        root = _no_links(args.root).resolve(strict=True)
        if root == root.parent or root.name.lower() in {".git", "keys"}:
            raise ValueError("不能清理磁盘根目录、Git 元数据或密钥目录")
        data = scanner.classify(root)
        selected = _select(data, args)
        print("目录：%s；模式：%s；选中 %d 项，%s" % (
            root, "实际删除" if args.apply else "演练", len(selected),
            scanner.human(sum(item["size"] for item in selected))))
        for item in selected:
            print("  %s  %s  %s" % (item["category"], os.path.relpath(item["path"], root), item["reason"]))
        if data["errors"]:
            raise ValueError("扫描存在读取错误，本次禁止删除；请先排除问题")
        if not args.apply:
            print("演练完成，未删除文件。实际执行须显式加 --apply。")
            return 0
        for item in selected:
            check_current(root, item)
        needs_backup = selected if args.backup else [item for item in selected if item["category"] == "confirm"]
        archive = backup_items(root, needs_backup, args.backup_dir)
        if archive:
            print("完整备份已校验：" + str(archive))
        for item in selected:
            check_current(root, item)
        for item in selected:
            remove_item(item, root)
            print("已删除：" + item["path"])
        print("完成：删除 %d 项。请检查项目运行状态及 git status。" % len(selected))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print("已停止：" + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
