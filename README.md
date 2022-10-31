# Jellyfin-Migrator

Script to migrate an entire Jellyfin database. 

**Update 2022-10-21: Confirmed! I successfully migrated my entire Jellyfin 10.8 installation from Windows to Docker on Linux.**

## Index

* [Description](#description)
* [Features](#features)
* [Usage](#usage)
	* [Installation](#installation)
	* [Preparation / Recommended Steps](#preparation--recommended-steps)
	* [Configuration](#configuration)
	* [Test it](#test-it)
* [Troubleshooting](#troubleshooting)
* [Examples](#examples)
* [ID Scanner](#id-scanner)
	* [Usage](#usage)
* [Credits](#credits)
* [License](#license)

## Description

I wanted to migrate my Jellyfin installation from Windows to Docker on Linux. Turns out the Jellyfin database is a nightmare. SQLite, XML, JSON, text files, custom structures - all mixed and even nested. And all of these structures contain hardcoded, absolute paths. 

That's the reason why I wrote this script. It goes through all the relevant files and replaces the paths as specified (and quite a few other things). I can't guarantee that it works in your case; I'd even bet it doesn't work without some sort of modification because every Jellyfin instance is different (just think about the plugins...). BUT I think and hope this tool can help many people, including you. 

Note: This script should in theory be able to migrate from Docker to Windows, too. But a) I'm not sure anyone ever wanted to migrate in that direction and b) I'm not sure it actually works. 

## Features

* Creates a complete copy of your Jellyfin database.
* User settings and stats
	* Layout settings
	* Password
	* Titles watched, progress, ...
* Metadata
	* All images, descriptions, etc. 
* Plugins
	* Those that I have installed migrated without issues. Might not be true in your case.
* Fixes all paths
	* Allows for a pretty much arbitrary reorganization of the paths. This includes merging media files from different directories into the same one (need to be of the same type though. merging movies with music won't work). 
	* Goes through all relevant files of the database and adjusts the paths. 
	* Reorganizes the copied and adjusted files according to these paths. 

## Usage

### Installation

* Install [Python](https://www.python.org/downloads/) 3.9 or higher (no guarantee for previous versions). On Windows, tick the option to add python to the PATH variable during the installation. No additional python modules required.
* Download/Clone this repository, particularly the jellyfin_migrator.py file. 
* Install your new Jellyfin server. In particular, make sure the webinterface can be reached (a.k.a. the network configuration works) and complete the initial setup. It's not strictly necessary to add any libraries, just make it to the homescreen. 

Optional:

* [DB Browser for SQLite](https://sqlitebrowser.org/)
* [Notepad++](https://notepad-plus-plus.org/)

### Preparation / Recommended Steps

* Copy your current Jellyfin database to a different folder. Since you're processing many small files, an SSD is highly recommended. You're not forced to copy your files before starting the migration, the script *can* work with the original files and won't modify them. However, I wouldn't recommend it and there are other reasons to not do it (see below).
* Your target directory for the migration should be on an SSD, too. Can be the same; SSDs don't mind reading/writing lots of small files. If you're on spinning drives though, I recommend putting source and target directory on separate drives. Furthermore, your target directory does *not* need to be in your Docker container where Jellyfin will run later. You can migrate the database first and copy it to its actual destination afterwards. 
* Your Jellyfin database contains some files that don't need to be migrated and can (AFAIK!) safely be deleted. While this wouldn't hurt your current Jellyfin installation if you deleted the files in its database, I strongly recommend to only delete files in the copy (see above) - then you don't loose anything if I'm mistaken! Here are the paths for a typical windows installation. You can probably figure out the matching paths for your installation, too.
	*`C:\ProgramData\Jellyfin\Server\cache`
	*`C:\ProgramData\Jellyfin\Server\log`
	*`C:\ProgramData\Jellyfin\Server\data\subtitles` - Note: these are actually only cached subtitles. Whenever Jellyfin's streaming a media file with embedded subtitles, it extracts them on the fly and saves them here. AFAIK no data is lost when deleting them. In any case, the script is *not* able to migrate these properly. 
* Plugins. The few [plugins from my installation]() migrated without issues. You may have different ones though that require more attention. Plugins may come with their own `.db` database files. You need to open them and check every table and column for file paths and IDs that the script needs to process:
	* Open the database in the DB Browser (see [Installation](#installation)). Select the tab "Browse Data". Then you can select the table (think of it as a sheet within an Excel file) in the drop-down menu at the top left. 
	* You need to check for all the columns if they contain paths. Some may have a lot of empty entries; in that case it's useful to sort them both ascending and descending. Then you're sure you don't have missed anything. 
	* Some columns may contain more complex structures in which paths are embedded. In particular, this script supports embedded JSON strings and what I'd call "Jellyfin Image Metadata". If you search for "Jellyfin Image Metadata" within the script, you can find a comment that explains the format. 
	* You also need to scan the database for IDs that may be used to identify the entries and their relations with other files. There's a script for that (see [ID Scanner](#id-scanner).
* **Careful with your network configuration!** You might want to *not* migrate / overwrite that file, since networking in Docker is quite different than networking under Windows f.ex. I suggest you to keep the`network.xml` file from your new Jellyfin installation. Path to the file under Windows (once again, you can probably find the file in your case, too):`C:\ProgramData\Jellyfin\Server\config\network.xml`

### Configuration

Every installation is different, therefore you need to adjust the paths in the script so that it matches your particular migration. This is the reason why you had get your new Jellyfin server already up and running; to make sure that you can figure out where all the files belong. Don't worry, you don't have to start from scratch. All the paths I had to adjust are still included in the script, so you'll know what to look for. 

This might seem complicated at first; I suggest you to check the [examples](#examples) below; they should clear things up!

* Open the python file in your preferred text editor (if you have none, I recommend [Notepad++](#installation).
* The entire file is fairly well commented. Though the interesting stuff for you as a user is all at the beginning of the file.
*`log_file`: Please provide a filepath where the script can log everything it does. This is not optional. 
*`path_replacements`: Here you specify how the paths are adapted. Please read the notes in the python file.
	* The structure you see is what was required for my own migration from Windows to the Linuxserver.io Jellyfin Docker. It might be different in your case. 
	* Please note that you need to specify the paths _as seen by Jellyfin_ when running within Docker (if you're using Docker). 
	* Some of them are fairly straight-forward. Others, especially if you migrate to a different target than I did, require you to compare your old and new Jellyfin installation to figure out which files and folders end up where. Again, keep in mind that Docker may remap some of these which must be taken into account. 
*`fs_path_replacements`: "Undoing" the Docker mapping. This dictionary is used to figure out the actual location of the new files in the filesystem. In my case f.ex.`cache`,`log`,`data`, ... were mapped by Docker to`/config/cache`,`/config/log`,`/config/data` but those folders are actually placed in the root directory of this Docker container.  This dictionary also lists the paths to all media files, because access to those is needed as well even if you don't copy them with this script. 
*`original_root`: original root directory of the Jellyfin database. On Windows this should be`C:\ProgramData\Jellyfin\Server`.
*`source_root`: root directory of the database to migrate. This can (but doesn't need to be) different than`original_root`. Meaning, you can copy the entire`orignal_root` folder to some other place, specify that path here and run the script (f.ex. if you want to be 100% sure your original database doesn't get f*ed up. Unless you force the script it's read-only on the source but having a backup never hurts, right?). 
*`target_root`: target folder where the new database is created. This definitely should be another directory. It doesn't have to be the final directory though. F.ex. I specified some folder on my Windows system and copied that to my Linux server once it was done. 
*`todo_list`: list of files that need to be processed. This script supports`.db` (SQLite),`.xml`,`.json` and`.mblink` files. The given list should work for "standard" Jellyfin instances. However, you might have some plugins that require additional files to be processed. 
	* The entries in the python file should be mostly self-explanatory. 

### Test it

* Run the script. Can easily take a few minutes. 
	* To run the script (on Windows), open a CMD/PowerShell/... window in the folder with the python file (SHIFT + right click => open PowerShell here). Type`python jellyfin_migrator.py` and hit enter. Linux users probably know how to do it anyways. 
	* Carefully check the log file for issues (See [Troubleshooting](#troubleshooting)).
* As a first check after the script has finished, you can search through the new database with any search tool (f.ex. Agent Ransack) for some of the old paths. Assuming you omitted all the cache and log files there shouldn't be any hits. Well, except for the SQLite`.db` files. Apparently there's some sort of "lazy" updating which does not remove the old values entirely. 
* Copy the new database to your new server and run Jellyfin. Check the logs. 
	* If there's any file system related error message there's likely something wrong. Either your `path_replacements` don't cover all paths, or some files ended up at places where they shouldn't be. I had multiple issues related to the Docker path mapping; took me a few tries to get the files where Docker expects them such that Jellyfin can actually see and access them. 
	
## Troubleshooting

Here are some common error messages and what to do with them. The log file is your friend!

### General tips:

* Make sure your `todo_list`s (especially the `todo_list_paths`) actually cover all the files you want to copy / migrate. Jellyfins "core" files should already be covered correctly by the `todo_list`s as they are when downloading the script. However, you may have very different plugins or use very different features of Jellyfin than I do. The only indication that you got for missing files is a warning when updating the file dates (see [below](#file-doesnt-seem-to-exist-cant-update-its-dates-in-the-database)). This may not cover files from plugins though. 
* Inspect the log file with a decent text editor that allows you to quickly remove uninteresting messages. Here is my workflow for Notepad++ (see [Installation](#installation)):
	* Open log file in Notepad++
	* Text encoding is UTF-8 (selectable under "Encoding -> UTF-8")
	* Go to "Search -> Mark..." (CTRL + M)
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

While updating file paths or IDs within filepaths, the script encountered a string that might be a path but that it cannot process because it doesn't match any of the given replacement rules. 

Causes and solutions:

* It's likely a false-positive and the string you see doesn't contain a path at all. The detection does skip the most common false-positives, but making it any better without risking to ignore actual paths wasn't worth the trouble IMO (since you can just ignore the false warnings). 
* The path points to a file you actually want to migrate (meaning, not a cache file or similar): Update your path replacement rules to include this and similar files. 
* It could be triggered by `fs_path_replacements` in cases where no `fs_path_replacements` are needed. See [Example 2](#example-2)
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
* If you know the files / folders exist, there's likely an issue with your `fs_path_replacements` dict. Make sure it properly maps the path shown in this message to the path required for this script to find the file (network drive mapping, Docker mappings, ...). Read the information here and in the script source about that dictionary for details. 

### Server not accessible after migration

Check out [Preparation / Recommended Steps](#preparation--recommended-steps). You likely overwrote Jellyfins network configuration file (`network.xml`), which is about the only file you don't necessarily want to migrate since your new installation likely has a different network setup than your previous one. Again, check out the details above. 

I also had the issue that the server just seemed to be unreachable (got the "Select Server" page or an error message on log in). In reality, it was just some browser cache issue. To verify that, try accessing your server from a private browser tab or even a different device. If you've verified that it's the browser cache, check how to delete it (restart probably helps). In my case (Firefox) CTRL+F5 did the job. 
	
## Examples

This section provides example configurations for two setups that were migrated with this script. By seeing the setupt and the resulting configuration of this script I hope it gets more clear how to adapt it to your own setup. 

### Example 1

This was my own setup and corresponds to what you'll see in the scrip as well.

#### Old Installation

* Pretty standard Windows Installation
* Metadata *not* located in the media folders, no NFO files there either. 
* Most of the stuff lives in C:/ProgramData/Jellyfin/Server/... Notably there are the following folders:
	* `cache`
	* `config`
	* `data`
	* `log`
	* `metadata`
	* `plugins`
	* `root`
	* `transcodes`
* Media Folders:
	* `F:/Musik` (Music)
	* `F:/Filme` (Movies)
	* `F:/Serien` (TV Shows)
	* `D:/Serien` (more TV Shows)
* Plugins: 
	* AudioDB
	* Intros
	* MusicBrainz
	* OMDb
	* Open Subtitles
	* **Playback Reporting**
	* Studio Images
	* TMDb
	* TVmaze
	* TheTVDB
	* Theme Songs
	* YoutubeMetada

#### New Installation
	
* I went with the linuxserver.io Jellyifn Docker container that I deployed on an unraid server. 
* All the configuration stuff from Docker containers is stored at `/mnt/user/appdata/[container name]`, in particular, the path for the Jellyfin container is `mnt/user/appdata/jellyfin`.
* The media files have already been copied and are located at
	* `/mnt/user/Media/Musik` (Music)
	* `/mnt/user/Media/Filme` (Movies)
	* `/mnt/user/Media/Serien` (all TV Shows, from both sources)
* The default Docker mappings plus the media mappings look like this:
	* `/mnt/user/appdata/jellyfin`: `/config`
	* `/mnt/user/Media/Musik`: `/data/music`
	* `/mnt/user/Media/Filme`: `/data/movies`
	* `/mnt/user/Media/Serien`: `/data/tvshows`

#### Script Location

* The script, in my case, runs on a computer different from both the old and the new server. Though nothing would change if it ran on the old Windows server. 
* I copied my entire Jellyfin database from `C:/ProgramData/Jellyfin/Server/` to `D:/Jellyfin/Server/`
* The migrated database shall end up in `D:/Jellyfin-patched`. From there I'll copy it to the new server. 

#### Determining the *_root Paths

Easiest things first. In the old installation, the whole configuration was located at `C:/ProgramData/Jellyfin/Server`. So that's what you put in for `original_root`

The script can find the files to migrate at `D:/Jellyfin/Server`. Thus, this is the value for `source_root`.

Finally, the script shall put the resulting files at `D:/Jellyfin-patched`. Put this in `target_root`.

#### Determining the Media Path Mappings

Let's start with the media paths since they're easier IMO. 

From the perspective of Jellyfin, any movie that used to be found at `F:/Filme/somedir/somemovie.mkv` is now visible at `/data/movies/somedir/somemovie.mkv` (remember, Jellyfin sees the files and folders where they've been mapped by Docker). So we add the following entry to `path_replacements`:
	```
	"F:/Filme": "/data/movies",
	```
Repeat for the other media locations and we get:
	```
	"F:/Filme": "/data/movies",
	"F:/Musik": "/data/music",
	"F:/Serien": "/data/tvshows",	
	"D:/Serien": "/data/tvshows",	
	```
Note that you can indeed map both TV Show source folders to the same target folder. Nothing else is needed to merge them together.

Those were the mappings for jellyfin. Now we need to determine how the script is going to access these files _on the new server_. Since my script doesn't run on that server, I created a network share for the `/mnt/user/Media` folder. On the computer that runs the script, this share is mounted under `Y:`. And thus `/mnt/user/Media/Filme` f.ex. ends up at `Y:/Filme`. 

So, to give the script access to the media files, I put this at the end of `fs_path_replacements`:
	```
    "/data/tvshows": "Y:/Serien",
    "/data/movies": "Y:/Filme",
    "/data/music": "Y:/Musik",
	```

That's it. The script can now properly migrate the old paths to the new paths for Jellyfin, and based on the latter ones figure out where it can find the files itself. 

#### Determining the Config Path Mappings

The config mappings can be more tricky to figure out depending on your Docker mappings. Once again, we first determine the mappings from Jellyfins perspective and then where the script is supposed to put the files on the disk. 

Let's take the example of the `C:/ProgramData/Jellyfin/Server/cache` directory. Looking at the root directory of our new Jellyfin installation (`/mnt/user/appdata/jellyfin`) we see a `cache` folder, too. And if we look at its content, we see that they're indeed both the same folders. Since Docker maps anything from `mnt/user/appdata/jellyfin` to `/config`, the `cache` subdirectory ends up being `/config/cache` for Jellyfin. This repeats for the `config` and `log` folders. 

Where things get interesting are the `metadata`, `plugin` and the other remaining folders from `C:/ProgramData/Jellyfin/Server`: Looking at the new installation, we find them at `mnt/user/appdata/jellyfin/data` - which is once again mapped by Docker to `/config/data`.

There are multiple ways to construct the `path_replacements` dictionary from this. You can list all folders individually, but I took a slightly shorter approach:

```
    "C:/ProgramData/Jellyfin/Server/config": "/config/config",
    "C:/ProgramData/Jellyfin/Server/cache": "/config/cache",
    "C:/ProgramData/Jellyfin/Server/log": "/config/log",
    "C:/ProgramData/Jellyfin/Server": "/config/data",
```

The first three should be straightforward. The last one uses the fact that the replacements are processed in the exact order you list them. So  after the first three entries, there are only folders left that need to go to `/config/data`. Therefore they don't need to be listed individually like the first three. However, you could just write 
```
    "C:/ProgramData/Jellyfin/Server/metadata": "/config/data/metadata",
```
(and repeat for all the remaining folders). 

As for `fs_path_replacements`, things are a bit different than in the case of the media folders. Anything Jellyfin sees under `/config` is actually located at `/mnt/user/appdata/jellyfin`, which is the _root_ folder for the Jellyfin Docker container. The script puts anything that goes to that path to `target_root`. So f.ex. `/config/data/metadata` shall end up at `target_root /data/metadata`. If you don't specify a full (absolute) path like for the media folders, but only `/data/metadata` f.ex., the script will automatically resolve it within the `target_root` folder. So the `fs_path_replacements` entry could look like this:
```
	"/config/data/metadata": "/data/metadata",
```
And you'd repeat that for all folders. However, you'll notice that all these entries share one common thing: the `/config` part is removed. So instead of having all of them listed individually (which is perfectly fine if you don't miss any), all these cases can be covered by this simple entry:
```
	"/config": "/",
```

#### %AppDataPath%, %MetadataPath%

These are path variables, meaning, jellyfin replaces them with their actual location. The script needs to do the same. On one hand, we need to make sure the script recognizes them as paths - but we don't need to change them. Hence the `path_replacements` dict needs these two entries:
```
	"%AppDataPath%": "%AppDataPath%",
	"%MetadataPath%": "%MetadataPath%",
```

If that doesn't make any sense to you, just ignore those lines and leave them as they are. Hopefully the next part makes more sense though. Just like Jellyfin, the script has to replace those variables, too, to locate the actual files (metadata files f.ex.). In the Windows installation, `%AppDataPath%` and `%MetadataPath%` point to `C:/ProgramData/Jellyfin/Server/data` and `C:/ProgramData/Jellyfin/Server/metadata` respectively. Applying the exact same logic as above, we get the following results for `fs_path_replacements`:
```
    "%AppDataPath%": "/data/data",
    "%MetadataPath%": "/data/metadata",	
```

You might want to go through this for yourself. It's not complicated, but the nested subfolders with identical names do make it confusing a.f. 

#### Plugins

I'll keep this one short. From all the plugins I had installed, only one had its own database: Playback Reporting. Running the [ID Scanner](#id-scanner) for that `.db` file revealed one column with IDs that need to be replaced:
```
Table             Column  ID Type(s) found    
PlaybackActivity  ItemId  ancestor-str (pure) 
```
 A manual inspection revealed no file paths at all. The `playback_reporting.db` thus only needs to be added to the `todo_list_ids`:
```
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
```

That's it! These were the settings that brought my installation from Windows to Linux without data loss. 

### Example 2

This second example is from another user of the script. I won't go into too much details since the process is the same as for the first example. The most important differences are that both Jellyfin and Docker were configured for slightly different paths.

First of all, Docker was configured to mount `/mnt/user/appdata/jellyfin/config` as `/config` (compare that to the Docker mapping from example 1!). Secondly, the `metadata`, `plugin`, ... folders were _not_ located within a `data` subfolder. Oh, and his media folders were slightly different, of course. 

That first difference means, that `fs_path_replacements` does _not_ need the `"/config": "/",` entry, which has an important consequence (see below). The second one just makes the paths less confusing I guess. This person also opted for listing all folders individually; his dict could be written shorted but it worked perfectly fine like this. 

```
path_replacements = {
    "target_path_slash": "/",

    "E:/Séries": "/data/medias/Series",
    "E:/Films": "/data/medias/Films",
    "E:/Animés": "/data/medias/Animes",

    "C:/ProgramData/Jellyfin/Server/config": "/config/config",
    "C:/ProgramData/Jellyfin/Server/cache": "/cache",
    "C:/ProgramData/Jellyfin/Server/log": "/config/log",
    "C:/ProgramData/Jellyfin/Server/data": "/config/data", 
    "C:/ProgramData/Jellyfin/Server/metadata": "/config/metadata",
    "C:/ProgramData/Jellyfin/Server/plugins": "/config/plugins",
    "C:/ProgramData/Jellyfin/Server/root": "/config/root",
    "C:/ProgramData/Jellyfin/Server/transcodes": "/config/transcodes",
    "C:/Program Files/Jellyfin/Server/ffmpeg.exe": "/config/usr/lib/jellyfin-ffmpeg/ffmpeg",

    "%MetadataPath%": "%MetadataPath%",
    "%AppDataPath%": "%AppDataPath%",
}

fs_path_replacements = {
    "log_no_warnings": True,
    "target_path_slash":   "/",
    "%AppDataPath%":       "/config/data",
    "%MetadataPath%":      "/config/metadata",
    "/data/medias/Series": "M:/Series",
    "/data/medias/Films":  "M:/Films",
    "/data/medias/Animes": "M:/Animes",
}
```

As teased above, the lack of the `/config` entry in `fs_path_replacements` means that many paths don't get changed by `fs_path_replacements` at all. This triggers a [warning](#no-entry-for-this-presumed-path) which - in this case - is a false positive. Therefore, if you are absolutely sure your `fs_path_replacements` are correct, you can (and should) set `"log_no_warnings"` to `True`. Careful! This blocks all warnings, and you may not notice issues with your `fs_path_replacements`! 

## ID Scanner

While developing the migrator script I wrote another tool that's contained in this repository:`jellyfin_id_scanner.py`. It scans a database for occurences of the IDs Jellyfin uses internally to identify files and folders and establish relations between them. This is helpful if you got database files from plugins that I don't have. Note that it can only tell you about ID formats it actually knows. 

### Usage

Unlike the main migrator script, this smaller one actually presents a command line interface (might also want to check the [Test it](#test-it) section above): 

```python jellyfin_id_scanner.py --library-db "C:\Some\Path\library.db" --scan-db "C:\Some\JF\Pluging\PluginDB.db```

Using `--help` gives a more detailed description if required. 

## Credits

Big thank you goes to the devs in the [official Jellyfin chats](https://jellyfin.org/contact) that pointed me to the correct places in the Jellyfin sources and helped me figure out how certain things work under the hood! 

## License

Jellyfin Migrator - Adjusts your Jellyfin database to run on a new system.
Copyright (C) 2022  Max Zuidberg

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program.  If not, see <https://www.gnu.org/licenses/>.
