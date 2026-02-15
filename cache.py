#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import logging
import config

def get_cache_dir():
    """
    Get the cache directory from the configuration.
    """
    return config.load_config().get('cache_dir', '.anime_renamer_cache')

def get_cache_duration():
    """
    Get the cache duration (in seconds) from the configuration.
    """
    conf = config.load_config()
    return conf.get('anilist_cache', {}).get('duration', 24) * 60 * 60

def get_cache_key(prefix, query):
    """
    Generate a unique cache key for a given query.
    """
    query_bytes = query.encode('utf-8')
    return f"{prefix}_{hashlib.md5(query_bytes).hexdigest()}.json"

def get_cached_data(key):
    """
    Retrieve data from the cache if it exists and is not expired.
    """
    cache_dir = get_cache_dir()
    cache_duration = get_cache_duration()

    if not os.path.exists(cache_dir):
        return None

    cache_file = os.path.join(cache_dir, key)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if time.time() - data.get('timestamp', 0) < cache_duration:
                    logging.info(f"Cache hit for key: {key}")
                    return data['payload']
                else:
                    logging.info(f"Cache expired for key: {key}")
        except (json.JSONDecodeError, KeyError) as e:
            logging.warning(f"Could not read cache file '{cache_file}': {e}")

    logging.info(f"Cache miss for key: {key}")
    return None

def save_to_cache(key, payload):
    """
    Save data to the cache.
    """
    cache_dir = get_cache_dir()

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    cache_file = os.path.join(cache_dir, key)
    data = {
        'timestamp': time.time(),
        'payload': payload
    }
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        logging.info(f"Saved to cache with key: {key}")
    except IOError as e:
        logging.error(f"Could not write to cache file '{cache_file}': {e}")
