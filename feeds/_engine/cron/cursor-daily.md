# Cursor Automation — AI Infra 日报

取代 Hermes `ai-infra-daily-news`（每天 08:00 HKT）和 `ai-infra-daily-publish`（每天 09:00 HKT）。一条任务里完成采集、编辑、发布。

- **name**: `blueyi-ai-infra-daily`
- **url**: https://cursor.com/automations/dc9d2685-e824-11f1-8a40-564e3474c41f
- **schedule**: `CRON_TZ=Asia/Hong_Kong 0 8 * * *`
- **repo**: `github.com/blueyi/blueyi.github.io`，分支 `master`
- **通知**: Cursor 运行记录。微信 / 飞书 / Discord 不在这条 Automation 上，最终回复里把 `DELIVERY` 写成 `not_attempted`。

## 执行步骤

在仓库根目录：

1. `python3 daily/_engine/prefetch_daily.py > /tmp/ai-infra-daily.json`
2. 只根据这个 JSON 写日报。把**纯正文**写到 `~/.cursor/blueyi-daily-snapshots/<date>.md`。`<date>` 用 JSON 的 `date`（Asia/Hong_Kong）。文件以 `# 📡 AI Infra 日报` 开头。不要把状态报告、cron、脚本说明写进这个文件。
3. 若 `counts.hn == counts.arxiv == counts.rss == counts.blog == counts.cn == 0`，不要发布，最终回复只写一行 `[SILENT]`。
4. 否则运行 `python3 daily/_engine/publish_daily.py`。它会校验亮点、在干净 worktree 里渲染、提交、`git push origin HEAD:master`，并核对线上页面。
5. 不要自己 `git push`，不要开 Pull Request，不要改 git config。发布器非零退出就是失败。
6. 发布成功后，云端工作区里不要再留一份未提交的日报改动。

## 编辑规则

只能使用 JSON 里真实出现的条目，不得编造 URL 或 score。8 个分类必须全部输出；某类没有条目时写「近两天无重大独立动态（背景：一句话）」。每条说明发生了什么、为何重要，并带 JSON 里的 `url`（没有则用 `hn_url`）。重大新闻加 🔥。每类 2–5 条，中英文同一事件只留信息更全的一条。全文 3500–5500 字。

分类：1 AI 芯片 · 2 AI 编译器与框架 · 3 AI 推理优化（数据中心） · 4 数据中心与基础设施 · 5 AI 安全与治理 · 6 具身智能 · 7 AI 自动算子与代码生成优化 · 8 边缘与端侧推理。

`rss` 主要进第 6 类；纯软件条目不要硬塞进具身。数据中心推理进第 3 类，手机 / PC / NPU 进第 8 类。

输出骨架：

```
# 📡 AI Infra 日报 · YYYY-MM-DD（周X）

> 覆盖窗口：<YYYY-MM-DD ~ YYYY-MM-DD> · 信息源：Hacker News / arXiv / 科技博客与产业媒体 / 中文科技媒体 / 具身媒体 RSS

## 1️⃣ AI 芯片
- **简短标题**：事件摘要与技术/产业影响。[来源](URL)

## 2️⃣ AI 编译器与框架
## 3️⃣ AI 推理优化（数据中心）
## 4️⃣ 数据中心与基础设施
## 5️⃣ AI 安全与治理
## 6️⃣ 具身智能
## 7️⃣ AI 自动算子与代码生成优化
## 8️⃣ 边缘与端侧推理

---

## 🌟 今日亮点

1. ...
```

亮点必须是 3–5 条编号结论，每条对应正文里的真实新闻。亮点之后不要再加任何列表或状态标题。

## 最终回复

分开写 `PREFETCH`、`CURATION`、`PUBLISH`、`DEPLOY`、`DELIVERY`。只有发布器打印 HTTP 200 才能写已上线。任一必需阶段失败时结论是 `FAILED`。
