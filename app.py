import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import sqlite3, os, re, requests
import xml.etree.ElementTree as ET

# -------------------- CONFIG --------------------
st.set_page_config(page_title="TradeSense AI", page_icon="📈", layout="wide")

DB_PATH = "tradesense.db"
DEFAULT_SYMBOLS = {
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
}
PERIODS = {"1 Month": "1mo", "3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y", "2 Years": "2y", "5 Years": "5y"}

# -------------------- STYLE --------------------
st.markdown("""
<style>
:root { --bg:#071321; --panel:#0e2033; --panel2:#122941; --cyan:#38bdf8; --muted:#91a8bd; }
.stApp {background:linear-gradient(135deg,#06111f 0%,#0a1c30 55%,#071321 100%); color:#e8f2fb;}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#0c2035,#071321); border-right:1px solid #1e3a54;}
h1,h2,h3 {color:#eaf6ff !important;}
p, label, .stMarkdown {color:#d4e4f1;}
div[data-testid="stMetric"] {background:linear-gradient(145deg,#122b43,#0c1e31); border:1px solid #1c3c57; padding:15px 17px; border-radius:14px;}
div[data-testid="stMetricLabel"] {color:#9bb5c9;}
div[data-testid="stMetricValue"] {color:#f2f9ff;}
.stButton>button {background:linear-gradient(90deg,#0284c7,#2563eb); color:white; border:0; border-radius:9px; font-weight:600;}
.stButton>button:hover {border:1px solid #7dd3fc; color:white;}
div[data-testid="stAlert"] {border-radius:12px;}
.small-muted {color:#91a8bd;font-size:0.85rem;}
.card {background:#0e2033;border:1px solid #1b3b55;border-radius:15px;padding:16px 18px;margin-bottom:10px;}
.badge {display:inline-block;padding:4px 10px;border-radius:20px;background:#123b55;color:#7dd3fc;font-size:0.8rem;}
hr {border-color:#1c3851;}
</style>
""", unsafe_allow_html=True)

# -------------------- DATABASE --------------------
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS watchlist
        (symbol TEXT PRIMARY KEY, added_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS predictions
        (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, created_at TEXT,
         horizon TEXT, prediction TEXT, reference_price REAL, actual_price REAL,
         status TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS strategies
        (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, symbol TEXT,
         buy_rsi REAL, sell_rsi REAL, created_at TEXT)""")
    con.commit()
    con.close()

init_db()

# -------------------- MARKET DATA --------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_history(symbol, period="6mo", interval="1d"):
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename_axis("Date").reset_index()
        needed = ["Open", "High", "Low", "Close", "Volume"]
        for c in needed:
            if c not in df.columns:
                return pd.DataFrame()
        for c in needed:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["Close"]).copy()
        return df
    except Exception:
        return pd.DataFrame()

def latest_price(df):
    if df.empty:
        return None, None
    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) > 1 else last
    change = ((last - prev) / prev * 100) if prev else 0
    return last, change

# -------------------- INDICATORS --------------------
def add_indicators(df):
    if df.empty:
        return df
    x = df.copy()
    close = x["Close"]
    x["EMA20"] = close.ewm(span=20, adjust=False).mean()
    x["EMA50"] = close.ewm(span=50, adjust=False).mean()
    x["SMA20"] = close.rolling(20).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI"] = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    x["MACD"] = ema12 - ema26
    x["MACD_SIGNAL"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_HIST"] = x["MACD"] - x["MACD_SIGNAL"]
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    x["BB_UPPER"] = mid + 2 * std
    x["BB_LOWER"] = mid - 2 * std
    prev_close = close.shift(1)
    tr = pd.concat([(x["High"]-x["Low"]), (x["High"]-prev_close).abs(),
                    (x["Low"]-prev_close).abs()], axis=1).max(axis=1)
    x["ATR"] = tr.rolling(14).mean()
    x["DailyReturn"] = close.pct_change()
    return x

def analyse_indicators(df):
    if df.empty or len(df) < 55:
        return {"trend":"Insufficient data","momentum":"Insufficient data","rsi":None,"macd":"Unavailable","reasons":["At least 55 candles are recommended for this analysis."]}
    last = df.iloc[-1]
    reasons=[]
    trend = "Bullish" if last["EMA20"] > last["EMA50"] else "Bearish"
    reasons.append("EMA 20 is above EMA 50." if trend=="Bullish" else "EMA 20 is below EMA 50.")
    rsi = float(last["RSI"]) if pd.notna(last["RSI"]) else None
    if rsi is not None:
        momentum = "Strong / overbought zone" if rsi >= 70 else "Weak / oversold zone" if rsi <= 30 else "Neutral momentum"
        reasons.append(f"RSI is {rsi:.1f}.")
    else:
        momentum="Unavailable"
    macd = "Positive" if last["MACD"] > last["MACD_SIGNAL"] else "Negative"
    reasons.append(f"MACD is {macd.lower()} relative to its signal line.")
    return {"trend":trend,"momentum":momentum,"rsi":rsi,"macd":macd,"reasons":reasons}

def intelligence_score(df):
    a = analyse_indicators(df)
    if a["rsi"] is None:
        return None, {}
    last = df.iloc[-1]
    trend_score = 80 if last["EMA20"] > last["EMA50"] else 35
    momentum_score = 75 if 45 <= a["rsi"] <= 65 else 55 if 30 < a["rsi"] < 70 else 30
    macd_score = 75 if a["macd"] == "Positive" else 35
    vol = df["DailyReturn"].tail(20).std() * np.sqrt(252) if df["DailyReturn"].tail(20).notna().sum() > 5 else np.nan
    risk_score = 70 if pd.notna(vol) and vol < 0.25 else 50 if pd.notna(vol) and vol < 0.45 else 25
    components = {"Trend":trend_score,"Momentum":momentum_score,"MACD":macd_score,"Risk":risk_score}
    score = round(trend_score*.30 + momentum_score*.30 + macd_score*.20 + risk_score*.20)
    return score, components

# -------------------- CHARTS --------------------
def candle_chart(df, title, indicators=True):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df["Date"], open=df["Open"], high=df["High"],
                                 low=df["Low"], close=df["Close"], name="Price"))
    if indicators:
        for col, name in [("EMA20","EMA 20"),("EMA50","EMA 50")]:
            if col in df:
                fig.add_trace(go.Scatter(x=df["Date"], y=df[col], mode="lines", name=name, line=dict(width=1.5)))
    fig.update_layout(template="plotly_dark", height=520, title=title,
                      xaxis_rangeslider_visible=False, paper_bgcolor="#0e2033",
                      plot_bgcolor="#0a1b2d", margin=dict(l=20,r=20,t=55,b=20),
                      legend=dict(orientation="h",y=1.02,x=0))
    return fig

def line_chart(df, title):
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=df["Date"],y=df["Close"],mode="lines",name="Close",line=dict(width=2)))
    fig.update_layout(template="plotly_dark",height=330,title=title,paper_bgcolor="#0e2033",
                      plot_bgcolor="#0a1b2d",margin=dict(l=20,r=20,t=50,b=20))
    return fig

# -------------------- EXPLANATION / CHAT --------------------
def market_explanation(symbol, df):
    a=analyse_indicators(df)
    if a["rsi"] is None:
        return "Is stock ke liye sufficient historical data available nahi hai."
    score, parts=intelligence_score(df)
    text=f"**{symbol} analysis:** Trend **{a['trend']}** hai. RSI **{a['rsi']:.1f}** hai, jo {a['momentum'].lower()} indicate karta hai. MACD signal **{a['macd']}** hai. "
    if score is not None:
        text += f"Custom Market Intelligence Score **{score}/100** hai. "
    text += "Ye historical indicators par based educational analysis hai; guaranteed prediction ya buy/sell advice nahi."
    return text

def chat_answer(question, symbol, df):
    q=question.lower()
    a=analyse_indicators(df)
    if any(k in q for k in ["analyse","analyze","analysis","market","stock","trend","reliance","tcs"]):
        return market_explanation(symbol,df)
    if "rsi" in q:
        return "RSI (Relative Strength Index) momentum indicator hai. Common interpretation: 70 se upar overbought zone aur 30 se neeche oversold zone. Ye akela buy/sell signal nahi hota."
    if "macd" in q:
        return "MACD do moving averages ke difference aur signal line se momentum ko study karta hai. MACD line signal line ke upar ho toh positive momentum ka indication ho sakta hai."
    if "ema" in q:
        return "EMA (Exponential Moving Average) recent prices ko zyada weight deta hai. EMA 20 aur EMA 50 ka comparison trend ko study karne mein help karta hai."
    if "risk" in q or "volatility" in q:
        return "Volatility price returns ke variation ko measure karti hai. High volatility ka matlab price movement zyada ho sakta hai; iska matlab direction predict hona nahi hai."
    if "backtest" in q:
        return "Backtesting historical data par predefined rules test karta hai. Ismein brokerage, slippage, look-ahead bias aur out-of-sample testing consider karna zaroori hai."
    return "Main RSI, MACD, EMA, trend, volatility, backtesting aur selected stock analysis samjha sakta hoon. Kisi stock ka analysis chahiye toh Market Analysis page use karo."

# -------------------- BACKTEST --------------------
def rsi_backtest(df, buy_rsi=30, sell_rsi=70, initial_capital=100000, cost_pct=0.001):
    x=add_indicators(df).dropna(subset=["RSI","Close"]).copy()
    if len(x)<30:
        return None, "Backtest ke liye sufficient data nahi hai."
    cash=float(initial_capital); units=0.0; trades=[]; equity=[]
    for _, row in x.iterrows():
        price=float(row["Close"]); rsi=float(row["RSI"])
        if units==0 and rsi < buy_rsi:
            units=(cash*(1-cost_pct))/price
            cash=0
            trades.append({"Date":row["Date"],"Action":"BUY","Price":price})
        elif units>0 and rsi > sell_rsi:
            cash=units*price*(1-cost_pct)
            units=0
            trades.append({"Date":row["Date"],"Action":"SELL","Price":price})
        equity.append(cash+units*price)
    final_value=cash+units*float(x["Close"].iloc[-1])
    curve=pd.Series(equity,index=x["Date"])
    ret=(final_value/initial_capital-1)*100
    peak=curve.cummax()
    dd=(curve/peak-1)*100
    completed=sum(1 for t in trades if t["Action"]=="SELL")
    result={"initial":initial_capital,"final":final_value,"return":ret,
            "trades":trades,"completed":completed,"max_dd":float(dd.min()) if len(dd) else 0,
            "curve":pd.DataFrame({"Date":x["Date"],"Equity":equity})}
    return result, None

# -------------------- ML --------------------
def train_direction_model(df):
    x=add_indicators(df).copy()
    x["Target"]=((x["Close"].shift(-1)/x["Close"]-1)>0).astype(int)
    features=["RSI","MACD","MACD_SIGNAL","EMA20","EMA50","ATR","DailyReturn"]
    x=x.replace([np.inf,-np.inf],np.nan).dropna(subset=features+["Target"])
    if len(x)<120:
        return None, "ML ke liye kam se kam ~120 valid historical rows chahiye."
    split=int(len(x)*0.8)
    train=x.iloc[:split]; test=x.iloc[split:]
    if train["Target"].nunique()<2 or test.empty:
        return None, "Available data mein dono target classes ya test rows nahi mile."
    from sklearn.ensemble import RandomForestClassifier
    model=RandomForestClassifier(n_estimators=150,max_depth=5,min_samples_leaf=4,
                                 random_state=42,class_weight="balanced")
    model.fit(train[features],train["Target"])
    pred=model.predict(test[features])
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    metrics={"accuracy":accuracy_score(test["Target"],pred),
             "precision":precision_score(test["Target"],pred,zero_division=0),
             "recall":recall_score(test["Target"],pred,zero_division=0),
             "f1":f1_score(test["Target"],pred,zero_division=0)}
    latest=x.iloc[[-1]][features]
    prob=float(model.predict_proba(latest)[0][1])
    return {"metrics":metrics,"prob_up":prob,"rows":len(x)}, None

# -------------------- WATCHLIST / PREDICTIONS --------------------
def watchlist_items():
    con=db(); rows=con.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC").fetchall(); con.close()
    return [r[0] for r in rows]

def add_watch(symbol):
    con=db(); con.execute("INSERT OR IGNORE INTO watchlist(symbol,added_at) VALUES(?,?)",
                          (symbol,datetime.now().isoformat(timespec="seconds"))); con.commit(); con.close()

def remove_watch(symbol):
    con=db(); con.execute("DELETE FROM watchlist WHERE symbol=?",(symbol,)); con.commit(); con.close()

def save_prediction(symbol,horizon,pred,price):
    con=db(); con.execute("""INSERT INTO predictions(symbol,created_at,horizon,prediction,reference_price,status)
        VALUES(?,?,?,?,?,'Pending')""",(symbol,datetime.now().isoformat(timespec="seconds"),horizon,pred,float(price)))
    con.commit(); con.close()

def get_predictions():
    con=db(); df=pd.read_sql_query("SELECT * FROM predictions ORDER BY id DESC",con); con.close(); return df

# -------------------- NEWS --------------------
@st.cache_data(ttl=900, show_spinner=False)
def get_news(query):
    try:
        url="https://news.google.com/rss/search"
        r=requests.get(url,params={"q":query+" stock market India","hl":"en-IN","gl":"IN","ceid":"IN:en"},
                       timeout=12,headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        root=ET.fromstring(r.content)
        items=[]
        for item in root.findall(".//item")[:15]:
            title=item.findtext("title","")
            link=item.findtext("link","")
            pub=item.findtext("pubDate","")
            source=item.find("source")
            source_name=source.text if source is not None else "News source"
            low=title.lower()
            positive=["profit","growth","surge","rises","rally","record","strong","gain","upgrade","beats"]
            negative=["loss","fall","falls","crash","decline","fraud","probe","weak","downgrade","misses"]
            p=sum(w in low for w in positive); n=sum(w in low for w in negative)
            sentiment="Positive" if p>n else "Negative" if n>p else "Neutral"
            items.append({"title":title,"link":link,"published":pub,"source":source_name,"sentiment":sentiment})
        return items
    except Exception:
        return []

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("# 📈 TradeSense AI")
    st.caption("Market intelligence • Learning • Analysis")
    st.markdown('<span class="badge">PROTOTYPE • HISTORICAL DATA MODE</span>',unsafe_allow_html=True)
    page=st.radio("NAVIGATION",[
        "🏠 Dashboard","📊 Market Analysis","🧠 AI Market Score","🤖 AI Chat",
        "⭐ Watchlist","📰 News & Sentiment","🧪 Strategy Builder",
        "📈 Backtesting","⚠️ Risk Analysis","🔮 ML Prediction","🎯 Prediction Tracker","⚙️ Settings"
    ])
    st.markdown("---")
    st.caption("Data provider: Yahoo Finance")
    st.caption("Upstox integration: Pending")

# Shared selection
with st.sidebar:
    chosen_name=st.selectbox("Selected instrument",list(DEFAULT_SYMBOLS.keys()))
    symbol=DEFAULT_SYMBOLS[chosen_name]
    period_label=st.selectbox("Historical period",list(PERIODS.keys()),index=2)

# Load data only for selected pages
needs_data = page not in ["📰 News & Sentiment","⚙️ Settings","⭐ Watchlist","🎯 Prediction Tracker"]
df_raw=get_history(symbol,PERIODS[period_label]) if needs_data else pd.DataFrame()
df=add_indicators(df_raw) if not df_raw.empty else pd.DataFrame()
price,change=latest_price(df) if not df.empty else (None,None)

# -------------------- HEADER --------------------
st.markdown("## TradeSense AI")
st.markdown("##### AI-Powered Market Intelligence & Trading Decision Support System")
st.markdown('<span class="badge">EDUCATIONAL DECISION-SUPPORT TOOL</span> &nbsp; <span class="small-muted">Market data may be delayed or unavailable.</span>',unsafe_allow_html=True)

if page=="🏠 Dashboard":
    st.markdown("### Market Overview")
    if df.empty:
        st.warning("Market data abhi fetch nahi ho pa raha. Internet, symbol availability aur Yahoo Finance service check karo.")
    else:
        c1,c2,c3,c4=st.columns(4)
        c1.metric(chosen_name,f"{price:,.2f}",f"{change:+.2f}%")
        c2.metric("Latest Close Date",pd.to_datetime(df["Date"].iloc[-1]).strftime("%d %b %Y"))
        c3.metric("RSI (14)",f"{df['RSI'].iloc[-1]:.1f}" if pd.notna(df["RSI"].iloc[-1]) else "N/A")
        score,_=intelligence_score(df); c4.metric("Intelligence Score",f"{score}/100" if score is not None else "N/A")
        st.plotly_chart(candle_chart(df,f"{chosen_name} • Candlestick & EMA"),use_container_width=True)
        left,right=st.columns([1.3,1])
        with left:
            st.markdown("### Market Snapshot")
            a=analyse_indicators(df)
            st.write(f"**Trend:** {a['trend']}  ·  **Momentum:** {a['momentum']}  ·  **MACD:** {a['macd']}")
            st.markdown(market_explanation(chosen_name,df))
        with right:
            st.markdown("### Latest Historical Data")
            st.dataframe(df[["Date","Open","High","Low","Close","Volume"]].tail(7),use_container_width=True,hide_index=True)
    st.caption("Dashboard prices are latest available historical candles from Yahoo Finance, not guaranteed live quotes.")

elif page=="📊 Market Analysis":
    st.markdown("### Technical Market Analysis")
    if df.empty: st.warning("Data unavailable for selected instrument.")
    else:
        a=analyse_indicators(df); last=df.iloc[-1]
        cols=st.columns(4)
        cols[0].metric("RSI (14)",f"{last['RSI']:.2f}" if pd.notna(last["RSI"]) else "N/A")
        cols[1].metric("MACD",f"{last['MACD']:.2f}" if pd.notna(last["MACD"]) else "N/A")
        cols[2].metric("EMA 20",f"{last['EMA20']:.2f}" if pd.notna(last["EMA20"]) else "N/A")
        cols[3].metric("EMA 50",f"{last['EMA50']:.2f}" if pd.notna(last["EMA50"]) else "N/A")
        st.plotly_chart(candle_chart(df,f"{chosen_name} • Price, EMA 20 & EMA 50"),use_container_width=True)
        fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.08,row_heights=[.5,.5],
                          subplot_titles=("RSI","MACD"))
        fig.add_trace(go.Scatter(x=df["Date"],y=df["RSI"],name="RSI"),row=1,col=1)
        fig.add_hline(y=70,line_dash="dash",line_color="red",row=1,col=1); fig.add_hline(y=30,line_dash="dash",line_color="green",row=1,col=1)
        fig.add_trace(go.Scatter(x=df["Date"],y=df["MACD"],name="MACD"),row=2,col=1)
        fig.add_trace(go.Scatter(x=df["Date"],y=df["MACD_SIGNAL"],name="Signal"),row=2,col=1)
        fig.update_layout(template="plotly_dark",height=520,paper_bgcolor="#0e2033",plot_bgcolor="#0a1b2d")
        st.plotly_chart(fig,use_container_width=True)
        st.markdown("### Indicator interpretation")
        for reason in a["reasons"]: st.write("• "+reason)

elif page=="🧠 AI Market Score":
    st.markdown("### Explainable Market Intelligence Score")
    if df.empty: st.warning("Data unavailable.")
    else:
        score,parts=intelligence_score(df)
        if score is None: st.warning("Not enough data to calculate score.")
        else:
            st.metric("Custom Intelligence Score",f"{score}/100")
            st.progress(score/100)
            st.caption("Score is a custom rule-based indicator, not a probability of profit.")
            st.bar_chart(pd.Series(parts,name="Score"))
            st.markdown(market_explanation(chosen_name,df))
            st.markdown("**Scoring weights:** Trend 30%, Momentum 30%, MACD 20%, Risk 20%. News sentiment is not included in this score yet.")

elif page=="🤖 AI Chat":
    st.markdown("### Market Assistant")
    st.info("Current version: rule-based educational assistant. LLM integration can be added later using a protected API key.")
    if "chat_history" not in st.session_state: st.session_state.chat_history=[]
    for role,msg in st.session_state.chat_history:
        with st.chat_message(role): st.markdown(msg)
    prompt=st.chat_input("Ask about RSI, MACD, trend, risk, backtesting...")
    if prompt:
        st.session_state.chat_history.append(("user",prompt))
        answer=chat_answer(prompt,chosen_name,df) if not df.empty else "Selected instrument ka market data abhi available nahi hai. Main RSI, MACD, EMA jaise general concepts explain kar sakta hoon."
        st.session_state.chat_history.append(("assistant",answer))
        st.rerun()

elif page=="⭐ Watchlist":
    st.markdown("### Your Watchlist")
    name_to_symbol=DEFAULT_SYMBOLS
    add_name=st.selectbox("Add instrument",list(name_to_symbol.keys()),key="watch_add")
    if st.button("＋ Add to Watchlist"): add_watch(name_to_symbol[add_name]); st.success(f"{add_name} added.")
    items=watchlist_items()
    if not items: st.info("Watchlist empty hai. Upar se instruments add karo.")
    for item in items:
        label=next((k for k,v in name_to_symbol.items() if v==item),item)
        hist=get_history(item,"5d")
        p,ch=latest_price(hist)
        c1,c2,c3=st.columns([2,2,1])
        c1.write(f"**{label}**")
        c2.metric("Latest available close",f"{p:,.2f}" if p is not None else "N/A",f"{ch:+.2f}%" if ch is not None else None)
        if c3.button("Remove",key="rm_"+item): remove_watch(item); st.rerun()

elif page=="📰 News & Sentiment":
    st.markdown("### Market News & Headline Sentiment")
    query=st.text_input("Search company / market",value=chosen_name)
    if st.button("Fetch News") or query:
        with st.spinner("Fetching news RSS..."): news=get_news(query)
        if not news: st.warning("News feed unavailable. Try again later.")
        for item in news:
            st.markdown(f'<div class="card"><b>{item["title"]}</b><br><span class="small-muted">{item["source"]} · {item["published"]}</span><br><span class="badge">{item["sentiment"]}</span><br><a href="{item["link"]}" target="_blank">Read article ↗</a></div>',unsafe_allow_html=True)
        st.caption("Headline sentiment is a simple keyword-based estimate, not a trained financial NLP model. Verify the original article.")

elif page=="🧪 Strategy Builder":
    st.markdown("### Build a Rule-Based RSI Strategy")
    st.write("Create a simple long-only strategy and save its parameters.")
    with st.form("strategy_form"):
        strategy_name=st.text_input("Strategy name","My RSI Strategy")
        buy_rsi=st.slider("Entry when RSI is below",10,45,30)
        sell_rsi=st.slider("Exit when RSI is above",55,90,70)
        submitted=st.form_submit_button("Save Strategy")
    if submitted:
        if buy_rsi>=sell_rsi: st.error("Entry RSI must be lower than exit RSI.")
        else:
            con=db(); con.execute("INSERT INTO strategies(name,symbol,buy_rsi,sell_rsi,created_at) VALUES(?,?,?,?,?)",
                                  (strategy_name,symbol,buy_rsi,sell_rsi,datetime.now().isoformat(timespec="seconds")))
            con.commit(); con.close(); st.success("Strategy saved.")
    con=db(); saved=pd.read_sql_query("SELECT name,symbol,buy_rsi,sell_rsi,created_at FROM strategies ORDER BY id DESC",con); con.close()
    if not saved.empty: st.dataframe(saved,use_container_width=True,hide_index=True)

elif page=="📈 Backtesting":
    st.markdown("### Historical Strategy Backtesting")
    b1,b2=st.columns(2)
    with b1: entry=st.slider("Buy when RSI below",10,45,30)
    with b2: exitv=st.slider("Sell when RSI above",55,90,70)
    capital=st.number_input("Initial capital (₹)",min_value=1000,value=100000,step=5000)
    if st.button("Run Backtest"):
        if entry>=exitv: st.error("Buy RSI must be lower than sell RSI.")
        elif df.empty: st.warning("Market data unavailable.")
        else:
            result,error=rsi_backtest(df,entry,exitv,capital)
            if error: st.warning(error)
            else:
                m1,m2,m3,m4=st.columns(4)
                m1.metric("Final Portfolio Value",f"₹{result['final']:,.2f}")
                m2.metric("Total Return",f"{result['return']:.2f}%")
                m3.metric("Completed Trades",result["completed"])
                m4.metric("Max Drawdown",f"{result['max_dd']:.2f}%")
                st.line_chart(result["curve"].set_index("Date"))
                if result["trades"]: st.dataframe(pd.DataFrame(result["trades"]),use_container_width=True,hide_index=True)
                st.caption("Illustrative backtest: long-only, one position at a time, close-price execution, estimated 0.1% cost per transaction. Not a live strategy recommendation.")

elif page=="⚠️ Risk Analysis":
    st.markdown("### Historical Risk Analysis")
    if df.empty: st.warning("Data unavailable.")
    else:
        returns=df["Close"].pct_change().dropna()
        ann_vol=returns.std()*np.sqrt(252)*100 if len(returns)>2 else np.nan
        cumulative=(1+returns).cumprod()
        drawdown=(cumulative/cumulative.cummax()-1)*100 if len(cumulative) else pd.Series(dtype=float)
        downside=returns[returns<0]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Annualised Volatility",f"{ann_vol:.2f}%" if pd.notna(ann_vol) else "N/A")
        c2.metric("Maximum Drawdown",f"{drawdown.min():.2f}%" if len(drawdown) else "N/A")
        c3.metric("Average Daily Return",f"{returns.mean()*100:.3f}%")
        c4.metric("Downside Volatility",f"{downside.std()*np.sqrt(252)*100:.2f}%" if len(downside)>1 else "N/A")
        fig=go.Figure(); fig.add_trace(go.Scatter(x=df["Date"].iloc[1:],y=drawdown,fill="tozeroy",name="Drawdown"))
        fig.update_layout(template="plotly_dark",height=350,title="Historical Drawdown",paper_bgcolor="#0e2033",plot_bgcolor="#0a1b2d")
        st.plotly_chart(fig,use_container_width=True)
        st.caption("Historical risk measures describe past price behaviour and do not guarantee future risk.")

elif page=="🔮 ML Prediction":
    st.markdown("### Experimental ML Direction Model")
    st.warning("This model estimates next-candle direction from historical indicators. It is experimental and not a price target.")
    if st.button("Train & Evaluate Model"):
        if df.empty: st.warning("Data unavailable.")
        else:
            with st.spinner("Training time-ordered Random Forest model..."):
                result,error=train_direction_model(df)
            if error: st.warning(error)
            else:
                m=result["metrics"]
                a,b,c,d=st.columns(4)
                a.metric("Test Accuracy",f"{m['accuracy']*100:.1f}%")
                b.metric("Precision",f"{m['precision']*100:.1f}%")
                c.metric("Recall",f"{m['recall']*100:.1f}%")
                d.metric("F1 Score",f"{m['f1']*100:.1f}%")
                st.metric("Model-estimated next-candle upward probability",f"{result['prob_up']*100:.1f}%")
                st.caption(f"Valid rows: {result['rows']}. Time-ordered 80/20 split. Past test performance does not guarantee future performance.")

elif page=="🎯 Prediction Tracker":
    st.markdown("### Prediction History")
    st.write("Current version records a rule-based directional view and its reference price. Actual outcome is pending until later price data is checked.")
    if st.button("Record current indicator view"):
        hist=get_history(symbol,"6mo")
        if not hist.empty:
            ind=add_indicators(hist); a=analyse_indicators(ind)
            pred="Positive" if a["trend"]=="Bullish" and a["macd"]=="Positive" else "Negative" if a["trend"]=="Bearish" and a["macd"]=="Negative" else "Neutral"
            save_prediction(symbol,"Next available daily candle",pred,float(hist["Close"].iloc[-1]))
            st.success(f"Recorded {pred} view for {chosen_name}.")
    pred_df=get_predictions()
    if pred_df.empty: st.info("No predictions recorded yet.")
    else: st.dataframe(pred_df,use_container_width=True,hide_index=True)

elif page=="⚙️ Settings":
    st.markdown("### Project Settings & Data Status")
    st.markdown('<div class="card"><b>Current market data provider</b><br>Yahoo Finance (yfinance) — historical / delayed availability; not guaranteed real-time.</div>',unsafe_allow_html=True)
    st.markdown('<div class="card"><b>Final provider</b><br>Upstox Analytics API — integration pending token and endpoint validation.</div>',unsafe_allow_html=True)
    st.markdown('<div class="card"><b>Storage</b><br>SQLite local database: watchlist, saved strategies, prediction records.</div>',unsafe_allow_html=True)
    st.markdown("**Implemented now:** historical market data, technical indicators, custom score, rule-based chat, watchlist, RSS news headlines, RSI strategy builder, backtesting, historical risk metrics, experimental ML model, prediction logging.")
    st.markdown("**Still dependent on external integration:** Upstox market feed / WebSocket and any guaranteed real-time feed. OpenAI-powered conversational responses also require an OpenAI API key and are not enabled in this build.")
    st.caption("If deployed to Streamlit Community Cloud, local SQLite persistence may not be durable across app restarts/redeployments. Use a hosted database for production persistence.")

st.markdown("---")
st.markdown('<div class="small-muted">TradeSense AI · Educational decision-support prototype · Not investment advice · Data may be delayed</div>',unsafe_allow_html=True)
