import os
import re
import html
import time
import hmac
import math
import base64
import random
import hashlib
import logging
import threading
import concurrent.futures

import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kp-travel")

# ==========================================
# 🔑 กุญแจ API  (อ่านจาก Environment ก่อน ถ้าไม่มีค่อย fallback)
#   แนะนำให้ตั้งค่าผ่าน env เพื่อไม่ให้คีย์รั่ว:
#   export GEMINI_API_KEY="..."  /  export GOOGLE_MAPS_API_KEY="..."
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAuI1Bwe2q1n9Op07LGaJ1S__gV2xGXJTs")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "AIzaSyBAH1v4IWIelgzE6iprX7lzVL6-SCtf6hk")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

# 🟢 LINE Messaging API (ตั้งค่าใน Render env: LINE_CHANNEL_ACCESS_TOKEN / LINE_CHANNEL_SECRET)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_HISTORY = {}  # เก็บประวัติแชทต่อ user (ในหน่วยความจำ)

# พิกัดกลางเมืองกำแพงเพชร ใช้เป็นค่า default ปลอดภัย
DEFAULT_LAT = "16.4828"
DEFAULT_LNG = "99.5227"

# จำกัดจำนวนวันสูงสุด กันการยิง prompt ใหญ่เกินเหตุ
MAX_DAYS = 7

API_CACHE = {}
GEO_CACHE = {}

FALLBACK_MAIN = """
- อุทยานประวัติศาสตร์กำแพงเพชร (⭐ 4.6) | พิกัด: 16.4928, 99.5153
- วัดพระบรมธาตุ กำแพงเพชร (⭐ 4.7) | พิกัด: 16.4891, 99.5175
- ศาลหลักเมืองกำแพงเพชร (⭐ 4.5) | พิกัด: 16.4872, 99.5168
- พิพิธภัณฑสถานแห่งชาติ กำแพงเพชร (⭐ 4.3) | พิกัด: 16.4865, 99.5155
- ตลาดย้อนยุคนครชุม (⭐ 4.4) | พิกัด: 16.4851, 99.5103
- สระน้ำมนต์ (⭐ 4.0) | พิกัด: 16.4940, 99.5160
- วัดช้างรอบ (⭐ 4.5) | พิกัด: 16.4995, 99.5120
- วัดพระสี่อิริยาบถ (⭐ 4.6) | พิกัด: 16.4975, 99.5140
"""

FALLBACK_NATURE = """
- อุทยานแห่งชาติน้ำตกคลองลาน (⭐ 4.8) | พิกัด: 16.1303, 99.2811
- จุดชมวิวช่องเย็น อุทยานแห่งชาติแม่วงก์ (⭐ 4.7) | พิกัด: 16.0991, 99.1068
- บ่อน้ำพุร้อนพระร่วง (⭐ 4.2) | พิกัด: 16.3216, 99.6648
- น้ำตกคลองน้ำไหล (⭐ 4.5) | พิกัด: 16.1604, 99.2555
- อุทยานแห่งชาติคลองวังเจ้า (⭐ 4.6) | พิกัด: 16.3768, 99.2312
- แก่งเกาะร้อย (⭐ 4.3) | พิกัด: 16.2050, 99.2900
"""

FALLBACK_FOOD = """
- บะหมี่ชากังราว (⭐ 4.3) | พิกัด: 16.4855, 99.5230
- ร้านอาหารครัวเห็ดโคน (⭐ 4.2) | พิกัด: 16.4815, 99.5210
- คาเฟ่ เฌอแตม กำแพงเพชร (⭐ 4.4) | พิกัด: 16.4880, 99.5250
- ร้านผัดไทยนครชุม (⭐ 4.5) | พิกัด: 16.4840, 99.5110
- กาแฟบ้านย่า กำแพงเพชร (⭐ 4.6) | พิกัด: 16.4820, 99.5200
- กินเตี๋ยว ดูสวน (⭐ 4.2) | พิกัด: 16.4800, 99.5150
- สวนอาหารขวัญข้าว (⭐ 4.3) | พิกัด: 16.4755, 99.5280
- เต้าฮวย นมสด (ร้านลับ) (⭐ 4.4) | พิกัด: 16.4860, 99.5180
"""

FALLBACK_HOTEL = """
- โรงแรมชากังราว ริเวอร์วิว (⭐ 4.1) | พิกัด: 16.4811, 99.5222
- นวรัตน์ เฮอริเทจ โฮเทล (⭐ 4.2) | พิกัด: 16.4830, 99.5255
- พี พาราไดซ์ โฮเต็ล (⭐ 4.3) | พิกัด: 16.4785, 99.5280
- ซีนิค ริเวอร์ไซด์ รีสอร์ท (⭐ 4.4) | พิกัด: 16.4750, 99.5300
- ไม้กะพยอม รีสอร์ท (⭐ 4.0) | พิกัด: 16.4850, 99.5150
"""

KNOWN_LOCATIONS = {
    "ตัวเมืองกำแพงเพชร": ("16.4828", "99.5227"),
    "อุทยานประวัติศาสตร์": ("16.4928", "99.5153"),
    "น้ำตกคลองลาน": ("16.1303", "99.2811"),
    "ช่องเย็น": ("16.0991", "99.1068"),
    "แม่วงก์": ("16.0991", "99.1068"),
    "บ่อน้ำพุร้อนพระร่วง": ("16.3216", "99.6648"),
    "ตลาดย้อนยุคนครชุม": ("16.4851", "99.5103"),
}


# ------------------------------------------------------------------
# Helper ทั่วไป
# ------------------------------------------------------------------
def safe_int(value, default=0):
    """แปลงเป็น int แบบไม่พังเด็ดขาด"""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def coords_str_to_tuple(s):
    """แปลง 'lat, lng' เป็น tuple (lat, lng) แบบ string"""
    m = re.findall(r'(-?\d+\.\d+)', s or "")
    return (m[0], m[1]) if len(m) >= 2 else None


def parse_db_coords(*blocks):
    """สร้าง lookup {ชื่อสถานที่: (lat, lng)} จากฐานข้อมูลสถานที่จริง"""
    lookup = {}
    for block in blocks:
        for line in (block or "").splitlines():
            m = re.search(r'-\s*(.+?)\s*\(.*?พิกัด:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', line)
            if m:
                lookup[m.group(1).strip()] = (m.group(2), m.group(3))
    return lookup


def _norm_name(s):
    """ตัดคำนำหน้า/วงเล็บ/เว้นวรรค เพื่อเทียบชื่อให้ยืดหยุ่นขึ้น"""
    s = s or ""
    s = re.sub(r'^\s*(จุดเริ่มต้น|จุดสิ้นสุด|เริ่มต้น|สิ้นสุด)\s*[:：\-]\s*', '', s)
    s = re.sub(r'\(.*?\)', '', s)        # ตัดวงเล็บ เช่น (ร้านลับ)
    s = re.sub(r'[\s\u200b\.\,]+', '', s)  # ตัดเว้นวรรค/จุด/จุลภาค
    return s.strip().lower()


def match_real_coords(name, lookup):
    """จับคู่ชื่อสถานที่กับพิกัดจริงในฐานข้อมูล (เทียบแบบ normalize + substring + คำสำคัญ)"""
    if not name:
        return None
    n = name.strip()
    if n in lookup:
        return lookup[n]
    nn = _norm_name(n)
    if not nn:
        return None
    # 1) normalize + substring สองทาง
    for key, coords in lookup.items():
        kn = _norm_name(key)
        if kn and (kn == nn or kn in nn or nn in kn):
            return coords
    # 2) fallback: แชร์ "คำสำคัญ" (ยาว >= 4 ตัวอักษร) ร่วมกัน
    name_words = [w for w in re.split(r'[\s\(\)\.,:：\-]+', n) if len(w) >= 4]
    for key, coords in lookup.items():
        for w in name_words:
            if w and w in key:
                return coords
    return None


def extract_gemini_text(data):
    """
    ดึงข้อความจากผลลัพธ์ Gemini อย่างปลอดภัย
    คืน None ถ้าไม่มีเนื้อหา (เช่น โดน safety block หรือคำตอบโดนตัดเพราะ MAX_TOKENS)
    """
    try:
        candidates = data.get("candidates") or []
        if not candidates:
            logger.warning("Gemini: ไม่มี candidates (อาจโดน block) -> %s", data.get("promptFeedback"))
            return None

        first = candidates[0] or {}
        finish_reason = first.get("finishReason")
        parts = ((first.get("content") or {}).get("parts")) or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
        text = "".join(texts).strip()

        if not text:
            logger.warning("Gemini: ตอบกลับว่างเปล่า (finishReason=%s)", finish_reason)
            return None
        return text
    except (AttributeError, IndexError, TypeError) as e:
        logger.warning("Gemini: parse ไม่สำเร็จ: %s", e)
        return None


def call_gemini(prompt=None, contents=None, system_instruction=None,
                max_tokens=8192, temperature=0.6, timeout=60, retries=2):
    """
    เรียก Gemini พร้อม retry + จับ error เฉพาะทาง
    - ส่ง prompt (ข้อความเดียว) หรือ contents (บทสนทนาหลายตา) อย่างใดอย่างหนึ่ง
    - system_instruction: บทบาท/กฎของผู้ช่วย (ไม่ปนกับข้อความผู้ใช้)
    คืนข้อความ (str) ถ้าสำเร็จ, คืน None ถ้าล้มเหลวทุกครั้ง
    """
    if contents is None:
        contents = [{"parts": [{"text": prompt or ""}]}]

    payload = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    headers = {"Content-Type": "application/json"}

    for attempt in range(retries + 1):
        try:
            resp = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                text = extract_gemini_text(resp.json())
                if text:
                    return text
                # ตอบ 200 แต่ไม่มีเนื้อหา -> ลองใหม่อีกครั้ง
                logger.warning("Gemini 200 แต่ไม่มีข้อความ (รอบที่ %s)", attempt + 1)
            else:
                logger.warning("Gemini HTTP %s (รอบที่ %s): %s",
                               resp.status_code, attempt + 1, resp.text[:200])
        except requests.exceptions.Timeout:
            logger.warning("Gemini timeout (รอบที่ %s)", attempt + 1)
        except requests.exceptions.RequestException as e:
            logger.warning("Gemini network error (รอบที่ %s): %s", attempt + 1, e)
        except ValueError as e:  # resp.json() พัง
            logger.warning("Gemini JSON ผิดรูป (รอบที่ %s): %s", attempt + 1, e)

        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))  # exponential backoff เบาๆ

    return None


def parse_location(loc_str):
    loc_str = (loc_str or "").strip()
    if not loc_str:
        return "ตัวเมืองกำแพงเพชร", f"{DEFAULT_LAT}, {DEFAULT_LNG}"

    coord_match = re.search(r'(-?\d+\.\d+),\s*(-?\d+\.\d+)', loc_str)
    if coord_match:
        return loc_str, f"{coord_match.group(1)}, {coord_match.group(2)}"

    for key, coords in KNOWN_LOCATIONS.items():
        if key in loc_str:
            return loc_str, f"{coords[0]}, {coords[1]}"

    lat, lng = geocode_location(loc_str)
    if lat is not None and lng is not None:
        return loc_str, f"{lat}, {lng}"

    return loc_str, f"{DEFAULT_LAT}, {DEFAULT_LNG}"


def geocode_location(location_name):
    if location_name in GEO_CACHE:
        return GEO_CACHE[location_name]
    url = (f"https://maps.googleapis.com/maps/api/geocode/json"
           f"?address={location_name}&key={GOOGLE_MAPS_API_KEY}&language=th")
    try:
        response = requests.get(url, timeout=3)
        data = response.json()
        if data.get('status') == 'OK' and data.get('results'):
            loc = data['results'][0]['geometry']['location']
            lat, lng = loc['lat'], loc['lng']
            GEO_CACHE[location_name] = (lat, lng)
            return lat, lng
    except (requests.exceptions.RequestException, ValueError, KeyError, IndexError) as e:
        logger.warning("geocode ล้มเหลว (%s): %s", location_name, e)
    return None, None


def _to_xy(lat, lon, lat0):
    """แปลง lat/lon เป็นพิกัดระนาบ (กม.) แบบประมาณ"""
    x = math.radians(lon) * math.cos(math.radians(lat0)) * 6371.0
    y = math.radians(lat) * 6371.0
    return x, y


def point_to_segment_km(plat, plon, alat, alon, blat, blon):
    """ระยะทาง (กม.) จากจุด P ถึงเส้นตรง A->B = น้ำหนัก 'ความใกล้เส้นทาง'"""
    lat0 = (alat + blat) / 2.0
    ax, ay = _to_xy(alat, alon, lat0)
    bx, by = _to_xy(blat, blon, lat0)
    px, py = _to_xy(plat, plon, lat0)
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def filter_places_near_route(places_text, start_coords, end_coords, max_km=25, limit=12):
    """
    กรองเฉพาะสถานที่ที่อยู่ใกล้แนวเส้นทาง เริ่ม->จุดหมาย (ในระยะ max_km)
    เรียงจากใกล้เส้นทางสุดก่อน คืน "" ถ้าไม่มีสักที่ (ให้ผู้เรียกใช้ fallback)
    """
    try:
        salat, salon = [float(x.strip()) for x in start_coords.split(',')]
        ealat, ealon = [float(x.strip()) for x in end_coords.split(',')]
    except (ValueError, AttributeError):
        return places_text  # พิกัดเสีย -> ไม่กรอง

    kept = []
    for line in (places_text or "").strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', line)
        if not m:
            continue
        plat, plon = float(m.group(1)), float(m.group(2))
        d = point_to_segment_km(plat, plon, salat, salon, ealat, ealon)
        if d <= max_km:
            kept.append((d, line))
    kept.sort(key=lambda x: x[0])
    return "\n".join(ln for _, ln in kept[:limit])


def _cap_lines(text, n=10):
    lines = [l for l in (text or "").strip().split('\n') if l.strip()]
    return "\n".join(lines[:n])


def fetch_live_places(keyword="สถานที่ท่องเที่ยว"):
    """คืน string รายการสถานที่ หรือคืน None ถ้าหาไม่ได้/ผิดพลาด"""
    if keyword in API_CACHE:
        return API_CACHE[keyword]

    url = (f"https://maps.googleapis.com/maps/api/place/textsearch/json"
           f"?query={keyword}&language=th&region=th&key={GOOGLE_MAPS_API_KEY}")
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        results = []
        if data.get('status') == 'OK':
            for place in data.get('results', []):
                name = place.get('name', 'ไม่ระบุชื่อ')
                address = place.get('formatted_address', '').lower()

                if ("กำแพงเพชร" not in address and "kamphaeng" not in address
                        and "กำแพง" not in address):
                    continue

                rating = place.get('rating', 'ไม่มีดาว')
                total_ratings = place.get('user_ratings_total', 0)
                try:
                    p_lat = place['geometry']['location']['lat']
                    p_lng = place['geometry']['location']['lng']
                except (KeyError, TypeError):
                    continue

                if total_ratings > 3:
                    results.append(f"- {name} (⭐ {rating}) | พิกัด: {p_lat}, {p_lng}")
                    if len(results) >= 20:
                        break

            if results:
                random.shuffle(results)
                final_res = "\n".join(results)
                API_CACHE[keyword] = final_res
                return final_res
        else:
            logger.info("Places API status=%s สำหรับ '%s'", data.get('status'), keyword)
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning("fetch_live_places ล้มเหลว ('%s'): %s", keyword, e)

    return None  # ให้ผู้เรียกใช้ fallback


def render_friendly_error(message):
    """หน้า error แบบสุภาพ ไม่ทำให้หน้าจอพัง และไม่เผย stack trace"""
    return render_template_string_safe(message), 200


def render_template_string_safe(message):
    safe_msg = html.escape(message)
    return f"""<!DOCTYPE html>
<html lang="th"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>เกิดข้อผิดพลาด</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{{font-family:'Sarabun',sans-serif;background:#f4fbf6;}}</style>
</head><body>
<div class="container py-5">
  <div class="card shadow-sm border-success mx-auto" style="max-width:560px;">
    <div class="card-body text-center p-5">
      <div style="font-size:3rem;">🙏</div>
      <h4 class="text-success fw-bold mt-3">ขออภัยครับ เกิดข้อขัดข้องชั่วคราว</h4>
      <p class="text-muted mt-3">{safe_msg}</p>
      <a href="/" class="btn btn-success rounded-pill px-4 mt-2">
        <i class="fas fa-arrow-left me-1"></i> กลับไปลองใหม่
      </a>
    </div>
  </div>
</div>
</body></html>"""


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/plan', methods=['GET', 'POST'])
def plan_trip():
    if request.method == 'GET':
        return redirect(url_for('index'))

    try:
        num_days = safe_int(request.form.get('num_days', '1'), default=1)
        num_days = max(1, min(num_days, MAX_DAYS))  # clamp 1..MAX_DAYS

        daily_start_time = request.form.getlist('daily_start_time[]')
        daily_end_time = request.form.getlist('daily_end_time[]')
        day_starts = request.form.getlist('day_start[]')
        day_ends = request.form.getlist('day_end[]')

        daily_budgets = request.form.getlist('daily_budget[]')
        if not daily_budgets:
            daily_budgets = ['1500']
        total_budget = sum(safe_int(b, 0) for b in daily_budgets)

        fuel_consumption = request.form.get('fuel_consumption', '15')
        fuel_price = request.form.get('fuel_price', '38')

        place_styles = request.form.getlist('place_styles')
        food_styles = request.form.getlist('food_styles')

        places_per_day = request.form.getlist('places_per_day[]')
        hotel_budget = max(500, safe_int(request.form.get('hotel_budget', '800'), default=800))

        str_places = "ยอดฮิต" if ("AI_Select" in place_styles or not place_styles) else " ".join(place_styles)
        str_foods = "อร่อย โลคอล" if ("AI_Select" in food_styles or not food_styles) else " ".join(food_styles)

        queries = [
            f"ที่เที่ยว {str_places} สถานที่ลับ Unseen กำแพงเพชร",
            "อุทยาน ธรรมชาติ น้ำตก จุดชมวิว กำแพงเพชร",
            f"ร้านอาหาร คาเฟ่ ร้านลับ โลคอล {str_foods} กำแพงเพชร",
            "โรงแรม รีสอร์ท โฮมสเตย์ กำแพงเพชร",
        ]

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(fetch_live_places, queries))
        except Exception as e:
            logger.warning("ThreadPool ล้มเหลว ใช้ fallback ทั้งหมด: %s", e)
            results = [None, None, None, None]

        # fetch_live_places คืน None เมื่อหาไม่ได้ -> ใช้ fallback
        db_attractions_main = results[0] or FALLBACK_MAIN
        db_attractions_outside = results[1] or FALLBACK_NATURE
        db_food = results[2] or FALLBACK_FOOD
        db_hotels = results[3] or FALLBACK_HOTEL

        # lookup ชื่อ->พิกัดจริง (ใช้แทนพิกัดที่ AI สร้างเอง กันหมุดมั่ว)
        place_coord_lookup = parse_db_coords(
            db_attractions_main, db_attractions_outside, db_food, db_hotels
        )
        day_start_coords = {}  # {day_number: (lat, lng)}
        day_end_coords = {}

        daily_routing_instructions = ""
        for i in range(num_days):
            s_loc = day_starts[i] if i < len(day_starts) else "ตัวเมืองกำแพงเพชร"
            e_loc = day_ends[i] if i < len(day_ends) else "ตัวเมืองกำแพงเพชร"

            ppd = max(3, min(safe_int(places_per_day[i], 6), 10)) if i < len(places_per_day) else 6
            t_start = daily_start_time[i] if i < len(daily_start_time) else "09:00"
            t_end = daily_end_time[i] if i < len(daily_end_time) else "18:00"

            s_name, s_coords = parse_location(s_loc)
            e_name, e_coords = parse_location(e_loc)

            # เก็บพิกัดจริงของจุดเริ่ม/จบรายวัน (ใช้ปักหมุดให้ตรง)
            day_start_coords[i + 1] = coords_str_to_tuple(s_coords)
            day_end_coords[i + 1] = coords_str_to_tuple(e_coords)

            # 🛣️ กราฟมีน้ำหนัก: กรองเฉพาะสถานที่ที่อยู่ "ใกล้แนวเส้นทาง" เริ่ม->จบ ของวันนี้
            day_attr = (filter_places_near_route(db_attractions_main, s_coords, e_coords, max_km=25, limit=10)
                        or _cap_lines(db_attractions_main, 8))
            day_nature = (filter_places_near_route(db_attractions_outside, s_coords, e_coords, max_km=30, limit=6)
                          or _cap_lines(db_attractions_outside, 4))
            day_food = (filter_places_near_route(db_food, s_coords, e_coords, max_km=25, limit=8)
                        or _cap_lines(db_food, 6))

            if "จุดสิ้นสุดของเมื่อวาน" in s_loc or "จุดสิ้นสุดของวันที่" in s_loc:
                header = (f"[DAY_{i+1}] เวลา {t_start}-{t_end} | เริ่ม: 'จุดสิ้นสุดของเมื่อวาน', "
                          f"จบ: '{e_name}' (พิกัด: {e_coords}) | ต้องการ {ppd} สถานที่\n")
            else:
                header = (f"[DAY_{i+1}] เวลา {t_start}-{t_end} | เริ่ม: '{s_name}' (พิกัด: {s_coords}), "
                          f"จบ: '{e_name}' (พิกัด: {e_coords}) | ต้องการ {ppd} สถานที่\n")

            daily_routing_instructions += (
                header +
                "  ▸ ที่เที่ยว/Unseen ที่อยู่ใกล้เส้นทางวันนี้ (เลือกจากนี่):\n" + day_attr + "\n" +
                "  ▸ ธรรมชาติ ที่อยู่ใกล้เส้นทางวันนี้:\n" + day_nature + "\n" +
                "  ▸ ร้านอาหาร/คาเฟ่ ที่อยู่ใกล้เส้นทางวันนี้:\n" + day_food + "\n\n"
            )

        if num_days > 1:
            hotel_block = f"[ที่พัก (ค้างคืน — ใส่ 1 แห่งที่ปลายของวันที่ต้องค้าง)]\n{db_hotels}"
            hotel_rule = ("9. ที่พัก: ทริปนี้ค้างคืน ให้ใส่ที่พัก 1 แห่งที่ปลายของแต่ละวันที่ต้องค้างคืน "
                          "(ก่อนบรรทัดจุดสิ้นสุด / วันสุดท้ายถ้ากลับบ้านแล้วไม่ต้องมีที่พัก) เลือกจากรายการที่พักเท่านั้น")
        else:
            hotel_block = "(ทริปนี้ 1 วัน ไป-กลับวันเดียว — ไม่มีที่พัก)"
            hotel_rule = "9. ⛔ ทริปนี้ 1 วัน (ไป-กลับวันเดียว) ห้ามใส่ที่พัก/โรงแรมในแผนเด็ดขาด"

        prompt = f"""
        คุณคือระบบจัดตารางทริปอัจฉริยะ ประจำ "จังหวัดกำแพงเพชร"
        ห้ามอธิบาย ห้ามใส่หัวตาราง ตอบเป็นข้อมูลดิบ | คั่นเท่านั้น!

        [ความชอบของลูกค้า]
        สไตล์ที่เที่ยว: {str_places}
        สไตล์ที่กิน: {str_foods}

        [ที่พัก (เลือกได้ทุกวัน)]
        {hotel_block}

        [แผนรายวัน — สถานที่ในแต่ละวัน "ถูกกรองมาแล้ว" ว่าอยู่ใกล้แนวเส้นทาง เริ่ม->จุดหมาย ของวันนั้น]
        {daily_routing_instructions}

        [⚠️ คำสั่งบังคับเด็ดขาด (ห้ามฝ่าฝืน)]
        1. เลือกสถานที่จากรายการ "ใกล้เส้นทางวันนี้" ของแต่ละวันเท่านั้น (และที่พักจากรายการที่พัก) ห้ามใช้สถานที่นอกรายการ เพราะรายการถูกกรองมาแล้วว่าอยู่ระหว่างทาง
        2. กระจายให้ทั่วเส้นทาง: เลือกให้แต่ละจุดอยู่คนละย่าน ห่างกันพอควร ห้ามกระจุกติดกันจุดเดียวทั้งหมด
        3. ⭐ จุดเริ่ม-จุดจบบังคับ: บรรทัด "แรก" ของแต่ละวันต้องเป็นจุดเริ่มต้น ตั้งชื่อขึ้นต้นว่า "จุดเริ่มต้น: ..." และใช้ "พิกัดของเริ่ม" ที่ระบุใน [จุดบังคับรายวัน] เป๊ะ / บรรทัด "สุดท้าย" ของแต่ละวันต้องเป็นจุดสิ้นสุด ตั้งชื่อ "จุดสิ้นสุด: ..." และใช้ "พิกัดของจบ" เป๊ะ ห้ามลืมสองบรรทัดนี้
        4. เรียงตามตำแหน่งจริงให้เดินทางต่อเนื่องเป็นเส้นเดียว (จุดเริ่ม -> ไล่ผ่านจุดระหว่างทางตามระยะ -> จุดจบ) ห้ามวิ่งย้อนกลับไปกลับมา
        5. จำนวนสถานที่: จัดตาม "ต้องการ N สถานที่" ของแต่ละวัน (นับเฉพาะจุดเที่ยว/กิน/พัก ไม่รวมจุดเริ่ม-จบ)
        6. เวลาในตาราง: จุดเริ่มต้นใช้ "เวลาเริ่ม" และจบไม่เกิน "เวลากลับ" ของวันนั้น เรียงเวลาจากน้อยไปมากเสมอ ห้ามย้อนหลัง เผื่อเวลาเดินทาง+อยู่แต่ละจุด (ปกติจุดละ 45-90 นาที)
        7. ระยะเวลาขับรถ: กะระยะเวลาขับรถจริงระหว่างจุด (เช่น 15 นาที, 40 นาที) ห้ามใส่ 0 นาทีรวด
        8. รูปแบบ: DAY_X | เวลา | ระยะเวลาขับรถ | รหัสไอคอน | ชื่อสถานที่ | ประเภท | พิกัดLat | พิกัดLng
        {hotel_rule}
        """

        ai_text = call_gemini(prompt, max_tokens=8192, temperature=0.6, timeout=55, retries=0)
        if not ai_text:
            return render_friendly_error(
                "ระบบ AI ไม่ตอบกลับในขณะนี้ (อาจมีผู้ใช้งานหนาแน่นหรือสัญญาณขัดข้อง) "
                "กรุณากดลองใหม่อีกครั้งในอีกสักครู่ครับ"
            )

        icon_dict = {
            'ICON_TEMPLE': "https://img.icons8.com/color/96/pagoda.png",
            'ICON_CAFE': "https://img.icons8.com/color/96/cafe.png",
            'ICON_HISTORY': "https://img.icons8.com/color/96/museum.png",
            'ICON_NATURE': "https://img.icons8.com/color/96/national-park.png",
            'ICON_HOTEL': "https://img.icons8.com/color/96/bed.png",
            'ICON_FOOD': "https://img.icons8.com/color/96/restaurant.png",
            'ICON_MARKET': "https://img.icons8.com/color/96/shopping-cart.png",
            'ICON_OTHER': "https://img.icons8.com/color/96/map-pin.png",
        }

        clean_text = ""
        current_day = ""
        ai_text = ai_text.replace('```', '').replace('text', '').replace('*', '').strip()

        for line in ai_text.split('\n'):
            if '|' not in line or 'DAY_' not in line.upper():
                continue

            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 3:
                continue

            day_match = re.search(r'DAY_(\d+)', line.upper())
            if not day_match:
                continue
            day_num = day_match.group(1)

            if f"DAY_{day_num}" != current_day:
                current_day = f"DAY_{day_num}"
                clean_text += f"""
                <tr class="table-success day-divider" data-day="{day_num}">
                    <td colspan="7" class="text-center fw-bold text-success fs-5 py-3">
                        <i class="fas fa-calendar-day me-2"></i> วันที่ {day_num} <span class="daily-budget-label fs-6"></span>
                    </td>
                </tr>
                """

            name_str = parts[4] if len(parts) >= 8 else "จุดแวะพัก"
            cat_str = parts[5] if len(parts) >= 8 else "ทั่วไป"
            name_str = re.sub(r'ICON_[A-Z_]+', '', name_str).strip()

            if "ไม่พบข้อมูล" in name_str:
                continue

            # ป้องกัน HTML แตกจากชื่อที่มีอักขระพิเศษ
            name_safe = html.escape(name_str or "จุดแวะพัก", quote=True)
            cat_safe = html.escape(cat_str or "ทั่วไป", quote=True)

            extracted_icon = 'ICON_OTHER'
            imatch = re.search(r'(ICON_[A-Z_]+)', line.upper())
            if imatch and imatch.group(1) in icon_dict:
                extracted_icon = imatch.group(1)
            else:
                # เดาจากชื่อ+ประเภท เรียงจากเฉพาะเจาะจงไปกว้าง (ลำดับสำคัญมาก)
                t = f"{name_str} {cat_str}"
                if re.search(r'(คาเฟ่|กาแฟ|coffee|cafe|เบเกอรี่|เค้ก|ชานม|ชาไทย)', t, re.IGNORECASE):
                    extracted_icon = 'ICON_CAFE'
                elif re.search(r'(พิพิธภัณฑ์|ประวัติศาสตร์|อุทยานประวัติศาสตร์|เมืองเก่า|โบราณสถาน|โบราณคดี)', t):
                    extracted_icon = 'ICON_HISTORY'
                elif re.search(r'(วัด|พระธาตุ|เจดีย์|พระ|ทำบุญ|ศาล|โบสถ์|มัสยิด)', t):
                    extracted_icon = 'ICON_TEMPLE'
                elif re.search(r'(น้ำตก|อุทยานแห่งชาติ|ธรรมชาติ|ภูเขา|เขา|ช่องเย็น|แก่ง|ป่า|จุดชมวิว|บ่อน้ำพุร้อน|สวน)', t):
                    extracted_icon = 'ICON_NATURE'
                elif re.search(r'(ตลาด|ถนนคนเดิน|ช้อปปิ้ง|ของฝาก|นัดหมาย|plaza|market)', t, re.IGNORECASE):
                    extracted_icon = 'ICON_MARKET'
                elif re.search(r'(โรงแรม|รีสอร์ท|รีสอร์ต|ที่พัก|โฮมสเตย์|เกสต์เฮาส์|นอน|hotel|resort)', t, re.IGNORECASE):
                    extracted_icon = 'ICON_HOTEL'
                elif re.search(r'(ร้านอาหาร|อาหาร|กิน|ข้าว|ก๋วยเตี๋ยว|ครัว|ภัตตาคาร|หมูกระทะ|ซีฟู้ด|ก๋วยเตี๋ยว|food|restaurant)', t, re.IGNORECASE):
                    extracted_icon = 'ICON_FOOD'

            img_src = icon_dict.get(extracted_icon, icon_dict['ICON_OTHER'])

            time_str = html.escape(parts[1].strip() if len(parts) > 1 else "00:00")
            travel_str = html.escape(parts[2].strip() if len(parts) > 2 else "0 นาที")

            coords = re.findall(r'(\d{2,3}\.\d{4,})', line)
            lat_str, lng_str = DEFAULT_LAT, DEFAULT_LNG
            if len(coords) >= 2:
                lat_str, lng_str = coords[0], coords[1]
                try:
                    lat_f = float(lat_str)
                    lng_f = float(lng_str)
                    if lat_f > 50 and lng_f < 50:  # สลับ lat/lng
                        lat_f, lng_f = lng_f, lat_f
                        lat_str, lng_str = str(lat_f), str(lng_f)
                    if not (15.0 <= float(lat_str) <= 17.5 and 98.5 <= float(lng_str) <= 100.5):
                        lat_str, lng_str = DEFAULT_LAT, DEFAULT_LNG
                except ValueError:
                    lat_str, lng_str = DEFAULT_LAT, DEFAULT_LNG

            # === ใช้พิกัดจริงแทนพิกัดที่ AI สร้าง (แก้หมุดมั่ว) ===
            is_start_or_end = ("เริ่ม" in name_str or "สิ้นสุด" in name_str
                               or "จุดจบ" in name_str or "เดินทาง" in name_str)
            real_coords = None
            if is_start_or_end:
                if "สิ้นสุด" in name_str or "จุดจบ" in name_str or "จบ" in name_str:
                    real_coords = day_end_coords.get(safe_int(day_num, 0))
                else:
                    real_coords = day_start_coords.get(safe_int(day_num, 0))
            else:
                real_coords = match_real_coords(name_str, place_coord_lookup)
                # จับคู่พิกัดจริงไม่ได้ = AI มั่วชื่อ/ไม่อยู่ในรายการ -> ตัดทิ้ง กันหมุดลอยกลางน้ำ
                if not real_coords:
                    continue
            if real_coords:
                lat_str, lng_str = real_coords[0], real_coords[1]

            is_hotel = ("HOTEL" in extracted_icon or "พัก" in line)

            # ทริป 1 วัน (ไป-กลับ) ไม่ต้องมีที่พักในแผน
            if is_hotel and num_days <= 1:
                continue

            if is_hotel:
                default_price, fuel_est = str(hotel_budget), "0"
            elif extracted_icon in ['ICON_TEMPLE', 'ICON_HISTORY']:
                default_price, fuel_est = "100", "30"
            elif extracted_icon == 'ICON_NATURE':
                default_price, fuel_est = "100", "60"
            elif extracted_icon == 'ICON_FOOD':
                default_price, fuel_est = "150", "20"
            elif extracted_icon == 'ICON_CAFE':
                default_price, fuel_est = "120", "20"
            elif extracted_icon == 'ICON_MARKET':
                default_price, fuel_est = "200", "20"
            else:
                default_price, fuel_est = "100", "30"

            is_start_or_end = ("เริ่มต้น" in name_str or "สิ้นสุด" in name_str
                               or "เดินทาง" in name_str or "จุดเริ่ม" in name_str)
            if is_start_or_end:
                default_price, fuel_est = "0", "0"

            # ลิงก์นำทาง Google Maps (แก้ลิงก์เสียจาก markdown เดิม)
            maps_url = f"https://www.google.com/maps/search/?api=1&query={lat_str},{lng_str}"

            row_extra_class = " hotel-row" if is_hotel else ""

            clean_text += f"""
            <tr class="trip-row day-{day_num}{row_extra_class}" data-lat="{lat_str}" data-lng="{lng_str}" data-name="{name_safe}">
                <td class="text-center align-middle">
                    <div contenteditable="true" class="fw-bold text-success" style="font-size: 0.9rem;">{time_str}</div>
                    <div class="text-muted mt-1" style="font-size: 0.7rem;"><i class="fas fa-clock"></i> ~{travel_str}</div>
                </td>
                <td class="text-center align-middle"><img src="{img_src}" class="place-icon bg-white shadow-sm rounded-circle" style="width:40px;height:40px;"></td>
                <td class="align-middle">
                    <div class="fw-bold text-dark">{name_safe}</div>
                    <span class="badge rounded-pill bg-light text-dark border mt-1">{cat_safe}</span><br>
                    <a href="{maps_url}" target="_blank" rel="noopener" class="btn btn-sm btn-outline-primary mt-2"><i class="fas fa-location-arrow"></i> นำทาง</a>
                </td>
                <td class="align-middle"><input type="number" class="form-control form-control-sm price-activity green-input" value="{default_price}" onchange="recalcBudget()"></td>
                <td class="align-middle"><input type="number" class="form-control form-control-sm price-fuel green-input" value="{fuel_est}" onchange="recalcBudget()"></td>
                <td class="text-end fw-bold text-success align-middle remaining-budget">...</td>
                <td class="text-center align-middle">
                    <div class="btn-group flex-wrap">
                        <button type="button" onclick="moveRow(this, -1)" class="btn btn-outline-success btn-sm" title="ขึ้น"><i class="fas fa-arrow-up"></i></button>
                        <button type="button" onclick="moveRow(this, 1)" class="btn btn-outline-success btn-sm" title="ลง"><i class="fas fa-arrow-down"></i></button>
                        <button type="button" onclick="delRow(this)" class="btn btn-danger btn-sm" title="ลบ"><i class="fas fa-trash"></i></button>
                    </div>
                </td>
            </tr>
            """

        if not clean_text.strip():
            return render_friendly_error(
                "AI ตอบกลับมาแต่จัดรูปแบบทริปไม่สำเร็จ กรุณากดลองใหม่อีกครั้งครับ"
            )

        return render_template(
            'result.html',
            plan_data=clean_text,
            total_budget=total_budget,
            daily_budgets=daily_budgets,
            daily_start_times=(daily_start_time or ['09:00']),
            fuel_consumption=fuel_consumption,
            fuel_price=fuel_price,
            google_maps_api_key=GOOGLE_MAPS_API_KEY,
        )

    except Exception as e:
        # กันไม่ให้หน้าจอพังด้วย stack trace; log ไว้ฝั่ง server
        logger.exception("plan_trip ล้มเหลวโดยไม่คาดคิด: %s", e)
        return render_friendly_error(
            "ระบบเกิดข้อผิดพลาดระหว่างจัดทริป กรุณากดลองใหม่อีกครั้งครับ"
        )


def ask_nong_guide(user_message, history=None):
    """
    สมองกลางของ 'น้องไกด์' — ใช้ทั้งหน้าเว็บและ LINE
    รับข้อความ + ประวัติแชท คืนคำตอบ (str) หรือ None ถ้าล้มเหลว
    """
    history = history or []

    # ข้อ 1: ดึงข้อมูลสถานที่จริงมาเป็นบริบท (ใช้ cache ซ้ำ ไม่เปลืองโควต้า)
    attractions = fetch_live_places("สถานที่ท่องเที่ยว Unseen กำแพงเพชร") or FALLBACK_MAIN
    nature = fetch_live_places("อุทยาน ธรรมชาติ น้ำตก กำแพงเพชร") or FALLBACK_NATURE
    food = fetch_live_places("ร้านอาหาร คาเฟ่ ร้านลับ กำแพงเพชร") or FALLBACK_FOOD

    system_instruction = f"""คุณคือ 'น้องไกด์' ผู้ช่วยแนะนำท่องเที่ยวจังหวัดกำแพงเพชร พูดสุภาพเป็นกันเอง ตอบกระชับเข้าใจง่าย
⚠️ กฎเหล็ก:
1. แนะนำเฉพาะสถานที่ใน "จังหวัดกำแพงเพชร" เท่านั้น
2. แนะนำโดยอ้างอิงจาก "รายการสถานที่จริง" ด้านล่างเป็นหลัก ห้ามแต่งชื่อสถานที่ที่ไม่มีในรายการ ถ้าไม่มีข้อมูลให้บอกตามตรงว่าไม่แน่ใจ
3. ถ้าผู้ใช้ถามนอกเรื่องเที่ยวกำแพงเพชร ให้ดึงกลับเข้าเรื่องอย่างสุภาพ

[ที่เที่ยว / Unseen]
{attractions}

[ธรรมชาติ / นอกเมือง]
{nature}

[ร้านอาหาร / คาเฟ่]
{food}
"""

    # ข้อ 2: ประกอบบทสนทนาพร้อมความจำย้อนหลัง (เก็บ 8 ตาล่าสุด กันยาวเกิน)
    contents = []
    for turn in history[-8:]:
        role = "model" if turn.get("role") in ("bot", "model", "assistant") else "user"
        text = (turn.get("text") or "").strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    return call_gemini(
        contents=contents,
        system_instruction=system_instruction,
        max_tokens=600, temperature=0.3, timeout=30, retries=1
    )


@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    try:
        data = request.get_json(silent=True) or {}
        user_message = (data.get('message') or '').strip()
        history = data.get('history') or []
        if not user_message:
            return jsonify({"status": "error", "response": "กรุณาพิมพ์คำถามก่อนนะครับ 😊"})

        answer = ask_nong_guide(user_message, history)
        if answer:
            return jsonify({"status": "success", "response": answer})
        return jsonify({"status": "error", "response": "ขออภัยครับ ระบบ AI ไม่ตอบกลับในขณะนี้ ลองใหม่อีกครั้งนะครับ"})
    except Exception as e:
        logger.exception("chat ล้มเหลว: %s", e)
        return jsonify({"status": "error", "response": "ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งนะครับ"})


# ==========================================
# 🟢 LINE Official Account — บอทถามตอบน้องไกด์
# ==========================================
def verify_line_signature(body_bytes, signature):
    """ตรวจลายเซ็นจาก LINE ว่าคำขอมาจาก LINE จริง (กันคนปลอม)"""
    if not LINE_CHANNEL_SECRET:
        return False
    mac = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")


def line_reply(reply_token, text):
    """ตอบกลับข้อความไปยัง LINE"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not reply_token:
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": (text or "")[:4900]}],
    }
    try:
        requests.post(LINE_REPLY_URL, headers=headers, json=payload, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.warning("LINE reply ล้มเหลว: %s", e)


def process_line_events(data):
    """ประมวลผล event จาก LINE (ทำใน background เพื่อตอบ 200 ให้ LINE เร็ว)"""
    for event in data.get("events", []):
        try:
            if event.get("type") != "message":
                continue
            msg = event.get("message", {})
            if msg.get("type") != "text":
                continue

            user_id = event.get("source", {}).get("userId", "anon")
            user_text = (msg.get("text") or "").strip()
            reply_token = event.get("replyToken")
            if not user_text:
                continue

            hist = LINE_HISTORY.get(user_id, [])
            answer = ask_nong_guide(user_text, hist) or "ขออภัยครับ ตอนนี้น้องไกด์ตอบไม่ได้ ลองใหม่อีกครั้งนะครับ 🙏"

            # อัปเดตความจำต่อ user (เก็บ 8 คู่ล่าสุด)
            hist = hist + [{"role": "user", "text": user_text}, {"role": "bot", "text": answer}]
            LINE_HISTORY[user_id] = hist[-16:]

            line_reply(reply_token, answer)
        except Exception as e:
            logger.exception("LINE event error: %s", e)


@app.route('/line/webhook', methods=['POST'])
def line_webhook():
    body = request.get_data()  # อ่าน raw bytes ไว้ตรวจลายเซ็น
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_line_signature(body, signature):
        logger.warning("LINE: ลายเซ็นไม่ถูกต้อง (อาจตั้ง LINE_CHANNEL_SECRET ผิด)")
        return "Bad signature", 400

    data = request.get_json(silent=True) or {}
    # ตอบ 200 ให้ LINE ทันที แล้วค่อยประมวลผล/ตอบกลับใน background
    threading.Thread(target=process_line_events, args=(data,), daemon=True).start()
    return "OK", 200


@app.errorhandler(404)
def not_found(_e):
    return redirect(url_for('index'))


@app.errorhandler(500)
def server_error(_e):
    return render_friendly_error("เกิดข้อผิดพลาดภายในระบบ กรุณากดลองใหม่อีกครั้งครับ")


if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=5001, debug=debug_mode, threaded=True)
