# Hermes cron 重建参数 — 具身智能每周资讯

- **name**: `feeds-embodied-weekly`
- **schedule**: `0 22 * * 0`  （每周日 22:00；时区取实例本地）
- **workdir**: 仓库根目录
- **enabled_toolsets**: `["terminal","file"]`
- **deliver**: `weixin,discord`
- **prompt**: 见 `feeds/_engine/prompts/embodied-ai-weekly.md` 全文
- **prefetch script**: `python3 <repo>/feeds/_engine/scripts/prefetch.py --channel embodied-ai`

## agent 编辑后必须执行
1. 写 curated 回 `feeds/embodied-ai/data/<week>.json`
2. `python3 feeds/_engine/scripts/render_week.py --channel embodied-ai --week <week>`
3. `python3 feeds/_engine/scripts/rebuild_index.py`
4. `cd <repo>; git add feeds/; git commit -m "feeds(embodied-ai): <week> weekly"; git push origin master`
5. 回复含线上链接 + 亮点（推送到 weixin+discord）
