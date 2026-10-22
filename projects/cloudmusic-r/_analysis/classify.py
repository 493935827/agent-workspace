# -*- coding: utf-8 -*-
"""Shared classification logic."""
import re

OST_ARTISTS = {
    'Assassin\'s Creed', 'Assassins Creed', 'Jesper Kyd', 'Austin Wintory', 'Lorne Balfe',
    'C418', 'Sea Power', 'Andrew Arcadi', 'Embark Studios', 'Sailor & I', 'Conisch',
    '牛尾憲輔', '澤野弘之', '山本康太', 'ATLUS GAME MUSIC', '目黒将司', 'Howie Lee',
    'Jonathan Morali', 'Syngro', 'Gordon McGladdery', 'A Shell In The Pit',
    'Clark Aboud', 'Lena Raine', 'Inon Zur', 'Jeremy Soule', 'Hans Zimmer', 'Ramin Djawadi',
    'François Coté', 'Maclaine Diemer', 'Kumi Tanioka', 'Yoko Shimomura', 'Motoi Sakuraba',
    '高橋諒', '坂本英城', 'Daniel Hagström', 'Oskar Hansen', 'Neil Damy', 'Elliot Van Orman',
    'Christopher Larkin', 'Andrew Prahlow', 'Darren Korb', 'Jesper Kyd & Einar Selvik',
    'Team Cherry', 'Disco Elysium', 'British Sea Power', 'Sea Power.',
    'Alex Brandon', 'Kevin Penkin', 'Yasunori Mitsuda', 'Nobuo Uematsu', '下村陽子',
    'Ryosuke Kojima',
}
OST_RE = re.compile(
    r'OST|Original Sound|Soundtrack|\bScore\b|原声|原聲|配樂|配乐|BGM|游戏音乐|Original Game|'
    r'刺客信条|Assassin|Forza|极限竞速|THE FINAL|Disco Elysium|Life is Strange|Life Is Strange|'
    r'Edith Finch|Firewatch|Hollow Knight|空洞骑士|Witcher|巫师|BioShock|Persona|ペルソナ|'
    r'Sifu|师父|Dispatch|Borderlands|无主之地|Dishonored|耻辱|Prey|掠食|League of Legends|英雄联盟|'
    r'Minecraft|我的世界|Sekiro|只狼|Elden Ring|艾尔登法环|God of War|战神|Red Dead|荒野大镖客|'
    r'Game of Thrones|权力的游戏|Sonny Boy|漂流少年|進撃の巨人|进击的巨人|Ping Pong|ピンポン|'
    r'命运石|Xenoblade|异度|NieR|尼尔|Undertale|Celeste|Hades|哈迪斯|正义之怒|Pathfinder|'
    r'Journey|风之旅人|Child of Light|光之子|Eastshade|What Remains|Outer Wilds|星际拓荒|'
    r'昆特牌|Gwent|炉石|Hearthstone|Valorant|Apex|CS:GO|Dota|王者荣耀|原神|Genshin|崩坏|'
    r'明日方舟|Arknights|最终幻想|Final Fantasy|女神异闻录|Vol. \d+ \(Original', re.I)

def track_of(t):
    if 'ar' in t:
        artists = [a.get('name') for a in (t.get('ar') or []) if a.get('name')]
        al = t.get('al') or {}
        album = al.get('name'); publish = al.get('publishTime') or t.get('publishTime')
    else:
        artists = list(t.get('artists') or [])
        album = t.get('album'); publish = t.get('publish')
    return {'id': t.get('id'), 'name': t.get('name'), 'artists': artists,
            'album': album, 'publish': publish}

def clean(tracks):
    bad = re.compile(r'[\\/]|\.mp3|\.flac|\.wav|\.ape|未知|Unknown Artist', re.I)
    return [t for t in tracks
            if t.get('name') and not bad.search(t['name']) and not bad.search(' '.join(t['artists']))]

def is_ost(t):
    artists = ' / '.join(t['artists'])
    low = artists.lower()
    for a in OST_ARTISTS:
        if len(a) > 5 and a.lower() in low: return True
    album = t.get('album') or ''
    if OST_RE.search(album): return True
    if not t['artists'] and OST_RE.search(t.get('name') or ''): return True
    return False

def lang(t):
    s = ' '.join(t['artists']) + ' ' + (t.get('album') or '')
    if re.search(r'[\uac00-\ud7af]', s): return '韩语'
    if re.search(r'[\u3040-\u30ff]', s): return '日语'
    if re.search(r'[\u4e00-\u9fff]', s): return '华语'
    if re.search(r'[А-я]', s): return '俄语/其他'
    return '欧美(英语)'

GENRE_MAP = {
    **{a: '游戏与影视原声' for a in OST_ARTISTS},
    'KOAN Sound': '电子·低音与Funk', 'Opiuo': '电子·低音与Funk', 'Russ Liquid': '电子·低音与Funk',
    'The Funk Hunters': '电子·低音与Funk', 'Eprom': '电子·低音与Funk', 'G Jones': '电子·低音与Funk',
    'Hamdi': '电子·低音与Funk', 'Cesco': '电子·低音与Funk', 'IMANU': '电子·低音与Funk',
    'Shades': '电子·低音与Funk', 'Alix Perez': '电子·低音与Funk', 'Ivy Lab': '电子·低音与Funk',
    'Tsuruda': '电子·低音与Funk', 'Mefjus': '电子·低音与Funk', 'Joyryde': '电子·低音与Funk',
    'Flume': '电子·低音与Funk', 'Haywyre': '电子·低音与Funk', 'SunSquabi': '电子·低音与Funk',
    'Anomalie': '电子·低音与Funk', 'Kiefer': '电子·低音与Funk', 'Tennyson': '电子·低音与Funk',
    'Pretty Lights': '电子·低音与Funk', 'Gramatik': '电子·低音与Funk', 'KAYTRANADA': '电子·低音与Funk',
    'DJ小女孩': '电子·低音与Funk', 'eden2001': '电子·低音与Funk', 'MT1990': '电子·低音与Funk',
    'Bonobo': '电子·低音与Funk', 'Jungle': '电子·低音与Funk', 'Tom Misch': '电子·低音与Funk',
    'Parcels': '电子·低音与Funk', 'Kiasmos': '电子·低音与Funk', 'Polo & Pan': '电子·低音与Funk',
    'Dabeull': '电子·低音与Funk', 'Holybrune': '电子·低音与Funk', 'Disclosure': '电子·低音与Funk',
    'Justice': '电子·低音与Funk', 'Phoenix': '欧美独立·流行', 'Roosevelt': '电子·低音与Funk',
    'HVOB': '电子·低音与Funk', 'PYLOT': '电子·低音与Funk', 'Les Gordon': '电子·低音与Funk',
    'Lewis OfMan': '电子·低音与Funk', "L'Impératrice": '电子·低音与Funk', 'WDL': '电子·低音与Funk',
    'ILLENIUM': '电子·流行', 'Kygo': '电子·流行', 'Vexento': '电子·流行', 'Alex Skrindo': '电子·流行',
    'ODESZA': '电子·流行', 'San Holo': '电子·流行', 'MitiS': '电子·流行',
    'Sappheiros': '氛围·轻音乐', 'Tommee Profitt': '氛围·轻音乐', 'Jacoo': '氛围·轻音乐',
    'HOPE-T': '氛围·轻音乐', '三亩地': '氛围·轻音乐', 'Snigellin': '氛围·轻音乐', 'AniFace': '氛围·轻音乐',
    'DJ OKAWARI': '氛围·轻音乐', '千坂': '氛围·轻音乐', '逆时针向': '氛围·轻音乐',
    'Nocturnes曳取': '氛围·轻音乐', '浮云心丶': '氛围·轻音乐', 'MoreanP': '氛围·轻音乐', 'LOCH': '氛围·轻音乐',
    '接个吻，开一枪': '氛围·轻音乐', 'Emily Styler': '氛围·轻音乐', 'Corn Wave': '氛围·轻音乐',
    'Joep Beving': '氛围·轻音乐', 'Ólafur Arnalds': '氛围·轻音乐', 'Jazzinuf': '氛围·轻音乐',
    'Rook1e': '氛围·轻音乐', 'Emapea': '氛围·轻音乐', 'Ooyy': '氛围·轻音乐',
    'Drake': '嘻哈·R&B', 'Kanye West': '嘻哈·R&B', 'The Weeknd': '嘻哈·R&B',
    'Bill Withers': '嘻哈·R&B', 'grandson': '嘻哈·R&B',
    '许嵩': '华语流行', '张震岳': '华语流行', '莫文蔚': '华语流行', '王菲': '华语流行',
    '林忆莲': '华语流行', '陶喆': '华语流行', '陈粒': '华语流行', '丁世光': '华语流行',
    '魏诗莹': '华语流行', 'JOYCE 就以斯': '华语流行', '单依纯': '华语流行', '魏如萱': '华语流行',
    '草东没有派对': '摇滚·独立', '张天赋': '华语流行', '容祖儿': '华语流行', '曾舜晞': '华语流行',
    '麦浚龙': '华语流行', '李宇春': '华语流行', '毛不易': '华语流行', '水仙LONE': '华语流行',
    '胡纯': '华语流行', 'L1VET..': '华语流行', '梦游动物园': '华语流行', 'Fayzz': '后摇',
    '劣': '摇滚·朋克', 'My Chemical Romance': '摇滚·朋克', 'Måneskin': '摇滚·朋克',
    'Eels': '摇滚·独立', 'Phosphorescent': '摇滚·独立', 'Punch Brothers': '民谣·蓝草',
    'Glass Animals': '欧美独立·流行', 'Gorillaz': '欧美独立·流行', 'AURORA': '欧美独立·流行',
    'Cœur de pirate': '欧美独立·流行', 'Fleurie': '欧美独立·流行', 'The fin.': '日系·独立',
    'The Midnight': '欧美独立·流行', 'M83': '欧美独立·流行', 'The Marías': '欧美独立·流行',
    'Muse': '摇滚·独立', 'Temples': '摇滚·独立', 'Paolo Nutini': '欧美独立·流行',
    'Laufey': '爵士', 'Saint Motel': '欧美独立·流行', 'Cosmo Sheldrake': '欧美独立·流行',
    'Chromatics': '欧美独立·流行', 'The Raveonettes': '摇滚·独立', 'Portugal. The Man': '摇滚·独立',
    'Young the Giant': '摇滚·独立', 'The Walters': '欧美独立·流行', 'Summer Salt': '欧美独立·流行',
    'JAWNY': '欧美独立·流行', 'Conan Gray': '欧美独立·流行', 'Madison Beer': '欧美独立·流行',
    'Bella Poarch': '欧美独立·流行', 'Mae Muller': '欧美独立·流行', 'Arden Jones': '欧美独立·流行',
    'HYBS': '欧美独立·流行', 'Elderbrook': '电子·低音与Funk', 'The Blaze': '电子·低音与Funk',
    'Colyn': '电子·低音与Funk', 'Atomic Drum Assembly': '电子·低音与Funk',
    'We Were Promised Jetpacks': '摇滚·独立', 'Black Box Recorder': '摇滚·独立',
    'The Rare Occasions': '摇滚·独立', 'Heavenstamp': '摇滚·独立', 'Unlike Pluto': '电子·流行',
    '菅野よう子': '游戏与影视原声', 'BAGANZO': '摇滚·独立', 'Shakhbanov': '氛围·轻音乐',
    'MondayNight': '氛围·轻音乐', 'Mark Arkinson': '氛围·轻音乐', 'Bo Peep': '华语流行',
    'Trevor Kowalski': '氛围·轻音乐', 'karaoke SESH': '氛围·轻音乐', 'Romi Kopelman': '氛围·轻音乐',
    'Oskar Schuster': '氛围·轻音乐', 'Clementine': '氛围·轻音乐', 'Oscar Anton': '欧美独立·流行',
    'Magdy Haddad': '氛围·轻音乐', 'Ash': '摇滚·独立', 'Jobe': '氛围·轻音乐',
    'Motohiko Hirami': '氛围·轻音乐', 'Ana Popovic': '摇滚·布鲁斯', 'Milton Popovic': '摇滚·布鲁斯',
    'The Seven Mile Journey': '后摇', 'Gia Margaret': '民谣·独立', 'Reymour': '摇滚·独立',
    'LAGXNA': '摇滚·独立', 'Home Is Where': '摇滚·独立', 'SadSvit': '摇滚·独立',
    'Marc Scibilia': '欧美独立·流行', 'Chernikovskaya Hata': '其他', 'CATS NEVER DIE': '电子·低音与Funk',
    'BUNT.': '民谣·独立', 'Graham': '欧美独立·流行', 'Between the Trees': '摇滚·独立',
    'Opiuo & Russ Liquid': '电子·低音与Funk',
    # Funk / Disco / groove
    'Vulfpeck': 'Funk·Disco·律动', 'Louis Cole': 'Funk·Disco·律动', 'KNOWER': 'Funk·Disco·律动',
    'DOMi & JD BECK': 'Funk·Disco·律动', 'The Floozies': 'Funk·Disco·律动', 'Thundercat': 'Funk·Disco·律动',
    'Cory Wong': 'Funk·Disco·律动', 'Chromeo': 'Funk·Disco·律动', 'Tuxedo': 'Funk·Disco·律动',
    'Franc Moody': 'Funk·Disco·律动', 'Caravan Palace': 'Funk·Disco·律动',
    'Purple Disco Machine': 'Funk·Disco·律动', 'Poolside': 'Funk·Disco·律动',
    'Khruangbin': 'Funk·Disco·律动', 'Nu Genea': 'Funk·Disco·律动', 'Channel Tres': 'Funk·Disco·律动',
    'YĪN YĪN': 'Funk·Disco·律动', 'Suchmos': 'Funk·Disco·律动', 'SIRUP': 'Funk·Disco·律动',
    'FKJ': 'Funk·Disco·律动', 'Snarky Puppy': 'Funk·Disco·律动', 'Jessie Ware': 'Funk·Disco·律动',
    'The Heavy': 'Funk·Disco·律动',
    # more electronic
    'Noisia': '电子·低音与Funk', 'Skrillex': '电子·低音与Funk', 'Habstrakt': '电子·低音与Funk',
    'Knock2': '电子·低音与Funk', 'Overmono': '电子·低音与Funk', 'Four Tet': '电子·低音与Funk',
    'Boards of Canada': '电子·低音与Funk', 'Jon Hopkins': '电子·低音与Funk', 'Caribou': '电子·低音与Funk',
    'Tourist': '电子·低音与Funk', 'Jamie xx': '电子·低音与Funk', 'DJ Shadow': '电子·低音与Funk',
    'Lusine Icl': '电子·低音与Funk', 'Vilja Larjosto': '电子·低音与Funk', 'DJ Total Eclipse': '电子·低音与Funk',
    'Else': '电子·低音与Funk', 'DRIPPROJECT': '电子·低音与Funk', 'Lindequist': '电子·低音与Funk',
    'ACK': '电子·低音与Funk', 'Mapps': '电子·低音与Funk', 'Noicybino': '电子·低音与Funk',
    'The Chemical Brothers': '电子·低音与Funk', 'Massive Attack': '电子·低音与Funk',
    'Portishead': '电子·低音与Funk', 'Maribou State': '电子·低音与Funk',
    # more ambient / chill
    'Zero 7': '氛围·轻音乐', 'Electus': '氛围·轻音乐', 'Lost Sky': '氛围·轻音乐', 'Ivoris': '氛围·轻音乐',
    'Sophie Barker': '氛围·轻音乐', 'Philip Jeck': '氛围·轻音乐', '羽肿': '氛围·轻音乐',
    '灰澈': '氛围·轻音乐', '不死神乐': '氛围·轻音乐', 'Vicetone': '电子·流行',
    # more CN
    '任贤齐': '华语流行', '杨乃文': '华语流行', '郁可唯': '华语流行', '孙燕姿': '华语流行',
    '莫非定律乐团': '华语流行', 'ChiliChill乐团': '华语流行', 'Sunken Boat 沉舟乐队': '华语流行',
    '陈萝莉': '华语流行', 'Evalia': '华语流行',
    # more western rock / indie
    'Mother Mother': '摇滚·独立', 'Cage the Elephant': '摇滚·独立', 'Alt-J': '摇滚·独立',
    'NewDad': '摇滚·独立', 'toe': '摇滚·独立', '椎名林檎': '日系·独立', 'The Turtles': '摇滚·独立',
    'Billy Joel': '欧美独立·流行', 'Dominic Fike': '欧美独立·流行', 'Sia': '欧美独立·流行',
    # JP voice actors
    '茅野愛衣': '日系·动漫声优', '戸松遥': '日系·动漫声优', '早見沙織': '日系·动漫声优',
}

def genre(t):
    if is_ost(t): return '游戏与影视原声'
    for a in t['artists']:
        if a in GENRE_MAP: return GENRE_MAP[a]
    txt = ' '.join(t['artists'] + [t.get('album') or '', t.get('name') or ''])
    if re.search(r'[\u4e00-\u9fff]', txt) and re.search(r'feat', txt, re.I): return '华语流行'
    return '其他'
