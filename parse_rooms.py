'''
To do (03/03):
Reroute json filtering -> match room by room against a list
and count available rooms that way. Would include individual
room names in the json.
    Includes square footage
    Automating pdf -> csv process
'''

# --- Imports ---
import os
import csv
import re
import json
from datetime import datetime
from collections import defaultdict

# Settings
SNAPSHOT_FOLDER = "/Users/lucysun/Desktop/Data"
SNAPSHOT_PREFIX = "spring_housing_selection_"
SNAPSHOT_YEAR = 2025
# LOOKUP_CSV = "/Users/lucysun/Desktop/Data/spring_room_selection_04_08_1200.csv"

# Base genders in the raw data
BASE_GENDERS = ("COED", "MALE", "FEMALE")
# Dropdown gender groupings
GENDER_GROUPS = ("COED", "COEDMALE", "COEDFEMALE", "ALL")
# Dropdown room-size options
SIZE_OPTIONS = ("ALL", 1, 2, 3, 4, 5, 9)

# Helpers

def size_label(size_opt):
    return "ALL" if size_opt == "ALL" else str(int(size_opt))

def normalize_name(name):
    return (
        (name or "")
        .upper()
        .replace(".", "")
        .replace("#", "")
        .replace("-", " ")
        .replace("  ", " ")
        .strip()
    )

# def load_building_lookup(csv_path):
#     lookup = {}
#     with open(csv_path, newline="", encoding="utf-8-sig") as f:
#         reader = csv.DictReader(f)
#         for row in reader:
#             lottery_name = normalize_name(row["Lottery_sheet_name"])
#             building_id = int(row["Building_ID"])
#             lookup[lottery_name] = building_id
#     return lookup

# def load_building_id_to_name(csv_path):
#     """
#     Returns dict: {Building_ID (int): Lottery_sheet_name (original casing from CSV)}
#     """
#     out = {}
#     with open(csv_path, newline="", encoding="utf-8-sig") as f:
#         reader = csv.DictReader(f)
#         for row in reader:
#             bid = int(row["Building_ID"])
#             out[bid] = row["Lottery_sheet_name"].strip()
#     return out

def parse_snapshot_time_from_filename(filename, year):
    """
    Expected filename pattern:
        spring_housing_selection_<month>_<day>_<HHMM>.csv
    Example:
        spring_housing_selection_04_08_0900.csv  -> April 8, 09:00
    Returns: datetime
    """
    fn = os.path.basename(filename)
    pattern = r"^" + re.escape(SNAPSHOT_PREFIX) + r"(\d{1,2})_(\d{1,2})_(\d{4})\.csv$"
    m = re.match(pattern, fn)
    if not m:
        raise ValueError(f"Filename does not match expected pattern: {fn}")
    month = int(m.group(1))
    day = int(m.group(2))
    hhmm = m.group(3)
    hour = int(hhmm[:2])
    minute = int(hhmm[2:])
    return datetime(year, month, day, hour, minute, 0)

def get_snapshot_files_with_times(folder):
    """
    Returns list of (snapshot_time, full_path) sorted by snapshot_time.
    """
    snapshots = []
    for fn in os.listdir(folder):
        if not fn.startswith(SNAPSHOT_PREFIX) or not fn.endswith(".csv"):
            continue
        full_path = os.path.join(folder, fn)
        try:
            t = parse_snapshot_time_from_filename(fn, SNAPSHOT_YEAR)
        except ValueError:
            continue
        snapshots.append((t, full_path))
    snapshots.sort(key=lambda x: x[0])
    return snapshots

def map_base_gender(raw_gender):
    """
    Maps raw Room Gender values to base categories:
      COED includes CoEd + DynamicGender
      MALE includes Male
      FEMALE includes Female
    Returns None if not recognized.
    """
    g = (raw_gender or "").strip()
    if g in ("CoEd", "DynamicGender"):
        return "COED"
    if g == "Male":
        return "MALE"
    if g == "Female":
        return "FEMALE"
    return None

# New-ish code
def get_lookup(snapshots):
    """
    Builds lookup file from snapshot files. 
    """
    # Make set of unique buildings from snapshots.
    # Only in general selection.
    buildings = set()
    for _, snapshot_csv in snapshots:
        with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                profile = row.get("Room Profile")
                if profile != "25-26 Spring Selection (Room)":
                    continue
                building = normalize_name(row.get("Building"))
                if building:
                    buildings.add(building)

    # Create lookup dictionaries
    building_lookup = {}
    building_id_to_name = {}
    for i, building in enumerate(sorted(buildings), start=1):
        building_lookup[building] = i
        building_id_to_name[i] = building.title()
    return building_lookup, building_id_to_name

# Aggregation - from Jasper
### IMPORTANT

def process_snapshot(snapshot_csv, building_lookup): # DO NOT TOUCH
    """
    Computes AVAILABLE fully-available room/suite counts for each building across:
      - base genders: COED/MALE/FEMALE
      - capacities (room/suite size): integer capacity
    Returns:
      avail_counts[building_id][base_gender][capacity] = count_of_fully_available_rooms
      avail_counts[building_id][base_gender]["ALL"] = sum across all capacities
    """
    # Track each unique room instance by: (building_id, room_key, base_gender)
    # Each holds capacity and available_beds count.
    rooms = {}
    counted_rooms = set()  # For special case "GREG A 125" block
    with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            profile = row.get("Room Profile")
            if profile != "25-26 Spring Selection (Room)":
                continue
            building_name = normalize_name(row.get("Building"))
            if building_name not in building_lookup:
                print("NOT MATCHED:", building_name)
                continue
            building_id = building_lookup[building_name]
            base_gender = map_base_gender(row.get("Room Gender"))
            if base_gender is None:
                # Skip unrecognized gender categories
                continue
            room_type = (row.get("Room Type") or "").strip()
            room_str = (row.get("Room") or "")
            # --- Grad Center rooms ---
            if "GRAD CENTER" in building_name:
                room_id = (row.get("Room") or "").strip()
                if not room_id:
                    continue
                capacity = 1
                key = (building_id, room_id, base_gender)
                if key not in rooms:
                    rooms[key] = {"capacity": capacity, "available_beds": 1}
                continue
            # --- Special suite case: GREG A 125 --- ## FIX CASE
            if "GREG A 125" in room_str:
                if "GREG A 125" not in counted_rooms:
                    capacity = 9
                    key = (building_id, "GREG A 125", base_gender)
                    rooms[key] = {"capacity": capacity, "available_beds": capacity}
                    for i in range(125, 133):
                        counted_rooms.add(f"GREG A {i}")
                continue
            # --- Regular suites ---
            if "Suite" in room_type:
                suite_id = (row.get("Suite") or "").strip()  # **Important: use Suite column**
                suite_size_raw = (row.get("Suite Size (if applicable)") or "").strip()
                if (not suite_id) or (suite_size_raw == "") or (suite_size_raw.upper() in ("NA", "N/A", "-", "NONE")):
                    print(f"Missing suite info for {building_name} {row.get('Room')}")
                    continue
                try:
                    capacity = int(float(suite_size_raw))
                except ValueError:
                    print(f"Bad suite size for {building_name} {row.get('Room')}: {suite_size_raw!r}")
                    continue
                key = (building_id, suite_id, base_gender)
                if key not in rooms:
                    rooms[key] = {"capacity": capacity, "available_beds": 1}
                else:
                    rooms[key]["available_beds"] += 1
                continue
            # --- Standard rooms ---
            room_id = (row.get("Suite") or "").strip()
            if not room_id:
                # If Suite is ever blank, you can decide to skip or fallback to Room.
                # Keeping strict to your current assumption: Suite is the ID.
                continue
            if "Single" in room_type:
                capacity = 1
            elif "Double" in room_type:
                capacity = 2
            elif "Triple" in room_type:
                capacity = 3
            elif "Quad" in room_type:
                capacity = 4
            else:
                print(f"Unknown room type for {building_name} {room_id}: {room_type}")
                continue
            key = (building_id, room_id, base_gender)
            if key not in rooms:
                rooms[key] = {"capacity": capacity, "available_beds": 1}
            else:
                rooms[key]["available_beds"] += 1
    # Aggregate fully-available rooms by building/base_gender/capacity
    avail_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (building_id, _room_id, base_gender), data in rooms.items():
        cap = data["capacity"]
        if data["available_beds"] == cap:
            avail_counts[building_id][base_gender][cap] += 1
            avail_counts[building_id][base_gender]["ALL"] += 1
    # Ensure all buildings appear (even if zero)
    for _bname, bid in building_lookup.items():
        if bid not in avail_counts:
            # initialize empty
            _ = avail_counts[bid]
    return avail_counts

# def totals_from_snapshot(snapshot_csv, building_lookup):
#     """
#     Computes TOTAL room/suite counts for each building across:
#       - base genders: COED/MALE/FEMALE
#       - capacities (room/suite size): integer capacity
#     This counts unique rooms/suites regardless of availability status.
#     Returns:
#       total_counts[building_id][base_gender][capacity] = total_rooms
#       total_counts[building_id][base_gender]["ALL"] = sum across all capacities
#     """
#     seen = set()
#     counted_rooms = set()
#     # We store (building_id, room_id, base_gender) -> capacity
#     room_caps = {}
#     with open(snapshot_csv, newline="", encoding="utf-8-sig") as f:
#         reader = csv.DictReader(f)
#         for row in reader:
#             profile = row.get("Room Profile")
#             if profile != "25-26 Spring Selection (Room)":
#                 continue
#             building_name = normalize_name(row.get("Building"))
#             if building_name not in building_lookup:
#                 continue
#             building_id = building_lookup[building_name]
#             base_gender = map_base_gender(row.get("Room Gender"))
#             if base_gender is None:
#                 continue
#             room_type = (row.get("Room Type") or "").strip()
#             room_str = (row.get("Room") or "")
#             # Grad Center
#             if "GRAD CENTER" in building_name:
#                 room_id = (row.get("Room") or "").strip()
#                 if not room_id:
#                     continue
#                 capacity = 1
#                 key = (building_id, room_id, base_gender)
#                 if key not in seen:
#                     seen.add(key)
#                     room_caps[key] = capacity
#                 continue
#             # Special GREG A 125
#             if "GREG A 125" in room_str:
#                 if "GREG A 125" not in counted_rooms:
#                     capacity = 9
#                     key = (building_id, "GREG A 125", base_gender)
#                     if key not in seen:
#                         seen.add(key)
#                         room_caps[key] = capacity
#                     for i in range(125, 133):
#                         counted_rooms.add(f"GREG A {i}")
#                 continue
#             # Suites
#             if "Suite" in room_type:
#                 suite_id = (row.get("Suite") or "").strip()
#                 suite_size_raw = (row.get("Suite Size (if applicable)") or "").strip()
#                 if (not suite_id) or (suite_size_raw == "") or (suite_size_raw.upper() in ("NA", "N/A", "-", "NONE")):
#                     continue
#                 try:
#                     capacity = int(float(suite_size_raw))
#                 except ValueError:
#                     continue
#                 key = (building_id, suite_id, base_gender)
#                 if key not in seen:
#                     seen.add(key)
#                     room_caps[key] = capacity
#                 continue
#             # Standard rooms
#             room_id = (row.get("Suite") or "").strip()
#             if not room_id:
#                 continue
#             if "Single" in room_type:
#                 capacity = 1
#             elif "Double" in room_type:
#                 capacity = 2
#             elif "Triple" in room_type:
#                 capacity = 3
#             elif "Quad" in room_type:
#                 capacity = 4
#             else:
#                 continue
#             key = (building_id, room_id, base_gender)
#             if key not in seen:
#                 seen.add(key)
#                 room_caps[key] = capacity
#     total_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
#     for (building_id, _room_id, base_gender), cap in room_caps.items():
#         total_counts[building_id][base_gender][cap] += 1
#         total_counts[building_id][base_gender]["ALL"] += 1
#     for _bname, bid in building_lookup.items():
#         if bid not in total_counts:
#             _ = total_counts[bid]
#     return total_counts

def aggregate_to_groups(counts_by_base):
    """
    Converts base counts (COED/MALE/FEMALE) into the 4 dropdown gender groups:
      COED, COEDMALE, COEDFEMALE, ALL
    Input:
      counts_by_base[building_id][base_gender][cap_or_ALL] = count
    Output:
      counts_by_group[building_id][group][cap_or_ALL] = count
    """
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for bid, by_base_gender in counts_by_base.items():
        # helper to get count safely
        def get(bg, cap):
            return by_base_gender.get(bg, {}).get(cap, 0)
        # Determine which capacity keys exist (include "ALL" plus any integers)
        cap_keys = set()
        for bg in BASE_GENDERS:
            cap_keys.update(by_base_gender.get(bg, {}).keys())
        if "ALL" not in cap_keys:
            cap_keys.add("ALL")
        for cap in cap_keys:
            coed = get("COED", cap)
            male = get("MALE", cap)
            female = get("FEMALE", cap)
            out[bid]["COED"][cap] = coed
            out[bid]["COEDMALE"][cap] = coed + male
            out[bid]["COEDFEMALE"][cap] = coed + female
            out[bid]["ALL"][cap] = coed + male + female
    return out

def slice_value(counts_by_group, bid, group, size_opt):
    """
    Returns the count for a (group, size_opt) slice.
    size_opt can be "ALL" or an int capacity.
    For size_opt="ALL", uses the precomputed "ALL" cap bucket.
    For numeric size_opt, uses that exact capacity bucket.
    """
    if size_opt == "ALL":
        return counts_by_group.get(bid, {}).get(group, {}).get("ALL", 0)
    return counts_by_group.get(bid, {}).get(group, {}).get(int(size_opt), 0)

def main():

    snapshots = get_snapshot_files_with_times(SNAPSHOT_FOLDER)
    if not snapshots:
        raise FileNotFoundError(f"No snapshot CSVs found in {SNAPSHOT_FOLDER} matching {SNAPSHOT_PREFIX}<m>_<d>_<HHMM>.csv")
    
    # Load lookup
    # building_lookup = load_building_lookup(LOOKUP_CSV)
    # building_id_to_name = load_building_id_to_name(LOOKUP_CSV)
    building_lookup, building_id_to_name = get_lookup(snapshots)

    ### BELOW: ADDED CODE - JSON OUTPUT
    ### PLEASE REVIEW

    output_data = {}
    for snapshot_time, snapshot_csv in snapshots:
        base_avail = process_snapshot(snapshot_csv, building_lookup)
        group_avail = aggregate_to_groups(base_avail)
        
        current_time = snapshot_time.isoformat()
        output_data[current_time] = {}

        for bid in building_lookup.values():
            building_name = building_id_to_name.get(bid)
            if not building_name:
                continue
            building_entry = {}
            total_available = slice_value(group_avail, bid, "ALL", "ALL")
            building_entry["Total Available Rooms"] = total_available

            for g in GENDER_GROUPS:
                building_entry[g] = {}
                for s in SIZE_OPTIONS:
                    val = slice_value(group_avail, bid, g, s)
                    building_entry[g][str(s)] = val
            output_data[current_time][building_name] = building_entry
    with open("housing_output.json", "w") as f:
        json.dump(output_data, f, indent=4)

    print("JSON export complete.")

# RUN -------------------------------------------------------
if __name__ == "__main__":
    main()