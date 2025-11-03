# Automatic Video and Subtitle Renamer

A powerful Python script to automatically scan directories, intelligently parse video and subtitle filenames, and rename them to a clean, standardized format for media players. It works on local files (Windows/Linux) and can also process cloud storage directly via `rclone`.

## Features

- **Intelligent Parsing:** Uses the `anitopy` library to accurately extract show titles, seasons, and episode numbers from complex filenames.
- **Standardized Naming:** Renames both video and subtitle files to `Show Name - S{season}E{episode}.ext`.
- **Cross-Platform:** Operates in two modes:
    - **Windows:** Can be run from the command line or integrated into the right-click context menu for easy folder processing.
    - **Linux:** Can process local folders or, if an `rclone.conf` file is present, it will automatically scan and process all configured `rclone` remotes.
- **Recursive Scanning:** Processes all files in the target directory and all of its subdirectories.
- **Persistent Logging:** When used with `rclone`, the script logs processed directories to avoid redundant scanning, saving time and resources on subsequent runs.

## Requirements

- **Python 3.6+**
- **anitopy library**
- **rclone** (for Linux remote processing)

## 1. Installation

1.  **Install Python:** If you don't have Python, download it from [python.org](https://www.python.org/downloads/) and install it. Make sure to check the box that says "Add Python to PATH" during installation.

2.  **Install `anitopy`:** Open a terminal or command prompt and run the following command:
    ```bash
    pip install anitopy
    ```

3.  **Install `rclone` (Linux Only):** If you plan to use the script with your cloud storage on Linux, install `rclone`. On Debian-based systems (like Ubuntu), you can use:
    ```bash
    sudo apt-get update && sudo apt-get install rclone
    ```

## 2. How to Use

### On Windows

Save the `renamer.py` script to a permanent location on your computer.

#### Option A: Run from Command Prompt

1.  Open a Command Prompt (`cmd.exe`).
2.  Navigate to the directory where you saved `renamer.py`.
3.  Run the script. It will prompt you to enter the path to the folder you want to process.
    ```bash
    python renamer.py
    ```

#### Option B: Add to Right-Click Context Menu (Recommended)

This allows you to right-click any folder and run the script on it directly.

1.  Press `Win + R`, type `regedit`, and press Enter to open the Registry Editor.
2.  Navigate to the following key:
    `HKEY_CLASSES_ROOT\Directory\Background\shell`
3.  Right-click the `shell` key and select `New` -> `Key`. Name it something descriptive, like `Rename Media Files`.
4.  Right-click the new key you just created (`Rename Media Files`) and select `New` -> `Key`. Name this new key `command`.
5.  With the `command` key selected, double-click the `(Default)` value in the right-hand pane.
6.  In the "Value data" field, you need to enter the command to run the script. It consists of the path to your Python executable, the path to your script, and a special argument `%V` which represents the folder you right-clicked.

    **Example:**
    `C:\Users\YourUser\AppData\Local\Programs\Python\Python39\python.exe "C:\Path\To\Your\renamer.py" "%V"`

    *   **Important:** You must replace the paths with the actual paths on your system. Right-click your Python shortcut and `renamer.py` file and go to "Properties" to find their exact locations.

### On Linux

Save the `renamer.py` script to a location of your choice.

#### Local Mode

If the script does not find an `rclone.conf` file in its directory, it will run in local mode.

1.  Open a terminal.
2.  Navigate to the directory where you saved the script.
3.  Run it. It will prompt you to enter the path to a local folder to process.
    ```bash
    python3 renamer.py
    ```

#### Rclone Mode

This is the script's most powerful feature. It allows you to directly organize files on your cloud storage without mounting it.

1.  **Locate your `rclone.conf` file.** This is typically found at `~/.config/rclone/rclone.conf`.
2.  **Copy (do not move)** your `rclone.conf` file into the same directory where you saved `renamer.py`.
3.  Run the script. It will automatically detect the config file, read all the remotes you have configured, and begin processing each one, folder by folder.
    ```bash
    python3 renamer.py
    ```

## 3. The Log File

When running in **Rclone Mode**, the script creates a file named `rename_script_log.txt`.

- **Purpose:** This file stores a list of every directory that the script has successfully scanned and processed. On subsequent runs, the script will read this log and **skip** any directory listed in it. This prevents the script from re-analyzing folders that are already organized, making it much more efficient.
- **Resetting:** If you ever want the script to re-scan all of your remotes from scratch, simply delete the `rename_script_log.txt` file.

---
***Disclaimer:*** *This script performs file renaming operations that can be difficult to reverse. It is always a good practice to test the script on a small, non-critical directory or have a backup of your data before running it on your entire library.*
