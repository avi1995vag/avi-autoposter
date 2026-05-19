"""
Auto-Poster Backend v19 — Full Resolution Images
=================================================
Core fix: Every CDN URL is rewritten to its MAXIMUM resolution version
before being returned. No more thumbnails.

CDN patterns handled:
- NDTV (c.ndtvimg.com): remove size suffix, get original
- TOI (static.toiimg.com): set width=1200
- IndiaToday (tosshub.com): remove size constraints
- BBC (ichef.bbci.co.uk): set to 1536 or 976 width
- Wikimedia: always 1200px
- Hindustan Times: remove resize params
- Zee News: remove size params
- Generic: detect and remove common resize query params
"""
import sys, re, time, hashlib, urllib.parse, io
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    try:
        import subprocess
        subprocess.check_call([sys.executable,'-m','pip','install','Pillow','--quiet'])
        from PIL import Image as PILImage
        HAS_PIL = True
    except:
        HAS_PIL = False

app = Flask(__name__)
CORS(app)  # Open — app is self-hosted on Render

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-IN,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
}

MIN_W, MIN_H = 500, 350

# ─────────────────────────────────────────────────────────────
#  FULL-RES URL CONVERTER
#  This is the KEY function — converts any thumbnail URL to full-size
# ─────────────────────────────────────────────────────────────
def to_fullres(url):
    """Convert CDN thumbnail URL to full-resolution version."""
    if not url: return url
    u = url

    # ── NDTV: c.ndtvimg.com ──────────────────────────────────
    # Thumb: https://c.ndtvimg.com/2026-05/abc_650x400_81716045678.jpg
    # Full:  https://c.ndtvimg.com/2026-05/abc.jpg
    if 'c.ndtvimg.com' in u:
        # Remove _WxH_timestamp suffix before extension
        u = re.sub(r'_\d+x\d+_\d+(\.\w+)$', r'\1', u)
        # Remove query params
        u = u.split('?')[0]
        return u

    # ── Times of India: static.toiimg.com ───────────────────
    # Thumb: https://static.toiimg.com/photo/msid-123,width-96,height-65.cms
    # Full:  https://static.toiimg.com/photo/msid-123,width-1200,height-900,resizemode-75.cms
    if 'static.toiimg.com' in u:
        u = re.sub(r'width-\d+', 'width-1200', u)
        u = re.sub(r'height-\d+', 'height-900', u)
        if 'width-' not in u:
            u = u.replace('.cms', ',width-1200,height-900,resizemode-75.cms')
        # Also handle /thumb/ path
        u = u.replace('/thumb/', '/photo/')
        return u

    # ── IndiaToday: tosshub.com ──────────────────────────────
    # Thumb: https://akm-img-a-in.tosshub.com/indiatoday/images/story/202605/abc-sixteen_nine_220.jpg
    # Full:  https://akm-img-a-in.tosshub.com/indiatoday/images/story/202605/abc-sixteen_nine.jpg
    if 'tosshub.com' in u:
        # Remove size suffix like _220, _660, _1200x675
        u = re.sub(r'[-_]\d+x\d+(\.\w+)$', r'\1', u)
        u = re.sub(r'[-_]\d{2,4}(\.\w+)$', r'\1', u)
        # Remove query params
        u = u.split('?')[0]
        return u

    # ── BBC: ichef.bbci.co.uk ────────────────────────────────
    # Thumb: https://ichef.bbci.co.uk/news/320/cpsprodpb/abc.jpg
    # Full:  https://ichef.bbci.co.uk/news/1536/cpsprodpb/abc.jpg
    if 'ichef.bbci.co.uk' in u:
        u = re.sub(r'/news/\d+/', '/news/1536/', u)
        u = re.sub(r'/ace/standard/\d+/', '/ace/standard/1536/', u)
        return u

    # ── Wikimedia ────────────────────────────────────────────
    # Thumb: https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/File.jpg/320px-File.jpg
    # Full:  https://upload.wikimedia.org/wikipedia/commons/a/ab/File.jpg
    if 'upload.wikimedia.org' in u:
        # Convert thumb URL to direct URL
        m = re.match(r'(https://upload\.wikimedia\.org/wikipedia/commons)/thumb/(.+)/\d+px-[^/]+$', u)
        if m:
            return f'{m.group(1)}/{m.group(2)}'
        # Already a /\d+px- URL — bump to 1200px
        u = re.sub(r'/\d+px-', '/1200px-', u)
        return u

    # ── Hindustan Times ──────────────────────────────────────
    if 'hindustantimes.com' in u:
        # Remove resize query params
        u = re.sub(r'\?.*$', '', u)
        return u

    # ── Zee News ─────────────────────────────────────────────
    if 'zeenews.com' in u or 'cdn.zeenews' in u:
        u = re.sub(r'\?.*$', '', u)
        u = re.sub(r'_\d+x\d+(\.\w+)$', r'\1', u)
        return u

    # ── News18 ───────────────────────────────────────────────
    if 'news18.com' in u or 'images.news18' in u:
        u = re.sub(r'[?&]w=\d+', '', u)
        u = re.sub(r'[?&]h=\d+', '', u)
        u = re.sub(r'_\d+x\d+(\.\w+)', r'\1', u)
        return u

    # ── Generic: remove common resize query params ────────────
    # width=, w=, height=, h=, size=, quality=, q=, resize=
    has_resize = re.search(r'[?&](width|w|height|h|size|resize|thumbnail|thumb)=\d+', u, re.I)
    if has_resize:
        # Keep URL but remove resize params (get original size)
        parsed = urllib.parse.urlparse(u)
        params = urllib.parse.parse_qs(parsed.query)
        # Remove size-related params
        for key in ['width','w','height','h','size','resize','thumbnail','thumb','quality','q']:
            params.pop(key, None)
            params.pop(key.upper(), None)
        new_query = urllib.parse.urlencode({k: v[0] for k,v in params.items()})
        u = urllib.parse.urlunparse(parsed._replace(query=new_query))

    return u

# ── URL filter ────────────────────────────────────────────────
BAD = [
    'instagram.png','googlestore.png','applestore.png','androidtv-app',
    'playstore','appstore','facebook.png','twitter.png','youtube.png',
    'whatsapp.png','telegram.png','linkedin.png','pinterest.png',
    '/resources/img/', 'tosshub.com/sites/indiatoday/resources',
    'default-690','default.jpg','default.png','placeholder','no-image',
    'no_image','noimage','blank.','spacer','1x1','transparent',
    'shutterstock','gettyimages','istock','alamy','freepik',
    'logo.png','logo.jpg','/icon.','/icons/','favicon',
    'social-share','twitter_card','beacon','tracking','analytics',
    'app-download', 'googleadservices','doubleclick',
]

def ok(url):
    if not url or not url.startswith('http'): return False
    low = url.lower()
    if not re.search(r'\.(jpg|jpeg|png|webp)(\?|$|#|&)', low): return False
    if any(b in low for b in BAD): return False
    fname = url.split('/')[-1].split('?')[0]
    if len(fname) < 6: return False
    return True

GOOD_CDNS = [
    'c.ndtvimg.com', 'static.toiimg.com',
    'akm-img-a-in.tosshub.com/indiatoday/',
    'smedia2.intoday.in', 'ichef.bbci.co.uk',
    'upload.wikimedia.org/wikipedia',
    'images.hindustantimes.com','images.news18.com',
    'img.etimg.com','english.cdn.zeenews.com',
    'thehindu.com','scroll.in','thewire.in',
]

def cdn_score(url):
    low = url.lower()
    for i, cdn in enumerate(GOOD_CDNS):
        if cdn in low: return 100 - i
    return 5

def dedup_sort(urls, n=12):
    seen = set(); out = []
    for u in urls:
        u2 = to_fullres(u)
        if u2 not in seen and ok(u2): seen.add(u2); out.append(u2)
    out.sort(key=cdn_score, reverse=True)
    return out[:n]

def add_u(dest, src):
    for u in src:
        u2 = to_fullres(u)
        if u2 not in dest and ok(u2): dest.append(u2)

# ── Dimension check ───────────────────────────────────────────
def passes_dimension(url, min_w=MIN_W, min_h=MIN_H):
    if not HAS_PIL: return True
    try:
        parsed = urllib.parse.urlparse(url)
        ref = f'{parsed.scheme}://{parsed.netloc}/'
        h = {'User-Agent': HEADERS['User-Agent'], 'Referer': ref, 'Accept': 'image/*'}
        r = requests.get(url, headers=h, timeout=12, stream=True)
        if r.status_code != 200:
            print(f'  [Dim] HTTP {r.status_code} — {url[:60]}')
            return False
        data = b''
        for chunk in r.iter_content(8192):
            data += chunk
            if len(data) > 524288: break  # read up to 512KB
        img = PILImage.open(io.BytesIO(data))
        w, h2 = img.size
        ok2 = w >= min_w and h2 >= min_h
        print(f'  [Dim] {w}x{h2} {"✅" if ok2 else "❌ SMALL"} — {url[:70]}')
        return ok2
    except Exception as e:
        print(f'  [Dim] Error ({e}) — accepting {url[:60]}')
        return True  # accept on error rather than reject

# ── HTML image extractor ──────────────────────────────────────
def extract_imgs(html, base=''):
    og, other = [], []

    # og:image / twitter:image — highest priority
    for pat in [
        r'<meta[^>]+(?:og:image|twitter:image)[^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:og:image|twitter:image)',
        r'"og:image"\s*content=["\']([^"\']+)["\']',
    ]:
        for m in re.findall(pat, html, re.I): og.append(m)

    # JSON-LD
    for m in re.findall(
        r'"(?:image|photo|thumbnail)"\s*:\s*"?(https?://[^">\s,\]]+\.(?:jpg|jpeg|png|webp)(?:\?[^">\s,\]]*)?)"?',
        html, re.I): other.append(m)

    # src / data-src
    for m in re.findall(
        r'(?:src|data-src|data-lazy-src|data-original|data-img-src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?)["\']',
        html, re.I): other.append(m)

    def fix(u):
        u = u.strip()
        if u.startswith('//'): u = 'https:' + u
        elif u.startswith('/') and base: u = base.rstrip('/') + u
        return to_fullres(u)

    out_og = [fix(u) for u in og if ok(fix(u))]
    out_other = [fix(u) for u in other if ok(fix(u))]
    return out_og + out_other  # og:image always first

# ── SOURCES ──────────────────────────────────────────────────

def from_article(url):
    if not url: return []
    try:
        m = re.match(r'(https?://[^/]+)', url)
        base = m.group(1) if m else ''
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        imgs = extract_imgs(r.text, base)
        result = dedup_sort(imgs, 4)
        print(f'[Article] {len(result)} — {url[:70]}')
        return result
    except Exception as e:
        print(f'[Article] {e}'); return []

def from_google_news_rss(query):
    try:
        enc = urllib.parse.quote(query)
        r = requests.get(
            f'https://news.google.com/rss/search?q={enc}&hl=en-IN&gl=IN&ceid=IN:en',
            headers=HEADERS, timeout=10)
        items = re.findall(r'<item>(.*?)</item>', r.text, re.S)
        urls = []
        for item in items[:6]:
            lk = re.search(r'<link>(https?://(?!news\.google)[^<]+)</link>', item)
            gd = re.search(r'<guid[^>]*>(https?://(?!news\.google)[^<]+)</guid>', item)
            u = lk or gd
            if u: urls.append(u.group(1))
        imgs = []
        for u in urls[:5]:
            add_u(imgs, from_article(u))
            if len(imgs) >= 6: break
        print(f'[GNewsRSS] {len(imgs)} from {len(urls)} articles')
        return imgs[:6]
    except Exception as e:
        print(f'[GNewsRSS] {e}'); return []

def from_ndtv(query):
    try:
        r = requests.get(f'https://www.ndtv.com/search?searchtext={urllib.parse.quote(query)}',
                         headers=HEADERS, timeout=10)
        imgs = [to_fullres(u) for u in extract_imgs(r.text, 'https://www.ndtv.com')
                if 'c.ndtvimg.com' in u or 'ndtv.com/cue' in u]
        imgs = dedup_sort(imgs, 5)
        print(f'[NDTV] {len(imgs)}')
        return imgs
    except Exception as e: print(f'[NDTV] {e}'); return []

def from_toi(query):
    try:
        slug = urllib.parse.quote(query.lower().replace(' ','-'))
        r = requests.get(f'https://timesofindia.indiatimes.com/topic/{slug}',
                         headers=HEADERS, timeout=10)
        imgs = [to_fullres(u) for u in extract_imgs(r.text)
                if 'static.toiimg.com' in u]
        imgs = dedup_sort(imgs, 5)
        print(f'[TOI] {len(imgs)}')
        return imgs
    except Exception as e: print(f'[TOI] {e}'); return []

def from_indiatoday(query):
    try:
        r = requests.get(f'https://www.indiatoday.in/search/{urllib.parse.quote(query)}',
                         headers=HEADERS, timeout=10)
        imgs = []
        for u in extract_imgs(r.text):
            low = u.lower()
            if ('akm-img-a-in.tosshub.com/indiatoday/' in low
                    and '/resources/' not in low
                    and 'default' not in low):
                imgs.append(to_fullres(u))
            elif 'smedia2.intoday.in' in low:
                imgs.append(u)
        imgs = dedup_sort(imgs, 5)
        print(f'[IndiaToday] {len(imgs)}')
        return imgs
    except Exception as e: print(f'[IndiaToday] {e}'); return []

def from_bbc(query):
    try:
        r = requests.get(f'https://www.bbc.com/search?q={urllib.parse.quote(query)}',
                         headers=HEADERS, timeout=10)
        imgs = [to_fullres(u) for u in extract_imgs(r.text)
                if 'ichef.bbci.co.uk' in u]
        imgs = dedup_sort(imgs, 4)
        print(f'[BBC] {len(imgs)}')
        return imgs
    except Exception as e: print(f'[BBC] {e}'); return []

def from_wikimedia(query):
    try:
        r = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action':'query','list':'search','srsearch':query,'srlimit':3,'format':'json'}, timeout=8)
        res = r.json().get('query',{}).get('search',[])
        if not res: return []
        title = res[0]['title']
        r2 = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action':'query','titles':title,'prop':'images|pageimages',
            'imlimit':10,'pithumbsize':2000,'format':'json'}, timeout=8)
        pages = r2.json().get('query',{}).get('pages',{})
        urls = []
        SKIP = ['flag','logo','icon','map','coat','emblem','symbol','seal',
                'signature','question','commons-logo','wikimedia','wikipedia',
                'wikidata','edit-ltr','pictogram','pictograph']
        for page in pages.values():
            thumb = page.get('thumbnail',{}).get('source','')
            if thumb:
                full = to_fullres(thumb)  # converts thumb path to direct path
                if ok(full): urls.append(full)
            for img in page.get('images',[]):
                t = img.get('title','')
                tl = t.lower()
                if not any(x in tl for x in ['.jpg','.jpeg','.png','.webp']): continue
                if any(s in tl for s in SKIP): continue
                fname = t.replace('File:','').replace(' ','_')
                md5 = hashlib.md5(fname.encode()).hexdigest()
                wu = f'https://upload.wikimedia.org/wikipedia/commons/{md5[0]}/{md5[0:2]}/{urllib.parse.quote(fname)}'
                if wu not in urls and ok(wu): urls.append(wu)
            if len(urls) >= 4: break
        print(f'[Wikimedia] {len(urls)}')
        return urls[:4]
    except Exception as e: print(f'[Wikimedia] {e}'); return []

def from_google_images(query):
    results = []
    G = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
        'Cookie': 'CONSENT=YES+cb; SOCS=CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyoBg'
    }
    for suffix in ['', ' news 2026']:
        try:
            q = urllib.parse.quote(query + suffix)
            # isz:l = large images only
            r = requests.get(
                f'https://www.google.com/search?q={q}&tbm=isch&tbs=itp:photo,isz:l&hl=en&gl=IN',
                headers=G, timeout=12)
            raw = r.text
            found = []
            found += re.findall(r'\["(https?://[^"\\]+\.(?:jpg|jpeg|png|webp))",\d+,\d+\]', raw, re.I)
            found += re.findall(r'"ou":"(https?://[^"\\]+\.(?:jpg|jpeg|png|webp))"', raw, re.I)
            found += re.findall(r'imgurl=(https?://[^&"]+\.(?:jpg|jpeg|png|webp))', raw, re.I)
            for u in found:
                u2 = urllib.parse.unquote(u.split('\\')[0])
                u2 = to_fullres(u2)
                if 'gstatic' not in u2 and 'google.com' not in u2 and ok(u2):
                    results.append(u2)
            print(f'[GoogleImg] {len(results)} for: {query+suffix}')
            if len(results) >= 6: break
            time.sleep(0.4)
        except Exception as e: print(f'[GoogleImg] {e}')
    return dedup_sort(results, 6)

# ── MASTER ───────────────────────────────────────────────────
def find_images(query, article_url=''):
    """
    Find images fast — NO blocking dimension check.
    Return candidates scored by CDN quality.
    Dimension check removed: it caused 30s+ timeouts → HTTP 502.
    Quality is ensured by CDN scoring and BAD URL filtering instead.
    """
    candidates = []
    print(f'\n{"━"*55}\n[Search] "{query}"\n{"━"*55}')
    try:
        if article_url:
            add_u(candidates, from_article(article_url))
            print(f'  After Article:    {len(candidates)}')

        if len(candidates) < 3:
            add_u(candidates, from_google_news_rss(query))
            print(f'  After GNewsRSS:   {len(candidates)}')

        if len(candidates) < 3:
            add_u(candidates, from_ndtv(query))
            print(f'  After NDTV:       {len(candidates)}')

        if len(candidates) < 3:
            add_u(candidates, from_toi(query))
            print(f'  After TOI:        {len(candidates)}')

        if len(candidates) < 3:
            add_u(candidates, from_indiatoday(query))
            print(f'  After IndiaToday: {len(candidates)}')

        if len(candidates) < 3:
            add_u(candidates, from_bbc(query))
            print(f'  After BBC:        {len(candidates)}')

        if len(candidates) < 3:
            add_u(candidates, from_google_images(query))
            print(f'  After GoogleImg:  {len(candidates)}')

        if len(candidates) < 2:
            add_u(candidates, from_wikimedia(query))
            print(f'  After Wikimedia:  {len(candidates)}')

    except Exception as e:
        print(f'[find_images] Error: {e}')

    final = dedup_sort(candidates, 12)
    print(f'  ✅ FINAL: {len(final)} images\n')
    return final

# ── ROUTES ───────────────────────────────────────────────────

@app.route('/')
def serve_index():
    """Serve the main app directly from Render — no separate hosting needed."""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except FileNotFoundError:
        return '<h2>index.html not found — upload it to your GitHub repo.</h2>', 404

@app.errorhandler(Exception)
def handle_exception(e):
    print(f'[GLOBAL ERROR] {e}')
    return jsonify({'error': str(e), 'images': []}), 200  # return 200 not 502

@app.route('/api/rss')
def proxy_rss():
    url = request.args.get('url','')
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        return Response(r.content, mimetype='text/xml')
    except Exception as e:
        return jsonify({'error':str(e)}), 200

@app.route('/api/search_image')
def search_image():
    try:
        query       = request.args.get('q','').strip()
        article_url = request.args.get('article_url','').strip()
        if not query:
            return jsonify({'images':[],'error':'No query'}), 200
        imgs = find_images(query, article_url)
        return jsonify({'images':imgs,'count':len(imgs),'query':query})
    except Exception as e:
        print(f'[search_image] ERROR: {e}')
        return jsonify({'images':[],'error':str(e),'count':0}), 200

@app.route('/api/proxy_image')
def proxy_image():
    url = request.args.get('url','').strip()
    if not url: return jsonify({'error':'No URL'}), 400
    try:
        parsed = urllib.parse.urlparse(url)
        ref = f'{parsed.scheme}://{parsed.netloc}/'
        h = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
            'Referer': ref,
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-IN,en;q=0.9',
        }
        r = requests.get(url, headers=h, timeout=20)
        if r.status_code != 200:
            return jsonify({'error':f'HTTP {r.status_code}'}), r.status_code
        excl = {'content-encoding','transfer-encoding','connection','keep-alive'}
        hdrs = [(k,v) for k,v in r.headers.items() if k.lower() not in excl]
        hdrs.append(('Access-Control-Allow-Origin','*'))
        hdrs.append(('Cache-Control','public, max-age=3600'))
        return Response(r.content, 200, hdrs,
                        content_type=r.headers.get('Content-Type','image/jpeg'))
    except Exception as e:
        print(f'[Proxy] Error: {e} — {url[:80]}')
        return jsonify({'error':str(e)}), 500

@app.route('/api/test')
def test():
    q = request.args.get('q','VD Satheesan sworn in Kerala Chief Minister 2026')
    imgs = find_images(q)
    html = f'<h2>"{q}" → {len(imgs)} full-res images</h2>'
    html += f'<p>Pillow installed: {HAS_PIL} | Min size: {MIN_W}x{MIN_H}px</p>'
    for u in imgs:
        p = f'/api/proxy_image?url={urllib.parse.quote(u)}'
        html += (f'<div style="display:inline-block;margin:8px;border:2px solid green;padding:4px;vertical-align:top;max-width:340px">'
                 f'<img src="{p}" style="max-width:330px;display:block">'
                 f'<small style="word-break:break-all;color:#555;font-size:10px">{u}</small></div>')
    return html

@app.route('/api/topics', methods=['GET'])
def get_topics():
    """View current weekly motivation topics."""
    try:
        from scheduler import WEEKLY_TOPICS, get_todays_topic
        return jsonify({'topics': WEEKLY_TOPICS, 'today': get_todays_topic()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/topics', methods=['POST'])
def set_topics():
    """Update weekly topics. Body: {week: 1, topics: ['topic1','topic2',...]}"""
    try:
        from scheduler import update_topics
        data = request.json
        update_topics(data['week'], data['topics'])
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs')
def get_logs():
    """View last 100 lines of scheduler log."""
    try:
        with open('scheduler.log','r',encoding='utf-8') as f:
            lines = f.readlines()[-100:]
        return '<pre style="background:#111;color:#0f0;padding:20px;font-size:12px">' + ''.join(lines) + '</pre>'
    except:
        return '<pre>No logs yet.</pre>'

@app.route('/api/post_now', methods=['POST'])
def post_now():
    """Manually trigger a post. Body: {page: 'EN_NEWS|KN_NEWS|EN_MOTI|KN_MOTI', type: 'deepdive|top10|motivation'}"""
    try:
        from scheduler import EN_NEWS, KN_NEWS, EN_MOTI, KN_MOTI
        from scheduler import gen_deepdive, gen_top10, gen_motivation, do_post
        data = request.json
        pages = {'EN_NEWS':EN_NEWS,'KN_NEWS':KN_NEWS,'EN_MOTI':EN_MOTI,'KN_MOTI':KN_MOTI}
        page = pages.get(data.get('page','EN_NEWS'))
        ptype = data.get('type','deepdive')
        cat   = data.get('category','India')
        if ptype == 'deepdive':
            content = gen_deepdive(page)
        elif ptype == 'top10':
            content = gen_top10(page, cat)
        else:
            content = gen_motivation(page)
        do_post(page, content, ptype)
        return jsonify({'ok': True, 'headline': content.get('headline', content.get('caption',''))[:100]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    try: import flask, flask_cors
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable,'-m','pip','install','flask','flask-cors','requests','Pillow'])
    import os
    
    # Start auto-posting scheduler in background
    try:
        from scheduler import start_scheduler
        start_scheduler()
        print('📅 Auto-scheduler started successfully')
    except Exception as e:
        print(f'⚠ Scheduler not started: {e}')

    port = int(os.environ.get('PORT', 5000))
    print(f'🚀 Backend running on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
