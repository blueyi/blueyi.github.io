# 迁到 OpenClaw（或其它 agent 框架）的等价配置

本资讯站的引擎（prefetch / render / rebuild）是纯 Python 标准库 + pyyaml，**与 agent 框架无关**。
迁移到 OpenClaw 或任何 agent，只需把「定时 + 注入素材 + LLM 编辑 + 提交」四步映射到目标框架。

## OpenClaw cron（agentTurn 模式）等价
- **schedule**: AI Infra `30 6 * * 6` 风格的 cron（OpenClaw 用 `{kind:cron, expr, tz}`）；具身 `0 22 * * 0`，tz `Asia/Hong_Kong`
- **sessionTarget**: `isolated`
- **payload.kind**: `agentTurn`
- **payload.message**: 把对应 `prompts/*.md` 全文作为 message，并在开头追加一句：
  「先在终端执行 `python3 <repo>/feeds/_engine/scripts/prefetch.py --channel <ch>` 获取本周素材，再按下述规则编辑」
  （OpenClaw 不像 Hermes 那样自动注入 script stdout，需让 agent 自己跑 prefetch）
- **delivery**: `{mode:announce, channel:<目标渠道>, to:<目标>}`；双通知则建两条或用多渠道

## 通用迁移检查清单（任何框架）
1. 目标机器 clone 本仓库，确保对 origin 有 push 权限（SSH key / token）。
2. `pip install pyyaml`（或确保 python3 能 import yaml）。
3. 确认 git 用户名/邮箱已配置（cron 提交需要）。
4. 在目标 agent 建两个定时任务，prompt 用 `prompts/`，时间/渠道按本目录 hermes-*.md。
5. 手动触发一次，确认：data/<week>.json 生成 → weeks/<week>.html 渲染 → index 重建 → push 成功 → 线上可访问。
6. 关掉旧机器/旧 agent 上的对应任务，避免重复推送。

## 关键不变量（换框架也不能破坏）
- `feeds/_engine/domains/*.yaml` 是领域单一事实源；改领域只改这里。
- `data/<week>.json` 是内容事实源；HTML 是产物，可随时由 render+rebuild 重建。
- 周编号用 ISO `YYYY-Www`，天然有序、跨年安全。
- 两频道内容严格隔离（domains 的 exclude_to_channel + 编辑规则双重保证）。
