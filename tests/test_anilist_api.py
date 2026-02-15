#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from unittest.mock import patch, MagicMock

# Mock requests and its exceptions before importing anilist_api
mock_requests = MagicMock()
mock_requests.exceptions.RequestException = Exception
sys.modules["requests"] = mock_requests

# Mock cache to avoid side effects and dependency issues
mock_cache = MagicMock()
sys.modules["cache"] = mock_cache

import anilist_api
import pytest

def test_search_anime_timeout():
    """
    Test that search_anime calls requests.post with a timeout.
    """
    mock_post = mock_requests.post
    mock_post.return_value.json.return_value = {'data': {'Page': {'media': []}}}
    mock_post.return_value.status_code = 200

    # Ensure cache miss
    mock_cache.get_cached_data.return_value = None

    anilist_api.search_anime("Test Anime")

    # Check if timeout was passed to requests.post
    args, kwargs = mock_post.call_args
    assert 'timeout' in kwargs, "requests.post was called without a timeout in search_anime"
    assert isinstance(kwargs['timeout'], (int, float)), "timeout should be a number"

def test_get_anime_season_data_timeout():
    """
    Test that get_anime_season_data calls requests.post with a timeout.
    """
    # Reset mock to clear previous calls
    mock_requests.post.reset_mock()
    mock_post = mock_requests.post
    mock_post.return_value.json.return_value = {
        'data': {
            'Media': {
                'id': 1,
                'title': {'romaji': 'Test Anime', 'english': 'Test Anime'},
                'episodes': 12,
                'relations': {'edges': []}
            }
        }
    }
    mock_post.return_value.status_code = 200

    # Ensure cache miss
    mock_cache.get_cached_data.return_value = None

    anilist_api.get_anime_season_data(1)

    # Check if timeout was passed to requests.post
    assert mock_post.called, "requests.post was not called in get_anime_season_data"
    args, kwargs = mock_post.call_args
    assert 'timeout' in kwargs, "requests.post was called without a timeout in get_anime_season_data"
    assert isinstance(kwargs['timeout'], (int, float)), "timeout should be a number"
