from keep_alive import keep_alive
keep_alive()
import os
import telebot
from openai import OpenAI
from collections import defaultdict
from io import BytesIO
from flask import Flask, request

# --- CONFIG ---
ADMIN_IDS = {5084575526}  # <-- Replace with your Telegram numeric ID(s)
CREATOR_NAME = "VaaYU"   # Bot will recognize creator/admin with this name

# --- Tokens from environment ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# --- Setup ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
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

# load authorized users
for line in safe_load_lines(AUTHORIZED_USERS_FILE):
    if line.isdigit():
        AUTHORIZED_USERS.add(int(line))

# load used keys
for line in safe_load_lines(USED_KEYS_FILE):
    if ":" in line:
        k, v = line.split(":", 1)
        k = k.strip(); v = v.strip()
        if v.isdigit():
            USED_KEYS[k] = int(v)

# load revoked keys
for line in safe_load_lines(REVOKED_KEYS_FILE):
    REVOKED_KEYS.add(line.strip())

# load valid keys
VALID_KEYS = safe_load_lines("keys.txt")

# ensure admin(s) are authorized on startup
AUTHORIZED_USERS.update(ADMIN_IDS)

# --- Flask app ---
app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    try:
        raw = request.stream.read().decode("utf-8")
        update = telebot.types.Update.de_json(raw)
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
    context = user_memory[user_id]
    messages = [{"role": "system", "content": PERSONALITY}] + context

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
    audio_bytes = speech.read()
    audio_file = BytesIO(audio_bytes)
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
        chat_id = message.chat.id
        if chat_id in ADMIN_IDS:
            return func(message, *args, **kwargs)
        if chat_id not in AUTHORIZED_USERS:
            bot.reply_to(message, "Access denied — contact admin for key.\nRegister with /register <KEY>")
            return
        return func(message, *args, **kwargs)
    return wrapper

# --- Commands ---
@bot.message_handler(commands=['start'])
def cmd_start(message):
    chat_id = message.chat.id
    if chat_id in ADMIN_IDS:
        bot.reply_to(message, f"Hi {CREATOR_NAME} ❤️ — How can I help today?")
        return
    if chat_id in AUTHORIZED_USERS:
        bot.reply_to(message, "Hi Babe 😘 — you are already registered. Just chat with me!")
    else:
        bot.reply_to(message, "Hi Babe 😘 To use me, register your key with /register <KEY>")

@bot.message_handler(commands=['register'])
def register_user(message):
    chat_id = message.chat.id
    if chat_id in ADMIN_IDS:
        AUTHORIZED_USERS.add(chat_id)
        save_authorized_users()
        bot.reply_to(message, f"You are the admin ({CREATOR_NAME}) — no key needed.")
        return

    if chat_id in AUTHORIZED_USERS:
        bot.reply_to(message, "You are already registered! 😘")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /register <YOUR-KEY>")
        return

    key = parts[1].strip()
    if key in REVOKED_KEYS:
        bot.reply_to(message, "This key has been revoked. Contact admin for a new key.")
        return
    if key not in VALID_KEYS:
        bot.reply_to(message, "Invalid key! Contact admin.")
        return
    if key in USED_KEYS:
        bot.reply_to(message, "This key has already been used by another user.")
        return

    AUTHORIZED_USERS.add(chat_id)
    USED_KEYS[key] = chat_id
    save_authorized_users()
    save_used_keys()
    bot.reply_to(message, "Access granted. Welcome!")

@bot.message_handler(commands=['createkey'])
def create_key(message):
    if message.chat.id not in ADMIN_IDS:
        bot.reply_to(message, "You are not authorized to use this command.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /createkey <NEW-KEY>")
        return
    new_key = parts[1].strip()
    if new_key in VALID_KEYS:
        bot.reply_to(message, f"This key already exists ❌")
        return
    VALID_KEYS.append(new_key)
    with open("keys.txt", "a") as f:
        f.write(f"{new_key}\n")
    bot.reply_to(message, f"✅ New key created: {new_key}")

@bot.message_handler(commands=['revoke'])
def revoke_user(message):
    chat_id = message.chat.id
    if chat_id not in ADMIN_IDS:
        bot.reply_to(message, "You are not authorized to use this command.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /revoke <USER_CHAT_ID> [KEY]")
        return
    uid = int(parts[1])
    if uid in AUTHORIZED_USERS:
        AUTHORIZED_USERS.remove(uid)
    # optional key revoke
    if len(parts) == 3:
        key = parts[2]
        REVOKED_KEYS.add(key)
        save_revoked_keys()
    save_authorized_users()
    bot.reply_to(message, f"User {uid} revoked successfully! ❌")

@bot.message_handler(commands=['list_users'])
def list_users(message):
    chat_id = message.chat.id
    if chat_id not in ADMIN_IDS:
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    text = "💌 Full User Report:\n\n"

    text += "👑 Admins:\n"
    for aid in ADMIN_IDS:
        text += f"- {aid}\n"

    text += "\n🙋 Authorized Users:\n"
    for uid in AUTHORIZED_USERS:
        if uid not in ADMIN_IDS:
            keys_used = [k for k, v in USED_KEYS.items() if v == uid]
            keys_str = ", ".join(keys_used) if keys_used else "No key recorded"
            text += f"- {uid} (Keys: {keys_str})\n"

    text += "\n❌ Revoked Keys:\n"
    text += ", ".join(REVOKED_KEYS) if REVOKED_KEYS else "None"

    bot.reply_to(message, text)

@bot.message_handler(commands=['commands'])
@check_authorized
def show_commands(message):
    cmds = (
        "/start - say hi 👋\n"
        "/register <KEY> - register your key 🔑\n"
        "/reset - clear memory 🔄\n"
        "/voice_on - enable voice replies 🎙️\n"
        "/voice_off - disable voice ✉️\n"
        "/image <prompt> - generate image 🖼️\n"
        "/revoke <USER_CHAT_ID> [key] - admin only 🚨\n"
        "/list_users - admin only 👥\n"
        "/createkey <KEY> - admin only 🔑\n"
        "/commands - show this list 📝"
    )
    bot.reply_to(message, cmds)

@bot.message_handler(commands=['reset'])
@check_authorized
def reset_memory(message):
    chat_id = message.chat.id
    user_memory[chat_id] = []
    user_image_count[chat_id] = 0
    bot.reply_to(message, "Memory reset! 😘 Taara is fresh!")

@bot.message_handler(commands=['voice_on'])
@check_authorized
def voice_on(message):
    user_voice_enabled[message.chat.id] = True
    bot.reply_to(message, "Voice replies enabled 🎙️")

@bot.message_handler(commands=['voice_off'])
@check_authorized
def voice_off(message):
    user_voice_enabled[message.chat.id] = False
    bot.reply_to(message, "Voice replies disabled ✉️")

@bot.message_handler(commands=['image'])
@check_authorized
def image_command(message):
    chat_id = message.chat.id
    if user_image_count[chat_id] >= MAX_IMAGES_PER_SESSION:
        bot.reply_to(message, "Babe 😅 you reached your free image limit!")
        return
    prompt = message.text.replace("/image", "").strip()
    if not prompt:
        bot.reply_to(message, "Tell me what image you want 🖌️")
        return
    bot.reply_to(message, "Creating your image... 🎨")
    try:
        url = generate_image(prompt)
        bot.send_photo(chat_id, url, caption="Here it is 💕 — Taara")
        user_image_count[chat_id] += 1
    except Exception as e:
        bot.reply_to(message, f"Oops, image creation failed 😔\n{e}")

# --- Main chat handler ---
@bot.message_handler(func=lambda message: True)
def chat_with_ai(message):
    chat_id = message.chat.id
    if chat_id not in AUTHORIZED_USERS and chat_id not in ADMIN_IDS:
        bot.reply_to(message, "Access denied — contact admin for key.\nRegister with /register <KEY>")
        return

    user_text = message.text or ""
    if "who made you" in user_text.lower() or "your name" in user_text.lower():
        bot.reply_to(message, f"I am Taara 💫 — created by {CREATOR_NAME} ❤️")
        return

    if chat_id in ADMIN_IDS and user_text.strip().lower() in ("/hi", "hi", "hello", "/start"):
        bot.reply_to(message, f"Hello {CREATOR_NAME}! I'm ready — what would you like me to do? 💖")
        return

    reply = generate_reply(chat_id, user_text)
    bot.reply_to(message, reply)

    if user_voice_enabled[chat_id]:
        try:
            audio_file = generate_voice(reply)
            bot.send_voice(chat_id, audio_file)
        except:
            bot.send_message(chat_id, "(Voice reply failed, continuing with text only)")

# --- Set webhook for Telegram ---
bot.remove_webhook()
bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/")

# --- Run Flask server ---
if __name__ == "__main__":
    print("💋 Taara is online — key-protected + admin mode 💫")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
