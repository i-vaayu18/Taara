import os
import threading
import queue
import time
from collections import defaultdict
from io import BytesIO

import telebot
from openai import OpenAI
from flask import Flask, request

# ================= CONFIG =================
ADMIN_IDS = {5084575526}
CREATOR_NAME = "VaaYU"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
client = OpenAI(api_key=OPENAI_API_KEY)

# ================= PERSONALITY =================
PERSONALITY = f"""
You are Taara — a sweet, smart, and flirty AI assistant created by {CREATOR_NAME}.
Be warm with emojis 💖 but clear and helpful.
"""

# ================= MEMORY =================
user_memory = defaultdict(list)
reply_cache = {}
MAX_CONTEXT = 10   # ❗ unchanged
memory_lock = threading.Lock()

# ================= FEATURES =================
user_voice_enabled = defaultdict(lambda: False)
user_image_count = defaultdict(int)
MAX_IMAGES_PER_SESSION = 2

# ================= AUTH FILES =================
AUTHORIZED_USERS_FILE = "authorized_users.txt"
USED_KEYS_FILE = "used_keys.txt"
REVOKED_KEYS_FILE = "revoked_keys.txt"
KEYS_FILE = "keys.txt"

AUTHORIZED_USERS = set()
USED_KEYS = {}
REVOKED_KEYS = set()
VALID_KEYS = []

# ================= SAFE LOAD =================
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
VALID_KEYS = safe_load_lines(KEYS_FILE)

# ================= FLASK =================
app = Flask(__name__)
update_queue = queue.Queue()

@app.route("/", methods=["POST"])
def webhook():
    raw = request.stream.read().decode("utf-8")
    update_queue.put(raw)   # ✅ safe queue
    return "OK", 200        # ⚡ instant ACK

@app.route("/ping")
def ping():
    return "Taara alive 💖", 200

# ================= WORKER =================
def update_worker():
    while True:
        raw = update_queue.get()
        try:
            update = telebot.types.Update.de_json(raw)
            bot.process_new_updates([update])
        except Exception as e:
            print("Worker error:", e)
        finally:
            update_queue.task_done()

threading.Thread(target=update_worker, daemon=True).start()

# ================= TYPING FEEL =================
def typing_indicator(chat_id, stop_event):
    while not stop_event.is_set():
        try:
            bot.send_chat_action(chat_id, "typing")
        except:
            pass
        time.sleep(3)

# ================= MEMORY SAFE =================
def add_to_memory(chat_id, role, content):
    with memory_lock:
        user_memory[chat_id].append({"role": role, "content": content})
        if len(user_memory[chat_id]) > MAX_CONTEXT:
            user_memory[chat_id] = user_memory[chat_id][-MAX_CONTEXT:]

# ================= AI =================
def generate_reply(chat_id, user_text):
    if user_text in reply_cache:
        return reply_cache[user_text]

    with memory_lock:
        user_memory[chat_id].append({"role": "user", "content": user_text})
        context = list(user_memory[chat_id])

    messages = [{"role": "system", "content": PERSONALITY}] + context

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    reply = response.choices[0].message.content

    with memory_lock:
        user_memory[chat_id].append({"role": "assistant", "content": reply})
        reply_cache[user_text] = reply

    return reply

def generate_voice(text):
    speech = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text
    )
    audio = BytesIO(speech.read())
    audio.name = "taara.ogg"
    return audio

def generate_image(prompt):
    img = client.images.generate(
        model="gpt-image-1",
        prompt=prompt
    )
    return img.data[0].url

# ================= AUTH DECORATOR =================
def check_authorized(func):
    def wrapper(message):
        cid = message.chat.id
        if cid in ADMIN_IDS or cid in AUTHORIZED_USERS:
            return func(message)
        bot.reply_to(message, "Access denied. Use /register <KEY>")
    return wrapper

# ================= COMMANDS =================
@bot.message_handler(commands=["start"])
def start(message):
    cid = message.chat.id
    if cid in AUTHORIZED_USERS:
        bot.reply_to(message, "Hi 😘 Just talk to me!")
    else:
        bot.reply_to(message, "Register with /register <KEY>")

@bot.message_handler(commands=["register"])
def register(message):
    cid = message.chat.id
    if cid in ADMIN_IDS:
        AUTHORIZED_USERS.add(cid)
        bot.reply_to(message, "Admin registered ✅")
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /register <KEY>")
        return

    key = parts[1]
    if key in REVOKED_KEYS or key not in VALID_KEYS or key in USED_KEYS:
        bot.reply_to(message, "Invalid or used key ❌")
        return

    AUTHORIZED_USERS.add(cid)
    USED_KEYS[key] = cid
    bot.reply_to(message, "Access granted 💖")

@bot.message_handler(commands=["reset"])
@check_authorized
def reset(message):
    cid = message.chat.id
    with memory_lock:
        user_memory[cid] = []
    bot.reply_to(message, "Memory reset 🔄")

@bot.message_handler(commands=["voice_on"])
@check_authorized
def voice_on(message):
    user_voice_enabled[message.chat.id] = True
    bot.reply_to(message, "Voice ON 🎙️")

@bot.message_handler(commands=["voice_off"])
@check_authorized
def voice_off(message):
    user_voice_enabled[message.chat.id] = False
    bot.reply_to(message, "Voice OFF ✉️")

@bot.message_handler(commands=["image"])
@check_authorized
def image_cmd(message):
    cid = message.chat.id
    if user_image_count[cid] >= MAX_IMAGES_PER_SESSION:
        bot.reply_to(message, "Image limit reached 😅")
        return
    prompt = message.text.replace("/image", "").strip()
    bot.reply_to(message, "Creating 🎨")
    url = generate_image(prompt)
    bot.send_photo(cid, url)
    user_image_count[cid] += 1

# ================= CHAT (WITH TYPING FEEL) =================
@bot.message_handler(func=lambda m: True)
def chat(message):
    cid = message.chat.id
    if cid not in AUTHORIZED_USERS and cid not in ADMIN_IDS:
        bot.reply_to(message, "Unauthorized ❌")
        return

    stop_event = threading.Event()
    typing_thread = threading.Thread(
        target=typing_indicator,
        args=(cid, stop_event),
        daemon=True
    )
    typing_thread.start()

    try:
        reply = generate_reply(cid, message.text)
        bot.reply_to(message, reply)

        if user_voice_enabled[cid]:
            try:
                bot.send_voice(cid, generate_voice(reply))
            except:
                pass
    finally:
        stop_event.set()

# ================= WEBHOOK =================
bot.remove_webhook()
bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/")

# ================= RUN =================
if __name__ == "__main__":
    print("Taara online 💖")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
