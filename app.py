import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="Institutional Valuation Dashboard", layout="wide")
st.title("📈 Nifty 50 Algorithmic Valuation Dashboard")
st.markdown("Automated DCF Engine with **Growth Decay** and **WACC Spread Safeguards**.")

@st.cache_data
def load_data():
    conn = sqlite3.connect('nifty_finance.db')
    master_df = pd.read_sql_query("SELECT * FROM final_valuations", conn)
    conn.close()
    return master_df

df = load_data()

st.sidebar.header("⚙️ Dashboard Filters")
selected_signal = st.sidebar.multiselect("Investment Signal", options=df['signal'].unique(), default=df['signal'].unique())
selected_sector = st.sidebar.multiselect("Sector Filter", options=df['sector'].unique(), default=df['sector'].unique())

filtered_df = df[(df['signal'].isin(selected_signal)) & (df['sector'].isin(selected_sector))]

st.markdown("### Pipeline Analytics")
col1, col2, col3 = st.columns(3)
col1.metric("Total Equities", len(filtered_df))
col2.metric("Conservative Buy Signals", len(filtered_df[filtered_df['signal'] == 'UNDERVALUED (BUY)']))
col3.metric("Negative Cash Flow", len(filtered_df[filtered_df['signal'] == 'NEGATIVE CASH FLOW']))

st.divider()
st.subheader("Defensive Valuation Output")
display_cols = ['ticker', 'company_name', 'sector', 'current_price', 'intrinsic_value', 'signal', 'dynamic_wacc', 'dynamic_sgr']

styled_df = filtered_df[display_cols].copy()
styled_df['dynamic_wacc'] = (styled_df['dynamic_wacc'] * 100).round(2).astype(str) + '%'
styled_df['dynamic_sgr'] = (styled_df['dynamic_sgr'] * 100).round(2).astype(str) + '%'

st.dataframe(styled_df, use_container_width=True)

st.subheader("Valuation Gap Analysis")
chart_df = filtered_df[filtered_df['intrinsic_value'] > 0]
if not chart_df.empty:
    st.bar_chart(chart_df.set_index('ticker')[['current_price', 'intrinsic_value']])