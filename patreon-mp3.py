#!/usr/local/bin/python3

import feedparser
import re
import requests
import shutil
import time
import datetime
import os
import configparser
import magic
import mimetypes
import argparse
from eyed3.id3 import Tag
from eyed3.id3 import ID3_V2_4
from pathlib import Path
from urllib.parse import urlparse

# common MIME-to-extension mapping for audio types
MIME_MAP = {
  'audio/mpeg': 'mp3',
  'audio/mp3': 'mp3',
  'audio/x-wav': 'wav',
  'audio/wav': 'wav',
  'audio/flac': 'flac',
  'audio/x-flac': 'flac',
  'audio/ogg': 'ogg',
  'application/ogg': 'ogg',
  'audio/webm': 'webm',
  'audio/aac': 'aac',
  'audio/mp4': 'm4a',
  'video/mp4': 'm4a',
}

# function that cleans up a file name so we can use it as the 
# local download file name
def download_name (n):
  o = re.sub(r'\s+', r'_', n)
  o = re.sub(r'[^a-zA-Z0-9_]', r'', o).lower()
  prefix = cfg.get('DownloadPrefix')
  if not prefix.endswith(os.sep):
    prefix = prefix + os.sep
  return os.path.join(prefix, o[:100])

# parse CLI args (do this early so we can run dry-runs)
argp = argparse.ArgumentParser(description='Patreon RSS audio downloader')
argp.add_argument('-n', '--dry-run', action='store_true', help='Do not download files or write state; only print planned actions')
argp.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debug output')
args = argp.parse_args()
DRY_RUN = args.dry_run
VERBOSE = args.verbose

# read in the configuration file
parser = configparser.ConfigParser()
parser.read('config.ini')
cfg = parser['feed']

# download the RSS XML and parse it
f = feedparser.parse(cfg.get('RSSURL'))
    
# file where we keep track of the last entry we previously saw
lastRunSeenFileName = cfg.get('DownloadPrefix') + '/last.txt'
lastRunSeen = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
if Path(lastRunSeenFileName).is_file():
  with open(lastRunSeenFileName, 'r') as ls_file:
    lastRunSeen = datetime.datetime.fromisoformat(ls_file.read())

artist = f.feed.title

# check if we already have a cover image, if not use the
# image specified in the RSS feed, downloading it to a local file
coverFileName = cfg.get('DownloadPrefix') + '/cover.jpg'
if not Path(coverFileName).is_file():
  imageUrl = f.feed.image.href
  print ('Download artist image')
  imageResponse = requests.get(imageUrl)
  with open(coverFileName, 'wb') as fd:
    for chunk in imageResponse.iter_content(chunk_size=256):
      fd.write(chunk)

# read in the cover image and figure out what file type it is
with open(coverFileName, 'rb') as file:
  coverImage = file.read()
coverImageType = magic.from_file(coverFileName, mime=True)

# now loop over the RSS feed items, in reverse order, 
# which hopefully is oldest first (so we get track numbers ordered properly)
lastSeen = datetime.datetime.fromtimestamp(0)
cnt = 0
f.entries.reverse()
for item in f.entries:
  cnt += 1
  song = item.title
  try:
    comment = item.summary.replace('<br>','').strip()
  except:
    pass
  published = datetime.datetime(item.published_parsed[0]
    ,item.published_parsed[1]
    ,item.published_parsed[2]
    ,item.published_parsed[3]
    ,item.published_parsed[4]
    ,item.published_parsed[5]
    ,0
    )

  # keep track of the most recent RSS item we have seen this run
  if published > lastSeen:
    lastSeen = published
    
  # if the item is older than the most recent item from the
  # last run, then skip it
  if published <= lastRunSeen:
    continue

  # process each enclosure of the RSS item, these are the links
  # to the audio files we want to download
  for enc in item.enclosures:
    audioUrl = enc.url
    parsed_url = urlparse(audioUrl)
    base_audioUrl = parsed_url.path
    if VERBOSE:
      print(f"audioUrl: {audioUrl}")
      print(f"base_audioUrl: {base_audioUrl}")

    # Determine file extension robustly:
    # 1) prefer the enclosure MIME type (if provided)
    # 2) fallback to the basename of the URL path
    # 3) fallback to a HEAD request Content-Type
    # 4) default to 'bin'

    ext = None
    mime = None
    try:
      mime = enc.get('type') if isinstance(enc, dict) else getattr(enc, 'type', None)
    except Exception:
      mime = None
    if mime:
      mime_key = mime.split(';')[0].strip().lower()
      if mime_key in MIME_MAP:
        ext = MIME_MAP[mime_key]
      else:
        guessed = mimetypes.guess_extension(mime_key)
        if guessed:
          ext = guessed.lstrip('.')

    if not ext:
      basename = os.path.basename(base_audioUrl)
      if '.' in basename:
        ext = basename.split('.')[-1].lower()

    if not ext:
      try:
        head = requests.head(audioUrl, allow_redirects=True, timeout=10)
        ct = head.headers.get('content-type')
        if ct:
          guessed = mimetypes.guess_extension(ct.split(';')[0].strip())
          if guessed:
            ext = guessed.lstrip('.')
      except Exception:
        pass

    if not ext:
      ext = 'bin'

    # sanitize extension to remove any stray slashes or unexpected chars
    ext = re.sub(r'[^a-z0-9]+', '', ext.lower())

    song_base_filename = download_name(published.strftime("%Y%m%d") + '_' + song)
    audioFileName = song_base_filename + ('.' + ext if ext else '')

    # ensure parent directory exists before writing (skip creation in dry-run)
    parent_dir = os.path.dirname(audioFileName) or '.'
    if not DRY_RUN:
      Path(parent_dir).mkdir(parents=True, exist_ok=True)

    if VERBOSE:
      print(f"ext: {ext}")
      print(f"audioFileName: {audioFileName}")

    if Path(audioFileName).is_file():
      continue

    if DRY_RUN:
      print('Dry-run: would download ' + audioFileName + ' from ' + audioUrl)
      continue

    print('Downloading new item ' + audioFileName)

    # go get the audio file and save it locally    
    with requests.get(audioUrl) as audioResponse:
      with open(audioFileName, 'wb') as audioFile:
        for chunk in audioResponse.iter_content(chunk_size=128):
          audioFile.write(chunk)
      audioFile.close()
      audioResponse.close()
      # replace the MP3 ID tags in the downloaded audio file
      if ext != 'wav':
        t = Tag()
        t.artist = artist
        t.album_artist = artist
        t.album = cfg.get('Album')
        t.title = song[:100]
        t.comments.set(comment)
        t.release_date = published.strftime("%Y-%m-%d")
        t.recording_date = published.strftime("%Y")
        t.genre = cfg.get('Genre')
        t.track_num = (cnt)
        t.disc_num = (1,1)
        t.images.set(3, coverImage, coverImageType)
        t.save(audioFileName, version=ID3_V2_4)
      # set the OS file time to the published time
      os.utime(audioFileName, (time.mktime(published.timetuple()), time.mktime(published.timetuple())))

# write out the newest item we saw, so we can skip previous
# items on next run (skip writing state in dry-run)
if not DRY_RUN:
  with open(lastRunSeenFileName, 'w') as ls_file:
    print(lastSeen.isoformat(), end='', file=ls_file)
