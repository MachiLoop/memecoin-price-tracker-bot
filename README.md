
---

## **Telegram Bot for Token Price Tracking**  

### **Overview**  
This Telegram bot allows users to track the price of any token on **DexScreener** (Solana network). Users can provide a **token address**, and the bot will:  
- Find the correct **SOL trading pair**.  
- Fetch and display the **current price** and **market capitalization**.  
- Continuously monitor the token price and send alerts when it **doubles (2x, 3x, 4x, ...)**.  

---

### **Features**  
✅ **Track Token Prices:** Users enter a **token address**, and the bot fetches real-time price data.  
✅ **Automatic Alerts:** Sends alerts when the token price reaches **2x, 3x, 4x, ...** its initial value.  
✅ **Market Cap Information:** Displays the token’s **market capitalization** if available.  
✅ **DexScreener Integration:** Uses the **DexScreener API** to fetch real-time data.  

---

### **How It Works**  
1️⃣ **User Inputs a Token Address**  
- Example command:  
  ```
  /track 5D27E...pump
  ```  
- The bot searches for the **SOL trading pair** on **DexScreener**.  
- If found, it fetches:
  - **Token name**
  - **Starting price (USD)**
  - **Market capitalization (if available)**  
- The bot confirms tracking with a message:  
  ```
  Tracking started for token: DeepSeek (5D27E...pump).
  Pair: 3pn6qn28uFSThxWg8jnKzVEXE65Q6rGyRzcCieiKH3z6
  Starting price: $0.1234
  Market Cap: $1,234,567.
  ```

2️⃣ **Automatic Price Monitoring**  
- The bot **checks the token price every 60 seconds**.  
- If the price **reaches a multiple (2x, 3x, 4x, ...)** of the starting price, it sends an alert:  
  ```
  🚀 Price Alert! DeepSeek (5D27E...pump) has reached 2x!
  Current price: $0.2468
  Base price: $0.1234
  ```

---

### **Commands**  
| Command        | Description  |
|---------------|-------------|
| `/start`       | Welcome message with instructions.  |
| `/track <token_address>` | Starts tracking the token’s price against SOL.  |

---

### **API Used**  
The bot fetches data from:  
🔗 **DexScreener API** – `https://api.dexscreener.com/latest/dex`  

---

### **Use Cases**  
📈 **Traders & Investors** – Get notified when a token pumps.  
📊 **Crypto Enthusiasts** – Monitor new Solana tokens in real-time.  

---
