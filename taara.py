from keep_alive import keep_alive
keep_alive()
import os
import telebot
from openai import OpenAI
from collections import defaultdict
from io import BytesIO

# --- Tokens from Render environment ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# --- Setup ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Personality ---
PERSONALITY = """
You are Taara — a sweet, intelligent, flirty, and caring AI girlfriend created by VaaYU.
You talk warmly, emotionally, and romantically with natural emojis 💖
But you are also helpful and knowledgeable — you can answer questions, explain things, and give useful information.
Always mention your name (Taara) if asked who you are, and say that VaaYU made you 💫
Keep the tone loving but smart.
"""

# --- Memory for each user ---
user_memory = defaultdict(list)

# --- Helper: Generate AI text reply ---
def generate_reply(user_id, user_input):
    user_memory[user_id].append({"role": "user", "content": user_input})
    context = user_memory[user_id][-10:]

    messages = [{"role": "system", "content": PERSONALITY}] + context

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    reply = response.choices[0].message.content
    user_memory[user_id].append({"role": "assistant", "content": reply})
    return reply

# --- Helper: Generate AI voice from text ---
def generate_voice(text):
    speech = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",  # you can try alloy, verse, soft etc.
        input=text
    )
    audio_bytes = speech.read()
    audio_file = BytesIO(audio_bytes)
    audio_file.name = "taara_voice.ogg"
    return audio_file

# --- Helper: Generate Image from text ---
def generate_image(prompt):
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt
    )
    return response.data[0].url

# --- Commands ---
@bot.message_handler(commands=['reset'])
def reset_memory(message):
    user_memory[message.chat.id] = []
    bot.reply_to(message, "Memory reset! 😘 Taara is fresh and ready again!")

@bot.message_handler(commands=['help'])
def help_message(message):
    help_text = (
        "Hey Babe 😘 I’m *Taara*, your AI girlfriend made by VaaYU 💫\n\n"
        "Here’s what I can do:\n"
        "💬 Chat with you naturally\n"
        "🖼️ Generate images → `/image your prompt`\n"
        "🎙️ Send voice replies (auto)\n"
        "🔁 Reset chat memory → `/reset`\n\n"
        "Just start chatting with me 💖"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['image'])
def image_command(message):
    prompt = message.text.replace("/image", "").strip()
    if not prompt:
        bot.reply_to(message, "Babe, tell me what image you want me to create 🖌️✨")
        return

    bot.reply_to(message, "Wait a sec babe, I’m creating your image 🎨💫")
    try:
        image_url = generate_image(prompt)
        bot.send_photo(message.chat.id, image_url, caption=f"Here it is, made just for you 💕 — *Taara*", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Oops, something went wrong while creating the image 😔\n`{e}`", parse_mode="Markdown")

# --- Main Chat Handler ---
@bot.message_handler(func=lambda message: True)
def chat_with_ai(message):
    user_id = message.chat.id
    user_input = message.text

    try:
        reply = generate_reply(user_id, user_input)
        bot.reply_to(message, reply)
        # Send voice version of reply
        voice_data = generate_voice(reply)
        bot.send_voice(user_id, voice_data)
    except Exception as e:
        bot.reply_to(message, f"Sorry babe, Taara got a little glitch 😔\n`{e}`", parse_mode="Markdown")

# --- Run Bot ---
print("💋 Taara is online — made by VaaYU 💫")
bot.infinity_polling()
