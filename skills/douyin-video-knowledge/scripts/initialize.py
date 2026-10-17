"""Create a separate job workspace, never overwrite existing job data."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--since', required=True)
    parser.add_argument('--until', required=True, help='Exclusive end date, Asia/Shanghai')
    parser.add_argument('--title', default='公开视频言论证据库')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--device', choices=['cpu','cuda'], default='cpu')
    parser.add_argument('--ocr-device', choices=['cpu','dml','cuda'], default='cpu')
    parser.add_argument('--model', choices=['small','medium','large-v3'], default='small')
    parser.add_argument('--crop-top', type=float, default=0)
    args = parser.parse_args()
    u = urlparse(args.profile)
    if u.scheme != 'https' or u.hostname != 'www.douyin.com' or not u.path.startswith('/user/') or not u.path[6:].strip('/'):
        parser.error('profile must be an https://www.douyin.com/user/... URL')
    if date.fromisoformat(args.since) >= date.fromisoformat(args.until):
        parser.error('since must precede exclusive until')
    if not 1 <= args.workers <= 8 or not 0 <= args.crop_top < 1:
        parser.error('workers must be 1..8 and crop-top in [0,1)')
    destination = args.workspace.resolve()
    if destination.exists() and any(destination.iterdir()):
        parser.error('workspace must be new or empty; resume existing jobs directly')
    destination.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1]/'assets/runtime'
    for path in source.iterdir():
        if path.is_file(): shutil.copy2(path, destination/path.name)
    cfg = {'profile_url': args.profile, 'since': args.since, 'until_exclusive': args.until,
           'title': args.title, 'workers': args.workers, 'device': args.device,
           'ocr_device': args.ocr_device, 'model': args.model,
           'crop_top': args.crop_top, 'interval': 0.5}
    (destination/'config.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Initialized {destination}; install dependencies, verify a sample, then collect the catalog.')

if __name__ == '__main__': main()
