#!/usr/bin/env bash
# run_channel.sh — 一键执行单频道的 prefetch（编辑步由 agent 完成，此脚本不含 LLM）。
# 用法: run_channel.sh <channel>   channel ∈ {ai-infra, embodied-ai}
# 典型在 cron 中：脚本先 prefetch 注入素材给 agent，agent 编辑 curated 后再调 render+rebuild+git。
set -euo pipefail
CH="${1:?usage: run_channel.sh <ai-infra|embodied-ai>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # feeds/_engine/scripts
REPO="$(cd "$HERE/../../.." && pwd)"                    # repo root (blueyi.github.io)
WEEK="$(python3 -c 'import datetime;y,w,_=datetime.date.today().isocalendar();print(f"{y}-W{w:02d}")')"

echo "[run_channel] channel=$CH week=$WEEK repo=$REPO"
# 1) 抓取（写 data/<week>.json 的 raw 段，并把 raw 打到 stdout 供 agent 当素材）
python3 "$HERE/prefetch.py" --channel "$CH"
# 2)（编辑步）agent 读取上面 stdout / data 文件，写回 curated 段——非本脚本职责
# 3) 渲染 + 重建索引：agent 写完 curated 后调用
#    python3 "$HERE/render_week.py" --channel "$CH" --week "$WEEK"
#    python3 "$HERE/rebuild_index.py"
# 4) 提交（命令用分号，勿用 &&）：
#    cd "$REPO"; git add feeds/ ; git commit -m "feeds($CH): $WEEK weekly"; git push origin master
echo "[run_channel] prefetch done; render/rebuild/commit 由 agent 在编辑 curated 后执行"
