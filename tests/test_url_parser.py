import pytest

from crawler import url_parser
from crawler.url_parser import parse_package_id, parse_url


def test_parse_url_extracts_package_and_country():
    pkg, country = parse_url(
        "https://play.google.com/store/apps/details?id=com.roblox.client&gl=vn"
    )
    assert (pkg, country) == ("com.roblox.client", "vn")


def test_plain_package_id_passthrough():
    assert parse_package_id("com.roblox.client") == "com.roblox.client"


def _mock_search(monkeypatch, results):
    monkeypatch.setattr(url_parser, "search", lambda *a, **k: results)


def test_normalized_match_beats_earlier_clone(monkeypatch):
    # Real app ranks below a clone but matches the query once normalized
    _mock_search(monkeypatch, [
        {"title": "Block Blast VN", "appId": "com.blockblast.vn"},
        {"title": "Block Blast!", "appId": "com.block.juggle"},
    ])
    assert parse_package_id("blockblast") == "com.block.juggle"


def test_featured_app_with_missing_id_raises_instead_of_picking_clone(monkeypatch):
    # Library bug: featured placement returns appId=None. Falling through to
    # the next result would silently crawl a lookalike app.
    _mock_search(monkeypatch, [
        {"title": "Block Blast!", "appId": None},
        {"title": "Block Blast VN", "appId": "com.blockblast.vn"},
    ])
    with pytest.raises(ValueError, match="package ID"):
        parse_package_id("blockblast")


def test_partial_match_uses_normalized_titles(monkeypatch):
    _mock_search(monkeypatch, [
        {"title": "Some Other Game", "appId": "com.other"},
        {"title": "Roblox — play together", "appId": "com.roblox.client"},
    ])
    assert parse_package_id("ROBLOX") == "com.roblox.client"
