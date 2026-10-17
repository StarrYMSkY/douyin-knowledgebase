"""Resumable downloads from official model/PyPI metadata, with SHA-256 verification."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent

def metadata(url):
    for attempt in range(6):
        try:
            with urlopen(url, timeout=25) as response: return json.load(response)
        except Exception:
            if attempt==5: raise
            time.sleep(2)

def fetch(url, target, size, digest):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.download')
    for attempt in range(15):
        offset = temporary.stat().st_size if temporary.exists() else 0
        if offset == size: break
        try:
            headers = {'User-Agent':'douyin-knowledge-local/1.0'}
            if offset: headers['Range'] = f'bytes={offset}-'
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                if offset and response.status != 206:
                    raise RuntimeError('Server did not accept resume range')
                with temporary.open('ab' if offset else 'wb') as output:
                    while chunk := response.read(256*1024): output.write(chunk)
            print(f'Downloaded {temporary.stat().st_size}/{size} bytes', flush=True)
        except Exception as error:
            print(f'Retry {attempt+1}: {type(error).__name__}; have {temporary.stat().st_size if temporary.exists() else 0}/{size}', flush=True)
            time.sleep(1)
    if not temporary.exists() or temporary.stat().st_size != size: raise RuntimeError('Incomplete download')
    with temporary.open('rb') as file: actual = hashlib.file_digest(file, 'sha256').hexdigest()
    if actual != digest: raise RuntimeError(f'SHA-256 mismatch; expected {digest}, got {actual}')
    temporary.replace(target)
    print(f'VERIFIED {target}', flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('kind', choices=['wheel','model'])
    parser.add_argument('name')
    parser.add_argument('--version')
    args=parser.parse_args()
    if args.kind=='wheel':
        data=metadata(f'https://pypi.org/pypi/{args.name}/{args.version}/json')
        record=next(x for x in data['urls'] if 'cp312-cp312-win_amd64.whl' in x['filename'])
        fetch(record['url'],ROOT/'packages'/record['filename'],record['size'],record['digests']['sha256'])
    else:
        data=metadata(f'https://huggingface.co/api/models/{args.name}?blobs=true')
        record=next(x for x in data['siblings'] if x['rfilename']=='model.bin')
        target=ROOT/'models'/args.name.split('/')[-1]/'model.bin'
        fetch(f"https://huggingface.co/{args.name}/resolve/{data['sha']}/model.bin",target,record['lfs']['size'],record['lfs']['sha256'])

if __name__=='__main__': main()
