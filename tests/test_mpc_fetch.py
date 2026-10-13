"""Tests: credential-free Sentinel-1 access via Microsoft Planetary Computer.

Planetary Computer mirrors the same ESA Sentinel-1 GRD products CDSE serves,
and it answers anonymous requests. These tests pin the pure logic -- blob-URL
parsing, STAC-feature normalisation, SAFE-layout mapping and SAS-token caching
-- so a network-free run can prove the transport is wired correctly.

Run:  python -m pytest tests/test_mpc_fetch.py -v
"""
import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ml.sar import mpc_fetch  # noqa: E402


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.status = 200
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


class TestBlobParsing:
    def test_account_and_container_extracted(self):
        acct, cont = mpc_fetch.account_container(
            "https://sentinel1euwest.blob.core.windows.net/s1-grd/x/y/vv.tiff")
        assert (acct, cont) == ("sentinel1euwest", "s1-grd")

    def test_non_blob_href_rejected(self):
        with pytest.raises(ValueError, match="not a blob href"):
            mpc_fetch.account_container("https://example.com/x.tiff")


class TestSceneNormalisation:
    def _feature(self):
        return {
            "id": "S1A_IW_GRDH_1SDV_20250710T233056_20250710T233121_060028_077526_568F",
            "properties": {"datetime": "2025-07-10T23:30:56Z",
                           "platform": "sentinel-1a"},
            "geometry": {"type": "Polygon", "coordinates": [
                [[90.0, 25.0], [91.0, 25.0], [91.0, 26.0],
                 [90.0, 26.0], [90.0, 25.0]]]},
            "assets": {"vv": {"href": "https://a.blob.core.windows.net/c/vv.tiff"}},
        }

    def test_safe_suffix_reattached(self):
        sc = mpc_fetch.scene_from_feature(self._feature())
        assert sc["name"].endswith(".SAFE")

    def test_bbox_computed_from_geometry(self):
        sc = mpc_fetch.scene_from_feature(self._feature())
        assert sc["bbox"] == [90.0, 25.0, 91.0, 26.0]

    def test_platform_and_asset_hrefs_flattened(self):
        sc = mpc_fetch.scene_from_feature(self._feature())
        assert sc["platform"] == "SENTINEL-1A"
        assert sc["assets"]["vv"].endswith("vv.tiff")

    def test_scene_dir_name_strips_safe(self):
        assert mpc_fetch.scene_dir_name({"name": "S1A_X.SAFE"}) == "S1A_X"
        assert mpc_fetch.scene_dir_name({"id": "S1A_Y"}) == "S1A_Y"


class TestSafeLayout:
    def test_asset_targets_cover_calibration_chain(self):
        t = mpc_fetch.asset_targets("VV")
        assert set(t) == {"vv", "schema-calibration-vv",
                          "schema-noise-vv", "schema-product-vv"}
        assert t["vv"] == ("measurement", "s1a-iw-vv.tiff")
        assert t["schema-calibration-vv"][0] == "annotation/calibration"

    def test_lowercase_pol_accepted(self):
        assert "vv" in mpc_fetch.asset_targets("vv")


class TestSasExpiry:
    def test_iso_expiry_parsed(self):
        # 2026-01-01T00:00:00Z as a UTC epoch (deterministic, not wall-clock)
        assert mpc_fetch._parse_expiry("2026-01-01T00:00:00Z") == 1767225600.0

    def test_bad_input_returns_none(self):
        assert mpc_fetch._parse_expiry(None) is None
        assert mpc_fetch._parse_expiry("not-a-date") is None


class TestSasCache:
    def test_token_ignored_expiry_is_still_usable(self):
        # cache hit path: no network, returns the already-held token
        cache = mpc_fetch.SasCache()
        href = "https://acct.blob.core.windows.net/cont/f.tiff"
        key = ("acct", "cont")
        cache._tokens[key] = ("se=2099&sig=xyz", time.time() + 10_000)
        assert cache.token_for(href) == "se=2099&sig=xyz"

    def test_miss_fetches_once_then_reuses(self, monkeypatch):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            return _FakeResp(json.dumps(
                {"token": "se=2099&sig=abc",
                 "msft:expiry": "2099-01-01T00:00:00Z"}).encode())

        monkeypatch.setattr(mpc_fetch.urllib.request, "urlopen", fake_urlopen)
        cache = mpc_fetch.SasCache()
        href = "https://acct.blob.core.windows.net/cont/f.tiff"
        assert cache.token_for(href) == "se=2099&sig=abc"
        assert cache.token_for(href) == "se=2099&sig=abc"
        assert calls["n"] == 1                     # second call served from cache

    def test_signed_url_appends_token(self, monkeypatch):
        monkeypatch.setattr(mpc_fetch.SasCache, "token_for",
                            lambda self, href, force=False: "se=1&sig=t")
        out = mpc_fetch.signed_url("https://a.blob.core.windows.net/c/f.tiff",
                                   mpc_fetch.SasCache())
        assert out.endswith("?se=1&sig=t")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
