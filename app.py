import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

# --- 1. INSTITUTIONAL UI: GOLDMAN SLATE THEME ---
st.set_page_config(page_title="Finance Terminal", layout="wide")

st.markdown("""
<style>
    .main { background-color: #0e1117; color: #e0e0e0; font-family: 'Inter', sans-serif; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 28px !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #9da5b1 !important; text-transform: uppercase; letter-spacing: 1.5px; font-size: 12px !important; }
    .stDataFrame { border: 1px solid #30363d; border-radius: 4px; }
    button[aria-selected="true"] { border-bottom: 3px solid #3d94ff !important; color: #ffffff !important; background-color: #1c2128 !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: #0e1117; padding: 0px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre; }
</style>
""", unsafe_allow_html=True)

# --- 2. DATA ENGINE: SEC EDGAR ARCHITECTURE ---
class SECEngine:
    HEADERS = {'User-Agent': "InstitutionalTerminal researcher@example.com"}

    @staticmethod
    @st.cache_data
    def get_ticker_map():
        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            r = requests.get(url, headers=SECEngine.HEADERS)
            return {v['ticker']: str(v['cik_str']).zfill(10) for k, v in r.json().items()}
        except: return {}

    @staticmethod
    @st.cache_data(ttl=3600)
    def fetch_sec_facts(cik):
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        r = requests.get(url, headers=SECEngine.HEADERS)
        return r.json() if r.status_code == 200 else None

    @staticmethod
    def get_clean_metric(data, tag, annual=True):
        try:
            facts = data['facts']['us-gaap'][tag]['units']['USD']
            df = pd.DataFrame(facts)
            df['end'] = pd.to_datetime(df['end'])
            if annual:
                df = df[df['form'] == '10-K']
            return df.sort_values('end').drop_duplicates('end', keep='last')
        except: return pd.DataFrame()

    @staticmethod
    def scale_data(df):
        """Intelligently scales financials and returns the unit label."""
        if df.empty or 'val' not in df.columns: return df, "Units"
        max_val = df['val'].abs().max()
        if max_val >= 1e9:
            df['val_scaled'] = (df['val'] / 1e9).round(2)
            return df, "Billions"
        if max_val >= 1e6:
            df['val_scaled'] = (df['val'] / 1e6).round(2)
            return df, "Millions"
        df['val_scaled'] = df['val']
        return df, "Units"

# --- 3. CORE INTERFACE ---
def main():
    # Sidebar Search only
    with st.sidebar:
        st.title("📂 Terminal")
        ticker_map = SECEngine.get_ticker_map()
        ticker = st.text_input("SECURITY SEARCH", "AAPL").upper()
        st.divider()
        st.caption("Direct SEC EDGAR Integration (15Y Depth)")

    if ticker not in ticker_map:
        st.error("INVALID TICKER OR SECURITY NOT REGISTERED WITH SEC.")
        return

    cik = ticker_map[ticker]
    raw = SECEngine.fetch_sec_facts(cik)
    if not raw:
        st.error("DATA RETRIEVAL FAILURE: SEC SERVERS UNREACHABLE.")
        return

    # Dynamic Tag Selection (Handles SEC variations)
    rev_tag = next((t for t in ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet'] if t in raw['facts']['us-gaap']), 'Revenues')
    
    # Fetch DataFrames
    df_rev = SECEngine.get_clean_metric(raw, rev_tag)
    df_net = SECEngine.get_clean_metric(raw, 'NetIncomeLoss')
    df_equity = SECEngine.get_clean_metric(raw, 'StockholdersEquity')
    
    # Scale Revenue for Statements
    df_rev_scaled, unit_label = SECEngine.scale_data(df_rev.copy())

    # --- TOP ROW: KPI HERO TILES ---
    st.header(f"Finance Terminal | {ticker}")
    c1, c2, c3, c4 = st.columns(4)
    if not df_rev.empty:
        latest = df_rev['val'].iloc[-1]
        prev = df_rev['val'].iloc[-2] if len(df_rev) > 1 else latest
        c1.metric("LTM REVENUE", f"${latest/1e9:.2f}B", f"{((latest/prev)-1)*100:+.2f}% YoY")
        c2.metric("CIK IDENTIFIER", cik)
        c3.metric("DATA DEPTH", f"{len(df_rev)} YEARS")
        c4.metric("REPORTING UNIT", unit_label)

    # --- MAIN TABS ---
    t_perf, t_stmt, t_ratio, t_dcf = st.tabs(["📈 PERFORMANCE", "📑 STATEMENTS", "📊 RATIO HISTORY", "💰 DCF VALUATION"])

    with t_perf:
        st.subheader(f"Historical Revenue Performance (USD)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_rev['end'], y=df_rev['val'], mode='lines+markers', line=dict(color='#3d94ff', width=3)))
        fig.update_layout(
            template="plotly_dark", height=500,
            xaxis_title="Filing Year", yaxis_title="Revenue (USD)",
            margin=dict(l=0, r=0, t=20, b=0), hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)

    with t_stmt:
        st.subheader(f"Income Statement Data (Values in {unit_label})")
        # Ensure only scaled values are shown
        statement_df = df_rev_scaled[['end', 'val_scaled', 'form']].sort_values('end', ascending=False)
        statement_df.columns = ['Filing Date', f'Revenue ({unit_label})', 'Form Type']
        st.dataframe(statement_df, use_container_width=True, hide_index=True)

    with t_ratio:
        st.subheader("10-Year Profitability Trend (Net Margin)")
        if not df_rev.empty and not df_net.empty:
            merged = pd.merge(df_rev, df_net, on='end', suffixes=('_r', '_n'))
            merged['Net Margin (%)'] = (merged['val_n'] / merged['val_r'] * 100).round(2)
            
            fig_r = go.Figure()
            fig_r.add_trace(go.Bar(x=merged['end'], y=merged['Net Margin (%)'], marker_color='#3d94ff', name="Net Margin"))
            fig_r.update_layout(template="plotly_dark", xaxis_title="Year", yaxis_title="Margin %", height=400)
            st.plotly_chart(fig_r, use_container_width=True)
            
            # Ratio Table
            ratio_tab = merged[['end', 'Net Margin (%)']].copy()
            ratio_tab['end'] = ratio_tab['end'].dt.year
            st.dataframe(ratio_tab.set_index('end').T, use_container_width=True)

    with t_dcf:
        st.subheader("Stage-2 Intrinsic Value Projection")
        # DCF Settings restricted to this container
        with st.container():
            s1, s2 = st.columns(2)
            growth = s1.slider("Terminal Growth Rate (%)", 0.0, 5.0, 2.0) / 100
            wacc = s2.slider("WACC / Discount Rate (%)", 5.0, 15.0, 8.0) / 100
            
            if not df_rev.empty:
                rev_base = df_rev['val'].iloc[-1]
                # High-level Stage 2 DCF
                terminal_val = (rev_base * (1 + growth)) / (wacc - growth)
                intrinsic = (rev_base + terminal_val) / ((1 + wacc)**5)
                st.metric("ESTIMATED INTRINSIC VALUE (REVENUE BASIS)", f"${intrinsic/1e9:,.2f}B")
                st.info("Analysis uses Revenue as a proxy for FCF in this 15-year historical view.")

if __name__ == "__main__":
    main()
