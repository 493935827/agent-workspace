# -*- coding: utf-8 -*-
"""Full music-taste analysis for bottlehunter (近1年)."""
import json, os, re, sys, time, collections, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

sys.stdout.reconfigure(encoding='utf-8')
BASE = r'D:\App\CloudMusic_R\_analysis'
D = json.load(open(os.path.join(BASE, 'dataset.json'), encoding='utf-8'))

for f in ['Microsoft YaHei', 'SimHei', 'DengXian']:
    if any(f.lower() == ff.name.lower() for ff in font_manager.fontManager.ttflist):
        plt.rcParams['font.sans-serif'] = [f]
        break
plt.rcParams['axes.unicode_minus'] = False

NOW = max(x['playtime'] for x in D['local_history'] + D['recent_songs'])  # ms
YEAR_AGO = NOW - 365 * 86400 * 1000
def dt(ms): return datetime.datetime.fromtimestamp(ms / 1000)
def ymd(ms): return dt(ms).strftime('%Y-%m-%d')

from classify import track_of, clean, is_ost, lang, genre, OST_RE

# ---------------- 1. recent plays (6 weeks of event logs) ----------------
plays, seen = [], set()
for x in D['recent_songs']:
    k = (x['id'], x['playtime'] // 60000)
    if k not in seen:
        seen.add(k); plays.append(track_of(x) | {'playtime': x['playtime']})
for x in D['local_history']:
    k = (x.get('id'), x['playtime'] // 60000)
    if k in seen: continue
    seen.add(k)
    plays.append({'id': x.get('id'), 'name': x.get('name'),
                  'artists': [a.get('name') for a in x.get('artists') or [] if a.get('name')],
                  'album': (x.get('album') or {}).get('albumName') if isinstance(x.get('album'), dict) else None,
                  'publish': None, 'playtime': x['playtime']})
plays.sort(key=lambda p: p['playtime'])
print('recent plays:', len(plays), ymd(plays[0]['playtime']), '->', ymd(plays[-1]['playtime']))

# ---------------- 2. liked / imports ----------------
pls = {p['id']: p for p in D['playlist_details']}
liked_raw = (pls.get(620266109) or {}).get('tracks') or []
liked = [track_of(t) for t in liked_raw]
imports = []
for p in D['playlist_details']:
    if str(p.get('name', '')).startswith('导入音乐'):
        imports += [track_of(t) for t in p['tracks']]
liked, imports = clean(liked), clean(imports)
print('liked:', len(liked), 'imports:', len(imports))

# ---------------- 4. metrics ----------------
def counter_tracks(tracks, weight=1):
    ac, tc = collections.Counter(), collections.Counter()
    for t in tracks:
        for a in t['artists']: ac[a] += weight
        tc[(t['name'], ' / '.join(t['artists'][:2]))] += weight
    return ac, tc

recent_ac, recent_tc = counter_tracks(plays, 1)
liked_ac, _ = counter_tracks(liked, 1)
imp_ac, _ = counter_tracks(imports, 1)

def top(c, n=15): return c.most_common(n)

# genre & language distributions
def dist(tracks_or_plays, key):
    c = collections.Counter()
    for t in tracks_or_plays:
        c[getattr(t, key)() if callable(getattr(t, key, None)) else key(t)] += 1
    return c

recent_genre = collections.Counter(genre(p) for p in plays)
liked_genre = collections.Counter(genre(t) for t in liked)
recent_lang = collections.Counter('原声(无人声)' if is_ost(p) else lang(p) for p in plays)
liked_lang = collections.Counter('原声(无人声)' if is_ost(t) else lang(t) for t in liked)

# era distribution (publish year)
def era_counts(tracks):
    c = collections.Counter()
    for t in tracks:
        pt = t.get('publish')
        if pt and pt > 0:
            y = dt(pt).year
            if 1950 <= y <= 2026:
                c[f"{(y//10)*10}s"] += 1
    return c
era_liked = era_counts(liked + imports)
era_recent = era_counts(plays)

# hour & weekday of recent plays
hours = collections.Counter(dt(p['playtime']).hour for p in plays)
wds = collections.Counter(dt(p['playtime']).weekday() for p in plays)

# listening time from playingCount (cumulative seconds per track)
total_sec = sum(r['playDuration'] for r in D['playing_count'] if r['resourceType'] == 'track')
dur_top = sorted(D['playing_count'], key=lambda r: -r['playDuration'])[:12]

# voice/podcast programs
voice_raw = json.load(open(os.path.join(BASE, 'cache_play_record_voice_list.json'), encoding='utf-8'))
programs, radios = [], collections.Counter()
for it in voice_raw['data']['list']:
    pd_ = (it['data'].get('pubDJProgramData') or {})
    radio = ((pd_.get('radio') or {}).get('name')) or ''
    radios[radio] += 1
    programs.append({'name': pd_.get('name') or it['data'].get('name'), 'radio': radio,
                     'playtime': it['playTime']})

# dated snapshots (日推 archives)
snaps = []
for p in D['playlist_details']:
    m = re.search(r'(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})', p.get('name') or '')
    if m and re.search(r'日推|推荐', p['name']):
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        tracks = [track_of(t) for t in p['tracks']]
        snaps.append({'date': d, 'name': p['name'], 'tracks': tracks,
                      'artists': collections.Counter(a for t in tracks for a in t['artists']),
                      'ost_ratio': sum(1 for t in tracks if is_ost(t)) / max(len(tracks), 1),
                      'lang': collections.Counter(('原声' if is_ost(t) else lang(t)) for t in tracks)})
snaps.sort(key=lambda s: s['date'])
year_snaps = [s for s in snaps if s['date'] >= datetime.date(2025, 1, 1)]

# playlist + album play records in past year
pl_recs = [r for r in D['playlist_records'] if r['playtime'] >= YEAR_AGO]
al_recs = [r for r in D['album_records'] if r['playtime'] >= YEAR_AGO]

# 2025 year playlist & decade playlist
y2025 = pls.get(17611939089) or {}
y2025_tracks = [track_of(t) for t in (y2025.get('tracks') or [])]
ten_pl = next((p for p in D['playlist_details'] if '十年' in (p.get('name') or '')), None)
ten_tracks = [track_of(t) for t in ((ten_pl or {}).get('tracks') or [])]

# active days / streak
days = sorted({dt(p['playtime']).date() for p in plays})

# ---------------- 5. charts ----------------
os.makedirs(os.path.join(BASE, 'charts'), exist_ok=True)
CH = os.path.join(BASE, 'charts')

# fig 1: hours + weekday
fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
hs = [hours.get(h, 0) for h in range(24)]
ax[0].bar(range(24), hs, color='#4c72b0')
ax[0].set_title('最近播放时段分布（近6周 %d 次播放）' % len(plays), fontsize=11)
ax[0].set_xticks(range(0, 24, 2)); ax[0].set_xlabel('小时'); ax[0].set_ylabel('播放次数')
wd = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
ax[1].bar(wd, [wds.get(i, 0) for i in range(7)], color='#dd8452')
ax[1].set_title('星期分布', fontsize=11)
plt.tight_layout(); plt.savefig(os.path.join(CH, 'fig_hours.png'), dpi=130); plt.close()

# fig 2: genre bars recent vs liked (merge fine buckets for readability)
def merge(g):
    if g in ('摇滚·朋克', '摇滚·独立', '后摇', '摇滚·布鲁斯'): return '摇滚·独立(含朋克/后摇)'
    if g in ('民谣·蓝草', '民谣·独立'): return '民谣·独立'
    if g in ('日系·动漫声优', '日系·独立'): return '日系'
    return g
recent_genre = collections.Counter(merge(g) for g in recent_genre.elements())
liked_genre = collections.Counter(merge(g) for g in liked_genre.elements())
genres = sorted(set(list(recent_genre) + list(liked_genre)),
                key=lambda g: -(recent_genre.get(g, 0) + liked_genre.get(g, 0)))
fig, ax = plt.subplots(figsize=(9, 5))
y = range(len(genres))
rv = [recent_genre.get(g, 0) for g in genres]
lv = [liked_genre.get(g, 0) for g in genres]
ax.barh([i + 0.2 for i in y], rv, height=0.4, label='最近6周实际播放', color='#4c72b0')
ax.barh([i - 0.2 for i in y], lv, height=0.4, label='收藏(红心)全部', color='#55a868')
ax.set_yticks(list(y)); ax.set_yticklabels(genres); ax.invert_yaxis()
ax.legend(); ax.set_title('音乐类型：近期在听 vs 长期收藏', fontsize=12)
plt.tight_layout(); plt.savefig(os.path.join(CH, 'fig_genre.png'), dpi=130); plt.close()

# fig 3: language donuts
fig, ax = plt.subplots(1, 2, figsize=(10, 4.4))
for a, (title, dist_) in zip(ax, [('最近6周播放', recent_lang), ('长期收藏(红心)', liked_lang)]):
    items = dist_.most_common()
    a.pie([v for _, v in items], labels=['%s %.0f%%' % (k, 100*v/sum(dist_.values())) for k, v in items],
          colors=plt.cm.tab20.colors, textprops={'fontsize': 9}, startangle=90)
    a.set_title(title, fontsize=11)
plt.tight_layout(); plt.savefig(os.path.join(CH, 'fig_lang.png'), dpi=130); plt.close()

# fig 4: era
order = sorted(era_liked)
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.bar(order, [era_liked[k] for k in order], color='#c44e52')
ax.set_title('收藏+导入曲库的发行年代分布（可识别年代的 %d 首）' % sum(era_liked.values()), fontsize=11)
plt.tight_layout(); plt.savefig(os.path.join(CH, 'fig_era.png'), dpi=130); plt.close()

# fig 5: past-year timeline stacked by category (playlist+album play records)
def rec_cat(name):
    if OST_RE.search(name): return '游戏/影视原声'
    if re.search(r'日推|推荐', name): return '日推存档'
    if re.search(r'Drake|Kanye|Hip|Rap|说唱', name, re.I): return '嘻哈'
    if re.search(r'Gorillaz|独立|Indie|AURORA|Mane|Måneskin', name, re.I): return '欧美独立'
    if re.search(r'粤语|华语|国风|莫文蔚|许嵩|陶喆', name): return '华语'
    return '其他/电子'
months = sorted({dt(r['playtime']).strftime('%Y-%m') for r in pl_recs + al_recs})
cats = ['游戏/影视原声', '日推存档', '嘻哈', '欧美独立', '华语', '其他/电子']
mat = {c: [0]*len(months) for c in cats}
for r in pl_recs + al_recs:
    m = dt(r['playtime']).strftime('%Y-%m')
    mat[rec_cat(r['name'])][months.index(m)] += 1
fig, ax = plt.subplots(figsize=(10, 4.2))
bottom = [0]*len(months)
colors = dict(zip(cats, ['#4c72b0', '#8c8c8c', '#c44e52', '#55a868', '#dd8452', '#ccb974']))
for c in cats:
    ax.bar(months, mat[c], bottom=bottom, label=c, color=colors[c])
    bottom = [b + v for b, v in zip(bottom, mat[c])]
ax.legend(fontsize=8, ncol=6); ax.set_title('近一年主动点开的内容（歌单/专辑播放记录，按月）', fontsize=11)
plt.xticks(rotation=45, fontsize=8)
plt.tight_layout(); plt.savefig(os.path.join(CH, 'fig_timeline.png'), dpi=130); plt.close()
print('charts saved')

# ---------------- 6. save analysis json (for report) ----------------
out = {
    'now': NOW, 'plays': len(plays), 'span': [ymd(plays[0]['playtime']), ymd(plays[-1]['playtime'])],
    'active_days': len(days), 'liked_count': len(liked), 'imports_count': len(imports),
    'recent_top_artists': top(recent_ac, 25), 'liked_top_artists': top(liked_ac, 20),
    'import_top_artists': top(imp_ac, 12),
    'recent_genre': recent_genre, 'liked_genre': liked_genre,
    'recent_lang': recent_lang, 'liked_lang': liked_lang,
    'era': era_liked, 'hours': {k: v for k, v in hours.items()},
    'total_listen_hours_recent': round(total_sec / 3600, 1),
    'snaps': [{'date': str(s['date']), 'name': s['name'], 'top_artists': s['artists'].most_common(5),
               'ost_ratio': round(s['ost_ratio'], 2), 'lang': dict(s['lang'])} for s in snaps],
    'pl_recs_year': len(pl_recs), 'al_recs_year': len(al_recs),
    'y2025_tracks': y2025_tracks, 'ten_tracks': ten_tracks,
    'radios': radios.most_common(12),
    'programs_recent': programs[:15],
}
json.dump(out, open(os.path.join(BASE, 'analysis.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
print('analysis.json saved')

# ---------------- 7. console summary ----------------
print('\n=== 近6周TOP艺人 ==='); [print(f'{c:3d} {a}') for a, c in out['recent_top_artists'][:20]]
print('\n=== 收藏TOP艺人 ==='); [print(f'{c:3d} {a}') for a, c in out['liked_top_artists']]
print('\n=== 类型分布(近6周) ==='); [print(f'{v:4d} {k}') for k, v in recent_genre.most_common()]
print('\n=== 类型分布(收藏) ==='); [print(f'{v:4d} {k}') for k, v in liked_genre.most_common()]
print('\n=== 日推快照语言变化 ===')
for s in out['snaps']:
    print(s['date'], s['lang'], s['top_artists'][:3])
print('\n2025年度歌单:', [t['name'] for t in y2025_tracks])
print('十年精选辑:', [t['name'] for t in ten_tracks][:18])
print('\n播客频道:', out['radios'])
