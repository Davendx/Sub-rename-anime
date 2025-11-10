#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from unittest.mock import patch, MagicMock
import anime_renamer

@pytest.fixture
def mock_anitopy(monkeypatch):
    """
    Fixture to mock the anitopy library.
    """
    mock = MagicMock()
    monkeypatch.setattr(anime_renamer, 'anitopy', mock)
    return mock

def test_sanitize_filename():
    """
    Test the sanitize_filename function.
    """
    assert anime_renamer.sanitize_filename('A<B>C:D"E/F\\G|H?I*J') == 'ABCDEFGHIJ'

def test_get_language_tag():
    """
    Test the get_language_tag function.
    """
    assert anime_renamer.get_language_tag('My Anime - 01 [eng].mkv') == ' [eng]'
    assert anime_renamer.get_language_tag('My Anime - 01 [jpn].mkv') == ' [jpn]'
    assert anime_renamer.get_language_tag('My Anime - 01.mkv') == ''

@patch('os.path.exists')
def test_get_unique_filepath(mock_exists):
    """
    Test the get_unique_filepath function.
    """
    mock_exists.side_effect = [True, True, False]
    filepath = 'test.txt'
    unique_filepath = anime_renamer.get_unique_filepath(filepath)
    assert unique_filepath == 'test_v3.txt'

@patch('xml.etree.ElementTree.ElementTree')
def test_create_nfo_file(mock_ElementTree):
    """
    Test the create_nfo_file function.
    """
    mock_tree_instance = mock_ElementTree.return_value

    anime_data = {
        'title': {'romaji': 'My Anime', 'english': 'My Anime'},
        'description': 'An anime about testing.'
    }
    # Test for video file NFO
    anime_renamer.create_nfo_file('test.nfo', anime_data, 1, 1, True)

    mock_ElementTree.assert_called_once()
    args, _ = mock_ElementTree.call_args
    root = args[0]

    assert root.tag == 'episodedetails'
    assert root.find('title').text == 'Episode 01'
    assert root.find('season').text == '1'
    assert root.find('episode').text == '1'
    assert root.find('showtitle').text == 'My Anime'
    assert root.find('plot').text == 'An anime about testing.'
    assert root.find('fileinfo') is None
    mock_tree_instance.write.assert_called_with('test.nfo', encoding='utf-8', xml_declaration=True)

    # Test for subtitle-only NFO
    mock_ElementTree.reset_mock()
    anime_renamer.create_nfo_file('sub_only.nfo', anime_data, 1, 2, False)

    mock_ElementTree.assert_called_once()
    args, _ = mock_ElementTree.call_args
    root = args[0]

    assert root.find('fileinfo') is not None
    assert root.find('fileinfo/streamdetails/video/codec').text == 'unknown'
    mock_tree_instance.write.assert_called_with('sub_only.nfo', encoding='utf-8', xml_declaration=True)

def test_calculate_season_episode():
    """
    Test the calculate_season_episode function.
    """
    season_data = [
        {'id': 1, 'episodes': 12},
        {'id': 2, 'episodes': 12},
    ]
    assert anime_renamer.calculate_season_episode(1, season_data) == (1, 1)
    assert anime_renamer.calculate_season_episode(12, season_data) == (1, 12)
    assert anime_renamer.calculate_season_episode(13, season_data) == (2, 1)
    assert anime_renamer.calculate_season_episode(24, season_data) == (2, 12)
    assert anime_renamer.calculate_season_episode(25, season_data) == (None, None) # Fallback

@patch('anime_renamer.rclone_handler')
def test_find_files_rclone(mock_rclone_handler):
    """
    Test the find_files function with an rclone remote.
    """
    mock_rclone_handler.rclone_lsjson.return_value = [
        {'Path': 'My Anime/S01/My Anime - 01.mkv', 'IsDir': False},
        {'Path': 'My Anime/S01/My Anime - 01.ass', 'IsDir': False},
        {'Path': 'My Anime/S01/another_file.txt', 'IsDir': False},
    ]

    file_groups = anime_renamer.find_files('gdrive:/Anime', recursive=True, rclone_remote='gdrive:/Anime', rclone_config='rclone.conf')

    expected_groups = {
        'My Anime/S01': {
            'videos': ['My Anime/S01/My Anime - 01.mkv'],
            'subtitles': ['My Anime/S01/My Anime - 01.ass']
        }
    }

    assert file_groups == expected_groups
    mock_rclone_handler.rclone_lsjson.assert_called_once_with('gdrive:/Anime', 'rclone.conf')

@patch('builtins.input', side_effect=['1', '/path/to/anime'])
@patch('anime_renamer.find_files')
@patch('os.path.isdir', return_value=True)
def test_interactive_menu_local(mock_isdir, mock_find_files, mock_input):
    """
    Test the interactive_menu function for local path processing.
    """
    with patch('sys.argv', ['anime_renamer.py']):
        anime_renamer.main()
    mock_find_files.assert_called_with('/path/to/anime', False)

@patch('anime_renamer.anilist_api.search_anime')
@patch('anime_renamer.find_files')
@patch('anime_renamer.process_folder')
@patch('os.path.isdir', return_value=True)
def test_mixed_title_matching(mock_isdir, mock_process_folder, mock_find_files, mock_search_anime):
    """
    Test that the script correctly matches an anime when files in a folder use different title variations.
    """
    mock_find_files.return_value = {
        'test_folder': {
            'videos': ['[SubsPlease] Lord Marksman and Vanadis - 01 (1080p) [F1488102].mkv'],
            'subtitles': ['[SomeGroup] Madan no Ou to Vanadis - 01 [v2].ass']
        }
    }

    mock_search_anime.side_effect = [
        # Results for "Lord Marksman and Vanadis"
        [{
            'id': 1,
            'title': {
                'romaji': 'Madan no Ou to Vanadis',
                'english': 'Lord Marksman and Vanadis',
                'native': '魔弾の王と戦姫'
            },
            'synonyms': []
        }],
        # Results for "Madan no Ou to Vanadis"
        [{
            'id': 1,
            'title': {
                'romaji': 'Madan no Ou to Vanadis',
                'english': 'Lord Marksman and Vanadis',
                'native': '魔弾の王と戦姫'
            },
            'synonyms': []
        }]
    ]

    with patch('sys.argv', ['anime_renamer.py', 'test_folder']):
        anime_renamer.main()

    # Verify that process_folder was called with the correct anime data
    mock_process_folder.assert_called_once()
    args, _ = mock_process_folder.call_args
    selected_anime = args[2] # The anime_data argument
    assert selected_anime['id'] == 1
    assert selected_anime['title']['romaji'] == 'Madan no Ou to Vanadis'
