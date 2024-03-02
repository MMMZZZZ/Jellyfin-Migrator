# Jellyfin Migrator - Adjusts your Jellyfin database to run on a new system.
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


import pathlib
import sqlite3
import json
import hashlib
import binascii
import xml.etree.ElementTree as ET
from pathlib import Path
from shutil import copy
from time import time
from jellyfin_id_scanner import *
import datetime
from string import ascii_letters
import os


# Please specify a log file. The script is rather verbose and important
# errors might get lost in the process. You should definitely check the
# log file after running the script to see if there are any warnings or
# other important messages! Use f.ex. notepad++ (npp) to quickly
# highlight and remove bunches of uninteresting log messages:
#   * Open log file in npp
#   * Go to "Search -> Mark... (CTRL + M)"
#   * Tick "Bookmark Line"
#   * Search for strings that (only!) occur in the lines you want to
#     remove. All those lines should get a marking next to the line number.
#   * Go to "Search -> Bookmark -> Remove Bookmarked Lines"
#   * Repeat as needed
# Text encoding is UTF-8 (in npp selectable under "Encoding -> UTF-8")
log_file = "~/jf-migrator.log"


# These paths will be processed in the order they're listed here.
# This can be very important! F.ex. if specific subfolders go to a different
# place than stuff in the root dir of a given path, the subfolders must be
# processed first. Otherwise, they'll be moved to the same place as the other
# stuff in the root folder.
# Note: all the strings below will be converted to Path objects, so it doesn't
# matter whether you write / or \\ or include a trailing / . After the path
# replacement it will be converted back to a string with slashes as specified
# by target_path_slash.
# Note2: The AppDataPath and MetadataPath entries are only there to make sure
# the script recognizes them as actual paths. This is necessary to adjust
# the (back)slashes as specified. This can only be done on "known" paths
# because (back)slashes occur in other strings, too, where they must not be
# changed.
path_replacements = {
    # Self-explanatory, I guess. "\\" if migrating *to* Windows, "/" else.
    #"target_path_slash": "/",
    # Paths to your libraries
    #"D:/Serien": "/data/tvshows",
    #"F:/Serien": "/data/tvshows",
    #"F:/Filme": "/data/movies",
    #"F:/Musik": "/data/music",
    # Paths to the different parts of the jellyfin database. Determine these
    # by comparing your existing installation with the paths in your new
    # installation.
    "/etc/jellyfin": "/config",
    "/var/cache/jellyfin": "/config/cache",
    "/var/log/jellyfin": "/config/log",
    "/var/lib/jellyfin": "/config/data", # everything else: metadata, plugins, ...
    "/var/lib/jellyfin/transcodes": "/config/data/transcodes",
    "usr/lib/jellyfin-ffmpeg/ffmpeg": "usr/lib/jellyfin-ffmpeg/ffmpeg",
    "%MetadataPath%": "%MetadataPath%",
    "%AppDataPath%": "%AppDataPath%",
}


# This additional replacement dict is required to convert from the paths docker
# shows to jellyfin back to the actual file system paths to figure out where
# the files shall be copied. If relative paths are provided, the replacements
# are done relative to target_root.
#
# Even if you're not using docker or not using path mapping with docker,
# you probably do need to add some entries for accessing the media files
# and appdata/metadata files. This is because the script must read all the
# file creation and modification dates *as seen by jellyfin*.
# In that case and if you're sure that this list is 100% correct,
# *and only then* you can set "log_no_warnings" to True. Otherwise your logs
# will be flooded with warnings that it couldn't find an entry to modify the
# paths (which in that case would be fine because no modifications are needed).
#
# If you actually don't need any of this (f.ex. running the script in the
# same environment as jellyfin), remove all entries except for
#   * "log_no_warnings" (again, can be set to true if you're sure)
#   * "target_path_slash"
#   * %AppDataPath%
#   * %MetadataPath%.
fs_path_replacements = {
    "log_no_warnings": False,
    "target_path_slash": "/",
    "/config": "/",
    "%AppDataPath%": "/data/data",
    "%MetadataPath%": "/data/metadata",
    #"/data/tvshows": "Y:/Serien",
    #"/data/movies": "Y:/Filme",
    #"/data/music": "Y:/Musik",
}


# Original root only needs to be filled if you're using auto target paths _and_
# if your source dir doesn't match the source paths specified above in
# path_replacements.
# auto target will first replace source_root with original_root in a given path
# and then do the replacement according to the path_replacements dict.
# This is required if you copied your jellyfin DB to another location and then
# start processing it with this script.
original_root = Path("/var/lib/jellyfin")
source_root = Path("/var/lib/jellyfin")
target_root = Path("/docker/jellyfin-prod")


### The To-Do Lists: todo_list_paths, todo_list_id_paths and todo_list_ids.
# If your installation is like mine, you don't need to change the following three todo_lists.
# They contain which files should be modified and how.
# The migration is a multistep process:
#   1. Specified files are copied to the new location according to the path changes listed above
#   2. All paths within those files are updated to match the new location
#   3. The IDs that are used internally and are derived from the paths are updated
#      1. They occur in jellyfins file paths, so these paths are updated both on the disk and in the databases.
#      2. All remaining occurences of any IDs are updated throughout all files.
#   4. Now that all files are where and how they should be, update the file creation and modification
#      dates in the database.
# todo_list_paths is used for step 1 and 2
# todo_list_id_paths is used for step 3.1
# todo_list_ids is used for step 3.2
# table and columns for step 4 are hardcoded / determined automatically.
#
# General Notes:
#   * For step 1, "path_replacements" is used to determine the new file paths.
#   * In step 2, the "replacements" from the todo_list is used, but it makes no sense to set it
#     to something different from what you used in step 1.
#   * In step 3 the "replacements" entry in the todo_lists is auto-generated, no need to touch it either.
#
# Notes from my own jellyfin installation:
#   3.1 seems to be "ancestor-str" and "ancestor" formatted IDs only (see jellyfin_id_scanner for details on the format)
#   3.2 seems like only certain .db files contain them.
#   Search for "ID types occurring in paths" to find the place in the code
#   where you can select the types to include.
todo_list_paths = [
    {
        "source": source_root / "data/library.db",
        "target": "auto",                      # Usually you want to leave this on auto. If you want to work on the source file, set it to the same path (YOU SHOULDN'T!).
        "replacements": path_replacements,     # Usually same for all but you could specify a specific one per db.
        "tables": {
            "TypedBaseItems": {        # Name of the table within the SQLite database file
                "path_columns": [      # All column names that can contain paths.
                    "path",
                ],
                "jf_image_columns": [  # All column names that can jellyfins "image paths mixed with image properties" strings.
                    "Images",
                ],
                "json_columns": [      # All column names that can contain json data with paths.
                    "data",
                ],
            },
            "mediastreams": {
                "path_columns": [
                    "Path",
                ],
            },
            "Chapters2": {
                "jf_image_columns": [
                    "ImagePath",
                ],
            },
        },
    },
    {
        "source": source_root / "data/jellyfin.db",
        "target": "auto",
        "replacements": path_replacements,
        "tables": {
            "ImageInfos": {
                "path_columns": [
                    "Path",
                ],
            },
        },
    },
    # Copy all other .db files. Since it's copy-only (no path adjustments), omit the log output.
    {
        "source": source_root / "data/*.db",
        "target": "auto",
        "replacements": path_replacements,
        "copy_only": True,
        "no_log": True,
    },

    {
        "source": source_root / "plugins/**/*.json",
        "target": "auto",
        "replacements": path_replacements,
    },

    {
        "source": source_root / "config/*.xml",
        "target": "auto",
        "replacements": path_replacements,
    },

    {
        "source": source_root / "metadata/**/*.nfo",
        "target": "auto",
        "replacements": path_replacements,
    },

    {
        # .xml, .mblink, .collection files are here.
        "source": source_root / "root/**/*.*",
        "target": "auto",
        "replacements": path_replacements,
    },

    {
        "source": source_root / "data/collections/**/collection.xml",
        "target": "auto",
        "replacements": path_replacements,
    },

    {
        "source": source_root / "data/playlists/**/playlist.xml",
        "target": "auto",
        "replacements": path_replacements,
    },

    # Lastly, copy anything that's left. Any file that's already been processed/copied is skipped
    # ... you should delete the cache and the logs though.
    {
        "source": source_root / "**/*.*",
        "target": "auto",
        "replacements": path_replacements,
        "copy_only": True,
        "no_log": True,
    },
]

# See comment from todo_list_paths for details about this todo_list.
# "replacements" designates the source -> target path replacement dict.
# Same as for the matching job in todo_list_paths.
# The ID replacements are determined automatically.
todo_list_id_paths = [
    {
        "source": source_root / "data/library.db",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
        "tables": {
            "TypedBaseItems": {        # Name of the table within the SQLite database file
                "path_columns": [      # All column names that can contain paths.
                    "path",
                ],
                "jf_image_columns": [  # All column names that can jellyfins "image paths mixed with image properties" strings.
                    "Images",
                ],
                "json_columns": [      # All column names that can contain json data with paths OR IDs!!
                    "data",
                ],
            },
            "mediastreams": {
                "path_columns": [
                    "Path",
                ],
            },
            "Chapters2": {
                "jf_image_columns": [
                    "ImagePath",
                ],
            },
        },
    },

    {
        "source": source_root / "config/*.xml",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
    },

    {
        "source": source_root / "metadata/**/*",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
    },

    {
        # .xml, .mblink, .collection files are here.
        "source": source_root / "root/**/*",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
    },

    {
        "source": source_root / "data/**/*",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
    },
]

# See comment from todo_list_paths for details about this todo_list.
# "replacements" designates the source -> target path replacement dict.
# The ID replacements are determined automatically.
todo_list_ids = [
    {
        "source": source_root / "data/library.db",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
        "tables": {
            "AncestorIds": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [
                    "AncestorIdText",
                ],
                "ancestor-str-dash": [],
                "bin": [
                    "ItemId",
                    "AncestorId",
                ],
            },
            "Chapters2": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [],
                "ancestor-str-dash": [],
                "bin": [
                    "ItemId",
                ],
            },
            "ItemValues": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [],
                "ancestor-str-dash": [],
                "bin": [
                    "ItemId",
                ],
            },
            "People": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [],
                "ancestor-str-dash": [],
                "bin": [
                    "ItemId",
                ],
            },
            "TypedBaseItems": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [
                    "TopParentId",
                    "PresentationUniqueKey",
                    "SeriesPresentationUniqueKey",
                ],
                "ancestor-str-dash": [
                    "UserDataKey",
                    "ExtraIds",
                ],
                "bin": [
                    "guid",
                    "ParentId",
                    "SeasonId",
                    "SeriesId",
                    "OwnerId"
                ],
            },
            "UserDatas": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [],
                "ancestor-str-dash": [
                    "key",
                ],
                "bin": [],
            },
            "mediaattachments": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [],
                "ancestor-str-dash": [],
                "bin": [
                    "ItemId",
                ],
            },
            "mediastreams": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [],
                "ancestor-str-dash": [],
                "bin": [
                    "ItemId",
                ],
            },
        },
    },
    {
        "source": source_root / "data/playback_reporting.db",
        "target": "auto-existing",             # If you used "auto" in todo_list_paths, leave this on "auto-existing". Otherwise specify same path.
        "replacements": {"oldids": "newids"},  # Will be auto-generated during the migration.
        "tables": {
            "PlaybackActivity": {
                "str": [],
                "str-dash": [],
                "ancestor-str": [
                    "ItemId",
                ],
                "ancestor-str-dash": [],
                "bin": [],
            },
        },
    },
]


# Since library.db will be needed throughout the process, its location is stored
# here once it's been moved and updated with the new paths.
library_db_target_path = Path()
library_db_source_path = Path()


# Similarly, the IDs are used in "hard-to-reach" places and are thus global, too.
ids = dict()


# Custom print function that prints to both the console as well as to a log file
logging_newline = False
def print_log(*args, **kwargs):
    global log_file, logging_newline
    print(*args, **kwargs)

    # Each new line gets a timestamp. That requires tracking of (previous)
    # line endings though. This is not perfect, but perfectly fine for this
    # script.
    dt = ""
    if logging_newline:
        dt = "[" + datetime.datetime.now().isoformat(sep=" ") + "] "
    if kwargs.get("end", "\n") == "\n":
        logging_newline = True
    else:
        logging_newline = False
    with open(log_file, "a", encoding="utf-8") as f:
        print(dt, *args, **kwargs, file=f)


# Recursively replace all paths in "d" which can be
#  * a path object
#  * a path string
#  * a dictionary (only values are checked, no keys).
#  * a list
#  * any nested structure of the above.
#  * anything else is returned unmodified.
# Returns the (un)modified object as well as how many items have been modified or ignored.
def recursive_root_path_replacer(d, to_replace: dict):
    modified, ignored = 0, 0
    if type(d) is dict:
        for k, v in d.items():
            d[k], mo, ig = recursive_root_path_replacer(v, to_replace)
            modified += mo
            ignored  += ig
    elif type(d) is list:
        for i, e in enumerate(d):
            d[i], mo, ig = recursive_root_path_replacer(e, to_replace)
            modified += mo
            ignored  += ig
    elif type(d) is str or isinstance(d, pathlib.PurePath):
        try:
            p = Path(d)
        except:
            # This actually doesn't occur I think; Path() can pretty much convert any string into a Path
            # object (which is equivalent to saying it doesn't have any restrictions for filenames).
            ignored += 1
        else:
            found = False
            for src, dst in to_replace.items():
                if p.is_relative_to(src):
                    # This filters out all the "garbage" paths that actually were no paths to begin with
                    # and of course all the paths that are actually not relative to the src, dst couple
                    # currently checked.
                    p = dst / p.relative_to(src)
                    # I guess 99% of the users won't migrate _to_ windows but the script could generate
                    # \ paths anyways.
                    # p.as_posix() makes sure that we always get a string with "/". Otherwise, on windows,
                    # str(p) would automatically return "\" paths.
                    d = p.as_posix().replace("/", to_replace["target_path_slash"])
                    found = True
                    break
            if found:
                modified += 1
            else:
                ignored += 1
                # No need to consider all the Path("sometext") objects. This might not be 100%
                # accurate, but it eliminates 99.9999% of the false-positives. This output is
                # after all only to give you a hint whether you missed a path.
                # Also exclude URLs. Btw: pathlib can be quite handy for messing with URLs.
                if len(p.parents) > 1 \
                        and not d.startswith("https:") \
                        and not d.startswith("http:") \
                        and not to_replace.get("log_no_warnings", False):
                    print_log(f"No entry for this (presumed) path: {d}")
    return d, modified, ignored


# Almost the same as recursive_root_path_replacer but for replacing id parts somewhere in
# the paths including file names (can't use "is_relative_to" for checking).
# ID paths usually have the format '.../83/833addde992893e93d0572907f8b4cad/...'. It's
# important to note and change that parent folder with the firs byte of the id, too.
# Sometimes the parent folder is just single digit. This code handles any subsring that
# starts at the beginning of the id string.
def recursive_id_path_replacer(d, to_replace: dict):
    modified, ignored = 0, 0
    if type(d) is dict:
        for k, v in d.items():
            d[k], mo, ig = recursive_id_path_replacer(v, to_replace)
            modified += mo
            ignored  += ig
    elif type(d) is list:
        for i, e in enumerate(d):
            d[i], mo, ig = recursive_id_path_replacer(e, to_replace)
            modified += mo
            ignored  += ig
    elif type(d) is str or isinstance(d, pathlib.PurePath):
        try:
            p = Path(d)
        except:
            # This actually doesn't occur I think; Path() can pretty much convert any string into a Path
            # object (which is equivalent to saying it doesn't have any restrictions for filenames).
            ignored += 1
        else:
            found = False

            src, dst = "", ""

            if set(p.stem).issubset(set("0123456789abcdef-")):
                dst = to_replace.get(p.stem, "")
                if dst:
                    found = True
                    p = p.with_stem(dst)

            if not found:
                for part in p.parts[:-1]:
                    # Check if it can actually be an ID. If so, look it up (which is expensive).
                    if set(part).issubset(set("0123456789abcdef-")):
                        src = part
                        dst = to_replace.get(part, "")
                        if dst:
                            break
                if dst:
                    found = True
                    q = Path()
                    # Find folder as path object that needs to be changed
                    q = p
                    while p.name != src:
                        p = p.parent
                    # q becomes the part relative to the now determined p part (with p.stem = id)
                    q = q.relative_to(p)
                    p = p.with_name(dst)

                    # Check if the parent folder starts with byte(s) from the id
                    if src.startswith(p.parent.name):
                        # If so, move the already replaced part from p to q
                        q = p.name / q
                        p = p.parent
                        # Replace required number of bytes
                        p = p.with_name(dst[:len(p.name)])

                    # Merge q and p back together
                    p = p / q
            if found:
                modified += 1
                # I guess 99% of the users won't migrate _to_ windows but the script could generate
                # \ paths anyways.
                # p.as_posix() makes sure that we always get a string with "/". Otherwise, on windows,
                # str(p) would automatically return "\" paths.
                d = p.as_posix().replace("/", to_replace["target_path_slash"])
            else:
                ignored += 1
                # Unlike recursive_root_path_replacer, there is no need to warn the user about
                # potential paths that haven't been altered. In case you suspect that something is
                # overlooked, check out jellyfin_id_scanner.py.
                # ignored is purely maintained for signature compatibility with recursive_root_path_replacer.
    return d, modified, ignored


def update_db_table(
        file,
        replace_dict,
        replace_func,
        table,
        path_columns=(),
        json_columns=(),
        jf_image_columns=(),
        preview=False
):
    # Initialize local variables
    rows_count, modified, ignored = 0, 0, 0

    # Initialize sqlite3 objects
    con = sqlite3.connect(file)
    cur = con.cursor()

    # If only one item has been specified, convert it to a list with one item instead.
    if type(path_columns) not in (tuple, set, list):
        path_columns = [path_columns]
    if type(json_columns) not in (tuple, set, list):
        json_columns = [json_columns]
    if type(jf_image_columns) not in (tuple, set, list):
        jf_image_columns = [jf_image_columns]

    # This index will be used to separate the json from the path columns in the cur.execute
    # result further below.
    json_stop = len(json_columns)
    path_stop = json_stop + len(path_columns)

    # For the sql query the desired row names should be enclosed in ` ` and comma separated.
    # It's important to note that the json columns come first, followed by the path columns
    columns = ", ".join([f"`{e}`" for e in list(json_columns) + list(path_columns)] + list(jf_image_columns))

    # Query the unique IDs of all rows. Note: we cannot iterate over the rows using
    #     for row in cur.execute(get rows)
    # because the rows are modified by the loop, which breaks that iterator. Hence
    # the solution with reading all row ids and iterating over them instead.
    # Note: The cur.execute yields tuples with all the columns queried. Which means that
    # the array below actually contains _tuples_ with the id. This is however desirable
    # in our case; see below where id is used.
    todo = [rowid for rowid in cur.execute(f"SELECT `rowid` FROM `{table}`") if rowid[0]]
    rows_count = len(todo)
    t = time()
    for progress, id in enumerate(todo):
        # Print the progress every second. Note: this is the only usage of the "progress" variable.
        now = time()
        if now - t > 1:
            print_log(f"Progress: {progress} / {rows_count} rows")
            t = now

        # Query the columns we want to check/modify of the current row (selected by id).
        # Since the id is a binary object, it's not directly included in the f-string.
        # The cur.execute expects as second argument a _tuple_ with as many elements as
        # there are ? characters in the query string. This is the reason why we kept the
        # IDs as tuple. The only other place where this id is used is in the update query
        # at the end of the loop which requires - just like here - a tuple.
        row = [r for r in cur.execute(f"SELECT {columns} FROM `{table}` WHERE `rowid` = ?", id)]
        # This _should_ not occur, but I think I have seen it happen rarely. Safe is safe.
        if len(row) != 1:
            print_log(f"Error with rowid {id}! Resulted in {len(row)} rows instead of 1. Skipping.")
            continue
        # cur.execute returns a 2D tuple, containing all rows matching the query, and then
        # in each row the selected columns. We only selected a single row, hence row[0] is
        # all we care about (and all there is, see error handling above).
        # Secondly we want row to be modifiable, hence the conversion to a list.
        # list(row[0]) would btw return a list with 1 element: the tuple of the columns.
        row = [e for e in row[0]]

        # result has the structure {column_name: updated_data} which makes it very easy to build
        # the update query at the end.
        result = dict()

        # It's important to note that the tuple from cur.execute contains the columns _in the order
        # of the query string_. Therefore, we can separate json and path entries like this.
        jsons = row[:json_stop]
        paths = row[json_stop:path_stop]
        jf_imgs = row[path_stop:]
        for i, data in enumerate(jsons):
            if data:
                # There are numerous rows that have empty columns which would result in an error
                # from json.loads. Just skip them
                data = json.loads(data)
                data, mo, ig = replace_func(data, replace_dict)
                modified += mo
                ignored  += ig
                result[json_columns[i]] = json.dumps(data)
        for i, path in enumerate(paths):
            # One could also skip the empty objects here, but recursive_path_replacer handles them
            # just fine (leaves them untouched).
            path, mo, ig = replace_func(path, replace_dict)
            modified += mo
            ignored  += ig
            result[path_columns[i]] = path
        for i, imgs in enumerate(jf_imgs):
            # Jellyfin Image Metadata. Some DB entries look like this:
            #     %MetadataPath%\library\71\71d037e6e74015a5a6231ce1b7912acf\poster.jpg*637693022742223153*Primary*198*198*eJC5#hK#Dj9GR/V@j]xuX8NG0x+xgN%MxaX7spNGnitQ$kK0wyV@Rj # noqa
            # Yeah. That's a path and some other data within the same string, separated by *. More specifically:
            #     path * last modified date * image type * width * height * blur hash
            # where width, height, blur hash are apparently optional.
            # In theory, the * could occur as normal character within regular paths but it's unlikely.
            # Oh, and did I mention that such strings can contain multiple of these structures separated by a | ?
            # Source (Jellyfin Server 10.7.7): DeserializeImages, AppendItemImageInfo:
            # https://github.com/jellyfin/jellyfin/blob/045761605531f98c55f379ac9eb5b5b6004ef670/Emby.Server.Implementations/Data/SqliteItemRepository.cs#L1118 # noqa
            if not imgs:
                continue
            imgs = imgs.split("|")
            for j, img_properties in enumerate(imgs):
                if not img_properties:
                    continue
                img_properties = img_properties.split("*")
                # path = first property
                img_properties[0], mo, ig = replace_func(img_properties[0], replace_dict)
                imgs[j] = "*".join(img_properties)
                modified += mo
                ignored  += ig
            imgs = "|".join(imgs)
            result[jf_image_columns[i]] = imgs

        # Similar to the initial query we construct a comma separated list of the columns, only this
        # time we write
        #     `columnname` = ?
        # While the new values are all strings, the question mark avoids any issues with handling
        # backslashes etc. The library offers an easy, built-in way to do it so there's no reason
        # to mess with it myself.
        # Note that this relies on result.keys() and result.values() returning the entries in the
        # same order (which is guaranteed).
        # Note: it can happen that no changes are made at all. In this case we can abort here and
        #       go for the next job from the todo_list.
        if not result:
            continue
        keys = ", ".join([f"`{k}` = ?" for k in result.keys()])
        query = f"UPDATE `{table}` SET {keys} WHERE `rowid` = ?"

        # The query has a question mark for each updated column plus one for the id to identify
        # the correct row.
        args = tuple(result.values()) + id
        try:
            cur.execute(query, args)
        except Exception as e:
            # This was mainly for debugging purposes and shouldn't be reached anymore. Doesn't
            # hurt to have it though.
            print_log("Error:", e)
            print_log("Query:", query)
            print_log("Args: ", args)
            print_log(e)
            exit()
        else:
            if cur.rowcount < 1:
                # This was mainly for debugging purposes and shouldn't be reached anymore.
                # Doesn't hurt to have it though.
                print_log("No data modified!")
                print_log("Query:", query)
                print_log("Args: ", args)
                exit()
    print_log(f"Processed {rows_count} rows in table {table}. ")
    print_log(f"{modified} paths have been modified.")

    # Once again, this came from the development and is not required anymore, especially
    # since by default the script is working on copies of the original files.
    if not preview:
        # Write the updated database back to the file.
        con.commit()
    con.close()


# Walks through an XML file and checks *all* entries.
# WARNING: The documentation of this parser explicitly mentions that it's not hardened against
# known XML vulnerabilities. It is NOT suitable for unknown/unsafe XML files. Shouldn't be an
# issue here though.
def update_xml(file: Path, replace_dict: dict, replace_func) -> None:
    modified, ignored = 0, 0
    tree = ET.parse(file)
    root = tree.getroot()
    for el in root.iter():
        # Exclude a few tags known to contain no paths.
        # biography, outline: These often contain lots of text (= slow to process) and generate
        # false-positives for the missed path detection (see recursive_root_path_replacer)
        if el.tag in ("biography", "outline"):
            continue
        el.text, mo, ig = replace_func(el.text, replace_dict)
        modified += mo
        ignored  += ig
    print_log(f"Processed {ignored + modified} elements. {modified} paths have been modified.")
    tree.write(file)  # , encoding="utf-8")


# Remember if the user wants to ignore all future warnings.
user_wants_inplace_warning = True


def get_target(
        source: Path,
        target: Path,
        replacements: dict,
        no_log: bool = False,
) -> Path:
    # Not the cleanest solution for remembering it between function calls but good enough here.
    global user_wants_inplace_warning
#    global all_path_changes

    source = Path(source)
    target = Path(target)

    skip_copy = False

    # "auto" means the target path is generated by the same path replacement dictionary that's
    # also used to update all the path strings.
    # In this case we don't care about the stats returned by recursive_path_replacer, hence
    # the variable names.
    if len(target.parts) == 1 and target.name.startswith("auto"):
        if target.name == "auto-existing":
            skip_copy = True
        original_source = original_root / source.relative_to(source_root)
        target, idgaf1, idgaf2 = recursive_root_path_replacer(original_source, to_replace=replacements)
        target, idgaf1, idgaf2 = recursive_root_path_replacer(target, to_replace=fs_path_replacements)
        target = Path(target)
        if not target.is_absolute():
            if target.is_relative_to("/"):
                # Otherwise the line below will make target relative to the _root_ of target_root
                # instead of relative to target_root.
                target = target.relative_to("/")
            target = target_root / target

    # If source and target are the same there are two possibilities:
    #     1. The user actually wants to work on the given source files; maybe he already created
    #        a copy and directly pointed this script towards that copy.
    #     2. The user forgot that they shouldn't touch the original files.
    #     3. Something's wrong with the path replacement dict.
    # In any cases, the user is notified and can decide whether he wants to continue this time,
    # all the remaining times, too, or abort.
    #
    # Program: Are you sure? User: I don't know [yet]
    usure = "idk"
    if source == target:
        if user_wants_inplace_warning:
            while usure not in "yna":
                usure = input("Warning! Working on original file! Continue? [Y]es, [N]o, [A]lways ")
                # j is for the german "ja" which means yes.
                usure = usure[0].lower().replace("j", "y")
            if usure == "n":
                print_log("Skipping this file. If you want to abort the whole process, stop the script"
                          "with CTRL + C.")
                target = None
            elif usure == "a":
                # Don't warn about this anymore.
                user_wants_inplace_warning = False
    elif not skip_copy:
        if not target.parent.exists():
            target.parent.mkdir(parents=True)
        if not no_log:
            print_log("Copying...", target, end=" ")
        copy(source, target)
        if not no_log:
            print_log("Done.")
    return target


def process_file(
        source: Path,
        target: Path,
        replacements: dict,
        replace_func,
        tables:dict = None,
        copy_only: bool = False,
        no_log: bool = False,
) -> None:
    if tables is None:
        tables = dict()

    # What do you want me to do with no input?
    if not target:
        return

    # Files only.
    if target.is_dir():
        return

    if not no_log:
        print_log("Processing", target)

    if copy_only:
        # No need to do any further checks.
        return
    elif target.suffix == ".db":
        # If it's "library.db", save it for later (see comment at declaration):
        if target.name == "library.db":
            global library_db_source_path, library_db_target_path
            library_db_source_path = source
            library_db_target_path = target
        # sqlite file. In this case table specifies which tables within that file have columns to check.
        # Iterate over those.
        for table, kwargs in tables.items():
            print_log("Processing table", table)
            # The remaining function arguments (**kwards) contain the details about the columns to process.
            # See update_db_table and/or the todo_list.
            update_db_table(file=target, replace_dict=replacements, replace_func=replace_func, table=table, **kwargs)
    elif target.suffix == ".xml" or target.suffix == ".nfo":
        update_xml(file=target, replace_dict=replacements, replace_func=replace_func)
    elif target.suffix == ".mblink":
        # .mblink files only contain a path, nothing else.
        with open(target, "r", encoding="utf-8") as f:
            path = f.read()
        path, modified, ignored = replace_func(path, replacements)
        print_log(f"Processed {modified + ignored} paths, {modified} paths have been modified.")
        with open(target, "w", encoding="utf-8") as f:
            f.write(path)
    elif target.suffix == ".json":
        # There are also json files with the ending .js but I haven't found any with paths.
        # Load the file by the json module (resulting in a dict or list object) and process
        # them by recursive_path_replacer which handles these structures.
        with open(target, "r", encoding="utf-8") as f:
            j = json.load(f)
        j, modified, ignored = replace_func(j, replacements)
        print_log(f"Processed {modified + ignored} paths, {modified} paths have been modified.")
        with open(target, "w", encoding="utf-8") as f:
            # indent 2 seems to be the default formatting for jellyfin json files.
            json.dump(j, f, indent=2)

    # If we're updating path ids we also need to check the paths of the files themselves
    # and move them if they're relative to a path.
    # This obviously leaves empty folders behind, which are cleaned up afterwards.
    if replace_func == recursive_id_path_replacer:
        source = target
        target, modified, ignored = recursive_id_path_replacer(source, replacements)
        if modified:
            print_log("Changing ID in filepath: ->", target)
            target = Path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)


# Processes the todo_list.
# It handles potential wildcards in the file paths and keeps track
# which files have already been processed. This allows you to have an
# automatic, wildcard copy in your todo_list that just copies the files
# to the (modified) destinations without processing them and without
# modifying those that have already been copied _and_ modified.
# Obviously this requires you to have the files that need processing
# first in the todo_list and only then the wildcard copies.
#
# lst: job list
# process_func: function to apply to jobs of lst.
# replace_func: function used by process_func to do the replacing of paths, ...
def process_files(lst: list, process_func, replace_func, path_replacements):
    done = set()
    for job in lst:
        if "no_log" not in job:
            job["no_log"] = False
        source = job["source"]
        print_log(f"Current job from todo_list: {source}")
        if "*" in str(source):
            # Path has wildcards, process all matching files.
            #
            # Ironically Path.glob can't handle Path objects, hence the need
            # to convert them to a string...
            # It is expected that all these paths are relative to source_root.
            source = source.relative_to(source_root)
            for src in source_root.glob(str(source)):
                if src.is_dir():
                    continue
                if src in done:
                    # File has already been processed by this script.
                    continue
                done.add(src)

                target = get_target(
                    source=src,
                    target=job["target"],
                    replacements=path_replacements,
                    no_log=job["no_log"],
                )

                # pass the job as is but with non-wildcard source path.
                process_func(
                    replace_func=replace_func,
                    source=src,
                    target=target,
                    **{k: v for k, v in job.items() if k not in ("source", "target")},
                )
        else:
            # No wildcards, process the path directly - if it hasn't already
            # been processed.
            if source in done:
                continue
            done.add(source)

            target = get_target(
                source=source,
                target=job["target"],
                replacements=path_replacements,
                no_log=job["no_log"],
            )

            process_func(
                replace_func=replace_func,
                source=source,
                target=target,
                **{k: v for k, v in job.items() if k not in ("source", "target")},
            )
        print_log("")


# Note: The .NET .Unicode method encodes as UTF16 little endian:
# https://docs.microsoft.com/en-us/dotnet/api/system.text.encoding.unicode?view=net-6.0
def get_dotnet_MD5(s: str):
    return hashlib.md5(s.encode("utf-16-le")).digest()


# Derived/copied from update_db_table. I couldn't see a good way to do this without
# copying. The data structures and processing are too different for path and id jobs.
# Note: kwargs is due to how process_files works. It passes a lot of stuff from the
# job list that's not needed here.
def update_db_table_ids(
        source,
        target,
        tables,
        preview=False,
        **kwargs
):
    global ids

    print_log("Updating Item IDs in database... ")

    # Initialize sqlite3 objects
    con = sqlite3.connect(target)
    cur = con.cursor()

    updated_ids_count = 0
    # That's a very nested loop and could probably be written more efficiently using
    # multiprocessing and more advanced sqlite queries.
    for table, columns_by_id_type in tables.items():
        for id_type, columns in columns_by_id_type.items():
            for column in columns:
                print_log(f"Updating {column} IDs in table {table}...")
                # See comment about iterating over rows while modifying them in update_db_table.
                rows = [r for r in cur.execute(f"SELECT DISTINCT `{column}` from `{table}`")]
                progress = 0
                rowcount = len(rows)
                t = time()
                for old_id, in rows:
                    progress += 1
                    # Print the progress every second. Note: this is the only usage of the "progress" variable.
                    now = time()
                    if now - t > 1:
                        print_log(f"Progress: {progress} / {rowcount} rows")
                        t = now
                    if old_id in ids[id_type]:
                        new_id = ids[id_type][old_id]
                        try:
                            cur.execute(f"UPDATE `{table}` SET `{column}` = ? WHERE `{column}` = ?", (new_id, old_id))
                        except sqlite3.IntegrityError:
                            col_names  = [x[0] for x in cur.execute(f"SELECT name FROM PRAGMA_TABLE_INFO('{table}')")]
                            rows = [x for x in cur.execute(f"SELECT * FROM `{table}` WHERE `{column}` = ?", (old_id,))]
                            rows = [dict(zip(col_names, row)) for row in rows]
                            print_log(f"Encountered {len(rows)} duplicated entries")
                            for i, row in enumerate(rows):
                                print_log(f"Deleting ({i+1}/{len(rows)}): ", row)
                            cur.execute(f"DELETE FROM `{table}` WHERE `{column}` = ?", (old_id,))
                        updated_ids_count += 1

    # Once again, this came from the development and is not required anymore, especially
    # since by default the script is working on copies of the original files.
    if not preview:
        # Write the updated database back to the file.
        con.commit()
    con.close()
    print_log(f"{updated_ids_count} IDs updated.")


def get_ids():
    global library_db_target_path, ids

    con = sqlite3.connect(library_db_target_path)
    cur = con.cursor()

    id_replacements_bin = dict()
    for guid, item_type, path in cur.execute("SELECT `guid`, `type`, `Path` FROM `TypedBaseItems`"):
        if not path or path.startswith("%"):
            continue

        # Source: https://github.com/jellyfin/jellyfin/blob/7e8428e588b3f0a0574da44081098c64fe1a47d7/Emby.Server.Implementations/Library/LibraryManager.cs#L504 # noqa
        new_guid = get_dotnet_MD5(item_type + path)
        # Omit IDs that haven't changed at all. Happens if not _all_ paths are modified
        if new_guid != guid:
            id_replacements_bin[guid] = new_guid

    ### Adapted from jellyfin_id_scanner
    id_replacements_str               = {bid2sid(k): bid2sid(v) for k, v in id_replacements_bin.items()}
    id_replacements_str_dash          = {sid2did(k): sid2did(v) for k, v in id_replacements_str.items()}
    id_replacements_ancestor_str      = {convert_ancestor_id(k): convert_ancestor_id(v) for k, v in id_replacements_str.items()}
    id_replacements_ancestor_bin      = {sid2bid(k): sid2bid(v) for k, v in id_replacements_ancestor_str.items()}
    id_replacements_ancestor_str_dash = {sid2did(k):sid2did(v) for k, v in id_replacements_ancestor_str.items()}

    ids = {
        "bin": id_replacements_bin,
        "str": id_replacements_str,
        "str-dash": id_replacements_str_dash,
        "ancestor-bin": id_replacements_ancestor_bin,
        "ancestor-str": id_replacements_ancestor_str,
        "ancestor-str-dash": id_replacements_ancestor_str_dash,
    }
    ### End of adapted code

    # Check for collisions between old and new ids in both the normal and ancestor format.
    # If there are collisions, get the (new) filepaths causing them
    uniques = set()
    duplicates = list()
    for id in id_replacements_str.values():
        if id in uniques:
            duplicates.append(id)
        else:
            uniques.add(id)

    # if there are duplicates, find the matching old_ids to query the lines from the database
    if duplicates:
        old_ids = []
        for k, v in id_replacements_str.items():
            if v in duplicates:
                old_ids.append(sid2bid(k))

        duplicates_new = [next(cur.execute("SELECT `guid`, `Path` FROM `TypedBaseItems` WHERE `guid` = ?", (guid,))) for guid in old_ids]
        # also fetch the old paths for better understanding/debugging
        con.close()
        con = sqlite3.connect(library_db_source_path)
        cur = con.cursor()
        duplicates_old = [next(cur.execute("SELECT `guid`, `Path` FROM `TypedBaseItems` WHERE `guid` = ?", (guid,))) for guid in old_ids]
        duplicates_old = dict(duplicates_old)
        con.close()

        print_log(f"Warning! {len(duplicates)} duplicates detected within new ids. This indicates that you're "
                  f"merging media files from different directories into fewer ones. If that's the case for all the "
                  f"collisions listed below, you can likely ignore this warning, otherwise recheck your path settings. "
                  f"IMPORTANT: The duplicated entries will be removed from the database. You got a backup of the "
                  f"database, right?")
        print_log("Duplicates: ")
        for id, newpath in duplicates_new:
            print_log(f"  Item ID: {bid2sid(id)},  Paths (old -> new): {duplicates_old[id]} -> {newpath}")
        input("Press Enter to continue or CTRL+C to abort. ")

    return ids


def update_ids():
    return


def jf_date_str_to_python_ns(s: str):
    # Python datetime has only support for microseconds because of resolution
    # problems. To convert from a date+time to ticks, the fractional seconds
    # part doesn't matter anyway (it remains the same). Hence, it's cut off
    # and added back later.
    subseconds = "0"
    if "." in s:
        s, subseconds = s.rsplit(".", 1)
    # In case subseconds has a higher resolution than 100ns and/or additional
    # information (f.ex. timezone, which is known to be UTC+00:00 for jellyfin),
    # Strip all of it.
    # Add trailing zeros til the ns digit, then convert to int, and we have ns.
    subseconds = int(subseconds.split("+")[0].rstrip(ascii_letters).ljust(9, "0"))
    # Add explicit information about the timezone (UTC+00:00)
    s += "+00:00"
    t = int(datetime.datetime.fromisoformat(s).timestamp())
    # Convert to ns
    t *= 1000000000
    t += subseconds
    return t


# Convert a _python_ timestamp (float seconds since epoch, which is os dependent)
# to a ISO like date string as found in the jellyfin database. I have no idea
# if this works for all OS'es in all timezones. Very likely not but that whole
# topic is about as much of a mess as jellyfin's databases. If you got any issues,
# I'm sorry. If you find a solution, them, please let me know!
def get_datestr_from_python_time_ns(time_ns: int):
    # Datetime has no support for sub-microsecond resolution (which is required here).
    # Doesn't matter anyway, we can add the whole sub-second part afterwards.
    time_s = time_ns // 1000000000
    time_frac_s_100ns = (time_ns // 100) % 10000000
    timestamp = datetime.datetime.utcfromtimestamp(time_s).isoformat(sep=" ", timespec="seconds")
    # Add back the sub-seconds part and the UTC time zone
    timestamp += "." + str(time_frac_s_100ns).rjust(7, "0").rstrip("0") + "Z"
    return timestamp


def delete_empty_folders(dir:str):
    dir = Path(dir)

    done = False
    while not done:
        done = True
        for p in dir.glob("**"):
            if not list(p.iterdir()):
                print_log("Removing empty folder", p)
                p.rmdir()
                done = False


def update_file_dates():
    global library_db_target_path, fs_path_replacements

    print_log("Updating file dates... Note: Reading file dates seems to be quite slow. "
              "This will take a couple minutes")

    con = sqlite3.connect(library_db_target_path)
    cur = con.cursor()

    rows = [r for r in cur.execute("SELECT `rowid`, `Path`, `DateCreated`, `DateModified` FROM `TypedBaseItems`")]

    progress = 0
    rowcount = len(rows)
    t = time()

    for rowid, target, date_created, date_modified in rows:
        progress += 1
        # Print the progress every second. Note: this is the only usage of the "progress" variable.
        now = time()
        if now - t > 1:
            print_log(f"Progress: {progress} / {rowcount} rows")
            t = now

        if not target:
            continue
        # Determine file path as seen by this script (see fs_path_replacements for details)
        # Code taken from get_target
        target, idgaf1, idgaf2 = recursive_root_path_replacer(target, to_replace=fs_path_replacements)
        target = Path(target)
        if not target.is_absolute():
            if target.is_relative_to("/"):
                # Otherwise the line below will make target relative to the _root_ of target_root
                # instead of relative to target_root.
                target = target.relative_to("/")
            target = target_root / target
        # End of code taken from get_target

        if not target.exists():
            print_log("File doesn't seem to exist; can't update its dates in the database: ", target)
            continue

        date_created_ns  = jf_date_str_to_python_ns(date_created)
        date_modified_ns = jf_date_str_to_python_ns(date_modified)

        if date_created_ns >= 0 and date_modified_ns >= 0:
            continue

        filestats = os.stat(target)

        if date_created_ns < 0:
            new_date_created = get_datestr_from_python_time_ns(filestats.st_ctime_ns)
            cur.execute("UPDATE `TypedBaseItems` SET `DateCreated` = ? WHERE `rowid` = ?",
                        (new_date_created, rowid))
        if date_modified_ns < 0:
            new_date_modified = get_datestr_from_python_time_ns(filestats.st_mtime_ns)
            cur.execute("UPDATE `TypedBaseItems` SET `DateModified` = ? WHERE `rowid` = ?",
                        (new_date_modified, rowid))

    con.commit()
    print_log("Done.")


if __name__ == "__main__":
    print_log("")
    print_log("Starting Jellyfin Database Migration")

    ### Copy relevant files and adjust all paths to the new locations.
    process_files(
        todo_list_paths,
        process_func=process_file,
        replace_func=recursive_root_path_replacer,
        path_replacements=path_replacements,
    )

    ### Update IDs
    # Generate IDs based on those new paths and save them in the global variable
    get_ids()
    # ID types occurring in paths (<- search for that to find another comment with more details if you missed it)
    # Include/Exclude types (see get_ids) to specify which are used for looking through paths.
    # Currently, all are included, just to be safe.
    id_replacements_path = {**ids["ancestor-str"], **ids["ancestor-str-dash"], **ids["str"], **ids["str-dash"],
                            "target_path_slash": path_replacements["target_path_slash"]}

    # To (mostly) reuse the same functions from step 1, the replacements dict needs to be updated with
    # id_replacements_path. It can't be replaced since it's also used to find the files (which uses the
    # same source -> target processing/conversion as step 1). In theory this alters the process since
    # the dict used to convert from source -> target is different, in reality, this is not an issue,
    # since step 1 only processes the roots of the paths (which cannot be similar to anything in
    # id_replacements_path).
    for i, job in enumerate(todo_list_id_paths):
        todo_list_id_paths[i]["replacements"] = id_replacements_path

    # Replace all paths with ids - both in the file system and within files.
    process_files(
        todo_list_id_paths,
        process_func=process_file,
        replace_func=recursive_id_path_replacer,
        path_replacements={**path_replacements, **id_replacements_path},
    )
    # Clean up empty folders that may be left behind in the target directory
    #delete_empty_folders(target_root)

    # Replace remaining ids.
    process_files(
        todo_list_ids,
        process_func=update_db_table_ids,
        replace_func=None,
        path_replacements = path_replacements,
    )

    # Finally, update the file dates in the db.
    update_file_dates()

    print_log("")
    print_log("Jellyfin Database Migration complete.")
