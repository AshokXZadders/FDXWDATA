import requests
import pyotp
import datetime
import time
from tabulate import tabulate
import pandas as pd
from SmartApi import SmartConnect
import tkinter as tk
from tkinter import messagebox
import matplotlib.pyplot as plt
import seaborn as sns

# Assuming 'watchlist.py' exists in the same directory
from watchlist import (
    banking_and_finance, automobiles, oil_and_gas,
    it_and_services, pharmaceuticals, metals_and_mining, chemicals,
    construction_and_cement, consumer_goods, utilities, real_estate,
    telecom, media, retail, capital_goods_and_engineering, transportation_and_logistics,
    hospital_and_healthcare, miscellaneous
) # This are dictionaries/lists of stock symbols per sector , the dictionary file can be downloaded from the watchlist repo.

# Instead of using SmartApi or AngelBroking , you can use yfinance 

# === Global Dictionaries & Settings ===
SECTOR_DICT = {
    "Banking and Finance": banking_and_finance,
    "Automobiles": automobiles,
    "Oil and Gas": oil_and_gas,
    "IT and Services": it_and_services,
    "Pharmaceuticals": pharmaceuticals,
    "Metals and Mining": metals_and_mining,
    "Chemicals": chemicals,
    "Construction and Cement": construction_and_cement,
    "Consumer Goods": consumer_goods,
    "Utilities": utilities,
    "Real Estate": real_estate,
    "Telecom": telecom,
    "Media": media,
    "Retail": retail,
    "Capital Goods and Engineering": capital_goods_and_engineering,
    "Transportation and Logistics": transportation_and_logistics,
    "Hospital and Healthcare": hospital_and_healthcare,
    "Miscellaneous": miscellaneous,
}

# === Credentials and API setup ===
API_KEY = ""
CLIENT_CODE = ""
PASSWORD = ""
TOTP_SECRET = ""
EXCHANGE = ""
TIME_DELAY = 1.25 # IMP as it helps avoid rate limits

# === API Connection (Singleton Pattern) ===
smartApi = None
symbol_to_token = {}

def initialize_api():
    global smartApi, symbol_to_token
    if smartApi:
        return True
    try:
        print("Connecting to API...")
        smartApi = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        login_data = smartApi.generateSession(CLIENT_CODE, PASSWORD, totp)
        
        print("Fetching instrument master list...")
        instruments = requests.get(
            "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        ).json()
        symbol_to_token = {
            item['symbol']: item['token']
            for item in instruments if item['exch_seg'] == EXCHANGE
        }
        print("API Connection Successful.")
        return True
    except Exception as e:
        print(f"Failed to connect to API: {e}")
        return False

# === GUI Functions ===

def initial_choice_gui():
    """The main menu to select which analysis to perform."""
    root = tk.Tk()
    root.title("Financial Analysis Tool")
    root.geometry("350x320") # <-- Increased height again

    tk.Label(root, text="Select an analysis to run:", font=("Arial", 14)).pack(pady=15)
    
    choice = ""
    def set_choice(option):
        nonlocal choice
        choice = option
        root.destroy()

    tk.Button(root, text="Full Sector Analysis", command=lambda: set_choice('sector'), font=("Arial", 11), width=30).pack(pady=5)
    tk.Button(root, text="Stock-Level Analysis", command=lambda: set_choice('stock'), font=("Arial", 11), width=30).pack(pady=5)
    tk.Button(root, text="Sector Correlation Analysis", command=lambda: set_choice('correlation'), font=("Arial", 11), width=30).pack(pady=5)
    tk.Button(root, text="Create Sector Index", command=lambda: set_choice('index'), font=("Arial", 11), width=30).pack(pady=5)
    
    # --- NEW BUTTON ---
    tk.Button(root, text="Stock vs. Sector Index", command=lambda: set_choice('stock_vs_index'), font=("Arial", 11), width=30).pack(pady=5)

    tk.Button(root, text="Exit", command=lambda: set_choice('exit'), font=("Arial", 11), width=30).pack(pady=5)
    
    root.mainloop()
    return choice

def choose_sectors_gui():
    """GUI to select multiple sectors for the main screener."""
    root = tk.Tk()
    root.title("Select Sectors for Screener")
    tk.Label(root, text="Choose sectors to run:", font=("Arial", 12)).pack(pady=8)
    listbox = tk.Listbox(root, selectmode=tk.MULTIPLE, width=40, height=12)
    for sector in SECTOR_DICT.keys():
        listbox.insert(tk.END, sector)
    listbox.pack(padx=10, pady=8)
    selected_sectors = []
    def on_submit():
        sel = [listbox.get(i) for i in listbox.curselection()]
        if not sel:
            messagebox.showwarning("No Selection", "Please select at least one sector.")
            return
        nonlocal selected_sectors
        selected_sectors = sel
        root.destroy()
    tk.Button(root, text="Run Screener", command=on_submit, font=("Arial", 11)).pack(pady=10)
    root.mainloop()
    return selected_sectors

def choose_sector_for_stocks_gui(sectors):
    """GUI to select a single sector to view its stocks."""
    root = tk.Tk()
    root.title("Select Sector for Stock Analysis")
    tk.Label(root, text="Choose a sector to see stock details:", font=("Arial", 12)).pack(pady=8)
    listbox = tk.Listbox(root, selectmode=tk.SINGLE, width=40, height=10)
    for sector in sectors:
        listbox.insert(tk.END, sector)
    listbox.pack(padx=10, pady=8)
    selected_sector = ""
    def on_submit():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a sector.")
            return
        nonlocal selected_sector
        selected_sector = listbox.get(sel[0])
        root.destroy()
    tk.Button(root, text="Show Stocks", command=on_submit, font=("Arial", 11)).pack(pady=10)
    root.mainloop()
    return selected_sector

# === Data Fetching and Calculation ===

def fetch_candle_data(symbol, days=30):
    token = symbol_to_token.get(symbol)
    if not token:
        print(f"Token not found for {symbol}")
        return None
    
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=days)
    params = {
        "exchange": EXCHANGE, "symboltoken": str(token), "interval": "ONE_DAY",
        "fromdate": start.strftime('%Y-%m-%d %H:%M'), "todate": end.strftime('%Y-%m-%d %H:%M')
    }
    
    try:
        response = smartApi.getCandleData(params)
        time.sleep(TIME_DELAY)
        if 'data' not in response or not response['data']:
            print(f"No candle data for {symbol}")
            return None
        df = pd.DataFrame(response['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df.dropna()
    except Exception as e:
        print(f"Error fetching candle data for {symbol}: {e}")
        return None

def calculate_stock_metrics(symbol):
    candle_df = fetch_candle_data(symbol, days=8)
    if candle_df is None or len(candle_df) < 2:
        print(f"[WARN] Skipping {symbol}: No valid candle data")
        return None

    initial_price = candle_df['close'].iloc[0]
    final_price = candle_df['close'].iloc[-1]
    
    price_change_abs = final_price - initial_price
    price_change_pct = (price_change_abs / initial_price) * 100 if initial_price != 0 else 0

    avg_volume = candle_df['volume'].mean()
    current_volume = candle_df['volume'].iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
    
    returns = candle_df['close'].pct_change().dropna()
    volatility = returns.std() * 100 if not returns.empty else 0
    
    return {
        "price_change": round(price_change_abs, 2),
        "price_change_pct": round(price_change_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "volatility": round(volatility, 2)
    }
    
# === Core Analysis Functions ===

def run_full_sector_analysis():
    """**Updated**: Runs sector screener and shows results in a new GUI table."""
    selected_sectors = choose_sectors_gui()
    if not selected_sectors:
        print("No sectors selected. Returning to main menu.")
        return

    sectors_to_analyze = {s: SECTOR_DICT[s] for s in selected_sectors}
    sector_metrics = analyze_sectors(sectors_to_analyze)
    if not sector_metrics:
        messagebox.showerror("No Data", "Could not analyze the selected sectors.")
        return
        
    table_data = []
    for sector, metrics in sector_metrics.items():
        classification = classify_sector(metrics)
        table_data.append([
            sector, classification, metrics['avg_price_change'],
            metrics['avg_volume_ratio'], metrics['avg_volatility'], metrics['num_stocks_analyzed']
        ])
    headers = ["Sector", "Classification", "PriceΔ", "VolRatio", "Volatility", "Stocks Analyzed"]
    
    # Print to console (for logging purposes)
    print("\n" + "="*80)
    print("SECTOR ANALYSIS SUMMARY")
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))
    print("="*80 + "\n")

    # --- NEW: Show results in a Tkinter GUI window ---
    sector_win = tk.Tk()
    sector_win.title("Sector Analysis Summary")
    tk.Label(sector_win, text="Sector Analysis Summary", font=("Arial", 14, "bold")).pack(pady=10)
    
    frame = tk.Frame(sector_win)
    frame.pack(padx=10, pady=10)

    # Create table headers
    for j, header in enumerate(headers):
        tk.Label(
            frame, text=header, font=("Arial", 10, "bold"), borderwidth=1, relief="solid", 
            width=25 if j == 0 else 15, padx=5, pady=2
        ).grid(row=0, column=j)

    # Populate table with data
    for i, row in enumerate(table_data, start=1):
        for j, val in enumerate(row):
            tk.Label(
                frame, text=str(val), font=("Arial", 10), borderwidth=1, relief="solid", 
                width=25 if j == 0 else 15, padx=5, pady=2
            ).grid(row=i, column=j)
            
    tk.Button(sector_win, text="Close", command=sector_win.destroy, font=("Arial", 11)).pack(pady=10)
    sector_win.mainloop()
    
    # Show charts after the GUI table is closed
    df = pd.DataFrame(table_data, columns=headers)
    plt.figure(figsize=(10, 7))
    sns.barplot(y="Sector", x="PriceΔ", data=df.sort_values("PriceΔ", ascending=False), palette="Blues_d")
    plt.title("Average Price Change by Sector")
    plt.tight_layout(); plt.show()

def analyze_sectors(sectors_dict):
    sector_results = {}
    for sector, stocks in sectors_dict.items():
        print(f"\nAnalyzing sector: {sector} ({len(stocks)} stocks)")
        metrics_list = [m for s in stocks if (m := calculate_stock_metrics(s))]
        if not metrics_list:
            print(f"No data for sector {sector}")
            continue
        df = pd.DataFrame(metrics_list)
        sector_results[sector] = {
            "avg_price_change": round(df['price_change'].mean(), 2),
            "avg_volume_ratio": round(df['volume_ratio'].mean(), 2),
            "avg_volatility": round(df['volatility'].mean(), 2),
            "num_stocks_analyzed": len(metrics_list)
        }
    return sector_results

def classify_sector(metrics):
    price = metrics["avg_price_change"]
    volume = metrics["avg_volume_ratio"]
    vol = metrics["avg_volatility"]
    if price > 0.5 and volume > 1 and vol < 2: return "Leading"
    elif price > 0.3 and volume > 0.6: return "Runner Up"
    elif price < -0.3 and volume < 0.6: return "Downfalling"
    else: return "Lacking Momentum"

def run_stock_level_analysis():
    chosen_sector = choose_sector_for_stocks_gui(SECTOR_DICT.keys())
    if not chosen_sector:
        print("No sector chosen. Returning to main menu.")
        return
    
    stock_list = SECTOR_DICT[chosen_sector]
    stock_table = []
    print(f"\nAnalyzing stocks in: {chosen_sector}")
    for sym in stock_list:
        metrics = calculate_stock_metrics(sym)
        if metrics:
            stock_table.append([
                sym,
                metrics["price_change"],
                f"{metrics['price_change_pct']}%",
                metrics["volume_ratio"],
                metrics["volatility"]
            ])
            
    if not stock_table:
        print(f"Could not retrieve data for any stocks in {chosen_sector}.")
        return

    headers = ["Stock", "PriceΔ", "PriceΔ (%)", "VolRatio", "Volatility"]
    print("\n" + "="*60)
    print(f"Stock-level details for {chosen_sector}")
    print(tabulate(stock_table, headers=headers, tablefmt="fancy_grid"))
    print("="*60 + "\n")
    
    stock_win = tk.Tk()
    stock_win.title(f"Stocks in {chosen_sector}")
    tk.Label(stock_win, text=f"Stocks in {chosen_sector}", font=("Arial", 12, "bold")).pack(pady=5)
    frame = tk.Frame(stock_win); frame.pack(padx=10, pady=10)
    for j, header in enumerate(headers):
        tk.Label(frame, text=header, font=("Arial", 10, "bold"), borderwidth=1, relief="solid", width=15, padx=5, pady=2).grid(row=0, column=j)
    for i, row in enumerate(stock_table, start=1):
        for j, val in enumerate(row):
            tk.Label(frame, text=str(val), font=("Arial", 10), borderwidth=1, relief="solid", width=15, padx=5, pady=2).grid(row=i, column=j)
    tk.Button(stock_win, text="Close", command=stock_win.destroy, font=("Arial", 11)).pack(pady=8)
    stock_win.mainloop()

# === Correlation Analysis Functions ===

def run_correlation_analysis():
    choose_sectors_for_correlation(SECTOR_DICT)

def classify_correlation(corr_value):
    """Classifies the overall correlation value into a readable string."""
    if corr_value > 0.7:
        return "Strong Positive Relation"
    elif corr_value > 0.4:
        return "Moderate Positive Relation"
    elif corr_value < -0.7:
        return "Strong Inverse Relation"
    elif corr_value < -0.4:
        return "Moderate Inverse Relation"
    else: # Between -0.4 and 0.4
        return "No Clear Relation"

def choose_sectors_for_correlation(sectors_to_analyze):
    while True:
        root = tk.Tk()
        root.title("Sector Correlation Analysis")
        tk.Label(root, text="Select two sectors to check correlation:", font=("Arial", 12)).pack(pady=8)
        listbox = tk.Listbox(root, selectmode=tk.MULTIPLE, width=50, height=12)
        for sector in sectors_to_analyze.keys():
            listbox.insert(tk.END, sector)
        listbox.pack(padx=10, pady=8)
        selected = []
        def on_submit():
            sel = [listbox.get(i) for i in listbox.curselection()]
            if len(sel) != 2:
                messagebox.showwarning("Invalid Selection", "Please select exactly TWO sectors.")
                return
            nonlocal selected
            selected = sel
            root.destroy()
        tk.Button(root, text="Run Correlation", command=on_submit, font=("Arial", 11)).pack(pady=10)
        root.mainloop()
        if not selected: return
        sec1, sec2 = selected
        def sector_price_series(stock_list):
            frames = [df[['timestamp', 'close']].set_index('timestamp').rename(columns={'close': sym})[sym]
                        for sym in stock_list if (df := fetch_candle_data(sym)) is not None]
            if not frames: return None
            merged = pd.concat(frames, axis=1, join="outer").ffill().bfill()
            return merged.mean(axis=1).rename('close')
            
        print(f"Fetching data for {sec1}...")
        s1_series = sector_price_series(sectors_to_analyze[sec1])
        print(f"Fetching data for {sec2}...")
        s2_series = sector_price_series(sectors_to_analyze[sec2])
        
        if s1_series is None or s2_series is None:
            messagebox.showerror("Data Error", "Could not fetch valid data for one or both selected sectors.")
        else:
            joined = pd.concat([s1_series, s2_series], axis=1, join="inner").dropna()
            joined.columns = [sec1, sec2]
            min_data_points = 15
            if len(joined) < min_data_points:
                messagebox.showerror("Not enough data", f"Found only {len(joined)} overlapping data points. Need at least {min_data_points}.")
            else:
                # --- START: NEW LOGIC ---
                
                # 1. Calculate the overall correlation for the entire period
                overall_corr = joined[sec1].corr(joined[sec2])
                
                # 2. Classify it using our new helper function
                relationship_text = classify_correlation(overall_corr)
                
                # 3. Calculate the rolling correlation signals
                corr_df = calculate_correlation_signals(joined, sec1, sec2)
                
                # 4. Pass ALL info (including new text) to the plot function
                plot_combined_data(joined, corr_df, overall_corr, relationship_text)
                
                # --- END: NEW LOGIC ---
                
        if not messagebox.askyesno("Run Again?", "Do you want to check another correlation?"): break

def calculate_correlation_signals(data: pd.DataFrame, asset1: str, asset2: str,
                                    window: int = 5, wide_window: int = 10, std_factor: float = 1.5) -> pd.DataFrame: # Changed from 10,20 to 5,10
    df = data.copy()
    df['rolling_corr'] = df[asset1].rolling(window=window, min_periods=window).corr(df[asset2])
    df['avg_corr'] = df['rolling_corr'].rolling(window=wide_window, min_periods=5).mean()
    df['std_corr'] = df['rolling_corr'].rolling(window=wide_window, min_periods=5).std()
    df['upper_threshold'] = df['avg_corr'] + (std_factor * df['std_corr'])
    df['lower_threshold'] = df['avg_corr'] - (std_factor * df['std_corr'])
    df['signal'] = 0
    df.loc[df['rolling_corr'] > df['upper_threshold'], 'signal'] = -1
    df.loc[df['rolling_corr'] < df['lower_threshold'], 'signal'] = 2
    return df[['rolling_corr', 'avg_corr', 'upper_threshold', 'lower_threshold', 'signal']]

def plot_combined_data(price_data: pd.DataFrame, correlation_data: pd.DataFrame,
                           overall_corr: float, relationship_text: str) -> None:
    """
    Plots the combined data with a new title showing the overall relationship.
    """
    fig, ax1 = plt.subplots(figsize=(14, 7))
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Price (Normalized)', color='black')
    normalized_price1 = (price_data.iloc[:, 0] / price_data.iloc[:, 0].iloc[0])
    normalized_price2 = (price_data.iloc[:, 1] / price_data.iloc[:, 1].iloc[0])
    ax1.plot(price_data.index, normalized_price1, label=price_data.columns[0], color='blue')
    ax1.plot(price_data.index, normalized_price2, label=price_data.columns[1], color='green')
    ax1.tick_params(axis='y', labelcolor='black')
    ax1.legend(loc='upper left'); ax1.grid(True)
    
    ax2 = ax1.twinx()
    ax2.set_ylabel('Correlation', color='purple')
    ax2.plot(correlation_data.index, correlation_data['rolling_corr'], label='Rolling Corr', color='purple')
    ax2.plot(correlation_data.index, correlation_data['avg_corr'], '--', label='Avg Corr', color='orange')
    ax2.fill_between(correlation_data.index, correlation_data['lower_threshold'], correlation_data['upper_threshold'], color='gray', alpha=0.2, label='Threshold')
    buy_signals = correlation_data[correlation_data['signal'] == 2]
    sell_signals = correlation_data[correlation_data['signal'] == -1]
    ax2.scatter(buy_signals.index, buy_signals['rolling_corr'], color='red', marker='^', s=100, label='Lower Signal', alpha=0.9)
    ax2.scatter(sell_signals.index, sell_signals['rolling_corr'], color='black', marker='v', s=100, label='Upper Signal', alpha=0.9)
    ax2.legend(loc='upper right')
    
    # --- NEW/UPDATED TITLE SECTION ---
    
    # Set title color based on relationship
    title_color = 'green'
    if 'Inverse' in relationship_text:
        title_color = 'red'
    elif 'No' in relationship_text:
        title_color = 'gray'
        
    # Set a main title
    fig.suptitle('Sector Prices (Normalized) & Rolling Correlation', fontsize=16)
    
    # Add the new relationship summary as a subtitle
    plt.title(
        f'Overall Relationship: {relationship_text} (Avg. Corr: {overall_corr:.2f})',
        color=title_color,
        fontsize=12
    )
    
    plt.show()
    
# === NEW: Sector Index Functions ===

def choose_index_method_gui():
    """GUI to select the index calculation method."""
    root = tk.Tk()
    root.title("Select Index Method")
    root.geometry("300x150")
    
    tk.Label(root, text="Choose index calculation method:", font=("Arial", 12)).pack(pady=10)
    
    method = ""
    def set_method(m):
        nonlocal method
        method = m
        root.destroy()

    tk.Button(root, text="Price-Based (Simple Avg)", command=lambda: set_method('price_based'), font=("Arial", 11), width=25).pack(pady=5)
    tk.Button(root, text="Volume-Weighted", command=lambda: set_method('weighted'), font=("Arial", 11), width=25).pack(pady=5)
    
    root.mainloop()
    return method

def plot_index(index_series: pd.Series):
    """Plots the calculated index series using matplotlib."""
    plt.figure(figsize=(14, 7))
    plt.plot(index_series.index, index_series.values, label=index_series.name, color='blue')
    plt.title(f"Sector Index: {index_series.name}")
    plt.ylabel("Index Value (Normalized to 100)")
    plt.xlabel("Date")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

def build_sector_index(sector_name, stock_list, method, days=60):
    """
    Fetches all stock data for a sector and builds a historical index.
    Fetches `days` of data to ensure ~30-40 trading days.
    """
    all_stock_data = {}
    print(f"Fetching data for {len(stock_list)} stocks in {sector_name}...")
    
    for sym in stock_list:
        df = fetch_candle_data(sym, days=days)
        if df is not None and not df.empty:
            # We only need close price and volume for our index
            all_stock_data[sym] = df[['timestamp', 'close', 'volume']].set_index('timestamp')
        
    if not all_stock_data:
        print("No valid stock data found for this sector.")
        return None

    # Combine all dataframes. Use 'outer' to keep all timestamps
    combined_df = pd.concat(all_stock_data.values(), keys=all_stock_data.keys(), axis=1, join='outer')
    
    # Fill missing data (e.g., holidays)
    combined_df = combined_df.ffill().bfill() 
    
    # Check if we still have data after alignment
    if combined_df.empty:
        print("Data alignment failed.")
        return None

    # Get all close prices and volume data
    close_prices = combined_df.loc[:, (slice(None), 'close')]
    close_prices.columns = close_prices.columns.get_level_values(0) # Simplify column names
    
    volumes = combined_df.loc[:, (slice(None), 'volume')]
    volumes.columns = volumes.columns.get_level_values(0)

    # --- Calculate the Index ---
    if method == 'price_based':
        # Simple average of all prices
        index_series = close_prices.mean(axis=1)
        index_name = f"{sector_name} (Price-Based)"
        
    elif method == 'weighted':
        # Use average 30-day volume as the weight
        avg_volumes = volumes.mean()
        total_volume = avg_volumes.sum()
        weights = avg_volumes / total_volume
        
        # Apply weights to the close prices
        weighted_prices = close_prices.multiply(weights, axis=1)
        
        # The index is the sum of all weighted prices
        index_series = weighted_prices.sum(axis=1)
        index_name = f"{sector_name} (Volume-Weighted)"
        
    else:
        return None

    # Normalize the index to a base of 100 for easy comparison
    index_series = (index_series / index_series.iloc[0]) * 100
    index_series.name = index_name
    
    return index_series.dropna()

def run_sector_index_analysis():
    """Handles the full workflow for creating and plotting a sector index."""
    
    # 1. Choose Sector
    chosen_sector = choose_sector_for_stocks_gui(SECTOR_DICT.keys())
    if not chosen_sector:
        print("No sector chosen. Returning to main menu.")
        return

    # 2. Choose Method
    method = choose_index_method_gui()
    if not method:
        print("No method chosen. Returning to main menu.")
        return

    print(f"Building {method} index for {chosen_sector}...")
    stock_list = SECTOR_DICT[chosen_sector]
    
    # 3. Build Index
    index_series = build_sector_index(chosen_sector, stock_list, method, days=60) 
    
    if index_series is None or index_series.empty:
        messagebox.showerror("Error", f"Could not build index for {chosen_sector}. Not enough data.")
        return
    
    # 4. Plot Index
    print("Index built successfully. Plotting...")
    plot_index(index_series)

def run_stock_vs_index_analysis():
    """Handles the full workflow for comparing a stock to its sector index."""
    
    # 1. Choose Sector
    chosen_sector = choose_sector_for_stocks_gui(SECTOR_DICT.keys())
    if not chosen_sector:
        print("No sector chosen. Returning to main menu.")
        return

    # 2. Choose Stock from that Sector
    chosen_stock = choose_stock_from_sector_gui(chosen_sector)
    if not chosen_stock:
        print("No stock chosen. Returning to main menu.")
        return

    # 3. Choose Index Method
    method = choose_index_method_gui()
    if not method:
        print("No method chosen. Returning to main menu.")
        return

    print(f"Building {method} index for {chosen_sector} to compare with {chosen_stock}...")
    stock_list = SECTOR_DICT[chosen_sector]
    
    # 4. Build Index
    index_series = build_sector_index(chosen_sector, stock_list, method, days=60)
    if index_series is None or index_series.empty:
        messagebox.showerror("Error", f"Could not build index for {chosen_sector}.")
        return

    # 5. Fetch Stock Data
    stock_df = fetch_candle_data(chosen_stock, days=60)
    if stock_df is None or stock_df.empty:
        messagebox.showerror("Error", f"Could not fetch data for stock: {chosen_stock}.")
        return
        
    stock_series = stock_df.set_index('timestamp')['close'].rename(chosen_stock)

    # 6. Align, Normalize, and Plot
    # We join 'inner' to only get dates where *both* the stock and index have data
    joined = pd.concat([stock_series, index_series], axis=1, join='inner').dropna()

    if joined.empty or len(joined) < 2:
        messagebox.showerror("Data Error", "Could not align stock and index data. Not enough overlapping days.")
        return
        
    # Normalize both to the same starting point (100)
    normalized_data = (joined / joined.iloc[0]) * 100
    
    print("Data aligned. Plotting comparison graph...")
    plot_stock_vs_index(normalized_data)

def choose_stock_from_sector_gui(sector_name):
    """GUI to select a single stock from the chosen sector."""
    stock_list = SECTOR_DICT.get(sector_name, [])
    if not stock_list:
        messagebox.showerror("Error", f"No stocks found for sector: {sector_name}")
        return ""

    root = tk.Tk()
    root.title(f"Select Stock from {sector_name}")
    tk.Label(root, text="Choose one stock to compare:", font=("Arial", 12)).pack(pady=8)
    
    listbox = tk.Listbox(root, selectmode=tk.SINGLE, width=50, height=15)
    for stock in stock_list:
        listbox.insert(tk.END, stock)
    listbox.pack(padx=10, pady=8)
    
    selected_stock = ""
    def on_submit():
        sel = listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a stock.")
            return
        nonlocal selected_stock
        selected_stock = listbox.get(sel[0])
        root.destroy()
        
    tk.Button(root, text="Compare vs. Index", command=on_submit, font=("Arial", 11)).pack(pady=10)
    root.mainloop()
    return selected_stock

def plot_stock_vs_index(normalized_data: pd.DataFrame):
    """
    Plots the normalized stock price vs. the normalized sector index.
    """
    stock_name = normalized_data.columns[0]
    index_name = normalized_data.columns[1]
    
    plt.figure(figsize=(14, 7))
    plt.plot(normalized_data.index, normalized_data.iloc[:, 0], label=stock_name, color='blue', linewidth=2)
    plt.plot(normalized_data.index, normalized_data.iloc[:, 1], label=index_name, color='orange', linestyle='--', linewidth=2)
    
    plt.title(f"{stock_name} vs. {index_name} (Normalized to 100)")
    plt.ylabel("Normalized Value")
    plt.xlabel("Date")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

# === Main Execution Block ===
def main():
    if not initialize_api():
        return
    
    while True:
        user_choice = initial_choice_gui()
        
        if user_choice == 'sector':
            run_full_sector_analysis()
        elif user_choice == 'stock':
            run_stock_level_analysis()
        elif user_choice == 'correlation':
            run_correlation_analysis()
        elif user_choice == 'index':
            run_sector_index_analysis()
            
        # --- NEW ELIF BLOCK ---
        elif user_choice == 'stock_vs_index':
            run_stock_vs_index_analysis()
            
        elif user_choice == 'exit':
            print("Exiting application.")
            break
        else: 
            print("No option selected. Exiting.")
            break
            
        if not messagebox.askyesno("Main Menu", "Do you want to return to the main menu?"):
            break

if __name__ == "__main__":
    main()