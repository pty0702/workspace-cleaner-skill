---
name: workspace-cleaner-skill
description: 清理项目工作区垃圾：按规则识别逆向产物、构建缓存、临时脚本、调试数据，安全删除并保留源码/文档/配置/凭证。先扫描出「可删·需确认·必留」三张清单，不可逆的先备份，删完校验代码仍可运行。适用于项目目录臃肿、交付前瘦身、交接给他人、换电脑迁移、或 git 仓库里混进大量探测产物时。
---

# 工作区清理（workspace-cleaner-skill）

目标：把项目目录从「什么都往里扔」瘦身成「能跑 + 有文档 + 凭证齐全」的最小集合，**且不误删不可恢复的东西**。

---

## 一、什么时候用

- 项目目录体积异常（几百 MB 以上，但代码其实只有几十 KB）
- 交付/开源/交接前要瘦身
- 换电脑迁移，只想带走有用的
- git status 里混进一堆探测产物、截图、抓取的 HTML
- 用户直接说「删掉垃圾」「清理一下」

**不要用**：
- 只想删一两个文件（直接删就行）
- 目录里全是必需文件（先扫描确认，别动手）

---

## 二、核心：文件分三类

| 类别 | 典型特征 | 处理 |
|---|---|---|
| ✅ **可删** | 见下方「分类规则表」 | 直接删 |
| ⚠️ **需确认** | 数据库、配置文件、含凭证的文件、可能含历史数据的目录 | **先问用户**，删前打包备份 |
| 🔒 **必留** | 源码、文档、部署脚本、私钥、启动脚本、`.git/` | 永远不动 |

### 分类规则表

| 类别 | 匹配特征 | 说明 |
|---|---|---|
| **逆向/抓取产物** | 目录 `_probe/` `samples/` `captures/` `dump/`；文件 `*.html`（非模板）、`*_payload.json`、`*_export.json`；目录 `js/`（前端 chunk 堆） | 抓取时留下的样本，代码不依赖 |
| **构建缓存** | `__pycache__/`、`*.pyc`、`.pytest_cache/`、`node_modules/`、`dist/`、`build/`、`.next/`、`target/`、`*.egg-info/` | 删了会自动重建 |
| **运行产物** | `logs/`、`*.log`、`tmp/`、`*.tmp`、`.cache/` | 运行时生成 |
| **一次性脚本** | `probe_*` `test_*`（注意：正式测试目录要留）`compare_*` `peek_*` `tmp_*` `_*.py` `*_old.*` `*.bak` `*.orig` | 调试时临时写的 |
| **调试数据** | `*_backup_*.db`、`data/test_*`、`*.sample` 的临时副本 | 调试备份 |
| ⚠️ **需确认** | `*.db` `*.sqlite`、`config.json` `*.conf`、`.env*`、`credentials*`、`*.pem` | 可能含历史数据或凭证 |
| 🔒 **必留** | `.git/`、`README*` `docs/`、`keys/` `*_ed25519` `id_rsa*`、`deploy/`、`*.service`、`Dockerfile`、启动脚本（`run*.bat` `start*.sh`）、`requirements.txt` `package.json` `pyproject.toml` | 核心资产 |

> 判断口诀：**「重新生成的成本 ≈ 0」的就是垃圾；「丢了要重配/重抓/重写」的就得确认。**

---

## 三、操作流程（六步，别跳）

### 第 1 步：扫描

```bash
python <skill>/scripts/scan.py [项目目录]
```

输出三张清单 + 各类体积，**按体积从大到小排**，先看大头。

### 第 2 步：确认「需确认」项

把扫描结果里「需确认」的逐条念给用户：

> 发现 `data/pzds.db`（132 KB，含 198 条记录）、`config.json`（2 KB，含飞书 webhook 和密码）
> 这两个删不删？数据库别处有副本吗？

**必须等用户明确回答**，不能自己决定删。

### 第 3 步：备份不可恢复的

决定要删的「需确认」项，先打包到**工作区外**：

```
D:\projects\_backup_<项目名>_<日期>.zip
```

用 `clean.py --backup` 会自动做这一步。

### 第 4 步：删除

```bash
# 先演练（只打印，不删）
python <skill>/scripts/clean.py --dry-run --all

# 确认没问题再真删
python <skill>/scripts/clean.py --all
```

或按类别挑着删：

```bash
python <skill>/scripts/clean.py --cache --logs          # 只删缓存和日志
python <skill>/scripts/clean.py --reverse --scripts     # 只删逆向产物和一次性脚本
```

### 第 5 步：校验代码没坏

```bash
# Python 项目
python -m compileall -q <包名>
python -m pytest tests/ -q          # 有正式测试就跑

# 前端
npm run build --if-present

# 通用
git status --short                   # 看删了哪些
```

**跑不通就立刻 `git checkout -- .` 回滚**（前提是删之前已经提交过）。

### 第 6 步：提交

删除也要留痕：

```bash
git add -A
git commit -m "清理工程：删除逆向产物/缓存/一次性脚本，保留源码与文档"
git push
```

---

## 四、坑清单（实战踩出来的）

| 坑 | 后果 | 对策 |
|---|---|---|
| 删了 `keys/` 里的私钥 | 运维/部署通道的钥匙彻底没了 | 归入「绝不动」 |
| 删了 `data/*.db` 但没确认 | 历史数据丢失 | 必须问「服务器/别处有副本吗」 |
| 删了 `config.json` | 凭证要重配一遍 | 归入「需确认」，删前备份 |
| 删了 `__pycache__` 后又跑脚本 | 目录重新生成 | 正常，不用管 |
| 删完忘了 commit | git 里一堆 `D` 挂着 | 第 6 步必须做 |
| 只删小文件没删大目录 | 体积几乎没降 | 扫描时**按体积排序**，先删大头 |
| Windows 上目录被占用删不掉 | `Access is denied` | 是进程持有句柄，先关相关服务/重启；空目录无害 |
| 删了 `README` 里提到的脚本 | 文档出现死链 | 删完 grep 一遍 README，把引用改掉 |
| 一次性脚本里其实有常用工具 | 误删 | 只看名字别信，扫一遍内容判断 |

---

## 五、脚本

| 脚本 | 作用 |
|---|---|
| `scripts/scan.py` | 扫描目录，按三类输出清单 + 体积统计（`--json` 可输出机器可读格式） |
| `scripts/clean.py` | 按类别删除，支持 `--dry-run` / `--backup` / 分类选择 |

```bash
python scripts/scan.py D:\projects\my-project
python scripts/clean.py --dry-run --all
python scripts/clean.py --all --backup
```

两个脚本都是纯标准库，无第三方依赖，Windows / Linux 都能跑。

---

## 六、给模型的执行建议

1. **先扫后删**，永远不要把 `clean.py` 当第一步
2. 「需确认」的**必须真的问用户**，不要自己假设
3. 删之前先 `git status` 确认工作区干净（或先 commit），这样出问题能回滚
4. 删完**一定校验**（编译/测试），报告里给出「释放了多少、还剩多少」
5. 报告时列出**删了什么类别、保留了什么**，让用户能核对
6. 用户说「只删纯垃圾」时，只动「可删」三类，配置/数据库一律保留
