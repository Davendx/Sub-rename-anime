# Anime Renamer

An intelligent Python script to rename anime video and subtitle files using metadata from AniList.co.

## Features

- **Intelligent Parsing:** Uses `anitopy` to parse existing filenames, even if they're messy.
- **Accurate Metadata:** Fetches canonical titles and seasonal information from the AniList GraphQL API.
- **Fuzzy Matching:** Automatically matches local files to the correct AniList entry, even with different titles or synonyms.
- **Season Inference:** Correctly handles continuous episode numbering across multiple seasons (e.g., episode 13 of a 12-episode season is correctly identified as S02E01).
- **Rclone Support:** Process files directly on any cloud storage provider supported by `rclone`.
- **NFO File Generation:** Create Kodi-compatible `.nfo` metadata files for each episode.
- **Interactive Menu:** A user-friendly menu to guide you through the renaming process when no path is provided.
- **Configurable:** Customize the script's behavior using a `config.yaml` file.
- **Command-Line Interface:** Provides a flexible command-line interface with a wide range of options.
- **Windows Context Menu Integration:** Can be added to the Windows right-click context menu for easy access.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/anime-renamer.git
    cd anime-renamer
    ```

2.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **(Optional) Install `rclone`:** If you want to process files on a remote storage provider, you'll need to install and configure `rclone`. You can find instructions on the [official `rclone` website](https://rclone.org/install/).

## Configuration

The script uses a `config.yaml` file to allow for easy customization. If this file doesn't exist, it will be created with default settings the first time you run the script.

Here's an example of the `config.yaml` file:

```yaml
# The title language to use for renamed files (romaji, english, or native)
title_language: romaji

# The template for renamed files
rename_template: "{title} - S{season:02d}E{episode:02d} - Episode {episode:02d}"

# The confidence threshold for fuzzy string matching (0-100)
fuzzy_threshold: 85
```

## Usage

### Interactive Menu

If you run the script without any arguments, you'll be greeted with an interactive menu that allows you to choose how you want to process your files:

```bash
python3 anime_renamer.py
```

### Command-Line Interface

You can also run the script from the command line by providing the path to the directory you want to process:

```bash
# Process a local directory
python3 anime_renamer.py "path/to/your/anime/folder"

# Process an rclone remote
python3 anime_renamer.py --rclone-remote "gdrive:/Anime"
```

The script supports a variety of flags to customize its behavior:

| Flag | Description |
| --- | --- |
| `--dry-run` | Preview the renames without making any changes. |
| `--recursive` | Scan all subdirectories within the specified folder. |
| `--verbose` | See detailed logs of the script's operations. |
| `--force-refresh` | Force a refresh of the AniList API cache. |
| `--interactive` | Pause for user confirmation on all major decisions. |
| `--batch` | Process a list of directories from a text file. |
| `--bundle-ova` | Move specials and OVAs to a `S00_OVAs` subfolder. |
| `--export-nfo` | Export `.nfo` files with metadata for each episode. |
| `--rclone-remote` | The rclone remote to process (e.g., `'gdrive:/Anime'`). |
| `--rclone-config` | Path to the `rclone.conf` file. |

## Windows Right-Click Context Menu Integration

You can add the script to the Windows right-click context menu to run it directly on a folder.

1.  **Create a new file** named `anime_renamer.reg` and open it in a text editor.

2.  **Paste the following content** into the file, making sure to replace `"C:\\path\\to\\your\\anime_renamer.py"` with the actual path to the `anime_renamer.py` script on your system.

    **Important:** You must use double backslashes (`\\`) in the path.

    ```reg
    Windows Registry Editor Version 5.00

    [HKEY_CLASSES_ROOT\Directory\Background\shell\AnimeRenamer]
    @="Rename Anime Files"

    [HKEY_CLASSES_ROOT\Directory\Background\shell\AnimeRenamer\command]
    @="pythonw.exe \"C:\\path\\to\\your\\anime_renamer.py\" \"%V\""
    ```

3.  **Save the file** and then **double-click it** to add the new keys to the Windows Registry.

4.  You should now see a "Rename Anime Files" option when you right-click inside a folder in Windows File Explorer.
