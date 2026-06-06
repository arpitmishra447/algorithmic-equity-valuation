import pandas as pd
import yfinance as yf
import sqlite3
import time
import requests
import numpy as np
import datetime
import re
import warnings
from io import StringIO
from bs4 import BeautifulSoup

# Suppress warnings for clean console output
warnings.filterwarnings('ignore')

# ==========================================
# MODULE 1: DYNAMIC MACROECONOMIC ENGINE
# ==========================================
def get_dynamic_macro_metrics():
    print("Initializing Dynamic Macroeconomic Engine...")
    rf_rate = None
    
    # 1. Targeted RBI Scraper (10-Year Benchmark GS 2035)
    print("  [*] Attempting to fetch 10-Year Yield (GS 2035) from RBI...")
    try:
        url = "https://www.rbi.org.in/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        strings = list(soup.stripped_strings)
        for i, text in enumerate(strings):
            if "GS 2035" in text:
                potential_val = strings[i+1]
                match = re.search(r'([0-9]+\.[0-9]+)', potential_val)
                if match:
                    rf_rate = float(match.group(1)) / 100
                    print(f"  [+] SUCCESS: Live 10-Yr Risk-Free Rate ({rf_rate*100:.4f}%) fetched via RBI.")
                    break
    except Exception as e:
        print(f"  [-] RBI Scraper failed: {e}")

    if rf_rate is None:
        print("  [!] Could not locate GS 2035. Defaulting to 7.05% baseline.")
        rf_rate = 0.0705

    # 2. Market Return (Nifty 50 10-Yr CAGR)
    try:
        nifty = yf.Ticker("^NSEI")
        nifty_hist = nifty.history(period="10y")
        start, end = nifty_hist['Close'].iloc[0], nifty_hist['Close'].iloc[-1]
        market_return = (end / start) ** (1 / 10) - 1
        print(f"  [+] Live Nifty 50 10-Yr CAGR ({market_return*100:.2f}%) fetched.")
    except:
        market_return = 0.12 # Standard baseline
        
    erp = market_return - rf_rate
    terminal_growth = min(rf_rate * 0.70, 0.045) # Conservative Cap
    
    return {'Risk_Free_Rate': rf_rate, 'Equity_Risk_Premium': erp, 'Terminal_Growth_Rate': terminal_growth}

# ==========================================
# MODULE 2: DATABASE & INGESTION
# ==========================================
def setup_database():
    conn = sqlite3.connect('nifty_finance.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS fundamental_data (
        ticker TEXT PRIMARY KEY, company_name TEXT, sector TEXT, net_income REAL,
        total_revenue REAL, total_assets REAL, total_equity REAL, operating_cash_flow REAL,
        capital_expenditure REAL, shares_outstanding REAL, current_price REAL,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn

def get_nifty50_tickers():
    print("Scraping live Nifty 50 constituents...")
    url = 'https://en.wikipedia.org/wiki/NIFTY_50'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    tables = pd.read_html(StringIO(response.text))
    for table in tables:
        if 'Symbol' in table.columns:
            return [symbol + '.NS' for symbol in table['Symbol'].tolist()]

def extract_and_store(conn, tickers):
    cursor = conn.cursor()
    print("Initiating API Extraction Pipeline...")
    for ticker in tickers:
        print(f"  -> Processing {ticker}...")
        try:
            stock = yf.Ticker(ticker)
            info, inc, bs, cf = stock.info, stock.financials, stock.balance_sheet, stock.cashflow
            def get_val(df, key): return df.loc[key].iloc[0] if key in df.index else 0
            
            equity = get_val(bs, 'Stockholders Equity') or get_val(bs, 'Total Equity Gross Minority Interest')
            
            cursor.execute('''INSERT OR REPLACE INTO fundamental_data 
            (ticker, company_name, sector, net_income, total_revenue, total_assets, total_equity, operating_cash_flow, capital_expenditure, shares_outstanding, current_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                ticker, info.get('shortName', ticker), info.get('sector', 'Unknown'),
                get_val(inc, 'Net Income'), get_val(inc, 'Total Revenue'), 
                get_val(bs, 'Total Assets'), equity,
                get_val(cf, 'Operating Cash Flow'), get_val(cf, 'Capital Expenditure'),
                info.get('sharesOutstanding', 1), info.get('currentPrice', 0.0)
            ))
            conn.commit()
            time.sleep(0.5)
        except Exception: pass

# ==========================================
# MODULE 3: INSTITUTIONAL VALUATION ENGINE
# ==========================================
def execute_pipeline(conn, macro):
    print("Executing DCF Engine with Cash Flow Smoothing & Growth Decay...")
    df = pd.read_sql_query("SELECT * FROM fundamental_data", conn)
    df.replace(0, np.nan, inplace=True)
    
    # 1. Engineering DuPont ROE
    df['net_profit_margin'] = df['net_income'] / df['total_revenue']
    df['asset_turnover'] = df['total_revenue'] / df['total_assets']
    df['equity_multiplier'] = df['total_assets'] / df['total_equity']
    df['programmatic_roe'] = df['net_profit_margin'] * df['asset_turnover'] * df['equity_multiplier']
    
    # 2. Institutional Cash Flow Smoothing
    # Assume a maintenance FCFF of 5% of Revenue if current FCFF is negative/distorted
    df['raw_fcff'] = df['operating_cash_flow'] + df['capital_expenditure']
    df['normalized_fcff'] = np.where(df['raw_fcff'] <= 0, df['total_revenue'] * 0.05, df['raw_fcff'])
    
    df.fillna(0, inplace=True)
    
    intrinsic_values, signals, dynamic_waccs, dynamic_sgrs = [], [], [], []
    
    for row in df.itertuples():
        try:
            stock_info = yf.Ticker(row.ticker).info
            beta = stock_info.get('beta', 1.1) or 1.1
            payout = stock_info.get('payoutRatio', 0.0) or 0.2
            
            # --- SAFEGUARD: WACC Floor (Institutional Practice for Emerging Markets) ---
            wacc = macro['Risk_Free_Rate'] + (beta * (macro['Equity_Risk_Premium'] + 0.02)) # +2% Country Risk
            wacc = max(wacc, 0.11) # 11% Floor
            
            # --- SAFEGUARD: Growth Cap ---
            initial_g = min(max(row.programmatic_roe * (1 - payout), 0.02), 0.10) # 10% Cap
            
            dynamic_waccs.append(wacc); dynamic_sgrs.append(initial_g)
            
            # --- SAFEGUARD: Mean-Reverting Growth (Fade growth toward terminal rate) ---
            p_fcff = []
            temp_fcff = row.normalized_fcff
            temp_g = initial_g
            for i in range(1, 6):
                temp_fcff *= (1 + temp_g)
                p_fcff.append(temp_fcff)
                temp_g = (temp_g * 0.7) + (macro['Terminal_Growth_Rate'] * 0.3)
            
            pv_explicit = sum([cf / (1 + wacc)**i for i, cf in enumerate(p_fcff, 1)])
            
            # Terminal Value
            term_g = min(macro['Terminal_Growth_Rate'], wacc - 0.05)
            terminal_val = (p_fcff[-1] * (1 + term_g)) / (wacc - term_g)
            intrinsic = (pv_explicit + (terminal_val / (1 + wacc)**5)) / row.shares_outstanding
            
            intrinsic_values.append(np.round(intrinsic, 2))
            # Margin of Safety Signal (Only BUY if 20% upside exists)
            signals.append("UNDERVALUED (BUY)" if intrinsic > (row.current_price * 1.2) else "OVERVALUED")
            
        except Exception:
            intrinsic_values.append(0); signals.append("ERROR"); dynamic_waccs.append(0); dynamic_sgrs.append(0)
            
    df['dynamic_wacc'], df['dynamic_sgr'] = dynamic_waccs, dynamic_sgrs
    df['intrinsic_value'], df['signal'] = intrinsic_values, signals
    df.to_sql('final_valuations', conn, if_exists='replace', index=False)

if __name__ == "__main__":
    db_conn = setup_database()
    macros = get_dynamic_macro_metrics()
    tickers = get_nifty50_tickers()
    extract_and_store(db_conn, tickers)
    execute_pipeline(db_conn, macros)
    db_conn.close()
    print("\n--- Pipeline Complete. Run 'streamlit run app.py' ---")