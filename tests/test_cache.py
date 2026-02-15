#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json
import os
import time
from unittest.mock import patch, mock_open, MagicMock
import cache

def test_get_cache_key():
    """
    Test the get_cache_key function.
    """
    prefix = "test"
    query = "search query"
    key = cache.get_cache_key(prefix, query)

    assert key.startswith(prefix + "_")
    assert key.endswith(".json")
    assert len(key) == len(prefix) + 1 + 32 + 5 # prefix + _ + md5 + .json

@patch('os.path.exists')
def test_get_cached_data_no_cache_dir(mock_exists):
    """
    Test get_cached_data when the cache directory does not exist.
    """
    mock_exists.return_value = False
    assert cache.get_cached_data("some_key") is None

@patch('os.path.exists')
def test_get_cached_data_no_cache_file(mock_exists):
    """
    Test get_cached_data when the cache file does not exist.
    """
    # First call for CACHE_DIR exists, second for cache_file exists
    mock_exists.side_effect = [True, False]
    assert cache.get_cached_data("some_key") is None

@patch('os.path.exists')
@patch('builtins.open', new_callable=mock_open, read_data='{"timestamp": 1000, "payload": "data"}')
@patch('time.time')
@patch('cache.logging')
def test_get_cached_data_expired(mock_logging, mock_time, mock_file, mock_exists):
    """
    Test get_cached_data when the cache file is expired.
    """
    mock_exists.return_value = True
    mock_time.return_value = 1000 + cache.CACHE_DURATION + 1

    assert cache.get_cached_data("some_key") is None
    mock_logging.info.assert_any_call("Cache expired for key: some_key")
    mock_logging.info.assert_any_call("Cache miss for key: some_key")

@patch('os.path.exists')
@patch('builtins.open', new_callable=mock_open, read_data='{"timestamp": 1000, "payload": "data"}')
@patch('time.time')
@patch('cache.logging')
def test_get_cached_data_valid(mock_logging, mock_time, mock_file, mock_exists):
    """
    Test get_cached_data when the cache file is valid.
    """
    mock_exists.return_value = True
    mock_time.return_value = 1000 + cache.CACHE_DURATION - 1

    assert cache.get_cached_data("some_key") == "data"
    mock_logging.info.assert_called_with("Cache hit for key: some_key")

@patch('os.path.exists')
@patch('builtins.open', new_callable=mock_open, read_data='invalid json')
@patch('cache.logging')
def test_get_cached_data_invalid_json(mock_logging, mock_file, mock_exists):
    """
    Test get_cached_data when the cache file contains invalid JSON.
    """
    mock_exists.return_value = True
    assert cache.get_cached_data("some_key") is None
    mock_logging.warning.assert_called()
    mock_logging.info.assert_called_with("Cache miss for key: some_key")

@patch('os.path.exists')
@patch('os.makedirs')
@patch('builtins.open', new_callable=mock_open)
@patch('json.dump')
@patch('time.time')
@patch('cache.logging')
def test_save_to_cache_success(mock_logging, mock_time, mock_json_dump, mock_file, mock_makedirs, mock_exists):
    """
    Test save_to_cache success scenario.
    """
    mock_exists.return_value = False # CACHE_DIR doesn't exist
    mock_time.return_value = 1000
    payload = {"result": "success"}
    key = "test_key"

    cache.save_to_cache(key, payload)

    mock_makedirs.assert_called_once_with(cache.CACHE_DIR)
    mock_file.assert_called_once_with(os.path.join(cache.CACHE_DIR, key), 'w', encoding='utf-8')
    # When using mock_open, the handle passed to json.dump is mock_file()
    mock_json_dump.assert_called_once_with({'timestamp': 1000, 'payload': payload}, mock_file())
    mock_logging.info.assert_called_with(f"Saved to cache with key: {key}")

@patch('os.path.exists')
@patch('os.makedirs')
@patch('builtins.open', side_effect=IOError("Write error"))
@patch('cache.logging')
def test_save_to_cache_io_error(mock_logging, mock_file, mock_makedirs, mock_exists):
    """
    Test save_to_cache when an IOError occurs.
    """
    mock_exists.return_value = True # CACHE_DIR exists

    # This should not raise an exception but log an error
    cache.save_to_cache("test_key", {"data": "test"})

    mock_makedirs.assert_not_called()
    mock_file.assert_called_once()
    mock_logging.error.assert_called()
