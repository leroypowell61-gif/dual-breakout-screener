    def style_table(dataframe):
        styles = pd.DataFrame(
            "",
            index=dataframe.index,
            columns=dataframe.columns
        )

        for idx, row in dataframe.iterrows():
            swing = str(row.get("🎯 SWING SIGNAL", ""))
            signal = str(row.get("1HR Signal", ""))
            trends = (
                str(row.get("2HR Trend", ""))
                + " "
                + str(row.get("Daily Trend", ""))
            )

            # Light red background for bearish plays
            if (
                "BEARISH" in swing
                or "BEARISH" in signal
                or "BEARISH CONTINUATION" in trends
            ):
                background = (
                    "background-color: #fce8e8; color: #212529"
                )

            # Light green background for bullish plays
            elif (
                "BULLISH" in swing
                or "BULLISH" in signal
                or "BULLISH CONTINUATION" in trends
            ):
                background = (
                    "background-color: #e6f4ea; color: #212529"
                )

            # Yellow for mixed or waiting signals
            elif (
                "WAIT" in swing
                or "MIXED" in swing
                or "MIXED" in trends
            ):
                background = (
                    "background-color: #fff3cd; color: #212529"
                )

            # Gray for everything else
            else:
                background = (
                    "background-color: #e9ecef; color: #212529"
                )

            for column in dataframe.columns:
                styles.loc[idx, column] = background

                # Preserve the individual signal colors
                signal_style = style_cell(
                    row[column],
                    column
                )

                if signal_style:
                    styles.loc[idx, column] = signal_style

        return styles
