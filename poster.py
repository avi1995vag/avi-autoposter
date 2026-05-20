"""
Auto-Poster v3 — GitHub Actions Edition
========================================
Runs every 30 minutes via GitHub Actions (free, no server needed).
One Instagram page + One Facebook page.
Rotates through categories every 30 minutes: 6AM-10PM IST.

ONLY NEEDS ONE TOKEN: META_LONG_LIVED_TOKEN
Everything else is auto-fetched.
"""

import os, sys, json, re, time, urllib.parse, datetime
import requests
import pytz

IST = pytz.timezone('Asia/Kolkata')

# ─────────────────────────────────────────────────────────────
#  CREDENTIALS — only ONE token needed
# ─────────────────────────────────────────────────────────────
GEMINI_KEY          = os.environ['GEMINI_KEY']
CLOUDINARY_NAME     = os.environ['CLOUDINARY_NAME']
CLOUDINARY_PRESET   = os.environ['CLOUDINARY_PRESET']
META_TOKEN          = os.environ['META_TOKEN']   # Your Meta Long-Lived Access Token
IG_USER_ID          = os.environ['IG_USER_ID']   # Instagram Business Account ID

# These are auto-fetched from META_TOKEN at runtime
IG_PAGE_TOKEN = None
FB_PAGE_ID    = None
FB_PAGE_TOKEN = None

def setup_tokens():
    """Auto-fetch Page Token and FB Page ID from Meta Long-Lived Token."""
    global IG_PAGE_TOKEN, FB_PAGE_ID, FB_PAGE_TOKEN
    log('🔑 Fetching page tokens from Meta…')
    try:
        r = requests.get(
            f'https://graph.facebook.com/v21.0/me/accounts?access_token={META_TOKEN}',
            timeout=15
        )
        data = r.json()
        if 'error' in data:
            raise Exception(data['error']['message'])
        pages = data.get('data', [])
        if not pages:
            raise Exception('No Facebook Pages found on this token.')
        page = pages[0]
        FB_PAGE_ID    = page['id']
        FB_PAGE_TOKEN = page['access_token']
        IG_PAGE_TOKEN = FB_PAGE_TOKEN  # Page Token works for both IG and FB
        log(f'✅ FB Page: {page["name"]} (ID: {FB_PAGE_ID})')
        log(f'✅ Tokens ready')
        return True
    except Exception as e:
        log(f'❌ Token setup failed: {e}')
        return False

# ─────────────────────────────────────────────────────────────
#  CATEGORY ROTATION — different every 30 minutes
#  Slot 0 = 6:00AM, Slot 1 = 6:30AM, Slot 2 = 7:00AM, etc.
# ─────────────────────────────────────────────────────────────
CATEGORIES = [
    # Morning (6AM-9AM) — motivational + top news
    {'slot': 0,  'time': '06:00', 'type': 'motivation',  'topic': 'Morning Discipline'},
    {'slot': 1,  'time': '06:30', 'type': 'news',        'topic': 'India Top News'},
    {'slot': 2,  'time': '07:00', 'type': 'news',        'topic': 'Karnataka News'},
    {'slot': 3,  'time': '07:30', 'type': 'motivation',  'topic': 'Success Mindset'},
    {'slot': 4,  'time': '08:00', 'type': 'news',        'topic': 'Business & Economy'},
    {'slot': 5,  'time': '08:30', 'type': 'news',        'topic': 'Sports & Cricket'},
    {'slot': 6,  'time': '09:00', 'type': 'motivation',  'topic': 'Growth Mindset'},
    {'slot': 7,  'time': '09:30', 'type': 'news',        'topic': 'Technology & AI'},
    # Midday (10AM-1PM)
    {'slot': 8,  'time': '10:00', 'type': 'news',        'topic': 'Global News'},
    {'slot': 9,  'time': '10:30', 'type': 'motivation',  'topic': 'Focus & Productivity'},
    {'slot': 10, 'time': '11:00', 'type': 'news',        'topic': 'India Politics'},
    {'slot': 11, 'time': '11:30', 'type': 'news',        'topic': 'Bengaluru City News'},
    {'slot': 12, 'time': '12:00', 'type': 'motivation',  'topic': 'Leadership'},
    {'slot': 13, 'time': '12:30', 'type': 'news',        'topic': 'Entertainment & Cinema'},
    {'slot': 14, 'time': '13:00', 'type': 'news',        'topic': 'Health & Science'},
    {'slot': 15, 'time': '13:30', 'type': 'motivation',  'topic': 'Resilience'},
    # Afternoon (2PM-5PM)
    {'slot': 16, 'time': '14:00', 'type': 'news',        'topic': 'Karnataka Politics'},
    {'slot': 17, 'time': '14:30', 'type': 'news',        'topic': 'Sports Live Updates'},
    {'slot': 18, 'time': '15:00', 'type': 'motivation',  'topic': 'Hustle & Hard Work'},
    {'slot': 19, 'time': '15:30', 'type': 'news',        'topic': 'Business News'},
    {'slot': 20, 'time': '16:00', 'type': 'news',        'topic': 'India Breaking News'},
    {'slot': 21, 'time': '16:30', 'type': 'motivation',  'topic': 'Confidence'},
    {'slot': 22, 'time': '17:00', 'type': 'news',        'topic': 'Global Politics'},
    {'slot': 23, 'time': '17:30', 'type': 'news',        'topic': 'Technology News'},
    # Evening (6PM-10PM)
    {'slot': 24, 'time': '18:00', 'type': 'motivation',  'topic': 'Evening Reflection'},
    {'slot': 25, 'time': '18:30', 'type': 'news',        'topic': 'Cricket & IPL'},
    {'slot': 26, 'time': '19:00', 'type': 'news',        'topic': 'Karnataka Top Stories'},
    {'slot': 27, 'time': '19:30', 'type': 'motivation',  'topic': 'Never Give Up'},
    {'slot': 28, 'time': '20:00', 'type': 'news',        'topic': 'India Night Bulletin'},
    {'slot': 29, 'time': '20:30', 'type': 'motivation',  'topic': 'Gratitude'},
    {'slot': 30, 'time': '21:00', 'type': 'news',        'topic': 'Global Night News'},
    {'slot': 31, 'time': '21:30', 'type': 'motivation',  'topic': 'Tomorrow Preparation'},
    {'slot': 32, 'time': '22:00', 'type': 'motivation',  'topic': 'Night Wisdom'},
]

def get_current_slot():
    """Find which 30-minute slot we're in right now."""
    now = datetime.datetime.now(IST)
    h, m = now.hour, now.minute
    slot_time = h * 60 + (30 if m >= 30 else 0)
    start_time = 6 * 60  # 6:00 AM
    end_time = 22 * 60   # 10:00 PM

    if slot_time < start_time or slot_time > end_time:
        print(f"[Scheduler] Outside posting hours ({now.strftime('%H:%M')} IST). Exiting.")
        sys.exit(0)

    slot_index = (slot_time - start_time) // 30
    cat = CATEGORIES[slot_index % len(CATEGORIES)]
    print(f"[Scheduler] {now.strftime('%H:%M')} IST — Slot {slot_index}: {cat['type'].upper()} — {cat['topic']}")
    return cat

# ─────────────────────────────────────────────────────────────
#  LOGGER
# ─────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.datetime.now(IST).strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

# ─────────────────────────────────────────────────────────────
#  GEMINI AI — with retry on overload
# ─────────────────────────────────────────────────────────────
def gemini(prompt, use_search=True, attempt=1):
    time.sleep(3)
    body = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.85, 'maxOutputTokens': 4000}
    }
    if use_search:
        body['tools'] = [{'google_search': {}}]
    try:
        r = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}',
            json=body, timeout=90
        )
        data = r.json()
        if 'error' in data:
            code = data['error'].get('code', 0)
            msg  = data['error'].get('message', '')
            if (code == 429 or 'demand' in msg or 'quota' in msg) and attempt <= 4:
                wait = attempt * 20
                log(f'⚠ Gemini busy — waiting {wait}s (attempt {attempt}/4)…')
                time.sleep(wait)
                return gemini(prompt, use_search, attempt + 1)
            raise Exception(f"Gemini error: {msg}")
        raw = data['candidates'][0]['content']['parts'][0]['text']
        raw = re.sub(r'^```json\s*', '', raw.strip())
        raw = re.sub(r'```\s*$', '', raw.strip())
        start, end = raw.find('{'), raw.rfind('}')
        if start == -1 or end == -1:
            raise Exception("No JSON in response")
        return json.loads(raw[start:end+1])
    except json.JSONDecodeError:
        if attempt <= 2:
            log(f'⚠ JSON parse error — retrying…')
            time.sleep(10)
            return gemini(prompt, use_search, attempt + 1)
        raise Exception("Gemini returned invalid JSON")

# ─────────────────────────────────────────────────────────────
#  CONTENT GENERATORS
# ─────────────────────────────────────────────────────────────
IMG_RULE = ('imageQuery: EXACT FULL NAME + action + place + year in English. '
            'E.g. "Shubman Gill batting India vs England 2026". '
            'NEVER write "politician", "player", "leader", "person". '
            'Each slide different query.')

def gen_news(topic):
    lang = 'English'
    return gemini(f"""ELITE breaking news journalist. Search Google News RIGHT NOW.
Find the TOP 5-8 most important and DIFFERENT stories about: {topic}
LANGUAGE: {lang}. imageQuery always in English.

Return RAW JSON only — no markdown:
{{"caption":"Instagram caption with emojis and hashtags",
"slides":[{{"id":1,"layout":"magazine","title":"max 6 words","body":"20-25 words",
"category":"BREAKING|CRIME|POLITICS|ELECTION|HEALTH|SPORTS|ECONOMY|TECH|ENVIRONMENT|HUMAN INTEREST",
"ticker":"district/state/country","imageQuery":"person+action+year English"}}]}}

EXACTLY 10 SLIDES:
S1:magazine — overview hook title 6 words, body 20-25 words.
S2-9:news-card — ONE different story per slide. title 8 words, body 25 words.
  category: pick best match. ticker: specific location of THAT story.
  imageQuery: {IMG_RULE}
S10:cta — layout="cta"
NO duplicate stories. All different topics.""")

def gen_motivation(topic):
    now = datetime.datetime.now(IST)
    mood = ('morning energy' if now.hour < 10 else
            'midday focus' if now.hour < 14 else
            'afternoon drive' if now.hour < 18 else
            'evening reflection')
    return gemini(f"""Viral motivation content creator.
Topic: {topic}. Mood: {mood}. LANGUAGE: English.

Return RAW JSON only:
{{"caption":"motivational caption with emojis hashtags",
"slides":[{{"id":1,"layout":"cover","title":"6 powerful words","body":"20-25 words",
"category":"MOTIVATION","ticker":"theme","imageQuery":"motivational scene English"}}]}}

6 SLIDES:
S1:cover — powerful hook.
S2-4:split — quote + explanation, 20-25 words each.
S5:stats — 5 action points, 3-4 words each, separated by \\n.
S6:cta.
All English. imageQuery in English. Make it viral and emotional.""",
use_search=False)

# ─────────────────────────────────────────────────────────────
#  IMAGE PIPELINE — search + upload to Cloudinary
# ─────────────────────────────────────────────────────────────
BACKEND = 'https://avi-autoposter.onrender.com'  # your image search backend

def search_images(query):
    """Search for real images via your Render backend."""
    try:
        r = requests.get(
            f'{BACKEND}/api/search_image?q={urllib.parse.quote(query)}',
            timeout=30
        )
        return r.json().get('images', [])
    except Exception as e:
        log(f'  [IMG] Search error: {e}')
        return []

def upload_cloudinary(image_url):
    """Upload image URL to Cloudinary and return permanent CDN URL."""
    try:
        r = requests.post(
            f'https://api.cloudinary.com/v1_1/{CLOUDINARY_NAME}/image/upload',
            data={'file': image_url, 'upload_preset': CLOUDINARY_PRESET},
            timeout=45
        )
        d = r.json()
        if 'error' in d: raise Exception(d['error']['message'])
        return d['secure_url']
    except Exception as e:
        log(f'  [Cloudinary] {e}')
        return None

def get_slide_images(slides):
    """Get Cloudinary URLs for all slides."""
    urls = []
    for i, slide in enumerate(slides):
        query = slide.get('imageQuery', slide.get('title', 'news'))
        log(f'  [IMG] {i+1}/{len(slides)}: "{query}"')
        imgs = search_images(query)
        uploaded = None
        for img_url in imgs[:6]:
            try:
                proxy = f'{BACKEND}/api/proxy_image?url={urllib.parse.quote(img_url)}'
                cdn = upload_cloudinary(proxy)
                if cdn:
                    uploaded = cdn
                    log(f'  [IMG] ✅ Uploaded')
                    break
            except: continue
        if uploaded:
            urls.append(uploaded)
        else:
            log(f'  [IMG] ❌ No image for slide {i+1}')
    return urls

# ─────────────────────────────────────────────────────────────
#  INSTAGRAM POSTING
# ─────────────────────────────────────────────────────────────
def post_instagram(image_urls, caption):
    token   = IG_PAGE_TOKEN
    user_id = IG_USER_ID
    log(f'📸 Posting {len(image_urls)} slides to Instagram…')
    try:
        # Create item containers
        ids = []
        for url in image_urls[:10]:
            r = requests.post(
                f'https://graph.facebook.com/v21.0/{user_id}/media',
                data={'image_url': url, 'is_carousel_item': 'true', 'access_token': token},
                timeout=30
            )
            d = r.json()
            if 'error' in d: raise Exception(d['error']['message'])
            ids.append(d['id'])

        # Create carousel
        r2 = requests.post(
            f'https://graph.facebook.com/v21.0/{user_id}/media',
            data={'media_type': 'CAROUSEL', 'children': ','.join(ids),
                  'caption': caption, 'access_token': token},
            timeout=30
        )
        d2 = r2.json()
        if 'error' in d2: raise Exception(d2['error']['message'])

        # Wait for processing
        for _ in range(20):
            time.sleep(5)
            r3 = requests.get(
                f'https://graph.facebook.com/v21.0/{d2["id"]}?fields=status_code&access_token={token}',
                timeout=15
            )
            d3 = r3.json()
            if d3.get('status_code') == 'FINISHED': break
            if d3.get('status_code') == 'ERROR': raise Exception('Meta rejected carousel')

        # Publish
        r4 = requests.post(
            f'https://graph.facebook.com/v21.0/{user_id}/media_publish',
            data={'creation_id': d2['id'], 'access_token': token},
            timeout=30
        )
        d4 = r4.json()
        if 'error' in d4: raise Exception(d4['error']['message'])
        log(f'✅ Instagram posted! ID: {d4["id"]}')
        return True
    except Exception as e:
        log(f'❌ Instagram failed: {e}')
        return False

# ─────────────────────────────────────────────────────────────
#  FACEBOOK POSTING
# ─────────────────────────────────────────────────────────────
def post_facebook(image_urls, caption):
    page_id = FB_PAGE_ID
    token   = FB_PAGE_TOKEN
    log(f'📘 Posting {len(image_urls)} slides to Facebook…')
    try:
        photo_ids = []
        for url in image_urls[:10]:
            r = requests.post(
                f'https://graph.facebook.com/v21.0/{page_id}/photos',
                headers={'Content-Type': 'application/json'},
                json={'url': url, 'published': False, 'access_token': token},
                timeout=30
            )
            d = r.json()
            if 'error' in d: raise Exception(d['error']['message'])
            photo_ids.append(d['id'])

        r2 = requests.post(
            f'https://graph.facebook.com/v21.0/{page_id}/feed',
            headers={'Content-Type': 'application/json'},
            json={
                'message': caption[:2200],
                'attached_media': [{'media_fbid': pid} for pid in photo_ids],
                'access_token': token
            },
            timeout=30
        )
        d2 = r2.json()
        if 'error' in d2: raise Exception(d2['error']['message'])
        log(f'✅ Facebook posted! ID: {d2["id"]}')
        return True
    except Exception as e:
        log(f'❌ Facebook failed: {e}')
        return False

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    now = datetime.datetime.now(IST)
    log(f'🚀 Auto-Poster starting — {now.strftime("%Y-%m-%d %H:%M:%S IST")}')

    # Setup tokens from Meta Long-Lived Token
    if not setup_tokens():
        sys.exit(1)

    # Get current slot category
    cat = get_current_slot()
    log(f'📌 Category: {cat["type"].upper()} — {cat["topic"]}')

    # Generate content
    log('🤖 Generating content with Gemini…')
    try:
        if cat['type'] == 'news':
            content = gen_news(cat['topic'])
        else:
            content = gen_motivation(cat['topic'])
    except Exception as e:
        log(f'❌ Content generation failed: {e}')
        sys.exit(1)

    slides  = content.get('slides', [])
    caption = content.get('caption', f'Auto-post: {cat["topic"]}')
    log(f'✅ {len(slides)} slides generated')

    if not slides:
        log('❌ No slides generated. Exiting.')
        sys.exit(1)

    # Get images
    log('🔍 Fetching images…')
    image_urls = get_slide_images(slides)
    log(f'✅ {len(image_urls)} images ready')

    if len(image_urls) < 2:
        log('❌ Too few images. Exiting.')
        sys.exit(1)

    # Post to both platforms
    ig_ok = post_instagram(image_urls, caption)
    fb_ok = post_facebook(image_urls, caption)

    if ig_ok and fb_ok:
        log('🎉 Both platforms posted successfully!')
    elif ig_ok:
        log('⚠ Instagram only — Facebook failed')
    elif fb_ok:
        log('⚠ Facebook only — Instagram failed')
    else:
        log('❌ Both platforms failed')
        sys.exit(1)

if __name__ == '__main__':
    main()
