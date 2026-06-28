# Hermes cron 重建参数 — AI Infra 每周资讯

迁移到任意 Hermes 实例时，用 `cronjob` 工具按以下参数重建（或用 `hermes` CLI）。

- **name**: `feeds-ai-infra-weekly`
- **schedule**: `0 6 * * 6`  （每周六 06:00；时区取实例本地，本机为 Asia/Hong_Kong）
- **script**: 指向仓库内 `feeds/_engine/scripts/prefetch.py` 的包装 —— 见下方 prefetch 注入方式
- **workdir**: 仓库根目录（如 `/home/ubuntu/workspace/repos/blueyi.github.io`）
- **enabled_toolsets**: `["terminal","file"]`
- **deliver**: `weixin,discord`（双通知；按目标实例已连接渠道调整）
- **prompt**: 见 `feeds/_engine/prompts/ai-infra-weekly.md` 全文

## prefetch 注入
Hermes cron 的 `script` 字段会把脚本 stdout 注入到 agent 输入。让 cron 的 script 执行：
```
python3 <repo>/feeds/_engine/scripts/prefetch.py --channel ai-infra
```
（脚本既把 raw 落盘到 data/<week>.json，又把 raw JSON 打到 stdout 作为 agent 素材。）

## 本机创建命令（参考，已在本机执行）
通过 Hermes `cronjob` 工具 action=create，字段如上。脚本放在 `~/.hermes/scripts/` 下做薄包装调用仓库内 prefetch.py（保持仓库自包含，脚本逻辑只在仓库里维护一份）。

## agent 编辑后必须执行
1. 写 curated 回 `feeds/ai-infra/data/<week>.json`
2. `python3 feeds/_engine/scripts/render_week.py --channel ai-infra --week <week>`
3. `python3 feeds/_engine/scripts/rebuild_index.py`
4. `cd <repo>; git add feeds/; git commit -m "feeds(ai-infra): <week> weekly"; git push origin master`
5. 回复含线上链接 + 亮点（推送到 weixin+discord）
