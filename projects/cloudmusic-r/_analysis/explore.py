# -*- coding: utf-8 -*-
"""Exploratory pass: see what we have."""
import json, sys, time, collections, re
sys.stdout.reconfigure(encoding='utf-8')
D = json.load(open(r'D:\App\CloudMusic_R\_analysis\dataset.json', encoding='utf-8'))
BASE = r'D:\App\CloudMusic_R\_analysis'

def ts(ms):
    return time.strftime('%Y-%m-%d', time.localtime(ms/1000)) if ms else '?'

recent = D['recent_songs']
hist = D['local_history']
# local history jsonStr has full song objects too
print('== recent server plays:', len(recent), ts(min(x['playtime'] for x in recent)), '->', ts(max(x['playtime'] for x in recent)))
print('== local history:', len(hist), ts(min(x['playtime'] for x in hist)), '->', ts(max(x['playtime'] for x in hist)))

# merge plays: recent(server) + local history (dedupe by id & close timestamp)
plays = []
seen = set()
for x in recent:
    key = (x['id'], x['playtime'] // 60000)
    if key in seen: continue
    seen.add(key)
    plays.append(x)
for x in hist:
    t = {'id': x.get('id'), 'name': x.get('name'),
         'artists': [a.get('name') for a in x.get('artists') or [] if a.get('name')],
         'album': (x.get('album') or {}).get('albumName') if isinstance(x.get('album'), dict) else None,
         'album_id': (x.get('album') or {}).get('id') if isinstance(x.get('album'), dict) else None,
         'publish': None, 'playtime': x['playtime']}
    key = (t['id'], t['playtime'] // 60000)
    if key in seen: continue
    seen.add(key)
    plays.append(t)
print('== merged plays:', len(plays))

# top artists recent
ac = collections.Counter()
tc = collections.Counter()
for p in plays:
    for a in p['artists']:
        ac[a] += 1
    tc[(p['name'], '/'.join(p['artists'][:2]))] += 1
print('\n== TOP artists (recent 6 weeks plays) ==')
for a, c in ac.most_common(30):
    print(f'{c:4d}  {a}')
print('\n== TOP tracks ==')
for (n, ar), c in tc.most_common(20):
    print(f'{c:3d}  {n} — {ar}')

# liked music
pls = {p['id']: p for p in D['playlist_details']}
liked = pls.get(620266109) or {}
lt = liked.get('tracks') or []
print('\n== liked music tracks:', len(lt), '/', liked.get('trackCount'))
lac = collections.Counter()
for t in lt:
    for a in (t.get('artists') or []):
        lac[a] += 1
for a, c in lac.most_common(30):
    print(f'{c:4d}  {a}')

# imports (local library)
imports = [p for p in D['playlist_details'] if str(p.get('name','')).startswith('导入音乐')]
ic = collections.Counter()
for p in imports:
    for t in p['tracks']:
        for a in (t.get('artists') or []):
            ic[a] += 1
print('\n== imported playlists:', len(imports), 'tracks:', sum(len(p['tracks']) for p in imports))
for a, c in ic.most_common(25):
    print(f'{c:4d}  {a}')

# dated snapshots (日推 archives)
snaps = []
for p in D['playlist_details']:
    m = re.search(r'(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})', p.get('name') or '')
    if m and ('日推' in p['name'] or '推荐' in p['name']):
        snaps.append((m.group(0), p['name'], len(p['tracks'])))
snaps.sort()
print('\n== dated daily-rec snapshots ==')
for s in snaps: print(' ', s)

# playlist play records timeline
print('\n== playlist play records (last 40) ==')
prs = sorted(D['playlist_records'], key=lambda x: -x['playtime'])
for r in prs[:40]:
    print(' ', ts(r['playtime']), r['name'][:40])

# album records
print('\n== album play records ==')
for r in sorted(D['album_records'], key=lambda x: -x['playtime'])[:30]:
    print(' ', ts(r['playtime']), '|', '/'.join(r['artist'])[:30], '|', r['name'])

# voice/podcast
print('\n== voice (podcast) records: top creators ==')
vc = collections.Counter(v['creator'] for v in D['voice_records'] if v['creator'])
for c, n in vc.most_common(15): print(f'{n:3d}  {c}')

# playlist names of own (semantic)
print('\n== own playlist names (non-日推, non-导入) ==')
for p in D['user_playlists']:
    if p['own'] and '日推' not in p['name'] and '导入' not in p['name'] and '推荐' not in p['name']:
        print('  [%5d] %s' % (p['trackCount'], p['name']))
