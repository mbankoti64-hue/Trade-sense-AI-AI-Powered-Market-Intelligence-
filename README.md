# TradeSense AI

AI-Powered Market Intelligence & Trading Decision Support System.

## Run locally
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Current data status
- Yahoo Finance (`yfinance`) is used for historical market data.
- It is not guaranteed to be real-time. The app labels the data accordingly.
- Upstox Analytics API / WebSocket integration is pending.
- Google News RSS is used for headline discovery; keyword sentiment is only a rough estimate.

## Included modules
Dashboard, technical indicators (RSI, MACD, EMA, Bollinger Bands, ATR), explainable custom score,
rule-based assistant, SQLite watchlist, news headlines, RSI strategy builder, backtesting,
historical risk metrics, experimental time-ordered Random Forest evaluation, prediction logging.

## Important
Educational prototype only; not investment advice. Backtest and model results do not guarantee future performance.
Never commit API tokens, passwords, or `.streamlit/secrets.toml` to GitHub.
