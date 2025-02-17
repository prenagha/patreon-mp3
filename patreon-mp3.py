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
from eyed3.id3 import Tag
from eyed3.id3 import ID3_V2_4
from pathlib import Path
from urllib.parse import urlparse

# function that cleans up a file name so we can use it as the 
# local download file name
def download_name (n):
  o = re.sub(r'\s+', r'_', n)
  o = re.sub(r'[^a-zA-Z0-9_]', r'', o).lower()
  return cfg.get('DownloadPrefix') + o[:100]

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
    #print(f"audioUrl: {audioUrl}")          # DEBUG: Print the original URL
    #print(f"base_audioUrl: {base_audioUrl}") # DEBUG: Print the base URL after parsing
    ext = re.sub(r'.*\.',r'', base_audioUrl.lower()) # Use base_audioUrl here
    song_base_filename = download_name(published.strftime("%Y%m%d") + '_' + song) # Calculate base filename
    audioFileName = song_base_filename + '.' + ext # Combine with extension
    #print(f"audioFileName: {audioFileName}") # DEBUG: Print the generated filename

    if Path(audioFileName).is_file():
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
# items on next run
with open(lastRunSeenFileName, 'w') as ls_file:
  print(lastSeen.isoformat(), end='', file=ls_file)
