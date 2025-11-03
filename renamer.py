import os
import sys
import subprocess
import platform
import re
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict

try:
    import anitopy
except ImportError:
    print("Anitopy library not found. Please install it using: pip install anitopy")
    sys.exit(1)

VIDEO_EXTENSIONS = ['.mkv', '.mp4', '.avi', '.mov']
SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.sub']
LOG_FILE = 'rename_script_log.txt'

# --- Core Logic: Smart Matching ---

def parse_filename(filepath: str) -> Optional[Dict[str, any]]:
    filename = os.path.basename(filepath)
    parsed_data = anitopy.parse(filename)
    title, ep_num = parsed_data.get('anime_title'), parsed_data.get('episode_number')
    if not title or not ep_num: return None
    season = parsed_data.get('anime_season', '01')
    _, extension = os.path.splitext(filename)
    return {'title': title.strip(), 'season': int(season), 'episode': int(ep_num), 'extension': extension, 'original_filename': filepath, 'is_video': extension.lower() in VIDEO_EXTENSIONS}

def calculate_season_offsets(files: List[Dict[str, any]]) -> Dict[int, int]:
    episodes_per_season = defaultdict(int)
    for f in files:
        season, episode = f['season'], f['episode']
        if episode > episodes_per_season[season]: episodes_per_season[season] = episode
    offsets, total_offset = {}, 0
    for season_num in sorted(episodes_per_season.keys()):
        offsets[season_num] = total_offset
        total_offset += episodes_per_season[season_num]
    return offsets

def find_smart_match(video: Dict[str, any], subtitles: List[Dict[str, any]], offsets: Dict[int, int]) -> Optional[Dict[str, any]]:
    absolute_episode_num = offsets.get(video['season'], 0) + video['episode']
    for sub in subtitles:
        if sub['season'] == video['season'] and sub['episode'] == video['episode']: return sub
        if sub['season'] == 1 and sub['episode'] == absolute_episode_num: return sub
    return None

# --- Rclone & Logging Helpers (Framework) ---

def load_processed_dirs() -> Set[str]:
    if not os.path.exists(LOG_FILE): return set()
    with open(LOG_FILE, 'r') as f: return set(line.strip() for line in f)

def log_processed_dir(remote_dir: str):
    with open(LOG_FILE, 'a') as f: f.write(f"{remote_dir}\n")

def get_rclone_remotes(conf_path: str) -> List[str]:
    remotes = []
    with open(conf_path, 'r') as f:
        for line in f:
            if line.strip().startswith('[') and line.strip().endswith(']'):
                remotes.append(line.strip()[1:-1])
    return remotes

# --- Processing Functions (To be completed) ---

def process_show_group_local(show_title: str, files: List[Dict[str, any]]) -> Tuple[List[Tuple[str, str]], List[str]]:
    videos = sorted([f for f in files if f['is_video']], key=lambda x: (x['season'], x['episode']))
    subtitles = [f for f in files if not f['is_video']]
    if not videos: return [], []

    season_offsets = calculate_season_offsets(videos)
    renamed_files, unmatched_videos = [], []

    for video in videos:
        match = find_smart_match(video, subtitles, season_offsets)
        if match:
            new_base_name = f"{video['title']} - S{video['season']:02d}E{video['episode']:02d}"
            old_video_path, old_sub_path = video['original_filename'], match['original_filename']
            new_video_path = os.path.join(os.path.dirname(old_video_path), f"{new_base_name}{video['extension']}")
            new_sub_path = os.path.join(os.path.dirname(old_sub_path), f"{new_base_name}{match['extension']}")

            video_renamed, sub_renamed = False, False
            if old_video_path != new_video_path:
                try: os.rename(old_video_path, new_video_path); video_renamed = True
                except OSError as e: print(f"  Error renaming video '{os.path.basename(old_video_path)}': {e}")
            if old_sub_path != new_sub_path:
                try: os.rename(old_sub_path, new_sub_path); sub_renamed = True
                except OSError as e: print(f"  Error renaming subtitle '{os.path.basename(old_sub_path)}': {e}")

            if video_renamed: renamed_files.append((os.path.basename(old_video_path), os.path.basename(new_video_path)))
            if sub_renamed: renamed_files.append((os.path.basename(old_sub_path), os.path.basename(new_sub_path)))

            subtitles.remove(match)
        else:
            unmatched_videos.append(video['original_filename'])

    return renamed_files, unmatched_videos

def process_all_files_local(file_paths: List[str]) -> Tuple[List[Tuple[str, str]], List[str]]:
    parsed_files = [p for p in (parse_filename(path) for path in file_paths) if p]
    grouped_by_show = defaultdict(list)
    for pf in parsed_files: grouped_by_show[pf['title']].append(pf)
    total_renamed, total_unmatched = [], []
    for show_title, show_files in grouped_by_show.items():
        renamed, unmatched = process_show_group_local(show_title, show_files)
        total_renamed.extend(renamed)
        total_unmatched.extend(unmatched)
    return total_renamed, total_unmatched

def process_local_directory(directory: str):
    print(f"--- Scanning Local Directory: {directory} ---")
    all_paths = [os.path.join(r, f) for r, _, fs in os.walk(directory) for f in fs]
    renamed, unmatched = process_all_files_local(all_paths)
    _print_report(renamed, unmatched)

def rename_rclone_file(remote: str, old_path: str, new_path: str):
    """Renames a file on an rclone remote, handling potential errors."""
    try:
        command = ['rclone', 'moveto', f'{remote}:{old_path}', f'{remote}:{new_path}']
        # Use capture_output to prevent verbose rclone output unless there's an error
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        # rclone might fail if the file is locked, etc.
        print(f"  Error renaming '{os.path.basename(old_path)}': {e.stderr.strip()}")

def process_show_group_rclone(remote: str, show_title: str, files: List[Dict[str, any]]) -> Tuple[List[Tuple[str, str]], List[str]]:
    videos = sorted([f for f in files if f['is_video']], key=lambda x: (x['season'], x['episode']))
    subtitles = [f for f in files if not f['is_video']]
    if not videos: return [], []

    season_offsets = calculate_season_offsets(videos)
    renamed_files, unmatched_videos = [], []

    for video in videos:
        match = find_smart_match(video, subtitles, season_offsets)
        if match:
            new_base_name = f"{video['title']} - S{video['season']:02d}E{video['episode']:02d}"
            old_video_path, old_sub_path = video['original_filename'], match['original_filename']
            new_video_path = os.path.join(os.path.dirname(old_video_path), f"{new_base_name}{video['extension']}")
            new_sub_path = os.path.join(os.path.dirname(old_sub_path), f"{new_base_name}{match['extension']}")

            video_renamed, sub_renamed = False, False
            if old_video_path != new_video_path:
                rename_rclone_file(remote, old_video_path, new_video_path)
                video_renamed = True
            if old_sub_path != new_sub_path:
                rename_rclone_file(remote, old_sub_path, new_sub_path)
                sub_renamed = True

            if video_renamed: renamed_files.append((os.path.basename(old_video_path), os.path.basename(new_video_path)))
            if sub_renamed: renamed_files.append((os.path.basename(old_sub_path), os.path.basename(new_sub_path)))

            subtitles.remove(match)
        else:
            unmatched_videos.append(video['original_filename'])

    return renamed_files, unmatched_videos

def process_rclone_remote(remote: str, processed_dirs: Set[str]):
    print(f"\n--- Processing Rclone Remote: {remote} ---")
    try:
        command = ['rclone', 'lsf', '-R', '--files-only', f'{remote}:']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        all_files = result.stdout.strip().split('\n')
        if not all_files or (len(all_files) == 1 and not all_files[0]):
            print(f"Remote '{remote}' appears to be empty."); return

        files_by_dir = defaultdict(list)
        for file_path in all_files:
            dir_name = os.path.dirname(file_path)
            files_by_dir[dir_name].append(file_path)

        for directory, files_in_dir in files_by_dir.items():
            remote_dir_id = f"{remote}:{directory}"
            if remote_dir_id in processed_dirs:
                print(f"Skipping already processed directory: {directory}")
                continue

            print(f"\nScanning directory: {directory}")
            parsed_files = [p for p in (parse_filename(f) for f in files_in_dir) if p]
            if not any(f['is_video'] for f in parsed_files):
                print("  No video files found to process."); log_processed_dir(remote_dir_id); continue

            grouped_by_show = defaultdict(list)
            for pf in parsed_files: grouped_by_show[pf['title']].append(pf)

            dir_renamed, dir_unmatched = [], []
            for show_title, show_files in grouped_by_show.items():
                renamed, unmatched = process_show_group_rclone(remote, show_title, show_files)
                dir_renamed.extend(renamed)
                dir_unmatched.extend(unmatched)

            _print_report(dir_renamed, dir_unmatched)
            log_processed_dir(remote_dir_id)

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Fatal error processing remote '{remote}': Check rclone is installed and configured. Error: {e}")

# --- UI and Reporting ---

def _print_report(renamed_files: list, unmatched_videos: list):
    print("\n--- Overall Operation Summary ---")
    if renamed_files:
        print("\nSuccessfully renamed:")
        for old, new in renamed_files: print(f"  '{old}' -> '{new}'")
    else: print("\nNo files were renamed.")
    if unmatched_videos:
        print("\nVideos with no matching subtitle:")
        for video in unmatched_videos: print(f"  - {os.path.basename(video)}")
    if not renamed_files and not unmatched_videos:
        print("Nothing to do. All files may be already organized or no media was found.")

# --- Main Execution Block ---

def handle_windows():
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        process_local_directory(sys.argv[1])
    else:
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path)
        else: print(f"Error: '{user_path}' is not a valid directory.")

def handle_linux():
    conf_file = 'rclone.conf'
    if os.path.exists(conf_file):
        print("rclone.conf found. Processing remotes...")
        processed_dirs = load_processed_dirs()
        remotes = get_rclone_remotes(conf_file)
        if not remotes: print("No remotes found in rclone.conf."); return
        for remote in remotes:
            process_rclone_remote(remote, processed_dirs)
    elif len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        process_local_directory(sys.argv[1])
    else:
        print("rclone.conf not found. Defaulting to interactive local mode.")
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path)
        else: print(f"Error: '{user_path}' is not a valid directory.")

def main():
    system = platform.system()
    if system == 'Windows': handle_windows()
    elif system == 'Linux': handle_linux()
    else:
        print(f"Unsupported OS: {system}. Defaulting to local processing.")
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path)
        else: print(f"Error: '{user_path}' is not a valid directory.")

if __name__ == '__main__':
    main()
