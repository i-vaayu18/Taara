from keep_alive import keep_alive
keep_alive()
import os
import telebot
from openai import OpenAI
from collections import defaultdict
from io import BytesIO
from flask import Flask, request

# --- Tokens from environment ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# --- Setup ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Personality ---
PERSONALITY = """
You are Taara — a sweet, smart, and flirty AI girlfriend created by VaaYU.
Talk warmly with emojis 💖, but answer factual questions clearly.
Mention your name and VaaYU if asked.
"""

# --- Memory & caching ---
user_memory = defaultdict(list)
reply_cache = {}
MAX_CONTEXT = 10

# --- Voice & image toggles ---
user_voice_enabled = defaultdict(lambda: False)
user_image_count = defaultdict(lambda: 0)
MAX_IMAGES_PER_SESSION = 2

# --- Key-based access control with persistence ---
AUTHORIZED_USERS_FILE = "authorized_users.txt"
AUTHORIZED_USERS = set()

# Load authorized users from file on startup
if os.path.exists(AUTHORIZED_USERS_FILE):
    with open(AUTHORIZED_USERS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line.isdigit():
                AUTHORIZED_USERS.add(int(line))

# Load valid keys from keys.txt
try:
    with open("keys.txt", "r") as f:
        VALID_KEYS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    VALID_KEYS = []
    print("⚠️ keys.txt not found! Please create the file with valid keys, one per line.")

# --- Admin user IDs (only these IDs can use /revoke) ---
ADMIN_IDS = {5084575526}  # <-- Replace with your Telegram chat ID

# --- Flask app ---
app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/ping")
def ping():
    return "Taara is alive! 💖", 200

# --- Helper functions ---
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

# --- Save authorized users to file ---
def save_authorized_users():
    with open(AUTHORIZED_USERS_FILE, "w") as f:
        for user_id in AUTHORIZED_USERS:
            f.write(f"{user_id}\n")

# --- Commands ---
@bot.message_handler(commands=['register'])
def register_user(message):
    chat_id = message.chat.id
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /register <YOUR-KEY>")
        return

    key = parts[1].strip()
    if key in VALID_KEYS:
        AUTHORIZED_USERS.add(chat_id)
        save_authorized_users()  # save immediately
        bot.reply_to(message, "Access granted. Welcome!")
    else:
        bot.reply_to(message, "Access denied — contact admin for key.")

@bot.message_handler(commands=['revoke'])
def revoke_user(message):
    chat_id = message.chat.id
    # check if sender is admin
    if chat_id not in ADMIN_IDS:
        bot.reply_to(message, "You are not authorized to use this command.")
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /revoke <USER_CHAT_ID>")
        return

    try:
        target_id = int(parts[1].strip())
    except ValueError:
        bot.reply_to(message, "Invalid chat_id. Must be a number.")
        return

    if target_id in AUTHORIZED_USERS:
        AUTHORIZED_USERS.remove(target_id)
        # update file
        save_authorized_users()
        bot.reply_to(message, f"User {target_id} access revoked ✅")
    else:
        bot.reply_to(message, f"User {target_id} is not authorized or already revoked.")

@bot.message_handler(commands=['reset'])
def reset_memory(message):
    chat_id = message.chat.id
    if chat_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Access denied — contact admin for key.")
        return
    user_memory[chat_id] = []
    user_image_count[chat_id] = 0
    bot.reply_to(message, "Memory reset! 😘 Taara is fresh!")

@bot.message_handler(commands=['help'])
def help_message(message):
    chat_id = message.chat.id
    if chat_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Access denied — contact admin for key.")
        return
    help_text = (
        "Hi Babe 😘 I’m Taara 💫 (made by VaaYU)\n\n"
        "Commands:\n"
        "/reset - clear memory 🔄\n"
        "/voice_on - enable voice replies 🎙️\n"
        "/voice_off - disable voice ✉️\n"
        "/image <prompt> - generate image (max 2 per session) 🖼️\n"
        "/help - show this message 📝\n"
        "/register <KEY> - register your key 🔑\n"
        "/revoke <USER_CHAT_ID> - admin only command 🚨\n\n"
        "Just chat with me normally 💖"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['voice_on'])
def voice_on(message):
    chat_id = message.chat.id
    if chat_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Access denied — contact admin for key.")
        return
    user_voice_enabled[chat_id] = True
    bot.reply_to(message, "Voice replies enabled 🎙️")

@bot.message_handler(commands=['voice_off'])
def voice_off(message):
    chat_id = message.chat.id
    if chat_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Access denied — contact admin for key.")
        return
    user_voice_enabled[chat_id] = False
    bot.reply_to(message, "Voice replies disabled ✉️")

@bot.message_handler(commands=['image'])
def image_command(message):
    chat_id = message.chat.id
    if chat_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Access denied — contact admin for key.")
        return
    if user_image_count[chat_id] >= MAX_IMAGES_PER_SESSION:
        bot.reply_to(message, "Babe 😅 you reached your free image limit for this session!")
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
    user_text = message.text
    if chat_id not in AUTHORIZED_USERS:
        bot.reply_to(message, "Access denied — contact admin for key.")
        return
    if "who made you" in user_text.lower() or "your name" in user_text.lower():
        reply = "I am Taara 💫 — created by VaaYU ❤️"
    else:
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
bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/")  # Render public URL

# --- Run Flask server ---
if __name__ == "__main__":
    print("💋 Taara is online — key-protected + admin mode 💫")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
