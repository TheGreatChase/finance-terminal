import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

# --- 1. INSTITUTIONAL LIGHT THEME (Marquee Slate) ---
st.set_page_config(page_title="Finance Terminal", layout="wide")

st.markdown("""
<style>
    /* High-contrast Slate background with White content areas */
    .main { background-color: #f0f2f6; color: #1a1c23; font-family: 'Inter', sans-serif; }
    [data-testid="stMetricValue"] { color: #0052cc !important; font-size: 30px !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #5e6c84 !important; text-transform: uppercase; font-size: 13px !important; font-weight: 600; }
    .stDataFrame { border: 1px solid #dfe1e6; background-color: #ffffff; }
    /* Navigation styling */
    button[aria-selected="true"] { border-bottom: 3px solid #0052cc !important; color: #0052cc !important; font-weight: 700 !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: #ffffff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

# --- 2. SEC DATA ENGINE ---
class SECEngine:
    HEADERS = {'User-Agent': "TerminalApp researcher@example.com"}

    @staticmethod
    @st.cache_data
    def get_cik_map():
        url = "https://www.sec.gov/files/company_tickers.json"
        r = requests.get(url, headers=SECEngine.HEADERS)
        return {v['ticker']: str(v['cik_str']).zfill(10) for k, v in r.json().items()}

    @staticmethod
    @st.cache_data(ttl=3600)
    def fetch_sec_facts(cik):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        r = requests.get(url, headers=SECEngine.HEADERS)
        return r.json() if r.status_code == 200 else None

    @staticmethod
    def get_clean_metric(data, tag):
        """Standardizes 15-year history and eliminates duplicate filings per year."""
        try:
            facts = data['facts']['us-gaap'][tag]['units']['USD']
            df = pd.DataFrame(facts)
            df['end'] = pd.to_datetime(df['end'])
            df['year'] = df['end'].dt.year
            # Sort and keep the most recent filing (handles 10-K/A amendments)
            return df.sort_values(['year', 'end']).drop_duplicates('year', keep='last')
        except: return pd.DataFrame()

# --- 3. TERMINAL INTERFACE ---
def main():
    with st.sidebar:
        st.title("📂 Terminal")
        ticker_map = SECEngine.get_cik_map()
        ticker = st.text_input("SECURITY SEARCH", "AAPL").upper()
        st.divider()
        # Time-Travel selection
        timeframe = st.radio("TIME-TRAVEL", ["1Y", "5Y", "10Y", "MAX"], index=3)

    if ticker not in ticker_map:
        st.error("TICKER NOT FOUND")
        return

    cik = ticker_map[ticker]
    raw_data = SECEngine.fetch_sec_facts(cik)
    if not raw_data: return

    # Metric Extraction
    rev_tag = next((t for t in ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax'] 
                    if t in raw_data['facts']['us-gaap']), 'Revenues')
    df_rev = SECEngine.get_clean_metric(raw_data, rev_tag)
    df_net = SECEngine.get_clean_metric(raw_data, 'NetIncomeLoss')

    # Apply Time-Travel Filters
    curr_yr = datetime.now().year
    lookback = {"1Y": 1, "5Y": 5, "10Y": 10, "MAX": 50}[timeframe]
    df_rev = df_rev[df_rev['year'] >= curr_yr - lookback]
    df_net = df_net[df_net['year'] >= curr_yr - lookback]

    # --- ROW 1: KPI HERO ---
    st.header(f"Finance Terminal | {ticker}")
    c1, c2, c3, c4 = st.columns(4)
    latest_rev = df_rev['val'].iloc[-1] if not df_rev.empty else 0
    c1.metric("LTM REVENUE", f"${latest_rev/1e9:.2f}B")
    c2.metric("DATA DEPTH", f"{len(df_rev)}Y")
    c3.metric("TIME-FRAME", timeframe)
    c4.metric("CIK", cik)

    # --- ROW 2: TABS ---
    t_perf, t_stmt, t_ratio, t_dcf = st.tabs(["📈 PERFORMANCE", "📑 STATEMENTS", "📊 RATIO TRENDS", "💰 DCF"])

    with t_perf:
        # Performance Line Graph
        st.subheader(f"Historical Revenue Trajectory: {timeframe}")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_rev['year'], y=df_rev['val'], mode='lines+markers', 
                                 line=dict(color='#0052cc', width=3), name="Annual Revenue"))
        fig.update_layout(template="simple_white", height=500, xaxis_title="Fiscal Year", 
                          yaxis_title="Revenue (USD)", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        

    with t_stmt:
        # Scaled Financial Statements
        st.subheader("Standardized Income Statement (Billions USD)")
        stmt_df = df_rev[['year', 'val', 'form']].sort_values('year', ascending=False).copy()
        stmt_df['val'] = (stmt_df['val'] / 1e9).round(2)
        stmt_df.columns = ["Year", "Revenue ($B)", "Filing Type"]
        st.dataframe(stmt_df, use_container_width=True, hide_index=True)

    with t_ratio:
        st.subheader("10-Year Profitability & Ratio Trends")
        if not df_rev.empty and not df_net.empty:
            merged = pd.merge(df_rev[['year', 'val']], df_net[['year', 'val']], on='year', suffixes=('_r', '_n'))
            merged['Net Margin (%)'] = (merged['val_n'] / merged['val_r'] * 100).round(2)
            
            # Trend Chart
            st.line_chart(merged.set_index('year')['Net Margin (%)'], color="#0052cc")
            
            # Ratio Horizontal Table (Unique Columns Guaranteed)
            ratio_tab = merged[['year', 'Net Margin (%)']].set_index('year').T
            st.dataframe(ratio_tab, use_container_width=True)

    with t_dcf:
        st.subheader("Intrinsic Value Projection Matrix")
        # Localized Controls
        col_s1, col_s2 = st.columns(2)
        growth = col_s1.slider("Terminal Growth (%)", 0.0, 5.0, 2.5) / 100
        wacc = col_s2.slider("Discount Rate / WACC (%)", 5.0, 15.0, 8.5) / 100
        
        # Calculation
        term_val = (latest_rev * (1 + growth)) / (wacc - growth)
        fair_val = (latest_rev + term_val) / ((1 + wacc)**5)
        st.metric("ESTIMATED FAIR VALUE (ANNUAL REVENUE BASIS)", f"${fair_val/1e9:.2f}B")
        st.caption("Intrinsic value calculated using current annual revenue as FCF proxy.")

if __name__ == "__main__":
    main()
