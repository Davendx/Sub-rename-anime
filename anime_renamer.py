#!/usr/-bin/env python3
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
import anilist_api

# Supported file extensions
VIDEO_EXTENSIONS = ('.mkv', '.mp4')
SUBTITLE_EXTENSIONS = ('.srt', '.ass')

def sanitize_filename(filename):
    """
    Remove characters that are invalid in filenames across different OS.
    """
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def find_files(directory, recursive):
    """
    Find video and subtitle files in the given directory and group them by folder.
    """
    file_groups = defaultdict(lambda: {'videos': [], 'subtitles': []})

    if recursive:
        for root, _, files in os.walk(directory):
            for file in files:
                item_path = os.path.join(root, file)
                if file.lower().endswith(VIDEO_EXTENSIONS):
                    file_groups[root]['videos'].append(item_path)
                elif file.lower().endswith(SUBTITLE_EXTENSIONS):
                    file_groups[root]['subtitles'].append(item_path)
    else:
        # In non-recursive mode, only scan the top-level directory.
        # Group all files under this single directory.
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                if item.lower().endswith(VIDEO_EXTENSIONS):
                    file_groups[directory]['videos'].append(item_path)
                elif item.lower().endswith(SUBTITLE_EXTENSIONS):
                    file_groups[directory]['subtitles'].append(item_path)

    return {folder: files for folder, files in file_groups.items() if files['videos']}

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

    return 1, absolute_episode


def process_folder(folder_path, files, anime_data, dry_run, verbose):
    """
    Process and rename all video and subtitle files in a single folder.
    """
    video_files = sorted(files['videos'])
    subtitle_files = files['subtitles']

    season_data = []
    if anime_data:
        logging.info(f"Fetching season data for {anime_data['title']['romaji']}...")
        season_data = anilist_api.get_anime_season_data(anime_data['id'])

    for video_path in video_files:
        original_filename = os.path.basename(video_path)
        parsed_video = anitopy.parse(original_filename)

        try:
            absolute_episode = int(parsed_video.get('episode_number', '0'))
        except (ValueError, TypeError):
            logging.warning(f"Could not parse episode number for '{original_filename}'. Skipping.")
            continue

        parsed_season = parsed_video.get('anime_season')
        if parsed_season:
            season = int(parsed_season)
            episode = absolute_episode
        elif season_data:
            season, episode = calculate_season_episode(absolute_episode, season_data)
            logging.info(f"Inferred S{season:02d}E{episode:02d} from absolute episode {absolute_episode}.")
        else:
            season, episode = 1, absolute_episode

        if anime_data:
            title = anime_data['title'].get('romaji') or anime_data['title'].get('english')
        else:
            title = parsed_video.get('anime_title', 'Unknown Title')

        sanitized_title = sanitize_filename(title)
        new_base_name = f"{sanitized_title} - S{season:02d}E{episode:02d}"

        video_ext = os.path.splitext(video_path)[1]
        new_video_name = f"{new_base_name}{video_ext}"
        new_video_path = os.path.join(folder_path, new_video_name)

        print(f"  - Video: '{original_filename}' -> '{new_video_name}'")
        if not dry_run:
            try:
                os.rename(video_path, new_video_path)
            except OSError as e:
                logging.error(f"Could not rename video file '{video_path}': {e}")

        for sub_path in list(subtitle_files): # Iterate over a copy
            parsed_sub = anitopy.parse(os.path.basename(sub_path))
            try:
                sub_absolute_episode = int(parsed_sub.get('episode_number', '-1'))
                if sub_absolute_episode == absolute_episode:
                    sub_ext = os.path.splitext(sub_path)[1]
                    new_sub_name = f"{new_base_name}{sub_ext}"
                    new_sub_path = os.path.join(folder_path, new_sub_name)
                    print(f"  - Subtitle: '{os.path.basename(sub_path)}' -> '{new_sub_name}'")
                    if not dry_run:
                        try:
                            os.rename(sub_path, new_sub_path)
                        except OSError as e:
                            logging.error(f"Could not rename subtitle file '{sub_path}': {e}")
                    subtitle_files.remove(sub_path)
            except (ValueError, TypeError):
                continue

def main():
    parser = argparse.ArgumentParser(description="Rename anime files using AniList.co for metadata.")
    parser.add_argument("directory", nargs="?", default=None, help="The directory containing anime files to process.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the renaming changes without applying them.")
    parser.add_argument("--recursive", action="store_true", help="Process subdirectories recursively.")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed logging.")
    args = parser.parse_args()

    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    target_directory = args.directory
    if not target_directory:
        try:
            target_directory = input("Please enter the path to the directory to process: ")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user."); sys.exit(0)

    if not os.path.isdir(target_directory):
        print(f"Error: The specified path '{target_directory}' is not a valid directory."); sys.exit(1)

    logging.info(f"Starting anime renamer on directory: {target_directory}")
    logging.info(f"Dry run: {'Yes' if args.dry_run else 'No'}")
    logging.info(f"Recursive: {'Yes' if args.recursive else 'No'}")

    file_groups = find_files(target_directory, args.recursive)
    if not file_groups:
        print("No video files found to process in the specified directory."); return

    for folder, files in file_groups.items():
        logging.info(f"\nProcessing folder: {folder}")

        sample_filename = os.path.basename(files['videos'][0])
        parsed_title = anitopy.parse(sample_filename).get('anime_title')

        if not parsed_title:
            logging.warning(f"Could not parse a title from '{sample_filename}'. Skipping folder."); continue

        logging.info(f"Searching AniList for '{parsed_title}'...")
        search_results = anilist_api.search_anime(parsed_title)

        selected_anime = None
        if not search_results:
            print(f"No results found for '{parsed_title}'. Proceeding with parsed filename.")
        elif len(search_results) == 1:
            selected_anime = search_results[0]
            title = selected_anime['title'].get('romaji') or selected_anime['title'].get('english')
            print(f"Automatically matched with the only AniList result: {title}")
        else:
            titles = { (anime['title'].get('romaji') or anime['title'].get('english')): anime for anime in search_results }
            best_match = process.extractOne(parsed_title, titles.keys())
            MATCH_THRESHOLD = 85
            if best_match and best_match[1] >= MATCH_THRESHOLD:
                selected_anime = titles[best_match[0]]
                title = selected_anime['title'].get('romaji') or selected_anime['title'].get('english')
                print(f"Automatically matched with AniList title (score: {best_match[1]}): {title}")
            else:
                logging.info(f"Fuzzy match score was too low ({best_match[1] if best_match else 'N/A'}). Asking for user input.")
                selected_anime = choose_anime(search_results)

        if selected_anime:
            title = selected_anime['title'].get('romaji') or selected_anime['title'].get('english')
            print(f"Processing with selected AniList title: {title}")

        process_folder(folder, files, selected_anime, args.dry_run, args.verbose)

    print("\nRenaming process complete.")

if __name__ == "__main__":
    main()
