import time
import requests
import pyotp
import pandas as pd
import matplotlib.pyplot as plt
import urllib3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tabulate import tabulate
from SmartApi import SmartConnect
from colorama import Fore, Style, init
from watchlist import oil_and_gas

# The data can be fetched from: yfinance, investing.com, or any other source. too i just used SmartApi it is more flexible.
# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

init(autoreset=True)

# ============ CONFIGURATION ============
API_KEY = ""
CLIENT_CODE = ""
PASSWORD = ""
TOTP_SECRET = ""
EXCHANGE = "NSE"
MAX_WORKERS = 1  # Single worker to ensure proper rate limiting

# Pivot Configuration
TIMEFRAME = "Weekly"  # Options: Weekly, Monthly
PROXIMITY_THRESHOLD = 2.0  # % threshold for highlighting nearby levels
RATE_LIMIT_DELAY = 1.2  # Seconds between API calls

watchlist = oil_and_gas

# ============ 1. SETUP ============
def login():
    print(f"{Fore.YELLOW}Connecting to Angel One...{Style.RESET_ALL}")
    try:
        smartApi = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smartApi.generateSession(CLIENT_CODE, PASSWORD, totp)
        if not data['status']: raise Exception(data['message'])
        print(f"{Fore.GREEN}✓ Connected Successfully.{Style.RESET_ALL}")
        return smartApi
    except Exception as e:
        print(f"{Fore.RED}Login Error: {e}{Style.RESET_ALL}")
        return None

def get_symbol_map():
    print("Fetching Instrument Master...")
    
    # Try multiple URLs in case one fails
    urls = [
        "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
        "http://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    ]
    
    for url in urls:
        try:
            print(f"Trying: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, verify=False, timeout=30, headers=headers)
            
            if response.status_code != 200:
                print(f"{Fore.YELLOW}Status code: {response.status_code}{Style.RESET_ALL}")
                continue
                
            data = response.json()
            
            if not data:
                print(f"{Fore.YELLOW}Empty response from {url}{Style.RESET_ALL}")
                continue
            
            symbol_map = {item['symbol']: item['token'] for item in data if item.get('exch_seg') == EXCHANGE}
            
            if symbol_map:
                print(f"{Fore.GREEN}✓ Loaded {len(symbol_map)} instruments from NSE{Style.RESET_ALL}")
                return symbol_map
            
        except requests.exceptions.JSONDecodeError as e:
            print(f"{Fore.YELLOW}JSON decode error: {e}{Style.RESET_ALL}")
            continue
        except Exception as e:
            print(f"{Fore.YELLOW}Error with {url}: {e}{Style.RESET_ALL}")
            continue
    
    # If all methods fail, provide manual token input option
    print(f"\n{Fore.RED}Failed to fetch instrument master automatically.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}You can either:{Style.RESET_ALL}")
    print(f"1. Download manually from: https://smartapi.angelbroking.com/instrument-master")
    print(f"2. Continue with manual token entry (for testing)")
    
    choice = input(f"\n{Fore.CYAN}Press Enter to continue with manual mode, or Ctrl+C to exit: {Style.RESET_ALL}")
    return {}

# ============ 2. FIBONACCI PIVOT CALCULATIONS ============

def calculate_fibonacci_pivots(high, low, close):
    """
    Pure Fibonacci Pivot Levels
    Based on Fibonacci ratios: 0, 0.382, 0.5, 0.618, 1.0
    """
    # Pivot Point (PP)
    P = (high + low + close) / 3
    
    # Range
    range_hl = high - low
    
    # Fibonacci Resistance Levels
    R1 = P + 0.382 * range_hl  # 38.2% Fibonacci
    R2 = P + 0.500 * range_hl  # 50% level
    R3 = P + 0.618 * range_hl  # 61.8% Fibonacci (Golden Ratio)
    R4 = P + 1.000 * range_hl  # 100% extension
    
    # Fibonacci Support Levels
    S1 = P - 0.382 * range_hl  # 38.2% Fibonacci
    S2 = P - 0.500 * range_hl  # 50% level
    S3 = P - 0.618 * range_hl  # 61.8% Fibonacci (Golden Ratio)
    S4 = P - 1.000 * range_hl  # 100% extension
    
    return {
        "P": P,
        "R1": R1, "R2": R2, "R3": R3, "R4": R4,
        "S1": S1, "S2": S2, "S3": S3, "S4": S4
    }

# ============ 3. PROXIMITY DETECTION ============

def is_near_level(ltp, level_value, threshold=PROXIMITY_THRESHOLD):
    """Check if LTP is within threshold % of a level"""
    if level_value is None:
        return False
    diff_pct = abs((ltp - level_value) / level_value * 100)
    return diff_pct <= threshold

def colorize_value(value, is_near=False):
    """Colorize values based on proximity"""
    if value is None:
        return "-"
    if is_near:
        return f"{Fore.YELLOW}{value:.2f}*{Style.RESET_ALL}"
    return f"{value:.2f}"

def find_nearest_levels(ltp, pivots):
    """Find nearest support and resistance"""
    resistances = {k: v for k, v in pivots.items() if v and v > ltp and k.startswith('R')}
    supports = {k: v for k, v in pivots.items() if v and v < ltp and k.startswith('S')}
    
    nearest_r = min(resistances.items(), key=lambda x: x[1]) if resistances else (None, None)
    nearest_s = max(supports.items(), key=lambda x: x[1]) if supports else (None, None)
    
    return nearest_r, nearest_s

# ============ 4. DATA FETCHING & RESAMPLING ============

def get_reference_period_data(df, timeframe="Weekly"):
    """
    Get the last completed period's OHLC data
    
    Parameters:
    -----------
    df : DataFrame with OHLC data
    timeframe : 'Weekly' or 'Monthly'
    
    Returns:
    --------
    high, low, close, open_price of the last completed period
    """
    
    df['datetime'] = pd.to_datetime(df['ts'])
    df.set_index('datetime', inplace=True)
    
    if timeframe == "Weekly":
        # Resample to weekly (W-FRI = week ending Friday)
        resampled = df.resample('W-FRI').agg({
            'o': 'first',
            'h': 'max',
            'l': 'min',
            'c': 'last'
        }).dropna()
        
        # Get last COMPLETED week (not current week)
        if len(resampled) >= 2:
            ref_period = resampled.iloc[-2]  # Last completed week
        else:
            ref_period = resampled.iloc[-1]
            
    elif timeframe == "Monthly":
        # Resample to monthly
        resampled = df.resample('M').agg({
            'o': 'first',
            'h': 'max',
            'l': 'min',
            'c': 'last'
        }).dropna()
        
        # Get last COMPLETED month
        if len(resampled) >= 2:
            ref_period = resampled.iloc[-2]  # Last completed month
        else:
            ref_period = resampled.iloc[-1]
    
    return ref_period['h'], ref_period['l'], ref_period['c'], ref_period['o'], resampled.index[-1 if len(resampled) == 1 else -2]

# ============ 5. STOCK ANALYSIS ============

def analyze_stock(symbol, symbol_map, smartApi, timeframe="Weekly"):
    token = symbol_map.get(symbol)
    if not token:
        # If token not found, try to get it from the API search
        try:
            search_result = smartApi.searchScrip(EXCHANGE, symbol)
            if search_result and 'data' in search_result and search_result['data']:
                token = search_result['data'][0]['symboltoken']
                print(f"{Fore.YELLOW}Found token for {symbol}: {token}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}Token not found for {symbol}{Style.RESET_ALL}")
                return None
        except Exception as e:
            print(f"{Fore.RED}Error searching for {symbol}: {e}{Style.RESET_ALL}")
            return None

    # Rate limiting: 1.2 seconds between requests
    time.sleep(RATE_LIMIT_DELAY)
    
    # Fetch enough data for weekly/monthly calculation
    end_dt = datetime.now()
    
    if timeframe == "Weekly":
        start_dt = end_dt - timedelta(days=30)  # Get ~4 weeks of data
    else:  # Monthly
        start_dt = end_dt - timedelta(days=90)  # Get ~3 months of data
    
    params = {
        "exchange": EXCHANGE, "symboltoken": token, "interval": "ONE_DAY",
        "fromdate": start_dt.strftime('%Y-%m-%d %H:%M'),
        "todate": end_dt.strftime('%Y-%m-%d %H:%M')
    }
    
    resp = None
    for _ in range(3):
        try:
            resp = smartApi.getCandleData(params)
            if resp and 'data' in resp: break
            time.sleep(1)
        except: time.sleep(1)
            
    if not resp or not resp['data']: return None

    try:
        df = pd.DataFrame(resp['data'], columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        cols = ['o', 'h', 'l', 'c']
        df[cols] = df[cols].apply(pd.to_numeric)
        
        # Get current LTP (last close)
        ltp = df['c'].iloc[-1]
        
        # Get reference period OHLC
        high, low, close, open_price, ref_date = get_reference_period_data(df.copy(), timeframe)

        # Calculate Fibonacci Pivots
        pivots = calculate_fibonacci_pivots(high, low, close)
        
        # Find nearest levels
        nearest_r, nearest_s = find_nearest_levels(ltp, pivots)
        
        # Proximity flags
        near_p = is_near_level(ltp, pivots['P'])
        near_r1 = is_near_level(ltp, pivots['R1'])
        near_r2 = is_near_level(ltp, pivots['R2'])
        near_r3 = is_near_level(ltp, pivots['R3'])
        near_r4 = is_near_level(ltp, pivots['R4'])
        near_s1 = is_near_level(ltp, pivots['S1'])
        near_s2 = is_near_level(ltp, pivots['S2'])
        near_s3 = is_near_level(ltp, pivots['S3'])
        near_s4 = is_near_level(ltp, pivots['S4'])
        
        # Calculate distance to pivot (%)
        pivot_dist = ((ltp - pivots['P']) / pivots['P'] * 100)
        
        # Format nearest levels
        nearest_r_str = f"{nearest_r[0]} ({nearest_r[1]:.2f})" if nearest_r[0] else "-"
        nearest_s_str = f"{nearest_s[0]} ({nearest_s[1]:.2f})" if nearest_s[0] else "-"
        
        return [
            symbol,
            ref_date.strftime('%Y-%m-%d') if hasattr(ref_date, 'strftime') else str(ref_date),
            f"{Fore.CYAN}{ltp:.2f}{Style.RESET_ALL}",
            colorize_value(pivots['P'], near_p),
            f"{pivot_dist:+.1f}%",
            colorize_value(pivots['R1'], near_r1),
            colorize_value(pivots['R2'], near_r2),
            colorize_value(pivots['R3'], near_r3),
            colorize_value(pivots['R4'], near_r4),
            colorize_value(pivots['S1'], near_s1),
            colorize_value(pivots['S2'], near_s2),
            colorize_value(pivots['S3'], near_s3),
            colorize_value(pivots['S4'], near_s4),
            f"{Fore.GREEN}{nearest_r_str}{Style.RESET_ALL}",
            f"{Fore.RED}{nearest_s_str}{Style.RESET_ALL}"
        ]

    except Exception as e:
        print(f"{Fore.RED}Error analyzing {symbol}: {e}{Style.RESET_ALL}")
        return [symbol, "Error", str(e), "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"]

# ============ 6. DETAILED CHART FOR INDIVIDUAL STOCK ============

def plot_stock_with_pivots(symbol, symbol_map, smartApi, timeframe="Weekly", lookback_days=60):
    """Generate detailed chart for a specific stock"""
    token = symbol_map.get(symbol)
    if not token:
        print(f"{Fore.RED}Symbol {symbol} not found.{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.YELLOW}Fetching detailed data for {symbol}...{Style.RESET_ALL}")
    
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=lookback_days + 30)
    params = {
        "exchange": EXCHANGE, "symboltoken": token, "interval": "ONE_DAY",
        "fromdate": start_dt.strftime('%Y-%m-%d %H:%M'),
        "todate": end_dt.strftime('%Y-%m-%d %H:%M')
    }
    
    try:
        resp = smartApi.getCandleData(params)
        if not resp or not resp['data']:
            print(f"{Fore.RED}No data available for {symbol}.{Style.RESET_ALL}")
            return
        
        df = pd.DataFrame(resp['data'], columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        df[['o', 'h', 'l', 'c']] = df[['o', 'h', 'l', 'c']].apply(pd.to_numeric)
        df['ts'] = pd.to_datetime(df['ts'])
        
        # Calculate pivots from reference period
        high, low, close, open_price, ref_date = get_reference_period_data(df.copy(), timeframe)
        pivots = calculate_fibonacci_pivots(high, low, close)
        
        # Plot only recent data
        plot_df = df.tail(lookback_days)
        
        # Plot
        fig, ax = plt.subplots(figsize=(15, 9))
        
        # Price action
        ax.plot(plot_df['ts'], plot_df['c'], 'b-', linewidth=2, label='Close Price', alpha=0.8, zorder=5)
        ax.fill_between(plot_df['ts'], plot_df['l'], plot_df['h'], alpha=0.2, color='gray', label='High-Low Range', zorder=1)
        
        # Fibonacci Pivot levels with proper colors
        colors = {
            'P': '#FB8C00',   # Orange - Pivot
            'R1': '#66BB6A',  # Light Green - 38.2%
            'R2': '#4CAF50',  # Green - 50%
            'R3': '#2E7D32',  # Dark Green - 61.8%
            'R4': '#1B5E20',  # Darker Green - 100%
            'S1': '#EF5350',  # Light Red - 38.2%
            'S2': '#F44336',  # Red - 50%
            'S3': '#C62828',  # Dark Red - 61.8%
            'S4': '#B71C1C',  # Darker Red - 100%
        }
        
        labels = {
            'P': 'Pivot',
            'R1': 'R1 (38.2%)',
            'R2': 'R2 (50%)',
            'R3': 'R3 (61.8%)',
            'R4': 'R4 (100%)',
            'S1': 'S1 (38.2%)',
            'S2': 'S2 (50%)',
            'S3': 'S3 (61.8%)',
            'S4': 'S4 (100%)',
        }
        
        for level, value in sorted(pivots.items(), key=lambda x: x[1] if x[1] else 0, reverse=True):
            if value is not None:
                ax.axhline(y=value, color=colors.get(level, '#FB8C00'), 
                          linestyle='--', linewidth=2, alpha=0.75, 
                          label=f'{labels[level]}: {value:.2f}', zorder=3)
        
        # Add current price marker
        current_price = plot_df['c'].iloc[-1]
        ax.axhline(y=current_price, color='#2196F3', linestyle='-', linewidth=2.5, 
                  alpha=0.9, label=f'Current: {current_price:.2f}', zorder=4)
        
        ax.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax.set_ylabel('Price (₹)', fontsize=12, fontweight='bold')
        ax.set_title(f'{symbol} - Fibonacci Pivots ({timeframe} OHLC)\nReference Period: {ref_date.strftime("%Y-%m-%d") if hasattr(ref_date, "strftime") else ref_date}', 
                    fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=9, ncol=2, framealpha=0.9)
        ax.grid(True, alpha=0.3, zorder=0)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
        
        print(f"{Fore.GREEN}✓ Chart generated successfully!{Style.RESET_ALL}")
        
    except Exception as e:
        print(f"{Fore.RED}Error generating chart: {e}{Style.RESET_ALL}")

# ============ 7. MAIN MENU ============

def display_menu():
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}     FIBONACCI PIVOT SCANNER v2.0{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    print(f"{Fore.GREEN}1.{Style.RESET_ALL} Scan Watchlist (Table View)")
    print(f"{Fore.GREEN}2.{Style.RESET_ALL} Generate Chart for Specific Stock")
    print(f"{Fore.GREEN}3.{Style.RESET_ALL} Change Timeframe (Current: {Fore.YELLOW}{TIMEFRAME}{Style.RESET_ALL})")
    print(f"{Fore.GREEN}4.{Style.RESET_ALL} Exit")
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Fibonacci Levels: 38.2%, 50%, 61.8%, 100%{Style.RESET_ALL}")

def change_timeframe():
    global TIMEFRAME
    timeframe_options = ["Weekly", "Monthly"]
    
    print(f"\n{Fore.YELLOW}Available Timeframes:{Style.RESET_ALL}")
    for i, tf in enumerate(timeframe_options, 1):
        print(f"{i}. {tf}")
    
    try:
        choice = int(input(f"\n{Fore.CYAN}Select timeframe (1-2): {Style.RESET_ALL}"))
        if 1 <= choice <= 2:
            TIMEFRAME = timeframe_options[choice - 1]
            print(f"{Fore.GREEN}✓ Timeframe changed to: {TIMEFRAME}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Invalid choice!{Style.RESET_ALL}")
    except:
        print(f"{Fore.RED}Invalid input!{Style.RESET_ALL}")

def scan_watchlist(api, token_map):
    print(f"\n{Fore.YELLOW}Analyzing {len(watchlist)} stocks with {TIMEFRAME} Fibonacci pivots...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}(Yellow * = Price within {PROXIMITY_THRESHOLD}% of level){Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Rate limiting: {RATE_LIMIT_DELAY}s between stocks (Total ~{len(watchlist) * RATE_LIMIT_DELAY:.0f}s){Style.RESET_ALL}\n")
    
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_stock, sym, token_map, api, TIMEFRAME): sym for sym in watchlist}
        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            if res: 
                results.append(res)
                print(f"{Fore.GREEN}✓{Style.RESET_ALL} Processed {i}/{len(watchlist)}: {res[0]}", end='\r')
    
    print("\n")  # Clear the progress line
    
    headers = ["Symbol", "Ref Period", "LTP", "Pivot", "Dist%", 
               "R1\n(38.2%)", "R2\n(50%)", "R3\n(61.8%)", "R4\n(100%)",
               "S1\n(38.2%)", "S2\n(50%)", "S3\n(61.8%)", "S4\n(100%)",
               "Nearest R", "Nearest S"]
    
    print("\n" + tabulate(results, headers=headers, tablefmt="grid"))
    print(f"\n{Fore.GREEN}✓ Scan complete! {len(results)} stocks analyzed.{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}Legend:{Style.RESET_ALL}")
    print(f"  • Dist% = Distance from Pivot Point")
    print(f"  • Yellow * = Price within {PROXIMITY_THRESHOLD}% of level")
    print(f"  • Fib Ratios: 38.2%, 50%, 61.8%, 100%")

# ============ 8. MAIN EXECUTION ============

if __name__ == "__main__":
    api = login()
    if not api:
        exit(1)
    
    token_map = get_symbol_map()
    
    while True:
        display_menu()
        try:
            choice = input(f"\n{Fore.CYAN}Enter your choice: {Style.RESET_ALL}").strip()
            
            if choice == "1":
                scan_watchlist(api, token_map)
            
            elif choice == "2":
                symbol = input(f"\n{Fore.CYAN}Enter stock symbol (e.g., HDFCBANK): {Style.RESET_ALL}").strip().upper()
                if symbol:
                    plot_stock_with_pivots(symbol, token_map, api, TIMEFRAME, lookback_days=60)
            
            elif choice == "3":
                change_timeframe()
            
            elif choice == "4":
                print(f"\n{Fore.GREEN}Thanks for using Fibonacci Pivot Scanner! 👋{Style.RESET_ALL}\n")
                break
            
            else:
                print(f"{Fore.RED}Invalid choice! Please select 1-4.{Style.RESET_ALL}")
        
        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}Interrupted by user. Exiting...{Style.RESET_ALL}\n")
            break
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")