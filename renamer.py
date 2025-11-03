import os
import sys
import subprocess
import platform
import re
from typing import List, Dict, Optional, Set

try:
    import anitopy
except ImportError:
    print("Anitopy library not found. Please install it using: pip install anitopy")
    sys.exit(1)

VIDEO_EXTENSIONS = ['.mkv', '.mp4', '.avi', '.mov']
SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.sub']
LOG_FILE = 'rename_script_log.txt'

# --- Core Logic ---

def parse_filename(filepath: str) -> Optional[Dict[str, str]]:
    """
    Parses a filename using anitopy to extract media information.
    The filepath should be the full path to the file.
    """
    filename = os.path.basename(filepath)
    parsed_data = anitopy.parse(filename)

    if not parsed_data.get('anime_title') or not parsed_data.get('episode_number'):
        return None

    season = parsed_data.get('anime_season', '01')
    _, extension = os.path.splitext(filename)

    return {
        'title': parsed_data.get('anime_title'),
        'season': f"{int(season):02d}",
        'episode': f"{int(parsed_data.get('episode_number')):02d}",
        'extension': extension,
        'original_filename': filepath  # Keep the full path
    }

def find_matching_subtitle(video_info: Dict[str, str], subtitles: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Finds a matching subtitle for a given video file."""
    for sub_info in subtitles:
        if (video_info['title'] == sub_info['title'] and
            video_info['season'] == sub_info['season'] and
            video_info['episode'] == sub_info['episode']):
            return sub_info
    return None

# --- Local File Processing (Windows) ---

def process_local_directory(directory: str):
    """Scans a local directory, matches, and renames files."""
    print(f"--- Processing Local Directory: {directory} ---")

    all_files_in_dir = []
    for root, _, files in os.walk(directory):
        for file in files:
            all_files_in_dir.append(os.path.join(root, file))

    videos = [parse_filename(f) for f in all_files_in_dir if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
    subtitles = [parse_filename(f) for f in all_files_in_dir if os.path.splitext(f)[1].lower() in SUBTITLE_EXTENSIONS]

    videos = [v for v in videos if v]
    subtitles = [s for s in subtitles if s]

    renamed_files, unmatched_videos = [], []

    for video_info in videos:
        matching_sub = find_matching_subtitle(video_info, subtitles)
        if matching_sub:
            base_new_name = f"{video_info['title']} - S{video_info['season']}E{video_info['episode']}"

            video_dir = os.path.dirname(video_info['original_filename'])
            sub_dir = os.path.dirname(matching_sub['original_filename'])

            new_video_path = os.path.join(video_dir, f"{base_new_name}{video_info['extension']}")
            new_sub_path = os.path.join(sub_dir, f"{base_new_name}{matching_sub['extension']}")

            try:
                if video_info['original_filename'] != new_video_path:
                    os.rename(video_info['original_filename'], new_video_path)
                if matching_sub['original_filename'] != new_sub_path:
                    os.rename(matching_sub['original_filename'], new_sub_path)
                renamed_files.append((os.path.basename(video_info['original_filename']), os.path.basename(new_video_path)))
            except OSError as e:
                print(f"Error renaming files: {e}")
        else:
            unmatched_videos.append(video_info['original_filename'])

    _print_report(renamed_files, unmatched_videos)

# --- Rclone Processing (Linux) ---

def load_processed_dirs() -> Set[str]:
    """Loads the set of processed directories from the log file."""
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE, 'r') as f:
        return set(line.strip() for line in f)

def log_processed_dir(remote_dir: str):
    """Adds a directory to the log file."""
    with open(LOG_FILE, 'a') as f:
        f.write(f"{remote_dir}\n")

def get_rclone_remotes(conf_path: str) -> List[str]:
    """Parses rclone.conf to get a list of remote names."""
    remotes = []
    with open(conf_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                remotes.append(line[1:-1])
    return remotes

def rename_rclone_file(remote: str, old_path: str, new_path: str):
    """Renames a file on an rclone remote."""
    try:
        command = ['rclone', 'moveto', f'{remote}:{old_path}', f'{remote}:{new_path}']
        subprocess.run(command, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  Error renaming '{old_path}': {e.stderr.strip()}")

def process_rclone_remote(remote: str, processed_dirs: Set[str]):
    """Scans and processes an entire rclone remote."""
    print(f"\n--- Processing Rclone Remote: {remote} ---")
    try:
        command = ['rclone', 'lsf', '-R', '--files-only', f'{remote}:']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        all_files = result.stdout.strip().split('\n')
        if not all_files or (len(all_files) == 1 and not all_files[0]):
            print(f"Remote '{remote}' appears to be empty.")
            return

        files_by_dir = {}
        for file_path in all_files:
            dir_name = os.path.dirname(file_path)
            if dir_name not in files_by_dir: files_by_dir[dir_name] = []
            files_by_dir[dir_name].append(file_path)

        for directory, files in files_by_dir.items():
            remote_dir_id = f"{remote}:{directory}"
            if remote_dir_id in processed_dirs:
                print(f"Skipping already processed directory: {remote_dir_id}")
                continue

            print(f"\nScanning directory: {remote_dir_id}")
            videos = [parse_filename(f) for f in files if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
            subtitles = [parse_filename(f) for f in files if os.path.splitext(f)[1].lower() in SUBTITLE_EXTENSIONS]
            videos, subtitles = [v for v in videos if v], [s for s in subtitles if s]

            if not videos:
                print("  No video files found to process.")
                log_processed_dir(remote_dir_id)
                continue

            renamed_files, unmatched_videos = [], []
            for video_info in videos:
                matching_sub = find_matching_subtitle(video_info, subtitles)
                if matching_sub:
                    base_new_name = f"{video_info['title']} - S{video_info['season']}E{video_info['episode']}"
                    video_dir, sub_dir = os.path.dirname(video_info['original_filename']), os.path.dirname(matching_sub['original_filename'])
                    new_video_path = os.path.join(video_dir, f"{base_new_name}{video_info['extension']}")
                    new_sub_path = os.path.join(sub_dir, f"{base_new_name}{matching_sub['extension']}")

                    if video_info['original_filename'] != new_video_path:
                        rename_rclone_file(remote, video_info['original_filename'], new_video_path)
                    if matching_sub['original_filename'] != new_sub_path:
                        rename_rclone_file(remote, matching_sub['original_filename'], new_sub_path)
                    renamed_files.append((os.path.basename(video_info['original_filename']), os.path.basename(new_video_path)))
                else:
                    unmatched_videos.append(video_info['original_filename'])

            _print_report(renamed_files, unmatched_videos)
            log_processed_dir(remote_dir_id)

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Fatal error processing remote '{remote}': {e}")

# --- Platform Handling & Reporting ---

def _print_report(renamed_files: list, unmatched_videos: list):
    """Prints a summary of the operations."""
    print("--- Operation Summary ---")
    if renamed_files:
        print("\nSuccessfully renamed:")
        for old, new in renamed_files:
            print(f"  '{old}' -> '{new}'")
    else:
        print("\nNo files were renamed.")

    if unmatched_videos:
        print("\nVideos with no matching subtitle:")
        for video in unmatched_videos:
            print(f"  - {os.path.basename(video)}")

    if not renamed_files and not unmatched_videos:
        print("Nothing to do. The folder may be empty or already organized.")

def handle_windows():
    """Handles the script's execution on Windows."""
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        if os.path.isdir(target_path): process_local_directory(target_path)
        else: print(f"Error: Provided path '{target_path}' is not a valid directory.")
    else:
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path)
        else: print(f"Error: '{user_path}' is not a valid directory.")

def handle_linux():
    """Handles the script's execution on Linux."""
    conf_file = 'rclone.conf'
    if os.path.exists(conf_file):
        print("rclone.conf found. Processing remotes...")
        processed_dirs = load_processed_dirs()
        remotes = get_rclone_remotes(conf_file)
        if not remotes:
            print("No remotes found in rclone.conf.")
            return
        for remote in remotes:
            process_rclone_remote(remote, processed_dirs)
    else:
        print("rclone.conf not found. Defaulting to local mode.")
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path)
        else: print(f"Error: '{user_path}' is not a valid directory.")

if __name__ == '__main__':
    system = platform.system()
    if system == 'Windows':
        handle_windows()
    elif system == 'Linux':
        handle_linux()
    else:
        print(f"Unsupported OS: {system}. Defaulting to local processing.")
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path)
        else: print(f"Error: '{user_path}' is not a valid directory.")
