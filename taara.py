# ================= Railway compatible (no keep_alive) =================

import os
import time
import telebot
from telebot import types
from openai import OpenAI
from collections import defaultdict
from io import BytesIO
from flask import Flask, request

# ---------------- CONFIG ----------------
ADMIN_IDS = {5084575526}
CREATOR_NAME = "VaaYU"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN")

# ---------------- SETUP ----------------
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- PERSONALITY ----------------
PERSONALITY = f"""
You are Taara — a sweet, smart, and flirty AI girlfriend created by {CREATOR_NAME}.
Talk warmly with emojis 💖, but answer factual questions clearly.
Mention your name and {CREATOR_NAME} if asked.
"""

# ---------------- MEMORY ----------------
user_memory = defaultdict(list)
reply_cache = {}
MAX_CONTEXT = 10

# ---------------- TOGGLES ----------------
user_voice_enabled = defaultdict(lambda: False)
user_image_count = defaultdict(int)
MAX_IMAGES_PER_SESSION = 2

# ---------------- FILES ----------------
AUTHORIZED_USERS_FILE = "authorized_users.txt"
USED_KEYS_FILE = "used_keys.txt"
REVOKED_KEYS_FILE = "revoked_keys.txt"

AUTHORIZED_USERS = set()
USED_KEYS = {}
REVOKED_KEYS = set()
VALID_KEYS = []

# ---------------- FILE LOADERS ----------------
def safe_load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [l.strip() for l in f if l.strip()]

AUTHORIZED_USERS.update(int(x) for x in safe_load_lines(AUTHORIZED_USERS_FILE) if x.isdigit())
AUTHORIZED_USERS.update(ADMIN_IDS)

for line in safe_load_lines(USED_KEYS_FILE):
    if ":" in line:
        k, v = line.split(":", 1)
        if v.isdigit():
            USED_KEYS[k] = int(v)

REVOKED_KEYS.update(safe_load_lines(REVOKED_KEYS_FILE))
VALID_KEYS = safe_load_lines("keys.txt")

# ---------------- FLASK ----------------
app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    try:
        update = types.Update.de_json(request.stream.read().decode("utf-8"))
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("Webhook error:", e)
        return "ERR", 500

@app.route("/ping")
def ping():
    return "Taara is alive 💖", 200

# ---------------- HELPERS ----------------
def typing(chat_id, t=1.2):
    bot.send_chat_action(chat_id, "typing")
    time.sleep(t)

def save_file(path, lines):
    with open(path, "w") as f:
        for l in lines:
            f.write(f"{l}\n")

def add_memory(cid, role, content):
    user_memory[cid].append({"role": role, "content": content})
    user_memory[cid] = user_memory[cid][-MAX_CONTEXT:]

def generate_reply(cid, text):
    if text in reply_cache:
        return reply_cache[text]

    add_memory(cid, "user", text)
    messages = [{"role": "system", "content": PERSONALITY}] + user_memory[cid]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    reply = response.choices[0].message.content
    add_memory(cid, "assistant", reply)
    reply_cache[text] = reply
    return reply

# ---------------- AUTH DECORATOR ----------------
def check_auth(func):
    def wrapper(message):
        cid = message.chat.id
        if cid in ADMIN_IDS or cid in AUTHORIZED_USERS:
            return func(message)
        bot.reply_to(message, "Access denied ❌\n/register <KEY>")
    return wrapper

# ---------------- COMMANDS ----------------
@bot.message_handler(commands=["start"])
def start(message):
    cid = message.chat.id
    typing(cid)
    if cid in ADMIN_IDS:
        bot.reply_to(message, f"Hi {CREATOR_NAME} ❤️")
    elif cid in AUTHORIZED_USERS:
        bot.reply_to(message, "Hi Babe 😘")
    else:
        bot.reply_to(message, "Register with /register <KEY>")

@bot.message_handler(commands=["register"])
def register(message):
    cid = message.chat.id
    parts = message.text.split()

    if cid in ADMIN_IDS:
        AUTHORIZED_USERS.add(cid)
        save_file(AUTHORIZED_USERS_FILE, AUTHORIZED_USERS)
        bot.reply_to(message, "Admin registered ✅")
        return

    if len(parts) < 2:
        bot.reply_to(message, "Usage: /register <KEY>")
        return

    key = parts[1]
    if key in REVOKED_KEYS or key not in VALID_KEYS or key in USED_KEYS:
        bot.reply_to(message, "Invalid or used key ❌")
        return

    AUTHORIZED_USERS.add(cid)
    USED_KEYS[key] = cid
    save_file(AUTHORIZED_USERS_FILE, AUTHORIZED_USERS)
    save_file(USED_KEYS_FILE, [f"{k}:{v}" for k, v in USED_KEYS.items()])
    bot.reply_to(message, "Access granted 💖")

@bot.message_handler(commands=["commands"])
@check_auth
def commands(message):
    bot.reply_to(message,
        "/start\n/reset\n/voice_on\n/voice_off\n/image <prompt>\n"
        "/createkey <key> (admin)\n/revoke <id> (admin)\n/list_users (admin)"
    )

@bot.message_handler(commands=["reset"])
@check_auth
def reset(message):
    user_memory[message.chat.id] = []
    bot.reply_to(message, "Memory reset 🔄")

@bot.message_handler(commands=["createkey"])
def createkey(message):
    if message.chat.id not in ADMIN_IDS:
        return
    key = message.text.split(maxsplit=1)[1]
    VALID_KEYS.append(key)
    save_file("keys.txt", VALID_KEYS)
    bot.reply_to(message, f"Key created ✅ {key}")

@bot.message_handler(commands=["revoke"])
def revoke(message):
    if message.chat.id not in ADMIN_IDS:
        return
    uid = int(message.text.split()[1])
    AUTHORIZED_USERS.discard(uid)
    save_file(AUTHORIZED_USERS_FILE, AUTHORIZED_USERS)
    bot.reply_to(message, f"User {uid} revoked ❌")

@bot.message_handler(commands=["list_users"])
def list_users(message):
    if message.chat.id not in ADMIN_IDS:
        return
    bot.reply_to(message, "\n".join(str(u) for u in AUTHORIZED_USERS))

# ---------------- CHAT ----------------
@bot.message_handler(func=lambda m: True)
def chat(message):
    cid = message.chat.id
    if cid not in AUTHORIZED_USERS and cid not in ADMIN_IDS:
        bot.reply_to(message, "Access denied ❌")
        return

    typing(cid, 0.2)
    reply = generate_reply(cid, message.text)
    bot.reply_to(message, reply)

# ---------------- WEBHOOK ----------------
if PUBLIC_DOMAIN:
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{PUBLIC_DOMAIN}/")
else:
    print("⚠️ PUBLIC DOMAIN not ready")

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("💋 Taara is online — key-protected + admin mode 💫")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

