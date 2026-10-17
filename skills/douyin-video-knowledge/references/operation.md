# 安装、执行与排障

## 隔离工作目录

以下命令中的占位值必须替换为用户指定值。日期区间为北京时间 `[since, until)`。重新采集其他账号使用新目录，避免旧目录中的 ID、模型配置或索引污染新任务。

```powershell
python <skill目录>/scripts/initialize.py --workspace <新空目录> --profile <抖音主页URL> --since 2024-08-29 --until 2026-10-18 --title <知识库名称>
cd <新空目录>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
```

Windows 需安装 Chrome；浏览器采集脚本使用 `channel: chrome`。Python 3.12 + PyAV 16.1.0 是原流程验证组合，升级应重新做单条样本验证。固定版本旨在重现实验，不代表永久安全推荐；安装时检查官方公告与兼容性。

## 目录与素材

```powershell
node collect-browser.cjs
```

在新打开的专用 Chrome 中登录并处理验证码。脚本只收集目录；不会把未经音轨校验的下载计为完成。20 分钟上限和无新作品超时会退出并保留快照；退出码 2 或 `capture/status.json` 中 `catalog_complete=false` 时需解决原因后重跑。重跑会重新遍历目录，但保留已有媒体文件。页面/API 变化可能导致失败，不应宣称越过这些障碍取得完整数据。

通过 `capture/posts.json` 的 ID、时间、分页结束状态与主页总数交叉检查；目录总数与所选日期范围的总数是不同指标。全部公开作品也只代表抓取时刻仍公开且账号有权查看的快照。

## 模型与小样本

```powershell
.\.venv\Scripts\python.exe prepare_models.py --model small
```

默认下载来自 Systran/faster-whisper-small，OCR 使用 RapidOCR 随包模型。不要把 `model.bin` 存在或包安装成功等同于模型可用：`models/verification.json` 的 `local_load_verified=true` 证明完成 CPU 离线加载检查，还需真实音频验证。

下载截断时可用 `fetch_verified.py model Systran/faster-whisper-small` 获取官方元数据里的 SHA-256 并断点续传。该工具只补 model.bin；其余配置、词表仍由 prepare_models 获取。重试有上限，不关闭 TLS 验证，不使用不明镜像。

先运行 `download_catalog.py` 获得已验证的 manifest，再在独立测试目录复制一条 manifest 和媒体，运行 `pipeline.py <单条manifest>` 检查结果。样本测试也会写知识库，应与正式工作目录隔离，避免覆盖正式结果。默认 CPU 单进程最稳妥。

## GPU 可选项

初始化参数支持 `--device cuda --ocr-device dml --workers 3 --crop-top 0.5`，但不要在资源未知时照抄。

- 原任务在 RTX 4070 Ti SUPER 16GB 上验证了三进程 CUDA Whisper + DirectML OCR；不代表其他机器拥有足够显存。
- CUDA ASR 还需 CTranslate2 所需的 CUDA/cuDNN 动态库。先用真实音频验证。
- Windows DirectML：在隔离环境卸载 CPU `onnxruntime` 后安装 `onnxruntime-directml==1.24.4`，不要并存多个提供同名模块的 runtime。确认 provider 包含 `DmlExecutionProvider`。
- CPU OCR 默认兼容；CUDA OCR 需要匹配 ONNX Runtime CUDA 版本与驱动，不提供盲目自动安装。
- 字幕不在下半屏时保留 `crop_top=0`；抽帧可能漏掉短暂内容。原流程固定识别宽度 960 提升速度，但准确性必须样本评估。

## 有限批处理与续跑

```powershell
.\.venv\Scripts\python.exe -X utf8 -u finish_pipeline.py
```

发布包按“先下载、后识别”分阶段运行，以减少清单并发更新的竞态；识别阶段仍可多进程。本地原任务的边下载边处理不受影响。

下载最多三轮；缺失处理最多补跑一次。`Ctrl+C` 停止自有处理子进程并保留输出。退出后重跑同一命令会复用已验证素材以及同配置结果。改变日期、账号或模型时优先新建目录；不要混合旧结果冒充新配置完成。

观察 `knowledge/job-status.json`、`progress-*.json`、`failures-*.json` 与 `logs/`。运行状态文件更新时间不一定每段刷新；结合各 worker 进度判断，不因单个时间戳静止就宣称卡死。

## 输出与验收边界

每个视频保留 source/asr/ocr/comparison 四份 JSON，source 含原链接、发布时间、媒体 SHA-256、模型和 OCR 参数。SQLite 含 evidence 与 trigram FTS 表；HTML 支持离线关键词检索。最终 `audit.json` 核对目标 ID、媒体完整性与四份输出，空转写或空 OCR 标为待处理而非自动成功。

`automatic_agreement` 仅代表归一化后文本一致，`needs_review` 包含语音误识、OCR 漏字、时间边界差异等多种原因。不能把相似度当准确率，也不能自动用一方覆盖另一方。数字、单位、专名、否定和引述需结合原始音画人工核验。

主题默认按房产/财经关键词分类，仅为原任务的可调整示例，其他主题应修改 `build_index.py` 的 TOPICS。整理的观点不是投资建议或事实认证。精确引文与摘要分开；摘要记录人物、主题、观点类型、来源、起止时间、审核方法及必要限制条件。

## 开源组件来源

- 浏览器自动化：[Microsoft Playwright](https://github.com/microsoft/playwright)
- 本地转写：[SYSTRAN faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- 字幕 OCR：[RapidAI RapidOCR](https://github.com/RapidAI/RapidOCR)
- 音视频解码：[PyAV](https://github.com/PyAV-Org/PyAV)
- 原流程评估过 [F2](https://github.com/Johnserf-Seed/f2)，但实际目录来自用户登录的正常页面请求。F2 非运行依赖，不将“尝试过”写成“已成功接入”。

组件按自身许可证安装；本仓库不重新分发第三方源码、模型或视频。站点接口与浏览器结构可能变化；使用时再检查官方来源，不把历史验证当成长期保证。
