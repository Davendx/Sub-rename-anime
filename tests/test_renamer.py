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
