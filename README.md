# Jellyfin-Migrator

Script to migrate an entire Jellyfin database.

## Index

* [Description](#description)
* [Features](#features)
* [Usage](#usage)
	* [Installation](#installation)
	* [Configuration](#configuration)
	* [Test it](#test-it)
* [License](#license)

## Description

I wanted to migrate my Jellyfin installation from Windows to Docker on Linux. Turns out the Jellyfin database is a nightmare. SQLite, XML, JSON, text files, custom structures - all mixed and even nested. And all of these structures contain hardcoded, absolute paths. 

That's the reason why I wrote this script. It goes through all the relevant files and replaces the paths as specified. I can't guarantee it works in your case; I'd even bet it doesn't work without some sort of modification because every Jellyfin instance is different (just think about the plugins...).

Note: This script should in theory be able to migrate from docker to windows, too. But a) I'm not sure anyone ever wanted to migrate in that direction and b) I'm not sure it actually works. 

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

* Install python 3.9 or higher (no guarantee for previous versions). On Windows, tick the option to add python to the PATH variable during the installation. 
* Download/Clone this repository, particularly the jellyfin_migrator.py file. 
* No additional python modules required.
* Install your new jellyfin server. Check that it's up and running. 

### Configuration

* Open the python file in your preferred text editor (if you have none, I recommend notepad++).
* The entire file is fairly well commented. Though the interesting stuff for you as a user is all at the beginning of the file.
* `db_path_replacements`: Here you specify how the paths are adapted. Please read the notes in the python file.
	* The structure you see is what was required for my own migration from Windows to the Linuxserver.io Jellyfin Docker. It might be different in your case. 
	* Please note that you need to specify the paths _as seen by Jellyfin_ when running within Docker. 
	* Some of them are fairly straight-forward. Others, especially if you migrate to a different target than I did, require you to compare your old and new Jellyfin installation to figure out what files and folders end up where. Again, keep in mind that Docker may remap some of these which must be taken into account. 
* `fs_path_replacements`: "Undoing" the Docker mapping. This dictionary is used to figure out the actual location of the new files in the filesystem. In my case f.ex. `cache`, `log`, `data`, ... were mapped by docker to `/config/cache`, `/config/log`, `/config/data` but those folders are actually placed in the root directory of this docker container. 
* `original_root`: original root directory of the Jellyfin database. On Windows this should be `C:\ProgramData\Jellyfin\Server`.
* `source_root`: root directory of the database to migrate. This can (but doesn't need to be) different than `original_root`. Meaning, you can copy the entire `orignal_root` folder to some other place, specify that path here and run the script (f.ex. if you want to be 100% sure your original database doesn't get f*ed up. Unless you force the script it's read-only on the source but having a backup never hurts, right?). 
* `target_root`: target folder where the new database is created. 
* `todo_list`: list of files that need to be processed. This script supports `.db` (SQLite), `.xml`, `.json` and `.mblink` files. The given list should work for "standard" Jellyfin instances. However, you might have some plugins that require additional files to be processed. 
	* The entries in the python file should be mostly self-explanatory. 

### Test it

* Run the script. Can easily take a few minutes. 
	* To run the script, open a CMD/PowerShell/... window in the folder with the python file (SHIFT + right click => open PowerShell here). Type `python jellyfin_migrator.py` and hit enter. 
	* Watch for messages that say "No entry to replace the following (presumed) path: ...". 99% are false positives (meaning just strings that happen to contain a slash). But if there's indeed a file path, you must adjust your `db_path_replacements`.
	* Note that some folders contain so many files that it "flushes" the entire console output. You might want to comment out certain entries of the `todo_list` to make sure you don't miss any messages in the log.
* As a first check after the script has finished, you can search through the new database with any search tool (f.ex. Agent Ransack) for some of the old paths. Except for cache and log files (which you can and probably should delete) there shouldn't be any hits. Well, except for the SQLite `.db` files. Apparently there's some sort of "lazy" updating which does not remove the old values entirely. 
* Copy the new database to your new server and run jellyfin. Check the logs. 
	* If there's any file system related error message there's likely something wrong. Either your `db_path_replacements` doesn't cover all paths, or some files ended up at places where they shouldn't be. I had multiple issues related to the Docker path mapping; took me a few tries to get the files where Docker expects them such that Jellyfin can actually see and access them. 

## License

Jellyfin Migrator - Adjusts your Jellyfin database to run on a new system.
Copyright (C) 2022  Max Zuidberg

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
