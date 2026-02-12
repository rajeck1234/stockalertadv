from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
import os
import json
import threading
import time
import requests
app = Flask(__name__, static_folder="public")
CORS(app)

PORT = int(os.environ.get("PORT", 3000))

print("CURRENT WORKING DIR:", os.getcwd())
import asyncio
import aiohttp
BASE_URL = "https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/NSE/segment/CASH/latest_prices_ohlc/{}"

# BASE_URL = "https://groww.in/v1/api/stocks_data/v1/tr_live_book/exchange/NSE/segment/CASH/{}/latest"

SEM = asyncio.Semaphore(50)
# -----------------------------
# JSON Helpers
# -----------------------------
def load_json(file, default):
    try:
        with open(file) as f:
            return json.load(f)
    except:
        return default

# def save_json(file, data):
    
#     print("\n===== SAVE_JSON CALLED =====")
#     print("File:", file)

#     print("Data going to be saved:")
#     for item in data:
#         print(item)

#     with open(file, "w") as f:
#         json.dump(data, f, indent=2)

#     print("File write completed")

#     # Verify file content immediately
#     try:
#         with open(file, "r") as f:
#             verify = json.load(f)

#         print("Data read back from file:")
#         for item in verify:
#             print(item)

#     except Exception as e:
#         print("Verification read failed:", e)

#     print("===== SAVE_JSON END =====\n")



def save_json(file, data):
    # print(file)
    # print(data)
    with open(file, "w") as f:
        # print("check")
        # print(file)
        json.dump(data, f, indent=2)
    # print("Full file path:", os.path.abspath(file))
    # with open(file, "r") as f:
    #     content = json.load(f)   # load json data
    #     print("JSON file content:")
    #     print(content)
# -----------------------------
# Load Files
# -----------------------------
stocks = load_json("stocks.json", [])
portfolio = load_json("portfolio.json", [])
prices_cache = load_json("prices.json", {})
# -----------------------------
# Load CSV Momentum Stocks
# -----------------------------
import pandas as pd
import logging

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

df = pd.read_csv("ind_copy.csv")

if "Symbol" not in df.columns:
    raise Exception("CSV must contain 'Symbol' column")

def clean_symbol(symbol):
    symbol = str(symbol).strip()
    symbol = symbol.replace("$", "")
    symbol = symbol.replace("-", "")
    return symbol + ".NS"

stocks1 = [clean_symbol(s) for s in df["Symbol"].tolist()]

print("Momentum stock list loaded:", len(stocks1))


# -----------------------------
# ⭐ BEST PRICE FETCH FUNCTION
# -----------------------------
def fetch_price(symbol):

    try:
        ticker = yf.Ticker(symbol)

        # 1️⃣ Primary
        price = ticker.info.get("currentPrice")

        # 2️⃣ Fallback
        
        if price is None:
            price = ticker.fast_info.get("last_price")

        # 3️⃣ Last fallback
        if price is None:
            hist = ticker.history(period="1d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]

        return price

    except Exception as e:
        print("Fetch error:", symbol, e)
        return None


# -----------------------------
# Update Prices From Yahoo
# -----------------------------
def update_prices():
    global prices_cache

    print("Updating prices...")

    for symbol in stocks:

        price = fetch_price(symbol)

        if price:
            prices_cache[symbol] = float(price)

    save_json("prices.json", prices_cache)


# -----------------------------
# Background Scheduler
# -----------------------------
def scheduler():
    while True:
        update_prices()
        time.sleep(5)

momentum_30_cache = []
momentum_3min_cache = []
momentum_30_price_cache = []
momentum_3min_price_cache = []

last_10_cycles = load_json("last_10_cycles.json", [])

# def fetch_all_prices():
    
#     try:
#         data = yf.download(
#             stocks1,
#             period="1d",
#             interval="1m",
#             group_by="ticker",
#             threads=False,
#             progress=False
#         )

#         prices = {}

#         for symbol in stocks1:
#             try:
#                 price = data[symbol]["Close"].iloc[-1]

#                 if price is not None and not pd.isna(price):
#                     prices[symbol] = float(price)
#                 else:
#                     prices[symbol] = 0

#             except:
#                 pass

#         return prices

#     except:
#         return {}



async def fetch_price_async(session, symbol):

    grow_symbol = symbol.replace(".NS", "")

    url = BASE_URL.format(grow_symbol)

    try:
        async with SEM:
            async with session.get(url) as response:
                data = await response.json()
                # print(data)
                # best_sell = data.get("sellBook", {}).get("1", {}).get("price")
                ltp_price = data.get("ltp")
                # print(symbol)
                # print(ltp_price)
                if ltp_price:
                    return symbol, float(ltp_price)

                return symbol, 0

                # if best_sell is not None:
                #     return symbol, float(best_sell)

                # return symbol, 0

    except:
        return symbol, 0


async def fetch_all_prices_async():

    prices = {}

    async with aiohttp.ClientSession() as session:

        tasks = [fetch_price_async(session, symbol) for symbol in stocks1]

        results = await asyncio.gather(*tasks)

        for symbol, price in results:
            prices[symbol] = price
    # print(price)
    return prices


# def fetch_all_prices():
#     return asyncio.run(fetch_all_prices_async())


def calculate_momentum(start, end):

    results = []
    # print("0")
    for stock in start:
        if stock in end and start[stock] != 0:
            change = ((end[stock] - start[stock]) / start[stock]) * 100
            results.append({
                "name": stock,
                "price": end[stock],
                "change": round(change,3)
            })

    results.sort(key=lambda x: x["change"], reverse=True)
    return results

def calculate_price_raise(start, end):
    
    results = []

    for stock in start:
        if stock in end:
            price_diff = end[stock] - start[stock]

            if price_diff > 0:
                results.append({
                    "name": stock,
                    "price": end[stock],
                    "diff": round(price_diff,3)
                })

    results.sort(key=lambda x: x["diff"], reverse=True)
    return results[:5]

def calculate_static_momentum(cycles):
    
    results = []
   
    if len(cycles) < 2:
        return []

    start_cycle = cycles[0]
    end_cycle = cycles[-1]

    for stock in start_cycle:

        if stock in end_cycle and start_cycle[stock] != 0:

            start_price = start_cycle[stock]
            end_price = end_cycle[stock]

            change = ((end_price - start_price) / start_price) * 100

            results.append({
                "name": stock,
                "price": end_price,
                "change": round(change, 3)
            })

    results.sort(key=lambda x: x["change"], reverse=True)

    return results[:5]

def calculate_static_price_raise(cycles):
    
    results = []

    if len(cycles) < 2:
        return []

    start_cycle = cycles[0]
    end_cycle = cycles[-1]

    for stock in start_cycle:

        if stock in end_cycle:

            price_diff = end_cycle[stock] - start_cycle[stock]

            if price_diff > 0:

                results.append({
                    "name": stock,
                    "price": end_cycle[stock],
                    "diff": round(price_diff,3)
                })

    results.sort(key=lambda x: x["diff"], reverse=True)

    return results[:5]
def momentum_scheduler():
    
    global momentum_30_cache
    global momentum_3min_cache
    global momentum_30_price_cache
    global momentum_3min_price_cache
    global last_10_cycles

    # ✅ Create ONE event loop only once
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    previous_prices = loop.run_until_complete(fetch_all_prices_async())

    if not previous_prices:
        previous_prices = {}

    while True:

        current_prices = loop.run_until_complete(fetch_all_prices_async())
        # print(current_prices)
        if not current_prices:
            time.sleep(5)
            continue

        # ⭐ 30 SEC MOMENTUM
        if previous_prices:

            temp_percent = calculate_momentum(previous_prices, current_prices)
            momentum_30_cache = temp_percent[:5]

            temp_price = calculate_price_raise(previous_prices, current_prices)
            momentum_30_price_cache = temp_price

        previous_prices = current_prices

        # ⭐ STORE LAST 5 CYCLES
        last_10_cycles.append(current_prices)

        if len(last_10_cycles) > 5:
            last_10_cycles.pop(0)

        save_json("last_10_cycles.json", last_10_cycles)

        # ⭐ 3 MIN MOMENTUM
        if len(last_10_cycles) == 5:

            momentum_3min_cache = calculate_static_momentum(last_10_cycles)
            momentum_3min_price_cache = calculate_static_price_raise(last_10_cycles)

        time.sleep(10)

# def momentum_scheduler():
    
#     global momentum_30_cache
#     global momentum_3min_cache
#     global momentum_30_price_cache
#     global momentum_3min_price_cache
#     global last_10_cycles

#     previous_prices = fetch_all_prices()
   
#     if not previous_prices:
#         previous_prices = {}

#     while True:

#         current_prices = fetch_all_prices()
#         print(current_prices)
#         if not current_prices:
#             time.sleep(5)
#             continue

#         # ===============================
#         # ⭐ 5 SEC PERCENTAGE MOMENTUM
#         # ===============================
#         if previous_prices:

#             temp_percent = calculate_momentum(previous_prices, current_prices)
#             momentum_30_cache = temp_percent[:5]

#             # ⭐ ADD PRICE MOMENTUM
#             temp_price = calculate_price_raise(previous_prices, current_prices)
#             momentum_30_price_cache = temp_price
#             # print(momentum_30_cache)
#             # print(momentum_30_price_cache)
#             # print(current_prices)
#         previous_prices = current_prices

#         # ===============================
#         # ⭐ STORE LAST 5 CYCLES
#         # ===============================
#         last_10_cycles.append(current_prices)

#         if len(last_10_cycles) > 5:
#             last_10_cycles.pop(0)

#         save_json("last_10_cycles.json", last_10_cycles)

#         # ===============================
#         # ⭐ 3 MIN PERCENTAGE MOMENTUM
#         # ===============================
#         if len(last_10_cycles) == 5:

#             momentum_3min_cache = calculate_static_momentum(last_10_cycles)

#             # ⭐ ADD PRICE MOMENTUM
#             momentum_3min_price_cache = calculate_static_price_raise(last_10_cycles)
#             # print(momentum_3min_cache)
#             # print(momentum_3min_price_cache)

#         time.sleep(10)

# def momentum_scheduler():
    
#     global momentum_30_cache, momentum_3min_cache, last_10_cycles

#     # ⭐ Pre-load first cycle to avoid empty UI
#     previous_prices = fetch_all_prices()
#     # print(previous_prices)
#     if not previous_prices:
#         previous_prices = {}

#     while True:

#         current_prices = fetch_all_prices()

#         # ⭐ If fetch failed, skip cycle
#         if not current_prices:
#             time.sleep(5)
#             continue

#         # -------------------------
#         # ⭐ 5 SEC MOMENTUM
#         # -------------------------
#         if previous_prices:
#             temp = calculate_momentum(previous_prices, current_prices)
#             momentum_30_cache = temp[:5]

#         previous_prices = current_prices

#         # -------------------------
#         # ⭐ STORE LAST 10 CYCLES
#         # -------------------------
#         if current_prices:

#             last_10_cycles.append(current_prices)

#             # Keep only last 10 cycles
#             if len(last_10_cycles) > 5:
#                 last_10_cycles.pop(0)

#             save_json("last_10_cycles.json", last_10_cycles)

#         # -------------------------
#         # ⭐ 3 MIN STATIC MOMENTUM
#         # -------------------------
#         if len(last_10_cycles) == 5:

#             momentum_3min_cache = calculate_static_momentum(last_10_cycles)

#         # ⭐ Wait 5 seconds
#         time.sleep(10)


@app.route("/momentum30")
def momentum30():
    return jsonify(momentum_30_cache)

@app.route("/momentum3min")
def momentum3min():
    return jsonify(momentum_3min_cache)

@app.route("/momentum30price")
def momentum30price():
    return jsonify(momentum_30_price_cache)

@app.route("/momentum3minprice")
def momentum3minprice():
    return jsonify(momentum_3min_price_cache)

# -----------------------------
# Serve Frontend
# -----------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


# -----------------------------
# Get Stocks
# -----------------------------
@app.route("/stocks")
def get_stocks():

    result = []
    # print("jss")
    for symbol in stocks:
        result.append({
            "name": symbol,
            "price": prices_cache.get(symbol)
        })
        # print(result)
        # print(symbol)
    return jsonify(result)


# -----------------------------
# Add Stock
# -----------------------------
@app.route("/add-stock", methods=["POST"])
def add_stock():
    
    data = request.get_json()
    symbol = data["symbol"].upper() 
    if not symbol.endswith(".NS"):
        symbol += ".NS"

    if symbol not in stocks:
        stocks.append(symbol)
        save_json("stocks.json", stocks)

    return jsonify(stocks)


@app.route("/removeStock/<name>", methods=["DELETE"])
def remove_stock(name):

    if name in stocks:
        stocks.remove(name)
        save_json("stocks.json", stocks)
        return jsonify({"status":"removed"})

    return jsonify({"status":"not found"})

# -----------------------------
# Portfolio
# -----------------------------
@app.route("/portfolio")
def get_portfolio():
    return jsonify(portfolio)


# -----------------------------
# Buy Stock
# -----------------------------
@app.route("/buy", methods=["POST"])
def buy_stock():

    data = request.get_json()
    buy_price = float(data["price"])

    stock = {
        "name": data["name"],
        "buy_price": buy_price,
        "target_price": buy_price,
        "highest_price": buy_price,
        "alert_triggered": False
    }
    portfolio.append(stock)
    save_json("portfolio.json", portfolio)

    return jsonify(portfolio)


# -----------------------------
# Sell Stock
# -----------------------------
@app.route("/sell", methods=["POST"])
def sell_stock():

    name = request.get_json()["name"]

    global portfolio
    portfolio = [s for s in portfolio if s["name"] != name]

    save_json("portfolio.json", portfolio)

    return jsonify(portfolio)


# -----------------------------
# ALERT LOGIC
# -----------------------------

@app.route("/check-alerts")
def check_alerts():

    alerts = []

    for stock in portfolio:

        symbol = stock["name"]
        current_price = prices_cache.get(symbol)

        if current_price is None:
            continue

        buy_price = stock["buy_price"]

        # Initialize highest price
        if "highest_price" not in stock:
            stock["highest_price"] = buy_price

        # Update highest price
        if current_price > stock["highest_price"]:
            
            stock["highest_price"] = current_price

        highest_price = stock["highest_price"]

        # -----------------------------
        # 🔴 CONDITION 1: STOP LOSS
        # -----------------------------
        stop_loss_price = buy_price - 3

        # -----------------------------
        # 🔴 CONDITION 2: TRAILING STOP
        # -----------------------------
        trailing_price = highest_price - 5

        # -----------------------------
        # 🚨 ALARM CONDITIONS
        # -----------------------------
        print("utkarsh")
        print(stop_loss_price)
        print(current_price)
        if current_price >= stop_loss_price:
            print(current_price)
            print(stop_loss_price)
            print(f"🚨 STOP LOSS HIT: {symbol}")
            alerts.append(symbol)

        elif current_price <= trailing_price:
            print(f"🚨 TRAILING STOP HIT: {symbol}")
            alerts.append(symbol)

    save_json("portfolio.json", portfolio)
    return jsonify(alerts)

# @app.route("/check-alerts")
# def check_alerts():

#     alerts = []

#     for stock in portfolio:

#         symbol = stock["name"]
#         current_price = prices_cache.get(symbol)

#         if current_price is None:
#             continue

#         buy_price = stock["buy_price"]
#         target_price = stock["target_price"]

#         # Initialize last price if not exists
#         if "last_price" not in stock:
#             stock["last_price"] = current_price

#         # Ignore until +3% profit
#         if current_price < target_price:
#             stock["alert_triggered"] = False
#             stock["last_price"] = current_price
#             continue

#         # Update highest price
#         if current_price > stock["highest_price"]:
#             stock["highest_price"] = current_price
#             stock["alert_triggered"] = False

#         highest_price = stock["highest_price"]
#         last_price = stock["last_price"]

#         # Calculate drop from highest
#         drop_percent = (highest_price - current_price) / highest_price

#         # 🟥 Alarm ON → falling direction + drop threshold
#         # print(current_price)
#         # print(last_price)
#         if (current_price <= last_price):
#             stock["alert_triggered"] = True
#             alerts.append(symbol)

#         # 🟩 Alarm OFF → price rising
#         if current_price > last_price:
#             stock["alert_triggered"] = False

#         # Update last price
#         stock["last_price"] = current_price

#     save_json("portfolio.json", portfolio)
#     return jsonify(alerts)


# -----------------------------
# Run Server
# -----------------------------
if __name__ == "__main__":

    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=momentum_scheduler, daemon=True).start()

    app.run(host="0.0.0.0", port=PORT)

