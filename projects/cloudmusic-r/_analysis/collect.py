# -*- coding: utf-8 -*-
"""Collect music taste data from NCM client caches + public API."""
import json, os, re, sys, time, sqlite3, collections
import requests

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\App\CloudMusic_R\_analysis'
OUT = os.path.join(BASE, 'dataset.json')
S = requests.Session()
S.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    'Referer': 'https://music.163.com/',
    'Cookie': 'os=pc; appver=3.0.0',
})

def load_cache(name):
    p = os.path.join(BASE, name)
    if os.path.exists(p):
        return json.load(open(p, encoding='utf-8'))
    return None

# ---------- 1. Local sqlite ----------
con = sqlite3.connect(os.path.join(BASE, 'webdb_copy.dat'))
cur = con.cursor()

def rows_to_tracks(table):
    out = []
    for pt, tid, js in cur.execute(f'SELECT playtime, id, jsonStr FROM {table}'):
        try:
            j = json.loads(js)
            j['playtime'] = pt
            out.append(j)
        except Exception:
            pass
    return out

local_history = rows_to_tracks('historyTracks')
playing_count = []
for row in cur.execute('SELECT resourceId, playDuration, updateTime, source, uid, resourceType, jsonStr FROM playingCount'):
    rid, dur, upd, src, uid, rtype, js = row
    playing_count.append({'resourceId': rid, 'playDuration': dur, 'updateTime': upd,
                          'source': src, 'uid': uid, 'resourceType': rtype})
dbtrack = []
for tid, js in cur.execute('SELECT id, jsonStr FROM dbTrack'):
    try:
        dbtrack.append(json.loads(js))
    except Exception:
        pass
con.close()
print(f'local historyTracks={len(local_history)} playingCount={len(playing_count)} dbTrack={len(dbtrack)}')

# ---------- 2. Cached API responses ----------
def norm_artist_names(artists):
    return [a.get('name', '') for a in (artists or []) if a.get('name')]

def song_from_songrec(d):  # data sub-object of play-record item
    return {'id': d.get('id'), 'name': d.get('name'),
            'artists': norm_artist_names(d.get('ar') or d.get('artists')),
            'album': (d.get('al') or d.get('album') or {}).get('name'),
            'album_id': (d.get('al') or {}).get('id') if isinstance(d.get('al'), dict) else None,
            'publish': (d.get('al') or {}).get('publishTime') if isinstance(d.get('al'), dict) else None,
            'duration': d.get('dt') or d.get('duration'), 'pop': d.get('pop')}

recent_songs = []
j = load_cache('cache_play_record_song_list.json')
for it in (j['data']['list'] if j else []):
    t = song_from_songrec(it['data'])
    t['playtime'] = it['playTime']
    recent_songs.append(t)

album_records = []
j = load_cache('cache_play_record_album_list.json')
for it in (j['data']['list'] if j else []):
    d = it['data']
    album_records.append({'id': d.get('id'), 'name': d.get('name'),
                          'artist': norm_artist_names(d.get('artists') or d.get('ar')),
                          'publish': d.get('publishTime'), 'playtime': it['playTime'],
                          'size': d.get('size')})

playlist_records = []
j = load_cache('cache_play_record_playlist_list.json')
for it in (j['data']['list'] if j else []):
    d = it['data']
    playlist_records.append({'id': d.get('id'), 'name': d.get('name'),
                             'playtime': it['playTime']})

voice_records = []
j = load_cache('cache_play_record_voice_list.json')
for it in (j['data']['list'] if j else []):
    d = it['data']
    name = d.get('name')
    dj = d.get('dj') or {}
    voice_records.append({'id': d.get('id'), 'name': name,
                          'creator': (dj.get('brand') or dj.get('name') or ''),
                          'playtime': it['playTime']})

# user playlist list
up = load_cache('cache_user_playlist.json')
user_playlists = []
for p in (up.get('playlist') or []):
    cr = p.get('creator') or {}
    user_playlists.append({'id': p['id'], 'name': p.get('name'), 'trackCount': p.get('trackCount'),
                           'own': cr.get('userId') in (432395459, 17856823984),
                           'creator': cr.get('nickname'), 'subscribed': p.get('subscribed')})
own_pls = [p for p in user_playlists if p['own']]
print(f'user playlists={len(user_playlists)} own={len(own_pls)}')
if own_pls:
    print('  sample own creator:', own_pls[0])

# ---------- 3. Already-cached playlist details ----------
playlists = {}  # id -> {'id','name','trackCount','tracks':[...]}
for fn in os.listdir(BASE):
    if not fn.startswith('cache_'):
        continue
    try:
        j = json.load(open(os.path.join(BASE, fn), encoding='utf-8'))
    except Exception:
        continue
    for pl in [j.get('playlist')] if isinstance(j.get('playlist'), dict) else []:
        if pl.get('id'):
            playlists[pl['id']] = {'id': pl['id'], 'name': pl.get('name'),
                                   'trackCount': pl.get('trackCount'),
                                   'tracks': pl.get('tracks') or []}
print('pre-cached playlist details:', len(playlists))

def api_playlist(pid, n=1000):
    url = f'https://music.163.com/api/v6/playlist/detail?id={pid}&n={n}'
    for attempt in range(3):
        try:
            r = S.get(url, timeout=20)
            j = r.json()
            if j.get('code') == 200 and j.get('playlist'):
                return j['playlist']
            if j.get('code') in (301, 400):
                return None
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
    return None

def fetch_missing_track_details(ids):
    out = []
    for i in range(0, len(ids), 900):
        chunk = ids[i:i+900]
        try:
            r = S.post('https://music.163.com/api/v3/song/detail',
                       data={'ids': json.dumps(chunk), 'c': json.dumps([{'id': x} for x in chunk])},
                       timeout=20)
            j = r.json()
            for d in (j.get('songs') or []):
                out.append({'id': d.get('id'), 'name': d.get('name'),
                            'artists': norm_artist_names(d.get('ar') or d.get('artists')),
                            'album': (d.get('al') or {}).get('name'),
                            'publish': (d.get('al') or {}).get('publishTime'),
                            'duration': d.get('dt') or d.get('duration'), 'pop': d.get('pop')})
        except Exception:
            pass
    return out

# ---------- 4. Fetch own playlists via public API ----------
need = []
for p in own_pls:
    if p['trackCount'] and p['id'] not in playlists:
        need.append(p)
print(f'fetching {len(need)} own playlists ...')
fetched = 0
for p in need:
    pl = api_playlist(p['id'])
    if pl:
        trs = pl.get('tracks') or []
        tids = [t['id'] for t in (pl.get('trackIds') or [])]
        if len(tids) > len(trs):
            missing = [i for i in tids if i not in {t['id'] for t in trs}]
            trs += fetch_missing_track_details(missing)
        playlists[pl['id']] = {'id': pl['id'], 'name': pl.get('name'),
                               'trackCount': pl.get('trackCount'), 'tracks': trs}
        fetched += 1
    time.sleep(0.3)
print(f'fetched {fetched} playlists, total details {len(playlists)}')

# ---------- 5. Save dataset ----------
dataset = {
    'local_history': local_history,
    'playing_count': playing_count,
    'recent_songs': recent_songs,
    'album_records': album_records,
    'playlist_records': playlist_records,
    'voice_records': voice_records,
    'user_playlists': user_playlists,
    'playlist_details': list(playlists.values()),
    'dbtrack_count': len(dbtrack),
}
json.dump(dataset, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print('saved ->', OUT)
total_tracks = sum(len(p['tracks']) for p in playlists.values())
print('playlist tracks total:', total_tracks)
