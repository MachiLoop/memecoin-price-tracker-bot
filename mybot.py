import requests
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import asyncio
import uuid  # Import UUID module

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "7780461778:AAH46gAVF9WkkjzJ-QQbGwm2XmsXOCUJWDc"
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Global tracking dictionary
user_tracking = {}  # Now stores alerts by alert_id instead of chat_id

def get_pair_address(token_address):
    """Finds the correct SOL trading pair for the given token address and returns token name."""
    url = f"https://api.dexscreener.com/latest/dex/search?q={token_address}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        pairs = data.get("pairs", [])

        # Look for a pair where SOL is involved
        for pair in pairs:
            if "SOL" in pair["baseToken"]["symbol"] or "SOL" in pair["quoteToken"]["symbol"]:
                token_name = pair["baseToken"]["name"]  # Extract token name
                return pair["pairAddress"], token_name  

    return None, None  # No valid pair found

def fetch_token_price(pair_address):
    """Fetch the current price and market cap of the token in the SOL pair."""
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        print("Raw API Response:", data)  # Debugging line

        if "pairs" in data and data["pairs"]:  # Ensure "pairs" is not None or empty
            pair_data = data["pairs"][0]
            price = float(pair_data.get("priceUsd", 0))
            market_cap = float(pair_data.get("fdv", 0))  # 'fdv' represents fully diluted market cap

            return price, market_cap

    print("❌ No valid price data found!")  # Debugging line
    return None, None  # Return None values if no data is available

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message."""
    await update.message.reply_text(
        "Welcome! Send me the token address (e.g., 5D27E...pump), and I'll track its price against SOL."
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tracking the token against SOL with a unique alert ID."""
    chat_id = update.effective_chat.id
    try:
        token_address = context.args[0]
        pair_address, token_name = get_pair_address(token_address)  # Unpack tuple

        if pair_address:
            print("Pair Address Found:", pair_address)  # Debugging line

            token_price, market_cap = fetch_token_price(pair_address)
            print("Token Data:", token_price, market_cap)  # Debugging line

            if token_price:
                alert_id = str(uuid.uuid4())[:8]  # Generate short unique alert ID

                user_tracking[alert_id] = {
                    "chat_id": chat_id,
                    "token_name": token_name,  # Store token name
                    "token_address": token_address,
                    "pair_address": pair_address,
                    "base_price": token_price,
                    "market_cap": market_cap,
                    "last_multiple": 1,
                }
                await update.message.reply_text(
                    f"🔔 Tracking Started!\n"
                    f"📌 Alert ID: `{alert_id}`\n"
                    f"🪙 Token: {token_name} ({token_address})\n"
                    f"🔗 Pair: {pair_address}\n"
                    f"💰 Starting Price: ${token_price:.4f}\n"
                    f"🏦 Market Cap: ${market_cap:,.2f}\n"
                    f"❌ Use `/delete {alert_id}` to stop tracking."
                )
            else:
                await update.message.reply_text("❌ Failed to fetch the token price.")
        else:
            await update.message.reply_text("❌ Could not find a SOL trading pair for this token.")

    except IndexError:
        await update.message.reply_text("⚠️ Please provide a token address. Example:\n`/track 5D27E...pump`")

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes an active alert by its ID."""
    try:
        alert_id = context.args[0]
        
        if alert_id in user_tracking:
            del user_tracking[alert_id]
            await update.message.reply_text(f"✅ Alert `{alert_id}` has been deleted successfully.")
        else:
            await update.message.reply_text("❌ Alert ID not found.")
    
    except IndexError:
        await update.message.reply_text("⚠️ Please provide an alert ID to delete. Example:\n`/delete abc12345`")

async def monitor_prices():
    """Monitor token prices and send alerts."""
    while True:
        for alert_id, data in list(user_tracking.items()):  # Convert to list to avoid runtime modification issues
            chat_id = data["chat_id"]
            pair_address = data["pair_address"]
            base_price = data["base_price"]
            last_multiple = data["last_multiple"]

            current_price, _ = fetch_token_price(pair_address)  # Fetch latest price
            if current_price:
                current_multiple = current_price / base_price
                if current_multiple >= last_multiple + 1:
                    next_multiple = int(current_multiple)
                    for multiple in range(last_multiple + 1, next_multiple + 1):
                        await bot.send_message(
                            chat_id,
                            f"🚀 Price Alert! {data['token_name']} has reached {multiple}x!\n"
                            f"💰 Current price: ${current_price:.4f}\n"
                            f"📌 Base price: ${base_price:.4f}\n"
                            f"🔔 Alert ID: `{alert_id}`"
                        )
                    user_tracking[alert_id]["last_multiple"] = next_multiple

        await asyncio.sleep(120)  # Check every 120 seconds

def main():
    """Start the Telegram bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("delete", delete))

    # Start monitoring prices in the background
    job_queue = application.job_queue
    job_queue.run_repeating(lambda _: asyncio.create_task(monitor_prices()), interval=60)

    application.run_polling()

if __name__ == "__main__":
    main()
