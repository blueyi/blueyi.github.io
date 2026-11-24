# Cursor Automation — AI Infra 每周资讯

取代 Hermes `feeds-ai-infra-weekly`。

- **name**: `blueyi-feeds-ai-infra-weekly`
- **url**: https://cursor.com/automations/dd381097-e824-11f1-8a40-564e3474c41f
- **schedule**: `CRON_TZ=Asia/Hong_Kong 0 6 * * 6`（每周六 06:00）
- **repo**: `github.com/blueyi/blueyi.github.io`，分支 `master`

## 执行步骤

在仓库根目录：

1. 需要时安装 PyYAML：`python3 -c "import yaml" || python3 -m pip install --user pyyaml`
2. `python3 feeds/_engine/scripts/prefetch.py --channel ai-infra`
   它把本周 raw 写入 `feeds/ai-infra/data/<YYYY-Www>.json`，并保留已有 curated。
3. 只编辑该 JSON 的 `curated` 段，保留 `raw` 和 `meta`。
4. `python3 feeds/_engine/scripts/publish_week.py --channel ai-infra --week <week> --data <该 JSON 的绝对路径>`
   发布器在锁内从 `origin/master` 建干净 worktree、校验、渲染、提交、推送，并检查线上 HTTP 200。
5. 不要自己 git add / commit / push，不要调用 `render_week.py` 或 `rebuild_index.py`，不要开 Pull Request，不要改 git config。
6. 发布成功后丢掉云端工作区里的本地改动，避免再开一次重复提交。`git fetch origin master && git reset --hard origin/master` 即可。

## 编辑规则

只用 JSON 真实条目，绝不编造标题、URL、score、融资金额、股价。domains 标签只是粗筛，按内容重新归类，一条只进一个领域。8 个技术领域都要处理，无料则 `items` 为空数组。重大新闻（拐点 / 首发 / 政策 / 大额资金 / HN≥200）设 `hot: true`。每条：简短中文标题、1–2 句中文摘要、真实 url、source（hn/arxiv/rss/cn_rss）、score（若 hn）。每领域 2–5 条。中英文同一事件只留一条。

领域 id 见 `feeds/_engine/domains/ai-infra.yaml`：chips、compilers、inference-dc、datacenter、safety、embodied-infra、autokernel、edge。纯 VLA / 灵巧操作 / sim2real / 世界模型 / 人形产业归具身频道；本频道第 6 类只收机器人算力、部署、推理系统。

`curated.industry`：

- `stocks`：从 markets 挑 6–10 只，price/pct/currency 原样抄录。
- `cn_stocks`：从 cn_markets 原样抄录。华为昇腾、壁仞、摩尔线程、燧原等未上市公司不要放进股票表。
- `funding`：2–6 条与 AI Infra 相关的融资或重大产业动态。没有金额就写 null，不要编造。泛消费、生物、气候融资剔除。
- markets 与 cn_markets 都失败且没有相关融资时可以省略 industry。

亮点 3–5 条，必须是中文周度结论，每条对应本期正文。同一 URL 只出现一次。不要把 PREFETCH / CURATION / PUBLISH / DEPLOY / DELIVERY 写进 curated。

## 最终回复

分开写 `PREFETCH`、`CURATION`、`PUBLISH`、`DEPLOY`、`DELIVERY`。微信、飞书、Discord 写 `not_attempted`。只有发布器给出 HTTP 200 才能写已上线。失败时结论是 `FAILED`。
