# workspace-cleaner-skill

用 Python 标准库递归扫描项目垃圾，支持逐项目批量报告；明确授权后再删除。兼容 Python 3.8+、Windows 和 Linux。

## 安装到 Codex

将 SKILL.md、scripts/、references/ 放到 ~/.codex/skills/workspace-cleaner-skill/。其他支持标准 SKILL.md 的 Agent 可按其技能目录约定安装。

使用时直接说：

> 用 workspace-cleaner-skill 扫描项目垃圾

## 扫描与报告

~~~bash
# 单项目，默认递归扫描
python -B scripts/scan.py D:\projects\my-project

# 逐项目扫描父目录下的每个一级文件夹
python -B scripts/scan.py D:\projects --batch --output report.html

# JSON 完整清单；--top 仅影响终端显示，不截断报告
python -B scripts/scan.py --top 20 D:\projects\my-project --json --output report.json
~~~

输出三类清单：可清理候选、需确认、保留。HTML 报告包含逐项目汇总和可展开明细；JSON 还包含错误、跳过入口及元数据指纹。

按文件逻辑大小统计，不跟随符号链接或 Windows 目录联接，排除各级 .git。读取失败会记录并返回非零状态，不能把失败项当成零字节垃圾；批量扫描会继续报告其他项目。硬链接、压缩、稀疏文件及进程占用可能影响实际释放空间。

Windows 的 nul、con、COM1 等保留设备名跳过并报告，不作为普通文件访问或删除。

## 清理

~~~bash
# 默认仅演练
python -B scripts/clean.py D:\projects\my-project --all

# 显式授权后删除缓存和日志候选
python -B scripts/clean.py D:\projects\my-project --cache --logs --apply

# 仅选中用户逐项确认的条目，自动先备份并校验
python -B scripts/clean.py D:\projects\my-project --include dist --confirm --apply

# --include 可重复；--backup 额外备份普通候选
python -B scripts/clean.py D:\projects\my-project --include debug.log --backup --apply
~~~

相较旧版，去掉 --dry-run 不再触发删除：必须显式 --apply。--confirm 不再放行全部需确认项，必须同时逐项 --include。--all 仍只选普通候选。--reverse、--scripts 保留类别接口，但样本和脚本通常需要逐项确认。

--include 可精确到折叠目录内的单个文件，例如 dist/old-report.html；此时按项目原上下文重新分类该文件，不会连同整个 dist 删除。

备份默认写到项目父目录的 _workspace-cleaner-backups，或使用 --backup-dir 指定项目外目录。只有完整写入、CRC 校验及源文件状态复核均成功，才发布 .zip 并继续删除；失败留下的 .partial 不视作完整备份。删除前再次检查路径边界、保护项和文件变化。

不会自动删除 Git 元数据、keys、已识别的私钥或链接。含这些资产、链接或读取错误的候选目录禁止整体删除。数据库、配置、构建交付产物、虚拟环境、浏览器数据和有歧义的源码/样本默认保留待确认。

完整分类见 [references/classify-rules.md](references/classify-rules.md)。

## 检查

~~~bash
python -B scripts/test_workflow.py
~~~

仅在仓库 .git/test-workflow 内创建隔离样本，覆盖递归统计、默认演练、显式选择、备份失败、文件变化和路径越界；Windows 还检查目录联接。测试不操作真实项目。可通过 WORKSPACE_CLEANER_TEST_DIR 指定隔离位置。

删除操作无法提供整个目录树的事务回滚；遇到变化或错误会停止剩余操作。实际清理后检查项目及 Git 状态，只提交本次改动。

## 许可

MIT
