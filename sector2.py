import requests
import pyotp
import datetime
import time
from tabulate import tabulate
import pandas as pd
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('TkAgg') 
# Importing sector stock lists from watchlist module , do not change the watchlist file content 
from watchlist import (
    banking_and_finance,automobiles,oil_and_gas,
    it_and_services,pharmaceuticals,metals_and_mining,chemicals,
    construction_and_cement,consumer_goods,utilities,real_estate,
    telecom,media,retail,capital_goods_and_engineering,transportation_and_logistics,
    hospital_and_healthcare,miscellaneous
) # Your sector stock lists

# === Credentials and API setup ===
API_KEY = ""
CLIENT_CODE = ""
PASSWORD = ""
TOTP_SECRET = ""# Your TOTP secret key
EXCHANGE = "NSE"
TIME_DELAY = 0.5 # seconds delay between API calls to avoid rate limiting

# Login to Angel One API
smartApi = SmartConnect(api_key=API_KEY)
totp = pyotp.TOTP(TOTP_SECRET).now()
login_data = smartApi.generateSession(CLIENT_CODE, PASSWORD, totp)
AUTH_TOKEN = login_data['data']['jwtToken']
FEED_TOKEN = smartApi.getfeedToken()

# Load instrument master to map symbols to tokens
print("Fetching instrument master list...")
response = requests.get("https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json")
instruments = response.json()

# Build symbol to token map for NSE stocks
symbol_to_token = {
    item['symbol']: item['token']
    for item in instruments if item['exch_seg'] == EXCHANGE
}

# Global dictionary to store OI change by token updated by WebSocket
oi_data = {}

#for fetching live price data
'''
# === WebSocket setup to fetch live OI data ===
def on_data(wsapp, message):
    print("[WebSocket] Received message:", message)
    for item in message:
        token = item.get('token')
        # Use open_interest_change_percentage as oi_change (default to 0 if missing)
        oi_change = item.get('open_interest_change_percentage', 0)
        if token:
            oi_data[token] = {
                'oi_change': oi_change
            }

def on_open(wsapp):
    print("WebSocket connected, subscribing to OI data...")
    all_tokens = []
    # Combine all symbol lists from both sectors
    for stocks in list(banking_and_finance.values()) + list(media.values()+list(real_estate.values())):
        for sym in stocks:
            token = symbol_to_token.get(sym)
            if token:
                all_tokens.append(token)
    # Subscribe with mode=3 (market data)
    wsapp.subscribe("sector-oi", 3, [{"exchangeType": 1, "tokens": all_tokens}])
def on_error(wsapp, error):
    print("WebSocket Error:", error)

def on_close(wsapp):
    print("WebSocket closed")

sws = SmartWebSocketV2(AUTH_TOKEN, API_KEY, CLIENT_CODE, FEED_TOKEN)
sws.on_open = on_open
sws.on_data = on_data
sws.on_error = on_error
sws.on_close = on_close

# Start websocket connection in a separate thread to keep receiving OI data
import threading
def run_websocket():
    sws.connect()

ws_thread = threading.Thread(target=run_websocket, daemon=True)
ws_thread.start()
'''
# Function to fetch candle data (5 days) for a stock
def fetch_candle_data(symbol, days=7):
    token = symbol_to_token.get(symbol)
    if not token:
        print(f"Token not found for {symbol}")
        return None

    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=days)

    params = {
        "exchange": EXCHANGE,
        "symboltoken": str(token),
        "interval": "ONE_DAY",#FIVE_MINUTE",ONE_DAY ETC
        "fromdate": start.strftime('%Y-%m-%d %H:%M'),
        "todate": end.strftime('%Y-%m-%d %H:%M')
    }

    retries = 3
    for attempt in range(retries):
        try:
            response = smartApi.getCandleData(params)
            time.sleep(TIME_DELAY)  # Delay to avoid rate limiting
            if 'data' not in response or not response['data']:
                print(f"No candle data for {symbol}")
                return None

            df = pd.DataFrame(response['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            return df
        except Exception as e:
            print(f"Error fetching candle data for {symbol} (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                return None

# Calculate metrics per stock
def calculate_stock_metrics(symbol):
    candle_df = fetch_candle_data(symbol)
    if candle_df is None or len(candle_df) < 2:
        print(f"[WARN] Skipping {symbol}: No valid candle data")
        return None

    price_change = candle_df['close'].iloc[-1] - candle_df['open'].iloc[-1]
    avg_volume = candle_df['volume'].mean()
    current_volume = candle_df['volume'].iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

    returns = candle_df['close'].pct_change().dropna()
    volatility = returns.std() * 100 if not returns.empty else 0

    return {
        "price_change": round(price_change, 2),
        "volume_ratio": round(volume_ratio, 2),
        "volatility": round(volatility, 2)
    }

# Analyze each sector
def analyze_sectors(sectors_dict):
    sector_results = {}
    for sector, stocks in sectors_dict.items():
        print(f"\nAnalyzing sector: {sector} ({len(stocks)} stocks)")

        metrics_list = []
        for symbol in stocks:
            metrics = calculate_stock_metrics(symbol)
            if metrics:
                metrics_list.append(metrics)

            time.sleep(TIME_DELAY)

        if not metrics_list:
            print(f"No data for sector {sector}")
            continue

        df = pd.DataFrame(metrics_list)

        # Calculate averages
        avg_price_change = df['price_change'].mean()
        avg_volume_ratio = df['volume_ratio'].mean()
        avg_volatility = df['volatility'].mean()

        sector_results[sector] = {
            "avg_price_change": round(avg_price_change, 2),
            "avg_volume_ratio": round(avg_volume_ratio, 2),
            "avg_volatility": round(avg_volatility, 2),
            "num_stocks_analyzed": len(metrics_list)
        }

    return sector_results

# Classify sector based on average metrics
def classify_sector(metrics):
    price = metrics["avg_price_change"]
    volume = metrics["avg_volume_ratio"]
    vol = metrics["avg_volatility"]

    if price > 0.5 and volume > 1  and vol < 2:
        return "Leading"
    elif price > 0.3 and volume > 0.6:
        return "Improving"
    elif price < -0.3 and volume < 0.6:
        return "Weakening"
    else:
        return "Lacking"

# Main function
def main():
    print("Waiting 30 seconds to prepare for analysis...")
    time.sleep(5)

    # Build the sector dictionary manually if each is a list
    #As of now the sectors are commented out to avoid confusion, to perdorm analysis on all sectors,
    #  uncomment the lines below or uncomment the sectors you want to analyze
    sectors_to_analyze = {
        #"Banking and Finance": banking_and_finance,
        #"Automobiles": automobiles,
        #"Oil and Gas": oil_and_gas,
        #"IT and Services": it_and_services,
        #"Pharmaceuticals": pharmaceuticals,
        #"Metals and Mining": metals_and_mining,
        #"Chemicals": chemicals,
        #"Construction and Cement": construction_and_cement,
        #"Consumer Goods": consumer_goods,
        #"Utilities": utilities,
        #"Real Estate": real_estate,
        #"Telecom": telecom,
        #"Media": media,
        #"Retail": retail,
        #"Capital Goods and Engineering": capital_goods_and_engineering,
        #"Transportation and Logistics": transportation_and_logistics,
        #"Hospital and Healthcare": hospital_and_healthcare,
        #"Miscellaneous": miscellaneous,
    }

    sector_metrics = analyze_sectors(sectors_to_analyze)

    # Prepare data for visualization
    table_data = []
    for sector, metrics in sector_metrics.items():
        classification = classify_sector(metrics)
        table_data.append([
            sector,
            classification,
            metrics['avg_price_change'],
            metrics['avg_volume_ratio'],
            metrics['avg_volatility'],
            metrics['num_stocks_analyzed']
        ])
    headers = ["Sector", "Classification", "PriceΔ", "VolRatio", "Volatility", "Stocks Analyzed"]
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))

    # Convert data to a DataFrame for visualization
    df = pd.DataFrame(table_data, columns=["Sector", "Classification", "PriceΔ", "VolRatio", "Volatility", "Stocks Analyzed"])

    # --- JdK-style Relative Rotation Graph (RRG) using benchmark 22595 ---
    nifty50 = 99926000 
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=5)

    params = {
        "exchange": EXCHANGE,
        "symboltoken": nifty50,
        "interval": "ONE_DAY",
        "fromdate": start.strftime('%Y-%m-%d %H:%M'),
        "todate": end.strftime('%Y-%m-%d %H:%M')
    }

    response = smartApi.getCandleData(params)
    benchmark = pd.DataFrame(response['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    # Update the price change calculation for Nifty 50 benchmark
    nifty_price_changes = []
    for day in range(5, 0, -1):
        if len(benchmark) >= day:
            candle = benchmark.iloc[-day]
            price_change = candle['close'] - candle['open']  # Corrected formula
            nifty_price_changes.append(price_change)
        else:
            nifty_price_changes.append(None)
    print("Nifty Price Changes:", nifty_price_changes)

    # Update the sector rolling metrics calculation
    sector_trajectories = {}
    for sector, stocks in sectors_to_analyze.items():
        price_changes = []
        volume_ratios = []
        for day in range(5, 0, -1):
            day_price_changes = []
            day_volume_ratios = []
            for symbol in stocks:
                df_candle = fetch_candle_data(symbol, days=5)
                if df_candle is not None and len(df_candle) >= day:
                    # Get the candle for the specific day
                    candle = df_candle.iloc[-day]
                    price_change = candle['close'] - candle['open']  # Corrected formula
                    avg_volume = df_candle['volume'].mean()
                    current_volume = candle['volume']
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                    day_price_changes.append(price_change)
                    day_volume_ratios.append(volume_ratio)
            if day_price_changes and day_volume_ratios:
                price_changes.append(sum(day_price_changes) / len(day_price_changes))
                volume_ratios.append(sum(day_volume_ratios) / len(day_volume_ratios))
            else:
                price_changes.append(None)
                volume_ratios.append(None)
        sector_trajectories[sector] = (price_changes, volume_ratios)


    # Gather all x and y values for dynamic axis limits
    all_x = []
    all_y = []
    for sector, (x, y) in sector_trajectories.items():
        all_x.extend([xi for xi in x if xi is not None])
        all_y.extend([yi for yi in y if yi is not None])
    print("all_x:", all_x)
    print("all_y:", all_y)

    # Set axis limits centered at (0,0) with margin

    #optional part to plot JdK-style Relative Rotation Graph (RRG), It will take a lot of time to plot
    # Remove the JdK-style Relative Rotation Graph (RRG) and keep only the normal scatter plot

    plt.figure(figsize=(11, 8))

    # Plot each sector's data as a scatter plot
    for sector, (x, y) in sector_trajectories.items():
        rel_x = []
        for idx, price_change in enumerate(x):
            if price_change is not None and nifty_price_changes[idx] is not None:
                rel_x.append(price_change - nifty_price_changes[idx])
            else:
                rel_x.append(None)
        rel_y = y  # Use volume ratio as momentum

        points = [(xi, yi) for xi, yi in zip(rel_x, rel_y) if xi is not None and yi is not None]
        print(f"Plotting {sector}: rel_x={rel_x}, rel_y={rel_y}, points={points}")
        if len(points) < 2:
            continue
        x_vals = [pt[0] for pt in points]
        y_vals = [pt[1] for pt in points]
        plt.scatter(x_vals, y_vals, linewidths=2, label=sector, s=80, alpha=0.8)
        plt.plot(x_vals, y_vals, linestyle='-', alpha=0.6)  # Add lines connecting the points


    # Add labels and title
    plt.xlabel("Relative Strength (Sector PriceΔ - Benchmark)", fontsize=12)
    plt.ylabel("Momentum (VolRatio)", fontsize=12)
    plt.title("Sector Performance Map", fontsize=15)
    plt.legend(title="Sectors", loc='upper left')
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.tight_layout()
    plt.show()

        
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL ERROR] {e}")

#TO plot the horizontal bar charts, uncomment the following section
'''
  # Horizontal bar chart for PriceΔ
    plt.figure(figsize=(8, 6))
    sns.barplot(y="Sector", x="PriceΔ", data=df, palette="Blues_d")
    plt.title("Average Price Change by Sector", fontsize=8)
    plt.xlabel("Average Price Change", fontsize=12)
    plt.ylabel("Sector", fontsize=12)
    plt.tight_layout()
    plt.show()

    # Horizontal bar chart for Volume Ratio
    plt.figure(figsize=(8, 6))
    sns.barplot(y="Sector", x="VolRatio", data=df, palette="Greens_d")
    plt.title("Average Volume Ratio by Sector", fontsize=8)
    plt.xlabel("Average Volume Ratio", fontsize=12)
    plt.ylabel("Sector", fontsize=12)
    plt.tight_layout()
    plt.show()

    # Horizontal bar chart for Volatility
    plt.figure(figsize=(8, 6))
    sns.barplot(y="Sector", x="Volatility", data=df, palette="Reds_d")
    plt.title("Average Volatility by Sector", fontsize=8)
    plt.xlabel("Average Volatility", fontsize=12)
    plt.ylabel("Sector", fontsize=12)
    plt.tight_layout()
    plt.show()

'''