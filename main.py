import logging
import os
import re
import sqlite3
import threading
from datetime import datetime

from flask import Flask
from openai import AsyncOpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("profitdriverus")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
PORT = int(os.getenv("PORT", "8080"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "/tmp/profitdriverus.db")

# ============================================================
# RAILWAY HEALTH SERVER
# ============================================================

web_app = Flask(__name__)

@web_app.get("/")
def home():
    return {
        "status": "online",
        "service": "ProfitDriveRUS AI",
        "telegram_ready": bool(TELEGRAM_BOT_TOKEN),
        "openai_ready": bool(OPENAI_API_KEY),
    }, 200

@web_app.get("/health")
def health():
    return "OK", 200

def run_web_server():
    web_app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False,
    )

# ============================================================
# DATABASE
# ============================================================

def db_connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                city TEXT DEFAULT '',
                state TEXT DEFAULT '',
                zip_code TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                purchase_price REAL NOT NULL,
                market_value REAL NOT NULL,
                repairs REAL DEFAULT 0,
                fees REAL DEFAULT 0,
                mileage INTEGER DEFAULT 0,
                city TEXT DEFAULT '',
                state TEXT DEFAULT '',
                listing_url TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )

def save_user(telegram_id: int, city: str = "", state: str = "", zip_code: str = ""):
    now = datetime.utcnow().isoformat()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO users
            (telegram_id, city, state, zip_code, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                city=excluded.city,
                state=excluded.state,
                zip_code=excluded.zip_code,
                updated_at=excluded.updated_at
            """,
            (telegram_id, city, state, zip_code, now, now),
        )

def get_user(telegram_id: int):
    with db_connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()

def add_deal(telegram_id: int, deal: dict):
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO deals
            (
                telegram_id, title, purchase_price, market_value,
                repairs, fees, mileage, city, state, listing_url, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                deal["title"],
                deal["purchase_price"],
                deal["market_value"],
                deal["repairs"],
                deal["fees"],
                deal["mileage"],
                deal["city"],
                deal["state"],
                deal["listing_url"],
                datetime.utcnow().isoformat(),
            ),
        )

def get_deals(telegram_id: int):
    with db_connect() as conn:
        return conn.execute(
            """
            SELECT *,
            (market_value - purchase_price - repairs - fees) AS profit
            FROM deals
            WHERE telegram_id=?
            ORDER BY profit DESC
            LIMIT 10
            """,
            (telegram_id,),
        ).fetchall()

# ============================================================
# OPENAI
# ============================================================

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = """
You are ProfitDriveRUS AI, an advanced but easy-to-understand car flipping assistant.

You help users:
- Analyze vehicle listings.
- Estimate possible repair costs and risks.
- Estimate potential flip profit.
- Create seller negotiation scripts.
- Create buyer reply scripts.
- Explain car problems.
- Help verify replacement parts.
- Teach beginner car flippers.

Rules:
- Do not invent VIN history, confirmed sales, title status, recalls, exact part fitment,
  live inventory, exact pricing, or guaranteed profit.
- Clearly label all estimates.
- Recommend an in-person inspection and VIN/title verification.
- Give safety warnings for serious mechanical problems.
- Keep answers direct and simple.
- Do not use markdown tables.
"""

async def ask_ai(prompt: str) -> str:
    if not openai_client:
        return (
            "⚠️ OPENAI_API_KEY is missing.\n\n"
            "Go to Railway → Variables and add your OpenAI API key."
        )

    try:
        response = await openai_client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=prompt,
        )
        return response.output_text.strip()
    except Exception as error:
        logger.exception("OpenAI request failed")
        return (
            "⚠️ The AI could not answer right now.\n\n"
            f"Error: {type(error).__name__}\n"
            "Check your OpenAI key, billing, and OPENAI_MODEL variable."
        )

# ============================================================
# TELEGRAM MENUS
# ============================================================

def main_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔥 Ready Deals", callback_data="deals"),
                InlineKeyboardButton("🔎 Analyze Car", callback_data="analyze"),
            ],
            [
                InlineKeyboardButton("📊 Market Pulse", callback_data="market"),
                InlineKeyboardButton("📍 My Location", callback_data="location"),
            ],
            [
                InlineKeyboardButton("🛠 Repair Hub", callback_data="repair"),
                InlineKeyboardButton("🧩 Parts Finder", callback_data="parts"),
            ],
            [
                InlineKeyboardButton("🤝 Seller Script", callback_data="seller"),
                InlineKeyboardButton("💬 Buyer Script", callback_data="buyer"),
            ],
            [
                InlineKeyboardButton("➕ Save Deal", callback_data="save_deal"),
                InlineKeyboardButton("📚 Flip Academy", callback_data="academy"),
            ],
            [InlineKeyboardButton("❓ Help", callback_data="help")],
        ]
    )

def back_button():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Main Menu", callback_data="menu")]]
    )

async def send_reply(update: Update, text: str, keyboard=None, parse_mode=None):
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )

# ============================================================
# COMMANDS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id):
        save_user(update.effective_user.id)

    await update.message.reply_text(
        "🚘 *ProfitDriveRUS AI*\n\n"
        "Analyze cars, estimate profit, find repair guidance, locate parts, "
        "and create negotiation scripts.\n\n"
        "Set your location first.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = None
    await send_reply(update, "Choose a feature:", main_menu())

async def location_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "location"
    await send_reply(
        update,
        "📍 Send your location like:\n\nDallas, TX, 75201\n\n"
        "You can also send only: Dallas, TX",
        back_button(),
    )

async def analyze_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "analyze"
    await send_reply(
        update,
        "🔎 Paste the Facebook Marketplace listing or send:\n\n"
        "Year, make, model, price, mileage, title status, known problems, city, and URL.",
        back_button(),
    )

async def seller_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "seller"
    await send_reply(
        update,
        "🤝 Send the vehicle, asking price, defects, and the offer you want to make.",
        back_button(),
    )

async def buyer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "buyer"
    await send_reply(
        update,
        "💬 Send your vehicle details and the buyer's message.",
        back_button(),
    )

async def repair_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "repair"
    await send_reply(
        update,
        "🛠 Send:\n"
        "• Year, make, model, and engine\n"
        "• Symptoms\n"
        "• Warning lights\n"
        "• Check-engine code\n"
        "• Recent repairs",
        back_button(),
    )

async def parts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "parts"
    await send_reply(
        update,
        "🧩 Send the year, make, model, engine, trim, and exact part needed.",
        back_button(),
    )

async def save_deal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = "save_deal"
    await send_reply(
        update,
        "➕ Use this exact format:\n\n"
        "Vehicle | purchase price | market value | repairs | fees | mileage | city | state | URL\n\n"
        "Example:\n"
        "2017 Honda Accord | 8500 | 11200 | 600 | 350 | 142000 | Dallas | TX | https://...",
        back_button(),
    )

async def show_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deals = get_deals(update.effective_user.id)

    if not deals:
        await send_reply(
            update,
            "🔥 You have no saved deals yet.\n\nUse ➕ Save Deal to add one.",
            back_button(),
        )
        return

    lines = ["🔥 *YOUR READY DEALS*\n"]
    for number, deal in enumerate(deals, 1):
        investment = deal["purchase_price"] + deal["repairs"] + deal["fees"]
        profit = deal["profit"]
        roi = (profit / investment * 100) if investment > 0 else 0

        lines.append(
            f"*{number}. {deal['title']}*\n"
            f"Purchase: ${deal['purchase_price']:,.0f}\n"
            f"Repairs: ${deal['repairs']:,.0f}\n"
            f"Fees: ${deal['fees']:,.0f}\n"
            f"Estimated resale: ${deal['market_value']:,.0f}\n"
            f"Estimated profit: ${profit:,.0f}\n"
            f"Estimated ROI: {roi:.1f}%\n"
            f"{deal['listing_url'] or ''}\n"
        )

    await send_reply(
        update,
        "\n".join(lines),
        back_button(),
        parse_mode="Markdown",
    )

async def show_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    location = "your area"
    if user and user["city"] and user["state"]:
        location = f"{user['city']}, {user['state']}"

    await send_reply(
        update,
        f"📊 *MARKET PULSE — {location}*\n\n"
        "This tab is ready for a licensed automotive market-data provider.\n\n"
        "It will show:\n"
        "• Most bought vehicles\n"
        "• Most sold vehicles\n"
        "• Fastest-selling vehicles\n"
        "• Most profitable models\n"
        "• Slow sellers\n"
        "• City, ZIP, state, and nearby-state comparisons\n\n"
        "Live Facebook Marketplace scanning requires approved or licensed data access.",
        back_button(),
        parse_mode="Markdown",
    )

async def show_academy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_reply(
        update,
        "📚 *FLIP ACADEMY*\n\n"
        "1. Verify the seller and title.\n"
        "2. Check the VIN and vehicle history.\n"
        "3. Scan the vehicle with an OBD-II scanner.\n"
        "4. Inspect fluids, leaks, tires, rust, warning lights, and body gaps.\n"
        "5. Compare similar local listings.\n"
        "6. Calculate repairs, taxes, registration, towing, and detailing.\n"
        "7. Leave money for unexpected repairs.\n"
        "8. Never buy only because the price looks cheap.",
        back_button(),
        parse_mode="Markdown",
    )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_reply(
        update,
        "❓ *HOW TO USE PROFITDRIVERUS*\n\n"
        "1. Set your location.\n"
        "2. Paste a listing into Analyze Car.\n"
        "3. Use Seller Script to negotiate.\n"
        "4. Use Repair Hub before buying a problem car.\n"
        "5. Use Parts Finder to verify replacement parts.\n"
        "6. Save promising listings to Ready Deals.",
        back_button(),
        parse_mode="Markdown",
    )

# ============================================================
# TEXT HANDLER
# ============================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    if not mode:
        await update.message.reply_text(
            "Use /menu and choose a feature.",
            reply_markup=main_menu(),
        )
        return

    if mode == "location":
        parts = [part.strip() for part in text.split(",")]
        if len(parts) < 2:
            await update.message.reply_text("Send it like: Dallas, TX, 75201")
            return

        city = parts[0]
        state = parts[1].upper()
        zip_code = parts[2] if len(parts) > 2 else ""

        save_user(update.effective_user.id, city, state, zip_code)
        context.user_data["mode"] = None

        await update.message.reply_text(
            f"✅ Location saved: {city}, {state} {zip_code}",
            reply_markup=main_menu(),
        )
        return

    if mode == "save_deal":
        parts = [part.strip() for part in text.split("|")]

        if len(parts) < 8:
            await update.message.reply_text(
                "Use this format:\n"
                "Vehicle | purchase price | market value | repairs | fees | mileage | city | state | URL"
            )
            return

        try:
            deal = {
                "title": parts[0],
                "purchase_price": float(parts[1].replace("$", "").replace(",", "")),
                "market_value": float(parts[2].replace("$", "").replace(",", "")),
                "repairs": float(parts[3].replace("$", "").replace(",", "")),
                "fees": float(parts[4].replace("$", "").replace(",", "")),
                "mileage": int(parts[5].replace(",", "")),
                "city": parts[6],
                "state": parts[7].upper(),
                "listing_url": parts[8] if len(parts) > 8 else "",
            }
        except ValueError:
            await update.message.reply_text(
                "One of the price, repair, fee, or mileage fields is not a valid number."
            )
            return

        add_deal(update.effective_user.id, deal)
        profit = (
            deal["market_value"]
            - deal["purchase_price"]
            - deal["repairs"]
            - deal["fees"]
        )
        context.user_data["mode"] = None

        await update.message.reply_text(
            f"✅ Deal saved.\nEstimated profit: ${profit:,.0f}",
            reply_markup=main_menu(),
        )
        return

    waiting = await update.message.reply_text("⏳ Analyzing...")

    if mode == "analyze":
        prompt = (
            "Analyze this potential car flip. Give:\n"
            "1. Missing information\n"
            "2. Estimated market value caution\n"
            "3. Likely repair risks\n"
            "4. Estimated total investment\n"
            "5. Possible resale range\n"
            "6. Possible profit range\n"
            "7. Maximum recommended offer\n"
            "8. Inspection checklist\n"
            "9. BUY, NEGOTIATE, or SKIP decision\n\n"
            f"Listing:\n{text}"
        )

    elif mode == "seller":
        prompt = (
            "Create three Facebook Marketplace seller messages:\n"
            "1. Friendly opener\n"
            "2. Direct offer\n"
            "3. Follow-up\n\n"
            f"Details:\n{text}"
        )

    elif mode == "buyer":
        prompt = (
            "Write an honest, confident response to this vehicle buyer. "
            "Do not hide defects. Include a clear next step.\n\n"
            f"Details:\n{text}"
        )

    elif mode == "repair":
        prompt = (
            "Explain this car problem. Include:\n"
            "1. Likely causes ranked\n"
            "2. Safe beginner checks\n"
            "3. Tools and likely parts\n"
            "4. DIY difficulty\n"
            "5. Estimated DIY cost\n"
            "6. Estimated shop cost\n"
            "7. General repair steps\n"
            "8. Stop-driving warnings\n"
            "9. Whether professional diagnosis is needed\n\n"
            f"Problem:\n{text}"
        )

    elif mode == "parts":
        prompt = (
            "Help verify the correct replacement part. Explain how to use the VIN, engine, "
            "trim, OEM number, connector, dimensions, and production date. Compare OEM, "
            "aftermarket, used, and rebuilt parts. Do not claim live inventory.\n\n"
            f"Request:\n{text}"
        )

    else:
        prompt = text

    answer = await ask_ai(prompt)

    if mode == "parts":
        search_query = re.sub(r"\s+", "+", text)
        answer += (
            "\n\n🔗 PART SEARCH LINKS\n"
            f"AutoZone: https://www.autozone.com/searchresult?searchText={search_query}\n"
            f"O'Reilly: https://www.oreillyauto.com/search?q={search_query}\n"
            f"NAPA: https://www.napaonline.com/en/search?text={search_query}\n"
            "RockAuto: https://www.rockauto.com/\n"
            "LKQ: https://www.lkqonline.com/\n"
            f"eBay Motors: https://www.ebay.com/sch/i.html?_nkw={search_query}"
        )

    context.user_data["mode"] = None

    try:
        await waiting.delete()
    except Exception:
        pass

    chunks = [answer[i:i + 3900] for i in range(0, len(answer), 3900)]

    for index, chunk in enumerate(chunks):
        await update.message.reply_text(
            chunk,
            reply_markup=main_menu() if index == len(chunks) - 1 else None,
            disable_web_page_preview=True,
        )

# ============================================================
# BUTTON ROUTER
# ============================================================

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    routes = {
        "menu": menu_command,
        "location": location_menu,
        "analyze": analyze_menu,
        "seller": seller_menu,
        "buyer": buyer_menu,
        "repair": repair_menu,
        "parts": parts_menu,
        "save_deal": save_deal_menu,
        "deals": show_deals,
        "market": show_market,
        "academy": show_academy,
        "help": show_help,
    }

    handler = routes.get(update.callback_query.data)
    if handler:
        await handler(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Telegram error", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Temporary error. Use /menu and try again."
        )

async def post_init(application):
    await application.bot.set_my_commands(
        [
            ("start", "Start ProfitDriveRUS"),
            ("menu", "Open the menu"),
            ("analyze", "Analyze a vehicle"),
            ("deals", "View saved deals"),
            ("repair", "Open Repair Hub"),
            ("parts", "Find vehicle parts"),
            ("help", "Get help"),
        ]
    )

def build_bot():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing. Add it in Railway Variables."
        )

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("analyze", analyze_menu))
    app.add_handler(CommandHandler("deals", show_deals))
    app.add_handler(CommandHandler("repair", repair_menu))
    app.add_handler(CommandHandler("parts", parts_menu))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    return app

if __name__ == "__main__":
    init_database()

    threading.Thread(
        target=run_web_server,
        daemon=True,
    ).start()

    logger.info("Railway health server started on port %s", PORT)

    telegram_bot = build_bot()
    logger.info("ProfitDriveRUS bot starting...")
    telegram_bot.run_polling(drop_pending_updates=True)
