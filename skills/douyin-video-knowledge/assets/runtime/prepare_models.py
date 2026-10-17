"""Download official Whisper weights into this project, then verify local loading."""
from pathlib import Path
import argparse
import json
import urllib.request
import shutil

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['small', 'medium', 'large-v3'], default='small')
    parser.add_argument('--download-only', action='store_true')
    args = parser.parse_args()
    destination = ROOT / 'models' / ('faster-whisper-' + args.model)
    if args.download_only:
        destination.mkdir(parents=True, exist_ok=True)
        api = 'https://huggingface.co/api/models/Systran/faster-whisper-' + args.model
        with urllib.request.urlopen(api, timeout=30) as response:
            metadata = json.load(response)
        revision = metadata['sha']
        for name in ['config.json', 'tokenizer.json', 'vocabulary.txt', 'model.bin']:
            target = destination / name
            if target.exists():
                continue
            url = f'https://huggingface.co/Systran/faster-whisper-{args.model}/resolve/{revision}/{name}'
            temporary = target.with_suffix(target.suffix + '.partial')
            print(f'Downloading {name}', flush=True)
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            temporary.replace(target)
        (destination / 'source.json').write_text(json.dumps({'repo': metadata['id'], 'revision': revision}), encoding='utf-8')
        print('Download complete; local model loading has not yet been verified.', flush=True)
        return
    from huggingface_hub import snapshot_download
    from faster_whisper import WhisperModel
    from rapidocr_onnxruntime import RapidOCR
    if not (destination / 'model.bin').exists():
        snapshot_download('Systran/faster-whisper-' + args.model,
                          local_dir=str(destination),
                          allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.*'])
    WhisperModel(str(destination), device='cpu', compute_type='int8', local_files_only=True)
    RapidOCR()
    report = {'asr_model': str(destination), 'local_load_verified': True,
              'ocr': 'rapidocr-onnxruntime bundled Chinese OCR models'}
    (ROOT / 'models' / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
