import streamlit as st
import pandas as pd
import requests

# 1. Page Setup: This makes the dashboard use the full width of your screen
st.set_page_config(page_title="Financial Data Terminal", layout="wide")
st.title("SEC Financial Intelligence Dashboard")

# 2. Identification: SEC requires this header to allow data access
# Using a generic placeholder as requested to avoid personal email
headers = {'User-Agent': "FinancialAnalysisApp researcher@example.com"}

# 3. Sidebar: This is where you will eventually add more companies
st.sidebar.header("Settings")
ticker = st.sidebar.text_input("Enter Ticker (Test with AAPL)", "AAPL")

# 4. SEC Data Logic: Pulling Apple (AAPL) as the default test
# Apple's CIK is 0000320193. We pad it with zeros to 10 digits.
cik = "0000320193"

# Link to the SEC's "Company Facts" JSON for this specific company
url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json"

# 5. Fetch and Process Data
try:
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        
        # We are pulling 'Revenues'. In SEC data, this is a standard label.
        # This reaches into the JSON folders: facts -> us-gaap -> Revenues
        rev_data = data['facts']['us-gaap']['Revenues']['units']['USD']
        
        # Turn that list of data into an easy-to-read table (DataFrame)
        df = pd.DataFrame(rev_data)
        
        # Convert dates into a format Python understands and sort them
        df['end'] = pd.to_datetime(df['end'])
        df = df.sort_values('end')

        # 6. Visual Interface
        st.subheader(f"Historical Revenue Trend: {ticker}")
        
        # Create the line chart
        st.line_chart(df.set_index('end')['val'])
        
        # Show the raw data table below the chart
        st.subheader("Filing Data Table")
        st.dataframe(df[['end', 'val', 'form']], use_container_width=True)
        
    else:
        st.error(f"SEC Server Error: {response.status_code}. Try again in a few minutes.")

except Exception as e:
    st.error(f"Could not load data: {e}")
