import pytest
import anime_renamer
import anitopy

def test_clean_filename():
    """
    Test the clean_filename function fixes specific problematic patterns.
    """
    # Fix S01-E13
    assert anime_renamer.clean_filename("Show S01-E13.ass") == "Show S01E13.ass"
    assert anime_renamer.clean_filename("Show s01-e13.ass") == "Show s01e13.ass"

    # Should not touch normal files
    assert anime_renamer.clean_filename("Show - 01.mkv") == "Show - 01.mkv"
    assert anime_renamer.clean_filename("Show S01E01.mkv") == "Show S01E01.mkv"

def test_parsing_after_clean():
    """
    Test that cleaning actually helps anitopy parse the episode.
    """
    bad_filename = "[AnimWorld] Tougen Anki S01-E13 ヒューゴ.ass"
    cleaned = anime_renamer.clean_filename(bad_filename)
    parsed = anitopy.parse(cleaned)
    assert parsed.get('episode_number') == '13'
    # Depending on anitopy version/env, anime_season might be parsed or not, but episode is key.

def test_parsing_webrip_tag():
    """
    Test parsing of the complex WebRip filename provided by user.
    """
    filename = "[LoliHouse] TOUGEN ANKI - 01 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv"
    cleaned = anime_renamer.clean_filename(filename)
    parsed = anitopy.parse(cleaned)
    assert parsed.get('episode_number') == '01'
