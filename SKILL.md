---
name: workspace-cleaner-skill
description: 递归扫描项目垃圾、批量生成各项目清单，并在明确授权后安全清理缓存和日志。适用于项目瘦身、交接前检查或排查目录体积异常；扫描请求只生成报告，不执行删除。
---

# 工作区扫描与清理

先区分用户是在要求扫描，还是已经明确授权删除。扫描不附带删除、备份或 Git 操作的授权。

## 扫描

脚本仅使用 Python 3.8+ 标准库。路径用用户指定的项目目录，不依赖当前终端位置。

~~~bash
# 单项目递归扫描
python -B <skill>/scripts/scan.py <项目目录>

# 对父目录下的各一级文件夹分别递归扫描
python -B <skill>/scripts/scan.py <项目父目录> --batch --output <报告.html>

# 机器可读完整清单
python -B <skill>/scripts/scan.py <项目目录> --json --output <清单.json>
~~~

汇总可清理候选、需确认和保留项，以及读取错误、跳过的链接。按逻辑大小统计，不能把候选大小承诺为实际可释放空间。父子清理项不重复计数。

需要判断某项是否仍有用时，查阅 [分类与边界](references/classify-rules.md)。名称只能给出候选：不要因为叫 tmp、js 或 logs 就认定整个目录可删。

## 删除

先向用户展示具体相对路径、体积和用途；需确认项逐项明确授权。只授权扫描时到此结束，不追问是否删除数据库。

~~~bash
# 默认演练；此命令不会删除
python -B <skill>/scripts/clean.py <项目目录> --all

# 用户授权后，删除可清理候选
python -B <skill>/scripts/clean.py <项目目录> --cache --logs --apply

# 用户逐项授权后，仅处理明确指定的需确认项；脚本强制校验备份
python -B <skill>/scripts/clean.py <项目目录> --include dist --confirm --apply
~~~

- 不带 --apply 永不删除；--dry-run 与 --apply 互斥。
- --all 不包含需确认项；--confirm 必须同时指定 --include，不能一次放行所有数据库或配置。
- 需确认项始终先备份；--backup 可额外备份普通候选。默认备份在项目父目录的 _workspace-cleaner-backups 中，也可用 --backup-dir 指定项目外的位置。
- 任何读取、备份、CRC 校验或文件状态复核失败，立即停止，不继续删除。
- Git 元数据、keys 目录、已识别的私钥、链接和目录联接不作为删除目标。扫描后文件发生变化时重新扫描确认，不强行绕过检查。
- 不对真实项目运行删除测试。隔离回归检查：python -B <skill>/scripts/test_workflow.py。

实际清理后检查项目运行状态及 git status；按项目约定仅提交本次改动。不要用 git add -A 混入用户的其他修改，也不要用 git checkout -- . 自动丢弃现有工作。
