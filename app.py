import streamlit as st
import json
import urllib.request
import smtplib
import ssl
import hmac
from email.message import EmailMessage
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh


# ============================================================
# PAGE SETTINGS
# ============================================================

st.set_page_config(
    page_title="Snowman Shark Finder Screener",
    page_icon="⛄",
    layout="wide",
)

st_autorefresh(interval=300000, key="auto_refresh")

try:
    st.image("IMG_0166.jpeg", use_container_width=True)
except Exception:
    pass

st.title("⛄🦈 Snowman Shark Finder Screener")

st.caption(
    "1HR = Entry Timing | 2HR + Daily Agreement = Swing Direction"
)

st.markdown(
    "**Signal colors:** 🟢 Bullish Breakout | 🔵 Bullish Trend | "
    "🟠 Bearish Trend | 🔴 Bearish Breakdown | ⚪ No Signal"
)


# ============================================================
# ALERT FUNCTIONS
# ============================================================

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

        payload = json.dumps(
            {"content": message}
        ).encode("utf-8")

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


# ============================================================
# STOCK LIST
# ============================================================

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
    "ABBV,JNJ,spx,ISRG,AMGN,CVX,COP,SLB,TSCO,TMO"
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


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(ttl=240, show_spinner=False)
def get_data(ticker, interval, period):

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

        needed = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(column in data.columns for column in needed):
            return None

        data = data[needed].dropna(
            subset=["Close"]
        ).sort_index()

        if data.empty:
            return None

        return data

    except Exception:
        return None


# ============================================================
# TREND CLASSIFICATION
# ============================================================

def trend_state(data, timeframe, exclude_last=False):

    if data is None or len(data) < 25:
        return "⚪ INSUFFICIENT DATA"

    frame = data.copy()

    if exclude_last and len(frame) > 25:
        frame = frame.iloc[:-1]

    close = frame["Close"].astype(float)

    if len(close) < 25:
        return "⚪ INSUFFICIENT DATA"

    ema9 = close.ewm(
        span=9,
        adjust=False
    ).mean()

    ema21 = close.ewm(
        span=21,
        adjust=False
    ).mean()

    last_close = float(close.iloc[-1])

    if (
        ema9.iloc[-1] > ema21.iloc[-1]
        and last_close > ema21.iloc[-1]
    ):
        return "🟢 BULLISH CONTINUATION"

    if (
        ema9.iloc[-1] < ema21.iloc[-1]
        and last_close < ema21.iloc[-1]
    ):
        return "🔴 BEARISH CONTINUATION"

    return "🟡 MIXED / WAIT"


# ============================================================
# DAILY TREND
# Uses actual completed daily candles.
# 1HR AND 2HR CALCULATIONS ARE NOT CHANGED.
# ============================================================

def daily_trend_state(data):

    if data is None or len(data) < 25:
        return "⚪ INSUFFICIENT DATA"

    frame = data.copy()

    try:
        now_et = datetime.now(
            ZoneInfo("America/New_York")
        )

        latest_date = pd.Timestamp(
            frame.index[-1]
        ).date()

        if (
            latest_date == now_et.date()
            and now_et.hour < 16
            and len(frame) > 25
        ):
            frame = frame.iloc[:-1]

    except Exception:
        pass

    return trend_state(frame, "Daily")


# ============================================================
# MAIN STOCK ANALYSIS
# ============================================================

def analyze_stock(ticker):

    hourly = get_data(ticker, "1h", "3mo")

    if hourly is None or len(hourly) < 25:
        return None

    close = hourly["Close"].astype(float)
    high = hourly["High"].astype(float)
    low = hourly["Low"].astype(float)
    volume = hourly["Volume"].astype(float)

    price = float(close.iloc[-1])

    previous_high = float(
        high.iloc[-21:-1].max()
    )

    previous_low = float(
        low.iloc[-21:-1].min()
    )

    ema9 = close.ewm(
        span=9,
        adjust=False
    ).mean()

    ema21 = close.ewm(
        span=21,
        adjust=False
    ).mean()

    avg_volume = float(
        volume.iloc[-21:-1].mean()
    )

    current_volume = float(
        volume.iloc[-1]
    )

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

    atr = float(
        true_range.rolling(14).mean().iloc[-1]
    )

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

    # --------------------------------------------------------
    # 2HR CALCULATION - PRESERVED
    # --------------------------------------------------------

    two_hour = hourly.resample(
        "2h",
        label="left",
        closed="left"
    ).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )

    two_hour = two_hour.dropna(
        subset=["Close"]
    )

    two_hour_state = trend_state(
        two_hour,
        "2HR",
        exclude_last=True
    )

    # --------------------------------------------------------
    # DAILY CALCULATION - UPDATED
    # Uses actual daily Yahoo Finance candles.
    # --------------------------------------------------------

    daily = get_data(
        ticker,
        "1d",
        "6mo"
    )

    daily_state = daily_trend_state(daily)

    # --------------------------------------------------------
    # SWING AGREEMENT
    # --------------------------------------------------------

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

    elif (
        "INSUFFICIENT DATA" in two_hour_state
        or "INSUFFICIENT DATA" in daily_state
    ):

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


# ============================================================
# PRIVATE CLOSE-8 REVERSAL SCAN
# ============================================================

def analyze_close8_reversal(ticker):

    daily = get_data(
        ticker,
        "1d",
        "6mo"
    )

    if daily is None or len(daily) < 10:
        return None

    frame = daily.copy()

    # Remove today's incomplete daily candle.
    try:
        now_et = datetime.now(
            ZoneInfo("America/New_York")
        )

        latest_date = pd.Timestamp(
            frame.index[-1]
        ).date()

        if (
            latest_date == now_et.date()
            and now_et.hour < 16
            and len(frame) > 10
        ):
            frame = frame.iloc[:-1]

    except Exception:
        pass

    if len(frame) < 6:
        return None

    last = frame.iloc[-1]
    previous = frame.iloc[-2]

    close = float(last["Close"])
    open_price = float(last["Open"])
    high = float(last["High"])
    low = float(last["Low"])

    # Close-8 means the whole-dollar portion ends in 8.
    # Examples: 128.40, 238.75, 378.12.
    close8 = int(np.floor(close)) % 10 == 8

    if not close8:
        return None

    close_3_days = float(frame["Close"].iloc[-4])
    close_5_days = float(frame["Close"].iloc[-6])

    move_3d = (
        (close / close_3_days) - 1
    ) * 100

    move_5d = (
        (close / close_5_days) - 1
    ) * 100

    strong_up = (
        move_3d >= 5
        or move_5d >= 8
    )

    strong_down = (
        move_3d <= -5
        or move_5d <= -8
    )

    if not strong_up and not strong_down:
        return None

    body = abs(close - open_price)

    upper_wick = high - max(
        close,
        open_price
    )

    lower_wick = min(
        close,
        open_price
    ) - low

    minimum_wick = max(
        close * 0.002,
        0.01
    )

    bearish_rejection = (
        upper_wick >= max(body * 1.2, minimum_wick)
        and close < float(previous["Close"])
    )

    bullish_rejection = (
        lower_wick >= max(body * 1.2, minimum_wick)
        and close > float(previous["Close"])
    )

    if strong_up and bearish_rejection:

        setup = "🔴 POTENTIAL BEARISH REVERSAL"
        direction = "BEARISH"
        move = max(move_3d, move_5d)

    elif strong_down and bullish_rejection:

        setup = "🟢 POTENTIAL BULLISH REVERSAL"
        direction = "BULLISH"
        move = min(move_3d, move_5d)

    elif strong_up:

        setup = "🟡 BEARISH WATCH — NO CONFIRMATION"
        direction = "BEARISH WATCH"
        move = max(move_3d, move_5d)

    else:

        setup = "🟡 BULLISH WATCH — NO CONFIRMATION"
        direction = "BULLISH WATCH"
        move = min(move_3d, move_5d)

    return {
        "Ticker": ticker,
        "Daily Close": round(close, 2),
        "3-Day Move %": round(move_3d, 2),
        "5-Day Move %": round(move_5d, 2),
        "Strong Move": round(move, 2),
        "Direction": direction,
        "Reversal Setup": setup,
    }


# ============================================================
# MAIN SCREENER
# ============================================================

st.write(
    f"**Stocks loaded:** {len(stocks)}"
)

st.write(
    "Scanning 1HR signals, 2HR continuation, and actual Daily trends. "
    "Automatic refresh every 5 minutes."
)

st.caption(
    "1HR helps with entry timing. 2HR + Daily alignment creates "
    "a swing signal. Confirm price action before trading."
)

results = []

with st.spinner("Scanning stocks across timeframes..."):

    progress = st.progress(0)

    for i, ticker in enumerate(stocks):

        result = analyze_stock(ticker)

        if result:
            results.append(result)

        progress.progress(
            (i + 1) / max(len(stocks), 1)
        )

    progress.empty()


if results:

    df = pd.DataFrame(results)

    # --------------------------------------------------------
    # SORTING
    # --------------------------------------------------------

    def priority(row):

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

        return 6

    df["_Priority"] = df.apply(
        priority,
        axis=1
    )

    df = df.sort_values(
        "_Priority"
    ).drop(
        columns=["_Priority"]
    )

    # --------------------------------------------------------
    # DISCORD ALERTS
    # --------------------------------------------------------

    current_signals = {
        row["Ticker"]: row["1HR Signal"]
        for _, row in df.iterrows()
        if (
            "BULLISH BREAKOUT" in row["1HR Signal"]
            or "BEARISH BREAKDOWN" in row["1HR Signal"]
        )
    }

    if "previous_discord_signals" not in st.session_state:

        st.session_state[
            "previous_discord_signals"
        ] = current_signals.copy()

    else:

        previous_signals = st.session_state[
            "previous_discord_signals"
        ]

        for ticker, signal in current_signals.items():

            if previous_signals.get(ticker) != signal:

                send_discord_alert(
                    f"⛄🦈 Screener Alert: {ticker} — {signal}"
                )

        st.session_state[
            "previous_discord_signals"
        ] = current_signals.copy()

    # --------------------------------------------------------
    # TABLE COLORS
    # --------------------------------------------------------

    def style_table(dataframe):

        styles = pd.DataFrame(
            "",
            index=dataframe.index,
            columns=dataframe.columns
        )

        for idx, row in dataframe.iterrows():

            swing = str(row["🎯 SWING SIGNAL"])

            # Light full-row background.
            if "BEARISH SWING WATCH" in swing:

                row_color = (
                    "background-color: #f8d7da; color: #212529"
                )

            elif "BULLISH SWING WATCH" in swing:

                row_color = (
                    "background-color: #d1e7dd; color: #212529"
                )

            else:

                row_color = ""

            if row_color:
                styles.loc[idx, :] = row_color

            # Preserve individual signal colors.
            signal = str(row["1HR Signal"])

            if "BULLISH BREAKOUT" in signal:

                styles.loc[idx, "1HR Signal"] = (
                    "background-color: #198754; color: white; "
                    "font-weight: bold"
                )

            elif "BULLISH TREND" in signal:

                styles.loc[idx, "1HR Signal"] = (
                    "background-color: #0d6efd; color: white; "
                    "font-weight: bold"
                )

            elif "BEARISH TREND" in signal:

                styles.loc[idx, "1HR Signal"] = (
                    "background-color: #fd7e14; color: black; "
                    "font-weight: bold"
                )

            elif "BEARISH BREAKDOWN" in signal:

                styles.loc[idx, "1HR Signal"] = (
                    "background-color: #dc3545; color: white; "
                    "font-weight: bold"
                )

            elif "NO SIGNAL" in signal:

                styles.loc[idx, "1HR Signal"] = (
                    "background-color: #e9ecef; color: black"
                )

            # Preserve timeframe indicators.
            for column in ("2HR Trend", "Daily Trend"):

                value = str(row[column])

                if "BULLISH CONTINUATION" in value:

                    styles.loc[idx, column] = (
                        "background-color: #0d6efd; color: white; "
                        "font-weight: bold"
                    )

                elif "BEARISH CONTINUATION" in value:

                    styles.loc[idx, column] = (
                        "background-color: #fd7e14; color: black; "
                        "font-weight: bold"
                    )

                elif "MIXED" in value:

                    styles.loc[idx, column] = (
                        "background-color: #fff3cd; color: black"
                    )

                elif "INSUFFICIENT DATA" in value:

                    styles.loc[idx, column] = (
                        "background-color: #e9ecef; color: black"
                    )

            # Preserve swing signal indicators.
            if "BEARISH SWING WATCH" in swing:

                styles.loc[idx, "🎯 SWING SIGNAL"] = (
                    "background-color: #dc3545; color: white; "
                    "font-weight: bold"
                )

            elif "BULLISH SWING WATCH" in swing:

                styles.loc[idx, "🎯 SWING SIGNAL"] = (
                    "background-color: #198754; color: white; "
                    "font-weight: bold"
                )

            elif "WAIT" in swing:

                styles.loc[idx, "🎯 SWING SIGNAL"] = (
                    "background-color: #fff3cd; color: black"
                )

        return styles

    st.subheader("📊 Live Screener Results")

    st.dataframe(
        df.style.apply(
            style_table,
            axis=None
        ),
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # SIGNAL SUMMARY
    # --------------------------------------------------------

    st.subheader("🎯 Signal Summary")

    bullish = df["1HR Signal"].str.contains(
        "BULLISH"
    ).sum()

    bearish = df["1HR Signal"].str.contains(
        "BEARISH"
    ).sum()

    bullish_swings = df["🎯 SWING SIGNAL"].str.contains(
        "BULLISH SWING WATCH"
    ).sum()

    bearish_swings = df["🎯 SWING SIGNAL"].str.contains(
        "BEARISH SWING WATCH"
    ).sum()

    mixed = df["🎯 SWING SIGNAL"].str.contains(
        "WAIT|MIXED",
        regex=True
    ).sum()

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("1HR Bullish", int(bullish))
    c2.metric("1HR Bearish", int(bearish))
    c3.metric("Bullish Swing Watches", int(bullish_swings))
    c4.metric("Bearish Swing Watches", int(bearish_swings))
    c5.metric("Mixed / Wait", int(mixed))

    st.info(
        "Technical screening signals are not guaranteed entries or "
        "predictions. Confirm price action and manage risk."
    )

else:

    st.warning(
        "No stock data returned. Check your internet connection "
        "and ticker symbols."
    )


# ============================================================
# PRIVATE CLOSE-8 REVERSAL SCAN
# ============================================================

st.divider()

st.subheader("🔒 Private Close-8 Reversal Scanner")

st.caption(
    "Private scan: identifies stocks that have made a strong "
    "multi-day move and whose daily closing price has a whole-dollar "
    "portion ending in 8."
)

private_password = st.secrets.get(
    "PRIVATE_SCAN_PASSWORD",
    ""
)

if not private_password:

    st.warning(
        "Private scan is disabled. Add PRIVATE_SCAN_PASSWORD "
        "to Streamlit Secrets to activate it."
    )

else:

    with st.form("private_scan_login"):

        entered_password = st.text_input(
            "Enter private scan password",
            type="password"
        )

        unlock = st.form_submit_button(
            "Unlock Private Scan"
        )

        if unlock:

            if hmac.compare_digest(
                entered_password,
                str(private_password)
            ):

                st.session_state[
                    "close8_authenticated"
                ] = True

            else:

                st.session_state[
                    "close8_authenticated"
                ] = False

                st.error("Incorrect password.")

    if st.session_state.get(
        "close8_authenticated",
        False
    ):

        st.success(
            "Private Close-8 Scanner unlocked."
        )

        st.markdown(
            """
            **Scan criteria**

            - Strong 3-day move of at least 5%, OR
              strong 5-day move of at least 8%.
            - Daily closing price has a whole-dollar portion
              ending in 8.
            - Identifies potential reversal candles.
            - Separates confirmed rejection patterns from watch setups.
            """
        )

        if st.button(
            "🔎 Run Private Close-8 Scan"
        ):

            close8_results = []

            with st.spinner(
                "Scanning for Close-8 reversal candidates..."
            ):

                private_progress = st.progress(0)

                for i, ticker in enumerate(stocks):

                    result = analyze_close8_reversal(
                        ticker
                    )

                    if result:
                        close8_results.append(result)

                    private_progress.progress(
                        (i + 1) / max(len(stocks), 1)
                    )

                private_progress.empty()

            if close8_results:

                close8_df = pd.DataFrame(
                    close8_results
                )

                close8_df["_Priority"] = (
                    close8_df["Direction"].map(
                        {
                            "BEARISH": 0,
                            "BEARISH WATCH": 1,
                            "BULLISH": 2,
                            "BULLISH WATCH": 3,
                        }
                    )
                )

                close8_df = close8_df.sort_values(
                    "_Priority"
                ).drop(
                    columns=["_Priority"]
                )

                def close8_style(dataframe):

                    styles = pd.DataFrame(
                        "",
                        index=dataframe.index,
                        columns=dataframe.columns
                    )

                    for idx, row in dataframe.iterrows():

                        direction = str(
                            row["Direction"]
                        )

                        if direction == "BEARISH":

                            styles.loc[idx, :] = (
                                "background-color: #f8d7da; "
                                "color: #212529"
                            )

                        elif direction == "BULLISH":

                            styles.loc[idx, :] = (
                                "background-color: #d1e7dd; "
                                "color: #212529"
                            )

                        else:

                            styles.loc[idx, :] = (
                                "background-color: #fff3cd; "
                                "color: #212529"
                            )

                    return styles

                st.subheader(
                    "🎯 Private Close-8 Candidates"
                )

                st.dataframe(
                    close8_df.style.apply(
                        close8_style,
                        axis=None
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                bearish_count = (
                    close8_df["Direction"]
                    .str.contains("BEARISH")
                    .sum()
                )

                bullish_count = (
                    close8_df["Direction"]
                    .str.contains("BULLISH")
                    .sum()
                )

                watch_count = (
                    close8_df["Direction"]
                    .str.contains("WATCH")
                    .sum()
                )

                p1, p2, p3 = st.columns(3)

                p1.metric(
                    "Bearish Candidates",
                    int(bearish_count)
                )

                p2.metric(
                    "Bullish Candidates",
                    int(bullish_count)
                )

                p3.metric(
                    "Watch Setups",
                    int(watch_count)
                )

                st.caption(
                    "A Close-8 match is a price filter, not an "
                    "automatic entry. Reversal confirmation is "
                    "based on the daily candle's rejection behavior."
                )

            else:

                st.info(
                    "No Close-8 candidates currently meet the "
                    "multi-day move criteria."
                )

        if st.button(
            "🔒 Lock Private Scan"
        ):

            st.session_state[
                "close8_authenticated"
            ] = False

            st.rerun()

