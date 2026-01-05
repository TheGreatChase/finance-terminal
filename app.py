import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from curl_cffi import requests as curl_requests
from datetime import datetime

# --- 1. INSTITUTIONAL UI CONFIGURATION ---
st.set_page_config(page_title="Finance Terminal", layout="wide")

# High-Contrast "Marquee" Slate Theme (Optimized for readability)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    .main { background-color: #0e1117; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    /* Metric Card Styling */
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 24px !important; font-weight: 600 !important; }
    [data-testid="stMetricLabel"] { color: #9da5b1 !important; font-size: 13px !important; text-transform: uppercase; }
    /* Sidebar Cleanup */
    .css-1d391kg { background-color: #161b22; }
    /* Dataframe Styling */
    .stDataFrame { border: 1px solid #30363d; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# --- 2. ADVANCED DATA ENGINE ---
class QuantEngine:
    @staticmethod
    @st.cache_data(ttl=3600)
    def fetch_full_terminal_data(ticker):
        session = curl_requests.Session(impersonate="chrome")
        t = yf.Ticker(ticker, session=session)
        try:
            info = t.info
            # Market price history (15Y max if available)
            hist = t.history(period="max")
            
            # Financials (Merging Annual and Quarterly)
            # yfinance provides 4 years by default; 10-15Y often requires multiple API calls or professional tier.
            # We pull the maximum available from the standard endpoint.
            data = {
                "info": info,
                "hist": hist,
                "is_a": t.financials, "is_q": t.quarterly_financials,
                "bs_a": t.balance_sheet, "bs_q": t.quarterly_balance_sheet,
                "cf_a": t.cashflow, "cf_q": t.quarterly_cashflow
            }
            return data
        except Exception as e:
            st.error(f"ENGINE ERROR: {e}")
            return None

    @staticmethod
    def format_currency(df):
        """Intelligently scales financials to Billions or Millions based on magnitude."""
        if df is None or df.empty: return df
        max_val = df.abs().max().max()
        if max_val > 1e9:
            return (df / 1e9).round(2), "Billions"
        elif max_val > 1e6:
            return (df / 1e6).round(2), "Millions"
        return df.round(2), "Units"

# --- 3. TERMINAL INTERFACE ---
def main():
    # Sidebar: Cleaned to only contain Search
    with st.sidebar:
        st.title("📂 Terminal")
        ticker = st.text_input("SECURITY SEARCH", "AAPL").upper()
        st.divider()
        st.caption("Institutional Financial Terminal v2.0")

    bundle = QuantEngine.fetch_full_terminal_data(ticker)
    if not bundle:
        st.error("SECURITY NOT FOUND")
        return

    info = bundle['info']
    hist = bundle['hist']

    # KPI Top Row
    st.header(f"Finance Terminal | {info.get('longName', ticker)}")
    c1, c2, c3, c4 = st.columns(4)
    price = info.get('currentPrice', 0)
    change = info.get('regularMarketChangePercent', 0)
    c1.metric("LATEST PRICE", f"${price:,.2f}", f"{change:+.2f}%")
    c2.metric("MARKET CAP", f"${info.get('marketCap', 0)/1e9:,.2f}B")
    c3.metric("ENT. VALUE", f"${info.get('enterpriseValue', 0)/1e9:,.2f}B")
    c4.metric("52W HIGH", f"${info.get('fiftyTwoWeekHigh', 0):,.2f}")

    # Main Tabs
    t_perf, t_stmt, t_ratio, t_dcf = st.tabs([
        "📈 PERFORMANCE", "📑 STATEMENTS", "📊 RATIO HISTORY", "💰 DCF VALUATION"
    ])

    with t_perf:
        # High-Density Line Graph with Proper Context
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', 
                                 line=dict(color='#3d94ff', width=2), name="Close Price"))
        fig.update_layout(
            template="plotly_dark", height=500,
            xaxis_title="Timeline", yaxis_title="Price (USD)",
            margin=dict(l=0, r=0, t=20, b=0),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)

    with t_stmt:
        col_type, col_period = st.columns([2, 1])
        s_type = col_type.radio("VIEW", ["Income Statement", "Balance Sheet", "Cash Flow"], horizontal=True)
        period = col_period.radio("PERIOD", ["Annual", "Quarterly"], horizontal=True)
        
        # Mapping Logic
        key = {"Income Statement": "is", "Balance Sheet": "bs", "Cash Flow": "cf"}[s_type]
        suffix = "_a" if period == "Annual" else "_q"
        raw_df = bundle[f"{key}{suffix}"]
        
        # Intelligent Formatting
        formatted_df, unit_key = QuantEngine.format_currency(raw_df)
        st.subheader(f"{s_type} (Values in {unit_key})")
        st.dataframe(formatted_df, use_container_width=True)

    with t_ratio:
        st.subheader("Historical Ratio Analytics")
        # Calculating Ratios over the available 4-year period
        is_stmt = bundle['is_a']
        bs = bundle['bs_a']
        try:
            # Vectorized Ratio Calculation
            net_income = is_stmt.loc['Net Income']
            revenue = is_stmt.loc['Total Revenue']
            equity = bs.loc['Stockholders Equity']
            
            ratios_df = pd.DataFrame({
                "Net Margin (%)": (net_income / revenue * 100).round(2),
                "ROE (%)": (net_income / equity * 100).round(2),
                "Asset Turnover": (revenue / bs.loc['Total Assets']).round(2)
            }).T
            st.dataframe(ratios_df, use_container_width=True)
            
            # Ratio Visualization
            st.line_chart(ratios_df.T)
        except:
            st.warning("Insufficient historical data for complete ratio trend.")

    with t_dcf:
        st.subheader("Stage-2 Intrinsic Value Model")
        # Settings only visible in this tab
        col_s1, col_s2 = st.columns(2)
        growth = col_s1.slider("Terminal Growth (%)", 0.0, 5.0, 2.5) / 100
        wacc = col_s2.slider("WACC (%)", 5.0, 15.0, 8.5) / 100
        
        fcf = info.get('freeCashflow', 0)
        if fcf > 0:
            term_val = (fcf * (1 + growth)) / (wacc - growth)
            fair_val = (fcf + term_val) / ((1 + wacc)**5)
            fair_price = fair_val / info.get('sharesOutstanding', 1)
            st.metric("ESTIMATED FAIR VALUE", f"${fair_price:,.2f}", f"{((fair_price/price)-1)*100:+.2f}% Upside")
        else:
            st.warning("Positive Free Cash Flow required for DCF calculation.")

if __name__ == "__main__":
    main()
