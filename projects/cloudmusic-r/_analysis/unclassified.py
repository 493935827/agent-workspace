# -*- coding: utf-8 -*-
"""Check remaining unclassified, >=2 occurrences."""
import json, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\App\CloudMusic_R\_analysis'
D = json.load(open(BASE + r'\dataset.json', encoding='utf-8'))
from classify import track_of, clean, genre, is_ost

plays, seen = [], set()
for x in D['recent_songs']:
    k = (x['id'], x['playtime'] // 60000)
    if k not in seen: seen.add(k); plays.append(track_of(x) | {'playtime': x['playtime']})
for x in D['local_history']:
    k = (x.get('id'), x['playtime'] // 60000)
    if k in seen: continue
    seen.add(k)
    plays.append({'id': x.get('id'), 'name': x.get('name'),
                  'artists': [a.get('name') for a in x.get('artists') or [] if a.get('name')],
                  'album': (x.get('album') or {}).get('albumName') if isinstance(x.get('album'), dict) else None,
                  'publish': None, 'playtime': x['playtime']})
pls = {p['id']: p for p in D['playlist_details']}
liked = clean([track_of(t) for t in (pls.get(620266109) or {}).get('tracks') or []])

un_recent = collections.Counter()
un_liked = collections.Counter()
for p in plays:
    if genre(p) == '其他':
        for a in p['artists']: un_recent[a] += 1
for t in liked:
    if genre(t) == '其他':
        for a in t['artists']: un_liked[a] += 1
print('== unclassified recent >=2 ==')
for a, c in un_recent.most_common(60):
    if c >= 2: print(f'{c:3d}  {a}')
print('\n== unclassified liked >=3 ==')
for a, c in un_liked.most_common(80):
    if c >= 3: print(f'{c:3d}  {a}')
print('\nliked unique artists:', len(set(a for t in liked for a in t['artists'])),
      'liked tracks:', len(liked))
