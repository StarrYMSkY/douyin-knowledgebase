"""Publish an offline searchable index of the local, timestamped evidence."""
import json
from html import escape
from pathlib import Path
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'knowledge'
TOPICS = {'货币与利率':['美债','美联储','加息','降息','货币'], '房产':['房价','楼市','买房','房地产','房产'],
          '交易与风险':['交易','风险','止损','抄底','波段','杠杆'], '汇率与资金':['汇率','美元','人民币','资金','外资'],
          '周期与资产':['牛市','熊市','周期','资产','估值']}
def main():
    documents = []
    for source in OUT.glob('*/source.json'):
        folder = source.parent
        try:
            meta = json.loads(source.read_text(encoding='utf-8'))
            comparison = json.loads((folder / 'comparison.json').read_text(encoding='utf-8'))
            asr = json.loads((folder / 'asr.json').read_text(encoding='utf-8'))
            ocr = json.loads((folder / 'ocr.json').read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError): continue
        text = ' '.join(r['text'] for r in asr)
        caption = ' '.join(r.get('subtitle_text',r['text']) for r in ocr)
        topics = [name for name, words in TOPICS.items() if any(w in text + caption for w in words)]
        documents.append({**meta, 'topics':topics, 'asr_text':text, 'ocr_text':caption, 'segments':comparison,
                          'disagreements':sum(s['status']=='needs_review' for s in comparison)})
    documents.sort(key=lambda d:d['published_at'],reverse=True)
    OUT.mkdir(exist_ok=True)
    (OUT/'index.json').write_text(json.dumps(documents,ensure_ascii=False),encoding='utf-8')
    payload = json.dumps(documents,ensure_ascii=False).replace('<','\\u003c')
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__KB_TITLE__</title><style>body{font:16px/1.65 system-ui,sans-serif;background:#f4f5f7;color:#202936;margin:0}main{max-width:1150px;margin:40px auto;padding:0 24px}h1{font-size:30px}input,select{font:inherit;padding:12px;border:1px solid #ccd3dc;border-radius:8px}input{width:65%}article{background:white;padding:22px;margin:18px 0;border-radius:12px;border:1px solid #e2e5e9}small,.meta{color:#677386}a{color:#1661aa}table{width:100%;border-collapse:collapse;margin-top:16px}td,th{padding:10px;border:1px solid #e0e4ea;vertical-align:top;text-align:left}th{background:#edf3f9}.flag{color:#99601b}details{margin-top:12px}summary{cursor:pointer}mark{background:#fff2ad}.warning{background:#fff6dc;border-left:4px solid #c79a31;padding:14px}</style>
<main><h1>__KB_TITLE__</h1><p class="meta">范围：__KB_RANGE__ · 原视频、语音转写、画面字幕与时间戳</p>
<p class="warning">这是公开言论的整理，不代表这些观点已经被事实验证。转写与字幕分别保留；差异段落标记待复核，不能把机器文本当作已逐字确认的引文。主题标签按关键词生成。</p>
<input id="q" placeholder="搜索词句，例如：美债、楼市、资金、周期"><select id="topic"><option value="">全部主题</option></select><p id="count"></p><div id="results"></div></main>
<script>const docs=__DATA__;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const q=document.querySelector('#q'),topic=document.querySelector('#topic'),box=document.querySelector('#results');
[...new Set(docs.flatMap(d=>d.topics))].sort().forEach(t=>{const o=document.createElement('option');o.value=o.textContent=t;topic.append(o)});
function render(){const term=q.value.trim().toLowerCase();const hits=docs.filter(d=>(!topic.value||d.topics.includes(topic.value))&&(!term||(d.title+' '+d.asr_text+' '+d.ocr_text).toLowerCase().includes(term)));document.querySelector('#count').textContent=`已完成双通道处理 ${docs.length} / __KB_EXPECTED__ 条；当前匹配 ${hits.length} 条`;box.innerHTML=hits.map(d=>`<article><h2>${esc(d.title||d.id)}</h2><p class="meta">${esc(d.published_at)} · ${Math.round(d.duration)} 秒 · ${esc(d.topics.join(' / '))}</p><a href="${esc(d.url)}" target="_blank" rel="noopener">打开原视频</a> · <span class="flag">${d.disagreements} 个机器差异段待复核</span><details><summary>语音转写全文</summary><p>${esc(d.asr_text)}</p></details><details><summary>画面字幕全文</summary><p>${esc(d.ocr_text)}</p></details><details><summary>查看时间戳与逐段核对</summary><table><tr><th>秒数</th><th>语音</th><th>字幕</th><th>状态</th></tr>${d.segments.map(s=>`<tr><td>${s.start.toFixed(1)}–${s.end.toFixed(1)}</td><td>${esc(s.text)}</td><td>${esc(s.ocr_text)}</td><td>${s.status==='automatic_agreement'?'机器一致':'待复核'}</td></tr>`).join('')}</table></details></article>`).join('')}
q.addEventListener('input',render);topic.addEventListener('change',render);render();</script></html>'''.replace('__DATA__',payload)
    from kb_config import config, selected_posts
    cfg = config()
    expected = len(selected_posts()) if (ROOT/'capture/posts.json').exists() else len(documents)
    html = html.replace('__KB_TITLE__', escape(cfg['title'])).replace('__KB_RANGE__', escape(cfg['since'] + ' 至 ' + cfg['until_exclusive'] + '（不含末日）')).replace('__KB_EXPECTED__', str(expected))
    selected_path=OUT/'selected_statements.json'
    if selected_path.exists():
        selected=json.loads(selected_path.read_text(encoding='utf-8'))
        cards=''.join(f'<article><strong>{escape(s["topic"])}</strong><p>{escape(s["statement"])}</p><small>{escape(s["kind"])} · {escape(s["published_at"])} · {s["start"]}–{s["end"]} 秒</small><p><a href="{escape(s["source_url"])}">原视频</a> · {escape(s["review_method"])}</p></article>' for s in selected)
        html=html.replace('<input id="q"', '<section><h2>已抽样对照的观点摘要</h2>'+cards+'</section><h2>全库检索</h2><input id="q"')
    (OUT/'index.html').write_text(html,encoding='utf-8')
    print(f'Offline index updated: {len(documents)} videos')
if __name__=='__main__': main()
