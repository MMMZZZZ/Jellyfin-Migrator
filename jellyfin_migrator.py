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
import xml.etree.ElementTree as ET
from pathlib import Path
from shutil import copy
from time import time


# These paths will be processed in the order they're listed here.
# This can be very important! F.ex. if specific subfolders go to a different
# place than stuff in the root dir of a given path, the subfolders must be
# processed first. Otherwise they'll be moved to the same place as the other
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
db_path_replacements = {
    # Self explanatory, I guess.
    "target_path_slash": "/",
    # Paths to your libraries
    "D:/Serien": "/data/tvshows",
    "F:/Filme": "/data/movies",
    "F:/Musik": "/data/music",
    # Paths to the different parts of the jellyfin database. Determine these
    # by comparing your existing installation with the paths in your new
    # installation.
    "C:/ProgramData/Jellyfin/Server/config": "/config",
    "C:/ProgramData/Jellyfin/Server/cache": "/config/cache",
    "C:/ProgramData/Jellyfin/Server/log": "/config/log",
    "C:/ProgramData/Jellyfin/Server": "/config/data", # everything else: metadata, plugins, ...
    "I:/Jellyfin/Server/transcodes": "/config/data/transcodes",
    "C:/Program Files/Jellyfin/Server/ffmpeg.exe": "/usr/lib/jellyfin-ffmpeg/ffmpegs",
    "%MetadataPath%": "%MetadataPath%",
    "%AppDataPath%": "%AppDataPath%",
}


# This additional replacement dict is required to convert from the paths docker
# shows to jellyfin back to the actual file system paths to figure out where
# the files shall be copied. These replacements are done relative to target_root.
# Not required if:
#   * You're not targetting docker
#   * Docker is configured to not map any paths differently than how they are
#     on the disk
# In these cases remove all entries except for "target_path_slash".
fs_path_replacements = {
    "target_path_slash": "/",
    "/config": "/"
}


# Original root only needs to be filled if you're using auto target paths _and_
# if your source dir doesn't match the source paths specified above in
# path_replacements.
# auto target will first replace source_root with original_root in a given path
# and then do the replacement according to the path_replacements dict.
# This is required if you copied your jellyfin DB to another location and then
# start processing it with this script.
original_root = Path("C:/ProgramData/Jellyfin/Server")
source_root = Path("C:/ProgramData/Jellyfin/Server")
target_root = Path("C:/Users/Max/Desktop/Jellyfin-patched")


todo_list = [
    {
        "source": source_root / "data/library.db",
        "target": "auto",                      # Usually you want to leave this on auto. If you want to work on the source file, set it to the same path (YOU SHOULDN'T!).
        "replacements": db_path_replacements,  # Usually same for all but you could specify a specific one per db.
        "tables": {
            "TypedBaseItems": {        # Name of the table within the SQLite database file
                "id_column":           # Preferably some sort of uuid, otherwise any other entry that uniquely identifies this line.
                    "guid",
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
                "id_column":
                    "Path",
                "path_columns": [
                    "Path",
                ],
            },
            "Chapters2": {
                "id_column":
                    "ItemId",
                "jf_image_columns": [
                    "ImagePath",
                ],
            },
        },
    },

    {
        "source": source_root / "data/jellyfin.db",
        "target": "auto",
        "replacements": db_path_replacements,
        "tables": {
            "ImageInfos": {
                "id_column":
                    "UserId",
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
        "replacements": db_path_replacements,
        "copy_only": True,
        "no_log": True,
    },

    {
        "source": source_root / "plugins/**/*.json",
        "target": "auto",
        "replacements": db_path_replacements,
    },

    {
        "source": source_root / "config/*.xml",
        "target": "auto",
        "replacements": db_path_replacements,
    },

    {
        "source": source_root / "metadata/**/*.nfo",
        "target": "auto",
        "replacements": db_path_replacements,
    },

    {
        # .xml, .mblink, .collection files are here.
        "source": source_root / "root/**/*.*",
        "target": "auto",
        "replacements": db_path_replacements,
    },

    {
        "source": source_root / "data/collections/**/collection.xml",
        "target": "auto",
        "replacements": db_path_replacements,
    },

    {
        "source": source_root / "data/playlists/**/playlist.xml",
        "target": "auto",
        "replacements": db_path_replacements,
    },

    # Lastly, copy anything that's left. Any file that's already been processed/copied is skipped
    {
        "source": source_root / "**/*.*",
        "target": "auto",
        "replacements": db_path_replacements,
        "copy_only": True,
        "no_log": True,
    },
]


def recursive_path_replacer(d, to_replace:dict):
    # d can be a list, a dictionary, or a string. anything else will be returned unmodified.
    # In the case of a list, all entries are checked recursively. Same for the _values_
    # of the dictionary. This assumes of couse that there are no paths in the keys which
    # should be a rather safe assumption.
    # Additionally, the script keeps track of how many strings have been modified or not.
    modified, ignored = 0, 0
    if type(d) is dict:
        for k, v in d.items():
            d[k], mo, ig = recursive_path_replacer(v, to_replace)
            modified += mo
            ignored  += ig
    elif type(d) is list:
        for i, e in enumerate(d):
            d[i], mo, ig = recursive_path_replacer(e, to_replace)
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
                        and not d.startswith("https:")\
                        and not d.startswith("http:"):
                    print(f"No entry to change this (presumed) path: {d}")
    return d, modified, ignored


def update_db_table(file, replace_dict, table, id_column, path_columns=(), json_columns=(), jf_image_columns=(), preview=False):
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
    # because the rows are modified by the loop, which breaks that iterator.
    # Hence the solution with reading all row ids and iterating over them instead.
    # Note: The cur.execute yields tuples with all the columns queried. Which means that
    # the array below actually contains _tuples_ with the id. This is however desirable
    # in our case; see below where id is used.
    todo = [id for id in cur.execute(f"SELECT `{id_column}` FROM `{table}`") if id[0]]
    rows_count = len(todo)
    t = time()
    for progress, id in enumerate(todo):
        # Print the progress every second. Note: this is the only usage of the "progress" variable.
        now = time()
        if now - t > 1:
            print(f"Progress: {progress} / {rows_count} rows")
            t = now

        # Query the columns we want to check/modify of the current row (selected by id).
        # Since the id is a binary object, it's not directly included in the f-string.
        # The cur.execute expects as second argument a _tuple_ with as many elements as
        # there are ? characters in the query string. This is the reason why we kept the
        # IDs as tuple. The only other place where this id is used is in the update query
        # at the end of the loop which requires - just like here - a tuple.
        row = [r for r in cur.execute(f"SELECT {columns} FROM `{table}` WHERE `{id_column}` = ?", id)]
        # One could argue whether this is an error or not and how it should be processed...
        # Just avoid it, ok?
        if len(row) > 1:
            print(f"Error: id {id} not unique! Skipping this id. ")
            continue
        # cur.execute retruns a 2D tuple, containing all rows matching the query, and then
        # in each row the selected columns. We only selected a single row, hence row[0] is
        # all we care about (and all there is, see error handling above.
        # Secondly we want row to be modifiable, hence the conversion to a list.
        # list(row[0]) would btw return a list with 1 element: the tuple of the columns.
        row = [e for e in row[0]]

        # result has the structure {column_name: updated_data} which makes it very easy to build
        # the update query at the end.
        result = dict()

        # It's important to note that the tuple from cur.execute contains the columns _in the order
        # of the query string_. Therefore we can separate json and path entries like this.
        jsons = row[:json_stop]
        paths = row[json_stop:path_stop]
        jf_imgs = row[path_stop:]
        for i, data in enumerate(jsons):
            if data:
                # There are numerous rows that have empty columns which would result in an error
                # from json.loads. Just skip them
                data = json.loads(data)
                data, mo, ig = recursive_path_replacer(data, replace_dict)
                modified += mo
                ignored  += ig
                result[json_columns[i]] = json.dumps(data)
        for i, path in enumerate(paths):
            # One could also skip the empty objects here, but recursive_path_replacer handles them
            # just fine (leaves them untouched).
            path, mo, ig = recursive_path_replacer(path, replace_dict)
            modified += mo
            ignored  += ig
            result[path_columns[i]] = path
        for i, imgs in enumerate(jf_imgs):
            # Some DB entries look like this:
            #     %MetadataPath%\library\71\71d037e6e74015a5a6231ce1b7912acf\poster.jpg*637693022742223153*Primary*
            #     198*198*eJC5#hK#Dj9GR/V@j]xuX8NG0x+xgN%MxaX7spNGnitQ$kK0wyV@Rj
            # Yeah. That's a path and some other data within the same string, separated by *.
            # In theory, the * could occur as normal character within regular paths but it's unlikely.
            # Oh, and did I mention that such strings can contain multiple of these structures separated by a | ?
            # "Reference" (Jellyfin Server 10.7.7 source): DeserializeImages, AppendItemImageInfo:
            #     https://github.com/jellyfin/jellyfin/blob/045761605531f98c55f379ac9eb5b5b6004ef670/
            #     Emby.Server.Implementations/Data/SqliteItemRepository.cs#L1118
            if not imgs:
                continue
            imgs = imgs.split("|")
            for j, img_properties in enumerate(imgs):
                if not img_properties:
                    continue
                img_properties = img_properties.split("*")
                # path = first property
                img_properties[0], mo, ig = recursive_path_replacer(img_properties[0], replace_dict)
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
        keys = ", ".join([f"`{k}` = ?" for k in result.keys()])
        query = f"UPDATE `{table}` SET {keys} WHERE `{id_column}` = ?"

        # The query has a question mark for each updated column plus one for the id to identify
        # the correct row.
        args  = tuple(result.values()) + id
        try:
            cur.execute(query, args)
        except Exception as e:
            # This was mainly for debugging purposes and shouldn't be reached anymore. Doesn't
            # hurt to have it though.
            print("Error:", e)
            print("Query:", query)
            print("Args: ", args)
            print(e)
            exit()
        else:
            if cur.rowcount < 1:
                # This was mainly for debugging purposes and shouldn't be reached anymore.
                # Doesn't hurt to have it though.
                print("No data modified!")
                print("Query:", query)
                print("Args: ", args)
                exit()
    print(f"Processed {rows_count} rows in table {table}. ")
    print(f"{modified} paths have been modified.")

    # Once again, this came from the development and is not required anymore, especially
    # since by default the script is working on copies of the original files.
    if not preview:
        # Write the updated database back to the file.
        con.commit()
    con.close()


def update_xml(file:Path, replace_dict:dict) -> None:
    # Walks through an XML file and checks *all* entries.
    # WARNING: The documentation of this parser explicitly mentions that it's not hardened against
    # known XML vulnerabilities. It is NOT suitable for unknown/unsafe XML files. Shouldn't be an
    # issue here though.
    modified, ignored = 0, 0
    tree = ET.parse(file)
    root = tree.getroot()
    for el in root.iter():
        el.text, mo, ig = recursive_path_replacer(el.text, replace_dict)
        modified += mo
        ignored  += ig
    print(f"Processed {ignored + modified} elements. {modified} paths have been modified.")
    tree.write(file) #, encoding="utf-8")


# Remember if the user wants to ignore all future warnings.
warn_if_original = True


def process_file(source:Path,
                 target:Path,
                 replacements:dict,
                 tables:dict=dict(),
                 copy_only:bool=False,
                 no_log:bool=False) -> None:
    # quick 'n dirty, I know.
    global warn_if_original

    # What do you want me to do with no input?
    if not source:
        return

    # Files only.
    if source.is_dir():
        return

    if not no_log:
        print("Processing", source)

    # "auto" means the target path is generated by the same path replacement dictionary that's
    # also used to update all the path strings.
    # In this case we don't care about the stats returned by recursive_path_replacer, hence
    # the variable names.
    if target == "auto":
        original_source = original_root / source.relative_to(source_root)
        target, idgaf1, idgaf2 = recursive_path_replacer(original_source, to_replace=replacements)
        target, idgaf1, idgaf2 = recursive_path_replacer(target, to_replace=fs_path_replacements)
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
    # In any case, the user is notified and can decide whether he wants to continue this time,
    # all the remaining times, too, or abort.
    #
    # Program: Are you sure? User: I don't know [yet]
    usure = "idk"
    if source == target:
        if warn_if_original:
            while usure not in "yna":
                usure = input("Warning! Working on original file! Continue? [Y]es, [N]o, [A]llways ")
                # j is for the german "ja" which means yes.
                usure = usure[0].lower().replace("j", "y")
            if usure == "n":
                print("Skipping this file. If you want to abort the whole process, stop the script"
                      "with CTRL + C.")
                return
            if usure == "a":
                # Don't warn about this anymore.
                warn_if_original = False
    else:
        if not target.parent.exists():
            target.parent.mkdir(parents=True)
        if not no_log:
            print("Copying...", target, end=" ")
        copy(source, target)
        if not no_log:
            print("Done.")


    if copy_only:
        # No need to do any further checks.
        return
    elif target.suffix == ".db":
        # sqlite file. In this case table specifies which tables within that file have columns to check.
        # Iterate over those.
        for table, kwargs in tables.items():
            print("Processing table", table)
            # The remaining function arguments (**kwards) contain the details about the columns to process.
            # See update_db_table and/or the todo_list.
            update_db_table(file=target, replace_dict=replacements, table=table, **kwargs)
    elif target.suffix == ".xml" or target.suffix == ".nfo":
        update_xml(file=target, replace_dict=replacements)
    elif target.suffix == ".mblink":
        # .mblink files only contain a path, nothing else.
        with open(target, "r") as f:
            path = f.read()
        path, modified, ignored = recursive_path_replacer(path, replacements)
        print(f"Processed {modified + ignored} paths, {modified} paths have been modified.")
        with open(target, "w") as f:
            f.write(path)
    elif target.suffix == ".json":
        # There are also json files with the ending .js but I haven't found any with paths.
        # Load the file by the json module (resulting in a dict or list object) and process
        # them by recursive_path_replacer which handles these structures.
        with open(target, "r") as f:
            j = json.load(f)
        j, modified, ignored = recursive_path_replacer(j, replacements)
        print(f"Processed {modified + ignored} paths, {modified} paths have been modified.")
        with open(target, "w") as f:
            # indent 2 seems to be the default formatting for jellyfin json files.
            json.dump(j, f, indent=2)


def process_files(lst:list):
    # Processes the todo_list.
    # It handles potential wildcards in the file paths and keeps track
    # which files have already been processed. This allows you to have an
    # automatic, wildcard copy in your todo_list that just copies the files
    # the the (modified) destinations without processing them and without
    # modifying those that have already been copied _and_ modified.
    # Obviously this requires you to have the files that need processing
    # first in the todo_list and only then the wildcard copies.
    done = set()
    for job in lst:
        source = job["source"]
        print(f"Current job from todo_list: {source}")
        if "*" in str(source):
            # Path has wildcards, process all matching files.
            #
            # Ironically Path.glob can't handle Path objects, hence the need
            # to convert them to a string...
            # It is expected that all these paths are relative to source_root.
            source = source.relative_to(source_root)
            for s in source_root.glob(str(source)):
                if s in done:
                    # File has already been processed by this script.
                    continue
                done.add(s)
                args = {k: (s if k == "source" else v) for k, v in job.items()}
                process_file(**args)
        else:
            # No wildcards, process the path directly - if it hasn't already
            # been processed.
            if source in done:
                continue
            done.add(source)
            process_file(**job)
        print("")

if __name__ == "__main__":
    # Nothing to see here.
    process_files(todo_list)
