#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import logging

CACHE_DIR = '.anime_renamer_cache'
CACHE_DURATION = 24 * 60 * 60  # 24 hours

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
    if not os.path.exists(CACHE_DIR):
        return None

    cache_file = os.path.join(CACHE_DIR, key)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if time.time() - data.get('timestamp', 0) < CACHE_DURATION:
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
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    cache_file = os.path.join(CACHE_DIR, key)
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
