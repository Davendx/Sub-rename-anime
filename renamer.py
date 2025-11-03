import os
import sys
import subprocess
import platform
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict
import json

try:
    import anitopy
    import requests
except ImportError:
    logging.critical("A required library was not found. Please install it using: pip install anitopy requests")
    sys.exit(1)

VIDEO_EXTENSIONS = ['.mkv', '.mp4', '.avi', '.mov']
SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.sub']
LOG_FILE = 'rename_script_log.txt'
ANILIST_API_URL = 'https://graphql.anilist.co'
ANILIST_CACHE_FILE = 'anilist_cache.json'

# --- Logging ---

def setup_logging():
    log_filename = f"renamer_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=log_filename, filemode='w')
    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    logging.getLogger('').addHandler(console)
    print(f"Detailed log will be written to: {log_filename}")

# --- Caching ---

def load_cache() -> Dict[str, any]:
    if not os.path.exists(ANILIST_CACHE_FILE): return {}
    try:
        with open(ANILIST_CACHE_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, IOError): return {}

def save_cache(cache: Dict[str, any]):
    try:
        with open(ANILIST_CACHE_FILE, 'w') as f: json.dump(cache, f, indent=2)
    except IOError as e:
        logging.warning(f"Could not save AniList cache file: {e}")

# --- AniList API Communication ---

def search_anilist(search_title: str) -> List[Dict[str, any]]:
    query = '''
    query ($search: String) {
      Page(page: 1, perPage: 5) {
        media(search: $search, type: ANIME, sort: POPULARITY_DESC) {
          id
          title { romaji english }
          popularity
        }
      }
    }
    '''
    variables = {'search': search_title}
    try:
        response = requests.post(ANILIST_API_URL, json={'query': query, 'variables': variables})
        response.raise_for_status()
        data = response.json()
        matches = data.get('data', {}).get('Page', {}).get('media', [])
        return [{'romaji': m['title']['romaji'], 'english': m['title']['english'], 'popularity': m['popularity']} for m in matches]
    except requests.RequestException as e:
        logging.error(f"Error communicating with AniList API: {e}")
        return []

def get_anilist_info_with_cache(search_title: str, cache: Dict[str, any]) -> List[Dict[str, any]]:
    if search_title in cache: return cache[search_title]
    results = search_anilist(search_title)
    cache[search_title] = results
    return results

# --- Core Logic: File Parsing and Matching ---

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

# --- Local File Processing ---

def process_show_group_local(show_title: str, files: List[Dict[str, any]]) -> Tuple[List[Tuple[str, str]], List[str]]:
    videos = sorted([f for f in files if f['is_video']], key=lambda x: (x['season'], x['episode']))
    subtitles = [f for f in files if not f['is_video']]
    if not videos: return [], []
    season_offsets = calculate_season_offsets(videos)
    renamed_files, unmatched_videos = [], []
    for video in videos:
        match = find_smart_match(video, subtitles, season_offsets)
        if match:
            subtitles.remove(match)
        else:
            unmatched_videos.append(video)
    if len(unmatched_videos) > 0 and len(unmatched_videos) == len(subtitles):
        logging.info(f"Attempting relative match for {len(unmatched_videos)} video(s) of '{show_title}'.")
        sorted_videos = sorted(unmatched_videos, key=lambda x: x['episode'])
        sorted_subtitles = sorted(subtitles, key=lambda x: (x['season'], x['episode']))
        newly_matched_videos = []
        for video, sub_match in zip(sorted_videos, sorted_subtitles):
            newly_matched_videos.append(video)
            new_base_name = f"{video['title']} - S{sub_match['season']:02d}E{sub_match['episode']:02d}"
            old_video_path, old_sub_path = video['original_filename'], sub_match['original_filename']
            new_video_path = os.path.join(os.path.dirname(old_video_path), f"{new_base_name}{video['extension']}")
            new_sub_path = os.path.join(os.path.dirname(old_sub_path), f"{new_base_name}{sub_match['extension']}")
            if old_video_path != new_video_path:
                try: os.rename(old_video_path, new_video_path); renamed_files.append((os.path.basename(old_video_path), os.path.basename(new_video_path)))
                except OSError as e: logging.error(f"Error renaming video '{os.path.basename(old_video_path)}': {e}")
            if old_sub_path != new_sub_path:
                try: os.rename(old_sub_path, new_sub_path); renamed_files.append((os.path.basename(old_sub_path), os.path.basename(new_sub_path)))
                except OSError as e: logging.error(f"Error renaming subtitle '{os.path.basename(old_sub_path)}': {e}")
        unmatched_videos = [v['original_filename'] for v in unmatched_videos if v not in newly_matched_videos]
    else:
        unmatched_videos = [v['original_filename'] for v in unmatched_videos]
    return renamed_files, unmatched_videos

def prompt_for_selection(parsed_title: str, results: List[Dict[str, any]]) -> Optional[Dict[str, any]]:
    print(f"\nMultiple matches found for '{parsed_title}'. Please choose one:")
    for i, result in enumerate(results):
        print(f"  [{i+1}] {result.get('romaji', 'N/A')} / {result.get('english', 'N/A')} (Pop: {result['popularity']})")
    print("  [0] Skip this show")
    try:
        choice = int(input("Enter your choice (number): "))
        if choice == 0: return None
        if 1 <= choice <= len(results): return results[choice - 1]
    except (ValueError, IndexError): pass
    print("Invalid choice. Skipping.")
    return None

def process_all_files_local(file_paths: List[str], anilist_cache: Dict[str, any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    parsed_files = [p for p in (parse_filename(path) for path in file_paths) if p]
    initial_groups = defaultdict(list)
    for pf in parsed_files: initial_groups[pf['title']].append(pf)
    official_groups = defaultdict(list)
    unresolved_files = []
    logging.info("\n--- Resolving Show Titles with AniList ---")
    is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
    for parsed_title, files in initial_groups.items():
        logging.info(f"Searching for '{parsed_title}'...")
        api_results = get_anilist_info_with_cache(parsed_title, anilist_cache)
        official_info = None
        if not api_results:
            logging.warning(f"  -> No match found for '{parsed_title}'. Skipping."); unresolved_files.extend(files); continue
        if len(api_results) > 1 and is_interactive:
            official_info = prompt_for_selection(parsed_title, api_results)
        else:
            official_info = api_results[0]
        if not official_info:
            logging.warning(f"  -> Skipped '{parsed_title}' by user or ambiguity."); unresolved_files.extend(files); continue
        official_title = official_info.get('romaji') or official_info.get('english')
        if not official_title:
            logging.warning(f"  -> Match found for '{parsed_title}', but has no valid title. Skipping."); unresolved_files.extend(files); continue
        logging.info(f"  -> Matched '{parsed_title}' to '{official_title}'.")
        for f in files: f['title'] = official_title
        official_groups[official_title].extend(files)
    total_renamed, total_unmatched = [], []
    for show_title, show_files in official_groups.items():
        renamed, unmatched = process_show_group_local(show_title, show_files)
        total_renamed.extend(renamed)
        total_unmatched.extend(unmatched)
    total_unmatched.extend([f['original_filename'] for f in unresolved_files if f['is_video']])
    return total_renamed, total_unmatched

def process_local_directory(directory: str, anilist_cache: Dict[str, any]):
    logging.info(f"--- Scanning Local Directory: {directory} ---")
    all_paths = [os.path.join(r, f) for r, _, fs in os.walk(directory) for f in fs]
    renamed, unmatched = process_all_files_local(all_paths, anilist_cache)
    _print_report(renamed, unmatched)

# --- Rclone Processing ---

def rename_rclone_file(remote: str, old_path: str, new_path: str):
    try:
        command = ['rclone', 'moveto', f'{remote}:{old_path}', f'{remote}:{new_path}']
        subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error renaming '{os.path.basename(old_path)}': {e.stderr.strip()}")

def process_show_group_rclone(remote: str, show_title: str, files: List[Dict[str, any]]) -> Tuple[List[Tuple[str, str]], List[str]]:
    videos = sorted([f for f in files if f['is_video']], key=lambda x: (x['season'], x['episode']))
    subtitles = [f for f in files if not f['is_video']]
    if not videos: return [], []
    season_offsets = calculate_season_offsets(videos)
    renamed_files, unmatched_videos = [], []
    for video in videos:
        match = find_smart_match(video, subtitles, season_offsets)
        if match:
            subtitles.remove(match)
        else:
            unmatched_videos.append(video)
    if len(unmatched_videos) > 0 and len(unmatched_videos) == len(subtitles):
        logging.info(f"Attempting relative match for {len(unmatched_videos)} video(s) of '{show_title}'.")
        sorted_videos = sorted(unmatched_videos, key=lambda x: x['episode'])
        sorted_subtitles = sorted(subtitles, key=lambda x: (x['season'], x['episode']))
        newly_matched_videos = []
        for video, sub_match in zip(sorted_videos, sorted_subtitles):
            newly_matched_videos.append(video)
            new_base_name = f"{show_title} - S{sub_match['season']:02d}E{sub_match['episode']:02d}"
            old_video_path, old_sub_path = video['original_filename'], sub_match['original_filename']
            new_video_path = os.path.join(os.path.dirname(old_video_path), f"{new_base_name}{video['extension']}")
            new_sub_path = os.path.join(os.path.dirname(old_sub_path), f"{new_base_name}{sub_match['extension']}")
            if old_video_path != new_video_path:
                rename_rclone_file(remote, old_video_path, new_video_path)
                renamed_files.append((os.path.basename(old_video_path), os.path.basename(new_video_path)))
            if old_sub_path != new_sub_path:
                rename_rclone_file(remote, old_sub_path, new_sub_path)
                renamed_files.append((os.path.basename(old_sub_path), os.path.basename(new_sub_path)))
        unmatched_videos = [v['original_filename'] for v in unmatched_videos if v not in newly_matched_videos]
    else:
        unmatched_videos = [v['original_filename'] for v in unmatched_videos]
    return renamed_files, unmatched_videos

def resolve_show_title_rclone(parsed_title: str, anilist_cache: Dict[str, any]) -> Optional[str]:
    logging.info(f"Searching for '{parsed_title}'...")
    api_results = get_anilist_info_with_cache(parsed_title, anilist_cache)
    if not api_results:
        logging.warning(f"  -> No match found for '{parsed_title}'. Skipping."); return None
    if len(api_results) > 1 and api_results[1]['popularity'] > (api_results[0]['popularity'] * 0.90):
        logging.warning(f"  -> Ambiguous results for '{parsed_title}'. Top two are '{api_results[0]['romaji']}' and '{api_results[1]['romaji']}'. Skipping."); return None
    official_info = api_results[0]
    official_title = official_info.get('romaji') or official_info.get('english')
    if not official_title:
        logging.warning(f"  -> Match found for '{parsed_title}', but it has no valid title. Skipping."); return None
    logging.info(f"  -> Matched '{parsed_title}' to '{official_title}'.")
    return official_title

def process_rclone_remote(remote: str, processed_dirs: Set[str], anilist_cache: Dict[str, any]):
    logging.info(f"Processing Rclone Remote: {remote}")
    try:
        command = ['rclone', 'lsf', '-R', '--files-only', f'{remote}:']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        all_files = result.stdout.strip().split('\n')
        if not all_files or (len(all_files) == 1 and not all_files[0]):
            logging.info(f"Remote '{remote}' appears to be empty."); return
        files_by_dir = defaultdict(list)
        for f in all_files: files_by_dir[os.path.dirname(f)].append(f)
        for directory, files_in_dir in files_by_dir.items():
            remote_dir_id = f"{remote}:{directory}"
            if remote_dir_id in processed_dirs: continue
            logging.info(f"Scanning directory: {directory}")
            parsed_files = [p for p in (parse_filename(f) for f in files_in_dir) if p]
            if not any(f['is_video'] for f in parsed_files):
                logging.info("  No video files found."); log_processed_dir(remote_dir_id); continue
            initial_groups = defaultdict(list)
            for pf in parsed_files: initial_groups[pf['title']].append(pf)
            official_groups = defaultdict(list)
            unresolved_files = []
            for parsed_title, files in initial_groups.items():
                official_title = resolve_show_title_rclone(parsed_title, anilist_cache)
                if official_title:
                    for f in files: f['title'] = official_title
                    official_groups[official_title].extend(files)
                else:
                    unresolved_files.extend(files)
            dir_renamed, dir_unmatched = [], []
            for show_title, show_files in official_groups.items():
                renamed, unmatched = process_show_group_rclone(remote, show_title, show_files)
                dir_renamed.extend(renamed)
                dir_unmatched.extend(unmatched)
            dir_unmatched.extend([f['original_filename'] for f in unresolved_files if f['is_video']])
            _print_report(dir_renamed, dir_unmatched)
            log_processed_dir(remote_dir_id)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.critical(f"Fatal error processing remote '{remote}': Check rclone is installed. Error: {e}")

# --- UI and Reporting ---

def _print_report(renamed_files: list, unmatched_videos: list):
    report = "\n--- Overall Operation Summary ---\n"
    if renamed_files:
        report += "\nSuccessfully renamed:\n"
        for old, new in renamed_files: report += f"  '{old}' -> '{new}'\n"
    else: report += "\nNo files were renamed.\n"
    if unmatched_videos:
        report += "\nVideos with no matching subtitle:\n"
        for video in unmatched_videos: report += f"  - {os.path.basename(video)}\n"
    if not renamed_files and not unmatched_videos:
        report += "Nothing to do. All files may be already organized or no media was found.\n"
    # Print to console and log
    print(report)
    logging.info(report)

# --- Rclone Placeholder Functions ---

PROCESSED_DIRS_FILE = 'processed_dirs.log'

def load_processed_dirs() -> Set[str]:
    """Loads a set of previously processed directory IDs to avoid reprocessing."""
    if not os.path.exists(PROCESSED_DIRS_FILE):
        return set()
    try:
        with open(PROCESSED_DIRS_FILE, 'r') as f:
            return {line.strip() for line in f}
    except IOError:
        return set()

def log_processed_dir(dir_id: str):
    """Logs a directory ID as processed."""
    try:
        with open(PROCESSED_DIRS_FILE, 'a') as f:
            f.write(f"{dir_id}\n")
    except IOError as e:
        logging.warning(f"Could not write to processed directories log: {e}")

def get_rclone_remotes(conf_file: str) -> List[str]:
    """Parses rclone.conf to get a list of remote names."""
    remotes = []
    try:
        with open(conf_file, 'r') as f:
            for line in f:
                match = re.match(r'^\[(.+)\]$', line.strip())
                if match:
                    remotes.append(match.group(1))
    except IOError as e:
        logging.error(f"Could not read rclone config file: {e}")
    return remotes

# --- Main Execution Block ---

def handle_windows(anilist_cache: Dict[str, any]):
    # Setup logging to file for Windows as well, but less verbose to console
    log_filename = f"renamer_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=log_filename, filemode='w')
    # Keep console output clean
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('%(message)s')) # Only show message on console
    logging.getLogger('').addHandler(console)

    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        process_local_directory(sys.argv[1], anilist_cache)
    else:
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path, anilist_cache)
        else: logging.error(f"Error: '{user_path}' is not a valid directory.")

def handle_linux(anilist_cache: Dict[str, any]):
    setup_logging()
    conf_file = 'rclone.conf'
    if os.path.exists(conf_file):
        logging.info("rclone.conf found. Processing remotes...")
        processed_dirs = load_processed_dirs()
        remotes = get_rclone_remotes(conf_file)
        if not remotes: logging.warning("No remotes found in rclone.conf."); return
        for remote in remotes:
            process_rclone_remote(remote, processed_dirs, anilist_cache)
    elif len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        process_local_directory(sys.argv[1], anilist_cache)
    else:
        logging.info("rclone.conf not found. Defaulting to interactive local mode.")
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path, anilist_cache)
        else: logging.error(f"Error: '{user_path}' is not a valid directory.")

def main():
    anilist_cache = load_cache()
    system = platform.system()
    try:
        if system == 'Windows': handle_windows(anilist_cache)
        elif system == 'Linux': handle_linux(anilist_cache)
        else:
            logging.warning(f"Unsupported OS: {system}. Defaulting to local processing.")
            user_path = input("Please enter the path to the folder to process: ")
            if os.path.isdir(user_path): process_local_directory(user_path, anilist_cache)
            else: logging.error(f"Error: '{user_path}' is not a valid directory.")
    finally:
        save_cache(anilist_cache)
        logging.info("AniList cache saved.")
        if system == 'Windows' and sys.stdin.isatty() and len(sys.argv) == 1:
            input("\nProcessing complete. Press Enter to exit.")

if __name__ == '__main__':
    main()
