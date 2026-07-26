import asyncio
import logging
import os
import threading
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)

from bot.database import Database
from bot.handlers import (
    start, menu, set_location, location_text_handler,
    analyze, analyze_text_handler, seller_script, buyer_script,
    repair, repair_text_handler, parts, parts_text_handler,
    ready_deals, market_pulse, add_deal, add_deal_text_handler,
    help_command, button_router, error_handler
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("carflipai")

app_health = Flask(__name__)

@app_health.get("/")
def health():
    return {"status": "online", "service": "CarFlip AI Bot"}

def run_health_server():
    port = int(os.getenv("PORT", "8080"))
    app_health.run(host="0.0.0.0", port=port)

async def post_init(application):
    await application.bot.set_my_commands([
        ("start", "Open CarFlip AI"),
        ("menu", "Main menu"),
        ("location", "Set your city or ZIP"),
        ("analyze", "Analyze a vehicle listing"),
        ("deals", "Show ready-to-buy deals"),
        ("market", "Local market pulse"),
        ("repair", "Diagnose a car problem"),
        ("parts", "Find compatible parts"),
        ("seller", "Create a seller pitch"),
        ("buyer", "Create a buyer response"),
        ("adddeal", "Add a deal manually"),
        ("help", "How to use the bot"),
    ])

def build_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable.")

    db = Database(os.getenv("DATABASE_PATH", "carflip.db"))
    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )
    application.bot_data["db"] = db

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("location", set_location))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("seller", seller_script))
    application.add_handler(CommandHandler("buyer", buyer_script))
    application.add_handler(CommandHandler("repair", repair))
    application.add_handler(CommandHandler("parts", parts))
    application.add_handler(CommandHandler("deals", ready_deals))
    application.add_handler(CommandHandler("market", market_pulse))
    application.add_handler(CommandHandler("adddeal", add_deal))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_router))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, location_text_handler), group=1)
    application.add_error_handler(error_handler)
    return application

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    bot = build_bot()
    logger.info("CarFlip AI starting...")
    bot.run_polling(drop_pending_updates=True)
