#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Anime Renamer
A script to rename anime video and subtitle files using AniList.co for metadata.
"""

import argparse
from collections import defaultdict
import logging
import os
import re
import sys
import anitopy
from fuzzywuzzy import process
from tqdm import tqdm
import xml.etree.ElementTree as ET
import anilist_api
import rclone_handler
import config

# Supported file extensions
VIDEO_EXTENSIONS = ('.mkv', '.mp4')
SUBTITLE_EXTENSIONS = ('.srt', '.ass')

def sanitize_filename(filename):
    """
    Remove characters that are invalid in filenames across different OS.
    """
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def find_files(directory, recursive, rclone_remote=None, rclone_config=None):
    """
    Find video and subtitle files in the given directory and group them by folder.
    """
    file_groups = defaultdict(lambda: {'videos': [], 'subtitles': []})

    if rclone_remote:
        files = rclone_handler.rclone_lsjson(directory, rclone_config)
        if files is None:
            return {}
        for file in tqdm(files, desc="Scanning remote files"):
            dir_path = os.path.dirname(file['Path'])
            if file['Path'].lower().endswith(VIDEO_EXTENSIONS):
                file_groups[dir_path]['videos'].append(file['Path'])
            elif file['Path'].lower().endswith(SUBTITLE_EXTENSIONS):
                file_groups[dir_path]['subtitles'].append(file['Path'])
    else:
        if recursive:
            for root, _, files in os.walk(directory):
                for file in tqdm(files, desc=f"Scanning {root}"):
                    item_path = os.path.join(root, file)
                    if file.lower().endswith(VIDEO_EXTENSIONS):
                        file_groups[root]['videos'].append(item_path)
                    elif file.lower().endswith(SUBTITLE_EXTENSIONS):
                        file_groups[root]['subtitles'].append(item_path)
        else:
            for item in tqdm(os.listdir(directory), desc=f"Scanning {directory}"):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    if item.lower().endswith(VIDEO_EXTENSIONS):
                        file_groups[directory]['videos'].append(item_path)
                    elif item.lower().endswith(SUBTITLE_EXTENSIONS):
                        file_groups[directory]['subtitles'].append(item_path)

    return {folder: files for folder, files in file_groups.items() if files['videos'] or files['subtitles']}


def choose_anime(results):
    """
    Prompt the user to select the correct anime from a list of AniList search results.
    """
    print("\nMultiple AniList results found. Please choose the correct one:")
    for i, anime in enumerate(results, 1):
        romaji = anime['title'].get('romaji', 'N/A')
        english = anime['title'].get('english', 'N/A')
        print(f"  {i}: {romaji} / {english} (Format: {anime.get('format', 'N/A')})")

    print("  0: Skip this folder (use parsed filename)")

    while True:
        try:
            choice_str = input(f"Enter your choice (0-{len(results)}): ")
            choice = int(choice_str)
            if 0 <= choice <= len(results):
                return results[choice - 1] if choice > 0 else None
            else:
                print("Invalid choice. Please try again.")
        except (ValueError, IndexError):
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            sys.exit(0)

def calculate_season_episode(absolute_episode, season_data):
    """
    Calculate the season and relative episode number from an absolute episode number.
    """
    if not season_data or absolute_episode <= 0:
        return 1, absolute_episode

    sorted_seasons = sorted(season_data, key=lambda s: s.get('id', 0))

    ep_offset = 0

    for i, season in enumerate(sorted_seasons):
        num_episodes = season.get('episodes')
        if num_episodes is None:
            if absolute_episode > ep_offset:
                 return i + 1, absolute_episode - ep_offset
            else:
                 break

        if absolute_episode <= ep_offset + num_episodes:
            return i + 1, absolute_episode - ep_offset

        ep_offset += num_episodes

    # Fallback if episode number is beyond all known seasons
    return None, None

def get_language_tag(filename):
    """
    Detect a language tag from the filename.
    """
    match = re.search(r'\[(eng|jpn)\]', filename, re.IGNORECASE)
    if match:
        return f" [{match.group(1).lower()}]"
    return ""

def get_unique_filepath(filepath):
    """
    Get a unique filepath by appending a version number if the file already exists.
    """
    if not os.path.exists(filepath):
        return filepath

    base, ext = os.path.splitext(filepath)
    version = 2
    while True:
        new_filepath = f"{base}_v{version}{ext}"
        if not os.path.exists(new_filepath):
            return new_filepath
        version += 1

def get_unique_rclone_filepath(remote, filepath, rclone_config=None):
    """
    Get a unique filepath on an rclone remote by appending a version number if the file already exists.
    """
    dir_path = os.path.dirname(filepath)
    remote_dir_path = f"{remote}:{dir_path}"

    existing_files = rclone_handler.rclone_lsf(remote_dir_path, rclone_config)

    if os.path.basename(filepath) not in existing_files:
        return filepath

    base, ext = os.path.splitext(filepath)
    version = 2
    while True:
        new_filename = f"{os.path.basename(base)}_v{version}{ext}"
        if new_filename not in existing_files:
            return os.path.join(dir_path, new_filename)
        version += 1

def create_nfo_file(nfo_path, anime_data, season, episode, has_video):
    """
    Create an .nfo file with the anime's metadata.
    """
    root = ET.Element("episodedetails")
    ET.SubElement(root, "title").text = f"Episode {episode:02d}"
    ET.SubElement(root, "season").text = str(season)
    ET.SubElement(root, "episode").text = str(episode)
    if anime_data:
        ET.SubElement(root, "showtitle").text = anime_data['title'].get('romaji') or anime_data['title'].get('english')
        ET.SubElement(root, "plot").text = anime_data.get('description', '')

    if not has_video:
        fileinfo = ET.SubElement(root, "fileinfo")
        streamdetails = ET.SubElement(fileinfo, "streamdetails")
        video = ET.SubElement(streamdetails, "video")
        ET.SubElement(video, "codec").text = "unknown"

    tree = ET.ElementTree(root)
    tree.write(nfo_path, encoding='utf-8', xml_declaration=True)


def process_folder(folder_path, files, anime_data, conf, dry_run, force_refresh, interactive, bundle_ova, export_nfo, verbose, rclone_remote=None, rclone_config=None):
    """
    Process and rename all video and subtitle files in a single folder.
    """
    all_files = sorted(files['videos'] + files['subtitles'])
    processed_episodes = set()

    season_data = []
    if anime_data:
        logging.info(f"Fetching season data for {anime_data['title']['romaji']}...")
        season_data = anilist_api.get_anime_season_data(anime_data['id'], force_refresh)

    for file_path in tqdm(all_files, desc=f"Processing files in {os.path.basename(folder_path)}"):
        original_filename = os.path.basename(file_path)
        parsed_file = anitopy.parse(original_filename)

        try:
            absolute_episode = int(parsed_file.get('episode_number', '0'))
        except (ValueError, TypeError):
            logging.warning(f"Could not parse episode number for '{original_filename}'. Skipping.")
            continue

        # Use a unique identifier for the show to track processed episodes
        show_id = anime_data['id'] if anime_data else parsed_file.get('anime_title')

        if (show_id, absolute_episode) in processed_episodes:
            continue

        anime_type = parsed_file.get('anime_type')
        if anime_type and (anime_type.lower() == 'ova' or anime_type.lower() == 'special'):
            season = 0
            episode = absolute_episode
        else:
            parsed_season = parsed_file.get('anime_season')
            if parsed_season:
                season = int(parsed_season)
                episode = absolute_episode
            elif season_data:
                season, episode = calculate_season_episode(absolute_episode, season_data)
                if season is None:
                    logging.warning(f"Could not infer season for episode {absolute_episode}. Skipping.")
                    continue
                logging.info(f"Inferred S{season:02d}E{episode:02d} from absolute episode {absolute_episode}.")
            else:
                season, episode = 1, absolute_episode

        if anime_data:
            title = anime_data['title'].get(conf['title_language']) or anime_data['title'].get('romaji') or anime_data['title'].get('english') or anime_data['title'].get('native')
        else:
            title = parsed_file.get('anime_title', 'Unknown Title')

        sanitized_title = sanitize_filename(title)
        new_base_name = conf['rename_template'].format(title=sanitized_title, season=season, episode=episode)

        # Rename video file
        video_file = next((v for v in files['videos'] if os.path.basename(v) == original_filename), None)
        if video_file:
            video_ext = os.path.splitext(video_file)[1]
            language_tag = get_language_tag(original_filename)
            new_video_name = f"{new_base_name}{language_tag}{video_ext}"

            if rclone_remote:
                dest_folder = os.path.join(os.path.dirname(video_file), "S00_OVAs") if bundle_ova and season == 0 else os.path.dirname(video_file)
                unique_video_path = get_unique_rclone_filepath(rclone_remote, os.path.join(dest_folder, new_video_name), rclone_config)
                new_video_path = f"{rclone_remote}:{unique_video_path}"
                original_video_path = f"{rclone_remote}:{video_file}"
            else:
                dest_folder = os.path.join(folder_path, "S00_OVAs") if bundle_ova and season == 0 else folder_path
                if not os.path.exists(dest_folder):
                    os.makedirs(dest_folder)
                new_video_path = get_unique_filepath(os.path.join(dest_folder, new_video_name))
                original_video_path = video_file

            new_video_name = os.path.basename(new_video_path)

            print(f"  - Video: '{original_filename}' -> '{new_video_name}'")
            if not dry_run:
                if rclone_remote:
                    if not rclone_handler.rclone_moveto(original_video_path, new_video_path, rclone_config):
                        if rclone_handler.rclone_copyto(original_video_path, new_video_path, rclone_config):
                            rclone_handler.rclone_delete(original_video_path, rclone_config)
                else:
                    try:
                        os.rename(original_video_path, new_video_path)
                    except OSError as e:
                        logging.error(f"Could not rename video file '{original_video_path}': {e}")

            if export_nfo:
                nfo_path = os.path.splitext(new_video_path)[0] + ".nfo"
                create_nfo_file(nfo_path, anime_data, season, episode, True)

        # Rename subtitle files
        for sub_path in list(files['subtitles']):
            parsed_sub = anitopy.parse(os.path.basename(sub_path))
            try:
                sub_absolute_episode = int(parsed_sub.get('episode_number', '-1'))
                sub_season, sub_episode = calculate_season_episode(sub_absolute_episode, season_data)

                if sub_season == season and sub_episode == episode:
                    sub_ext = os.path.splitext(sub_path)[1]
                    language_tag = get_language_tag(os.path.basename(sub_path))
                    new_sub_name = f"{new_base_name}{language_tag}{sub_ext}"

                    if rclone_remote:
                        dest_folder = os.path.join(os.path.dirname(sub_path), "S00_OVAs") if bundle_ova and season == 0 else os.path.dirname(sub_path)
                        unique_sub_path = get_unique_rclone_filepath(rclone_remote, os.path.join(dest_folder, new_sub_name), rclone_config)
                        new_sub_path = f"{rclone_remote}:{unique_sub_path}"
                        original_sub_path = f"{rclone_remote}:{sub_path}"
                    else:
                        dest_folder = os.path.join(folder_path, "S00_OVAs") if bundle_ova and season == 0 else folder_path
                        if not os.path.exists(dest_folder):
                            os.makedirs(dest_folder)
                        new_sub_path = get_unique_filepath(os.path.join(dest_folder, new_sub_name))
                        original_sub_path = sub_path

                    new_sub_name = os.path.basename(new_sub_path)

                    print(f"  - Subtitle: '{os.path.basename(sub_path)}' -> '{new_sub_name}'")
                    if not dry_run:
                        if rclone_remote:
                            if not rclone_handler.rclone_moveto(original_sub_path, new_sub_path, rclone_config):
                                if rclone_handler.rclone_copyto(original_sub_path, new_sub_path, rclone_config):
                                    rclone_handler.rclone_delete(original_sub_path, rclone_config)
                        else:
                            try:
                                os.rename(original_sub_path, new_sub_path)
                            except OSError as e:
                                logging.error(f"Could not rename subtitle file '{original_sub_path}': {e}")
                    files['subtitles'].remove(sub_path)

                    if export_nfo and not video_file:
                        nfo_path = os.path.splitext(new_sub_path)[0] + ".nfo"
                        create_nfo_file(nfo_path, anime_data, season, episode, False)

            except (ValueError, TypeError):
                continue
        processed_episodes.add((show_id, absolute_episode))

def interactive_menu():
    """
    Display an interactive menu for the user to choose an action.
    """
    print("\nAnime Renamer Menu:")
    print("  1. Process a local directory")
    print("  2. Process an rclone remote")
    print("  3. Process a batch file")
    print("  4. Process all rclone remotes from config")

    while True:
        try:
            choice = int(input("Enter your choice (1-4): "))
            if 1 <= choice <= 4:
                return choice
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            sys.exit(0)

def main():
    conf = config.load_config()
    parser = argparse.ArgumentParser(description="Rename anime files using AniList.co for metadata.")
    parser.add_argument("directory", nargs="?", default=None, help="The directory containing anime files to process.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the renaming changes without applying them.")
    parser.add_argument("--recursive", action="store_true", help="Process subdirectories recursively.")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed logging.")
    parser.add_argument("--force-refresh", action="store_true", help="Force a refresh of the API cache.")
    parser.add_argument("--interactive", action="store_true", help="Pause for user confirmation on all major decisions.")
    parser.add_argument("--batch", help="Process a list of directories from a text file.")
    parser.add_argument("--bundle-ova", action="store_true", help="Move specials and OVAs to a S00_OVAs subfolder.")
    parser.add_argument("--export-nfo", action="store_true", help="Export .nfo files with metadata.")
    parser.add_argument("--rclone-remote", help="The rclone remote to process (e.g., 'gdrive:/Anime').")
    parser.add_argument("--rclone-config", help="Path to the rclone.conf file.")
    args = parser.parse_args()

    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    if len(sys.argv) == 1:
        choice = interactive_menu()
        if choice == 1:
            args.directory = input("Enter the local path to process: ")
        elif choice == 2:
            args.rclone_remote = input("Enter the rclone remote path to process: ")
        elif choice == 3:
            args.batch = input("Enter the path to the batch file: ")
        elif choice == 4:
            remotes = rclone_handler.parse_rclone_conf(args.rclone_config or 'rclone.conf')
            if not remotes:
                print("No remotes found in rclone.conf")
                sys.exit(1)
            print("Available remotes:")
            for i, remote in enumerate(remotes, 1):
                print(f"  {i}: {remote}")
            try:
                choice = int(input(f"Enter your choice (1-{len(remotes)}): "))
                args.rclone_remote = remotes[choice - 1]
            except (ValueError, IndexError):
                print("Invalid choice.")
                sys.exit(1)

    directories = []
    if args.batch:
        try:
            with open(args.batch, 'r', encoding='utf-8') as f:
                directories = [line.strip() for line in f if line.strip()]
        except IOError as e:
            print(f"Error reading batch file: {e}")
            sys.exit(1)
    elif args.directory:
        directories.append(args.directory)
    elif args.rclone_remote:
        directories.append(args.rclone_remote)

    for directory in directories:
        if args.rclone_remote:
            logging.info(f"Processing rclone remote: {directory}")
            file_groups = find_files(directory, args.recursive, rclone_remote=args.rclone_remote, rclone_config=args.rclone_config)
        else:
            if not os.path.isdir(directory):
                print(f"Error: The specified path '{directory}' is not a valid directory."); continue
            logging.info(f"Starting anime renamer on directory: {directory}")
            file_groups = find_files(directory, args.recursive)

        if not file_groups:
            print("No video or subtitle files found to process."); continue

        for folder, files in file_groups.items():
            logging.info(f"\nProcessing folder: {folder}")

            sample_filename = os.path.basename(files['videos'][0] if files['videos'] else files['subtitles'][0])
            parsed_title = anitopy.parse(sample_filename).get('anime_title')

            if not parsed_title:
                logging.warning(f"Could not parse a title from '{sample_filename}'. Skipping folder."); continue

            logging.info(f"Searching AniList for '{parsed_title}'...")
            search_results = anilist_api.search_anime(parsed_title, args.force_refresh)

            selected_anime = None
            if not search_results:
                print(f"No results found for '{parsed_title}'. Proceeding with parsed filename.")
            elif len(search_results) == 1:
                selected_anime = search_results[0]
                title = selected_anime['title'].get(conf['title_language']) or selected_anime['title'].get('romaji') or selected_anime['title'].get('english') or selected_anime['title'].get('native')
                print(f"Automatically matched with the only AniList result: {title}")
            else:
                titles = { (anime['title'].get('romaji') or anime['title'].get('english') or anime['title'].get('native')): anime for anime in search_results }
                best_match = process.extractOne(parsed_title, titles.keys())
                if best_match and best_match[1] >= conf['fuzzy_threshold']:
                    selected_anime = titles[best_match[0]]
                    title = selected_anime['title'].get(conf['title_language']) or selected_anime['title'].get('romaji') or selected_anime['title'].get('english') or selected_anime['title'].get('native')
                    print(f"Automatically matched with AniList title (score: {best_match[1]}): {title}")
                else:
                    logging.info(f"Fuzzy match score was too low ({best_match[1] if best_match else 'N/A'}). Asking for user input.")
                    selected_anime = choose_anime(search_results)

            if selected_anime:
                title = selected_anime['title'].get(conf['title_language']) or selected_anime['title'].get('romaji') or selected_anime['title'].get('english') or selected_anime['title'].get('native')
                print(f"Processing with selected AniList title: {title}")

            if args.interactive and selected_anime:
                try:
                    choice = input("Proceed with this match? (y/n): ").lower()
                    if choice != 'y':
                        print("Skipping folder.")
                        continue
                except KeyboardInterrupt:
                    print("\nOperation cancelled by user.")
                    sys.exit(0)

            process_folder(folder, files, selected_anime, conf, args.dry_run, args.force_refresh, args.interactive, args.bundle_ova, args.export_nfo, args.verbose, rclone_remote=args.rclone_remote, rclone_config=args.rclone_config)

    print("\nRenaming process complete.")

if __name__ == "__main__":
    main()
