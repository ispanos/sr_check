from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from sr_checker_lib import download_raidres_data, get_item_name_from_raidres_id


def normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def get_previous_event_code(event_data: Dict[str, Any]) -> Optional[str]:
    return event_data.get("previousRaidEventReference") or None


def get_character_reservations(
    event_data: Dict[str, Any], character_name: str
) -> List[Dict[str, Any]]:
    target = normalize_name(character_name)
    return [
        r
        for r in event_data.get("reservations", [])
        if normalize_name(r["character"]["name"]) == target
    ]


def character_attended_event(event_data: Dict[str, Any], character_name: str) -> bool:
    return len(get_character_reservations(event_data, character_name)) > 0


def find_last_attended_event(
    current_event_data: Dict[str, Any],
    character_name: str,
    max_consecutive_misses_allowed: int = 3,
    past_events_dict=None,
) -> Tuple[Optional[Dict[str, Any]], int, Optional[str]]:
    """
    Walk backward through previousRaidEventReference until finding the most recent
    raid the character attended.

    If misses exceed max_consecutive_misses_allowed, points reset.
    """
    misses = 0
    prev_code = get_previous_event_code(current_event_data)

    while prev_code:
        if prev_code in past_events_dict:
            prev_event = past_events_dict[prev_code]
        else:
            prev_event = download_raidres_data(event_code=prev_code)
            past_events_dict[prev_code] = prev_event

        if character_attended_event(prev_event, character_name):
            return prev_event, misses, prev_code, past_events_dict

        misses += 1
        if misses > max_consecutive_misses_allowed:
            return None, misses, None, past_events_dict

        prev_code = get_previous_event_code(prev_event)

    return None, misses, None, past_events_dict


def build_expected_points_from_previous_attended_raid(
    previous_reservations: List[Dict[str, Any]],
    increment: int = 10,
) -> Dict[int, int]:
    """
    Build expected current SR+ by item from the previous attended raid.

    Rule:
      expected[item] = one_previous_srplus_value_for_item + increment * count_of_item_in_previous_raid

    Assumes repeated copies of the same item in a given raid should all display the same SR+ value.
    """
    by_item = defaultdict(list)

    for r in previous_reservations:
        by_item[r["raidItemId"]].append(r)

    expected = {}

    for item_id, rows in by_item.items():
        # pick one SR+ value from that raid for that item
        prev_value = int((rows[0].get("srPlus") or {}).get("value") or 0)
        count_this_item = len(rows)
        expected[item_id] = prev_value + increment * count_this_item

    return expected


def check_srplus_integrity(
    raidres_event_raw: dict,
    max_consecutive_misses_allowed: int = 3,
    raidres_metadata: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """
    Returns one row per current reservation, with expected vs entered SR+.
    """
    increment = int(raidres_event_raw.get("defaultSrPlusIncrease", 10) or 10)

    current_reservations = raidres_event_raw.get("reservations", [])

    # Group current reservations by character
    by_char = defaultdict(list)
    for r in current_reservations:
        by_char[r["character"]["name"]].append(r)

    rows_out = []

    past_events_dict = {}

    for character_name, curr_rows in sorted(
        by_char.items(), key=lambda kv: kv[0].lower()
    ):
        prev_event, misses, source_event_code, past_events_dict = (
            find_last_attended_event(
                current_event_data=raidres_event_raw,
                character_name=character_name,
                max_consecutive_misses_allowed=max_consecutive_misses_allowed,
                past_events_dict=past_events_dict,
            )
        )

        if prev_event is None:
            expected_by_item = {}
        else:
            prev_rows = get_character_reservations(prev_event, character_name)
            expected_by_item = build_expected_points_from_previous_attended_raid(
                prev_rows,
                increment=increment,
            )

        for r in curr_rows:
            item_id = r["raidItemId"]
            comment = r["comment"]
            if raidres_metadata:
                item_name = get_item_name_from_raidres_id(item_id, raidres_metadata)
            else:
                item_name = f"NA"

            entered_value = int((r.get("srPlus") or {}).get("value") or 0)
            expected_value = int(expected_by_item.get(item_id, 0))

            rows_out.append(
                {
                    "character": character_name,
                    "item_id": item_id,
                    "item_name": item_name,
                    "entered_srplus": entered_value,
                    "expected_srplus": expected_value,
                    "comment": comment,
                    "ok": entered_value == expected_value,
                    "carry_from_event": source_event_code,
                    "from_event": f"https://raidres.top/res/{source_event_code}",
                    "#absences (at least:)": misses,
                    "reason": (
                        ""
                        if entered_value == expected_value
                        else f"entered {entered_value}, expected {expected_value}"
                    ),
                }
            )

    out_df = pd.DataFrame(rows_out).sort_values(
        ["ok", "character", "item_name"],
        ascending=[True, True, True],
    )

    return out_df
