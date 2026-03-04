import math
import re

import streamlit as st

from sr_checker_lib import (
    extract_code,
    get_participants_from_logs,
    get_sr_df,
    get_violation_output,
    show_name_list_in_columns,
)

st.set_page_config(page_title="SR Checker", layout="wide")
st.title("SR Checker")


with st.sidebar:
    st.markdown("### Inputs")

    raidres_event_code_in = st.text_input(
        "Raidres event code",
        placeholder="PQWT2X or paste RaidRes link",
    )

    logs_code_in = st.text_input(
        "Turtlelogs event code (optional)",
        placeholder="E.g. enter '95136' for https://www.turtlogs.com/viewer/95136/base?history_state=1",
    )

    run = st.button("Run", type="primary")

with st.sidebar:
    st.markdown("### Optional settings")

    high_value_override = st.text_area(
        "Override HIGH_VALUE_ITEMS (one item per line).", height=150
    )

if high_value_override.strip():
    custom_items = [x.strip() for x in high_value_override.split("\n") if x.strip()]

    high_value_items = custom_items
else:
    high_value_items = None  # will use default in get_sr_df

# ----------------------------
# Run
# ----------------------------
if run:
    raidres_event_code = extract_code(raidres_event_code_in)
    logs_code = extract_code(logs_code_in)

    if not raidres_event_code:
        st.error("Please enter raidres_event_code.")
        st.stop()

    # 1) Build SR df
    try:
        with st.spinner("Downloading SR data..."):
            sr_df = get_sr_df(
                raidres_event_code, high_value_items=high_value_items
            )  # you said raid auto-detected now
    except Exception as e:
        st.exception(e)
        st.stop()

    # 2) Violations first
    st.header("Violations")

    out = get_violation_output(sr_df)
    if out is None:
        st.success("No violations found.")
    else:
        violations_df, violations_df_full_by_char = out
        st.dataframe(violations_df, use_container_width=True)
        st.subheader("Violation details (by character)")
        st.dataframe(violations_df_full_by_char, use_container_width=True)

    # 3) High-value SRs second
    st.header("High-value SRs")
    hv_df = sr_df[sr_df["is_high_value"]].drop(
        columns=["item_norm", "is_high_value", "id"], errors="ignore"
    )
    st.dataframe(hv_df, use_container_width=True)

    # 4) If logs_code provided: print participant list + bench/non-participants table
    if logs_code:
        st.header("Logs cross-check")

        try:
            with st.spinner("Downloading participants from logs..."):
                logged_participants = get_participants_from_logs(logs_code)
        except Exception as e:
            st.error(
                "Error fetching participants from logs: Please check the logs code and try again."
            )
            # st.exception(e)
            st.stop()

        # print logged_participants (nice columns, alphabetical)
        show_name_list_in_columns(
            logged_participants,
            st,
            n_cols=4,
            header=f"Logged participants ({len(logged_participants)})",
        )

        # then show bench / missing participants
        mask_bench = sr_df["comment"].str.contains("bench", case=False, na=False)
        mask_participants = sr_df["attendee"].isin(logged_participants)

        st.subheader("Bench OR not in logs")
        st.dataframe(
            sr_df[mask_bench | ~mask_participants][["attendee", "comment"]],
            use_container_width=True,
        )
