#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import logging
import cache

API_URL = 'https://graphql.anilist.co'
RATE_LIMIT_DELAY = 0.7  # ~85 requests per minute, safely under the 90 limit

def search_anime(title, force_refresh=False):
    """
    Search for an anime by title on AniList, with caching.
    """
    cache_key = cache.get_cache_key('search', title)
    if not force_refresh:
        cached_data = cache.get_cached_data(cache_key)
        if cached_data:
            return cached_data

    query = '''
    query ($search: String) {
        Page(page: 1, perPage: 10) {
            media(search: $search, type: ANIME, sort: POPULARITY_DESC) {
                id
                title {
                    romaji
                    english
                    native
                }
                format
                episodes
                synonyms
            }
        }
    }
    '''
    variables = {'search': title}

    try:
        response = requests.post(API_URL, json={'query': query, 'variables': variables})
        response.raise_for_status()
        data = response.json()['data']['Page']['media']
        cache.save_to_cache(cache_key, data)
        time.sleep(RATE_LIMIT_DELAY)
        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred while communicating with the AniList API: {e}")
        return None
    except (KeyError, TypeError):
        logging.error("Unexpected response format from AniList API during search.")
        return None

def get_anime_season_data(anime_id, force_refresh=False, fetched_ids=None):
    """
    Recursively fetch the seasonal data for an anime, with caching.
    """
    cache_key = cache.get_cache_key('season', str(anime_id))
    if not force_refresh:
        cached_data = cache.get_cached_data(cache_key)
        if cached_data:
            return cached_data

    if fetched_ids is None:
        fetched_ids = set()

    if anime_id in fetched_ids:
        return []

    query = '''
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title {
          romaji
          english
        }
        episodes
        relations {
          edges {
            relationType(version: 2)
            node {
              id
              format
              episodes
              title {
                romaji
                english
              }
            }
          }
        }
      }
    }
    '''

    variables = {'id': anime_id}
    try:
        response = requests.post(API_URL, json={'query': query, 'variables': variables})
        response.raise_for_status()
        data = response.json()['data']['Media']
        fetched_ids.add(anime_id)
        time.sleep(RATE_LIMIT_DELAY)

        seasons = [{'id': data['id'], 'title': data['title']['romaji'] or data['title']['english'], 'episodes': data['episodes'], 'relations': data['relations']}]

        for edge in data['relations']['edges']:
            relation_type = edge['relationType']
            node = edge['node']

            if relation_type in ['SEQUEL', 'PREQUEL'] and node['format'] in ['TV', 'OVA', 'ONA']:
                seasons.extend(get_anime_season_data(node['id'], force_refresh, fetched_ids))

        cache.save_to_cache(cache_key, seasons)
        return seasons

    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred while fetching season data: {e}")
        return []
    except (KeyError, TypeError):
        logging.error("Unexpected response format from AniList API during season data fetch.")
        return []
