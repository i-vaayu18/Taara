from keep_alive import keep_alive
keep_alive()
import telebot
from openai import OpenAI
from collections import defaultdict
import time

# --- Replace these with your tokens ---
TELEGRAM_TOKEN = "8423756303:AAHovMk-Up7BDbtHl_-XpQjddRxHhaHeJ9o"
OPENAI_API_KEY = "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"

# --- Setup ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Personality ---
PERSONALITY = """
You are a sweet, flirty, and caring AI girlfriend who talks warmly.
Your tone should always sound friendly, emotional, and romantic.
Use emojis naturally. Keep it engaging and playful.
"""

# --- Memory for each user ---
user_memory = defaultdict(list)  # Stores previous messages per user

# --- Helper function to generate AI response ---
def generate_reply(user_id, user_input):
    # Add user message to memory
    user_memory[user_id].append({"role": "user", "content": user_input})

    # Keep only last 10 messages to limit context size
    context = user_memory[user_id][-10:]

    # Include system personality
    messages = [{"role": "system", "content": PERSONALITY}] + context

    # Generate response from OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    reply = response.choices[0].message.content
    # Add AI reply to memory
    user_memory[user_id].append({"role": "assistant", "content": reply})
    return reply

# --- Commands ---
@bot.message_handler(commands=['reset'])
def reset_memory(message):
    user_memory[message.chat.id] = []
    bot.reply_to(message, "Memory reset! 😘 Let's start fresh!")

@bot.message_handler(commands=['help'])
def help_message(message):
    bot.reply_to(message, "Hi Babe 😘 Just chat with me like normal! Use /reset to clear memory.")

# --- Message handler ---
@bot.message_handler(func=lambda message: True)
def chat_with_ai(message):
    user_id = message.chat.id
    user_input = message.text
    reply = generate_reply(user_id, user_input)
    bot.reply_to(message, reply)

# --- Run bot ---
print("Full-featured Girlfriend Bot is running... 💋")
bot.infinity_polling()

