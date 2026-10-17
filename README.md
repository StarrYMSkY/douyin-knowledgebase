# Douyin Knowledge Base

**English** | [简体中文](README.zh-CN.md)

A reusable Codex Skill for turning a creator's publicly accessible Douyin videos into a local, searchable evidence library—with speech transcripts, on-screen subtitles, timestamps, and source links.

Extracted from a real batch-processing workflow. Creator URLs, date ranges, workspace paths, and hardware settings are configurable. This repository contains tools and instructions, **not collected videos, transcripts, login sessions, or model weights**.

## Workflow

1. **Collect the catalog in batches.** A dedicated Chrome profile loads the public post list after the user signs in. Record unique video IDs and whether pagination actually finished.
2. **Validate downloaded media.** Filter by publication date, check video and audio tracks, and download separate audio when a low-bitrate video has none.
3. **Run local ASR and OCR.** Use faster-whisper for Mandarin speech and RapidOCR for on-screen text.
4. **Compare timestamped evidence.** Keep both originals and flag differences for review.
5. **Build and audit the library.** Export offline HTML search, JSON, and a SQLite full-text index; report missing or empty results.

The packaged pipeline downloads first, then processes videos with configurable workers. Retries are bounded and compatible completed results can be reused.

## Requirements

- Reference environment: **Windows + Python 3.12**. Other platforms have not been validated end to end.
- Node.js/npm and Google Chrome for catalog collection.
- Network access for initial dependency/model downloads and authorized media collection; sufficient disk space for media and models.
- CPU is the default. GPU acceleration is optional and requires a compatible runtime verified on your machine.

Installing packages does not mean model weights are ready. Model download, local loading, and real-sample inference are separate checks.

## Quick start

Run in PowerShell. Replace the example creator URL and dates. The job directory must be new or empty and is created outside the source repository.

```powershell
git clone https://github.com/StarrYMSkY/douyin-knowledgebase.git
cd douyin-knowledgebase

$skillPath = (Resolve-Path .\skills\douyin-video-knowledge).Path
$jobPath = Join-Path (Split-Path (Get-Location).Path -Parent) "douyin-job"

python "$skillPath\scripts\initialize.py" `
  --workspace "$jobPath" `
  --profile "https://www.douyin.com/user/REPLACE_WITH_CREATOR_ID" `
  --since 2024-08-29 --until 2026-10-18 `
  --title "Public Video Evidence Library"

Set-Location "$jobPath"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install

node collect-browser.cjs
.\.venv\Scripts\python.exe prepare_models.py --model small
.\.venv\Scripts\python.exe -X utf8 -u finish_pipeline.py
```

Complete login and verification yourself in the dedicated Chrome window. The collector uses normal browser-loaded public post data and does not export cookies. Resolve access or incomplete-pagination problems before proceeding; a partial catalog is not treated as complete.

**Date range: `[since, until)` in Asia/Shanghai time.** The start date is included; the end date is excluded. To exclude August 28 entirely, use `--since 2024-08-29`. Always choose an explicit end date for the snapshot.

Before a large batch, validate one video in a separate test workspace: check the audio, Mandarin transcript, subtitle position, and timestamp alignment. Default processing is one CPU worker with full-frame OCR. Only tune cropping or GPU settings after checking a sample.

## Use as a Skill

Place the entire `skills/douyin-video-knowledge` folder in your configured Codex skills directory, then invoke:

```text
Use $douyin-video-knowledge to collect this creator's public videos
within the specified date range and build a local evidence library.
```

The [Skill entry point](skills/douyin-video-knowledge/SKILL.md) and [operating guide](skills/douyin-video-knowledge/references/operation.md) cover scope checks, model verification, optional GPU setup, recovery, and review standards. These agent-facing guides are currently in Chinese.

## Structure

```text
skills/douyin-video-knowledge/
├── SKILL.md                 # Agent instructions and boundaries
├── agents/openai.yaml       # Skill discovery metadata
├── scripts/
│   ├── initialize.py        # Create an isolated job workspace
│   └── test_runtime.py      # Offline regression tests
├── assets/runtime/          # Collection and processing scripts
└── references/operation.md  # Detailed operation and troubleshooting
```

## Outputs and progress

| Path in the job workspace | Purpose |
| --- | --- |
| `capture/posts.json`, `capture/status.json` | Catalog, publication metadata, pagination completeness |
| `manifest.jsonl` | Downloaded, audio-validated processing inputs |
| `knowledge/<video-id>/` | Source metadata, ASR, OCR, and comparison JSON |
| `knowledge/index.html` | Offline keyword search and timestamped comparisons |
| `knowledge/index.json`, `knowledge/knowledge.sqlite` | Structured documents and full-text index |
| `knowledge/job-status.json`, `knowledge/progress-*.json` | Overall and worker progress |
| `knowledge/audit.json`, `logs/` | Final coverage audit and execution logs |

Open `knowledge/index.html` locally and refresh as processing advances. Completion requires the final audit to pass, not just successful downloads. After interruption, rerun the pipeline in the same workspace to reuse compatible results. Use a new workspace for another creator or materially different configuration.

## Accuracy, privacy, and limitations

- **Machine agreement is not human verification.** `automatic_agreement` means normalized texts match. `needs_review` can mean recognition errors, missing OCR, or timing differences; neither is a calibrated accuracy score.
- Attribute claims: distinguish the creator's views, quotations, predictions, examples, and your summaries. Preserve source links/time ranges, and check names, numbers, units, negations, and context before quoting.
- Completeness refers to the publicly accessible snapshot at collection time. Deleted, private, blocked, or later-published videos are not guaranteed to be included.
- Frame sampling/cropping can miss brief or repositioned captions. Speech recognition is configured for Mandarin. Default topic labels are finance/property keyword examples, not semantic classification.
- Process only content you are authorized to access and use. No login, CAPTCHA, private-content, or other access-control bypasses are provided.
- Keep browser profiles, cookies, signed media URLs, media, transcripts, model weights, and logs out of source control. Job folders contain sensitive session data and should remain local.
- Website behavior and package compatibility may change. Offline tests do not verify live Douyin access, model downloads, GPU drivers, or every target machine.

## Validation

From the repository root:

```powershell
python -X utf8 skills/douyin-video-knowledge/scripts/test_runtime.py
```

Five offline tests cover initialization/overwrite protection, date filtering, text comparison, coverage audit/index generation, and Python source compilation. They use temporary fixtures, without contacting Douyin or downloading models.

## Acknowledgements

Thank you to the maintainers and contributors of the open-source projects used or evaluated in this workflow:

| Project | Role in this workflow |
| --- | --- |
| [F2 — Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) | Installed and evaluated during the original Douyin collection work. F2 is not a runtime dependency of this release; the packaged collector uses normal page requests from a user-authenticated browser instead. |
| [Playwright — Microsoft](https://github.com/microsoft/playwright) | Browser automation and public-post catalog collection. |
| [faster-whisper — SYSTRAN](https://github.com/SYSTRAN/faster-whisper) | Local speech transcription. |
| [RapidOCR — RapidAI](https://github.com/RapidAI/RapidOCR) | On-screen subtitle and text recognition. |
| [PyAV](https://github.com/PyAV-Org/PyAV) | Audio/video stream validation and frame decoding. |
| [ONNX Runtime — Microsoft](https://github.com/microsoft/onnxruntime) | Inference runtime used by the OCR pipeline, with optional hardware acceleration. |

The speech model is downloaded separately from [SYSTRAN's faster-whisper model repository](https://huggingface.co/Systran/faster-whisper-small). Credit for upstream libraries and models belongs to their respective authors; this project packages the workflow and integration scripts and does not imply upstream endorsement or affiliation.

Dependencies and model weights retain their respective licenses and usage terms. Please consult the upstream repositories before use or redistribution. Third-party source code, model weights, and creator media are not redistributed here.
