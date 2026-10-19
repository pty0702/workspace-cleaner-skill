# workspace-cleaner-skill

清理项目工作区垃圾的 **Agent Skill**：按规则识别逆向产物、构建缓存、临时脚本、调试数据，安全删除并保留源码/文档/配置/凭证。

## 它解决什么

项目目录几百 MB，其实代码只有几十 KB——剩下全是抓取的 HTML、下载的 chunk、调试脚本、日志、缓存。

直接删怕删错，不删又占地方、git 里还混一堆垃圾。

这个 skill 给出一套**可执行的清理流程**：

1. **扫描** → 输出「可删 / 需确认 / 必留」三张清单 + 体积统计
2. **确认** → 数据库、配置、凭证类逐条问人（不擅自删）
3. **备份** → 决定删的不可逆项先打包到工作区外
4. **删除** → 按类别批量删，可先 `--dry-run` 演练
5. **校验** → 编译/测试/`git status`，确认代码没坏
6. **提交** → 删除也要留痕

## 核心判据

> **「重新生成的成本 ≈ 0 吗？」**
>
> - 是（缓存、抓取样本、日志、一次性脚本）→ 直接删
> - 不是（数据库、配置文件、私钥）→ **需确认**或**必留**

## 安装

```bash
mkdir -p ~/.agents/skills
cp -r . ~/.agents/skills/workspace-cleaner-skill
```

Windows：

```powershell
Copy-Item -Recurse . "$env:USERPROFILE\.agents\skills\workspace-cleaner-skill"
```

装好后，直接跟模型说：

> 用 workspace-cleaner-skill 清一下这个项目的垃圾

## 手动使用脚本

脚本是纯标准库，无第三方依赖，Windows / Linux 都能跑。

```bash
# 1. 扫描（先看清单，别急着删）
python scripts/scan.py D:\projects\my-project

# 2. 演练（只打印，不删）
python scripts/clean.py D:\projects\my-project --dry-run --all

# 3. 真删（自动把「需确认」项备份到工作区外）
python scripts/clean.py D:\projects\my-project --all --backup

# 4. 只删某几类
python scripts/clean.py . --cache --logs
python scripts/clean.py . --reverse --scripts

# 5. 连数据库/配置一起删（危险，必须显式加 --confirm）
python scripts/clean.py . --all --confirm --backup
```

## 文件分类规则（摘要）

| 类别 | 特征 | 处理 |
|---|---|---|
| 逆向/抓取产物 | `_probe/` `samples/` `js/` `*.html` 样本 `*_dump.json` | 删 |
| 构建缓存 | `__pycache__/` `node_modules/` `dist/` `*.pyc` | 删 |
| 运行产物 | `logs/` `*.log` `tmp/` | 删 |
| 一次性脚本 | `probe_*` `compare_*` `peek_*` `_*.py` `*.bak` | 删 |
| ⚠️ 需确认 | `*.db` `config.json` `.env` `*credentials*` | 先问人 |
| 🔒 必留 | `.git/` `keys/` `README*` `deploy/` `*.service` 源码 | 永不动 |

完整规则和易误判边界见 [references/classify-rules.md](references/classify-rules.md)。

## 目录结构

```
workspace-cleaner-skill/
├─ SKILL.md                    流程手册（分类规则 + 六步操作 + 9 个坑）
├─ scripts/
│  ├─ scan.py                  扫描分类与体积
│  └─ clean.py                 执行清理（dry-run / backup / 分类选择）
└─ references/
   └─ classify-rules.md        分类规则表 + 边界判断
```

## 许可

MIT
