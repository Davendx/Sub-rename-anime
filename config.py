#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import os
import logging

DEFAULT_CONFIG = {
    'title_language': 'romaji',
    'rename_template': '{title} - S{season:02d}E{episode:02d} - Episode {episode:02d}',
    'fuzzy_threshold': 85,
    'anilist_cache': {
        'enabled': True,
        'duration': 24
    }
}

def load_config():
    """
    Load the config.yaml file.
    """
    config_path = 'config.yaml'
    if not os.path.exists(config_path):
        logging.info("No config.yaml found, using default settings.")
        return DEFAULT_CONFIG

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            # Merge with defaults to ensure all keys are present
            return {**DEFAULT_CONFIG, **config}
    except (yaml.YAMLError, IOError) as e:
        logging.error(f"Could not load or parse config.yaml: {e}")
        return DEFAULT_CONFIG
