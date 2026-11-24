# Cursor Automation — 具身智能每周资讯

取代 Hermes `feeds-embodied-weekly`。

- **name**: `blueyi-feeds-embodied-weekly`
- **url**: https://cursor.com/automations/ddce12c6-e824-11f1-8a40-564e3474c41f
- **schedule**: `CRON_TZ=Asia/Hong_Kong 0 20 * * 6`（每周六 20:00）
- **repo**: `github.com/blueyi/blueyi.github.io`，分支 `master`

## 执行步骤

在仓库根目录：

1. 需要时安装 PyYAML：`python3 -c "import yaml" || python3 -m pip install --user pyyaml`
2. `python3 feeds/_engine/scripts/prefetch.py --channel embodied-ai`
3. 只编辑 `feeds/embodied-ai/data/<week>.json` 的 `curated` 段，保留 `raw` 和 `meta`。
4. `python3 feeds/_engine/scripts/publish_week.py --channel embodied-ai --week <week> --data <该 JSON 的绝对路径>`
5. 不要自己 git add / commit / push，不要直接渲染，不要开 Pull Request，不要改 git config。
6. 发布成功后执行 `git fetch origin master && git reset --hard origin/master`，避免云端工作区再提交一份重复改动。

## 编辑规则

只用 JSON 真实条目，绝不编造标题、机构、URL、score。一条只进一个方向。7 个方向都要输出，无料则 `items` 为空数组。开源大数据集、头部公司产品、关键能力突破、HN≥200、范式变化设 `hot: true`。每条：简短中文标题、1–2 句摘要，摘要末尾加层次标签，加真实 url、source、score（若 hn）。

层次标签只用：`[感知层]`、`[规划层]`、`[控制层·扩散]`、`[控制层·BC]`、`[控制层·RL]`、`[控制层·世界模型]`、`[端到端VLA]`。跨层只标最核心的一层。

方向 id 见 `feeds/_engine/domains/embodied-ai.yaml`。方向 1 收端到端 VLA 模型本身；方向 4 收感知、规划、控制和非 VLA 的扩散 / RL / 世界模型。纯基础设施（vLLM、MLIR、数据中心、HBM、量化系统）归 AI Infra，不要收进本频道。

优先看 `hf_papers` 里 upvotes ≥ 20、带 github_repo、关键词含机器人 / 具身 / VLA / manipulation 的条目。制造和产业方向没有公开材料就留空，不要为了填满而编造。

`curated.industry`：`stocks` 从 markets 抄具身相关标的，数值不得改；`funding` 只收机器人 / 具身相关事件，没有确切金额就写 null。

亮点 3–5 条，中文周度结论，优先跨层突破或层内 SOTA。同一 URL 只出现一次。不要把运行状态写进 curated。

## 最终回复

分开写 `PREFETCH`、`CURATION`、`PUBLISH`、`DEPLOY`、`DELIVERY`。微信、飞书、Discord 写 `not_attempted`。只有发布器给出 HTTP 200 才能写已上线。失败时结论是 `FAILED`。
