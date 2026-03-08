import streamlit as st

from sr_checker_lib import (
    extract_code,
    get_participants_from_logs,
    get_sr_df,
    get_violation_output,
    high_value_items_raid_map,
    raid_codes_map_reverse,
    show_name_list_in_columns,
    style_by_attendee,
)

qp = st.query_params


if "initialized_from_qp" not in st.session_state:
    st.session_state.initialized_from_qp = True
    st.session_state.raidres_event_code_in = qp.get("rc", "") or ""
    st.session_state.logs_code_in = qp.get("lc", "") or ""


st.set_page_config(page_title="SR Checker", layout="wide")
st.title("Still Standing - Loot System validation tool")


with st.sidebar:
    st.markdown("### Inputs")

    raidres_event_code_in = st.text_input(
        "Raidres event code",
        placeholder="PQWT2X or paste RaidRes link",
        key="raidres_event_code_in",
    )

    logs_code_in = st.text_input(
        "Turtlelogs event code (optional)",
        placeholder="E.g. enter '95136' for https://www.turtlogs.com/viewer/95136/base?history_state=1",
        key="logs_code_in",
    )

    run = st.button("Run", type="primary")

with st.sidebar:
    with st.expander("Optional settings"):
        high_value_override = st.text_area(
            "Override HIGH_VALUE_ITEMS (one item per line).",
            height=150,
            key="high_value_override",
        )

if high_value_override.strip():
    custom_items = [x.strip() for x in high_value_override.split("\n") if x.strip()]

    high_value_items = custom_items
else:
    high_value_items = None  # will use default in get_sr_df

# Auto run if raidres_event_code_in is provided (either via URL or user input)
if st.session_state.raidres_event_code_in:
    run = True

if run:
    raidres_event_code = extract_code(st.session_state.raidres_event_code_in)
    st.markdown(
        f"Results for RaidRes event: [https://raidres.top/res/{raidres_event_code}](https://raidres.top/res/{raidres_event_code})"
    )
    logs_code = st.session_state.logs_code_in
    # logs_code = extract_code(st.session_state.logs_code_in)

    if not raidres_event_code:
        st.error("Please enter raidres_event_code.")
        st.stop()

    # write into URL: rc always, lc only if present
    new_qp = {"rc": raidres_event_code}
    if logs_code:
        new_qp["lc"] = logs_code
    st.query_params.clear()
    st.query_params.update(new_qp)

    # 1) Build SR df
    try:
        with st.spinner("Downloading SR data..."):
            raid_id, sr_df = get_sr_df(
                raidres_event_code, high_value_items=high_value_items
            )
    except Exception as e:
        st.exception(e)
        st.stop()

    raid_name = raid_codes_map_reverse.get(raid_id, f"Raid ID {raid_id}")
    st.write(
        f"Hello raiders, you now have 3SR+ for {raid_name}. Please be fair when using your SR+. If you need many upgrades, please use your 3 SR +",
        "If you need one of the valuable item in the following list then you can only use 1SR+ :",
    )
    show_name_list_in_columns(
        high_value_items_raid_map.get(raid_name, []),
        st,
        n_cols=1,
        header=None,
    )
    st.info(
        "A Player Must Have at least 3 attendances within the Guilds runs before being able to roll for one of the High Priority Items!"
        + " During this Period you can still Sr the item and build points towards it!"
        + " Attendance is Bound to the Character you are Bringing!"
    )

    st.warning(
        "⚠️Disclosure⚠️: You Will be loot Banned + Discord Kicked If: \n"
        + " (i) If you get caught trying to cheat the system!\n"
        + " (ii) Ignore the Sr Rules\n"
        + "(iii) Blatantly Ignoring Raid Calls"
    )

    # 2) Violations first
    st.header("Violations")

    out = get_violation_output(sr_df)
    if out is None:
        st.success("No violations found.")
    else:
        violations_df, violations_df_full_by_char = out
        st.dataframe(
            style_by_attendee(violations_df),
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Violation details (by character)")
        violations_df_full_by_char = violations_df_full_by_char.reset_index().drop(
            columns=["row"]
        )
        st.dataframe(
            style_by_attendee(violations_df_full_by_char),
            use_container_width=True,
            hide_index=True,
        )

    # 3) High-value SRs second
    st.header("High-value SRs")
    hv_df = sr_df[sr_df["is_high_value"]].drop(
        columns=["item_norm", "is_high_value", "id"], errors="ignore"
    )
    st.dataframe(
        style_by_attendee(hv_df.reset_index(drop=True)),
        use_container_width=True,
        hide_index=True,
    )

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
        mask_participants = (
            sr_df["attendee"].str.lower().isin([p.lower() for p in logged_participants])
        )

        st.subheader("Bench OR not in logs")
        st.dataframe(
            sr_df[mask_bench | ~mask_participants][
                ["attendee", "comment"]
            ].drop_duplicates(),
            use_container_width=True,
        )
else:
    st.info("Enter a raidres event link (or code) to check for SR violations.")
    st.info(
        "Enter a logs code and click Run to cross-check SR attendees with logs participants."
    )

st.markdown("---")

st.markdown(
    """
    <div style="text-align:center; font-size:0.9rem; color:gray;">
        Made for <b>Still Standing</b> ⚔️ | Please report any issues or suggestions in our discord.
    </div>
    """,
    unsafe_allow_html=True,
)

# Hide the "Made with Streamlit" footer
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
