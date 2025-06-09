import os
import json
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
import openai

# ======================
# SECRET MANAGEMENT
# ======================
# Load environment variables from .env file
load_dotenv()

# Get secrets from environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))

# Validate secrets
if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not ADMIN_USER_ID:
    raise ValueError("Missing required environment variables. Check .env file")

# ======================
# CONFIGURATION (Non-secret settings)
# ======================
CONFIG = {
    "SYSTEM_PROMPT": "You are a helpful assistant. Respond concisely and helpfully.",
    "MODEL": "gpt-4-turbo",
    "MAX_HISTORY": 10,
    "TEMPERATURE": 0.7,
    "WELCOME_MESSAGE": "👋 Hello! I'm your AI assistant. How can I help you today?",
    "HELP_MESSAGE": (
        "🤖 <b>AI Assistant Bot</b>\n\n"
        "• Just chat with me normally\n"
        "• Use /clear to reset our conversation\n"
        "• Use /help to see this message\n\n"
        "I remember the last {MAX_HISTORY} messages in our conversation."
    ),
    "RESPONDING_TO_OTHERS": True,
    "ERROR_NOTIFICATIONS": True
}

# ======================
# INITIALIZATION
# ======================
# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set up OpenAI
openai.api_key = OPENAI_API_KEY

# Conversation history storage
conversations = {}

# ======================
# HELPER FUNCTIONS
# ======================
def get_conversation_history(chat_id):
    """Retrieve conversation history for a chat"""
    if chat_id not in conversations:
        conversations[chat_id] = [
            {"role": "system", "content": CONFIG["SYSTEM_PROMPT"]}
        ]
    return conversations[chat_id]

def update_conversation_history(chat_id, role, content):
    """Update conversation history for a chat"""
    history = get_conversation_history(chat_id)
    history.append({"role": role, "content": content})
    
    # Trim history to maintain max length
    if len(history) > CONFIG["MAX_HISTORY"] + 1:
        conversations[chat_id] = [history[0]] + history[-CONFIG["MAX_HISTORY"]:]

def clear_conversation_history(chat_id):
    """Reset conversation history for a chat"""
    conversations[chat_id] = [
        {"role": "system", "content": CONFIG["SYSTEM_PROMPT"]}
    ]

async def generate_ai_response(history):
    """Generate AI response using OpenAI API"""
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=CONFIG["MODEL"],
            messages=history,
            temperature=CONFIG["TEMPERATURE"]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "⚠️ Sorry, I'm having trouble thinking right now. Please try again later."

# ======================
# TELEGRAM HANDLERS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message when /start is issued."""
    await update.message.reply_text(CONFIG["WELCOME_MESSAGE"])

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message when /help is issued."""
    help_msg = CONFIG["HELP_MESSAGE"].format(MAX_HISTORY=CONFIG["MAX_HISTORY"])
    await update.message.reply_text(help_msg, parse_mode="HTML")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear conversation history when /clear is issued."""
    clear_conversation_history(update.message.chat_id)
    await update.message.reply_text("🧹 Conversation history cleared!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and generate AI responses."""
    message = update.message
    chat_id = message.chat_id
    user_id = message.from_user.id
    
    # Ignore messages from other users if configured
    if not CONFIG["RESPONDING_TO_OTHERS"] and user_id != ADMIN_USER_ID:
        return
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Update conversation history
    update_conversation_history(chat_id, "user", message.text)
    
    # Generate AI response
    history = get_conversation_history(chat_id)
    ai_response = await generate_ai_response(history)
    
    # Update history and send response
    update_conversation_history(chat_id, "assistant", ai_response)
    await message.reply_text(ai_response)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and optionally send notification to admin."""
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    
    if CONFIG["ERROR_NOTIFICATIONS"]:
        error_text = (
            "⚠️ <b>Bot Error</b>\n\n"
            f"<code>{context.error}</code>"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=error_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")

# ======================
# MAIN FUNCTION
# ======================
def main():
    """Start the bot."""
    # Create Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))

    # Message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_message
    ))

    # Error handler
    application.add_error_handler(error_handler)

    # Start polling
    logger.info("AI Assistant Bot is running...")
    logger.info(f"Using model: {CONFIG['MODEL']}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
