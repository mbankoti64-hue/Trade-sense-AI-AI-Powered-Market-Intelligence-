import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3, requests, xml.etree.ElementTree as ET

# ============================================================
# TRADESENSE AI | Premium Dark Trading Terminal
# Historical-data prototype. Upstox integration is a later step.
# ============================================================

st.set_page_config(
    page_title="TradeSense AI | Market Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

IST = ZoneInfo("Asia/Kolkata")
DB_PATH = "tradesense.db"

INSTRUMENTS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "ICICI BANK": "ICICIBANK.NS",
    "ITC": "ITC.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "BHARTI AIRTEL": "BHARTIARTL.NS",
    "WIPRO": "WIPRO.NS",
    "SBIN": "SBIN.NS",
    "LT": "LT.NS"
}
PERIODS = {"1 Month":"1mo", "3 Months":"3mo", "6 Months":"6mo", "1 Year":"1y", "2 Years":"2y", "5 Years":"5y"}

# ---------------------------- STYLE ----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --bg:#050d18; --panel:#0b1b2b; --panel2:#10263a; --line:#1b3b55; --cyan:#38d5ff; --blue:#2588ff; --muted:#8fa9bf; }
html, body, [class*="css"] {font-family:'DM Sans',sans-serif;}
.stApp {
 background:
 radial-gradient(ellipse at 12% 0%, rgba(0,157,255,.16), transparent 35%),
 radial-gradient(ellipse at 88% 15%, rgba(0,225,255,.09), transparent 28%),
 linear-gradient(135deg,#050d18 0%,#081729 48%,#06111e 100%);
 color:#eaf5ff;
}
[data-testid="stSidebar"] {
 background:linear-gradient(180deg,#0b1e31 0%,#06111e 100%);
 border-right:1px solid #1b3b55;
}
[data-testid="stSidebar"] * {color:#d9eafa;}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif!important;color:#f2f8ff!important;letter-spacing:-.4px;}
p, label, .stMarkdown {color:#d2e2ef;}
div[data-testid="stMetric"] {
 background:linear-gradient(145deg,rgba(17,43,66,.96),rgba(8,25,41,.96));
 border:1px solid rgba(56,213,255,.20); padding:15px 17px; border-radius:15px;
 box-shadow:0 8px 26px rgba(0,0,0,.18);
}
div[data-testid="stMetricLabel"] {color:#9cb6ca;}
div[data-testid="stMetricValue"] {color:#f5fbff;font-family:'Space Grotesk',sans-serif;}
.stButton>button {
 background:linear-gradient(100deg,#087bb8,#1765d1);color:white;border:1px solid #238dc5;
 border-radius:10px;font-weight:700;min-height:2.5rem;transition:.2s;
}
.stButton>button:hover {border:1px solid #7ce8ff;box-shadow:0 0 18px rgba(56,213,255,.25);color:white;}
.stTextInput input,.stNumberInput input,.stSelectbox div[data-baseweb="select"] {
 background:#0b2033!important;color:#eef8ff!important;border-color:#25445e!important;
}
div[data-testid="stAlert"] {border-radius:12px;}
hr {border-color:#1b3b55;}
div[data-testid="stDataFrame"] {border:1px solid #1b3b55;border-radius:12px;overflow:hidden;}
.ts-hero {
 background:linear-gradient(115deg,rgba(13,44,69,.96),rgba(8,25,43,.94));
 border:1px solid rgba(56,213,255,.28); border-radius:20px; padding:24px 26px;
 box-shadow:0 12px 40px rgba(0,0,0,.22); margin-bottom:18px;
}
.ts-kicker {color:#50dfff;text-transform:uppercase;letter-spacing:2px;font-size:11px;font-weight:700;}
.ts-sub {color:#9eb8cd;font-size:13px;}
.ts-pill {display:inline-block;background:rgba(56,213,255,.12);border:1px solid rgba(56,213,255,.28);
 color:#8beaff;border-radius:30px;padding:5px 11px;font-size:11px;font-weight:700;letter-spacing:.5px;}
.ts-card {background:linear-gradient(145deg,#10263a,#0a1b2c);border:1px solid #1b3b55;
 border-radius:16px;padding:17px 19px;margin:7px 0;box-shadow:0 8px 24px rgba(0,0,0,.16);}
.ts-muted {color:#91a9bd;font-size:12px;}
.ts-good {color:#42e3a4;font-weight:700;}
.ts-bad {color:#ff6e7e;font-weight:700;}
.ts-warn {color:#ffcf70;font-weight:700;}
[data-testid="stRadio"] label {padding:5px 4px;}
footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------------- DATABASE ----------------------------
def connect_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con = connect_db()
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, added_at TEXT)")
    cur.execute("""CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, created_at TEXT,
        horizon TEXT, view TEXT, reference_price REAL, status TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS strategies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, symbol TEXT,
        entry_rsi REAL, exit_rsi REAL, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT,
        quantity REAL, price REAL, created_at TEXT)""")
    con.commit()
    con.close()

init_db()

# ---------------------------- TIME / MARKET DATA ----------------------------
def now_ist():
    return datetime.now(IST)

@st.cache_data(ttl=240, show_spinner=False)
def fetch_history(symbol, period="6mo"):
    try:
        data = yf.download(symbol, period=period, interval="1d", auto_adjust=True,
                           progress=False, threads=False)
        if data is None or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = data.rename_axis("Date").reset_index()
        required = ["Open","High","Low","Close","Volume"]
        if not all(c in data.columns for c in required):
            return pd.DataFrame()
        for c in required:
            data[c] = pd.to_numeric(data[c], errors="coerce")
        return data.dropna(subset=["Close"]).copy()
    except Exception:
        return pd.DataFrame()

def add_indicators(data):
    if data.empty: return data
    x = data.copy()
    c = x["Close"]
    x["EMA20"] = c.ewm(span=20, adjust=False).mean()
    x["EMA50"] = c.ewm(span=50, adjust=False).mean()
    x["SMA20"] = c.rolling(20).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    x["RSI"] = 100 - 100/(1+rs)
    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    x["MACD"] = e12-e26
    x["MACD_SIGNAL"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_HIST"] = x["MACD"]-x["MACD_SIGNAL"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    x["BB_UPPER"] = mid+2*sd
    x["BB_LOWER"] = mid-2*sd
    prev = c.shift(1)
    tr = pd.concat([(x["High"]-x["Low"]), (x["High"]-prev).abs(), (x["Low"]-prev).abs()],axis=1).max(axis=1)
    x["ATR"] = tr.rolling(14).mean()
    x["RET"] = c.pct_change()
    return x

def current_price_change(data):
    if data.empty: return None, None
    p = float(data["Close"].iloc[-1])
    prev = float(data["Close"].iloc[-2]) if len(data)>1 else p
    return p, ((p-prev)/prev*100) if prev else 0

def indicator_view(data):
    if data.empty or len(data)<55:
        return {"trend":"Insufficient data","momentum":"Unavailable","rsi":None,"macd":"Unavailable","reasons":["At least 55 historical candles are recommended."]}
    r=data.iloc[-1]
    trend = "Bullish" if r["EMA20"]>r["EMA50"] else "Bearish"
    rsi=float(r["RSI"]) if pd.notna(r["RSI"]) else None
    momentum = "Overbought zone" if rsi is not None and rsi>=70 else "Oversold zone" if rsi is not None and rsi<=30 else "Neutral zone"
    macd="Positive" if r["MACD"]>r["MACD_SIGNAL"] else "Negative"
    reasons=[
        "EMA 20 is above EMA 50." if trend=="Bullish" else "EMA 20 is below EMA 50.",
        f"RSI is {rsi:.1f} ({momentum.lower()})." if rsi is not None else "RSI is unavailable.",
        f"MACD momentum is {macd.lower()}."
    ]
    return {"trend":trend,"momentum":momentum,"rsi":rsi,"macd":macd,"reasons":reasons}

def score_parts(data):
    v=indicator_view(data)
    if v["rsi"] is None: return None, {}
    last=data.iloc[-1]
    trend=85 if last["EMA20"]>last["EMA50"] else 35
    momentum=80 if 45<=v["rsi"]<=65 else 55 if 30<v["rsi"]<70 else 30
    macd=80 if v["macd"]=="Positive" else 35
    vol=data["RET"].tail(20).std()*np.sqrt(252) if data["RET"].tail(20).notna().sum()>5 else np.nan
    risk=80 if pd.notna(vol) and vol<.22 else 55 if pd.notna(vol) and vol<.40 else 25
    parts={"Trend":trend,"Momentum":momentum,"MACD":macd,"Risk profile":risk}
    score=round(.30*trend+.30*momentum+.20*macd+.20*risk)
    return score,parts

def market_mood(data):
    if data.empty or len(data)<55: return "Insufficient data","Need more candles"
    v=indicator_view(data)
    vol=data["RET"].tail(20).std()*np.sqrt(252)
    if pd.notna(vol) and vol>.45: return "High Volatility","Recent annualised volatility estimate is elevated."
    if v["trend"]=="Bullish" and v["macd"]=="Positive": return "Bullish Trend","Trend and MACD currently point in the same positive direction."
    if v["trend"]=="Bearish" and v["macd"]=="Negative": return "Bearish Trend","Trend and MACD currently point in the same negative direction."
    return "Sideways / Uncertain","Indicators are mixed; directional conviction is limited."

def why_not_trade(data):
    if data.empty or len(data)<55:
        return ["Insufficient history to run the trade-quality checks."]
    v=indicator_view(data); last=data.iloc[-1]; warnings=[]
    if v["rsi"] is not None and v["rsi"]>=68: warnings.append("RSI is near/inside the upper momentum zone; chasing a move may be risky.")
    if v["rsi"] is not None and v["rsi"]<=32: warnings.append("RSI is near/inside the lower momentum zone; weakness may persist.")
    if v["trend"]=="Bullish" and v["macd"]=="Negative": warnings.append("Trend and MACD disagree; momentum confirmation is missing.")
    if v["trend"]=="Bearish" and v["macd"]=="Positive": warnings.append("Trend and MACD disagree; downside momentum is not confirmed.")
    atr=float(last["ATR"]) if pd.notna(last["ATR"]) else 0
    price=float(last["Close"])
    if atr and price and atr/price>.035: warnings.append("ATR is high relative to price; position sizing and stop distance need extra care.")
    if not warnings: warnings.append("No major warning was triggered by these simple rules, but that is not a buy/sell recommendation.")
    return warnings

def market_summary(name,data):
    v=indicator_view(data); score,_=score_parts(data)
    if v["rsi"] is None: return "Not enough historical data for a reliable summary."
    return (f"{name} currently shows a **{v['trend'].lower()}** EMA trend, "
            f"RSI **{v['rsi']:.1f}**, and **{v['macd'].lower()}** MACD momentum. "
            f"The custom analytical score is **{score}/100**. This describes historical indicators, not a forecast.")

# ---------------------------- CHARTS ----------------------------
def price_chart(data,title):
    fig=go.Figure()
    fig.add_trace(go.Candlestick(x=data["Date"],open=data["Open"],high=data["High"],low=data["Low"],close=data["Close"],name="Candles"))
    for col,label in [("EMA20","EMA 20"),("EMA50","EMA 50")]:
        fig.add_trace(go.Scatter(x=data["Date"],y=data[col],mode="lines",name=label,line=dict(width=1.5)))
    fig.update_layout(template="plotly_dark",height=510,title=title,xaxis_rangeslider_visible=False,
                      paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(5,15,27,.8)",
                      margin=dict(l=15,r=15,t=55,b=15),legend=dict(orientation="h",y=1.02,x=0))
    return fig

# ---------------------------- STRATEGY TESTING ----------------------------
def rsi_backtest(data,entry=30,exit_level=70,capital=100000,cost=.001):
    x=add_indicators(data).dropna(subset=["RSI"]).copy()
    if len(x)<30: return None
    cash=float(capital); qty=0.0; trades=[]; curve=[]
    for _,row in x.iterrows():
        px=float(row["Close"]); rsi=float(row["RSI"])
        if qty==0 and rsi<entry:
            qty=(cash*(1-cost))/px; cash=0
            trades.append({"Date":row["Date"],"Side":"BUY","Price":px})
        elif qty>0 and rsi>exit_level:
            cash=qty*px*(1-cost); qty=0
            trades.append({"Date":row["Date"],"Side":"SELL","Price":px})
        curve.append(cash+qty*px)
    final=cash+qty*float(x["Close"].iloc[-1])
    equity=pd.Series(curve,index=x["Date"])
    dd=(equity/equity.cummax()-1)*100
    completed=sum(t["Side"]=="SELL" for t in trades)
    return {"final":final,"return_pct":(final/capital-1)*100,"completed":completed,
            "max_dd":float(dd.min()),"trades":trades,
            "curve":pd.DataFrame({"Date":x["Date"],"Equity":curve})}

# ---------------------------- NEWS ----------------------------
@st.cache_data(ttl=900,show_spinner=False)
def fetch_news(query):
    try:
        r=requests.get("https://news.google.com/rss/search",
            params={"q":query+" stock market India","hl":"en-IN","gl":"IN","ceid":"IN:en"},
            headers={"User-Agent":"Mozilla/5.0"},timeout=12)
        r.raise_for_status()
        root=ET.fromstring(r.content); output=[]
        pos=["profit","growth","surge","rises","rally","strong","gain","upgrade","beats","record"]
        neg=["loss","fall","falls","crash","decline","fraud","probe","weak","downgrade","misses"]
        for item in root.findall(".//item")[:15]:
            title=item.findtext("title",""); low=title.lower()
            p=sum(k in low for k in pos); n=sum(k in low for k in neg)
            sentiment="Positive" if p>n else "Negative" if n>p else "Neutral"
            src=item.find("source")
            output.append({"title":title,"link":item.findtext("link",""),
                           "date":item.findtext("pubDate",""),
                           "source":src.text if src is not None else "News source",
                           "sentiment":sentiment})
        return output
    except Exception: return []

# ---------------------------- DB HELPERS ----------------------------
def add_watch(symbol):
    con=connect_db(); con.execute("INSERT OR IGNORE INTO watchlist VALUES(?,?)",(symbol,now_ist().isoformat(timespec="seconds"))); con.commit(); con.close()
def get_watchlist():
    con=connect_db(); d=pd.read_sql_query("SELECT symbol,added_at FROM watchlist ORDER BY added_at DESC",con); con.close(); return d
def remove_watch(symbol):
    con=connect_db(); con.execute("DELETE FROM watchlist WHERE symbol=?",(symbol,)); con.commit(); con.close()
def record_prediction(symbol,view,price):
    con=connect_db(); con.execute("INSERT INTO predictions(symbol,created_at,horizon,view,reference_price,status) VALUES(?,?,?,?,?,'Pending')",
        (symbol,now_ist().isoformat(timespec="seconds"),"Next available daily candle",view,float(price))); con.commit(); con.close()
def save_strategy(name,symbol,entry,exit_level):
    con=connect_db(); con.execute("INSERT INTO strategies(name,symbol,entry_rsi,exit_rsi,created_at) VALUES(?,?,?,?,?)",
        (name,symbol,entry,exit_level,now_ist().isoformat(timespec="seconds"))); con.commit(); con.close()

# ---------------------------- SIDEBAR ----------------------------
with st.sidebar:
    st.markdown("# 📈 TradeSense AI")
    st.markdown('<span class="ts-pill">PREMIUM MARKET TERMINAL</span>',unsafe_allow_html=True)
    st.caption("Explainable AI • Market Intelligence")
    page=st.radio("WORKSPACE",[
        "🏠 Dashboard","📊 Market Analysis","🧠 Intelligence Score",
        "🚫 Why Not to Trade?","🌦️ Market Mood","🤖 AI Assistant",
        "⭐ Watchlist","📰 News & Sentiment","🧪 Strategy Builder",
        "📈 Backtesting","🧯 Strategy Stress Test","⚠️ Risk Analysis",
        "🔮 ML Prediction","🎯 Prediction Tracker","🎮 Paper Trading","⚙️ Settings"
    ],label_visibility="visible")
    st.markdown("---")
    selected_name=st.selectbox("Instrument",list(INSTRUMENTS.keys()))
    selected_symbol=INSTRUMENTS[selected_name]
    period_name=st.selectbox("Historical window",list(PERIODS.keys()),index=2)
    if st.button("↻ Refresh market data",use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    clock=now_ist()
    st.markdown(f'<div class="ts-card"><div class="ts-kicker">INDIA STANDARD TIME</div><div style="font-size:23px;font-weight:700;color:#f4fbff">{clock.strftime("%I:%M:%S %p")}</div><div class="ts-muted">{clock.strftime("%A, %d %B %Y")}</div></div>',unsafe_allow_html=True)
    st.caption("Provider: Yahoo Finance · Historical/delayed")
    st.caption("Upstox live integration: Pending")

# Refresh date/time shown on each rerun. Data date is separate.
needs_data=page not in ["📰 News & Sentiment","⭐ Watchlist","🎯 Prediction Tracker","⚙️ Settings","🎮 Paper Trading"]
raw=fetch_history(selected_symbol,PERIODS[period_name]) if needs_data else pd.DataFrame()
data=add_indicators(raw) if not raw.empty else pd.DataFrame()
latest,change=current_price_change(data) if not data.empty else (None,None)

# ---------------------------- HERO ----------------------------
st.markdown(f"""
<div class="ts-hero">
 <div class="ts-kicker">AI-POWERED MARKET INTELLIGENCE</div>
 <h1 style="margin:5px 0 2px 0;font-size:34px">TradeSense AI</h1>
 <div class="ts-sub">Your Personal AI Market Analyst & Trading Decision Support System</div>
 <div style="margin-top:14px"><span class="ts-pill">EXPLAINABLE ANALYSIS</span> &nbsp;
 <span class="ts-pill">RISK-AWARE INSIGHTS</span> &nbsp;
 <span class="ts-pill">HISTORICAL DATA MODE</span></div>
</div>
""",unsafe_allow_html=True)

st.caption(f"App clock: {now_ist().strftime('%d %b %Y, %I:%M:%S %p IST')} · This clock shows current app time; market candle date below shows the latest data date returned by the provider.")

# ---------------------------- PAGES ----------------------------
if page=="🏠 Dashboard":
    st.subheader("Market Overview")
    if data.empty:
        st.warning("Market data fetch nahi ho paaya. Internet connection, selected symbol ya Yahoo Finance availability check karein.")
    else:
        score,_=score_parts(data); mood,mood_detail=market_mood(data)
        k=st.columns(4)
        k[0].metric(selected_name,f"{latest:,.2f}",f"{change:+.2f}%")
        k[1].metric("Latest candle date",pd.to_datetime(data["Date"].iloc[-1]).strftime("%d %b %Y"))
        k[2].metric("Market mood",mood)
        k[3].metric("Intelligence score",f"{score}/100" if score is not None else "N/A")
        st.plotly_chart(price_chart(data,f"{selected_name} · Historical candlestick & EMA"),use_container_width=True)
        left,right=st.columns([1.35,1])
        with left:
            st.markdown("### AI Market Brief")
            st.markdown(market_summary(selected_name,data))
            st.markdown(f'<div class="ts-card"><b>Market mood</b><br>{mood}<div class="ts-muted">{mood_detail}</div></div>',unsafe_allow_html=True)
        with right:
            st.markdown("### Latest available candles")
            st.dataframe(data[["Date","Open","High","Low","Close","Volume"]].tail(6),hide_index=True,use_container_width=True)
        st.caption("Prices are historical/delayed provider data. 1 November 2026 is a Sunday, so a latest candle dated 30 October 2026 can be correct if it is the last available trading session.")

elif page=="📊 Market Analysis":
    st.subheader("Technical Analysis Lab")
    if data.empty: st.warning("No data available.")
    else:
        last=data.iloc[-1]; view=indicator_view(data)
        cols=st.columns(5)
        for col,label,val in zip(cols,["RSI 14","MACD","EMA 20","EMA 50","ATR 14"],
            [f"{last['RSI']:.2f}",f"{last['MACD']:.2f}",f"{last['EMA20']:.2f}",f"{last['EMA50']:.2f}",f"{last['ATR']:.2f}"]):
            col.metric(label,val)
        st.plotly_chart(price_chart(data,f"{selected_name} · Price trend"),use_container_width=True)
        sub=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.08,subplot_titles=("RSI (14)","MACD"))
        sub.add_trace(go.Scatter(x=data["Date"],y=data["RSI"],name="RSI"),row=1,col=1)
        sub.add_hline(y=70,line_dash="dash",line_color="#ff6878",row=1,col=1)
        sub.add_hline(y=30,line_dash="dash",line_color="#38dfa5",row=1,col=1)
        sub.add_trace(go.Scatter(x=data["Date"],y=data["MACD"],name="MACD"),row=2,col=1)
        sub.add_trace(go.Scatter(x=data["Date"],y=data["MACD_SIGNAL"],name="Signal"),row=2,col=1)
        sub.update_layout(template="plotly_dark",height=520,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#081827")
        st.plotly_chart(sub,use_container_width=True)
        st.markdown("### Indicator reasoning")
        for reason in view["reasons"]: st.write("• "+reason)

elif page=="🧠 Intelligence Score":
    st.subheader("Explainable Market Intelligence Score")
    if data.empty: st.warning("No data.")
    else:
        score,parts=score_parts(data)
        if score is None: st.warning("At least 55 candles recommended.")
        else:
            a,b=st.columns([1,1.4])
            with a:
                st.metric("Custom score",f"{score}/100")
                st.progress(score/100)
                st.caption("A rule-based analytical score, not probability of profit.")
            with b:
                st.markdown("### Score breakdown")
                st.bar_chart(pd.Series(parts,name="Component score"))
            st.info("Weights: Trend 30%, Momentum 30%, MACD 20%, Risk profile 20%. News sentiment is not included in this score in this version.")
            st.markdown(market_summary(selected_name,data))

elif page=="🚫 Why Not to Trade?":
    st.subheader("AI Guardrail · Why Not to Trade?")
    st.write("This module looks for warning conditions that may make a trade less attractive. It does not issue a guaranteed no-trade decision.")
    if data.empty: st.warning("No data.")
    else:
        warnings=why_not_trade(data)
        st.markdown('<div class="ts-card"><div class="ts-kicker">RISK CHECKLIST</div><h3>Conditions to review before acting</h3>',unsafe_allow_html=True)
        for w in warnings: st.warning(w)
        st.markdown("</div>",unsafe_allow_html=True)
        st.caption("Rule-based warnings using RSI, EMA/MACD agreement and ATR/price. This is a decision-support checklist, not personal financial advice.")

elif page=="🌦️ Market Mood":
    st.subheader("Market Regime & Mood Detection")
    if data.empty: st.warning("No data.")
    else:
        mood,detail=market_mood(data)
        st.markdown(f'<div class="ts-card"><div class="ts-kicker">CURRENT HISTORICAL REGIME ESTIMATE</div><h2>{mood}</h2><div class="ts-muted">{detail}</div></div>',unsafe_allow_html=True)
        rets=data["RET"].dropna()
        vol=rets.tail(20).std()*np.sqrt(252)*100 if len(rets)>20 else np.nan
        st.columns(3)[0].metric("20-session annualised volatility",f"{vol:.2f}%" if pd.notna(vol) else "N/A")
        st.columns(3)[1].metric("EMA trend",indicator_view(data)["trend"])
        st.columns(3)[2].metric("MACD momentum",indicator_view(data)["macd"])
        st.caption("Mood is classified by transparent rules in this version; it is not yet a trained regime-detection ML model.")

elif page=="🤖 AI Assistant":
    st.subheader("TradeSense AI Assistant")
    st.info("Current assistant uses transparent Python rules. OpenAI-powered conversation is a later optional integration.")
    if "messages" not in st.session_state: st.session_state.messages=[]
    for role,msg in st.session_state.messages:
        with st.chat_message(role): st.markdown(msg)
    prompt=st.chat_input("Ask about the selected stock, RSI, MACD, risk or trading...")
    if prompt:
        st.session_state.messages.append(("user",prompt))
        q=prompt.lower()
        if not data.empty and any(k in q for k in ["analyse","analyze","analysis","stock","market","trend","selected"]):
            ans=market_summary(selected_name,data)
        elif "rsi" in q: ans="RSI (Relative Strength Index) momentum ko 0–100 scale par measure karta hai. Common reference levels 70 aur 30 hain; RSI akela entry/exit signal nahi hai."
        elif "macd" in q: ans="MACD fast aur slow EMA ke difference ko signal line ke saath compare karta hai. Ye momentum context deta hai, guarantee nahi."
        elif "ema" in q: ans="EMA recent prices ko zyada weight deta hai. EMA 20 aur EMA 50 ka comparison trend context ke liye use hota hai."
        elif "why not" in q or "trade" in q: ans="Why Not to Trade page par RSI, trend-MACD disagreement aur ATR/price warnings check karein."
        elif "risk" in q: ans="Risk Analysis page par historical volatility, maximum drawdown aur downside volatility dekh sakte hain."
        else: ans="Main selected stock analysis, RSI, MACD, EMA, market mood, risk, backtesting aur Why Not to Trade explain kar sakta hoon."
        st.session_state.messages.append(("assistant",ans)); st.rerun()

elif page=="⭐ Watchlist":
    st.subheader("Personal Watchlist")
    add_name=st.selectbox("Add instrument to watchlist",list(INSTRUMENTS.keys()),key="watch_select")
    if st.button("＋ Add instrument"): add_watch(INSTRUMENTS[add_name]); st.success(f"{add_name} added.")
    items=get_watchlist()
    if items.empty: st.info("Your watchlist is empty.")
    else:
        for _,row in items.iterrows():
            sym=row["symbol"]; label=next((n for n,s in INSTRUMENTS.items() if s==sym),sym)
            hist=fetch_history(sym,"5d"); p,ch=current_price_change(hist)
            c1,c2,c3=st.columns([2,2,1])
            c1.write(f"**{label}**")
            c2.metric("Latest available close",f"{p:,.2f}" if p is not None else "N/A",f"{ch:+.2f}%" if ch is not None else None)
            if c3.button("Remove",key="remove_"+sym): remove_watch(sym); st.rerun()

elif page=="📰 News & Sentiment":
    st.subheader("Market News Radar")
    query=st.text_input("Company / market search",selected_name)
    if st.button("Fetch latest headlines"):
        with st.spinner("Loading news feed..."): news=fetch_news(query)
        if not news: st.warning("News feed unavailable. Try again later.")
        for item in news:
            st.markdown(f'<div class="ts-card"><b>{item["title"]}</b><div class="ts-muted">{item["source"]} · {item["date"]}</div><span class="ts-pill">{item["sentiment"]}</span><br><a href="{item["link"]}" target="_blank">Read original article ↗</a></div>',unsafe_allow_html=True)
        st.caption("Headline sentiment is keyword-based and may misclassify context, sarcasm or financial terminology. Verify original sources.")

elif page=="🧪 Strategy Builder":
    st.subheader("Strategy Workshop")
    st.write("Create a simple long-only RSI rule set. Save it for later testing.")
    with st.form("build_strategy"):
        name=st.text_input("Strategy name","RSI Mean Reversion")
        entry=st.slider("Enter when RSI is below",10,45,30)
        exit_level=st.slider("Exit when RSI is above",55,90,70)
        submit=st.form_submit_button("Save strategy")
    if submit:
        if entry>=exit_level: st.error("Entry threshold must be below exit threshold.")
        else: save_strategy(name,selected_symbol,entry,exit_level); st.success("Strategy saved.")
    con=connect_db(); saved=pd.read_sql_query("SELECT name,symbol,entry_rsi,exit_rsi,created_at FROM strategies ORDER BY id DESC",con); con.close()
    if not saved.empty: st.dataframe(saved,use_container_width=True,hide_index=True)

elif page=="📈 Backtesting":
    st.subheader("Historical Strategy Backtester")
    c1,c2=st.columns(2)
    entry=c1.slider("Buy when RSI below",10,45,30)
    exit_level=c2.slider("Sell when RSI above",55,90,70)
    capital=st.number_input("Starting virtual capital (₹)",min_value=1000,value=100000,step=5000)
    if st.button("Run historical backtest"):
        if data.empty: st.warning("No historical data.")
        elif entry>=exit_level: st.error("Buy threshold must be lower than sell threshold.")
        else:
            result=rsi_backtest(data,entry,exit_level,capital)
            if result is None: st.warning("Not enough candles.")
            else:
                a,b,c,d=st.columns(4)
                a.metric("Final value",f"₹{result['final']:,.2f}")
                b.metric("Total return",f"{result['return_pct']:.2f}%")
                c.metric("Completed trades",result["completed"])
                d.metric("Maximum drawdown",f"{result['max_dd']:.2f}%")
                st.line_chart(result["curve"].set_index("Date"))
                if result["trades"]: st.dataframe(pd.DataFrame(result["trades"]),use_container_width=True,hide_index=True)
                st.caption("Simplified long-only backtest: close-price execution, one position at a time, estimated 0.1% cost per transaction. It omits taxes, market impact and realistic order fills.")

elif page=="🧯 Strategy Stress Test":
    st.subheader("Strategy Stress Test · Compare Market Regimes")
    st.write("Test the same RSI rule on historical slices classified by a simple trend proxy. These slices are approximate regimes, not perfect market labels.")
    entry=st.slider("Entry RSI",10,45,30,key="stress_entry")
    exit_level=st.slider("Exit RSI",55,90,70,key="stress_exit")
    if st.button("Run stress test"):
        if data.empty or len(data)<100: st.warning("Choose a longer historical period with at least 100 candles.")
        elif entry>=exit_level: st.error("Entry must be lower than exit.")
        else:
            x=add_indicators(data).dropna(subset=["RSI","EMA20","EMA50"]).copy()
            x["Regime"]=np.where(x["EMA20"]>x["EMA50"],"EMA bullish slice","EMA bearish slice")
            results=[]
            for regime,part in x.groupby("Regime"):
                part=part.drop(columns=["Regime"])
                r=rsi_backtest(part,entry,exit_level,100000)
                if r: results.append({"Historical slice":regime,"Return %":round(r["return_pct"],2),"Max drawdown %":round(r["max_dd"],2),"Completed trades":r["completed"]})
            if results: st.dataframe(pd.DataFrame(results),use_container_width=True,hide_index=True)
            else: st.info("Not enough observations in each regime slice.")
    st.caption("Regime split is based on EMA20 vs EMA50. It is an educational stress test, not a statistically rigorous regime study.")

elif page=="⚠️ Risk Analysis":
    st.subheader("Risk & Volatility Lab")
    if data.empty: st.warning("No data.")
    else:
        ret=data["Close"].pct_change().dropna()
        vol=ret.std()*np.sqrt(252)*100 if len(ret)>2 else np.nan
        wealth=(1+ret).cumprod()
        dd=(wealth/wealth.cummax()-1)*100 if len(wealth) else pd.Series(dtype=float)
        downside=ret[ret<0]
        a,b,c,d=st.columns(4)
        a.metric("Annualised volatility",f"{vol:.2f}%" if pd.notna(vol) else "N/A")
        b.metric("Max drawdown",f"{dd.min():.2f}%" if len(dd) else "N/A")
        c.metric("Average daily return",f"{ret.mean()*100:.3f}%")
        d.metric("Downside volatility",f"{downside.std()*np.sqrt(252)*100:.2f}%" if len(downside)>1 else "N/A")
        fig=go.Figure(go.Scatter(x=data["Date"].iloc[1:],y=dd,fill="tozeroy",name="Drawdown"))
        fig.update_layout(template="plotly_dark",height=350,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="#081827",title="Historical drawdown")
        st.plotly_chart(fig,use_container_width=True)
        st.caption("Historical risk statistics are backward-looking and do not guarantee future outcomes.")

elif page=="🔮 ML Prediction":
    st.subheader("Experimental ML Direction Model")
    st.warning("Experimental next-session direction classifier. Not a price target or trading recommendation.")
    if st.button("Train and evaluate"):
        if data.empty: st.warning("No data.")
        else:
            x=add_indicators(data)
            x["Target"]=(x["Close"].shift(-1)>x["Close"]).astype(int)
            feats=["RSI","MACD","MACD_SIGNAL","EMA20","EMA50","ATR","RET"]
            x=x.replace([np.inf,-np.inf],np.nan).dropna(subset=feats+["Target"])
            if len(x)<120: st.warning("At least ~120 valid rows are recommended. Select a longer period.")
            else:
                split=int(len(x)*.8); train=x.iloc[:split]; test=x.iloc[split:]
                if train["Target"].nunique()<2 or test.empty: st.warning("Not enough class variety for evaluation.")
                else:
                    from sklearn.ensemble import RandomForestClassifier
                    from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score
                    model=RandomForestClassifier(n_estimators=150,max_depth=5,min_samples_leaf=4,random_state=42,class_weight="balanced")
                    model.fit(train[feats],train["Target"]); pred=model.predict(test[feats])
                    m1,m2,m3,m4=st.columns(4)
                    m1.metric("Accuracy",f"{accuracy_score(test['Target'],pred)*100:.1f}%")
                    m2.metric("Precision",f"{precision_score(test['Target'],pred,zero_division=0)*100:.1f}%")
                    m3.metric("Recall",f"{recall_score(test['Target'],pred,zero_division=0)*100:.1f}%")
                    m4.metric("F1",f"{f1_score(test['Target'],pred,zero_division=0)*100:.1f}%")
                    latest_row=x.iloc[[-1]][feats]
                    prob=model.predict_proba(latest_row)[0][list(model.classes_).index(1)]
                    st.metric("Model-estimated next-session upward probability",f"{prob*100:.1f}%")
                    st.caption("Chronological 80/20 split. A single split is not enough for robust validation; use walk-forward testing before making claims.")

elif page=="🎯 Prediction Tracker":
    st.subheader("Prediction Journal")
    st.write("Record a rule-based view with its reference price. This prototype does not yet automatically resolve outcomes.")
    if st.button("Record current analysis"):
        if data.empty: st.warning("No data.")
        else:
            v=indicator_view(data)
            view="Positive" if v["trend"]=="Bullish" and v["macd"]=="Positive" else "Negative" if v["trend"]=="Bearish" and v["macd"]=="Negative" else "Neutral"
            record_prediction(selected_symbol,view,latest); st.success(f"{view} view recorded at {latest:.2f}.")
    con=connect_db(); pred=pd.read_sql_query("SELECT * FROM predictions ORDER BY id DESC",con); con.close()
    if pred.empty: st.info("No predictions recorded.")
    else: st.dataframe(pred,use_container_width=True,hide_index=True)

elif page=="🎮 Paper Trading":
    st.subheader("Paper Trading Simulator")
    st.write("Practice with virtual orders only. No real money or broker order is involved.")
    if "paper_cash" not in st.session_state: st.session_state.paper_cash=100000.0
    if "paper_positions" not in st.session_state: st.session_state.paper_positions={}
    a,b=st.columns(2)
    a.metric("Virtual cash",f"₹{st.session_state.paper_cash:,.2f}")
    b.metric("Selected instrument reference price",f"₹{latest:,.2f}" if latest is not None else "N/A")
    qty=st.number_input("Quantity",min_value=1,value=1,step=1)
    if latest is not None:
        buy_cost=latest*qty
        c1,c2=st.columns(2)
        if c1.button("Buy (virtual)"):
            if buy_cost>st.session_state.paper_cash: st.error("Not enough virtual cash.")
            else:
                st.session_state.paper_cash-=buy_cost
                st.session_state.paper_positions[selected_symbol]=st.session_state.paper_positions.get(selected_symbol,0)+qty
                st.success("Virtual buy recorded.")
        if c2.button("Sell (virtual)"):
            held=st.session_state.paper_positions.get(selected_symbol,0)
            if qty>held: st.error("Virtual holdings insufficient.")
            else:
                st.session_state.paper_cash+=buy_cost
                st.session_state.paper_positions[selected_symbol]=held-qty
                st.success("Virtual sell recorded.")
    st.markdown("### Virtual holdings")
    if st.session_state.paper_positions: st.json(st.session_state.paper_positions)
    else: st.info("No virtual holdings yet. Note: simulator state is session-based and resets when session is cleared.")

elif page=="⚙️ Settings":
    st.subheader("System & Data Settings")
    st.markdown('<div class="ts-card"><b>Current provider</b><br>Yahoo Finance via yfinance — historical/delayed availability, not guaranteed real-time.</div>',unsafe_allow_html=True)
    st.markdown('<div class="ts-card"><b>Final provider</b><br>Upstox Analytics API / WebSocket — pending account verification and token setup.</div>',unsafe_allow_html=True)
    st.markdown('<div class="ts-card"><b>Current implemented logic</b><br>Technical indicators, custom score, Why Not to Trade rules, market mood rules, rule-based assistant, watchlist, RSS news, RSI strategy builder, simplified backtest, regime-slice stress test, risk metrics, experimental ML classifier, prediction journal and session-based paper trading.</div>',unsafe_allow_html=True)
    st.markdown("**Not yet production-grade:** automatic prediction outcome resolution, OpenAI-powered chat, FinBERT sentiment, robust walk-forward ML validation, durable cloud database, and Upstox live feed.")
    st.caption("Streamlit Cloud local SQLite storage may not be durable across restarts/redeployments. Use hosted database storage for production.")

st.markdown("---")
st.markdown('<div class="ts-muted">TradeSense AI · Educational decision-support prototype · Not investment advice · Data may be delayed</div>',unsafe_allow_html=True)
