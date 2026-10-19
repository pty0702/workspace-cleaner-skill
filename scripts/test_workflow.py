#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔离回归检查：python scripts/test_workflow.py；不访问真实项目。"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import clean
import scan

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.environ.get("WORKSPACE_CLEANER_TEST_DIR",
                         str(Path(__file__).resolve().parent.parent / ".git" / "test-workflow"))).resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.fixture = Path(tempfile.mkdtemp(prefix="case-", dir=str(self.base))).resolve()
        self.assertEqual(self.fixture.parent, self.base)
        self.root = self.fixture / "project"
        self.root.mkdir()
        self.external = self.fixture / "external"
        self.external.mkdir()

    def tearDown(self):
        target = self.fixture.resolve()
        if target.parent != self.base or not target.name.startswith("case-"):
            raise RuntimeError("测试清理目标越界")
        shutil.rmtree(str(target))

    def put(self, name, content="fixture"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_clean(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return clean.main([str(self.root)] + list(args))

    def assert_not_candidate(self, report, relative):
        target = str(self.root / relative)
        self.assertFalse(any(target == item["path"] or target.startswith(item["path"] + os.sep)
                             for item in report["deletable"]), relative)

    def test_recursive_classification_and_partition(self):
        self.put("src/pkg/__init__.py")
        self.put("src/pkg/__main__.py")
        self.put("src/pkg/__pycache__/module.pyc")
        self.put("tmp/business.fdb")
        self.put("tmp/.env", "test=1")
        self.put("profile/Default/IndexedDB/example.leveldb/000001.log")
        self.put("smali_classes3/com/example/temp/Entry.smali")
        self.put("node_modules/pkg/index.js")
        self.put("dist-app/node_modules/pkg/index.js")
        self.put("_probe.py")
        self.put("README.md")
        report = scan.classify(self.root)
        for name in ("src/pkg/__init__.py", "src/pkg/__main__.py", "tmp/business.fdb",
                     "profile/Default/IndexedDB/example.leveldb/000001.log",
                     "smali_classes3/com/example/temp/Entry.smali",
                     "dist-app/node_modules/pkg/index.js", "_probe.py"):
            self.assert_not_candidate(report, name)
        self.assertTrue(any(item["path"].endswith("__pycache__") for item in report["deletable"]))
        self.assertTrue(any(item["path"] == str(self.root / "node_modules") for item in report["deletable"]))
        expected = sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())
        self.assertEqual(report["summary"]["size"], expected)
        self.assertEqual(sum(report["summary"][bucket] for bucket in scan.BUCKETS), expected)
        paths = [Path(item["path"]) for bucket in ("deletable", "confirm") for item in report[bucket]]
        self.assertEqual(len(paths), len(set(paths)))
        for path in paths:
            self.assertFalse(any(parent in paths for parent in path.parents))

    def test_nested_git_and_keys_cannot_be_removed_as_tmp(self):
        self.put("tmp/nested/.git/config")
        self.put("logs/keys/id_ed25519")
        report = scan.classify(self.root)
        self.assert_not_candidate(report, "tmp/nested/.git/config")
        self.assert_not_candidate(report, "logs/keys/id_ed25519")
        self.assertEqual(self.run_clean("--all", "--apply"), 0)
        self.assertTrue((self.root / "tmp/nested/.git/config").exists())
        self.assertTrue((self.root / "logs/keys/id_ed25519").exists())

    def test_default_is_dry_run(self):
        path = self.put("logs/runtime.log")
        self.assertEqual(self.run_clean("--all"), 0)
        self.assertTrue(path.exists())

    def test_apply_only_removes_candidates(self):
        cache = self.put("src/__pycache__/module.pyc")
        source = self.put("src/__init__.py")
        database = self.put("business.db")
        self.assertEqual(self.run_clean("--cache", "--apply"), 0)
        self.assertFalse(cache.exists())
        self.assertTrue(source.exists())
        self.assertTrue(database.exists())

    def test_confirm_requires_explicit_selection(self):
        path = self.put("business.db")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_clean("--all", "--confirm", "--apply")
        self.assertTrue(path.exists())

    def test_only_selected_confirm_item_is_backed_up_and_deleted(self):
        first = self.put("first.db", "first")
        second = self.put("second.db", "second")
        self.assertEqual(self.run_clean("--include", "first.db", "--confirm", "--apply"), 0)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        archives = list((self.fixture / "_workspace-cleaner-backups").glob("*.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(str(archives[0])) as archive:
            self.assertEqual(archive.namelist(), ["first.db"])
            self.assertEqual(archive.read("first.db"), b"first")
            self.assertIsNone(archive.testzip())

    def test_backup_write_failure_prevents_all_deletions(self):
        cache = self.put("logs/runtime.log")
        database = self.put("business.db")
        with mock.patch.object(zipfile.ZipFile, "write", side_effect=OSError("模拟读取失败")):
            result = self.run_clean("--all", "--include", "business.db", "--confirm", "--apply")
        self.assertEqual(result, 2)
        self.assertTrue(cache.exists())
        self.assertTrue(database.exists())

    def test_select_nested_confirm_item_without_selecting_parent(self):
        first = self.put("dist/old-report.html", "old")
        second = self.put("dist/current-report.html", "current")
        self.assertEqual(self.run_clean("--include", "dist/old-report.html", "--confirm", "--apply"), 0)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        archives = list((self.fixture / "_workspace-cleaner-backups").glob("*.zip"))
        with zipfile.ZipFile(str(archives[0])) as archive:
            self.assertEqual(archive.namelist(), ["dist/old-report.html"])
            self.assertEqual(archive.read("dist/old-report.html"), b"old")

    def test_backup_crc_failure_prevents_deletion(self):
        database = self.put("business.db")
        with mock.patch.object(zipfile.ZipFile, "testzip", return_value="business.db"):
            result = self.run_clean("--include", "business.db", "--confirm", "--apply")
        self.assertEqual(result, 2)
        self.assertTrue(database.exists())

    def test_backup_inside_project_is_rejected(self):
        database = self.put("business.db")
        self.assertEqual(self.run_clean("--include", "business.db", "--confirm", "--apply",
                                       "--backup-dir", str(self.root / "backup")), 2)
        self.assertTrue(database.exists())

    def test_boundaries_and_keep_items(self):
        self.put("README.md")
        outside = self.external / "outside.db"
        outside.write_text("outside", encoding="utf-8")
        for path in (self.root, self.external, outside):
            with self.assertRaises(ValueError):
                clean.safe_target(self.root, path)
        self.assertEqual(self.run_clean("--include", "../external/outside.db", "--confirm", "--apply"), 2)
        self.assertEqual(self.run_clean("--include", "README.md", "--confirm", "--apply"), 2)
        self.assertTrue(outside.exists())

    def test_changes_after_scan_are_rejected(self):
        path = self.put("runtime.log", "before")
        item = scan.classify(self.root)["deletable"][0]
        path.write_text("after with new data", encoding="utf-8")
        with self.assertRaises(ValueError):
            clean.remove_item(item, self.root)
        self.assertTrue(path.exists())

    def test_unreadable_file_is_reported_and_blocks_apply(self):
        unreadable = self.put("blocked.txt")
        cache = self.put("runtime.log")
        real_lstat = os.lstat
        def deny(path, *args, **kwargs):
            if os.path.abspath(os.fspath(path)) == str(unreadable):
                raise PermissionError("模拟拒绝读取")
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(os, "lstat", side_effect=deny):
            report = scan.classify(self.root)
            result = self.run_clean("--all", "--apply")
        self.assertTrue(report["errors"])
        self.assertEqual(result, 2)
        self.assertTrue(cache.exists())

    def test_symlink_does_not_escape(self):
        outside = self.external / "outside.log"
        outside.write_text("keep", encoding="utf-8")
        link = self.root / "logs"
        try:
            os.symlink(str(self.external), str(link), target_is_directory=True)
        except OSError:
            self.skipTest("当前环境不允许创建符号链接")
        report = scan.classify(self.root)
        self.assertTrue(report["skipped"])
        with self.assertRaises(ValueError):
            clean.safe_target(self.root, link / "outside.log")
        self.assertEqual(self.run_clean("--all", "--apply"), 0)
        self.assertTrue(outside.exists())

    @unittest.skipUnless(os.name == "nt", "仅 Windows 存在目录联接")
    def test_windows_junction_does_not_escape(self):
        pwsh = os.environ.get("WORKSPACE_CLEANER_PWSH") or shutil.which("pwsh")
        if not pwsh:
            self.skipTest("未找到 PowerShell 7")
        outside = self.external / "outside.log"
        outside.write_text("keep", encoding="utf-8")
        link = self.root / "logs"
        env = dict(os.environ, WORKSPACE_CLEANER_TEST_LINK=str(link),
                   WORKSPACE_CLEANER_TEST_TARGET=str(self.external))
        result = subprocess.run([pwsh, "-NoProfile", "-Command",
            "New-Item -ItemType Junction -Path $env:WORKSPACE_CLEANER_TEST_LINK -Target $env:WORKSPACE_CLEANER_TEST_TARGET | Out-Null"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertTrue(scan.classify(self.root)["skipped"])
        data = {"projects": [], "skipped": [{"path": str(link), "reason": "目录联接"}]}
        report_path = self.fixture / "link-report.html"
        scan.write_report(data, report_path)
        self.assertIn(str(link), report_path.read_text(encoding="utf-8"))
        self.assertEqual(self.run_clean("--all", "--apply"), 0)
        self.assertTrue(outside.exists())

    def test_argparse_batch_and_html_json_reports(self):
        self.put("frontend/node_modules/pkg/index.js")
        self.put("a&b.html")
        self.put("frontend/__init__.py")
        output = self.fixture / "report.html"
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(io.StringIO()):
            result = scan.main(["--top", "2", str(self.fixture), "--batch", "--json", "--output", str(output)])
        self.assertEqual(result, 0)
        data = json.loads(stream.getvalue())
        self.assertEqual(len(data["projects"]), 2)
        self.assertIn("a&amp;b.html", output.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["size"], sum(p["summary"]["size"] for p in data["projects"]))
        json_output = self.fixture / "report.json"
        scan.write_report(data, json_output)
        self.assertEqual(json.loads(json_output.read_text(encoding="utf-8")), data)

    def test_batch_continues_after_project_error(self):
        self.put("runtime.log")
        real_classify = scan.classify
        def fail_one(path, progress=None):
            if os.path.abspath(path) == str(self.external):
                raise PermissionError("模拟项目不可读")
            return real_classify(path, progress)
        stream = io.StringIO()
        with mock.patch.object(scan, "classify", side_effect=fail_one), contextlib.redirect_stdout(stream), contextlib.redirect_stderr(io.StringIO()):
            result = scan.main([str(self.fixture), "--batch", "--json"])
        data = json.loads(stream.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(len(data["projects"]), 2)
        self.assertTrue(any(project["errors"] for project in data["projects"]))
        self.assertTrue(any(project["deletable"] for project in data["projects"]))

    def test_explicit_source_root_protects_package_namespace(self):
        self.put("src/temp/module.py")
        report = scan.classify(self.root / "src")
        self.assertEqual(report["deletable"], [])

    @unittest.skipUnless(os.name == "nt", "仅 Windows 存在保留设备名")
    def test_reserved_device_name_is_skipped_without_aborting_project(self):
        self.put("runtime.log")
        real_entries = scan._entries
        def with_device(state, path):
            result = real_entries(state, path)
            if str(path) == str(self.root):
                result.append(SimpleNamespace(path=str(self.root / "nul"), name="nul"))
            return result
        with mock.patch.object(scan, "_entries", side_effect=with_device):
            report = scan.classify(self.root)
        self.assertFalse(report["errors"])
        self.assertEqual(len(report["deletable"]), 1)
        self.assertTrue(any("设备名" in item["reason"] for item in report["skipped"]))
        for name in ("nul", "NUL.txt", "COM1", "con"):
            with self.assertRaises(ValueError):
                clean.safe_target(self.root, self.root / name)

if __name__ == "__main__":
    unittest.main(verbosity=2)
