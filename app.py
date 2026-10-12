import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Dual Breakout Screener",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Dual Breakout Screener")
st.write(
    "Find potential bullish breakouts, bearish breakdowns, "
    "and triangle chart patterns."
)

st.warning(
    "Educational tool only. Signals are not guarantees. "
    "Confirm trades independently before entering."
)

default_tickers = (
    "NVDA, AMD, TSLA, AAPL, MSFT, AMZN, META, "
    "GOOGL, AVGO, MU, MRVL, ALAB, LLY, TER, LRCX"
)

tickers_input = st.text_area(
    "Stock tickers (separate with commas)",
    value=default_tickers
)

lookback = st.slider(
    "Resistance/support lookback",
    min_value=10,
    max_value=60,
    value=20
)

volume_multiplier = st.slider(
    "Volume confirmation multiplier",
    min_value=1.0,
    max_value=3.0,
    value=1.5,
    step=0.1
)

run_scan = st.button("🔍 Scan Stocks", type="primary")


def analyze_stock(ticker):
    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if df.empty or len(df) < lookback + 5:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna(subset=["Close", "High", "Low", "Volume"])

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        volume = df["Volume"].astype(float)

        price = float(close.iloc[-1])

        resistance = float(
            high.iloc[-lookback-1:-1].max()
        )

        support = float(
            low.iloc[-lookback-1:-1].min()
        )

        avg_volume = float(
            volume.iloc[-21:-1].mean()
        )

        current_volume = float(volume.iloc[-1])

        ema20 = float(
            close.ewm(span=20, adjust=False).mean().iloc[-1]
        )

        ema50 = float(
            close.ewm(span=50, adjust=False).mean().iloc[-1]
        )

        avg_range = float(
            (high - low).rolling(14).mean().iloc[-1]
        )

        recent_highs = high.iloc[-10:].to_numpy()
        recent_lows = low.iloc[-10:].to_numpy()

        high_slope = np.polyfit(
            np.arange(len(recent_highs)),
            recent_highs,
            1
        )[0]

        low_slope = np.polyfit(
            np.arange(len(recent_lows)),
            recent_lows,
            1
        )[0]

        contracting = (
            high_slope < 0
            and low_slope > 0
        )

        volume_confirmed = (
            avg_volume > 0
            and current_volume >= avg_volume * volume_multiplier
        )

        bullish = (
            price > resistance
            and volume_confirmed
        )

        bearish = (
            price < support
            and volume_confirmed
        )

        if bullish:
            signal = "BULLISH BREAKOUT"
        elif bearish:
            signal = "BEARISH BREAKDOWN"
        elif contracting:
            signal = "POSSIBLE SYMMETRICAL TRIANGLE"
        elif price > ema20 and ema20 > ema50:
            signal = "BULLISH TREND"
        elif price < ema20 and ema20 < ema50:
            signal = "BEARISH TREND"
        else:
            signal = "WAIT / NO CONFIRMED SIGNAL"

        if bullish:
            entry = resistance
            stop = resistance - avg_range
            target = entry + (entry - stop) * 2
        elif bearish:
            entry = support
            stop = support + avg_range
            target = entry - (stop - entry) * 2
        else:
            entry = np.nan
            stop = np.nan
            target = np.nan

        return {
            "Ticker": ticker,
            "Price": round(price, 2),
            "Signal": signal,
            "Resistance": round(resistance, 2),
            "Support": round(support, 2),
            "EMA 20": round(ema20, 2),
            "EMA 50": round(ema50, 2),
            "Volume Confirmed": "Yes" if volume_confirmed else "No",
            "Entry Reference": round(entry, 2) if np.isfinite(entry) else None,
            "Stop Reference": round(stop, 2) if np.isfinite(stop) else None,
            "2R Target": round(target, 2) if np.isfinite(target) else None,
        }

    except Exception as e:
        return {
            "Ticker": ticker,
            "Price": None,
            "Signal": "DATA ERROR",
            "Resistance": None,
            "Support": None,
            "EMA 20": None,
            "EMA 50": None,
            "Volume Confirmed": "No",
            "Entry Reference": None,
            "Stop Reference": None,
            "2R Target": None,
        }


if run_scan:
    tickers = list(
        dict.fromkeys(
            t.strip().upper()
            for t in tickers_input.split(",")
            if t.strip()
        )
    )

    if not tickers:
        st.error("Enter at least one stock ticker.")
    else:
        results = []

        progress = st.progress(0)
        status = st.empty()

        for i, ticker in enumerate(tickers):
            status.write(f"Scanning {ticker}...")

            result = analyze_stock(ticker)

            if result:
                results.append(result)

            progress.progress((i + 1) / len(tickers))

        status.write("Scan complete!")

        if results:
            results_df = pd.DataFrame(results)

            st.subheader("📊 Screener Results")

            bullish_df = results_df[
                results_df["Signal"] == "BULLISH BREAKOUT"
            ]

            bearish_df = results_df[
                results_df["Signal"] == "BEARISH BREAKDOWN"
            ]

            col1, col2, col3 = st.columns(3)

            col1.metric("Stocks Scanned", len(results_df))
            col2.metric("Bullish Breakouts", len(bullish_df))
            col3.metric("Bearish Breakdowns", len(bearish_df))

            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Download Scan Results CSV",
                data=results_df.to_csv(index=False),
                file_name="dual_breakout_results.csv",
                mime="text/csv"
            )

            st.caption(
                "Resistance and support use prior daily candles. "
                "Signals are based on daily closing prices and volume. "
                "The triangle detector is a simple approximation, "
                "not a verified chart-pattern recognition system. "
                "Targets and stops are illustrative price references, "
                "not predictions or guaranteed execution prices."
            )
        else:
            st.error("No results returned. Check your internet connection.")