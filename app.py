import os
import re
import math
import random
import concurrent.futures

import requestsimport os
import re
import time
import math
import random
import concurrent.futures

import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

# ==========================================
# 🔑 กุญแจ API — ตั้งเป็น Environment Variable (ห้ามฝังในโค้ด)
#   GEMINI_API_KEY=...   GOOGLE_MAPS_API_KEY=...
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "")


def call_gemini(payload, budget=105):
    """เรียก Gemini แบบลองซ้ำเมื่อเซิร์ฟเวอร์ยุ่ง (429/500/503) และสลับไปโมเดลสำรองถ้าตั้งไว้
    budget = เวลารวมสูงสุด (วินาที) ต้องน้อยกว่า --timeout ของ gunicorn"""
    models = [GEMINI_MODEL] + ([GEMINI_FALLBACK_MODEL] if GEMINI_FALLBACK_MODEL else [])
    deadline = time.time() + budget
    last = None
    for attempt in range(4):
        model = models[attempt % len(models)]
        remaining = deadline - time.time()
        if remaining < 8:
            break
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={GEMINI_API_KEY}")
        try:
            r = requests.post(url, headers={"Content-Type": "application/json"},
                              json=payload, timeout=min(60, remaining))
            if r.status_code not in (429, 500, 502, 503, 504):
                return r
            last = r
        except requests.exceptions.Timeout:
            last = None
        time.sleep(min(2 + attempt * 2, max(deadline - time.time() - 8, 0)))
    return last


API_CACHE = {}
GEO_CACHE = {}
CITY = (16.4828, 99.5227)

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
    "ตัวเมืองกำแพงเพชร": (16.4828, 99.5227),
    "อุทยานประวัติศาสตร์": (16.4928, 99.5153),
    "น้ำตกคลองลาน": (16.1303, 99.2811),
    "ช่องเย็น": (16.0991, 99.1068),
    "แม่วงก์": (16.0991, 99.1068),
    "บ่อน้ำพุร้อนพระร่วง": (16.3216, 99.6648),
    "ตลาดย้อนยุคนครชุม": (16.4851, 99.5103),
}

# ราคาตั้งต้นของแต่ละประเภท (บาท) — ผู้ใช้แก้ไขเองได้ในหน้าผลลัพธ์
DEFAULT_PRICE = {"TEMPLE": 20, "HISTORY": 20, "NATURE": 40, "FOOD": 120,
                 "CAFE": 100, "MARKET": 100, "HOTEL": 0, "OTHER": 50}
VALID_ICONS = set(DEFAULT_PRICE)


def geocode_location(name):
    if name in GEO_CACHE:
        return GEO_CACHE[name]
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": name, "key": GOOGLE_MAPS_API_KEY, "language": "th"},
            timeout=3,
        )
        data = r.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            GEO_CACHE[name] = (loc["lat"], loc["lng"])
            return GEO_CACHE[name]
    except Exception:
        pass
    return None


def parse_location(text):
    """คืน (ชื่อ, lat, lng) จากข้อความ: พิกัด / ชื่อที่รู้จัก / geocode / กลางเมือง"""
    text = (text or "").strip() or "ตัวเมืองกำแพงเพชร"
    m = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", text)
    if m:
        return text, float(m.group(1)), float(m.group(2))
    for key, (la, ln) in KNOWN_LOCATIONS.items():
        if key in text:
            return text, la, ln
    g = geocode_location(text)
    if g:
        return text, g[0], g[1]
    return text, CITY[0], CITY[1]


def fetch_live_places(keyword):
    if keyword in API_CACHE:
        return API_CACHE[keyword]
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": keyword, "language": "th", "region": "th", "key": GOOGLE_MAPS_API_KEY},
            timeout=5,
        )
        data = r.json()
        results = []
        if data.get("status") == "OK":
            for p in data["results"]:
                addr = p.get("formatted_address", "").lower()
                if "กำแพง" not in addr and "kamphaeng" not in addr:
                    continue
                if p.get("user_ratings_total", 0) <= 3:
                    continue
                loc = p["geometry"]["location"]
                results.append(f"- {p.get('name', 'ไม่ระบุชื่อ')} (⭐ {p.get('rating', '-')}) | พิกัด: {loc['lat']}, {loc['lng']}")
                if len(results) >= 20:
                    break
        if results:
            random.shuffle(results)
            API_CACHE[keyword] = "\n".join(results)
            return API_CACHE[keyword]
    except Exception:
        pass
    return "ไม่มีข้อมูล"


def haversine_km(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = p2 - p1
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def guess_icon(text):
    if re.search(r"(โรงแรม|รีสอร์ท|โฮมสเตย์|ที่พัก|นอน)", text): return "HOTEL"
    if re.search(r"(คาเฟ่|กาแฟ|cafe)", text, re.I): return "CAFE"
    if re.search(r"(อาหาร|ร้าน|ก๋วยเตี๋ยว|บะหมี่|ข้าว|เตี๋ยว|ผัดไทย|เต้าฮวย)", text): return "FOOD"
    if re.search(r"(วัด|พระ|ศาล)", text): return "TEMPLE"
    if re.search(r"(พิพิธภัณฑ์|พิพิธภัณฑ|ประวัติศาสตร์|เมืองโบราณ)", text): return "HISTORY"
    if re.search(r"(น้ำตก|อุทยาน|ธรรมชาติ|เขา|ช่องเย็น|แก่ง|น้ำพุร้อน)", text): return "NATURE"
    if re.search(r"(ตลาด|ถนนคนเดิน)", text): return "MARKET"
    return "OTHER"


def parse_plan(ai_text, consumption, fuel_price):
    """แปลงข้อความดิบจาก AI เป็น list ของจุดแวะ (dict) พร้อมคำนวณค่าน้ำมันจากระยะทางจริง"""
    stops, prev = [], {}
    text = ai_text.replace("```", "").replace("*", "")
    for line in text.split("\n"):
        m = re.search(r"DAY_(\d+)", line.upper())
        if "|" not in line or not m:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue
        day = int(m.group(1))
        name = re.sub(r"ICON_[A-Z_]+", "", parts[4]).strip()
        if not name or "ไม่พบข้อมูล" in name:
            continue

        icon = parts[3].upper().replace("ICON_", "")
        if icon not in VALID_ICONS:
            icon = guess_icon(name + " " + parts[5])

        try:
            lat, lng = float(parts[6]), float(parts[7])
            if lat > 50 and lng < 50:
                lat, lng = lng, lat
        except ValueError:
            lat, lng = CITY
        is_endpoint = bool(re.search(r"(เริ่มต้น|สิ้นสุด|เดินทาง|จุดเริ่ม)", name))
        if not is_endpoint and not (15.0 <= lat <= 17.5 and 98.5 <= lng <= 100.5):
            lat, lng = CITY

        price = 0 if is_endpoint else DEFAULT_PRICE.get(icon, 50)
        fuel = 0
        if day in prev and not is_endpoint:
            km = haversine_km(prev[day][0], prev[day][1], lat, lng) * 1.3  # ชดเชยทางจริงที่อ้อมกว่าเส้นตรง
            fuel = round(km / max(consumption, 1) * fuel_price)
        prev[day] = (lat, lng)

        stops.append({
            "day": day, "time": parts[1], "travel": parts[2], "icon": icon,
            "name": name, "cat": parts[5] or "ทั่วไป", "lat": round(lat, 6), "lng": round(lng, 6),
            "price": price, "fuel": fuel,
        })
    return stops


def to_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/plan", methods=["GET", "POST"])
def plan_trip():
    if request.method == "GET":
        return redirect(url_for("index"))
    try:
        f = request.form
        num_days = min(max(int(f.get("num_days", "1")), 1), 4)
        start_time = f.get("daily_start_time", "09:00")
        end_time = f.get("daily_end_time", "18:00")
        daily_budget = max(int(to_float(f.get("daily_budget"), 1500)), 1000)
        hotel_budget = f.get("hotel_budget", "1000")
        consumption = to_float(f.get("fuel_consumption"), 15)
        fuel_price = to_float(f.get("fuel_price"), 37.5)
        vehicle = f.get("vehicle_type", "รถเก๋ง")

        place_styles = f.getlist("place_styles")
        food_styles = f.getlist("food_styles")
        str_places = "ยอดฮิต" if (not place_styles or "AI_Select" in place_styles) else " ".join(place_styles)
        str_foods = "อร่อย โลคอล" if (not food_styles or "AI_Select" in food_styles) else " ".join(food_styles)

        s_name, s_lat, s_lng = parse_location(f.get("start_loc"))
        end_raw = (f.get("end_loc") or "").strip()
        e_name, e_lat, e_lng = parse_location(end_raw) if end_raw else (s_name, s_lat, s_lng)

        queries = [
            f"ที่เที่ยว {str_places} สถานที่ลับ Unseen กำแพงเพชร",
            "อุทยาน ธรรมชาติ น้ำตก จุดชมวิว กำแพงเพชร",
            f"ร้านอาหาร คาเฟ่ ร้านลับ โลคอล {str_foods} กำแพงเพชร",
            "โรงแรม รีสอร์ท โฮมสเตย์ กำแพงเพชร",
        ]
        with concurrent.futures.ThreadPoolExecutor() as ex:
            res = list(ex.map(fetch_live_places, queries))
        fallbacks = [FALLBACK_MAIN, FALLBACK_NATURE, FALLBACK_FOOD, FALLBACK_HOTEL]
        db = [r if "ไม่มีข้อมูล" not in r else fb for r, fb in zip(res, fallbacks)]

        routing = "".join(
            f"[DAY_{i}] เริ่ม: '{s_name}' (พิกัด: {s_lat}, {s_lng}), จบ: '{e_name}' (พิกัด: {e_lat}, {e_lng}), "
            f"เวลา {start_time}-{end_time}\n"
            for i in range(1, num_days + 1)
        )

        prompt = f"""
        คุณคือระบบจัดตารางทริปอัจฉริยะ ประจำ "จังหวัดกำแพงเพชร"
        ห้ามอธิบาย ห้ามใส่หัวตาราง ตอบเป็นข้อมูลดิบ | คั่นเท่านั้น!

        [ฐานข้อมูลสถานที่]
        (หมวด 1: ที่เที่ยวในเมือง/Unseen)
        {db[0]}
        (หมวด 2: ธรรมชาติ/นอกเมือง)
        {db[1]}
        (หมวด 3: ร้านอาหาร/คาเฟ่/ร้านลับโลคอล)
        {db[2]}
        (หมวด 4: ที่พัก)
        {db[3]}

        [ความชอบของลูกค้า] ที่เที่ยว: {str_places} | กิน: {str_foods}
        [พาหนะ] {vehicle} | งบต่อวัน {daily_budget} บาท | งบที่พักต่อคืน {hotel_budget} บาท
        [จุดบังคับรายวัน]
        {routing}

        [คำสั่งบังคับ]
        1. เลือกสถานที่จากฐานข้อมูลเท่านั้น และห้ามใช้สถานที่ซ้ำข้ามวัน
        2. ผสมสถานที่ดังกับสถานที่แปลกใหม่ (Unseen) / ร้านโลคอลลับ
        3. 1 วันมี 6-8 คิว เรียงตามเวลา: เริ่ม -> เที่ยว -> กิน -> ธรรมชาติ/เที่ยวลับ -> คาเฟ่ -> จบ
        4. คิวแรกของวันคือจุดเริ่มต้น คิวสุดท้ายคือจุดสิ้นสุด ใช้ชื่อและพิกัดตามที่บังคับ (ชื่อควรมีคำว่า "เริ่มต้น" หรือ "สิ้นสุด")
        5. ระยะเวลาขับรถให้กะตามจริง (เช่น 20 นาที, 1 ชม.) ห้ามใส่ 0 นาทีรวด
        6. รหัสไอคอนเลือกจาก: ICON_TEMPLE ICON_HISTORY ICON_NATURE ICON_FOOD ICON_CAFE ICON_MARKET ICON_HOTEL ICON_OTHER
        7. รูปแบบ: DAY_X | เวลา | ระยะเวลาขับรถ | รหัสไอคอน | ชื่อสถานที่ | ประเภท | พิกัดLat | พิกัดLng
        """
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.6}}
        resp = call_gemini(payload)
        if resp is None:
            return render_template("index.html", error="AI ใช้เวลาตอบนานเกินไป ลองกดสร้างแผนอีกครั้ง หรือลดจำนวนวันลง"), 504
        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text[:200]
            if resp.status_code in (429, 503):
                detail = "ตอนนี้มีคนใช้ Gemini จำนวนมาก ลองกดสร้างแผนอีกครั้งในอีกสักครู่"
            return render_template("index.html", error=f"AI ตอบกลับผิดพลาด (รหัส {resp.status_code}): {detail}"), 502

        candidates = resp.json().get("candidates", [])
        if not candidates:
            return render_template("index.html", error="AI ไม่ตอบกลับ ลองกดสร้างแผนอีกครั้ง"), 502

        stops = parse_plan(candidates[0]["content"]["parts"][0]["text"], consumption, fuel_price)
        if not stops:
            return render_template("index.html", error="AI ส่งข้อมูลมาในรูปแบบที่อ่านไม่ได้ ลองกดสร้างแผนอีกครั้ง"), 502

        return render_template("result.html", plan=stops, num_days=num_days,
                               daily_budget=daily_budget, maps_key=GOOGLE_MAPS_API_KEY)
    except Exception as e:
        return render_template("index.html", error=f"เกิดข้อผิดพลาด: {e}"), 500


@app.route("/api/chat", methods=["POST"])
def chat_with_ai():
    try:
        message = (request.json or {}).get("message", "")
        prompt = f"""
        คุณคือ 'น้องไกด์' ประจำ "จังหวัดกำแพงเพชร"
        กฎเหล็ก: แนะนำเฉพาะสถานที่ในกำแพงเพชรเท่านั้น! ตอบสั้น กระชับ เป็นกันเอง
        คำถาม: {message}
        """
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"temperature": 0.4, "maxOutputTokens": 500}}
        r = requests.post(GEMINI_API_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        if r.status_code == 200:
            c = r.json().get("candidates", [])
            if c:
                return jsonify({"status": "success", "response": c[0]["content"]["parts"][0]["text"]})
        return jsonify({"status": "error", "response": "ขออภัยครับ ตอนนี้เชื่อมต่อ AI ไม่ได้ ลองใหม่อีกครั้งนะครับ"})
    except Exception as e:
        return jsonify({"status": "error", "response": f"ระบบขัดข้อง: {e}"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

# ==========================================
# 🔑 กุญแจ API — ตั้งเป็น Environment Variable (ห้ามฝังในโค้ด)
#   GEMINI_API_KEY=...   GOOGLE_MAPS_API_KEY=...
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)
API_CACHE = {}
GEO_CACHE = {}
CITY = (16.4828, 99.5227)

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
    "ตัวเมืองกำแพงเพชร": (16.4828, 99.5227),
    "อุทยานประวัติศาสตร์": (16.4928, 99.5153),
    "น้ำตกคลองลาน": (16.1303, 99.2811),
    "ช่องเย็น": (16.0991, 99.1068),
    "แม่วงก์": (16.0991, 99.1068),
    "บ่อน้ำพุร้อนพระร่วง": (16.3216, 99.6648),
    "ตลาดย้อนยุคนครชุม": (16.4851, 99.5103),
}

# ราคาตั้งต้นของแต่ละประเภท (บาท) — ผู้ใช้แก้ไขเองได้ในหน้าผลลัพธ์
DEFAULT_PRICE = {"TEMPLE": 20, "HISTORY": 20, "NATURE": 40, "FOOD": 120,
                 "CAFE": 100, "MARKET": 100, "HOTEL": 0, "OTHER": 50}
VALID_ICONS = set(DEFAULT_PRICE)


def geocode_location(name):
    if name in GEO_CACHE:
        return GEO_CACHE[name]
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": name, "key": GOOGLE_MAPS_API_KEY, "language": "th"},
            timeout=3,
        )
        data = r.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            GEO_CACHE[name] = (loc["lat"], loc["lng"])
            return GEO_CACHE[name]
    except Exception:
        pass
    return None


def parse_location(text):
    """คืน (ชื่อ, lat, lng) จากข้อความ: พิกัด / ชื่อที่รู้จัก / geocode / กลางเมือง"""
    text = (text or "").strip() or "ตัวเมืองกำแพงเพชร"
    m = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", text)
    if m:
        return text, float(m.group(1)), float(m.group(2))
    for key, (la, ln) in KNOWN_LOCATIONS.items():
        if key in text:
            return text, la, ln
    g = geocode_location(text)
    if g:
        return text, g[0], g[1]
    return text, CITY[0], CITY[1]


def fetch_live_places(keyword):
    if keyword in API_CACHE:
        return API_CACHE[keyword]
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": keyword, "language": "th", "region": "th", "key": GOOGLE_MAPS_API_KEY},
            timeout=5,
        )
        data = r.json()
        results = []
        if data.get("status") == "OK":
            for p in data["results"]:
                addr = p.get("formatted_address", "").lower()
                if "กำแพง" not in addr and "kamphaeng" not in addr:
                    continue
                if p.get("user_ratings_total", 0) <= 3:
                    continue
                loc = p["geometry"]["location"]
                results.append(f"- {p.get('name', 'ไม่ระบุชื่อ')} (⭐ {p.get('rating', '-')}) | พิกัด: {loc['lat']}, {loc['lng']}")
                if len(results) >= 20:
                    break
        if results:
            random.shuffle(results)
            API_CACHE[keyword] = "\n".join(results)
            return API_CACHE[keyword]
    except Exception:
        pass
    return "ไม่มีข้อมูล"


def haversine_km(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = p2 - p1
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def guess_icon(text):
    if re.search(r"(โรงแรม|รีสอร์ท|โฮมสเตย์|ที่พัก|นอน)", text): return "HOTEL"
    if re.search(r"(คาเฟ่|กาแฟ|cafe)", text, re.I): return "CAFE"
    if re.search(r"(อาหาร|ร้าน|ก๋วยเตี๋ยว|บะหมี่|ข้าว|เตี๋ยว|ผัดไทย|เต้าฮวย)", text): return "FOOD"
    if re.search(r"(วัด|พระ|ศาล)", text): return "TEMPLE"
    if re.search(r"(พิพิธภัณฑ์|พิพิธภัณฑ|ประวัติศาสตร์|เมืองโบราณ)", text): return "HISTORY"
    if re.search(r"(น้ำตก|อุทยาน|ธรรมชาติ|เขา|ช่องเย็น|แก่ง|น้ำพุร้อน)", text): return "NATURE"
    if re.search(r"(ตลาด|ถนนคนเดิน)", text): return "MARKET"
    return "OTHER"


def parse_plan(ai_text, consumption, fuel_price):
    """แปลงข้อความดิบจาก AI เป็น list ของจุดแวะ (dict) พร้อมคำนวณค่าน้ำมันจากระยะทางจริง"""
    stops, prev = [], {}
    text = ai_text.replace("```", "").replace("*", "")
    for line in text.split("\n"):
        m = re.search(r"DAY_(\d+)", line.upper())
        if "|" not in line or not m:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue
        day = int(m.group(1))
        name = re.sub(r"ICON_[A-Z_]+", "", parts[4]).strip()
        if not name or "ไม่พบข้อมูล" in name:
            continue

        icon = parts[3].upper().replace("ICON_", "")
        if icon not in VALID_ICONS:
            icon = guess_icon(name + " " + parts[5])

        try:
            lat, lng = float(parts[6]), float(parts[7])
            if lat > 50 and lng < 50:
                lat, lng = lng, lat
        except ValueError:
            lat, lng = CITY
        is_endpoint = bool(re.search(r"(เริ่มต้น|สิ้นสุด|เดินทาง|จุดเริ่ม)", name))
        if not is_endpoint and not (15.0 <= lat <= 17.5 and 98.5 <= lng <= 100.5):
            lat, lng = CITY

        price = 0 if is_endpoint else DEFAULT_PRICE.get(icon, 50)
        fuel = 0
        if day in prev and not is_endpoint:
            km = haversine_km(prev[day][0], prev[day][1], lat, lng) * 1.3  # ชดเชยทางจริงที่อ้อมกว่าเส้นตรง
            fuel = round(km / max(consumption, 1) * fuel_price)
        prev[day] = (lat, lng)

        stops.append({
            "day": day, "time": parts[1], "travel": parts[2], "icon": icon,
            "name": name, "cat": parts[5] or "ทั่วไป", "lat": round(lat, 6), "lng": round(lng, 6),
            "price": price, "fuel": fuel,
        })
    return stops


def to_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/plan", methods=["GET", "POST"])
def plan_trip():
    if request.method == "GET":
        return redirect(url_for("index"))
    try:
        f = request.form
        num_days = min(max(int(f.get("num_days", "1")), 1), 4)
        start_time = f.get("daily_start_time", "09:00")
        end_time = f.get("daily_end_time", "18:00")
        daily_budget = max(int(to_float(f.get("daily_budget"), 1500)), 1000)
        hotel_budget = f.get("hotel_budget", "1000")
        consumption = to_float(f.get("fuel_consumption"), 15)
        fuel_price = to_float(f.get("fuel_price"), 37.5)
        vehicle = f.get("vehicle_type", "รถเก๋ง")

        place_styles = f.getlist("place_styles")
        food_styles = f.getlist("food_styles")
        str_places = "ยอดฮิต" if (not place_styles or "AI_Select" in place_styles) else " ".join(place_styles)
        str_foods = "อร่อย โลคอล" if (not food_styles or "AI_Select" in food_styles) else " ".join(food_styles)

        s_name, s_lat, s_lng = parse_location(f.get("start_loc"))
        end_raw = (f.get("end_loc") or "").strip()
        e_name, e_lat, e_lng = parse_location(end_raw) if end_raw else (s_name, s_lat, s_lng)

        queries = [
            f"ที่เที่ยว {str_places} สถานที่ลับ Unseen กำแพงเพชร",
            "อุทยาน ธรรมชาติ น้ำตก จุดชมวิว กำแพงเพชร",
            f"ร้านอาหาร คาเฟ่ ร้านลับ โลคอล {str_foods} กำแพงเพชร",
            "โรงแรม รีสอร์ท โฮมสเตย์ กำแพงเพชร",
        ]
        with concurrent.futures.ThreadPoolExecutor() as ex:
            res = list(ex.map(fetch_live_places, queries))
        fallbacks = [FALLBACK_MAIN, FALLBACK_NATURE, FALLBACK_FOOD, FALLBACK_HOTEL]
        db = [r if "ไม่มีข้อมูล" not in r else fb for r, fb in zip(res, fallbacks)]

        routing = "".join(
            f"[DAY_{i}] เริ่ม: '{s_name}' (พิกัด: {s_lat}, {s_lng}), จบ: '{e_name}' (พิกัด: {e_lat}, {e_lng}), "
            f"เวลา {start_time}-{end_time}\n"
            for i in range(1, num_days + 1)
        )

        prompt = f"""
        คุณคือระบบจัดตารางทริปอัจฉริยะ ประจำ "จังหวัดกำแพงเพชร"
        ห้ามอธิบาย ห้ามใส่หัวตาราง ตอบเป็นข้อมูลดิบ | คั่นเท่านั้น!

        [ฐานข้อมูลสถานที่]
        (หมวด 1: ที่เที่ยวในเมือง/Unseen)
        {db[0]}
        (หมวด 2: ธรรมชาติ/นอกเมือง)
        {db[1]}
        (หมวด 3: ร้านอาหาร/คาเฟ่/ร้านลับโลคอล)
        {db[2]}
        (หมวด 4: ที่พัก)
        {db[3]}

        [ความชอบของลูกค้า] ที่เที่ยว: {str_places} | กิน: {str_foods}
        [พาหนะ] {vehicle} | งบต่อวัน {daily_budget} บาท | งบที่พักต่อคืน {hotel_budget} บาท
        [จุดบังคับรายวัน]
        {routing}

        [คำสั่งบังคับ]
        1. เลือกสถานที่จากฐานข้อมูลเท่านั้น และห้ามใช้สถานที่ซ้ำข้ามวัน
        2. ผสมสถานที่ดังกับสถานที่แปลกใหม่ (Unseen) / ร้านโลคอลลับ
        3. 1 วันมี 6-8 คิว เรียงตามเวลา: เริ่ม -> เที่ยว -> กิน -> ธรรมชาติ/เที่ยวลับ -> คาเฟ่ -> จบ
        4. คิวแรกของวันคือจุดเริ่มต้น คิวสุดท้ายคือจุดสิ้นสุด ใช้ชื่อและพิกัดตามที่บังคับ (ชื่อควรมีคำว่า "เริ่มต้น" หรือ "สิ้นสุด")
        5. ระยะเวลาขับรถให้กะตามจริง (เช่น 20 นาที, 1 ชม.) ห้ามใส่ 0 นาทีรวด
        6. รหัสไอคอนเลือกจาก: ICON_TEMPLE ICON_HISTORY ICON_NATURE ICON_FOOD ICON_CAFE ICON_MARKET ICON_HOTEL ICON_OTHER
        7. รูปแบบ: DAY_X | เวลา | ระยะเวลาขับรถ | รหัสไอคอน | ชื่อสถานที่ | ประเภท | พิกัดLat | พิกัดLng
        """
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.6}}
                try:
                    resp = requests.post(GEMINI_API_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=100)
                except requests.exceptions.Timeout:
                    return render_template("index.html", error="AI ใช้เวลาตอบนานเกินไป ลองกดสร้างแผนอีกครั้ง หรือลดจำนวนวันลง"), 504
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text[:200]
            return render_template("index.html", error=f"AI ตอบกลับผิดพลาด (รหัส {resp.status_code}): {detail}"), 502

        candidates = resp.json().get("candidates", [])
        if not candidates:
            return render_template("index.html", error="AI ไม่ตอบกลับ ลองกดสร้างแผนอีกครั้ง"), 502

        stops = parse_plan(candidates[0]["content"]["parts"][0]["text"], consumption, fuel_price)
        if not stops:
            return render_template("index.html", error="AI ส่งข้อมูลมาในรูปแบบที่อ่านไม่ได้ ลองกดสร้างแผนอีกครั้ง"), 502

        return render_template("result.html", plan=stops, num_days=num_days,
                               daily_budget=daily_budget, maps_key=GOOGLE_MAPS_API_KEY)
    except Exception as e:
        return render_template("index.html", error=f"เกิดข้อผิดพลาด: {e}"), 500


@app.route("/api/chat", methods=["POST"])
def chat_with_ai():
    try:
        message = (request.json or {}).get("message", "")
        prompt = f"""
        คุณคือ 'น้องไกด์' ประจำ "จังหวัดกำแพงเพชร"
        กฎเหล็ก: แนะนำเฉพาะสถานที่ในกำแพงเพชรเท่านั้น! ตอบสั้น กระชับ เป็นกันเอง
        คำถาม: {message}
        """
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"temperature": 0.4, "maxOutputTokens": 500}}
        r = requests.post(GEMINI_API_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        if r.status_code == 200:
            c = r.json().get("candidates", [])
            if c:
                return jsonify({"status": "success", "response": c[0]["content"]["parts"][0]["text"]})
        return jsonify({"status": "error", "response": "ขออภัยครับ ตอนนี้เชื่อมต่อ AI ไม่ได้ ลองใหม่อีกครั้งนะครับ"})
    except Exception as e:
        return jsonify({"status": "error", "response": f"ระบบขัดข้อง: {e}"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
