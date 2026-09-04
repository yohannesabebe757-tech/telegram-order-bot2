"""
Telegram Product Ordering Bot
Products: Mozzarella cheese, Slice cheese, Table butter, Chicken, Chicken breast

SETUP:
1. pip install python-telegram-bot --upgrade
2. Get a bot token from @BotFather on Telegram
3. Get your own chat ID from @userinfobot on Telegram (so you receive orders)
4. Fill in BOT_TOKEN and SELLER_CHAT_ID below
5. Run: python bot.py
"""

import sqlite3
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ---------- CONFIG ----------
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
SELLER_CHAT_ID = "YOUR_CHAT_ID_HERE"  # where new orders get sent

logging.basicConfig(level=logging.INFO)

# ---------- PRODUCTS ----------
# price is per 1 kg (or per listed unit)
PRODUCTS = {
    "mozzarella":     {"name": "Mozzarella Cheese (1kg)",  "price": 750},
    "slice_cheese":   {"name": "Slice Cheese (1kg)",       "price": 900},
    "table_butter":   {"name": "Table Butter (200g)",      "price": 300},
    "chicken":        {"name": "Chicken (1kg)",             "price": 1000},
    "chicken_breast": {"name": "Chicken Breast (1kg)",      "price": 1800},
}

# Conversation states
CHOOSING_QTY, GETTING_NAME, GETTING_PHONE, GETTING_ADDRESS = range(4)

# ---------- DATABASE ----------
DB_PATH = "orders.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER,
            product_key TEXT,
            product_name TEXT,
            quantity INTEGER,
            unit_price INTEGER,
            total_price INTEGER,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_order(user_id, product_key, qty, name, phone, address):
    product = PRODUCTS[product_key]
    total = product["price"] * qty
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO orders (telegram_user_id, product_key, product_name, quantity,
                             unit_price, total_price, customer_name, phone, address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, product_key, product["name"], qty, product["price"], total,
          name, phone, address, datetime.now().isoformat()))
    conn.commit()
    order_id = c.lastrowid
    conn.close()
    return order_id, total


# ---------- HANDLERS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"{p['name']} - {p['price']} birr", callback_data=key)]
        for key, p in PRODUCTS.items()
    ]
    await update.message.reply_text(
        "🧀🐔 Welcome! Please choose a product to order:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def product_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_key = query.data
    context.user_data["product"] = product_key
    product = PRODUCTS[product_key]
    await query.edit_message_text(
        f"You selected: {product['name']} ({product['price']} birr per unit)\n\n"
        f"How many units (kg) would you like?"
    )
    return CHOOSING_QTY


async def qty_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("Please enter a valid number (e.g. 1, 2, 5).")
        return CHOOSING_QTY

    context.user_data["qty"] = int(text)
    await update.message.reply_text("Great — what's your full name?")
    return GETTING_NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("What's your phone number?")
    return GETTING_PHONE


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("What's your delivery address?")
    return GETTING_ADDRESS


async def address_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["address"] = update.message.text.strip()
    d = context.user_data
    product = PRODUCTS[d["product"]]

    order_id, total = save_order(
        user_id=update.effective_user.id,
        product_key=d["product"],
        qty=d["qty"],
        name=d["name"],
        phone=d["phone"],
        address=d["address"],
    )

    summary = (
        f"✅ Order #{order_id} confirmed!\n\n"
        f"Product: {product['name']}\n"
        f"Quantity: {d['qty']}\n"
        f"Unit price: {product['price']} birr\n"
        f"Total: {total} birr\n\n"
        f"Name: {d['name']}\n"
        f"Phone: {d['phone']}\n"
        f"Address: {d['address']}\n\n"
        f"We'll contact you shortly to confirm delivery. Thank you! 🙏"
    )
    await update.message.reply_text(summary)

    # Notify seller
    if SELLER_CHAT_ID and SELLER_CHAT_ID != "YOUR_CHAT_ID_HERE":
        await context.bot.send_message(
            chat_id=SELLER_CHAT_ID,
            text=f"📦 New Order #{order_id}\n\n" + summary,
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Order cancelled. Send /start to order again.")
    return ConversationHandler.END


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["📋 *Our Products:*\n"]
    for p in PRODUCTS.values():
        lines.append(f"• {p['name']} — {p['price']} birr")
    lines.append("\nSend /start to place an order.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, product_name, quantity, total_price, created_at
        FROM orders WHERE telegram_user_id = ?
        ORDER BY id DESC LIMIT 10
    """, (update.effective_user.id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("You have no past orders. Send /start to place one.")
        return

    lines = ["🧾 *Your recent orders:*\n"]
    for order_id, name, qty, total, created_at in rows:
        date = created_at.split("T")[0]
        lines.append(f"#{order_id} — {name} x{qty} — {total} birr — {date}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, qty_received)],
            GETTING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            GETTING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            GETTING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(product_chosen))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("myorders", myorders))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
