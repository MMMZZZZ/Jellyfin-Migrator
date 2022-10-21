# Jellyfin-Migrator

Script to migrate an entire Jellyfin database. 

**Update 2022-10-21: Confirmed! I successfully migrated my entire Jellyfin installation from Windows to Docker on Linux.**

## Index

* [Description](#description)
* [Features](#features)
* [Usage](#usage)
	* [Installation](#installation)
	* [Preparation / Recommended Steps](#preparation-recommended-steps)
	* [Configuration](#configuration)
	* [Test it](#test-it)
* [Troubleshooting](#troubleshooting)
* [ID Scanner](#id-scanner)
	* [Usage](#usage)
* [License](#license)

## Description

I wanted to migrate my Jellyfin installation from Windows to Docker on Linux. Turns out the Jellyfin database is a nightmare. SQLite, XML, JSON, text files, custom structures - all mixed and even nested. And all of these structures contain hardcoded, absolute paths. 

That's the reason why I wrote this script. It goes through all the relevant files and replaces the paths as specified (and quite a few other things). I can't guarantee that it works in your case; I'd even bet it doesn't work without some sort of modification because every Jellyfin instance is different (just think about the plugins...). BUT I think and hope this tool can help many people, including you. 

Note: This script should in theory be able to migrate from Docker to Windows, too. But a) I'm not sure anyone ever wanted to migrate in that direction and b) I'm not sure it actually works. 

## Features

* Creates a complete copy of your jellyfin database.
* User settings and stats
	* Layout settings
	* Password
	* Titles watched, progress, ...
* Metadata
	* All images, descriptions, etc. 
* Plugins
	* Those that I have installed migrated without issues. Might not be true in your case.
* Fixes all paths
	* Allows for a pretty much arbitrary reorganization of the paths. 
	* Goes through all relevant files of the database and adjusts the paths. 
	* Reorganizes the copied and adjusted files according to these paths. 

## Usage

### Installation

* Install [Python](https://www.python.org/downloads/) 3.9 or higher (no guarantee for previous versions). On Windows, tick the option to add python to the PATH variable during the installation. No additional python modules required.
* Download/Clone this repository, particularly the jellyfin_migrator.py file. 
* Install your new jellyfin server. Check that it's up and running. 

Optional:

* [DB Browser for SQLite](https://sqlitebrowser.org/)
* [Notepad++](https://notepad-plus-plus.org/)

### Preparation / Recommended Steps

* Copy your current jellyfin database to a different folder. Since you're processing many small files, an SSD is highly recommended. You're not forced to copy your files before starting the migration, the script *can* work with the original files and won't modify them. However, I wouldn't recommend it and there are other reasons to not do it (see below).
* Your jellyfin database contains some files that don't need to be migrated and can safely be deleted. While this wouldn't hurt your current jellyfin installation if you deleted the files in its database, I strongly recommend to only delete files in the copy from step 1 - then you don't loose anything if I'm mistaken! Here are the paths for a typical windows installation. You can probably figure out the matching paths for your installation, too.
	* `C:\ProgramData\Jellyfin\Server\cache`
	* `C:\ProgramData\Jellyfin\Server\log`
	* `C:\ProgramData\Jellyfin\Server\data\subtitles` - Note: these are actually only cached subtitles. Whenever streaming a media file with embedded subtitles, jellyfin extracts them on the fly and saves them here. AFAIK no data is lost when deleting them.
* Your target directory for the migration should be on an SSD, too. Can be the same; SSDs don't mind reading/writing lots of small files. If you're on spinning drives though, I recommend putting source and target directory on separate drives. Furthermore, your target directory does *not* need to be in your docker container where jellyfin will run later. You can migrate the database first and copy it to it's actual destination afterwards. 
* Plugins. The few plugins I got migrated without issues. You may have different ones though that require more attention. Plugins may come with their own .db database files. You need to open them and check every table and column for file paths and IDs that the script needs to process:
	* Open the database in the DB Browser (see [Installation](#installation)). Select the tab "Browse Data". Then you can select the table (think of it as a sheet within an Excel file) in the drop-down menu at the top left. 
	* You need to check for all the columns if they contain paths. Some may have a lot of empty entries; in that case it's useful to sort them ascending and descending. Then you're sure you don't have missed anything. 
	* Some columns may contain more complex structures in which paths are embedded. In particular, this script supports embedded JSON strings and what I'd call "Jellyfin Image Metadata". If you search for "Jellyfin Image Metadata" within the script, you can find a comment that explains the format. 
	* You also need to scan the database for IDs that may be used to identify the entries and their relations with other files. There's a script for that (see [ID Scanner](#id-scanner).

### Configuration

* Open the python file in your preferred text editor (if you have none, I recommend notepad++).
* The entire file is fairly well commented. Though the interesting stuff for you as a user is all at the beginning of the file.
* `log_file`: Please provide a filepath where the script can log everything it does. This is not optional. 
* `path_replacements`: Here you specify how the paths are adapted. Please read the notes in the python file.
	* The structure you see is what was required for my own migration from Windows to the Linuxserver.io Jellyfin Docker. It might be different in your case. 
	* Please note that you need to specify the paths _as seen by Jellyfin_ when running within Docker (if you're using Docker). 
	* Some of them are fairly straight-forward. Others, especially if you migrate to a different target than I did, require you to compare your old and new Jellyfin installation to figure out what files and folders end up where. Again, keep in mind that Docker may remap some of these which must be taken into account. 
* `fs_path_replacements`: "Undoing" the Docker mapping. This dictionary is used to figure out the actual location of the new files in the filesystem. In my case f.ex. `cache`, `log`, `data`, ... were mapped by docker to `/config/cache`, `/config/log`, `/config/data` but those folders are actually placed in the root directory of this docker container.  This dictionary also lists the paths to all media files, because access to those is needed as well even if you don't copy them with this script. 
* `original_root`: original root directory of the Jellyfin database. On Windows this should be `C:\ProgramData\Jellyfin\Server`.
* `source_root`: root directory of the database to migrate. This can (but doesn't need to be) different than `original_root`. Meaning, you can copy the entire `orignal_root` folder to some other place, specify that path here and run the script (f.ex. if you want to be 100% sure your original database doesn't get f*ed up. Unless you force the script it's read-only on the source but having a backup never hurts, right?). 
* `target_root`: target folder where the new database is created. This definitely should be another directory. It doesn't have to be the final directory though. F.ex. I specified some folder on my Windows system and copied that to my Linux server once it was done. 
* `todo_list`: list of files that need to be processed. This script supports `.db` (SQLite), `.xml`, `.json` and `.mblink` files. The given list should work for "standard" Jellyfin instances. However, you might have some plugins that require additional files to be processed. 
	* The entries in the python file should be mostly self-explanatory. 

### Test it

* Run the script. Can easily take a few minutes. 
	* To run the script, open a CMD/PowerShell/... window in the folder with the python file (SHIFT + right click => open PowerShell here). Type `python jellyfin_migrator.py` and hit enter. 
	* Carefully check the log file for issues (See troubleshooting
* As a first check after the script has finished, you can search through the new database with any search tool (f.ex. Agent Ransack) for some of the old paths. Except for cache and log files (which you can and probably should delete) there shouldn't be any hits. Well, except for the SQLite `.db` files. Apparently there's some sort of "lazy" updating which does not remove the old values entirely. 
* Copy the new database to your new server and run jellyfin. Check the logs. 
	* If there's any file system related error message there's likely something wrong. Either your `db_path_replacements` doesn't cover all paths, or some files ended up at places where they shouldn't be. I had multiple issues related to the Docker path mapping; took me a few tries to get the files where Docker expects them such that Jellyfin can actually see and access them. 
	
## Troubleshooting

Here are some common error messages and what to do with them. The log file is your friend!

### General tips:

* Make sure your todo_lists (especially the todo_list_paths) actually cover all the files you want to copy / migrate. Jellyfins "core" files should be properly covered by the todo_lists as they are since it worked for me. However, you may have very different plugins or use very different features of jellyfin than I do. The only indication that you got for missing files is a warning when updating the file dates (see [below](#file-doesnt-seem-to-exist-cant-update-its-dates-in-the-database)). This may not cover files from plugins though. 
* Inspect the log file with a decent text editor that allows you to quickly remove uninteresting messages. Here is my workflow for Notepad++ (short: npp) (see [Installation](#installation)):
	* Open log file in npp	
	* Text encoding is UTF-8 (selectable under "Encoding -> UTF-8")
	* Go to "Search -> Mark... (CTRL + M)
	* Tick "Bookmark Line"
	* Search for strings that (only!) occur in the lines you want to remove. All those lines should get a marking next to the line number.
	* Go to "Search -> Bookmark -> Remove Bookmarked Lines"
	* Repeat as needed

### Warning! Working on original file! Continue?

Apparently your paths are configured such that one or more file(s) would end up in the same place (meaning, their new path equals their old path). 

Causes and solutions:
	* Pretty sure your `source_root` and `target_root` paths are the same. If this is intentional, you can select to get no warnings anymore (until you restart the script)
	* Maybe some other paths you specified are wrong, too? Copy paste errors? 
	* Check the previous log message(s) to see which path / job caused the issue.


### No entry for this (presumed) path

While updating file paths or IDs within filepaths, the script encountered a string that might be a path but that it cannot process because it doesn't match any of the rules. 

Causes and solutions:
	* 99% are false-positives and no paths at all. The detection could be made smarter but that would likely also slow down the process. It already ignores some common false-positives. 
	* The path points to a file you actually want to migrate (meaning, not a cache file or similar): Update your path replacement rules to include this and similar files. 
	* The path points to a file you don't want or need to migrate:
		* It happens while processing a .db file (scroll back up to find the log message that indicates what file it's processing): Update your rules anyways. Better safe than sorry when it comes to the database files IMO. 
	* If it happens during the ID path migration (Step 3), it likely means that those paths use an ID type that the script doesn't support (yet). You can open an issue but I can't promise a fix. 
	
### Warning! duplicates detected within new ids

When generating the new IDs for the migrated database, the script found that some IDs occured more than once. 

Causes and solutions:
	* Most likely: Folders that used to be different are merged into the same new folder by your path replacement rules. This can be intentional if f.ex. you had media files spread across different drives and now move/copy them into the same folder. If that's indeed the case, you can ignore this message. 
	
	
### Encountered duplicated entries | Deleting ...

See [above](#warning-duplicates-detected-within-new-ids). This just informs you about the exact entries that have been deleted from the database.

### File doesn't seem to exist; can't update its dates in the database

The script goes through all the migrated files and folders listed in the library database and tries to retrieve their creation and modified date from the file system. This message means that a file or folder listed in the database could not be found and thus its date can't be updated. 

Causes and solutions:
	* In my case this happened for a lot of metadata folders that were actually empty to begin with. I don't know why there were empty folders but okay. Since the script only copies *files*, those folders had not been copied. If you checked that in your original installation those directories were actually empty, it's probably (!) okay.
	* If you checked the original installation and there *are* files that should have been copied, your `todo_list_paths` likely doesn't cover all the files. Meaning, paths in the database have been updated, but the corresponding files haven't been copied.
	* If you know the files / folders exist, there's likely an issue with your `fs_path_replacements` dict. Make sure it properly maps the path shown in this message to the path required for this script to find the file (Network drive mapping, docker mappings, ...). Read the information here and in the script source about that dictionary for details. 
	
## ID Scanner

While developing the migrator script I wrote another tool that's contained in this repository: `jellyfin_id_scanner.py`. It scans a database for occurences of the IDs jellyfin uses internally to identify files and folders and establish relations between them. This is helpful if you got database files from plugins that I don't have. Note that it can only tell you about ID formats it actually knows. 

### Usage

Unlike the main migrator script, this smaller one actually presents a command line interface (might also want to check the [Test it](#test-it) section above): 

```python jellyfin_id_scanner.py --library-db "C:\Some\Path\library.db" --scan-db "C:\Some\JF\Pluging\PluginDB.db```

Using `--help` gives a more detailed description if required. 

## License

Jellyfin Migrator - Adjusts your Jellyfin database to run on a new system.
Copyright (C) 2022  Max Zuidberg

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
