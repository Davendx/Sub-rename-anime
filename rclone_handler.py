#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import json
import logging
import os
import re

def parse_rclone_conf(conf_path):
    """
    Parse the rclone.conf file to get a list of available remotes.
    """
    remotes = []
    if not os.path.exists(conf_path):
        return remotes

    try:
        with open(conf_path, 'r', encoding='utf-8') as f:
            content = f.read()
            remotes = re.findall(r'\[(.*?)\]', content)
    except IOError as e:
        logging.error(f"Could not read rclone.conf file: {e}")

    return remotes

def rclone_lsjson(remote_path, rclone_config=None):
    """
    List files on an rclone remote using lsjson.
    """
    cmd = ['rclone', 'lsjson', remote_path]
    if rclone_config:
        cmd.extend(['--config', rclone_config])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logging.error(f"Failed to list files on rclone remote '{remote_path}': {e}")
        return None

def rclone_moveto(source_path, dest_path, rclone_config=None):
    """
    Move a file on an rclone remote using moveto.
    """
    cmd = ['rclone', 'moveto', source_path, dest_path]
    if rclone_config:
        cmd.extend(['--config', rclone_config])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to move file from '{source_path}' to '{dest_path}': {e}")
        return False

def rclone_copyto(source_path, dest_path, rclone_config=None):
    """
    Copy a file to an rclone remote using copyto.
    """
    cmd = ['rclone', 'copyto', source_path, dest_path]
    if rclone_config:
        cmd.extend(['--config', rclone_config])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to copy file from '{source_path}' to '{dest_path}': {e}")
        return False

def rclone_delete(remote_path, rclone_config=None):
    """
    Delete a file on an rclone remote.
    """
    cmd = ['rclone', 'delete', remote_path]
    if rclone_config:
        cmd.extend(['--config', rclone_config])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to delete file '{remote_path}': {e}")
        return False
