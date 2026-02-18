import yt_dlp
import asyncio

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
}

_ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)


async def extract_youtube(search: str):
    """Extracts a youtube URL/title/info for a search term or direct URL."""
    def run():
        return _ytdl.extract_info(search, download=False)

    info = await asyncio.to_thread(run)
    if not info:
        return None

    if 'entries' in info:
        entry = info['entries'][0]
    else:
        entry = info

    url = None
    if 'formats' in entry and entry['formats']:
        for f in reversed(entry['formats']):
            if f.get('acodec') != 'none' and f.get('url'):
                url = f['url']
                break
    if not url and entry.get('url'):
        url = entry['url']

    title = entry.get('title') or entry.get('id')

    return {'title': title, 'url': url, 'webpage_url': entry.get('webpage_url')}


async def extract_playlist(playlist_url: str):
    """Extract entries from a YouTube playlist URL and return list of track dicts.

    Each track dict has `title`, `url` (direct playable url), and `webpage_url`.
    """
    def run():
        return _ytdl.extract_info(playlist_url, download=False)

    info = await asyncio.to_thread(run)
    if not info:
        return []

    entries = info.get('entries') or []
    results = []
    for e in entries:
        # prefer webpage_url if present
        page = e.get('webpage_url') or e.get('url')
        if not page:
            continue
        # reuse extract_youtube to get playable url and title
        track = await extract_youtube(page)
        if track:
            results.append(track)

    return results
