// Batch public-post acquisition through a normal, user-authenticated browser.
// No cookies are printed, exported, or passed to third-party services.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const ROOT = __dirname;
const catalogOnly = true; // Catalog and validated media download are separate phases.
const config = JSON.parse(fs.readFileSync(path.join(ROOT, 'config.json'), 'utf8'));
const profileUrl = config.profile_url;
const secUid = new URL(profileUrl).pathname.split('/').filter(Boolean).pop();
const since = Date.parse(config.since + 'T00:00:00+08:00') / 1000;
const until = Date.parse(config.until_exclusive + 'T00:00:00+08:00') / 1000;
const out = path.join(ROOT, 'capture');
const media = path.join(ROOT, 'media');
fs.mkdirSync(out, { recursive: true }); fs.mkdirSync(media, { recursive: true });
const posts = new Map();
let terminal = false, active = 0, failures = [], pageCount = 0, stopping = false;
const queue = [];
const completed = new Set();
const write = (name, value) => fs.writeFileSync(path.join(out, name), JSON.stringify(value, null, 2));
const inScope = p => p.create_time >= since && p.create_time < until;
const chinaDate = epoch => new Date(epoch * 1000 + 8 * 3600000).toISOString().replace('Z', '+08:00');
function checkpoint() {
  const all = [...posts.values()].sort((a, b) => b.create_time - a.create_time);
  write('posts.json', all);
  write('status.json', { profile_url: profileUrl, since: config.since, until_exclusive: config.until_exclusive,
    catalog_complete: terminal, api_pages: pageCount, catalog_count: all.length,
    in_scope: all.filter(inScope).length, downloaded: completed.size, queued: queue.length,
    active, failed: failures.length, updated_at: new Date().toISOString() });
  write('failures.json', failures);
  if (!catalogOnly) fs.writeFileSync(path.join(ROOT, 'manifest.jsonl'), all.filter(p => completed.has(p.id)).map(p => JSON.stringify({
    id: p.id, path: path.join(media, p.id + '.mp4'), url: 'https://www.douyin.com/video/' + p.id,
    published_at: chinaDate(p.create_time), title: p.desc
  })).join('\n') + '\n');
}
async function main() {
  const context = await chromium.launchPersistentContext(path.join(ROOT, '.capture-browser'), {
    channel: 'chrome', headless: false, viewport: { width: 1280, height: 900 },
    acceptDownloads: true, args: ['--autoplay-policy=user-gesture-required']
  });
  const page = context.pages()[0] || await context.newPage();
  async function pump() {
    while (active < 3 && queue.length) {
      const p = queue.shift(); active++;
      (async () => {
        const target = path.join(media, p.id + '.mp4');
        if (fs.existsSync(target) && fs.statSync(target).size > 10000) { completed.add(p.id); return; }
        let last = 'No media URL';
        for (const url of p.urls) {
          try {
            const response = await context.request.get(url, { timeout: 60000, headers: { Referer: 'https://www.douyin.com/' } });
            if (!response.ok()) { last = 'HTTP ' + response.status(); await response.dispose(); continue; }
            const body = await response.body(); await response.dispose();
            if (body.length < 10000 || !body.subarray(0, 64).includes(Buffer.from('ftyp'))) { last = 'Not a complete MP4 response'; continue; }
            fs.writeFileSync(target + '.partial', body); fs.renameSync(target + '.partial', target);
            completed.add(p.id); console.log('DOWNLOADED', p.id, body.length); return;
          } catch (e) { last = e.message.slice(0, 160); }
        }
        failures.push({ id: p.id, error: last });
      })().catch(e => failures.push({ id: p.id, error: e.message.slice(0, 160) })).finally(() => {
        active--; checkpoint(); if (!stopping) pump();
      });
    }
  }
  page.on('response', async response => {
    const url = response.url();
    if (!url.includes('/aweme/v1/web/aweme/post/')) return;
    try {
      const requestUrl = new URL(url);
      if (requestUrl.searchParams.get('sec_user_id') !== secUid) return;
      const data = await response.json();
      if (!Array.isArray(data.aweme_list)) return;
      pageCount++;
      for (const item of data.aweme_list) {
        const id = String(item.aweme_id || '');
        if (!/^\d+$/.test(id) || posts.has(id)) continue;
        if (item.author?.sec_uid && item.author.sec_uid !== secUid) continue;
        const urls = [...new Set([...(item.video?.play_addr?.url_list || []),
          ...(item.video?.bit_rate || []).flatMap(b => b.play_addr?.url_list || [])])]
          .filter(u => /^https?:\/\//.test(u));
        const p = { id, create_time: Number(item.create_time), desc: item.desc || '',
          author_sec_uid: item.author?.sec_uid || secUid, duration_ms: item.video?.duration,
          aweme_type: item.aweme_type, urls, video_meta: item.video,
          caption_fields: Object.fromEntries(Object.entries(item).filter(([key]) => /caption|subtitle/i.test(key))) };
        posts.set(id, p);
        if (inScope(p) && !catalogOnly) queue.push(p);
      }
      if (data.has_more === 0 || data.has_more === false) terminal = true;
      console.log('CATALOG', JSON.stringify({ pages: pageCount, count: posts.size, terminal }));
      checkpoint(); pump();
    } catch (e) { console.log('CATALOG_RESPONSE_ERROR', e.message.slice(0, 160)); }
  });
  console.log('LOGIN: Complete any normal Douyin login in the opened Chrome window. Collection starts automatically when the public post list loads.');
  await page.goto(profileUrl, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => console.log('NAVIGATION', e.message.slice(0, 120)));
  const deadline = Date.now() + 20 * 60 * 1000;
  let lastCount = -1, idleRounds = 0;
  while (!terminal && Date.now() < deadline) {
    await page.waitForTimeout(3000);
    if (!posts.size) continue; // allow the user to log in or complete site challenges
    if (posts.size === lastCount) idleRounds++; else idleRounds = 0;
    lastCount = posts.size;
    // Scroll only the public post list. This uses normal UI loading and site-generated requests.
    await page.evaluate(() => {
      const a = document.querySelector('a[href^="/video/"]');
      let el = a?.parentElement;
      while (el) {
        if (el.scrollHeight > el.clientHeight + 100 && /auto|scroll/.test(getComputedStyle(el).overflowY)) {
          el.scrollTop = el.scrollHeight; return;
        }
        el = el.parentElement;
      }
      window.scrollTo(0, document.documentElement.scrollHeight);
    });
    if (idleRounds === 15) console.log('WAITING_FOR_CATALOG: Post list stopped growing; check the browser for a login or verification prompt.');
    if (idleRounds > 60) break;
  }
  while ((queue.length || active) && Date.now() < deadline) await page.waitForTimeout(1000);
  stopping = true; checkpoint();
  console.log('FINISHED', JSON.stringify({ complete: terminal, posts: posts.size, downloaded: completed.size, failed: failures.length }));
  await context.close();
  if (!terminal || failures.length) process.exitCode = 2;
}
main().catch(error => { stopping = true; checkpoint(); console.error('STOPPED', error.message); process.exitCode = 1; });
