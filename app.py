import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="TradeSense AI",
    page_icon="📈",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>
.stApp {
    background-color: #081525;
    color: white;
}

[data-testid="stSidebar"] {
    background-color: #10243b;
}

h1, h2, h3 {
    color: #38bdf8;
}
</style>
""", unsafe_allow_html=True)


# Sidebar
st.sidebar.title("📈 TradeSense AI")
st.sidebar.caption("Your Personal AI Market Analyst")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "AI Chat",
        "Market Analysis",
        "Watchlist",
        "News & Sentiment",
        "Backtesting",
        "Prediction Tracker",
        "Strategy Builder",
        "Risk Analysis",
        "Settings"
    ]
)

# Header
st.title("TradeSense AI")
st.caption("AI-Powered Market Intelligence & Trading Decision Support System")

st.info(
    "Data Mode: Yahoo Finance | "
    "Historical/delayed data. Not a live trading feed."
)

# Dashboard
if page == "Dashboard":

    st.subheader("Market Overview")

    col1, col2, col3 = st.columns(3)

    symbols = {
        "NIFTY 50": "^NSEI",
        "BANK NIFTY": "^NSEBANK",
        "RELIANCE": "RELIANCE.NS"
    }

    for col, (name, symbol) in zip(
        [col1, col2, col3], symbols.items()
    ):
        try:
            data = yf.Ticker(symbol).history(period="5d")

            if not data.empty:
                price = data["Close"].iloc[-1]

                col.metric(
                    name,
                    f"₹{price:,.2f}"
                )
            else:
                col.warning(f"{name}: Data unavailable")

        except Exception:
            col.warning(f"{name}: Unable to fetch data")

    st.divider()

    st.subheader("Market Chart")

    selected_stock = st.selectbox(
        "Select Stock",
        ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    )

    try:
        stock_data = yf.Ticker(selected_stock).history(
            period="1mo",
            interval="1d"
        )

        if not stock_data.empty:

            fig = go.Figure()

            fig.add_trace(
                go.Candlestick(
                    x=stock_data.index,
                    open=stock_data["Open"],
                    high=stock_data["High"],
                    low=stock_data["Low"],
                    close=stock_data["Close"],
                    name="Price"
                )
            )

            fig.update_layout(
                template="plotly_dark",
                height=500,
                title=f"{selected_stock} - Historical Price",
                xaxis_title="Date",
                yaxis_title="Price"
            )

            st.plotly_chart(fig, use_container_width=True)

            st.caption(
                f"Last available candle: "
                f"{stock_data.index[-1]}"
            )

        else:
            st.warning("Market data is currently unavailable.")

    except Exception as error:
        st.error(f"Data fetching error: {error}")


# Other Pages
elif page == "AI Chat":
    st.subheader("🤖 AI Market Assistant")
    st.info("AI Chat module will be developed next.")

elif page == "Market Analysis":
    st.subheader("📊 Market Analysis")
    st.info("Technical indicators and market analysis coming next.")

elif page == "Watchlist":
    st.subheader("⭐ Watchlist")
    st.info("Watchlist module coming next.")

elif page == "News & Sentiment":
    st.subheader("📰 News & Sentiment")
    st.info("Live news integration will be added.")

elif page == "Backtesting":
    st.subheader("📈 Strategy Backtesting")
    st.info("Backtesting engine coming next.")

elif page == "Prediction Tracker":
    st.subheader("🎯 Prediction Tracker")
    st.info("Prediction tracking module coming next.")

elif page == "Strategy Builder":
    st.subheader("🧪 Strategy Builder")
    st.info("Custom strategy builder coming next.")

elif page == "Risk Analysis":
    st.subheader("⚠️ Risk Analysis")
    st.info("Risk analysis module coming next.")

elif page == "Settings":
    st.subheader("⚙️ Settings")
    st.write("Data source: Yahoo Finance")
    st.write("Upstox integration: Pending")
    st.write("Project: TradeSense AI")

st.divider()

st.caption(
    "TradeSense AI | Educational and Decision Support System | "
    f"{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
)
