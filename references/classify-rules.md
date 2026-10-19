# 文件分类规则表

判断一个文件/目录是不是垃圾，只问一个问题：

> **「重新生成的成本 ≈ 0 吗？」**
> - 是 → 垃圾，可删
> - 不是（要重抓、重配、重写）→ 需确认或必留

---

## 一、可删（重新生成成本 ≈ 0）

| 类别 | 特征 | 为什么能删 |
|---|---|---|
| **逆向/抓取产物** | 目录 `_probe/` `samples/` `captures/` `dump/` `js/`；文件 `*.html`（非模板）、`*_payload.json`、`*_export.json`、`nuxt_goods.json` | 抓一次就有，代码不依赖 |
| **构建缓存** | `__pycache__/`、`*.pyc`、`.pytest_cache/`、`.mypy_cache/`、`node_modules/`、`dist/`、`build/`、`.next/`、`target/`、`*.egg-info/` | 重新构建就回来了 |
| **运行产物** | `logs/`、`*.log`、`tmp/`、`temp/`、`*.tmp`、`*.out`、`*.err` | 运行时生成 |
| **一次性脚本** | `probe_*`、`compare_*`、`peek_*`、`tmp_*`、`_*.py`、`*_old.*`、`*.bak`、`*.orig`、`verify_*` | 当时调试用，任务已完成 |
| **调试数据** | `*_backup_*.db`、`data/test_*`、`*.sample` 的临时副本 | 调试快照 |

---

## 二、需确认（可能有价值）

| 特征 | 风险 | 问什么 |
|---|---|---|
| `*.db` / `*.sqlite` | 可能是业务数据、历史记录 | 「这个数据库别处有副本吗？删了历史数据就没了」 |
| `config.json` / `*.conf` / `.env*` | 含凭证、API key、密码 | 「删了要重新配置，备份一份还是直接删？」 |
| `credentials*` / `secrets*` / `*.pem` | 密钥 | 「这是线上在用的吗？」 |

**确认后要删的，必须先打包到工作区外**（`clean.py --backup` 会自动做）。

---

## 三、必留（删了要命）

| 特征 | 原因 |
|---|---|
| `.git/` | 版本历史 |
| `keys/`、`*_ed25519`、`id_rsa*`、`*.pub` | 私钥删了无法恢复 |
| `README*`、`docs/`、`*.md` | 文档沉淀 |
| `deploy/`、`*.service`、`Dockerfile`、`docker-compose.yml` | 部署能力 |
| `run*.bat`、`start*.sh` | 启动入口 |
| `requirements.txt`、`package.json`、`pyproject.toml` | 依赖清单 |
| `tests/`、`test/`、`migrations/` | 正式测试与迁移脚本 |
| 源码（`*.py`、`*.js`、`*.ts`、`*.go`…） | 产品本体 |

---

## 四、容易误判的边界情况

| 情况 | 判断 |
|---|---|
| `test_*.py` | 在 `tests/` 目录里 → **必留**（正式测试）；在根目录/`tools/` 里 → 大概率一次性 |
| `*.html` | 是模板（`templates/`、`public/`）→ 必留；是抓的样本 → 可删 |
| `data/` 目录 | 里面是 `*.db` → 需确认；里面是 `*.json` 配置 → 看内容 |
| `js/` 目录 | 前端源码目录 → 必留；下载的 chunk 堆 → 可删 |
| `*.json` | 配置文件（`package.json`、`config.json`）→ 特殊对待；抓取导出（`*_dump.json`）→ 可删 |
| `.vscode/`、`.idea/` | 编辑器配置，团队共享的留，个人的删 |
| `venv/`、`.venv/` | 环境目录，能重建但重建慢，一般删（用 requirements 重装） |

**拿不准就归「必留」**——少删一个不影响，删错一个要重来。

---

## 五、体积参考（什么算「异常臃肿」）

| 项目类型 | 正常体积 | 超过这个就要扫 |
|---|---|---|
| Python 小工具 | 几百 KB ~ 几 MB | > 20 MB |
| Node 前端项目（不含 node_modules） | 几 MB | > 50 MB |
| 爬虫项目 | 几十 KB ~ 几 MB（不含数据库） | > 100 MB |
| 任何项目 | — | 90% 体积是「可删」类别时 |

判断标准不是绝对体积，而是**「可删类别占比」**——超过 80% 就该清了。
