# TradeSense AI — Premium Dark Trading Terminal

AI-Powered Market Intelligence & Trading Decision Support System.

## Run
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Current capabilities
- Dashboard with current app clock (IST) and separate latest available market-candle date
- Yahoo Finance historical data (not guaranteed real-time)
- Candlestick charts and EMA overlays
- RSI, MACD, EMA20/50, SMA20, Bollinger Bands and ATR
- Explainable rule-based market score
- Why Not to Trade warning checklist
- Rule-based market mood detection
- Rule-based AI assistant
- SQLite watchlist, saved strategies and prediction journal
- Google News RSS headline discovery with basic keyword sentiment
- RSI strategy builder, simplified backtesting and regime-slice stress test
- Historical risk metrics and experimental Random Forest direction model
- Session-based paper trading simulator

## Data accuracy and limitations
Yahoo Finance data availability, delay and completeness can vary. The app must not describe it as a live feed.
The displayed app clock is the current runtime time in Asia/Kolkata. The market candle date is the last date returned by the data provider. On weekends/holidays, the latest trading candle can be from the previous trading session.
News sentiment is keyword-based. The ML model is experimental. Backtesting is simplified and omits realistic execution details.
Upstox Analytics API / WebSocket integration is pending token setup and endpoint validation.

## Security
Never commit API tokens, passwords, `.env`, or `.streamlit/secrets.toml` to GitHub.
