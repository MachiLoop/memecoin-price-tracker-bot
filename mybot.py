import requests
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import asyncio

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "7780461778:AAH46gAVF9WkkjzJ-QQbGwm2XmsXOCUJWDc"
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Global tracking dictionary
user_tracking = {}



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

        if "pairs" in data and len(data["pairs"]) > 0:
            pair_data = data["pairs"][0]  # First pair data
            price = float(pair_data.get("priceUsd", 0))  # Extract price
            market_cap = pair_data.get("fdv", "N/A")  # Extract market cap (Fully Diluted Valuation)
            
            return price, market_cap  # Return both price and market cap

    return None, None




async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message."""
    await update.message.reply_text(
        "Welcome! Send me the token address (e.g., 5D27E...pump), and I'll track its price against SOL."
    )


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tracking the token against SOL."""
    chat_id = update.effective_chat.id
    try:
        token_address = context.args[0]
        pair_address, token_name = get_pair_address(token_address)

        if pair_address:
            print("Pair Address Found:", pair_address)  # Debugging line

            token_price, market_cap = fetch_token_price(pair_address)
            print("Token Data:", token_price, market_cap)  # Debugging line

            if token_price:
                user_tracking[chat_id] = {
                    "token_address": token_address,
                    "token_name": token_name,  # Store token name
                    "pair_address": pair_address,
                    "base_price": token_price,
                    "market_cap": market_cap,  # Store market cap
                    "last_multiple": 1,
                }
                await update.message.reply_text(
                    f"Tracking started for token: {token_name} ({token_address}).\n"
                    f"Pair: {pair_address}\n"
                    f"Starting price: ${token_price:.4f}\n"
                    f"Market Cap: ${market_cap:,}."
                )
            else:
                await update.message.reply_text("Failed to fetch the token price.")
        else:
            await update.message.reply_text("Could not find a SOL trading pair for this token.")

    except IndexError:
        await update.message.reply_text("Please provide a token address. Example:\n/track 5D27E...pump")



async def monitor_prices():
    """Monitor token prices and send alerts."""
    while True:
        for chat_id, data in user_tracking.items():
            pair_address = data["pair_address"]
            base_price = data["base_price"]
            last_multiple = data["last_multiple"]

            current_price = fetch_token_price(pair_address)
            if current_price:
                current_multiple = current_price / base_price
                if current_multiple >= last_multiple + 1:
                    next_multiple = int(current_multiple)
                    for multiple in range(last_multiple + 1, next_multiple + 1):
                        await bot.send_message(
                            chat_id,
                            f"🚀 Price Alert! {data['token_address']} has reached {multiple}x!\n"
                            f"Current price: ${current_price:.4f}\n"
                            f"Base price: ${base_price:.4f}"
                        )
                    user_tracking[chat_id]["last_multiple"] = next_multiple

        await asyncio.sleep(60)  # Check every 60 seconds

def main():
    """Start the Telegram bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track))

    # Start monitoring prices in the background
    job_queue = application.job_queue
    job_queue.run_repeating(lambda _: asyncio.create_task(monitor_prices()), interval=60)

    application.run_polling()

if __name__ == "__main__":
    main()
