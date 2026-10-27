import streamlit as st
import json
import urllib.request
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="Snowman Shark Finder Screener",
    page_icon="⛄",
    layout="wide",
)

# Refresh the screener every 5 minutes.
st_autorefresh(interval=300000, key="auto_refresh")

try:
    st.image("IMG_0166.jpeg", use_container_width=True)
except Exception:
    pass

st.title("⛄🦈 Snowman Shark Finder Screener")
st.caption(
    "1HR = entry timing  |  2HR + Daily agreement = swing direction"
)
st.markdown(
    "**Signal colors:** 🟢 Bullish breakout  |  🔵 Bullish trend  |  "
    "🟠 Bearish trend  |  🔴 Bearish breakdown  |  ⚪ No signal"
)


def send_email_alert(subject, body):
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = st.secrets["SENDER_EMAIL"]
        msg["To"] = st.secrets["ALERT_EMAIL"]
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(
                st.secrets["SENDER_EMAIL"],
                st.secrets["GMAIL_APP_PASSWORD"],
            )
            server.send_message(msg)
        return True
    except Exception as e:
        st.error("Email error: " + str(e))
        return False


def send_discord_alert(message):
    try:
        webhook_url = st.secrets.get("DISCORD_WEBHOOK_URL", "")
        if not webhook_url:
            return False

        payload = json.dumps({"content": message}).encode("utf-8")
        request = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except Exception as e:
        st.error("Discord error: " + str(e))
        return False


DEFAULT_STOCKS = (
    "NVDA,AMD,TSLA,AAPL,MSFT,AMZN,META,GOOGL,AVGO,MU,"
    "MRVL,ALAB,LLY,TER,LRCX,ASML,APP,GS,UNH,COST,"
    "SPOT,DELL,TSM,AMAT,MDB,QCOM,ARM,INTC,SMCI,ORCL,"
    "CRM,NFLX,PLTR,JPM,COIN,XOM,CRWD,CAT,BA,SNOW,"
    "RDDT,GOOG,BRK-B,WMT,HD,LOW,TGT,MCD,SBUX,NKE,"
    "DIS,UBER,LYFT,ABNB,BKNG,SHOP,NOW,PANW,ZS,NET,"
    "DDOG,SNPS,CDNS,KLAC,AMKR,ON,TXN,ADI,NXPI,HON,"
    "GE,RTX,LMT,NOC,DE,CMI,F,GM,BAC,WFC,"
    "C,MS,BLK,V,MA,PYPL,HOOD,SCHW,PFE,MRK,"
    "ABBV,JNJ,REGN,ISRG,AMGN,CVX,COP,SLB,TSCO,TMO"
)

stocks_input = st.text_area(
    "Stocks to scan (comma-separated)",
    value=DEFAULT_STOCKS,
    height=100,
)
stocks = list(
    dict.fromkeys(
        symbol.strip().upper()
        for symbol in stocks_input.split(",")
        if symbol.strip()
    )
)

col_scan, col_clear = st.columns(2)
with col_scan:
    if st.button("🔄 Scan Now"):
        st.rerun()
with col_clear:
    if st.button("Clear Cached Data"):
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=240, show_spinner=False)
def get_data(ticker, interval, period):
    """Download and normalize OHLCV data from Yahoo Finance."""
    try:
        data = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        needed = ["Open", "High", "Low", "Close", "Volume"]
        if not all(column in data.columns for column in needed):
            return None

        data = data[needed].dropna(subset=["Close"]).sort_index()
        if data.empty:
            return None
        return data
    except Exception:
        return None


def trend_state(data, timeframe, exclude_last=False):
    """
    Classify trend using EMA 9 and EMA 21.
    For 2HR, the hourly data is resampled and the newest bar is excluded
    to reduce the chance of using a still-forming candle.
    """
    if data is None or len(data) < 25:
        return "⚪ INSUFFICIENT DATA"

    frame = data.copy()
    if exclude_last and len(frame) > 25:
        frame = frame.iloc[:-1]

    close = frame["Close"].astype(float)
    if len(close) < 25:
        return "⚪ INSUFFICIENT DATA"

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    last_close = float(close.iloc[-1])

    if ema9.iloc[-1] > ema21.iloc[-1] and last_close > ema21.iloc[-1]:
        return "🟢 BULLISH CONTINUATION"
    if ema9.iloc[-1] < ema21.iloc[-1] and last_close < ema21.iloc[-1]:
        return "🔴 BEARISH CONTINUATION"
    return "🟡 MIXED / WAIT"


def daily_trend_state(data):
    """Use the latest completed daily candle where possible."""
    if data is None or len(data) < 25:
        return "⚪ INSUFFICIENT DATA"

    frame = data.copy()
    try:
        # During the regular New York trading day, today's daily candle
        # is still forming. Exclude it until 4:00 p.m. Eastern.
        now_et = datetime.now(ZoneInfo("America/New_York"))
        latest_date = pd.Timestamp(frame.index[-1]).date()
        if latest_date == now_et.date() and now_et.hour < 16 and len(frame) > 25:
            frame = frame.iloc[:-1]
    except Exception:
        pass

    return trend_state(frame, "Daily")


def analyze_stock(ticker):
    hourly = get_data(ticker, "1h", "3mo")
    if hourly is None or len(hourly) < 25:
        return None

    close = hourly["Close"].astype(float)
    high = hourly["High"].astype(float)
    low = hourly["Low"].astype(float)
    volume = hourly["Volume"].astype(float)

    price = float(close.iloc[-1])
    previous_high = float(high.iloc[-21:-1].max())
    previous_low = float(low.iloc[-21:-1].min())

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    avg_volume = float(volume.iloc[-21:-1].mean())
    current_volume = float(volume.iloc[-1])
    volume_ok = avg_volume > 0 and current_volume >= avg_volume * 1.2

    bullish_breakout = (
        price > previous_high
        and ema9.iloc[-1] > ema21.iloc[-1]
        and volume_ok
    )
    bearish_breakdown = (
        price < previous_low
        and ema9.iloc[-1] < ema21.iloc[-1]
        and volume_ok
    )
    bullish_trend = ema9.iloc[-1] > ema21.iloc[-1] and price > ema21.iloc[-1]
    bearish_trend = ema9.iloc[-1] < ema21.iloc[-1] and price < ema21.iloc[-1]

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = float(true_range.rolling(14).mean().iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        atr = max(price * 0.01, 0.01)

    if bullish_breakout:
        signal = "🟢 BULLISH BREAKOUT"
        entry = price
        entry_trigger = previous_high
        stop = entry - atr
        target1 = entry + atr
        target2 = entry + (2 * atr)
    elif bearish_breakdown:
        signal = "🔴 BEARISH BREAKDOWN"
        entry = price
        entry_trigger = previous_low
        stop = entry + atr
        target1 = entry - atr
        target2 = entry - (2 * atr)
    elif bullish_trend:
        signal = "🔵 BULLISH TREND"
        entry = price
        entry_trigger = float(ema9.iloc[-1])
        stop = entry - atr
        target1 = entry + atr
        target2 = entry + (2 * atr)
    elif bearish_trend:
        signal = "🟠 BEARISH TREND"
        entry = price
        entry_trigger = float(ema9.iloc[-1])
        stop = entry + atr
        target1 = entry - atr
        target2 = entry - (2 * atr)
    else:
        signal = "⚪ NO SIGNAL"
        entry = np.nan
        entry_trigger = np.nan
        stop = np.nan
        target1 = np.nan
        target2 = np.nan

    # Build the 2-hour candles from hourly candles.
    # Yahoo's hourly feed is used because a native 2-hour interval is not
    # consistently available. Drop the newest 2-hour bar to be conservative.
    two_hour = hourly.resample("2h", label="left", closed="left").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    two_hour = two_hour.dropna(subset=["Close"])
    two_hour_state = trend_state(two_hour, "2HR", exclude_last=True)

    # Derive daily candles from the already-downloaded hourly data. This avoids
    # a second Yahoo request for every ticker and helps reduce rate limiting.
    daily = hourly.resample("1D").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    ).dropna(subset=["Close"])
    daily_state = daily_trend_state(daily)

    if (
        "BULLISH CONTINUATION" in two_hour_state
        and "BULLISH CONTINUATION" in daily_state
    ):
        swing_setup = "🟢 BULLISH SWING WATCH"
    elif (
        "BEARISH CONTINUATION" in two_hour_state
        and "BEARISH CONTINUATION" in daily_state
    ):
        swing_setup = "🔴 BEARISH SWING WATCH"
    elif "INSUFFICIENT DATA" in two_hour_state or "INSUFFICIENT DATA" in daily_state:
        swing_setup = "⚪ NOT ENOUGH DATA"
    else:
        swing_setup = "🟡 WAIT — TIMEFRAMES MIXED"

    return {
        "Ticker": ticker,
        "Price": round(price, 2),
        "1HR Signal": signal,
        "2HR Trend": two_hour_state,
        "Daily Trend": daily_state,
        "🎯 SWING SIGNAL": swing_setup,
        "Entry Reference": round(entry, 2) if pd.notna(entry) else None,
        "Entry Trigger": round(entry_trigger, 2) if pd.notna(entry_trigger) else None,
        "Stop Loss (1 ATR)": round(stop, 2) if pd.notna(stop) else None,
        "Target 1 (1 ATR)": round(target1, 2) if pd.notna(target1) else None,
        "Target 2 (2 ATR)": round(target2, 2) if pd.notna(target2) else None,
        "Previous High": round(previous_high, 2),
        "Previous Low": round(previous_low, 2),
        "Volume Confirmed": "Yes" if volume_ok else "No",
    }


st.write(f"**Stocks loaded:** {len(stocks)}")
st.write(
    "Scanning 1HR signals, 2HR trend, and Daily trend. "
    "The screener refreshes automatically every 5 minutes."
)
st.caption(
    "How to use it: 1HR helps with timing; 2HR + Daily alignment creates a "
    "swing signal. A swing signal is not an automatic entry—check price action "
    "and risk before trading."
)

results = []
with st.spinner("Scanning stocks across timeframes..."):
    progress = st.progress(0)
    for i, ticker in enumerate(stocks):
        result = analyze_stock(ticker)
        if result:
            results.append(result)
        progress.progress((i + 1) / max(len(stocks), 1))
    progress.empty()

if results:
    df = pd.DataFrame(results)

    def priority(row):
        """Show bearish opportunities first, then bullish, then mixed/no signal."""
        swing = str(row["🎯 SWING SIGNAL"])
        signal = str(row["1HR Signal"])
        if "BEARISH SWING WATCH" in swing:
            return 0
        if "BEARISH BREAKDOWN" in signal:
            return 1
        if "BEARISH TREND" in signal:
            return 2
        if "BULLISH SWING WATCH" in swing:
            return 3
        if "BULLISH BREAKOUT" in signal:
            return 4
        if "BULLISH TREND" in signal:
            return 5
        if "WAIT" in swing or "MIXED" in swing:
            return 6
        return 7

    df["_Priority"] = df.apply(priority, axis=1)
    df = df.sort_values("_Priority").drop(columns=["_Priority"])

    # Alert only when a ticker's confirmed 1HR breakout/breakdown changes.
    current_signals = {
        row["Ticker"]: row["1HR Signal"]
        for _, row in df.iterrows()
        if "BULLISH BREAKOUT" in row["1HR Signal"]
        or "BEARISH BREAKDOWN" in row["1HR Signal"]
    }
    if "previous_discord_signals" not in st.session_state:
        st.session_state["previous_discord_signals"] = current_signals.copy()
    else:
        previous_signals = st.session_state["previous_discord_signals"]
        for ticker, signal in current_signals.items():
            if previous_signals.get(ticker) != signal:
                send_discord_alert(f"⛄🦈 Screener Alert: {ticker} — {signal}")
        st.session_state["previous_discord_signals"] = current_signals.copy()

        for idx, row in dataframe.iterrows():
        swing = str(row["🎯 SWING SIGNAL"])
        signal = str(row["1HR Signal"])
        two_hr = str(row["2HR Trend"])
        daily = str(row["Daily Trend"])

        # Bearish swing setups get light red.
        if "BEARISH SWING WATCH" in swing:
            background = "#fce8e8"

        # Bullish swing setups get light green.
        elif "BULLISH SWING WATCH" in swing:
            background = "#e6f4ea"

        # Mixed timeframes get yellow.
        elif "WAIT" in swing or "MIXED" in swing:
            background = "#fff3cd"

        # Other bearish signals get light red.
        elif (
            "BEARISH" in signal
            or "BEARISH" in two_hr
            or "BEARISH" in daily
        ):
            background = "#fce8e8"

        # Other bullish signals get light green.
        elif (
            "BULLISH" in signal
            or "BULLISH" in two_hr
            or "BULLISH" in daily
        ):
            background = "#e6f4ea"

        else:
            background = "#e9ecef"

        for column in dataframe.columns:
            styles.loc[idx, column] = (
                f"background-color: {background}; color: black;"
            )

        styles.loc[idx, "1HR Signal"] += " font-weight: bold;"
        styles.loc[idx, "🎯 SWING SIGNAL"] += " font-weight: bold;"

    return styles

    def style_table(dataframe):
        styles = pd.DataFrame("", index=dataframe.index, columns=dataframe.columns)
        for column in dataframe.columns:
            styles[column] = dataframe[column].map(
                lambda value: style_cell(value, column)
            )
        return styles

    st.subheader("📊 Live Screener Results")
    st.dataframe(
        df.style.apply(style_table, axis=None),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("🎯 Signal Summary")
    bullish = df["1HR Signal"].str.contains("BULLISH").sum()
    bearish = df["1HR Signal"].str.contains("BEARISH").sum()
    bullish_swings = df["🎯 SWING SIGNAL"].str.contains("BULLISH SWING WATCH").sum()
    bearish_swings = df["🎯 SWING SIGNAL"].str.contains("BEARISH SWING WATCH").sum()
    mixed = df["🎯 SWING SIGNAL"].str.contains("WAIT|MIXED", regex=True).sum()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("1HR Bullish", int(bullish))
    c2.metric("1HR Bearish", int(bearish))
    c3.metric("Bullish Swing Watches", int(bullish_swings))
    c4.metric("Bearish Swing Watches", int(bearish_swings))
    c5.metric("Mixed / Wait", int(mixed))

    st.info(
        "These are technical screening signals, not guaranteed entries or "
        "predictions. The 2HR and Daily columns are trend filters. Confirm "
        "the price action and manage risk before trading options."
    )
else:
    st.warning(
        "No stock data returned. Check your internet connection and ticker "
        "symbols, then try again."
    )

