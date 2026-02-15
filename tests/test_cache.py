#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import sys
from unittest.mock import MagicMock, patch

# Mock yaml to allow importing config without it being installed
sys.modules['yaml'] = MagicMock()

import cache
import config

def test_get_cache_dir_defaults():
    """Test that get_cache_dir returns the default if not in config."""
    with patch('config.load_config') as mock_load:
        mock_load.return_value = config.DEFAULT_CONFIG
        assert cache.get_cache_dir() == '.anime_renamer_cache'

def test_get_cache_dir_custom():
    """Test that get_cache_dir returns the custom value from config."""
    with patch('config.load_config') as mock_load:
        mock_load.return_value = {'cache_dir': '.custom_cache'}
        assert cache.get_cache_dir() == '.custom_cache'

def test_get_cache_duration():
    """Test that get_cache_duration converts hours to seconds."""
    with patch('config.load_config') as mock_load:
        mock_load.return_value = {'anilist_cache': {'duration': 2}}
        assert cache.get_cache_duration() == 7200

def test_cache_functionality():
    """Test save and retrieve functionality with a custom directory."""
    test_dir = '.temp_test_cache'
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    with patch('cache.get_cache_dir', return_value=test_dir):
        with patch('cache.get_cache_duration', return_value=3600):
            key = cache.get_cache_key('test', 'query')
            payload = {'hello': 'world'}

            # Test miss
            assert cache.get_cached_data(key) is None

            # Test save
            cache.save_to_cache(key, payload)
            assert os.path.exists(test_dir)

            # Test hit
            assert cache.get_cached_data(key) == payload

    # Clean up
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
