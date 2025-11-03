import os
import sys
import subprocess
import platform
import re
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict

try:
    import anitopy
    import requests
except ImportError:
    print("A required library was not found. Please install it using: pip install anitopy requests")
    sys.exit(1)

VIDEO_EXTENSIONS = ['.mkv', '.mp4', '.avi', '.mov']
import json

SUBTITLE_EXTENSIONS = ['.srt', '.ass', '.sub']
LOG_FILE = 'rename_script_log.txt'
ANILIST_API_URL = 'https://graphql.anilist.co'
ANILIST_CACHE_FILE = 'anilist_cache.json'

# --- Caching ---

def load_cache() -> Dict[str, any]:
    """Loads the AniList search cache from a JSON file."""
    if not os.path.exists(ANILIST_CACHE_FILE):
        return {}
    try:
        with open(ANILIST_CACHE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If the file is corrupted or unreadable, start with an empty cache
        return {}

def save_cache(cache: Dict[str, any]):
    """Saves the AniList search cache to a JSON file."""
    try:
        with open(ANILIST_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        print(f"\nWarning: Could not save AniList cache file: {e}")


# --- AniList API Communication ---

def search_anilist(search_title: str) -> List[Dict[str, any]]:
    """
    Searches for an anime on AniList and returns a list of potential matches.
    """
    query = '''
    query ($search: String) {
      Page(page: 1, perPage: 5) {
        media(search: $search, type: ANIME, sort: POPULARITY_DESC) {
          id
          title {
            romaji
            english
          }
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
        if not matches:
            return []

        # Format the results into a cleaner list
        return [
            {
                'romaji': m['title']['romaji'],
                'english': m['title']['english'],
                'popularity': m['popularity']
            }
            for m in matches
        ]
    except requests.RequestException as e:
        print(f"\nError communicating with AniList API: {e}")
        return []

def get_anilist_info_with_cache(search_title: str, cache: Dict[str, any]) -> List[Dict[str, any]]:
    """
    Retrieves AniList info for a title, using a cache to avoid redundant API calls.
    """
    cleaned_title = search_title.replace('-', ' ')
    if cleaned_title in cache:
        # print(f"Cache hit for '{cleaned_title}'") # Optional: for debugging
        return cache[cleaned_title]

    # print(f"Cache miss for '{cleaned_title}', searching online...") # Optional: for debugging
    results = search_anilist(cleaned_title)
    cache[cleaned_title] = results # Cache the result, even if it's an empty list
    return results

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
            new_base_name = f"{show_title} - S{video['season']:02d}E{video['episode']:02d}"
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

def prompt_for_selection(parsed_title: str, results: List[Dict[str, any]]) -> Optional[Dict[str, any]]:
    """Displays a prompt for the user to select the correct anime from a list."""
    print(f"\nMultiple matches found for '{parsed_title}'. Please choose one:")
    for i, result in enumerate(results):
        romaji = result.get('romaji', 'N/A')
        english = result.get('english', 'N/A')
        print(f"  [{i+1}] {romaji} / {english} (Popularity: {result['popularity']})")
    print("  [0] Skip this show")

    try:
        choice = input("Enter your choice (number): ")
        choice_num = int(choice)
        if choice_num == 0:
            return None
        if 1 <= choice_num <= len(results):
            return results[choice_num - 1]
    except (ValueError, IndexError):
        # Invalid input
        pass

    print("Invalid choice. Skipping this show.")
    return None

def normalize_title(title: str) -> str:
    return re.sub(r'[^\w\s]', '', title).strip().lower()

def process_all_files_local(file_paths: List[str], anilist_cache: Dict[str, any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    parsed_files = [p for p in (parse_filename(path) for path in file_paths) if p]

    # Resolve titles for all files first
    for pf in parsed_files:
        print(f"Searching for '{pf['title']}'...")
        api_results = get_anilist_info_with_cache(pf['title'], anilist_cache)
        official_info = None

        is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if not api_results:
            print(f"  -> No match found. Using original title.")
            continue

        if len(api_results) > 1 and is_interactive:
            official_info = prompt_for_selection(pf['title'], api_results)
        else:
            official_info = api_results[0]

        if not official_info:
            print(f"  -> Skipped by user or ambiguity. Using original title.")
            continue

        official_title = official_info.get('romaji') or official_info.get('english')
        if not official_title:
            print(f"  -> Match found, but has no valid title. Using original title.")
            continue

        print(f"  -> Matched '{pf['title']}' to '{official_title}'.")
        pf['title'] = official_title

    # Now group by a normalized version of the (potentially updated) title
    official_groups = defaultdict(list)
    for pf in parsed_files:
        official_groups[normalize_title(pf['title'])].append(pf)

    total_renamed, total_unmatched = [], []
    for normalized_title, show_files in official_groups.items():
        # Use the title from the first file in the group as the official title
        official_title = show_files[0]['title']
        renamed, unmatched = process_show_group_local(official_title, show_files)
        total_renamed.extend(renamed)
        total_unmatched.extend(unmatched)

    return total_renamed, total_unmatched

def process_local_directory(directory: str, anilist_cache: Dict[str, any]):
    print(f"--- Scanning Local Directory: {directory} ---")
    all_paths = [os.path.join(r, f) for r, _, fs in os.walk(directory) for f in fs]
    renamed, unmatched = process_all_files_local(all_paths, anilist_cache)
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
            new_base_name = f"{show_title} - S{video['season']:02d}E{video['episode']:02d}"
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

def resolve_show_title_rclone(parsed_title: str, anilist_cache: Dict[str, any]) -> Optional[str]:
    """Resolves a parsed title to an official AniList title for non-interactive mode."""
    print(f"Searching for '{parsed_title}'...")
    api_results = get_anilist_info_with_cache(parsed_title, anilist_cache)

    if not api_results:
        print(f"  -> No match found. Skipping.")
        return None

    # Safety check: if the top two results have very similar popularity, it's ambiguous.
    # We define "similar" as the second being > 90% as popular as the first.
    if len(api_results) > 1 and api_results[1]['popularity'] > (api_results[0]['popularity'] * 0.90):
        print(f"  -> Ambiguous results. Top two are '{api_results[0]['romaji']}' and '{api_results[1]['romaji']}'. Skipping.")
        return None

    official_info = api_results[0]
    official_title = official_info.get('romaji') or official_info.get('english')

    if not official_title:
        print(f"  -> Match found, but it has no valid title. Skipping.")
        return None

    print(f"  -> Matched to '{official_title}'.")
    return official_title

def process_rclone_remote(remote: str, processed_dirs: Set[str], anilist_cache: Dict[str, any]):
    print(f"\n--- Processing Rclone Remote: {remote} ---")
    try:
        command = ['rclone', 'lsf', '-R', '--files-only', f'{remote}:']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        all_files = result.stdout.strip().split('\n')
        if not all_files or (len(all_files) == 1 and not all_files[0]):
            print(f"Remote '{remote}' appears to be empty."); return

        files_by_dir = defaultdict(list)
        for f in all_files: files_by_dir[os.path.dirname(f)].append(f)

        for directory, files_in_dir in files_by_dir.items():
            remote_dir_id = f"{remote}:{directory}"
            if remote_dir_id in processed_dirs: continue

            print(f"\nScanning directory: {directory}")
            parsed_files = [p for p in (parse_filename(f) for f in files_in_dir) if p]
            if not any(f['is_video'] for f in parsed_files):
                print("  No video files found."); log_processed_dir(remote_dir_id); continue

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

def handle_windows(anilist_cache: Dict[str, any]):
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        process_local_directory(sys.argv[1], anilist_cache)
    else:
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path, anilist_cache)
        else: print(f"Error: '{user_path}' is not a valid directory.")

def handle_linux(anilist_cache: Dict[str, any]):
    conf_file = 'rclone.conf'
    if os.path.exists(conf_file):
        print("rclone.conf found. Processing remotes...")
        processed_dirs = load_processed_dirs()
        remotes = get_rclone_remotes(conf_file)
        if not remotes: print("No remotes found in rclone.conf."); return
        for remote in remotes:
            process_rclone_remote(remote, processed_dirs, anilist_cache)
    elif len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        process_local_directory(sys.argv[1], anilist_cache)
    else:
        print("rclone.conf not found. Defaulting to interactive local mode.")
        user_path = input("Please enter the path to the folder to process: ")
        if os.path.isdir(user_path): process_local_directory(user_path, anilist_cache)
        else: print(f"Error: '{user_path}' is not a valid directory.")

def main():
    anilist_cache = load_cache()

    system = platform.system()
    try:
        if system == 'Windows': handle_windows(anilist_cache)
        elif system == 'Linux': handle_linux(anilist_cache)
        else:
            print(f"Unsupported OS: {system}. Defaulting to local processing.")
            user_path = input("Please enter the path to the folder to process: ")
            if os.path.isdir(user_path): process_local_directory(user_path, anilist_cache)
            else: print(f"Error: '{user_path}' is not a valid directory.")
    finally:
        # Ensure the cache is saved even if the script encounters an error
        save_cache(anilist_cache)
        print("\nAniList cache saved.")

if __name__ == '__main__':
    main()
