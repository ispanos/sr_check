import pandas as pd


def get_last_attendance_update(df):
    # drop the junk first column if needed
    df2 = df.iloc[:, 1:].copy()

    # first row contains labels like "Tuesday Naxx", "Wednesday AQ 40", etc.
    event_labels = df2.iloc[0]

    summary_df = pd.DataFrame(
        {
            "logged_date_raw": df2.columns,
            "event": event_labels.values,
        }
    )

    # parse the column headers as datetimes
    summary_df["last_logged_date"] = pd.to_datetime(
        summary_df["logged_date_raw"], errors="coerce"
    )

    # keep only valid event names
    summary_df["event"] = summary_df["event"].astype(str).str.strip()
    summary_df = summary_df[
        summary_df["event"].notna()
        & (summary_df["event"] != "")
        & (summary_df["event"].str.lower() != "missing value")
        & (summary_df["event"].str.lower() != "nan")
    ]

    # latest logged date for each day/raid combo
    latest_per_event = (
        summary_df.groupby("event", as_index=False)["last_logged_date"]
        .max()
        .sort_values("last_logged_date")
    )

    latest_per_event["last_logged_date"] = latest_per_event[
        "last_logged_date"
    ].dt.strftime("%Y-%m-%d %Hst")
    summary = latest_per_event.T
    summary.columns = summary[0:1].values[0]
    return summary[1:]


def download_attendance_google_sheet():
    # Hard-coded until a proper database is online.
    google_sheet_attendance = "https://docs.google.com/spreadsheets/d/11HTbDcaCt2mndJy1pYKRKL1TvDOSam-R4Q7UKzbS5w0/export?format=csv&gid=1696774817"
    df = pd.read_csv(google_sheet_attendance)
    return df.drop(1)


def get_attendance_per_char(df, left_merge_df=None):

    # drop junk first column if needed
    df2 = df.iloc[:, 1:].copy()

    event_labels = df2.iloc[0]
    players = df2.iloc[1:].copy()
    players.columns = event_labels

    long_df = players.melt(var_name="event", value_name="player")
    long_df["player"] = long_df["player"].astype(str).str.strip()

    long_df = long_df[
        (long_df["player"] != "")
        & (long_df["player"].str.lower() != "missing value")
        & (long_df["player"].str.lower() != "nan")
    ]

    long_df["dungeon"] = long_df["event"].str.replace(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+",
        "",
        regex=True,
    )

    attendance_pivot = (
        long_df.groupby(["player", "dungeon"]).size().unstack(fill_value=0).sort_index()
    )
    attendance_pivot = attendance_pivot.astype("Int64").reset_index()
    attendance_pivot = attendance_pivot.rename(columns={"player": "attendee"})

    if left_merge_df is not None:
        return pd.merge(left_merge_df, attendance_pivot, on="attendee", how="left")

    return attendance_pivot


def get_attendance_column(header, logged_participants):

    return pd.DataFrame(
        {
            header: ["TRUE"] + logged_participants,
        }
    )
