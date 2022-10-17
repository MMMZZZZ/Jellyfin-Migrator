# Jellyfin ID Scanner - Searches through database files for occurences of jellyfin IDs
# Copyright (C) 2022  Max Zuidberg
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import sqlite3
import binascii
from multiprocessing import Pool
import argparse


ids = dict()


# Functions used for converting IDs between the various formats. See load_ids
def convert_ancestor_id(id: str):
    # Group by bytes
    id = [id[i : i+2] for i in range(0, len(id), 2)]

    # Reorder (not sure why it's done like this but it is)
    # and convert back to string.
    # Note that only the first 8 bytes are rearranged, the others remain.
    byte_order = (3, 2, 1, 0, 5, 4, 7, 6)
    swapped_id = [id[i] for i in byte_order]
    swapped_id.extend(id[8:])
    return "".join(swapped_id)
def bid2sid(id): return binascii.b2a_hex(id).decode("ascii")
def sid2bid(id): return binascii.a2b_hex(id)
def sid2did(id): return "-".join([id[:8], id[8:12], id[12:16], id[16:20], id[20:]])
def sid2pid(id): return f"{id[:2]}/{id}"


# Loads all IDs from jellyfins library.db file.
# Additionally, it generates all the variants of each ID that may be used.
# More details on the formats can be found in comments in jellyfin_migrator.py
def load_ids(library_db:str):
    con = sqlite3.connect(library_db)
    cur = con.cursor()
    id_replacements_bin = [x[0] for x in cur.execute("SELECT `guid` FROM `TypedBaseItems`")]
    con.close()

    id_replacements_str               = [bid2sid(k) for k in id_replacements_bin]
    id_replacements_str_dash          = [sid2did(k) for k in id_replacements_str]
    id_replacements_str_ancestor      = [convert_ancestor_id(k) for k in id_replacements_str]
    id_replacements_bin_ancestor      = [sid2bid(k) for k in id_replacements_str_ancestor]
    id_replacements_str_ancestor_dash = [sid2did(k) for k in id_replacements_str_ancestor]

    ids = {
        "bin": id_replacements_bin,
        "str": id_replacements_str,
        "str-dash": id_replacements_str_dash,
        "ancestor-bin": id_replacements_bin_ancestor,
        "ancestor-str": id_replacements_str_ancestor,
        "ancestor-str-dash": id_replacements_str_ancestor_dash,
    }

    print(f"{len(id_replacements_bin)} IDs loaded from library.db")

    byteids = dict()
    for k, v in ids.items():
        if "bin" in k:
            byteids[k] = v
        else:
            byteids[k] = [s.encode("ascii") for s in v]
    ids = {k: v for k, v in ids.items() if "bin" not in k}
    return ids, byteids


# Loads the name of all tables in a sqlite db file as well as each one's columns.
def load_db_tables_columns(path_to_db):
    con = sqlite3.connect(path_to_db)
    cur = con.cursor()

    # Get all table names. The query will also return index stuff that isn't required. It's (mostly) filtered.
    table_names = [
        x[0] for x in cur.execute("SELECT name from sqlite_master")
        if not x[0].startswith("idx")
        and not x[0].startswith("sqlite_autoindex")
        and x[0][-6:-1].lower() != "index"
    ]

    # For each table, get all column names.
    table_info = {n: [x[0] for x in cur.execute(f"SELECT name FROM PRAGMA_TABLE_INFO('{n}')")] for n in table_names}

    con.close()

    return table_info


# Returns a list with all rows of all tables, no column excluded.
def load_all_rows(path_to_db):
    table_info = load_db_tables_columns(path_to_db)

    con = sqlite3.connect(path_to_db)
    cur = con.cursor()

    rows = []

    for table, columns in table_info.items():
        for column in columns:
            col_values = {x[0] for x in cur.execute(f"SELECT `{column}` FROM `{table}`") if x[0]}
            if not col_values:
                continue
            rows.append([table, column, col_values])

    con.close()

    return rows


# Scans a job (entire column) for occurrences of any ID in binary (BLOB) format.
# Binary IDs are always "pure", meaning not embedded within a string with other stuff.
def check_bin_ids(job):
    table, column, column_values, byteids = job
    id_types = set()

    if not type(next(iter(column_values))) is bytes:
        return

    for id_type, values in byteids.items():
        for value in values:
            if value in column_values:
                id_types.add(id_type + " (pure)")
    if id_types:
        result = table, column, id_types
        return result


# Scans a job (entire column) for occurrences of any ID in any string format.
# Column entries can either be pure (just the ID string) or have an ID string
# embedded into other stuff (JSON string f.ex.).
# The function also checks if more than one ID format is found within the column.
def check_embedded_id_types(job):
    table, column, column_values, ids = job
    id_types = set()
    check_for_next_type = False

    for id_type, values in ids.items():
        for value in values:
            for column_type, column_value in column_values:
                if value in column_value:
                    id_types.add(f"{id_type} ({column_type})")
                    check_for_next_type = True
                if check_for_next_type:
                    break
            if check_for_next_type:
                break
    if id_types:
        result = table, column, id_types
        return result


# Takes an arbitrary string or byte-string and returns a set with all the chunks
# from it that could be an ID: sequences of >=32 hexadecimal digits
# (plus the - symbol used in some ID formats).
def get_id_candidates(s):
    result = ""
    if type(s) is bytes:
        result = "".join(chr(c) if c in b"0123456789abcdef-" else " " for c in s)
    elif type(s) is str:
        result = "".join(c if c in "0123456789abcdef-" else " " for c in s)

    # check if it's a pure id or an id embedded within other data.
    column_type = "embedded"
    if result == s:
        column_type = "pure"

    result = result.split(" ")
    result = {piece for piece in result if len(piece) >= 32}
    return column_type, result


if __name__ == "__main__":
    desc = """
    Jellyfin ID Scanner - Searches through database files for occurences of jellyfin IDs
    Copyright (C) 2022  Max Zuidberg
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    """
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--library-db", type=str, required=True,
                        help="Path to Jellyfins library.db file. Always required")
    parser.add_argument("--scan-db", type=str, required=True,
                        help="Path to the db file to scan. Can also be library.db or f.ex. a db file from a plugin. "
                             "Other file types are currently unsupported but should be easy to add. Always required")

    args = parser.parse_args()

    print("Loading IDs from library.db")
    ids, byteids = load_ids(args.library_db)

    print("Loading db to scan")
    jobs = [row + [byteids] for row in load_all_rows(args.scan_db)]
    values = sum([len(job[2]) for job in jobs])
    print(f"Loaded {values} values.")

    print("Scanning... This will take a while. Example: scanning a library.db file with 78k IDs "
          "and 1.2M entries took about 5 minutes.")
    results = []
    with Pool() as p:
        results.extend(p.map(check_bin_ids, jobs, chunksize=64))

    # Search through all values for ID occurences. to speed this up,
    # remove anything that for sure doesn't match, like shorter items or non alphanum chars.
    for i, job in enumerate(jobs):
        col_values = job[2]
        with Pool() as p:
            col_values = [x for x in p.imap_unordered(get_id_candidates, col_values, chunksize=64) if x[1]]
        jobs[i] = (job[0], job[1], col_values, ids)

    check_embedded_id_types(jobs[i])
    with Pool() as p:
        results.extend(p.map(check_embedded_id_types, jobs, chunksize=1))

    # Remove empty results, sort them for convenience, and format them for pretty printing.
    results = [[x[0], x[1], ", ".join(x[2])] for x in results if x]
    results.sort(key=lambda x:"".join(x))
    results = [["Table", "Column", "ID Type(s) found"]] + results
    lengths = [max([len(x) for x in col]) for col in zip(*results)]
    results = [[x[i].ljust(lengths[i] + 1) for i in range(len(x))] for x in results]
    for x in results:
        print(*x)
