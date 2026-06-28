# feeds/ 资讯站引擎 + 迁移自包含包

`blueyi.github.io/feeds` 是一个**独立、自包含**的每周资讯静态站点，含两个频道：
- **AI Infra 每周资讯**（`feeds/ai-infra/`）— 每周六 06:00 自动生成
- **具身智能每周资讯**（`feeds/embodied-ai/`）— 每周日 22:00 自动生成

本方案**不依赖任何其它抓取/推送方案**。停掉旧方案后照常运行。本目录（`_engine/`）含迁移到新机器/新 agent 所需的全部信息。

---

## 1. 它是怎么工作的

```
[定时] → prefetch.py 抓最近7天 HN+arXiv（按频道 domains 关键词过滤+分流）
       → 写 <channel>/data/<YYYY-Www>.json 的 raw 段，并把 raw 打到 stdout
[agent] 读 raw → 按 prompt 规则筛选/分类/中文编辑 → 写回 data 的 curated 段
       → render_week.py 渲染 weeks/<week>.html
       → rebuild_index.py 重建频道 index + manifest + feeds 总入口
       → git add/commit/push origin master → GitHub Pages 上线
       → 推送提醒到 微信 + Discord（含线上链接 + 亮点）
```

线上地址：
- 总入口 `https://yulong.wang/feeds/`
- AI Infra `https://yulong.wang/feeds/ai-infra/`
- 具身智能 `https://yulong.wang/feeds/embodied-ai/`

## 2. 目录结构

```
feeds/
├── index.html                 # 总入口（rebuild_index.py 生成）
├── assets/feeds.css           # 共用样式（唯一改样式的地方）
├── ai-infra/  embodied-ai/    # 两个频道
│   ├── index.html             # 周报列表（生成）
│   ├── manifest.json          # 频道清单（生成，迁移用）
│   ├── weeks/<YYYY-Www>.html  # 单周页（生成）
│   └── data/<YYYY-Www>.json   # 周数据事实源（raw=抓取, curated=编辑）
└── _engine/
    ├── README.md              # 本文件
    ├── domains/<channel>.yaml # 领域定义 + 关键词 + 去重（单一事实源）
    ├── scripts/               # prefetch / render_week / rebuild_index / run_channel.sh
    ├── templates/             # 结构参考（实际渲染逻辑在 render_week.py）
    ├── prompts/               # 两频道的 agent 编辑 prompt
    └── cron/                  # Hermes / OpenClaw 重建参数
```

## 3. 依赖
- Python 3.8+，标准库 + `pyyaml`（`pip install pyyaml`）。
- git，且对 `origin`（`git@github.com:blueyi/blueyi.github.io.git`）有 push 权限。
- 无前端构建、无 Node、无 CDN。站点 `.nojekyll`，master 分支直发 GitHub Pages。

## 4. 手动跑一期（验证 / 补发）
```bash
cd <repo>/feeds/_engine/scripts
python3 prefetch.py --channel ai-infra          # 抓取，写 data raw 段 + stdout
# —— 人工或 agent 按 prompts/ai-infra-weekly.md 把 curated 写回 data/<week>.json ——
python3 render_week.py --channel ai-infra --week 2026-W27
python3 rebuild_index.py
cd <repo>; git add feeds/; git commit -m "feeds(ai-infra): 2026-W27 weekly"; git push origin master
# 本地预览：python3 -m http.server 8731 然后访问 /feeds/index.html
```

## 5. 迁移到新机器 / 新 agent（完整步骤）
1. 在目标机器 `git clone git@github.com:blueyi/blueyi.github.io.git`，配好 SSH push 权限。
2. `pip install pyyaml`；配置 git user.name/email。
3. 在目标 agent 建两个定时任务：
   - AI Infra：见 `cron/hermes-ai-infra.md`（周六 06:00，prompt 用 `prompts/ai-infra-weekly.md`）
   - 具身智能：见 `cron/hermes-embodied.md`（周日 22:00，prompt 用 `prompts/embodied-ai-weekly.md`）
   - 非 Hermes 框架见 `cron/openclaw-equivalents.md`。
4. 手动触发各一次，验证 data→html→index→push→线上可访问 全链路。
5. 关闭旧机器/旧 agent 上的对应任务，避免重复推送。

## 6. 常见维护
- **加领域 / 改关键词**：只改 `domains/<channel>.yaml`。
- **改样式**：只改 `assets/feeds.css`。
- **改页面结构**：改 `scripts/render_week.py`（templates/ 仅文档）。
- **HTML 丢了 / 想重排**：data 还在，`rebuild_index.py` + 对每周 `render_week.py` 即可全量重建。
- **arXiv 周末为空**：prefetch 已内置 arXiv API 兜底（RSS 空时按最近提交时间取），周六/周日跑也有料。
- **微信限流**：站点 push 成功即视为交付；投递渠道失败不影响站点已上线，下次自然恢复。

## 7. 两频道内容隔离（不串场）
- `domains/*.yaml` 的 `exclude_to_channel` 在抓取阶段就把跨界条目分流。
- prompt 里再加编辑规则：AI Infra 第 6 类只收「基础设施视角」的具身条目；纯算法/产业归具身频道。
- 验证：两频道周页互相不出现对方专有术语（已在首期回归通过）。
