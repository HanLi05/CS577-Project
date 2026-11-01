"""Content-verified, immutable HTTP snapshots and public source discovery."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import requests

USER_AGENT = "CS577-GolfResearch/0.1 (academic pilot; cached, paced requests)"
RELEASES = "https://api.github.com/repos/array-carpenter/golfastr/releases"
ASAP = "https://www.asapsports.com/"


class CacheError(RuntimeError):
    pass


class Cache:
    def __init__(self, root, offline=False, delay=1.0, retries=2, get=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.offline, self.delay, self.retries = offline, delay, retries
        self.get = get or requests.Session().get
        self.last_request = 0.0

    def fetch(self, url, allowed_status=()):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.root / f"{key}.bin"
        meta_path = path.with_suffix(".json")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
                raise CacheError(f"Cache hash mismatch: {url}")
            if meta['url'] != url:
                raise CacheError(f"Cache URL mismatch: {url}")
            if meta['status'] != 200 and meta['status'] not in allowed_status:
                raise CacheError(f"Cached HTTP {meta['status']}: {url}")
            return path
        if self.offline:
            raise CacheError(f"Source not cached: {url}")
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
                if response.status_code not in allowed_status:
                    response.raise_for_status()
                break
            except requests.RequestException as error:
                # Do not retry permanent HTTP errors, authentication, or rate limits.
                status = getattr(getattr(error, 'response', None), 'status_code', None)
                if attempt == self.retries or (status and status < 500):
                    raise
                time.sleep(self.delay * (2 ** attempt))
        content = response.content
        temporary = path.with_suffix('.part')
        temporary.write_bytes(content)
        temporary.replace(path)
        metadata = {
            "url": url, "resolved_url": response.url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
            "status": response.status_code, "content_type": response.headers.get('Content-Type'),
            "collector_version": "0.1.0",
        }
        temporary = meta_path.with_suffix('.part')
        temporary.write_text(json.dumps(metadata, indent=2) + '\n')
        temporary.replace(meta_path)
        return path

    def json(self, url):
        return json.loads(self.fetch(url).read_bytes())

    def check_robots(self, base):
        url = urljoin(base, "robots.txt")
        path = self.fetch(url, allowed_status=(404,))
        meta = json.loads(path.with_suffix('.json').read_text())
        parser = RobotFileParser()
        parser.parse([] if meta['status'] == 404 else path.read_text(errors='replace').splitlines())
        return parser


def links(content, base, contains):
    soup = BeautifulSoup(content, 'html.parser')
    return sorted(set((a.get_text(' ', strip=True), urljoin(base, a['href']).replace('http://www.asapsports.com', ASAP.rstrip('/')))
                      for a in soup.select('a[href]') if contains in a['href']))


def release_assets(cache):
    return {a['name']: a for release in cache.json(RELEASES) for a in release['assets']}


def fetch_asset(cache, assets, name):
    if name not in assets:
        raise CacheError(f"golfastR release asset not available: {name}")
    asset = assets[name]
    path = cache.fetch(asset['browser_download_url'])
    digest = asset.get('digest')
    if digest and digest.startswith('sha256:') and hashlib.sha256(path.read_bytes()).hexdigest() != digest[7:]:
        raise CacheError(f"Release digest mismatch: {name}")
    return path
