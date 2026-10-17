import streamlit as st
import json
import urllib.request

import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import smtplib
import ssl
from email.message import EmailMessage
st.set_page_config(
    page_title="Dual Breakout Screener",
    page_icon="📈",
    layout="wide"
)

# Refresh and rescan every 5 minutes
st_autorefresh(interval=300000, key="auto_refresh")
st.image("IMG_0166.jpeg", use_container_width=True)
st.title("⛄🦈 Snowman Shark Finder Screener")
st.caption("Green = Bullish | Red = Bearish | Yellow = Watch")
def send_email_alert(subject, body):
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = st.secrets["SENDER_EMAIL"]
        msg["To"] = st.secrets["ALERT_EMAIL"]
        msg.set_content(body)

        context = ssl.create_default_context()

        with smtplib.SMTP_SSL(
            "smtp.gmail.com", 465, context=context
        ) as server:
            server.login(
                st.secrets["SENDER_EMAIL"],
                st.secrets["GMAIL_APP_PASSWORD"]
            )
            server.send_message(msg)

        return True

    except Exception as e:
        st.error(f"Email alert failed: {e}")
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

    except Exception:
        return False
if st.button("Test Discord Alert"):
    if send_discord_alert("Discord test successful! Your screener is connected."):
        st.success("Discord alert sent successfully!")
    else:
        st.error("Discord alert failed. Check your Secrets settings.")
DEFAULT_STOCKS = (
    "NVDA,AMD,TSLA,AAPL,MSFT,AMZN,META,GOOGL,AVGO,MU,"
    "MRVL,ALAB,LLY,TER,LRCX,ASML,APP,GS,UNH,COST,SPOT,"
    "DELL,TSM,AMAT,KLAC,QCOM,ARM,INTC,SMCI,ORCL,CRM,"
    "NFLX,PLTR,JPM,COIN,HOOD,UBER,CAT,BA,XOM"
)

stocks_input = st.text_area(
    "Stocks to scan (comma-separated)",
    value=DEFAULT_STOCKS,
    height=100
)

stocks = list(dict.fromkeys(
    s.strip().upper()
    for s in stocks_input.split(",")
    if s.strip()
))

if st.button("🔄 Scan Now"):
    st.rerun()


@st.cache_data(ttl=240, show_spinner=False)
def get_data(ticker):
    try:
        data = yf.download(
            ticker,
            period="3mo",
            interval="1h",
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        data = data.dropna(subset=["Close"])

        if len(data) < 25:
            return None

        return data

    except Exception:
        return None


def analyze_stock(ticker):
    data = get_data(ticker)

    if data is None:
        return None

    close = data["Close"].astype(float)
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    volume = data["Volume"].astype(float)

    price = float(close.iloc[-1])
    previous_low_value = float(low.iloc[-21:-1].min())
    previous_high_value = float(high.iloc[-21:-1].max())

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    previous_high = float(high.iloc[-21:-1].max())
    previous_low = float(low.iloc[-21:-1].min())

    avg_volume = float(volume.iloc[-21:-1].mean())
    current_volume = float(volume.iloc[-1])

    volume_ok = (
        avg_volume > 0
        and current_volume >= avg_volume * 1.2
    )

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

    bullish_trend = (
        ema9.iloc[-1] > ema21.iloc[-1]
        and price > ema21.iloc[-1]
    )

    bearish_trend = (
        ema9.iloc[-1] < ema21.iloc[-1]
        and price < ema21.iloc[-1]
    )

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
        signal = "🟢 BULLISH TREND"
        entry = price
        entry_trigger = float(ema9.iloc[-1])
        stop = entry - atr
        target1 = entry + atr
        target2 = entry + (2 * atr)

    elif bearish_trend:
        signal = "🔴 BEARISH TREND"
        entry = price
        entry_trigger = float(ema9.iloc[-1])
        stop = entry + atr
        target1 = entry - atr
        target2 = entry - (2 * atr)

    else:
        signal = "🟡 WATCH / NO CONFIRMATION"
        entry = np.nan
        entry_trigger = np.nan
        stop = np.nan
        target1 = np.nan
        target2 = np.nan

    return {
        "Ticker": ticker,
        "Price": round(price, 2),
        "Signal": signal,
               "Action": (
            "🟢 BREAKOUT CONFIRMED — REVIEW ENTRY"
            if "BULLISH BREAKOUT" in signal
            else "🔴 BREAKDOWN CONFIRMED — REVIEW ENTRY"
            if "BEARISH BREAKDOWN" in signal
            else "🟢 BULLISH TREND — WATCH ENTRY"
            if "BULLISH TREND" in signal
            else "🔴 BEARISH TREND — WATCH ENTRY"
            if "BEARISH TREND" in signal
            else "🟡 WAIT — NO CLEAR SETUP"
        ),
        "Entry Reference": round(entry, 2) if pd.notna(entry) else None,
        "Entry Trigger": round(entry_trigger, 2) if pd.notna(entry_trigger) else None,
        "Stop Loss (1 ATR)": round(stop, 2) if pd.notna(stop) else None,
        "Target 1 (1 ATR)": round(target1, 2) if pd.notna(target1) else None,
        "Target 2 (2 ATR)": round(target2, 2) if pd.notna(target2) else None,
        "Previous High": round(previous_high, 2),
        "Previous Low": round(previous_low, 2),       
        "Volume Confirmed": "Yes" if volume_ok else "No"
    }


if st.button("Clear Cached Data"):
    st.cache_data.clear()
    st.rerun()

st.write(f"**Stocks loaded:** {len(stocks)}")
st.write("Scanning hourly candles. Refreshing automatically every 5 minutes.")

results = []

with st.spinner("Scanning stocks..."):
    progress = st.progress(0)

    for i, ticker in enumerate(stocks):
        result = analyze_stock(ticker)

        if result:
            results.append(result)

        progress.progress((i + 1) / max(len(stocks), 1))

    progress.empty()

if results:
    df = pd.DataFrame(results)
        # Send alerts for new confirmed breakouts and breakdowns
    current_signals = {
        row["Ticker"]: row["Signal"]
        for _, row in df.iterrows()
        if "BULLISH BREAKOUT" in row["Signal"]
        or "BEARISH BREAKDOWN" in row["Signal"]
    }

    if "previous_discord_signals" not in st.session_state:
        st.session_state["previous_discord_signals"] = current_signals.copy()
    else:
        previous_signals = st.session_state["previous_discord_signals"]

        for ticker, signal in current_signals.items():
            if previous_signals.get(ticker) != signal:
                send_discord_alert(
                    f"📈 Screener Alert: {ticker} — {signal}"
                )

        st.session_state["previous_discord_signals"] = current_signals.copy()

    def color_signal(row):
        signal = row["Signal"]

        if "BREAKOUT" in signal or "BULLISH TREND" in signal:
            color = "#d4edda"
        elif "BREAKDOWN" in signal or "BEARISH TREND" in signal:
            color = "#f8d7da"
        else:
            color = "#fff3cd"

        return [f"background-color: {color}"] * len(row)

    st.subheader("📊 Live Screener Results")

    st.dataframe(
        df.style.apply(color_signal, axis=1),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("🎯 Signal Summary")

    bullish = df["Signal"].str.contains("BULLISH").sum()
    bearish = df["Signal"].str.contains("BEARISH").sum()
    watch = df["Signal"].str.contains("WATCH").sum()

    col1, col2, col3 = st.columns(3)

    col1.metric("Bullish Setups", int(bullish))
    col2.metric("Bearish Setups", int(bearish))
    col3.metric("Watch", int(watch))

    st.info(
        "Important: These are technical screening signals, not guaranteed "
        "entries. Confirm the price action and risk before trading options."
    )

else:
    st.warning(
        "No stock data returned. Check your internet connection and "
        "the ticker symbols, then try again."
    )
    


