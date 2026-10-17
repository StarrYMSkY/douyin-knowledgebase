"""Finite, resumable download/ASR/OCR job; configuration in config.json."""
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime
from kb_config import config, selected_posts

ROOT = Path(__file__).resolve().parent

def status(stage, **fields):
    target = ROOT/'knowledge/job-status.json'
    target.parent.mkdir(exist_ok=True)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps({'stage':stage, 'updated_at':datetime.now().astimezone().isoformat(), **fields}, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)

def audit():
    expected = {p['id'] for p in selected_posts()}
    assets = json.loads((ROOT/'capture/downloads.json').read_text(encoding='utf-8'))
    ready = {p['id'] for p in assets if p['status']=='downloaded'}
    missing, empty, processed = [], [], []
    for key in sorted(expected):
        try:
            folder = ROOT/'knowledge'/key
            values = [json.loads((folder/name).read_text(encoding='utf-8')) for name in
                      ['source.json','asr.json','ocr.json','comparison.json']]
            if values[0]['id'] != key: raise ValueError('Source ID mismatch')
            processed.append(key)
            if not values[1] or not values[2] or not values[3]: empty.append(key)
        except (OSError, ValueError, KeyError): missing.append(key)
    report = {'expected':len(expected), 'assets_ready':len(expected & ready),
              'processed':len(processed), 'missing_processing':missing,
              'missing_media':sorted(expected-ready), 'empty_text':empty,
              'download_failures':[p for p in assets if p['status']!='downloaded'],
              'complete':bool(expected) and expected <= ready and not missing and not empty,
              'review_scope':'Machine comparison only; empty text needs review; no full human listening claim',
              'finished_at':datetime.now().astimezone().isoformat()}
    (ROOT/'knowledge/audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def build_index():
    subprocess.run([sys.executable,str(ROOT/'build_index.py')],cwd=ROOT,check=True)

def process(cfg):
    children, streams = [], []
    try:
        for shard in range(cfg['workers']):
            stream = (ROOT/f'logs/worker-{shard}.log').open('a',encoding='utf-8')
            streams.append(stream)
            cmd = [sys.executable,'-X','utf8','-u',str(ROOT/'pipeline.py'),str(ROOT/'manifest.jsonl'),
                   '--since',cfg['since'],'--model',str(ROOT/'models'/('faster-whisper-'+cfg['model'])),
                   '--device',cfg['device'],'--ocr-device',cfg['ocr_device'],
                   '--crop-top',str(cfg['crop_top']),'--interval',str(cfg['interval']),
                   '--shard-index',str(shard),'--shard-count',str(cfg['workers'])]
            children.append(subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT))
        count_previous = -1
        while any(p.poll() is None for p in children):
            count = len(list((ROOT/'knowledge').glob('*/source.json')))
            if count != count_previous:
                build_index()
                status('processing',processed=count,expected=len(selected_posts()))
                print(f'PROGRESS: {count}/{len(selected_posts())}',flush=True)
                count_previous = count
            time.sleep(5)
        return all(p.returncode == 0 for p in children)
    finally:
        for p in children:
            if p.poll() is None: p.terminate()
        for p in children:
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        for stream in streams: stream.close()

def main():
    cfg = config()
    (ROOT/'logs').mkdir(exist_ok=True)
    catalog_status = json.loads((ROOT/'capture/status.json').read_text(encoding='utf-8'))
    if not catalog_status.get('catalog_complete'):
        raise SystemExit('Catalog incomplete: inspect browser/access; do not claim all posts.')
    if catalog_status.get('profile_url') != cfg['profile_url']:
        raise SystemExit('Catalog belongs to another profile; use a new workspace.')
    for attempt in range(1,4):
        status('downloading',attempt=attempt)
        with (ROOT/f'logs/download-{attempt}.log').open('a',encoding='utf-8') as log:
            result = subprocess.run([sys.executable,'-u',str(ROOT/'download_catalog.py'),'--workers','4'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode == 0: break
    if not (ROOT/'manifest.jsonl').exists():
        status('needs_attention',reason='No downloadable media manifest')
        raise SystemExit(2)
    for attempt in range(2):
        process(cfg)
        report = audit()
        if not report['missing_processing']: break
    build_index()
    status('complete' if report['complete'] else 'needs_attention',**report)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report['complete']: raise SystemExit(2)

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt:
        status('interrupted',reason='User interrupted; completed results retained')
        raise SystemExit(130)
