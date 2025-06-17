# FDXWDATA
Project of API from Angle one SmartAPI to access data and us for real time moments and Breakouts using watchlist ( Only stocks that have F&amp;O) , to perform on multiple stocks and sector analysis.
# 📈 Sector Performance Analyzer using Angel One SmartAPI

This project is a **Sector Performance Analyzer** that evaluates and visualizes stock sector health based on price action, volume activity, and volatility. It fetches historical candle data from the Angel One SmartAPI and optionally uses WebSocket live data for Open Interest (OI) analysis. The project also generates a JdK-style **Relative Rotation Graph (RRG)** to visualize sector strength and momentum.

## 🔍 Features

- Analyzes multiple sectors across Indian stock market (NSE)
- Calculates sector metrics:
  - Average price change
  - Volume ratio (current volume vs average)
  - Volatility
- Classifies sectors as:
  - **Leading**
  - **Improving**
  - **Weakening**
  - **Lacking**
- Optional JdK-style **RRG plot** for visual comparison
- Modular sector definitions (via `watchlist.py`)
- Ready to plug in live Open Interest (OI) tracking via WebSocket


## 🧪 Requirements

- Python 3.7+
- Angel One SmartAPI account
- TOTP key for 2FA authentication

### Python Dependencies

Install all required packages:

```bash
pip install -r requirements.txt
```
#🔐 Setup
Replace the following placeholders in main.py:

python

API_KEY = "your_api_key"
CLIENT_CODE = "your_client_code"
PASSWORD = "your_password"
TOTP_SECRET = "your_totp_secret"

#Ensure watchlist.py contains properly structured sector-wise stock symbols like:
#Take a look in watchlist.py to know how to write stock name.
python

banking_and_finance = {
    "Private Banks": ["AXISBANK-EQ", "HDFCBANK-EQ"],
    "NBFC": ["BAJFINANCE-EQ"]
}
#📊 Sample Output

╒════════════════════════════════╤═══════════════╤══════════╤════════════╤══════════════╤════════════════════╕
│ Sector                         │ Classification│ PriceΔ   │ VolRatio   │ Volatility   │ Stocks Analyzed     │
╞════════════════════════════════╪═══════════════╪══════════╪════════════╪══════════════╪════════════════════╡
│ IT and Services                │ Leading       │ 1.24     │ 1.12       │ 1.84         │ 14                 │
│ Pharmaceuticals                │ Weakening     │ -0.62    │ 0.42       │ 2.45         │ 12                 │
╘════════════════════════════════╧═══════════════╧══════════╧════════════╧══════════════╧══════════════

#📡 Live OI Tracking (Optional)
To enable live Open Interest (OI) tracking:

Uncomment the WebSocket section in main.py

Add relevant tokens from sectors of interest

#📈 Plot Example

🛠️ Future Improvements
Add support for intraday analysis (5-min or 15-min candles)

Integrate alerting or Telegram notifications

Optimize plotting for large sector sets

Include Open Interest impact in classification

There are 3 files WTO.py sector2.py , watchlist.py 
WTO.py : can be use as base code to perfon any opreation watchlist based data extraction.

🤝 Contributing
Feel free to fork and submit pull requests if you'd like to enhance the functionality or UI.

