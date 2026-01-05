import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from curl_cffi import requests as curl_requests
from datetime import datetime, timedelta

# --- 1. TERMINAL UI & THEME CONFIGURATION ---
st.set_page_config(page_title="Finance Terminal", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Roboto+Mono&display=swap');
    .main { background-color: #0b0e14; color: #d1d4dc; font-family: 'Inter', sans-serif; }
    .stMetric { background-color: #1e222d; padding: 15px; border-radius: 4px; border-left: 3px solid #3d94ff; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    [data-baseweb="tab-list"] { background-color: #151921; border-radius: 4px; gap: 8px; padding: 4px; }
    button[data-baseweb="tab"] { color: #828282 !important; font-size: 13px; font-weight: 600; text-transform: uppercase; }
    button[aria-selected="true"] { color: #ffffff !important; background-color: #2b2f3a !important; border-bottom: 2px solid #3d94ff !important; }
    .stDataFrame { border: 1px solid #333; }
    h1, h2, h3 { color: #ffffff; font-weight: 700; letter-spacing: -0.5px; }
</style>
""", unsafe_allow_html=True)

# --- 2. LOGIC LAYER: QUANT ENGINE ---
class QuantEngine:
    @staticmethod
    @st.cache_data(ttl=3600)
    def fetch_terminal_bundle(ticker):
        """
        Extracts institutional data bundle. 
        Returns serializable dicts/DataFrames to avoid st.cache_data pickling errors.
        """
        session = curl_requests.Session(impersonate="chrome")
        t = yf.Ticker(ticker, session=session)
        
        try:
            info = t.info
            hist = t.history(period="max")
            if hist.empty: return None
            
            # Extract serializable snapshots of financial statements
            statements = {
                "income": t.financials,
                "balance": t.balance_sheet,
                "cashflow": t.cashflow,
                "quarterly_income": t.quarterly_financials
            }
            return {"info": info, "hist": hist, "statements": statements}
        except Exception as e:
            st.error(f"ENGINE ERROR: {e}")
            return None

    @staticmethod
    def compute_ratios(info, statements):
        """Calculates solvency, profitability, and valuation ratios."""
        try:
            bs = statements['balance']
            is_stmt = statements['income']
            
            # Safety-checked metric extraction
            def get_val(df, row): return df.loc[row][0] if row in df.index else 0

            equity = get_val(bs, 'Stockholders Equity')
            assets = get_val(bs, 'Total Assets')
            net_income = info.get('netIncomeToCommon', 0)
            ebitda = info.get('ebitda', 0)
            ev = info.get('enterpriseValue', 0)

            return {
                "Valuation": {
                    "P/E": info.get('trailingPE', "N/A"),
                    "Forward P/E": info.get('forwardPE', "N/A"),
                    "EV/EBITDA": round(ev/ebitda, 2) if ebitda else "N/A",
                    "P/S": info.get('priceToSalesTrailing12Months', "N/A")
                },
                "Profitability": {
                    "ROE (%)": round((net_income / equity) * 100, 2) if equity else "N/A",
                    "ROA (%)": round((net_income / assets) * 100, 2) if assets else "N/A",
                    "Profit Margin": f"{info.get('profitMargins', 0)*100:.2f}%"
                },
                "Solvency": {
                    "Current Ratio": info.get('currentRatio', "N/A"),
                    "Debt/Equity": info.get('debtToEquity', "N/A")
                }
            }
        except: return None

# --- 3. VISUAL LAYER ---
def main():
    with st.sidebar:
        st.title("🎄 Terminal Controls")
        ticker = st.text_input("SEARCH TICKER (Universal)", "AAPL").upper()
        st.divider()
        st.subheader("DCF Valuation Inputs")
        t_growth = st.slider("Terminal Growth (%)", 0.0, 5.0, 2.0) / 100
        wacc = st.slider("WACC / Discount Rate (%)", 5.0, 15.0, 8.0) / 100
        st.caption("Adjust sliders to update Stage-2 Intrinsic Value estimates.")

    # Data Acquisition with Caching
    bundle = QuantEngine.fetch_terminal_bundle(ticker)
    
    if not bundle:
        st.error(f"CRITICAL: Symbol '{ticker}' rejected by master data service.")
        return

    info, hist, statements = bundle['info'], bundle['hist'], bundle['statements']

    # --- ROW 1: KPI TILES ---
    st.header(f"Finance Terminal | {info.get('longName', ticker)}")
    
    m1, m2, m3, m4 = st.columns(4)
    price = info.get('currentPrice', 0)
    change = info.get('regularMarketChangePercent', 0)
    m1.metric("PRICE", f"${price:,.2f}", f"{change:+.2f}%")
    m2.metric("MARKET CAP", f"${info.get('marketCap', 0)/1e9:,.2f}B")
    m3.metric("ENT. VALUE (EV)", f"${info.get('enterpriseValue', 0)/1e9:,.2f}B")
    m4.metric("PEER GROUP", info.get('industry', 'N/A'))

    # --- ROW 2: TABS ---
    tab_price, tab_stmt, tab_ratio, tab_dcf = st.tabs([
        "📈 Performance", "📑 Statements", "📊 Ratio Analysis", "💰 DCF Model"
    ])

    with tab_price:
        # High-Density Interactive Chart
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close']
        )])
        fig.update_layout(
            template="plotly_dark", height=550, xaxis_rangeslider_visible=False,
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(rangeselector=dict(buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="MAX")
            ])), type="date")
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_stmt:
        s_choice = st.radio("SELECT VIEW", ["Income", "Balance", "Cash Flow"], horizontal=True)
        if s_choice == "Income": st.dataframe(statements['income'], use_container_width=True)
        elif s_choice == "Balance": st.dataframe(statements['balance'], use_container_width=True)
        else: st.dataframe(statements['cashflow'], use_container_width=True)

    with tab_ratio:
        st.subheader("Institutional Metrics Snapshot")
        r_data = QuantEngine.compute_ratios(info, statements)
        if r_data:
            for category, metrics in r_data.items():
                st.write(f"**{category}**")
                cols = st.columns(len(metrics))
                for i, (k, v) in enumerate(metrics.items()):
                    cols[i].metric(k, v)
                st.divider()

    with tab_dcf:
        st.subheader("Intrinsic Value Matrix")
        fcf = info.get('freeCashflow', 0)
        if fcf > 0:
            shares = info.get('sharesOutstanding', 1)
            term_val = (fcf * (1 + t_growth)) / (wacc - t_growth)
            intrinsic = (fcf + term_val) / ((1 + wacc)**5)
            fair_price = intrinsic / shares
            upside = ((fair_price / price) - 1) * 100
            st.metric("EST. FAIR VALUE", f"${fair_price:,.2f}", f"{upside:+.2f}% Upside")
        else:
            st.warning("DATA UNAVAILABLE: Positive FCF required for DCF projections.")

if __name__ == "__main__":
    main()
