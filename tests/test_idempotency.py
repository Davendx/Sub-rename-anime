import pytest
from unittest.mock import MagicMock, patch
import os
import anime_renamer

@patch('anime_renamer.anilist_api.get_anime_season_data')
@patch('anime_renamer.os.path.abspath')
@patch('anime_renamer.os.path.exists')
@patch('anime_renamer.get_unique_filepath')
@patch('anime_renamer.os.rename')
def test_idempotency_local(mock_rename, mock_unique, mock_exists, mock_abspath, mock_get_season):
    # Setup mocks
    mock_get_season.return_value = [] # No season data needed for this test
    mock_abspath.side_effect = lambda x: x # Mock abspath as identity for simplicity
    mock_exists.return_value = True # Destination exists
    mock_unique.side_effect = lambda x: x + "_v2" # Mock unique to generate v2

    files = {'videos': ['/path/to/Show - S01E01.mkv'], 'subtitles': []}
    anime_data = {'id': 1, 'title': {'romaji': 'Show', 'english': 'Show'}}
    conf = {'rename_template': '{title} - S{season:02d}E{episode:02d}', 'title_language': 'romaji'}

    # Run process_folder
    # We expect NO rename call because source == destination candidate

    # Mock anitopy to return correct parsed data so it matches template
    with patch('anime_renamer.anitopy.parse') as mock_parse:
        mock_parse.return_value = {'anime_title': 'Show', 'episode_number': '01', 'anime_season': '01'}

        anime_renamer.process_folder('/path/to', files, anime_data, conf, False, False, False, False, False, False)

        mock_rename.assert_not_called()
        mock_unique.assert_not_called()

@patch('anime_renamer.os.makedirs')
@patch('anime_renamer.anilist_api.get_anime_season_data')
@patch('anime_renamer.os.path.abspath')
@patch('anime_renamer.os.path.exists')
@patch('anime_renamer.get_unique_filepath')
@patch('anime_renamer.os.rename')
def test_rename_needed(mock_rename, mock_unique, mock_exists, mock_abspath, mock_get_season, mock_makedirs):
    # Setup mocks
    mock_get_season.return_value = []
    mock_abspath.side_effect = lambda x: x
    mock_exists.return_value = False # Destination does not exist
    mock_unique.side_effect = lambda x: x

    files = {'videos': ['/path/to/Original.mkv'], 'subtitles': []}
    anime_data = {'id': 1, 'title': {'romaji': 'Show', 'english': 'Show'}}
    conf = {'rename_template': '{title} - S{season:02d}E{episode:02d}', 'title_language': 'romaji'}

    with patch('anime_renamer.anitopy.parse') as mock_parse:
        mock_parse.return_value = {'anime_title': 'Show', 'episode_number': '01', 'anime_season': '01'}

        anime_renamer.process_folder('/path/to', files, anime_data, conf, False, False, False, False, False, False)

        mock_rename.assert_called()

@pytest.mark.parametrize("bad_parse_result", [
    {'anime_title': 'Show'}, # No episode_number
    {'anime_title': 'Show', 'episode_number': None},
    {'anime_title': 'Show', 'episode_number': ''},
])
def test_process_folder_skips_bad_parse(bad_parse_result):
    from unittest.mock import patch, MagicMock

    files = {'videos': ['/path/to/Show.mkv'], 'subtitles': []}
    anime_data = {'id': 1, 'title': {'romaji': 'Show', 'english': 'Show'}}
    conf = {'rename_template': '{title} - S{season:02d}E{episode:02d}', 'title_language': 'romaji'}

    with patch('anime_renamer.anitopy.parse') as mock_parse,          patch('anime_renamer.anilist_api.get_anime_season_data') as mock_season,          patch('anime_renamer.logging.warning') as mock_log:

        mock_parse.return_value = bad_parse_result
        mock_season.return_value = []

        anime_renamer.process_folder('/path/to', files, anime_data, conf, False, False, False, False, False, False)

        mock_log.assert_called()
