import requests
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import asyncio
import uuid
import json

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")  # Replace with your Firebase service account key
firebase_admin.initialize_app(cred)
db = firestore.client()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = "7780461778:AAH46gAVF9WkkjzJ-QQbGwm2XmsXOCUJWDc"
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Global tracking dictionary
user_tracking = {}  # Stores alerts by alert_id

def load_tracking_data():
    """Load tracked tokens from Firebase Firestore on startup."""
    global user_tracking
    user_tracking.clear()  # Reset local dictionary

    docs = db.collection("tracked_tokens").stream()
    for doc in docs:
        user_tracking[doc.id] = doc.to_dict()

def save_tracking_data():
    """Save the current user tracking data to Firestore."""
    for alert_id, data in user_tracking.items():
        db.collection("tracked_tokens").document(alert_id).set(data)

def delete_tracking_data(alert_id):
    """Delete a specific tracking alert from Firestore."""
    db.collection("tracked_tokens").document(alert_id).delete()

def get_pair_address(token_address):
    """Finds the correct SOL trading pair for the given token address and returns token name."""
    url = f"https://api.dexscreener.com/latest/dex/search?q={token_address}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        pairs = data.get("pairs", [])

        for pair in pairs:
            if "SOL" in pair["baseToken"]["symbol"] or "SOL" in pair["quoteToken"]["symbol"]:
                token_name = pair["baseToken"]["name"]
                return pair["pairAddress"], token_name  

    return None, None  # No valid pair found

def fetch_token_price(pair_address):
    """Fetch the current price and market cap of the token in the SOL pair."""
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if "pairs" in data and data["pairs"]:  
            pair_data = data["pairs"][0]
            price = float(pair_data.get("priceUsd", 0))
            market_cap = float(pair_data.get("fdv", 0))  
            return price, market_cap

    return None, None  

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message."""
    await update.message.reply_text(
        "Welcome! Send me the token address (e.g., 5D27E...pump), and I'll track its price against SOL."
    )

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tracking the token against SOL with a unique alert ID, max 10 tokens per user."""
    chat_id = update.effective_chat.id
    user_alerts = [alert_id for alert_id, data in user_tracking.items() if data["chat_id"] == chat_id]
    if len(user_alerts) >= 10:
        await update.message.reply_text("⚠️ You can only track a maximum of 10 tokens at a time. Delete some before adding new ones.")
        return

    try:
        token_address = context.args[0]
        pair_address, token_name = get_pair_address(token_address)

        if pair_address:
            token_price, market_cap = fetch_token_price(pair_address)
            if token_price:
                alert_id = str(uuid.uuid4())[:8]  
                user_tracking[alert_id] = {
                    "chat_id": chat_id,
                    "token_name": token_name,
                    "token_address": token_address,
                    "pair_address": pair_address,
                    "base_price": token_price,
                    "market_cap": market_cap,
                    "last_multiple": 1,
                }
                save_tracking_data()  # Save to Firebase
                await update.message.reply_text(
                    f"🔔 Tracking Started!\n"
                    f"📌 Alert ID: `{alert_id}`\n"
                    f"🪙 Token: {token_name} ({token_address})\n"
                    f"💰 Starting Price: ${token_price:.4f}\n"
                    f"🏦 Market Cap: ${market_cap:,.2f}\n"
                    f"❌ Use `/delete {alert_id}` to stop tracking.", parse_mode="Markdown"
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
            delete_tracking_data(alert_id)  # Remove from Firebase
            await update.message.reply_text(f"✅ Alert `{alert_id}` has been deleted successfully.")
        else:
            await update.message.reply_text("❌ Alert ID not found.")
    except IndexError:
        await update.message.reply_text("⚠️ Please provide an alert ID to delete. Example:\n`/delete abc12345`")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all active alerts for a user directly from Firestore."""
    chat_id = update.effective_chat.id
    alerts_ref = db.collection("tracked_tokens").where("chat_id", "==", chat_id)
    docs = alerts_ref.stream()

    user_alerts = [doc.to_dict() for doc in docs]

    if not user_alerts:
        await update.message.reply_text("📭 You are not tracking any tokens.")
        return

    message = "📋 **Your Active Alerts:**\n"
    for idx, data in enumerate(user_alerts, start=1):
        current_price, current_market_cap = fetch_token_price(data["pair_address"])  

        if current_price:
            current_multiple = current_price / data["base_price"]
        else:
            current_price, current_market_cap, current_multiple = "N/A", "N/A", "N/A"

        message += (
            f"\n{idx}. 🪙 **{data['token_name']}** ({data['token_address']})\n"
            f"   📌 Alert ID: `{data.get('alert_id', 'N/A')}`\n"
            f"   💰 Base Price: ${data['base_price']:.4f}\n"
            f"   💰 Current Price: ${current_price}\n"
            f"   🏦 Base Market Cap: ${data['market_cap']:,.2f}\n"
            f"   🏦 Current Market Cap: ${current_market_cap}\n"
            f"   🔢 Current Multiples: {current_multiple}\n"
        )

    await update.message.reply_text(message, parse_mode="Markdown")


async def monitor_prices():
    """Periodically checks token prices and alerts users if they hit a multiple."""
    while True:
        for alert_id, data in list(user_tracking.items()):
            current_price, _ = fetch_token_price(data["pair_address"])
            if current_price:
                multiple = current_price / data["base_price"]
                next_multiple = data["last_multiple"] + 1

                if multiple >= next_multiple:
                    chat_id = data["chat_id"]
                    await bot.send_message(
                        chat_id,
                        f"🚀 **Price Alert!** 🚀\n"
                        f"🪙 **{data['token_name']}** has reached **{next_multiple}x** its base price!\n"
                        f"💰 Base Price: ${data['base_price']:.4f}\n"
                        f"💰 Current Price: ${current_price:.4f}\n",
                        parse_mode="Markdown"
                    )
                    user_tracking[alert_id]["last_multiple"] = next_multiple
                    save_tracking_data()  # Update Firebase
        
        await asyncio.sleep(60)  

def main():
    """Start the Telegram bot."""
    load_tracking_data()  # Load tracking data from Firebase on startup

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("list", list_alerts))

    loop = asyncio.get_event_loop()
    loop.create_task(monitor_prices())  

    application.run_polling()

if __name__ == "__main__":
    main()



# import requests
# import firebase_admin
# from firebase_admin import credentials, firestore
# from telegram import Update, Bot
# from telegram.ext import (
#     Application,
#     CommandHandler,
#     ContextTypes,
# )
# import asyncio
# import uuid
# import json

# # Initialize Firebase
# cred = credentials.Certificate("serviceAccountKey.json")  # Replace with your Firebase service account key
# firebase_admin.initialize_app(cred)
# db = firestore.client()

# # Telegram Bot Token
# TELEGRAM_BOT_TOKEN = "7780461778:AAH46gAVF9WkkjzJ-QQbGwm2XmsXOCUJWDc"
# bot = Bot(token=TELEGRAM_BOT_TOKEN)

# # Global tracking dictionary
# user_tracking = {}  # Stores alerts by alert_id

# def load_tracking_data():
#     """Load tracked tokens from Firebase Firestore on startup."""
#     global user_tracking
#     user_tracking.clear()  # Reset local dictionary

#     docs = db.collection("tracked_tokens").stream()
#     for doc in docs:
#         user_tracking[doc.id] = doc.to_dict()

# def save_tracking_data():
#     """Save the current user tracking data to Firestore."""
#     for alert_id, data in user_tracking.items():
#         db.collection("tracked_tokens").document(alert_id).set(data)

# def delete_tracking_data(alert_id):
#     """Delete a specific tracking alert from Firestore."""
#     db.collection("tracked_tokens").document(alert_id).delete()

# def get_pair_address(token_address):
#     """Finds the correct SOL trading pair for the given token address and returns token name."""
#     url = f"https://api.dexscreener.com/latest/dex/search?q={token_address}"
#     response = requests.get(url)

#     if response.status_code == 200:
#         data = response.json()
#         pairs = data.get("pairs", [])

#         for pair in pairs:
#             if "SOL" in pair["baseToken"]["symbol"] or "SOL" in pair["quoteToken"]["symbol"]:
#                 token_name = pair["baseToken"]["name"]
#                 return pair["pairAddress"], token_name  

#     return None, None  # No valid pair found

# def fetch_token_price(pair_address):
#     """Fetch the current price and market cap of the token in the SOL pair."""
#     url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
#     response = requests.get(url)

#     if response.status_code == 200:
#         data = response.json()
#         if "pairs" in data and data["pairs"]:  
#             pair_data = data["pairs"][0]
#             price = float(pair_data.get("priceUsd", 0))
#             market_cap = float(pair_data.get("fdv", 0))  
#             return price, market_cap

#     return None, None  

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Send a welcome message."""
#     await update.message.reply_text(
#         "Welcome! Send me the token address (e.g., 5D27E...pump), and I'll track its price against SOL."
#     )

# async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Start tracking the token against SOL with a unique alert ID, max 10 tokens per user."""
#     chat_id = update.effective_chat.id
#     user_alerts = [alert_id for alert_id, data in user_tracking.items() if data["chat_id"] == chat_id]
#     if len(user_alerts) >= 10:
#         await update.message.reply_text("⚠️ You can only track a maximum of 10 tokens at a time. Delete some before adding new ones.")
#         return

#     try:
#         token_address = context.args[0]
#         pair_address, token_name = get_pair_address(token_address)

#         if pair_address:
#             token_price, market_cap = fetch_token_price(pair_address)
#             if token_price:
#                 alert_id = str(uuid.uuid4())[:8]  
#                 user_tracking[alert_id] = {
#                     "chat_id": chat_id,
#                     "token_name": token_name,
#                     "token_address": token_address,
#                     "pair_address": pair_address,
#                     "base_price": token_price,
#                     "market_cap": market_cap,
#                     "last_multiple": 1,
#                 }
#                 save_tracking_data()  # Save to Firebase
#                 await update.message.reply_text(
#                     f"🔔 Tracking Started!\n"
#                     f"📌 Alert ID: `{alert_id}`\n"
#                     f"🪙 Token: {token_name} ({token_address})\n"
#                     f"💰 Starting Price: ${token_price:.4f}\n"
#                     f"🏦 Market Cap: ${market_cap:,.2f}\n"
#                     f"❌ Use `/delete {alert_id}` to stop tracking.", parse_mode="Markdown"
#                 )
#             else:
#                 await update.message.reply_text("❌ Failed to fetch the token price.")
#         else:
#             await update.message.reply_text("❌ Could not find a SOL trading pair for this token.")
#     except IndexError:
#         await update.message.reply_text("⚠️ Please provide a token address. Example:\n`/track 5D27E...pump`")

# async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Deletes an active alert by its ID."""
#     try:
#         alert_id = context.args[0]
#         if alert_id in user_tracking:
#             del user_tracking[alert_id]
#             delete_tracking_data(alert_id)  # Remove from Firebase
#             await update.message.reply_text(f"✅ Alert `{alert_id}` has been deleted successfully.")
#         else:
#             await update.message.reply_text("❌ Alert ID not found.")
#     except IndexError:
#         await update.message.reply_text("⚠️ Please provide an alert ID to delete. Example:\n`/delete abc12345`")

# async def monitor_prices():
#     """Periodically checks token prices and alerts users if they hit a multiple."""
#     while True:
#         for alert_id, data in list(user_tracking.items()):
#             current_price, _ = fetch_token_price(data["pair_address"])
#             if current_price:
#                 multiple = current_price / data["base_price"]
#                 next_multiple = data["last_multiple"] + 1

#                 if multiple >= next_multiple:
#                     chat_id = data["chat_id"]
#                     await bot.send_message(
#                         chat_id,
#                         f"🚀 **Price Alert!** 🚀\n"
#                         f"🪙 **{data['token_name']}** has reached **{next_multiple}x** its base price!\n"
#                         f"💰 Base Price: ${data['base_price']:.4f}\n"
#                         f"💰 Current Price: ${current_price:.4f}\n",
#                         parse_mode="Markdown"
#                     )
#                     user_tracking[alert_id]["last_multiple"] = next_multiple
#                     save_tracking_data()  # Update Firebase
        
#         await asyncio.sleep(60)  

# def main():
#     """Start the Telegram bot."""
#     load_tracking_data()  # Load tracking data from Firebase on startup

#     application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(CommandHandler("track", track))
#     application.add_handler(CommandHandler("delete", delete))

#     loop = asyncio.get_event_loop()
#     loop.create_task(monitor_prices())  

#     application.run_polling()

# if __name__ == "__main__":
#     main()



# import requests
# from telegram import Update, Bot
# from telegram.ext import (
#     Application,
#     CommandHandler,
#     ContextTypes,
# )
# import asyncio
# import uuid

# # Telegram Bot Token
# TELEGRAM_BOT_TOKEN = "7780461778:AAH46gAVF9WkkjzJ-QQbGwm2XmsXOCUJWDc"
# bot = Bot(token=TELEGRAM_BOT_TOKEN)

# # Global tracking dictionary
# user_tracking = {}  # Stores alerts by alert_id

# def get_pair_address(token_address):
#     """Finds the correct SOL trading pair for the given token address and returns token name."""
#     url = f"https://api.dexscreener.com/latest/dex/search?q={token_address}"
#     response = requests.get(url)

#     if response.status_code == 200:
#         data = response.json()
#         pairs = data.get("pairs", [])

#         for pair in pairs:
#             if "SOL" in pair["baseToken"]["symbol"] or "SOL" in pair["quoteToken"]["symbol"]:
#                 token_name = pair["baseToken"]["name"]
#                 return pair["pairAddress"], token_name  

#     return None, None  # No valid pair found

# def fetch_token_price(pair_address):
#     """Fetch the current price and market cap of the token in the SOL pair."""
#     url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
#     response = requests.get(url)

#     if response.status_code == 200:
#         data = response.json()
#         if "pairs" in data and data["pairs"]:  # Ensure "pairs" is not None or empty
#             pair_data = data["pairs"][0]
#             price = float(pair_data.get("priceUsd", 0))
#             market_cap = float(pair_data.get("fdv", 0))  # 'fdv' represents fully diluted market cap
#             return price, market_cap

#     return None, None  # Return None values if no data is available

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Send a welcome message."""
#     await update.message.reply_text(
#         "Welcome! Send me the token address (e.g., 5D27E...pump), and I'll track its price against SOL."
#     )

# async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Start tracking the token against SOL with a unique alert ID, max 10 tokens per user."""
#     chat_id = update.effective_chat.id
#     user_alerts = [alert_id for alert_id, data in user_tracking.items() if data["chat_id"] == chat_id]
#     if len(user_alerts) >= 10:
#         await update.message.reply_text("⚠️ You can only track a maximum of 10 tokens at a time. Delete some before adding new ones.")
#         return

#     try:
#         token_address = context.args[0]
#         pair_address, token_name = get_pair_address(token_address)

#         if pair_address:
#             token_price, market_cap = fetch_token_price(pair_address)
#             if token_price:
#                 alert_id = str(uuid.uuid4())[:8]  # Generate short unique alert ID
#                 user_tracking[alert_id] = {
#                     "chat_id": chat_id,
#                     "token_name": token_name,
#                     "token_address": token_address,
#                     "pair_address": pair_address,
#                     "base_price": token_price,
#                     "market_cap": market_cap,
#                     "last_multiple": 1,
#                 }
#                 await update.message.reply_text(
#                     f"🔔 Tracking Started!\n"
#                     f"📌 Alert ID: `{alert_id}`\n"
#                     f"🪙 Token: {token_name} ({token_address})\n"
#                     f"🔗 Pair: {pair_address}\n"
#                     f"💰 Starting Price: ${token_price:.4f}\n"
#                     f"🏦 Market Cap: ${market_cap:,.2f}\n"
#                     f"❌ Use `/delete {alert_id}` to stop tracking.", parse_mode="Markdown"
#                 )
#             else:
#                 await update.message.reply_text("❌ Failed to fetch the token price.")
#         else:
#             await update.message.reply_text("❌ Could not find a SOL trading pair for this token.")
#     except IndexError:
#         await update.message.reply_text("⚠️ Please provide a token address. Example:\n`/track 5D27E...pump`")

# async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Deletes an active alert by its ID."""
#     try:
#         alert_id = context.args[0]
#         if alert_id in user_tracking:
#             del user_tracking[alert_id]
#             await update.message.reply_text(f"✅ Alert `{alert_id}` has been deleted successfully.")
#         else:
#             await update.message.reply_text("❌ Alert ID not found.")
#     except IndexError:
#         await update.message.reply_text("⚠️ Please provide an alert ID to delete. Example:\n`/delete abc12345`")

# async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Lists all active alerts for a user with additional details."""
#     chat_id = update.effective_chat.id
#     user_alerts = [(alert_id, data) for alert_id, data in user_tracking.items() if data["chat_id"] == chat_id]

#     if not user_alerts:
#         await update.message.reply_text("📭 You are not tracking any tokens.")
#         return

#     message = "📋 **Your Active Alerts:**\n"
#     for idx, (alert_id, data) in enumerate(user_alerts, start=1):
#         current_price, current_market_cap = fetch_token_price(data["pair_address"])  # Fetch latest details
#         if current_price:
#             current_multiple = current_price / data["base_price"]
#         else:
#             current_price, current_market_cap, current_multiple = "N/A", "N/A", "N/A"
        
#         message += (
#             f"\n{idx}. 🪙 **{data['token_name']}** ({data['token_address']})\n"
#             f"   📌 Alert ID: `{alert_id}`\n"
#             f"   💰 Base Price: ${data['base_price']:.4f}\n"
#             f"   💰 Current Price: ${current_price}\n"
#             f"   🏦 Base Market Cap: ${data['market_cap']:,.2f}\n"
#             f"   🏦 Current Market Cap: ${current_market_cap}\n"
#             f"   🔢 Current Multiples: {current_multiple}\n"
#         )

#     await update.message.reply_text(message, parse_mode="Markdown")

# async def monitor_prices():
#     """Periodically checks token prices and alerts users if they hit a multiple."""
#     while True:
#         for alert_id, data in list(user_tracking.items()):
#             current_price, _ = fetch_token_price(data["pair_address"])
#             if current_price:
#                 multiple = current_price / data["base_price"]
#                 next_multiple = data["last_multiple"] + 1

#                 if multiple >= next_multiple:
#                     chat_id = data["chat_id"]
#                     await bot.send_message(
#                         chat_id,
#                         f"🚀 **Price Alert!** 🚀\n"
#                         f"🪙 **{data['token_name']}** has reached **{next_multiple}x** its base price!\n"
#                         f"💰 Base Price: ${data['base_price']:.4f}\n"
#                         f"💰 Current Price: ${current_price:.4f}\n",
#                         parse_mode="Markdown"
#                     )
#                     user_tracking[alert_id]["last_multiple"] = next_multiple  # Update last triggered multiple
        
#         await asyncio.sleep(60)  # Check every 60 seconds

# def main():
#     """Start the Telegram bot."""
#     application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(CommandHandler("track", track))
#     application.add_handler(CommandHandler("delete", delete))
#     application.add_handler(CommandHandler("list", list_alerts))
    
#     loop = asyncio.get_event_loop()
#     loop.create_task(monitor_prices())  # Start monitoring in the background

#     application.run_polling()

# if __name__ == "__main__":
#     main()
