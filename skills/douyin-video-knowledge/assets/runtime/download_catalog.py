"""Download the public URLs captured from the authenticated post list in parallel."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import av
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ZONE = timezone(timedelta(hours=8))

def get_file(url, destination):
    try:
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.douyin.com/'}),timeout=25) as response, destination.open('wb') as output:
            expected=response.headers.get('Content-Length')
            shutil.copyfileobj(response,output,length=256*1024)
        if expected and destination.stat().st_size != int(expected): raise ValueError('Incomplete HTTP response')
    except Exception:
        curl=shutil.which('curl.exe')
        if not curl: raise
        result=subprocess.run([curl,'--location','--fail','--silent','--show-error','--retry','1','--retry-all-errors',
            '--connect-timeout','10','--max-time','45','--user-agent','Mozilla/5.0','--referer','https://www.douyin.com/',
            '--output',str(destination),url],capture_output=True,text=True)
        if result.returncode: raise RuntimeError('curl transfer failed: '+result.stderr[:180])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    posts = json.loads((ROOT / 'capture/posts.json').read_text(encoding='utf-8'))
    from kb_config import config, bounds
    start, end = bounds(config())
    selected = [p for p in posts if start <= p['create_time'] < end]
    media = ROOT / 'media'; media.mkdir(exist_ok=True)
    results = {}
    def finalize(p, destination, existing):
        with av.open(str(destination)) as container:
            if not container.streams.video: raise ValueError('No video track')
            has_audio = bool(container.streams.audio)
        audio_path = destination
        if not has_audio:
            audio_path = media / (p['id'] + '.m4a')
            valid = False
            if audio_path.exists():
                try:
                    with av.open(str(audio_path)) as container: valid = bool(container.streams.audio)
                except Exception: pass
            if not valid:
                variants = sorted(p.get('video_meta', {}).get('bit_rate_audio', []),
                                  key=lambda row: row.get('audio_meta', {}).get('bitrate', 0), reverse=True)
                audio_urls = []
                for variant in variants:
                    urls = variant.get('audio_meta', {}).get('url_list', {})
                    audio_urls.extend([urls.get('backup_url'), urls.get('main_url')])
                last_error = 'No separate audio URLs'
                for url in audio_urls:
                    if not url: continue
                    try:
                        temporary = audio_path.with_suffix('.audio-download')
                        get_file(url,temporary)
                        with av.open(str(temporary)) as container:
                            if not container.streams.audio: raise ValueError('No audio track in audio response')
                        temporary.replace(audio_path); valid=True; break
                    except Exception as error: last_error = type(error).__name__ + ': ' + str(error)[:150]
                if not valid:
                    for url in p.get('video_meta', {}).get('play_addr', {}).get('url_list', []):
                        parsed = urlparse(url)
                        if parsed.scheme != 'https' or not any((parsed.hostname or '').endswith(d) for d in ['.zjcdn.com','.douyinvod.com']): continue
                        try:
                            temporary=destination.with_suffix('.combined-download')
                            get_file(url,temporary)
                            with av.open(str(temporary)) as container:
                                if not container.streams.video or not container.streams.audio: raise ValueError('Combined stream lacks audio or video')
                            temporary.replace(destination); audio_path=destination; valid=True; break
                        except Exception as error: last_error=type(error).__name__+': '+str(error)[:150]
                if not valid: return {'id':p['id'],'status':'failed','errors':[last_error],'video_saved':True}
        return {'id':p['id'],'status':'downloaded','bytes':destination.stat().st_size,
                'existing':existing,'audio_path':str(audio_path),'has_audio':True}
    def download(p):
        destination = media / (p['id'] + '.mp4')
        if destination.exists() and destination.stat().st_size > 10000:
            try: return finalize(p, destination, True)
            except Exception: pass
        def rank(url):
            parsed = urlparse(url); query = parse_qs(parsed.query)
            bitrate = int(query.get('br', ['999999'])[0])
            # Prefer directly observed CDN files over API redirects; prefer compact encodings.
            return (parsed.hostname == 'www.douyin.com', bitrate, 'experiment' not in (parsed.hostname or ''))
        urls = sorted(p['urls'], key=rank)
        errors = []
        attempted = set()
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not any((parsed.hostname or '').endswith(d) for d in ['.zjcdn.com', '.douyinvod.com']):
                continue
            # At most eight current alternatives; repeated failures must stay visible.
            if len(attempted) >= 8: break
            if url in attempted: continue
            attempted.add(url)
            temporary = destination.with_suffix('.download')
            try:
                request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.douyin.com/'})
                with urlopen(request, timeout=25) as response, temporary.open('wb') as output:
                    expected = response.headers.get('Content-Length')
                    shutil.copyfileobj(response, output, length=1024 * 256)
                size = temporary.stat().st_size
                with temporary.open('rb') as file: header = file.read(64)
                if size < 10000 or b'ftyp' not in header:
                    raise ValueError('Response is not an MP4 video')
                if expected and size != int(expected):
                    raise ValueError('Incomplete HTTP body')
                temporary.replace(destination)
                return finalize(p, destination, False)
            except Exception as error:
                errors.append(type(error).__name__ + ': ' + str(error)[:160])
        return {'id': p['id'], 'status': 'failed', 'errors': errors or ['No supported CDN URL']}
    def checkpoint():
        ordered = [results[p['id']] for p in selected if p['id'] in results]
        (ROOT / 'capture/downloads.json').write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest = []
        for p in selected:
            if results.get(p['id'], {}).get('status') != 'downloaded': continue
            manifest.append(json.dumps({'id': p['id'], 'path': str(media / (p['id'] + '.mp4')),
                'audio_path':results[p['id']]['audio_path'],
                'url': 'https://www.douyin.com/video/' + p['id'],
                'published_at': datetime.fromtimestamp(p['create_time'], ZONE).isoformat(), 'title': p['desc']}, ensure_ascii=False))
        temporary = ROOT / 'manifest.jsonl.tmp'
        temporary.write_text('\n'.join(manifest) + '\n', encoding='utf-8')
        temporary.replace(ROOT / 'manifest.jsonl')
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        jobs = {executor.submit(download, p): p['id'] for p in selected}
        for future in as_completed(jobs):
            result = future.result(); results[result['id']] = result
            checkpoint()
            print(json.dumps({'finished': len(results), 'total': len(selected), **result}, ensure_ascii=False), flush=True)
    failed = sum(r['status'] != 'downloaded' for r in results.values())
    (ROOT / 'capture/download_complete.json').write_text(json.dumps({'expected': len(selected), 'downloaded': len(results)-failed,
        'failed': failed, 'completed_at': datetime.now(ZONE).isoformat()}, indent=2), encoding='utf-8')
    print(f'DONE: {len(results)-failed}/{len(selected)} downloaded; {failed} failed.', flush=True)
    if failed: raise SystemExit(2)

if __name__ == '__main__':
    main()
