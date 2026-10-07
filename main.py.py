"""
بوت بصمة نُسيبه - @Naseebah_bot
نظام حضور وانصراف بالموقع - 3 فروع - 80 متر
النسخة المصححة - الأزرار تعمل 100%
"""

import os
import sqlite3
import math
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

BRANCHES = {
    "فرع ساحة دان": {"lat": 21.311746875, "lon": 39.51455625, "radius": 80},
    "فرع درايف ثرو العوالي": {"lat": 21.311863594, "lon": 39.51664031, "radius": 80},
    "فرع درايف ثرو الشوقيه": {"lat": 21.312759375, "lon": 39.39463125, "radius": 80},
}

EMPLOYEES = {
    "احمد": "فرع ساحة دان",
    "محمود": "فرع ساحة دان",
    "عبدالعزيز": "فرع ساحة دان",
    "نواف": "فرع درايف ثرو العوالي",
    "حنشون": "فرع درايف ثرو العوالي",
    "بدوي": "فرع درايف ثرو العوالي",
    "علي": "فرع درايف ثرو الشوقيه",
    "اسامه": "فرع درايف ثرو الشوقيه",
}

WORK_START = "08:00"
ALLOWED_LATE_MINUTES = 15
TEST_MODE = True  # خليه True للتجربة من أي مكان، False للتشغيل الحقيقي 80 متر

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def init_db():
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, name TEXT, branch TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, name TEXT, branch TEXT, date TEXT, check_in TEXT, check_out TEXT, check_in_lat REAL, check_in_lon REAL, check_out_lat REAL, check_out_lon REAL, status TEXT)")
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT name, branch FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return row

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing = get_user(user_id)
    if existing:
        name, branch = existing
        keyboard = [[KeyboardButton("📍 تسجيل حضور")],[KeyboardButton("🚪 تسجيل انصراف")],[KeyboardButton("📊 سجلي اليوم"), KeyboardButton("🏢 فروعي")]]
        await update.message.reply_text(f"أهلاً {name} 👋\nفرعك: {branch}\n\nاختر:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    else:
        keyboard = []
        names = list(EMPLOYEES.keys())
        for i in range(0, len(names), 2):
            row = [InlineKeyboardButton(names[j], callback_data=f"reg_{names[j]}") for j in range(i, min(i+2, len(names)))]
            keyboard.append(row)
        await update.message.reply_text("👋 أهلاً في بوت بصمة نُسيبه\nاختر اسمك:", reply_markup=InlineKeyboardMarkup(keyboard))

async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = query.data.replace("reg_", "")
    branch = EMPLOYEES.get(name, "فرع ساحة دان")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?)", (query.from_user.id, name, branch, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await query.edit_message_text(f"✅ تم تسجيلك: {name}\nفرعك: {branch}\n\nالآن ارسل /start")
    keyboard = [[KeyboardButton("📍 تسجيل حضور")],[KeyboardButton("🚪 تسجيل انصراف")],[KeyboardButton("📊 سجلي اليوم"), KeyboardButton("🏢 فروعي")]]
    await query.message.reply_text("اختر:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("سجل اسمك أولاً /start")
        return
    name, assigned_branch = user_data
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    closest_branch = None
    min_dist = float('inf')
    for b_name, b in BRANCHES.items():
        d = haversine(lat, lon, b["lat"], b["lon"])
        if d < min_dist:
            min_dist = d
            closest_branch = b_name
    action = context.user_data.get("action", "in")
    allowed_radius = BRANCHES[closest_branch]["radius"]
    
    # في وضع التجربة يسمح حتى لو بعيد
    if not TEST_MODE and min_dist > allowed_radius:
        await update.message.reply_text(f"❌ أنت بعيد\nأقرب فرع: {closest_branch}\nالمسافة: {int(min_dist)}م\nالمطلوب: {allowed_radius}م\n\nفعّل GPS وتأكد داخل الفرع")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")
    now_time = datetime.now()
    work_time = datetime.strptime(WORK_START, "%H:%M").replace(year=now_time.year, month=now_time.month, day=now_time.day)
    late_limit = work_time + timedelta(minutes=ALLOWED_LATE_MINUTES)
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    if action == "in":
        c.execute("SELECT id FROM attendance WHERE telegram_id=? AND date=? AND check_in IS NOT NULL", (user_id, today))
        if c.fetchone():
            await update.message.reply_text("⚠️ مسجل حضور اليوم")
            conn.close()
            return
        status = "متأخر" if now_time > late_limit else "حاضر"
        if TEST_MODE and min_dist > allowed_radius:
            status += f" (تجربة - بعيد {int(min_dist)}م)"
        c.execute("INSERT INTO attendance (telegram_id, name, branch, date, check_in, check_in_lat, check_in_lon, status) VALUES (?,?,?,?,?,?,?,?)",
                  (user_id, name, closest_branch, today, now_str, lat, lon, status))
        conn.commit()
        await update.message.reply_text(f"✅ تم تسجيل الحضور\n👤 {name}\n🏢 {closest_branch}\n⏰ {now_str}\n📍 {int(min_dist)}م\n📌 {status}")
    else:
        c.execute("SELECT id, check_in, check_out FROM attendance WHERE telegram_id=? AND date=? ORDER BY id DESC LIMIT 1", (user_id, today))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("❌ ما سجلت حضور اليوم")
            conn.close()
            return
        if row[2]:
            await update.message.reply_text("⚠️ مسجل انصراف already")
            conn.close()
            return
        c.execute("UPDATE attendance SET check_out=?, check_out_lat=?, check_out_lon=? WHERE id=?", (now_str, lat, lon, row[0]))
        conn.commit()
        check_in_time = datetime.strptime(row[1], "%H:%M:%S")
        check_out_time = datetime.strptime(now_str, "%H:%M:%S")
        diff = (check_out_time - check_in_time).total_seconds() / 3600
        await update.message.reply_text(f"✅ انصراف\n👤 {name}\n🏢 {closest_branch}\n⏰ {now_str}\n⏱️ {diff:.1f} ساعة")
    conn.close()

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if "حضور" in text:
        context.user_data["action"] = "in"
        await update.message.reply_text("📍 الآن أرسل موقعك بالضغط على الزر:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 إرسال موقعي الحالي", request_location=True)]], resize_keyboard=True))
    elif "انصراف" in text:
        context.user_data["action"] = "out"
        await update.message.reply_text("📍 الآن أرسل موقعك:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 إرسال موقعي الحالي", request_location=True)]], resize_keyboard=True))
    elif "سجلي" in text:
        user_id = update.effective_user.id
        conn = sqlite3.connect("attendance.db")
        c = conn.cursor()
        c.execute("SELECT date, check_in, check_out, branch, status FROM attendance WHERE telegram_id=? ORDER BY date DESC LIMIT 7", (user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("لا يوجد سجل")
        else:
            msg = "📊 آخر 7 أيام:\n\n"
            for r in rows:
                msg += f"{r[0]} | {r[3]}\nدخول: {r[1] or '-'} خروج: {r[2] or '-'} ({r[4]})\n---\n"
            await update.message.reply_text(msg)
    elif "فروعي" in text:
        msg = "🏢 فروع نُسيبه (80م):\n\n"
        for bname, bdata in BRANCHES.items():
            msg += f"📍 {bname}\n"
        msg += "\nTEST_MODE=True يعني يقبل من أي مكان للتجربة"
        await update.message.reply_text(msg)
    else:
        keyboard = [[KeyboardButton("📍 تسجيل حضور")],[KeyboardButton("🚪 تسجيل انصراف")],[KeyboardButton("📊 سجلي اليوم"), KeyboardButton("🏢 فروعي")]]
        await update.message.reply_text("اختر:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT name, branch, check_in, check_out, status FROM attendance WHERE date=?", (today,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"لا يوجد حضور {today}")
        return
    msg = f"📋 تقرير {today}:\n\n"
    for r in rows:
        msg += f"👤 {r[0]} ({r[1]})\n⏰ {r[2]} -> {r[3] or 'لم ينصرف'} | {r[4]}\n---\n"
    await update.message.reply_text(msg)

def main():
    init_db()
    if not BOT_TOKEN:
        print("❌ ضع BOT_TOKEN في .env")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CallbackQueryHandler(register_callback, pattern="^reg_"))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ بوت نُسيبه شغال - 80م - TEST_MODE", TEST_MODE)
    app.run_polling()

if __name__ == "__main__":
    main()
