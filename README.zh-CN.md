# 抖音知识库

[English](README.md) | **简体中文**

一个可复用的 Codex Skill：将创作者公开可访问的抖音视频批量整理成本地可检索的证据库，保留语音转写、画面字幕、时间戳和原视频链接。

项目从实际批处理流程整理而来，账号、日期范围、工作目录与硬件设置均可配置。仓库只包含工具和说明，**不包含采集视频、转写内容、登录会话或模型权重**。

## 工作流程

1. **批量采集目录**：用户在独立 Chrome 配置中登录后，读取正常加载的公开作品列表，记录去重视频 ID 和分页是否完成。
2. **下载并校验媒体**：按发布日期筛选，检查视频轨和音轨；低码率视频没有声音时补下独立音频。
3. **本地语音与字幕识别**：使用 faster-whisper 识别普通话语音，RapidOCR 识别画面文字。
4. **按时间核对证据**：保留两份原文，将差异标为待复核。
5. **生成并审计知识库**：输出离线 HTML 搜索页、JSON、SQLite 全文索引，并报告缺失或空文本结果。

发布版流水线先下载、再识别，处理进程数量可配置。重试次数有限，重新运行可复用兼容的已完成结果。

## 环境要求

- 参考环境：**Windows + Python 3.12**。其他平台尚未完成端到端验证。
- 目录采集需要 Node.js/npm 和 Google Chrome。
- 安装依赖、下载模型和授权范围内的媒体需要网络；预留足够磁盘空间。
- 默认 CPU；GPU 加速可选，需要在本机配置并验证兼容运行环境。

安装依赖不等于模型就绪。权重下载、离线加载和真实样本推理应分别验证。

## 快速开始

在 PowerShell 中执行，将示例主页和日期换成自己的范围。任务目录必须是新目录或空目录，示例将其创建在源码仓库之外。

```powershell
git clone https://github.com/StarrYMSkY/douyin-knowledgebase.git
cd douyin-knowledgebase

$skillPath = (Resolve-Path .\skills\douyin-video-knowledge).Path
$jobPath = Join-Path (Split-Path (Get-Location).Path -Parent) "douyin-job"

python "$skillPath\scripts\initialize.py" `
  --workspace "$jobPath" `
  --profile "https://www.douyin.com/user/REPLACE_WITH_CREATOR_ID" `
  --since 2024-08-29 --until 2026-10-18 `
  --title "公开视频言论证据库"

Set-Location "$jobPath"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install

node collect-browser.cjs
.\.venv\Scripts\python.exe prepare_models.py --model small
.\.venv\Scripts\python.exe -X utf8 -u finish_pipeline.py
```

在专用 Chrome 窗口中自行登录并完成验证。采集器使用浏览器正常加载的公开作品数据，不导出 Cookie。若访问受阻或分页不完整，先解决原因；不完整的目录不会被视为全部作品。

**日期为北京时间 Asia/Shanghai 下的 `[since, until)` 区间：包含开始日，不包含结束日。** 若要排除 8 月 28 日全天，使用 `--since 2024-08-29`。每次快照都应明确结束日期。

批量运行前先在独立测试目录验证一条视频，检查音频、普通话转写、字幕位置和时间对齐。默认单进程 CPU、全画面 OCR；样本验证后再调整裁剪或 GPU 配置。

## 作为 Skill 使用

将整个 `skills/douyin-video-knowledge` 文件夹放入自己的 Codex skills 目录，然后调用：

```text
使用 $douyin-video-knowledge，按指定账号和日期范围
批量采集公开视频，并建立本地证据知识库。
```

[Skill 入口](skills/douyin-video-knowledge/SKILL.md)和[详细运行说明](skills/douyin-video-knowledge/references/operation.md)包含范围核查、模型验证、可选 GPU 配置、恢复方法和审核标准。

## 仓库结构

```text
skills/douyin-video-knowledge/
├── SKILL.md                 # Agent 指令与边界
├── agents/openai.yaml       # Skill 发现信息
├── scripts/
│   ├── initialize.py        # 创建独立任务目录
│   └── test_runtime.py      # 离线回归测试
├── assets/runtime/          # 采集与处理脚本
└── references/operation.md  # 详细运行与排障说明
```

## 输出与进度

| 任务目录中的路径 | 用途 |
| --- | --- |
| `capture/posts.json`、`capture/status.json` | 作品目录、发布时间、分页完整性 |
| `manifest.jsonl` | 已下载且音轨校验通过的处理输入 |
| `knowledge/<video-id>/` | 来源、语音转写、字幕 OCR 与对照 JSON |
| `knowledge/index.html` | 离线关键词搜索与时间戳对照 |
| `knowledge/index.json`、`knowledge/knowledge.sqlite` | 结构化文档与全文索引 |
| `knowledge/job-status.json`、`knowledge/progress-*.json` | 整体与各进程进度 |
| `knowledge/audit.json`、`logs/` | 最终覆盖审计与运行日志 |

本地打开 `knowledge/index.html`，随处理进度刷新即可。最终审计通过才算完成，不能将下载完成当作全流程完成。中断后在同一目录重跑可复用兼容结果；更换创作者或显著改变配置时应新建任务目录。

## 准确性、隐私与限制

- **机器一致不等于人工确认。** `automatic_agreement` 仅指归一化文本一致；`needs_review` 可能来自识别错误、OCR 缺失或时间边界差异。两者都不是经过校准的准确率。
- 区分作者观点、引述、预测、案例和整理者概括。保留来源链接与时间范围；引用前检查人名、数字、单位、否定词和上下文。
- 完整性只对应采集时公开可访问的快照。已删除、私密、受限或后来发布的视频不保证包含。
- 抽帧和裁剪可能漏掉短暂或换位置的字幕。语音识别面向普通话；默认主题是财经/房产关键词示例，不是语义分类模型。
- 仅处理你有权访问和使用的内容。不提供登录、验证码、私密权限或其他访问控制绕过手段。
- 浏览器配置、Cookie、签名媒体 URL、视频、转写、模型权重和日志不应纳入源码版本管理。任务目录含敏感会话数据，应保留在本地。
- 网站行为与依赖兼容性可能变化。离线测试不验证抖音实时访问、模型下载、GPU 驱动或所有目标机器。

## 验证

在仓库根目录执行：

```powershell
python -X utf8 skills/douyin-video-knowledge/scripts/test_runtime.py
```

五项离线测试覆盖初始化与防覆盖、日期筛选、文本对照、覆盖审计与索引生成、Python 源码编译。测试使用临时数据，不连接抖音，也不下载模型。

## 开源致谢

感谢以下开源项目的维护者与贡献者。本流程使用或曾评估这些项目：

| 项目 | 在本流程中的作用 |
| --- | --- |
| [F2 — Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) | 原始抖音采集任务中安装并评估过。F2 不是本发布版的运行依赖；当前采集脚本采用用户登录浏览器正常加载的页面请求。 |
| [Playwright — Microsoft](https://github.com/microsoft/playwright) | 浏览器自动化与公开作品目录采集。 |
| [faster-whisper — SYSTRAN](https://github.com/SYSTRAN/faster-whisper) | 本地语音转写。 |
| [RapidOCR — RapidAI](https://github.com/RapidAI/RapidOCR) | 画面字幕与文字识别。 |
| [PyAV](https://github.com/PyAV-Org/PyAV) | 音视频流校验与视频帧解码。 |
| [ONNX Runtime — Microsoft](https://github.com/microsoft/onnxruntime) | OCR 推理运行时，并提供可选的硬件加速。 |

语音模型另行从 [SYSTRAN 的 faster-whisper 模型仓库](https://huggingface.co/Systran/faster-whisper-small)下载。上游库与模型的贡献归各自作者所有；本项目提供工作流整理与集成脚本，不代表获得上游项目背书或存在隶属关系。

依赖与模型权重保留各自许可证及使用条款，使用或再分发前请查看上游仓库。本仓库不重新分发第三方源码、模型权重或创作者媒体。
