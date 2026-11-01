import hashlib
import json

import pytest
import requests

from golf_matching.sources import Cache, CacheError


class Response:
    status_code = 200
    content = b"test source"
    headers = {"Content-Type": "text/plain"}
    url = "https://example.org/data"

    def raise_for_status(self):
        pass


def test_replay_and_integrity(tmp_path):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response()
    c = Cache(tmp_path, delay=0, get=get)
    p = c.fetch(Response.url)
    assert p.read_bytes() == Response.content
    assert c.fetch(Response.url) == p
    assert calls == [Response.url]
    assert Cache(tmp_path, offline=True).fetch(Response.url) == p
    p.write_bytes(b"truncated")
    with pytest.raises(CacheError, match="hash"):
        c.fetch(Response.url)


def test_offline_missing_and_orphan(tmp_path):
    c = Cache(tmp_path, offline=True)
    with pytest.raises(CacheError, match="not cached"):
        c.fetch(Response.url)
    key = hashlib.sha256(Response.url.encode()).hexdigest()
    (tmp_path / f"{key}.bin").write_bytes(b"partial")
    with pytest.raises(CacheError):
        c.fetch(Response.url)


def test_retry_limit_and_no_cache_on_failure(tmp_path):
    calls = []
    def fail(url, **kwargs):
        calls.append(url)
        raise requests.ConnectionError("unavailable")
    with pytest.raises(requests.ConnectionError):
        Cache(tmp_path, delay=0, retries=2, get=fail).fetch(Response.url)
    assert len(calls) == 3
    assert not list(tmp_path.glob('*.json'))


def test_metadata_is_bound_to_url_and_payload(tmp_path):
    c = Cache(tmp_path, delay=0, get=lambda *a, **kw: Response())
    p = c.fetch(Response.url)
    meta = json.loads(p.with_suffix('.json').read_text())
    assert meta['url'] == Response.url
    assert meta['sha256'] == hashlib.sha256(Response.content).hexdigest()
    assert meta['retrieved_at']

