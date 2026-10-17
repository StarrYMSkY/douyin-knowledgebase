"""Local ASR + frame OCR, with timestamped evidence and conservative review flags.

Input manifest is JSONL, one object per video: id, path, url, published_at, title.
Only records with a known publication date in scope can enter the knowledge base.
"""
import argparse
from datetime import datetime, date, timezone, timedelta
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

ROOT = Path(__file__).resolve().parent

def normalized(text):
    return re.sub(r'[^\w]', '', text).lower()

def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)

def extract_ocr(path, engine, interval, crop_top):
    import av
    from av.codec.hwaccel import HWAccel
    try:
        container = av.open(str(path), hwaccel=HWAccel('cuda', allow_software_fallback=True))
    except Exception:
        container = av.open(str(path))
    if not container.streams.video:
        container.close()
        raise ValueError('No video track')
    stream = container.streams.video[0]
    duration = float(stream.duration * stream.time_base) if stream.duration else container.duration / av.time_base
    width = min(720, stream.width)
    height = round(stream.height * width / stream.width / 2) * 2
    rows = []
    next_sample = 0.0
    samples = 0
    try:
        for decoded in container.decode(video=0):
            if decoded.time is None: continue
            t = max(0.0, float(decoded.time) - float(stream.start_time or 0) * stream.time_base)
            if t + 0.001 < next_sample: continue
            next_sample = t + interval
            frame = decoded.reformat(width=width, height=height, format='bgr24').to_ndarray()
            # Preserve the opening title; subsequent frames focus on spoken captions.
            effective_crop = 0.0 if samples == 0 else crop_top
            crop_offset = int(frame.shape[0] * effective_crop)
            region = frame[crop_offset:, :]
            detections, _ = engine(region)
            parts = [(box, text, float(score)) for box, text, score in (detections or []) if score >= 0.5]
            parts.sort(key=lambda item: (min(p[1] for p in item[0]), min(p[0] for p in item[0])))
            text = ' '.join(item[1] for item in parts)
            if text:
                if rows and normalized(rows[-1]['text']) == normalized(text) and rows[-1]['end'] >= t - interval:
                    rows[-1]['end'] = min(t + interval, duration)
                else:
                    lines = [{'text': text, 'confidence': score,
                              'box': [[float(x), float(y + crop_offset)] for x, y in box]}
                             for box, text, score in parts]
                    subtitle = ' '.join(line['text'] for line in lines
                                        if min(point[1] for point in line['box']) >= frame.shape[0] * 0.5)
                    rows.append({'start': t, 'end': min(t + interval, duration),
                                 'text': text, 'subtitle_text': subtitle, 'lines': lines,
                                 'processed_frame_size': [width, height],
                                 'confidence': min(item[2] for item in parts)})
            samples += 1
            if samples % 100 == 0:
                print(f'OCR {path.name}: {t:.1f}/{duration:.1f}s', flush=True)
    finally:
        container.close()
    return rows

def compare(segments, ocr):
    rows = []
    for segment in segments:
        matches = [r for r in ocr if r['start'] < segment['end'] and r['end'] > segment['start']]
        subtitle = ' '.join(r.get('subtitle_text', r['text']) for r in matches)
        similarity = SequenceMatcher(None, normalized(segment['text']), normalized(subtitle)).ratio() if subtitle else None
        rows.append({**segment, 'ocr_text': subtitle, 'similarity': similarity,
                     'status': 'automatic_agreement' if similarity == 1 else 'needs_review',
                     'reason': 'OCR missing' if not subtitle else 'Machine comparison only; verify original audio and frames'})
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--since', default='0001-01-01', help='Inclusive publication date; batch runner supplies config date')
    parser.add_argument('--model', type=Path, default=ROOT / 'models/faster-whisper-small')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--ocr-device', choices=['cpu', 'cuda', 'dml'], default='cpu')
    parser.add_argument('--watch', action='store_true', help='Process newly downloaded records until download_complete.json appears')
    parser.add_argument('--shard-index',type=int,default=0)
    parser.add_argument('--shard-count',type=int,default=1)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--crop-top', type=float, default=0.0, help='Fraction to crop from frame top; inspect caption placement first')
    args = parser.parse_args()
    if args.interval <= 0 or not 0 <= args.crop_top < 1:
        parser.error('interval must be positive and crop-top must be in [0, 1)')
    from faster_whisper import WhisperModel
    from rapidocr_onnxruntime import RapidOCR
    model = WhisperModel(str(args.model), device=args.device,
                         compute_type='int8' if args.device == 'cpu' else 'float16', local_files_only=True)
    gpu = args.ocr_device == 'cuda'
    engine = RapidOCR(det_use_cuda=gpu, cls_use_cuda=gpu, rec_use_cuda=gpu,
                      det_use_dml=args.ocr_device == 'dml', cls_use_dml=args.ocr_device == 'dml', rec_use_dml=args.ocr_device == 'dml',
                      use_cls=False, rec_img_shape=[3,48,960],
                      intra_op_num_threads=2, inter_op_num_threads=2)
    if gpu and ('CUDAExecutionProvider' not in engine.text_det.infer.session.get_providers()
                or 'CUDAExecutionProvider' not in engine.text_rec.session.session.get_providers()):
        raise RuntimeError('GPU OCR was requested but a CUDA execution provider did not load')
    if args.ocr_device == 'dml' and ('DmlExecutionProvider' not in engine.text_det.infer.session.get_providers()
                or 'DmlExecutionProvider' not in engine.text_rec.session.session.get_providers()):
        raise RuntimeError('DirectML OCR was requested but the DirectML provider did not load')
    out = ROOT / 'knowledge'
    out.mkdir(exist_ok=True)
    database = sqlite3.connect(out / 'knowledge.sqlite',timeout=60)
    database.execute('PRAGMA busy_timeout=60000')
    database.execute('CREATE TABLE IF NOT EXISTS evidence (video_id TEXT, start REAL, end REAL, asr TEXT, ocr TEXT, source_url TEXT, published_at TEXT, status TEXT)')
    database.execute('CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(video_id UNINDEXED, asr, ocr, tokenize="trigram")')
    cutoff = date.fromisoformat(args.since)
    failures = []
    failed_ids = set()
    completed_ids = set()
    progress_path=out/f'progress-{args.shard_index}.json'
    failure_path=out/f'failures-{args.shard_index}.json'
    while True:
      for line in args.manifest.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip(): continue
        record = json.loads(line)
        if int(record['id']) % args.shard_count != args.shard_index: continue
        if record['id'] in failed_ids: continue
        try:
            published = date.fromisoformat(record['published_at'][:10])
            if published < cutoff:
                continue
            if not re.fullmatch(r'[A-Za-z0-9_-]+', record['id']):
                raise ValueError('Unsafe video ID')
            if not record.get('url'):
                raise ValueError('Source URL is required')
            path = Path(record['path'])
            if not path.is_absolute():
                path = args.manifest.resolve().parent / path
            audio_path = Path(record.get('audio_path', str(path)))
            if not audio_path.is_absolute(): audio_path = args.manifest.resolve().parent / audio_path
            folder = out / record['id']
            folder.mkdir(exist_ok=True)
            if (folder / 'source.json').exists() and (folder / 'comparison.json').exists():
                previous = json.loads((folder / 'source.json').read_text(encoding='utf-8'))
                if previous.get('asr_model') == str(args.model) and previous.get('ocr_interval') == args.interval and previous.get('crop_top') == args.crop_top:
                    completed_ids.add(record['id'])
                    continue
            write_json(progress_path, {'active_video': record['id'], 'stage': 'asr', 'updated_at': datetime.now().astimezone().isoformat()})
            segments, info = model.transcribe(str(audio_path), language='zh', vad_filter=True, beam_size=5)
            asr = [{'start': s.start, 'end': s.end, 'text': s.text, 'avg_logprob': s.avg_logprob,
                    'no_speech_prob': s.no_speech_prob} for s in segments]
            write_json(folder / 'asr.json', asr)
            write_json(progress_path, {'active_video': record['id'], 'stage': 'ocr', 'updated_at': datetime.now().astimezone().isoformat()})
            ocr = extract_ocr(path, engine, args.interval, args.crop_top)
            write_json(folder / 'ocr.json', ocr)
            review = compare(asr, ocr)
            write_json(folder / 'comparison.json', review)
            with path.open('rb') as source_file:
                digest = hashlib.file_digest(source_file, 'sha256').hexdigest()
            write_json(folder / 'source.json', {**record, 'sha256': digest, 'asr_model': str(args.model),
                       'duration': info.duration, 'generated_at': datetime.now().astimezone().isoformat(),
                       'review_status': 'unverified', 'ocr_interval': args.interval, 'crop_top': args.crop_top,
                       'ocr_device': args.ocr_device, 'ocr_rec_width':960,
                       'decoder':'PyAV continuous decode with CUDA when available', 'speech_detected':bool(asr), 'ocr_detected':bool(ocr)})
            with database:
                database.execute('DELETE FROM evidence WHERE video_id=?', (record['id'],))
                database.execute('DELETE FROM evidence_fts WHERE video_id=?', (record['id'],))
                for row in review:
                    database.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)',
                        (record['id'], row['start'], row['end'], row['text'], row['ocr_text'], record['url'], record['published_at'], row['status']))
                    database.execute('INSERT INTO evidence_fts VALUES (?,?,?)', (record['id'], row['text'], row['ocr_text']))
            print(f"Processed {record['id']}: {len(asr)} ASR segments; {len(ocr)} OCR spans", flush=True)
            completed_ids.add(record['id'])
            write_json(progress_path, {'active_video': None, 'stage': 'waiting',
                       'processed_videos': database.execute('SELECT COUNT(DISTINCT video_id) FROM evidence').fetchone()[0],
                       'updated_at': datetime.now().astimezone().isoformat()})
        except Exception as error:
            failed_ids.add(record.get('id'))
            failures.append({'record': record, 'error': str(error)})
            print(f"FAILED {record.get('id')}: {error}", flush=True)
      write_json(failure_path, failures)
      latest_records=[json.loads(line) for line in args.manifest.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
      pending=[r for r in latest_records if int(r['id']) % args.shard_count == args.shard_index and r['id'] not in completed_ids and r['id'] not in failed_ids]
      if pending: continue
      if not args.watch or (ROOT / 'capture/download_complete.json').exists(): break
      time.sleep(5)
    write_json(failure_path, failures)
    database.close()
    if failures:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
