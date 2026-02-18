import requests
import re


def is_spotify_url(text: str) -> bool:
    return bool(re.search(r"open\.spotify\.com/(track|album|playlist)", text))


def resolve_spotify_title(url: str) -> str | None:
    """Try to resolve a Spotify URL to a human-readable title via oEmbed."""
    try:
        r = requests.get('https://open.spotify.com/oembed', params={'url': url}, timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get('title')
    except Exception:
        return None
