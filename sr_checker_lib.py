import argparse
import csv
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import requests

HIGH_VALUE_ITEMS = (
    [
        "Badge of the Swarmguard",
        "Gloves of the Primordial Burrower",
        "Dark Edge of Insanity",
        "Eyestalk Waist Cord",
        "Eye of C'Thun",
        "Yshgo'lar, Cowl of Fanatical Devotion",
        "Spotted Qiraji Battle Tank",
    ]
    + [
        "Kiss of the Spider",
        "Wraith Blade",
        "Band of Unnatural Forces",
        "Corrupted Ashbringer",
        "Eye of the Dead",
        "The Restrained Essence of Sapphiron",
        "Cloak of the Necropolis",
        "Slayer's Crest",
        "Gressil, Dawn of Ruin",
        "Might of Menethil",
        "Plagued Riding Spider",
        "The Hungering Cold",
        "Hammer of the Twisting Nether",
    ]
    + [
        "Mechanical Horse",
        "Raka'shishi, Spear of the Adrift Hunt",
        "Felforged Dreadhound",
        "Heart of Mephistroth",
        "Kirel'narak, the Death Sentence",
        "Thunderfall, Stormhammer of the Chief Thane",
        "Shar'tateth, the Shattered Edge",
        "Ephemeral Pendant",
        "Shieldrender Talisman",
        "Khadgar's Guidance",
    ]
)

raid_codes_map = {
    "aq40": 99,
    "kara40": 109,
    "zg": 100,
    "ony": 97,
    "naxx": 96,
    "es": 102,
}


def norm_item(s: str) -> str:
    """Normalize item strings for matching."""
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    # remove common punctuation that may differ across exports
    s = re.sub(r"[’'`]", "", s)
    s = re.sub(r"[\(\)\[\]\{\}]", "", s)
    s = re.sub(r"\s*-\s*", "-", s)
    return s


def get_exclusive_items(list_of_exclusive_items):
    with open(list_of_exclusive_items, "r") as rf:
        return [norm_item(line) for line in rf]


def download_raidres_data(
    *, event_code: str = None, raid_code: str = None, timeout: int = 30
) -> Dict[str, Any]:
    """
    Download https://raidres.top/api/events/<event_code> and
    https://raidres.top/raids/raid_<raid_code>.json using browser-like headers.

    If you still get 403:
      - try adding your own cookies (see `requests.Session()` and `session.cookies`)
      - or run it from the same machine/browser session and copy cookies
    """
    if event_code is None and raid_code is None:
        raise ValueError("Either event_code or raid_code must be provided")
    if event_code is not None and raid_code is not None:
        raise ValueError("Only one of event_code or raid_code must be provided")

    if event_code is not None:
        url = f"https://raidres.top/api/events/{event_code}"
    else:
        url = f"https://raidres.top/raids/raid_{raid_code}.json"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": url,
        "Origin": "https://raidres.top",
    }

    with requests.Session() as s:
        r = s.get(url, headers=headers, timeout=timeout)
        # one simple retry without Referer/Origin sometimes helps
        if r.status_code == 403:
            r = s.get(
                url,
                headers={**headers},
                timeout=timeout,
            )
        r.raise_for_status()
        return r.json()


def get_item_name_from_raidres_id(sr_raid_item_id, name_map):
    for item in name_map["raidItems"]:
        item_id = item["id"]
        if item_id == sr_raid_item_id:
            return item["name"]


def get_boss_name_from_raidres_id(sr_raid_item_id, name_map):
    raidBosses_returned = []
    for item in name_map["raidItems"]:
        item_id = item["id"]
        if item_id == sr_raid_item_id:
            raid_boss_ids = item["raidBosses"]
            for raid_boss_id in raid_boss_ids:
                raidBosses = name_map["raidBosses"]
                for boss in raidBosses:
                    if boss["id"] == raid_boss_id:
                        raidBosses_returned.append(boss["name"])
    return raidBosses_returned


def build_sr_df(payload: Dict[str, Any], name_map) -> pd.DataFrame:
    """
    Create a DataFrame with columns:
      ID, Item, Boss, Attendee, Comment, SR+

    Loops over payload['reservations'] and extracts:
      - character.name
      - srPlus.value
      - comment
      - id
      - raidItemId
    Then resolves Item/Boss via helper functions:
      get_item_name_from_raidres_id(raid_item_id)
      get_boss_name_from_raidres_id(raid_item_id)
    """
    # cols = ["id", "item", "boss", "attendee", "comment", "sr+"]

    reservations = payload.get("reservations", [])
    if not isinstance(reservations, list):
        raise TypeError(
            f"payload['reservations'] must be a list, got {type(reservations)}"
        )

    rows = []
    for sr_line in reservations:
        # Required fields (will raise KeyError if missing; change to .get(...) if you prefer)
        sr_attendee = sr_line["character"]["name"]
        sr_attendee_spec = sr_line["character"]["specialization"]
        sr_plus = sr_line["srPlus"]["value"]
        sr_comment = sr_line.get("comment", "")
        sr_id = sr_line["id"]
        sr_raid_item_id = sr_line["raidItemId"]

        # Resolve item + boss from raidItemId
        sr_item_name = get_item_name_from_raidres_id(sr_raid_item_id, name_map)
        sr_boss_names = get_boss_name_from_raidres_id(sr_raid_item_id, name_map)
        rows.append(
            {
                "id": sr_id,
                "item": sr_item_name,
                "boss": sr_boss_names,
                "attendee": sr_attendee,
                "loot_spec": sr_attendee_spec,
                "comment": sr_comment,
                "sr+": sr_plus,
                # 'sr_raid_item_id': sr_raid_item_id,
            }
        )

    df = pd.DataFrame(rows)
    df["item_norm"] = df["item"].map(norm_item)
    return df


def get_violation_list(sr_df):
    # count SRs per player
    sr_counts = (
        sr_df.groupby("attendee")
        .agg(
            total_srs=("item", "count"),
            high_value_srs=("is_high_value", "sum"),
        )
        .reset_index()
    )

    violations = []

    for _, row in sr_counts.iterrows():
        reasons = None
        if row.high_value_srs >= 1 and row.total_srs > 1:
            reasons = "High-value item reserved with other items"
        if row.high_value_srs > 1:
            reasons = "More than one high-value item reserved"

        if reasons:
            violations.append(
                {
                    "attendee": row.attendee,
                    "total_srs": row.total_srs,
                    "high_value_srs": row.high_value_srs,
                    "violation": reasons,
                }
            )
    return violations


def get_sr_df(raidres_event_code, *, raid=None, high_value_items=None):

    if high_value_items is None:
        high_value_items = [norm_item(item) for item in HIGH_VALUE_ITEMS]
    else:
        high_value_items = [norm_item(item) for item in high_value_items]

    sr_data = download_raidres_data(event_code=raidres_event_code)
    raid_id = sr_data["raidId"]
    if raid:
        raid_id = raid_codes_map.get(raid)
        if raid_id is None:
            raise ValueError(
                f"Invalid raid name: {raid}. Valid options: {list(raid_codes_map.keys())}"
            )
    sr_df = build_sr_df(
        download_raidres_data(event_code=raidres_event_code),
        download_raidres_data(raid_code=raid_id),
    )
    sr_df["is_high_value"] = sr_df["item_norm"].isin(high_value_items)
    return sr_df


def get_violation_output(sr_df):
    violations = get_violation_list(sr_df)
    if violations != []:
        violations_df = pd.DataFrame(violations)

        violators = violations_df["attendee"].to_list()

        violations_df_full = sr_df[sr_df["attendee"].isin(violators)]
        violations_df_full = violations_df_full
        violations_df_full_by_char = (
            violations_df_full.assign(
                row=lambda d: d.groupby(
                    [
                        "attendee",
                    ]
                ).cumcount()
                + 1
            )
            .set_index(["attendee", "item", "row"])
            .sort_index()
            .drop(columns=["item_norm", "id"])
        )
        return violations_df, violations_df_full_by_char
    else:
        print("No violations found.")


def get_participants_from_logs(event_code: str, *, timeout: int = 30) -> Dict[str, Any]:
    url = f"https://www.turtlogs.com/API/instance/export/participants/{event_code}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": url,
        "Origin": "https://www.turtlogs.com",
    }

    with requests.Session() as s:
        r = s.get(url, headers=headers, timeout=timeout)
        # one simple retry without Referer/Origin sometimes helps
        if r.status_code == 403:
            r = s.get(
                url,
                headers={**headers},
                timeout=timeout,
            )
        r.raise_for_status()
        # return r.json()
    return list(set([x["name"] for x in r.json() if x["name"].isalpha()]))


# ----------------------------
def extract_code(s: str) -> str:
    """
    Accepts a raw code like 'PQWT2X' or a full link like
    https://raidres.top/api/events/PQWT2X or https://raidres.net/25PAP4
    and returns the last path token.
    """
    s = (s or "").strip()
    if not s:
        return ""
    s = s.rstrip("/")
    return s.split("/")[-1]


def show_name_list_in_columns(names, st, n_cols=4, header="Participants"):
    names = sorted(set(names), key=lambda x: x.lower())
    st.subheader(header)

    if not names:
        st.info("No names to show.")
        return

    cols = st.columns(n_cols)
    per_col = math.ceil(len(names) / n_cols)

    for i, col in enumerate(cols):
        chunk = names[i * per_col : (i + 1) * per_col]
        # one name per line
        col.markdown("\n".join([f"- {n}" for n in chunk]))
