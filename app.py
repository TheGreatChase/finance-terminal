import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from curl_cffi import requests as curl_requests
from datetime import datetime, timedelta

# --- 1. TERMINAL CONFIGURATION ---
st.set_page_config(page_title="Finance Terminal", layout="wide")

# Bloomberg-Style Dark Mode CSS
st.markdown("""
<style>
    .main { background-color: #0b0e14; color: #d1d4dc; font-family: 'Inter', sans-serif; }
    .stMetric { background-color: #1e222d; padding: 15px; border-radius: 5px; border-left: 4px solid #3d94ff; box-shadow: 0 2px 4px rgba(0,0,0,0.3); }
    [data-baseweb="tab-list"] { background-color: #1e222d; border-radius: 5px; gap: 10px; padding: 5px; }
    button[data-baseweb="tab"] { color: #d1d4dc !important; font-size: 14px; font-weight: 600; }
    button[aria-selected="true"] { border-bottom-color: #3d94ff !important; background-color: #2b2f3a !important; }
    .stDataFrame { border: 1px solid #333; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# --- 2. ANALYTICS ENGINE ---
class QuantEngine:
    @staticmethod
    @st.cache_data(ttl=3600)
    def fetch_terminal_data(ticker):
        """
        Fetches pricing and fundamentals. 
        Crucial: We do NOT return the Ticker object 't' to avoid caching errors.
        """
        session = curl_requests.Session(impersonate="chrome")
        t = yf.Ticker(ticker, session=session)
        
        try:
            # We extract all data locally within this function
            info = t.info
            hist = t.history(period="max")
            
            if hist.empty:
                return None, None, None, None, None
            
            # Fundamentals extracted as serializable DataFrames
            is_stmt = t.financials
            bs = t.balance_sheet
            cf = t.cashflow
            
            # Return only pickle-serializable data types
            return info, hist, is_stmt, bs, cf
        except Exception as e:
            st.error(f"Data Retrieval Error: {e}")
            return None, None, None, None, None

    @staticmethod
    def calculate_valuation_ratios(info, bs):
        """Calculates institutional valuation metrics."""
        try:
            equity = bs.loc['Stockholders Equity'][0] if 'Stockholders Equity' in bs.index else 0
            
            metrics = {
                "Trailing P/E": info.get('trailingPE', "N/A"),
                "Forward P/E": info.get('forwardPE', "N/A"),
                "P/B Ratio": info.get('priceToBook', "N/A"),
                "ROE (%)": round((info.get('netIncomeToCommon', 0) / equity) * 100, 2) if equity else "N/A",
                "Debt/Equity": info.get('debtToEquity', "N/A")
            }
            return metrics
        except Exception:
            return None

# --- 3. TERMINAL INTERFACE ---
def main():
    with st.sidebar:
        st.title("🗄️ Controls")
        ticker_input = st.text_input("SYMBOL SEARCH", "AAPL").upper()
        st.divider()
        st.subheader("DCF Valuation Logic")
        growth = st.slider("Long-term Growth (%)", 0.0, 5.0, 2.5) / 100
        wacc = st.slider("Discount Rate / WACC (%)", 5.0, 15.0, 8.5) / 100

    # Execution Layer: Note the removed 't' from the return values
    data_bundle = QuantEngine.fetch_terminal_data(ticker_input)
    info, hist, is_stmt, bs, cf = data_bundle

    if not info or 'shortName' not in info:
        st.error(f"FATAL: SECURITY '{ticker_input}' NOT FOUND.")
        return

    # Header section - renamed to Finance Terminal
    st.header(f"Finance Terminal | {info['shortName']} ({ticker_input})")
    
    # Hero Metric Tiles
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("PRICE", f"${info.get('currentPrice', 0):,.2f}", f"{info.get('regularMarketChangePercent', 0):+.2f}%")
    m2.metric("MARKET CAP", f"${info.get('marketCap', 0)/1e9:,.2f}B")
    m3.metric("ENTERPRISE VALUE", f"${info.get('enterpriseValue', 0)/1e9:,.2f}B")
    m4.metric("DIVIDEND YIELD", f"{info.get('dividendYield', 0)*100:.2f}%" if info.get('dividendYield') else "0.00%")

    # Functional Tabs
    tab_price, tab_fin, tab_ratios, tab_dcf = st.tabs([
        "📈 PERFORMANCE", "📑 STATEMENTS", "📊 RATIO ANALYSIS", "💰 DCF MODEL"
    ])

    with tab_price:
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Price"
        )])
        fig.update_layout(
            template="plotly_dark", height=600, xaxis_rangeslider_visible=False,
            xaxis=dict(rangeselector=dict(buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(count=5, label="5Y", step="year", stepmode="backward"),
                dict(step="all", label="MAX")
            ])), type="date")
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_fin:
        st_choice = st.radio("VIEW", ["Income Statement", "Balance Sheet", "Cash Flow"], horizontal=True)
        if st_choice == "Income Statement":
            st.dataframe(is_stmt, use_container_width=True)
        elif st_choice == "Balance Sheet":
            st.dataframe(bs, use_container_width=True)
        else:
            st.dataframe(cf, use_container_width=True)

    with tab_ratios:
        st.subheader("Institutional Ratio Comparison")
        ratios = QuantEngine.calculate_valuation_ratios(info, bs)
        if ratios:
            r_cols = st.columns(len(ratios))
            for i, (label, val) in enumerate(ratios.items()):
                r_cols[i].metric(label, val)

    with tab_dcf:
        st.subheader("DCF Valuation Matrix")
        fcf = info.get('freeCashflow', 0)
        if fcf > 0:
            shares = info.get('sharesOutstanding', 1)
            term_val = (fcf * (1 + growth)) / (wacc - growth)
            fair_val_total = (fcf + term_val) / ((1 + wacc)**5)
            fair_price = fair_val_total / shares
            upside = ((fair_price / info.get('currentPrice', 1)) - 1) * 100
            st.metric("ESTIMATED INTRINSIC VALUE", f"${fair_price:,.2f}", f"{upside:+.2f}% Upside")
        else:
            st.warning("Negative Free Cash Flow detected. DCF unavailable.")

if __name__ == "__main__":
    main()
