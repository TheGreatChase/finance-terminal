import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. TERMINAL UI CONFIGURATION ---
st.set_page_config(page_title="Huzu Intelligence Terminal", layout="wide")

# Institutional Bloomberg-Style CSS
st.markdown("""
<style>
    .main { background-color: #0b0e14; color: #d1d4dc; font-family: 'Inter', sans-serif; }
    .stMetric { background-color: #1e222d; padding: 15px; border-radius: 5px; border-left: 4px solid #3d94ff; }
    [data-baseweb="tab-list"] { background-color: #1e222d; border-radius: 5px; gap: 10px; }
    button[data-baseweb="tab"] { color: #d1d4dc !important; font-size: 14px; font-weight: 600; }
    button[aria-selected="true"] { border-bottom-color: #3d94ff !important; }
    .stDataFrame { border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 2. QUANT DATA ENGINE ---
class QuantEngine:
    @staticmethod
    @st.cache_data(ttl=3600)
    def fetch_data(ticker):
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="max")
        # Ensure hist isn't empty before proceeding
        if hist.empty:
            return None, None, None, None, None
        return t, info, hist, t.financials, t.balance_sheet, t.cashflow

    @staticmethod
    def calculate_ratios(info, bs, is_stmt):
        try:
            # Valuation
            mcap = info.get('marketCap', 0)
            ev = info.get('enterpriseValue', 0)
            ebitda = info.get('ebitda', 0)
            
            # Profitability
            net_income = info.get('netIncomeToCommon', 0)
            equity = bs.loc['Stockholders Equity'][0] if 'Stockholders Equity' in bs.index else 0
            assets = bs.loc['Total Assets'][0] if 'Total Assets' in bs.index else 0
            
            ratios = {
                "P/E": info.get('trailingPE', "N/A"),
                "Forward P/E": info.get('forwardPE', "N/A"),
                "EV/EBITDA": round(ev / ebitda, 2) if ebitda else "N/A",
                "ROE (%)": round((net_income / equity) * 100, 2) if equity else "N/A",
                "ROA (%)": round((net_income / assets) * 100, 2) if assets else "N/A",
                "Current Ratio": info.get('currentRatio', "N/A"),
                "Debt/Equity": info.get('debtToEquity', "N/A")
            }
            return ratios
        except Exception:
            return None

# --- 3. DASHBOARD COMPONENTS ---
def render_terminal():
    # Sidebar Search
    with st.sidebar:
        st.title("🗄️ Terminal Controls")
        ticker_input = st.text_input("ENTER TICKER SYMBOL", "AAPL").upper()
        st.divider()
        st.subheader("DCF Assumptions")
        growth_rate = st.slider("Terminal Growth Rate (%)", 0.0, 5.0, 2.5) / 100
        wacc = st.slider("WACC (%)", 5.0, 15.0, 8.5) / 100

    # Data Acquisition
    t, info, hist, is_stmt, bs, cf = QuantEngine.fetch_data(ticker_input)

    if not info or 'shortName' not in info:
        st.error(f"SECURITY '{ticker_input}' NOT FOUND IN MASTER DATABASE.")
        return

    # --- ROW 1: HERO METRICS ---
    st.header(f"{info['shortName']} ({ticker_input}) | {info.get('exchange', 'N/A')}")
    col1, col2, col3, col4 = st.columns(4)
    price = info.get('currentPrice', 0)
    change = info.get('regularMarketChangePercent', 0)
    
    col1.metric("PRICE", f"${price:,.2f}", f"{change:+.2f}%")
    col2.metric("MARKET CAP", f"${info.get('marketCap', 0)/1e9:,.2f}B")
    col3.metric("ENT. VALUE (EV)", f"${info.get('enterpriseValue', 0)/1e9:,.2f}B")
    col4.metric("SECTOR", info.get('sector', 'N/A'))

    # --- ROW 2: CORE TABS ---
    tab_overview, tab_financials, tab_peers, tab_dcf = st.tabs([
        "📈 PERFORMANCE", "📑 STATEMENTS", "📊 PEER ANALYSIS", "💰 DCF VALUATION"
    ])

    with tab_overview:
        # Range Selector Logic
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], 
                                     low=hist['Low'], close=hist['Close'], name="Price"))
        fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False,
                          xaxis=dict(rangeselector=dict(buttons=list([
                              dict(count=1, label="1M", step="month", stepmode="backward"),
                              dict(count=6, label="6M", step="month", stepmode="backward"),
                              dict(count=1, label="YTD", step="year", stepmode="todate"),
                              dict(count=1, label="1Y", step="year", stepmode="backward"),
                              dict(step="all", label="MAX")
                          ])), type="date"))
        st.plotly_chart(fig, use_container_width=True)

        # Ratios Breakdown
        st.subheader("Key Valuation & Profitability Ratios")
        ratios = QuantEngine.calculate_ratios(info, bs, is_stmt)
        if ratios:
            r_cols = st.columns(len(ratios))
            for i, (label, val) in enumerate(ratios.items()):
                r_cols[i].metric(label, val)

    with tab_financials:
        # High-Density Financial Tables
        f_type = st.radio("SELECT STATEMENT", ["Income Statement", "Balance Sheet", "Cash Flow"], horizontal=True)
        if f_type == "Income Statement":
            st.dataframe(is_stmt, use_container_width=True)
        elif f_type == "Balance Sheet":
            st.dataframe(bs, use_container_width=True)
        else:
            st.dataframe(cf, use_container_width=True)

    with tab_peers:
        st.subheader(f"Competitor Benchmarking: {info.get('industry', 'Peer Group')}")
        # Simplified Peer Selection based on Industry
        peer_list = [ticker_input, 'MSFT', 'GOOGL', 'AMZN', 'META'] # Placeholder logic for demo
        peer_data = []
        for p in peer_list:
            p_info = yf.Ticker(p).info
            peer_data.append({
                "Ticker": p,
                "P/E": p_info.get('trailingPE', 0),
                "EV/EBITDA": round(p_info.get('enterpriseValue', 0) / (p_info.get('ebitda', 1)), 2),
                "Net Margin (%)": round(p_info.get('profitMargins', 0) * 100, 2)
            })
        st.table(pd.DataFrame(peer_data))

    with tab_dcf:
        st.subheader("2-Stage Discounted Cash Flow Model")
        fcf = info.get('freeCashflow', 0)
        if fcf > 0:
            terminal_value = (fcf * (1 + growth_rate)) / (wacc - growth_rate)
            intrinsic_val = (fcf + terminal_value) / ((1 + wacc)**5) # Multi-stage simplified
            share_price = intrinsic_val / info.get('sharesOutstanding', 1)
            
            st.metric("ESTIMATED FAIR VALUE", f"${share_price:,.2f}", 
                      f"{((share_price/price)-1)*100:+.2f}% Upside/Downside")
            st.caption("Simplified model assuming current FCF persists through terminal phase.")
        else:
            st.warning("POSITIVE FREE CASH FLOW REQUIRED FOR DCF MODELING.")

# --- 4. EXECUTION ---
if __name__ == "__main__":
    render_terminal()
