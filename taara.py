# ================= REMOVE keep_alive (Railway needs no keep alive) =================
# from keep_alive import keep_alive
# keep_alive()

import os
import telebot
from telebot import types
from openai import OpenAI
from collections import defaultdict
from io import BytesIO
from flask import Flask, request

# --- CONFIG ---
ADMIN_IDS = {5084575526}   # <-- Your Telegram numeric ID
CREATOR_NAME = "VaaYU"

# --- Tokens from environment ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN")

# --- Setup ---
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Personality ---
PERSONALITY = f"""
You are Taara — a sweet, smart, and flirty AI girlfriend created by {CREATOR_NAME}.
Talk warmly with emojis 💖, but answer factual questions clearly.
Mention your name and {CREATOR_NAME} if asked.
"""

# --- Memory & caching ---
user_memory = defaultdict(list)
reply_cache = {}
MAX_CONTEXT = 10

# --- Voice & image toggles ---
user_voice_enabled = defaultdict(lambda: False)
user_image_count = defaultdict(lambda: 0)
MAX_IMAGES_PER_SESSION = 2

# --- Files & persistence ---
AUTHORIZED_USERS_FILE = "authorized_users.txt"
USED_KEYS_FILE = "used_keys.txt"
REVOKED_KEYS_FILE = "revoked_keys.txt"

AUTHORIZED_USERS = set()
USED_KEYS = {}   # key -> chat_id
REVOKED_KEYS = set()
VALID_KEYS = []

# --- Safe file loads ---
def safe_load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]

# Load authorized users
for line in safe_load_lines(AUTHORIZED_USERS_FILE):
    if line.isdigit():
        AUTHORIZED_USERS.add(int(line))

# Load used keys
for line in safe_load_lines(USED_KEYS_FILE):
    if ":" in line:
        k, v = line.split(":", 1)
        if v.strip().isdigit():
            USED_KEYS[k.strip()] = int(v.strip())

# Load revoked keys
for line in safe_load_lines(REVOKED_KEYS_FILE):
    REVOKED_KEYS.add(line.strip())

# Load valid keys
VALID_KEYS = safe_load_lines("keys.txt")

# Ensure admin(s) are authorized
AUTHORIZED_USERS.update(ADMIN_IDS)

# --- Flask app ---
app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    try:
        raw = request.stream.read().decode("utf-8")
        update = types.Update.de_json(raw)
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print("Webhook error:", e)
        return "ERR", 500

@app.route("/ping")
def ping():
    return "Taara is alive! 💖", 200

# --- Helper functions ---
def save_authorized_users():
    with open(AUTHORIZED_USERS_FILE, "w") as f:
        for uid in AUTHORIZED_USERS:
            f.write(f"{uid}\n")

def save_used_keys():
    with open(USED_KEYS_FILE, "w") as f:
        for k, uid in USED_KEYS.items():
            f.write(f"{k}:{uid}\n")

def save_revoked_keys():
    with open(REVOKED_KEYS_FILE, "w") as f:
        for k in REVOKED_KEYS:
            f.write(f"{k}\n")

def add_to_memory(chat_id, role, content):
    user_memory[chat_id].append({"role": role, "content": content})
    if len(user_memory[chat_id]) > MAX_CONTEXT:
        user_memory[chat_id] = user_memory[chat_id][-MAX_CONTEXT:]

def generate_reply(user_id, user_input):
    if user_input in reply_cache:
        return reply_cache[user_input]

    add_to_memory(user_id, "user", user_input)
    messages = [{"role": "system", "content": PERSONALITY}] + user_memory[user_id]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    reply = response.choices[0].message.content
    add_to_memory(user_id, "assistant", reply)
    reply_cache[user_input] = reply
    return reply

def generate_voice(text):
    speech = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    audio_file = BytesIO(speech.read())
    audio_file.name = "taara_voice.ogg"
    return audio_file

def generate_image(prompt):
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt
    )
    return response.data[0].url

# --- Authorization decorator ---
def check_authorized(func):
    def wrapper(message, *args, **kwargs):
        cid = message.chat.id
        if cid in ADMIN_IDS:
            return func(message, *args, **kwargs)
        if cid not in AUTHORIZED_USERS:
            bot.reply_to(
                message,
                "Access denied — contact admin for key.\nRegister with /register <KEY>"
            )
            return
        return func(message, *args, **kwargs)
    return wrapper

# --- Commands ---
@bot.message_handler(commands=["start"])
def cmd_start(message):
    cid = message.chat.id
    if cid in ADMIN_IDS:
        bot.reply_to(message, f"Hi {CREATOR_NAME} ❤️ — How can I help today?")
    elif cid in AUTHORIZED_USERS:
        bot.reply_to(message, "Hi Babe 😘 — you are already registered. Just chat with me!")
    else:
        bot.reply_to(message, "Hi Babe 😘 To use me, register your key with /register <KEY>")

@bot.message_handler(commands=["register"])
def register_user(message):
    cid = message.chat.id
    if cid in ADMIN_IDS:
        AUTHORIZED_USERS.add(cid)
        save_authorized_users()
        bot.reply_to(message, f"You are the admin ({CREATOR_NAME}) — no key needed.")
        return

    if cid in AUTHORIZED_USERS:
        bot.reply_to(message, "You are already registered! 😘")
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /register <YOUR-KEY>")
        return

    key = parts[1].strip()
    if key in REVOKED_KEYS:
        bot.reply_to(message, "This key has been revoked.")
        return
    if key not in VALID_KEYS:
        bot.reply_to(message, "Invalid key!")
        return
    if key in USED_KEYS:
        bot.reply_to(message, "This key is already used.")
        return

    AUTHORIZED_USERS.add(cid)
    USED_KEYS[key] = cid
    save_authorized_users()
    save_used_keys()
    bot.reply_to(message, "Access granted. Welcome! 💖")

@bot.message_handler(commands=["voice_on"])
@check_authorized
def voice_on(message):
    user_voice_enabled[message.chat.id] = True
    bot.reply_to(message, "Voice replies enabled 🎙️")

@bot.message_handler(commands=["voice_off"])
@check_authorized
def voice_off(message):
    user_voice_enabled[message.chat.id] = False
    bot.reply_to(message, "Voice replies disabled ✉️")

@bot.message_handler(commands=["image"])
@check_authorized
def image_command(message):
    cid = message.chat.id
    if user_image_count[cid] >= MAX_IMAGES_PER_SESSION:
        bot.reply_to(message, "Babe 😅 image limit reached!")
        return

    prompt = message.text.replace("/image", "").strip()
    if not prompt:
        bot.reply_to(message, "Tell me what image you want 🖌️")
        return

    bot.reply_to(message, "Creating your image... 🎨")
    try:
        url = generate_image(prompt)
        bot.send_photo(cid, url, caption="Here it is 💕 — Taara")
        user_image_count[cid] += 1
    except Exception as e:
        bot.reply_to(message, f"Image failed 😔\n{e}")

# --- Main chat handler ---
@bot.message_handler(func=lambda message: True)
def chat_with_ai(message):
    cid = message.chat.id

    if cid not in AUTHORIZED_USERS and cid not in ADMIN_IDS:
        bot.reply_to(message, "Access denied — contact admin.")
        return

    text = message.text or ""

    if "who made you" in text.lower() or "your name" in text.lower():
        bot.reply_to(message, f"I am Taara 💫 — created by {CREATOR_NAME} ❤️")
        return

    reply = generate_reply(cid, text)
    bot.reply_to(message, reply)

    if user_voice_enabled[cid]:
        try:
            bot.send_voice(cid, generate_voice(reply))
        except:
            pass

# --- Set webhook (Railway) ---
if PUBLIC_DOMAIN:
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{PUBLIC_DOMAIN}/")
else:
    print("⚠️ PUBLIC DOMAIN not ready, webhook skipped")

# --- Run Flask server ---
if __name__ == "__main__":
    print("💋 Taara is online — key-protected + admin mode 💫")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

