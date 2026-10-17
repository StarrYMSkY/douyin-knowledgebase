"""Shared, user-owned job configuration; no account or machine defaults."""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
ZONE = timezone(timedelta(hours=8))

def config():
    return json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))

def bounds(cfg):
    return tuple(datetime.fromisoformat(cfg[key]).replace(tzinfo=ZONE).timestamp()
                 for key in ('since', 'until_exclusive'))

def selected_posts():
    start, stop = bounds(config())
    posts = json.loads((ROOT/'capture/posts.json').read_text(encoding='utf-8'))
    return [p for p in posts if start <= p['create_time'] < stop]
