#!/usr/local/bin/python3

import feedparser
import re
import requests
import shutil
import time
import os
import configparser
from eyed3.id3 import Tag
from eyed3.id3 import ID3_V2_4
from pathlib import Path

parser = configparser.ConfigParser()
parser.read('config.ini')
cfg = parser['feed']

f = feedparser.parse(cfg.get('RSSURL'))
    
def download_name (n):
  o = re.sub(r'\s+', r'_', n)
  o = re.sub(r'[^a-zA-Z0-9_]', r'', o).lower()
  return cfg.get('DownloadPrefix') + o[:100]

artist = f.feed.title
imageUrl = f.feed.image.href

print ('Get artist image')
imageResponse = requests.get(imageUrl)

cnt = 0
f.entries.reverse()
for item in f.entries:
  cnt += 1
  song = item.title
  comment = item.summary.replace('<br>','').strip()
  published = item.published_parsed
  for enc in item.enclosures:
    audioUrl = enc.url
    ext = re.sub(r'.*\.',r'', audioUrl.lower())
    audioFileName = download_name(time.strftime("%Y%m%d", published) + '_' + song) + '.' + ext
    if Path(audioFileName).is_file():
      continue

    print ('Downloading audio file ' + str(cnt) + '/' + str(len(f.entries)) + ' ' + song)
    with requests.get(audioUrl) as audioResponse:
      with open(audioFileName, 'wb') as audioFile:
        for chunk in audioResponse.iter_content(chunk_size=128):
          audioFile.write(chunk)
      audioFile.close()
      audioResponse.close()
      if ext != 'wav':
        t = Tag()
        t.artist = artist
        t.album_artist = artist
        t.album = cfg.get('Album')
        t.title = song[:100]
        t.comments.set(comment)
        t.release_date = time.strftime("%Y-%m-%d", published)
        t.recording_date = time.strftime("%Y", published)
        t.genre = cfg.get('Genre')
        t.track_num = (cnt,len(f.entries))
        t.disc_num = (1,1)
        t.images.set(3, imageResponse.content, imageResponse.headers['content-type'])
        t.save(audioFileName, version=ID3_V2_4)
      os.utime(audioFileName, (time.mktime(published), time.mktime(published)))
