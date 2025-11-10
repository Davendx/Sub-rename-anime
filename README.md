# Anime Renamer

An intelligent Python script to rename anime video and subtitle files using metadata from AniList.co.

## Features

- **Intelligent Parsing:** Uses `anitopy` to parse existing filenames, even if they're messy.
- **Accurate Metadata:** Fetches canonical titles and seasonal information from the AniList GraphQL API.
- **Fuzzy Matching:** Automatically matches local files to the correct AniList entry, even with different titles or synonyms.
- **Season Inference:** Correctly handles continuous episode numbering across multiple seasons (e.g., episode 13 of a 12-episode season is correctly identified as S02E01).
- **Interactive Disambiguation:** Prompts the user to choose the correct anime when there are multiple possibilities.
- **Command-Line Interface:** Provides a flexible command-line interface with the following options:
    - `--dry-run`: Preview the renaming changes without applying them.
    - `--recursive`: Process subdirectories recursively.
    - `--verbose`: Enable detailed logging.
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

## Usage

You can run the script from the command line by providing the path to the directory you want to process:

```bash
python3 anime_renamer.py "path/to/your/anime/folder"
```

You can also use the available flags to modify the script's behavior:

-   `--dry-run`: Preview the renames without making any changes.
-   `--recursive`: Scan all subdirectories within the specified folder.
-   `--verbose`: See detailed logs of the script's operations.

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
