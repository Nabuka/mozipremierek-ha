import urllib.request
import re
import json
import os
import html
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://mozipremierek.hu"
MAX_WORKERS = 10  # egyszerre futó adatlap-lekérések száma

MONTH_MAP = {
    "január": 1, "jan": 1, "február": 2, "feb": 2, "március": 3, "már": 3,
    "április": 4, "ápr": 4, "május": 5, "máj": 5, "június": 6, "jún": 6,
    "július": 7, "júl": 7, "augusztus": 8, "aug": 8, "szeptember": 9, "szept": 9,
    "október": 10, "okt": 10, "november": 11, "nov": 11, "december": 12, "dec": 12
}

STREAMING_MAP = [
    (["netflix"], {"name": "Netflix", "color": "#e50914"}),
    (["disney"], {"name": "Disney+", "color": "#113ccf"}),
    (["hbo", "max"], {"name": "Max", "color": "#002be7"}),
    (["skyshowtime"], {"name": "SkyShowtime", "color": "#000000"}),
    (["apple"], {"name": "Apple TV+", "color": "#333333"}),
    (["prime", "amazon"], {"name": "Prime Video", "color": "#00a8e1"}),
    (["rtl"], {"name": "RTL+", "color": "#ff4500"}),
    (["filmio"], {"name": "Filmio", "color": "#d32f2f"})
]

def clean_text(text):
    if not text:
        return ""
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def fetch_url(url):
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return ""

def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.lower().strip()
    today = datetime.now()
    now_year = today.year

    match = re.search(r'(\d{4})[\.\s]+(\d{1,2})[\.\s]+(\d{1,2})', date_str)
    if match:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date()
        
    match = re.search(r'(\d{4})[\.\s]+([a-zöőúüűáéíó]+)[\.\s]+(\d{1,2})', date_str)
    if match and match.group(2) in MONTH_MAP:
        return datetime(int(match.group(1)), MONTH_MAP[match.group(2)], int(match.group(3))).date()

    match_no_year = re.search(r'([a-zöőúüűáéíó]+)[\.\s]+(\d{1,2})', date_str)
    if match_no_year and match_no_year.group(1) in MONTH_MAP:
        month = MONTH_MAP[match_no_year.group(1)]
        year = now_year
        # Évforduló-kezelés: ha a hónap jóval korábbi, mint a mai hónap
        # (pl. decemberben egy "január" dátum), az szinte biztosan a
        # következő évre vonatkozik, nem az idei januárra.
        if month < today.month - 2:
            year += 1
        return datetime(year, month, int(match_no_year.group(2))).date()

    return None

def detect_platform_from_text(text):
    if not text:
        return None
    text_lower = text.lower()
    for keywords, provider in STREAMING_MAP:
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                return provider
    return None

def extract_spec_field(labels, html_text):
    for label in labels:
        patterns = [
            r'(?:>|\b)' + label + r'\s*[:\s]*</(?:strong|b|span|td|th|dt)>\s*<(?:dd|td|span|div)[^>]*>(.*?)</(?:dd|td|span|div)>',
            r'(?:>|\b)' + label + r'\s*[:\s]*</(?:strong|b|span|td|th|dt)>\s*([^<\n\r]+|<a[^>]*>[^<]+</a>(?:,\s*<a[^>]*>[^<]+</a>)*)',
            r'(?:>|\b)' + label + r'\s*:\s*([^<\n\r]+|<a[^>]*>[^<]+</a>(?:,\s*<a[^>]*>[^<]+</a>)*)',
        ]
        for pat in patterns:
            m = re.search(pat, html_text, re.IGNORECASE | re.DOTALL)
            if m:
                res = clean_text(re.sub(r'<[^>]+>', ' ', m.group(1)))
                if res and len(res) < 250 and not res.startswith("http"):
                    return res
    return ""

def extract_list_spec_field(labels, html_text):
    """
    Olyan mezők kinyerése, amiket az oldal <ul><li>...</li></ul> listaként
    jelenít meg a címke után, pl.:
        <strong>Rendező:</strong> <ul><li>Louis Leterrier</li></ul>
        <strong>Főszereplők:</strong> <ul><li>Név1</li><li>Név2</li></ul>
    Ezt a formátumot a régi extract_spec_field nem ismeri fel, mert az csak
    sima szöveget vagy <a> linkeket vár közvetlenül a záró </strong> után.
    """
    for label in labels:
        pattern = r'(?:>|\b)' + label + r'\s*[:\s]*</(?:strong|b|span|dt|th)>\s*<ul[^>]*>(.*?)</ul>'
        m = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if m:
            items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.IGNORECASE | re.DOTALL)
            names = [clean_text(re.sub(r'<[^>]+>', ' ', it)) for it in items]
            names = [n for n in names if n]
            if names:
                return ", ".join(names)
    return ""

def trim_boilerplate(text):
    """
    Biztonsági háló: ha egy szinopszis-jelölt véletlenül tartalmazná a
    forgalmazói/sajtójogi közleményt (pl. "Forgalmazó:", "Az oldalon közölt
    képek..."), azt levágjuk, hogy ne szennyezze be a leírást.
    """
    if not text:
        return text
    cut_markers = [
        "Forgalmazó:", "Eredeti cím:", "Gyártás éve:", "Rendező:", "Rendezők:",
        "Főszereplők:", "Az oldalon közölt képek", "közvetítésével adott engedélyt"
    ]
    cut_at = len(text)
    for marker in cut_markers:
        idx = text.find(marker)
        if idx != -1:
            cut_at = min(cut_at, idx)
    return text[:cut_at].strip()

def extract_body_synopsis(detail_html):
    """
    A teljes, nem csonkolt leírás kinyerése a részletes oldal törzséből.

    A meta description / og:description tageket a mozipremierek.hu maga is
    csonkolva adja ki (pl. "...így SZUPER" a "...így SZUPERKUTYIK" helyett),
    ezért ezekre nem lehet támaszkodni. A konkrét CSS class nevek pedig
    változhatnak / eltérhetnek oldalanként, ezért nem azokra hagyatkozunk.

    Ehelyett a film címét tartalmazó <h1> és az első specifikációs mező
    (Forgalmazó / Eredeti cím / Rendező / stb.) közötti szövegrészt vesszük,
    tag-határok mentén darabokra bontjuk, és a leghosszabb, tag nélküli
    szövegdarabot tekintjük a teljes leírásnak - ez a gyakorlatban mindig
    az összefüggő szinopszis-bekezdés, minden más elem (értékelés, futásidő,
    IMDb link) ennél jóval rövidebb.
    """
    h1_match = re.search(r'<h1[^>]*>.*?</h1>', detail_html, re.DOTALL | re.IGNORECASE)
    if not h1_match:
        return ""
    start_idx = h1_match.end()

    search_window = detail_html[start_idx:start_idx + 12000]
    spec_match = re.search(
        r'(?:>|\b)(Forgalmaz[óo]|Eredeti\s*c[íi]m|Gy[áa]rt[áa]s\s*[ée]ve|Rendez[őo][k]?|F[őo]szerepl[őo][k]?)'
        r'\s*[:\s]*</(?:strong|b|span|dt|th)>',
        search_window,
        re.IGNORECASE
    )
    end_idx = start_idx + (spec_match.start() if spec_match else min(6000, len(search_window)))

    region = detail_html[start_idx:end_idx]
    # Script/style blokkok kiszűrése, hogy ne kerüljön kód a jelöltek közé
    region = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', region, flags=re.DOTALL | re.IGNORECASE)

    # Tag-határok mentén szeletekre bontás - a leírás jellemzően egy hosszú,
    # belső tag nélküli szövegfolyam, így ez lesz a leghosszabb darab.
    blocks = re.split(r'<[^>]+>', region)
    candidates = []
    for b in blocks:
        text = clean_text(b)
        if len(text) < 60:
            continue
        low = text.lower()
        if low.startswith("http") or "imdb.com" in low:
            continue
        candidates.append(text)

    if not candidates:
        return ""
    return max(candidates, key=len)

def parse_detail_page(detail_html):
    info = {
        "genres": "",
        "runtime": "",
        "director": "",
        "cast": "",
        "synopsis": "",
        "is_streaming": False,
        "platform": None,
        "hd_poster": None,
        "trailer_url": None
    }

    if not detail_html:
        return info

    synopsis_candidates = []
    ld_genre = ld_runtime = ld_director = ld_cast = ""

    # 1. JSON-LD strukturált adatok próbálkozása - csak jelöltként tároljuk,
    #    mert némely filmnél hiányos vagy hiányzik, ezért nem hagyatkozunk
    #    kizárólag erre.
    json_ld_matches = re.findall(r'<script\s+type=["\']application/ld\+json["\']>(.*?)</script>', detail_html, re.DOTALL | re.IGNORECASE)
    for ld_raw in json_ld_matches:
        try:
            ld = json.loads(ld_raw.strip())
            if isinstance(ld, list):
                ld = ld[0]
            if isinstance(ld, dict) and ld.get('@type') in ['Movie', 'TVSeries', 'ItemPage']:
                if 'genre' in ld:
                    g = ld['genre']
                    ld_genre = ", ".join(g) if isinstance(g, list) else str(g)
                if 'duration' in ld:
                    dur = str(ld['duration'])
                    m_dur = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?', dur)
                    if m_dur:
                        h = int(m_dur.group(1) or 0)
                        m = int(m_dur.group(2) or 0)
                        tot = h * 60 + m
                        if tot > 0:
                            ld_runtime = f"{tot} perc"
                    else:
                        ld_runtime = dur
                if 'director' in ld:
                    d = ld['director']
                    if isinstance(d, list):
                        ld_director = ", ".join([x.get('name', '') for x in d if isinstance(x, dict)])
                    elif isinstance(d, dict):
                        ld_director = d.get('name', '')
                    elif isinstance(d, str):
                        ld_director = d
                if 'actor' in ld:
                    a = ld['actor']
                    if isinstance(a, list):
                        ld_cast = ", ".join([x.get('name', '') for x in a if isinstance(x, dict)][:5])
                    elif isinstance(a, dict):
                        ld_cast = a.get('name', '')
                if 'description' in ld:
                    # A JSON-LD description néha ugyanaz a csonkolt szöveg, mint
                    # a meta tag - ezért csak jelöltként vesszük fel, nem
                    # fogadjuk el automatikusan véglegesnek.
                    synopsis_candidates.append(clean_text(ld['description']))
        except Exception:
            pass

    # 2. YouTube előzetes és HD Poszter
    yt_match = re.search(r'data-video-id="([a-zA-Z0-9_-]+)"', detail_html)
    if yt_match:
        info["trailer_url"] = f"https://www.youtube.com/watch?v={yt_match.group(1)}"

    hd_poster_match = re.search(r'href="(https://media\.mozipremierek\.hu/poster/[^"]+\.webp)"', detail_html)
    if hd_poster_match:
        info["hd_poster"] = hd_poster_match.group(1)

    # 3. Műfajok - a lap alján lévő "movie-category" cimkékből. Ez mindig
    #    jelen van a HTML-ben, függetlenül attól, hogy a JSON-LD tartalmaz-e
    #    "genre" mezőt (ami néhány filmnél hiányzik).
    genre_tags = re.findall(r'<a\s+class="movie-category"[^>]*>(.*?)</a>', detail_html, re.IGNORECASE | re.DOTALL)
    if genre_tags:
        names, seen = [], set()
        for g in genre_tags:
            name = clean_text(re.sub(r'<[^>]+>', ' ', g))
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
        info["genres"] = ", ".join(names)
    if not info["genres"]:
        info["genres"] = ld_genre or extract_spec_field([r'Műfajok?', r'Kategória', r'Műfaj\(ok\)'], detail_html)

    # 4. Játékidő - közvetlenül a "movie-runtime" span-ból (pl. <span
    #    class="movie-runtime">110 perc</span>), ami szintén mindig jelen
    #    van, szemben a "Hossz:"/"Játékidő:" felirattal, ami nem létezik
    #    az oldal HTML-jében.
    runtime_match = re.search(r'<span[^>]*class="movie-runtime"[^>]*>(.*?)</span>', detail_html, re.IGNORECASE | re.DOTALL)
    if runtime_match:
        info["runtime"] = clean_text(re.sub(r'<[^>]+>', ' ', runtime_match.group(1)))
    if not info["runtime"]:
        info["runtime"] = ld_runtime or extract_spec_field([r'Hossz', r'Játékidő', r'Műsoridő', r'Invervallum'], detail_html)
        if info["runtime"] and "perc" not in info["runtime"].lower() and info["runtime"].isdigit():
            info["runtime"] += " perc"

    # 5. Rendező és Főszereplők - ezeket az oldal <ul><li> listaként adja meg
    #    a címke után (<strong>Rendező:</strong><ul><li>Név</li></ul>), amit
    #    a régi extract_spec_field nem ismer fel.
    info["director"] = (
        extract_list_spec_field([r'Rendezők?', r'Rendezte', r'Rendező\(k\)'], detail_html)
        or ld_director
        or extract_spec_field([r'Rendezők?', r'Rendezte', r'Rendező\(k\)'], detail_html)
    )
    info["cast"] = (
        extract_list_spec_field([r'Szereplők?', r'Főszereplők?', r'Színészek', r'Szereplőgárda'], detail_html)
        or ld_cast
        or extract_spec_field([r'Szereplők?', r'Főszereplők?', r'Színészek', r'Szereplőgárda'], detail_html)
    )

    # 6. Tartalom (leírás) kinyerése - a legteljesebb, leghosszabb változat
    #    kiválasztása. Szándékosan NEM használunk class/id substring alapú
    #    keresést (pl. "*plot*"), mert az a "movie-v2-plot" wrapper divet is
    #    elkaphatja, ami a Forgalmazó/sajtójogi szöveget is tartalmazza.
    body_synopsis = extract_body_synopsis(detail_html)
    if body_synopsis:
        synopsis_candidates.append(body_synopsis)

    # Meta description - utolsó, tartalék lehetőség, mert ez tudottan
    # csonkolt szöveget tartalmaz az oldalon.
    meta_desc = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', detail_html, re.IGNORECASE)
    if meta_desc:
        synopsis_candidates.append(clean_text(meta_desc.group(1)))

    synopsis_candidates = [trim_boilerplate(c) for c in synopsis_candidates]
    synopsis_candidates = [c for c in synopsis_candidates if c]
    if synopsis_candidates:
        # A leghosszabb jelölt szinte biztosan a teljes, csonkolatlan leírás -
        # a csonkolt meta verzió csak akkor nyer, ha nincs más jelölt.
        info["synopsis"] = max(synopsis_candidates, key=len)

    # 7. Platform szűrés az adatlapról
    distrib_match = re.search(r'(?:Forgalmazó|Megjelenés|Platform)[^:]*:\s*([^<>\n\r]+|<[^>]+>[^<]+</[^>]+>)', detail_html, re.IGNORECASE)
    if distrib_match:
        dist_text = clean_text(re.sub(r'<[^>]+>', ' ', distrib_match.group(1)))
        platform = detect_platform_from_text(dist_text)
        if platform:
            info["is_streaming"] = True
            info["platform"] = platform

    return info

def build_pending_item(rel_url, block):
    """
    A film listaoldali blokkjából kinyeri az adatlap-lekérés ELŐTT elérhető
    adatokat (cím, poszter, dátum, a listából detektált platform). Ez a
    lépés nem igényel hálózati hívást, ezért gyors és szálbiztos módon
    végezhető el a párhuzamosítás előtt.
    """
    detail_url = BASE_URL + rel_url

    title_match = re.search(r'<strong class=[\'"]item-title[\'"]>(.*?)</strong>', block, re.DOTALL)
    title = clean_text(title_match.group(1)) if title_match else "Ismeretlen cím"

    poster_match = re.search(r'<img [^>]*class="poster-view-img"[^>]*src="([^"]+)"', block)
    poster = poster_match.group(1) if poster_match else ""
    if poster:
        poster = re.sub(r'\.small\.webp$', '.thumb.webp', poster)

    clean_block = re.sub(r'<span class="distributor[^"]*">.*?</span>', '', block, flags=re.DOTALL)
    date_match = re.search(r'<span class="premier-date[^"]*">(.*?)</span>', clean_block, re.DOTALL)
    date_text = clean_text(re.sub(r'<[^>]+>', '', date_match.group(1))) if date_match else ""
    movie_date = parse_date(date_text)

    block_clean_text = clean_text(re.sub(r'<[^>]+>', ' ', block))
    platform_from_list = detect_platform_from_text(block_clean_text)

    return {
        "title": title,
        "poster": poster,
        "date_text": date_text,
        "movie_date": movie_date,
        "detail_url": detail_url,
        "platform_from_list": platform_from_list,
    }

def fetch_movie_detail(pending):
    """
    Egy film adatlapjának letöltése és feldolgozása. Ez a lépés végzi a
    hálózati I/O-t, ezért ezt futtatjuk párhuzamosan, szálanként egy-egy
    filmre - a bemenete és a kimenete is önálló, más szálakkal nem oszt meg
    állapotot, így biztonságosan hívható egyszerre több szálból.
    """
    detail_info = {}
    if pending["detail_url"]:
        detail_html = fetch_url(pending["detail_url"])
        detail_info = parse_detail_page(detail_html)

    poster = pending["poster"]
    if detail_info.get("hd_poster"):
        poster = detail_info["hd_poster"]

    platform = pending["platform_from_list"] or detail_info.get("platform")
    is_streaming = platform is not None

    item = {
        "title": pending["title"],
        "date": pending["date_text"],
        "poster": poster,
        "detail_url": pending["detail_url"],
        "trailer_url": detail_info.get("trailer_url"),
        "is_streaming": is_streaming,
        "platform": platform,
        "genres": detail_info.get("genres", ""),
        "runtime": detail_info.get("runtime", ""),
        "director": detail_info.get("director", ""),
        "cast": detail_info.get("cast", ""),
        "synopsis": detail_info.get("synopsis", "")
    }
    return pending["movie_date"], item

def get_movies():
    main_html = fetch_url(BASE_URL)
    if not main_html:
        return {"cinema_current": [], "streaming_current": [], "cinema_past": []}

    movie_blocks = re.findall(r'<a\s+href="(/movie/[^"]+)"[^>]*class="movie"[^>]*>(.*?)</a>', main_html, re.DOTALL)

    today = datetime.now().date()
    start_this_week = today - timedelta(days=today.weekday())
    end_next_week = start_this_week + timedelta(days=13)
    three_weeks_ago = start_this_week - timedelta(days=21)

    # 1. lépés: a listaoldal feldolgozása és a duplikátumok kiszűrése -
    # ehhez nem kell hálózati hívás, ezért soros ciklusban marad.
    seen_keys = set()
    pending_items = []
    for rel_url, block in movie_blocks:
        detail_url = BASE_URL + rel_url

        # Duplikáció kiszűrése kizárólag a detail_url alapján. A cím alapú
        # szűrés korábban tévesen kiszűrte volna azt az esetet, amikor egy
        # remake ugyanazt a címet viseli, mint az eredeti film (pl. "The
        # Karate Kid" 1984 és 2010) - ilyenkor a két film detail_url-je
        # egyértelműen különbözik (egyedi azonosítót tartalmaz), így ez
        # önmagában is megbízhatóan megkülönbözteti őket. Ha ugyanaz a film
        # kétszer szerepel a főoldalon (pl. több szekcióban is), annak
        # detail_url-je mindkétszer azonos, tehát ez a duplikátumokat is
        # helyesen kiszűri.
        if detail_url in seen_keys:
            continue
        seen_keys.add(detail_url)

        pending_items.append(build_pending_item(rel_url, block))

    # 2. lépés: az adatlapok párhuzamos letöltése és feldolgozása - ez a
    # hálózat-igényes rész, ezért ezt osztjuk szét szálak között. A
    # as_completed() a szálak befejezési sorrendjében adja vissza az
    # eredményeket, ami futtatásonként változhat, ezért a végén dátum
    # szerint rendezzük a listákat, hogy a kimenet sorrendje stabil maradjon.
    cinema_current = []
    streaming_current = []
    cinema_past = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_movie_detail, pending) for pending in pending_items]
        for future in as_completed(futures):
            movie_date, item = future.result()

            if not movie_date:
                continue
            if start_this_week <= movie_date <= end_next_week:
                if item["is_streaming"]:
                    streaming_current.append((movie_date, item))
                else:
                    cinema_current.append((movie_date, item))
            elif three_weeks_ago <= movie_date < start_this_week:
                if not item["is_streaming"]:
                    cinema_past.append((movie_date, item))

    cinema_current.sort(key=lambda pair: pair[0])
    streaming_current.sort(key=lambda pair: pair[0])
    cinema_past.sort(key=lambda pair: pair[0])

    return {
        "cinema_current": [item for _, item in cinema_current],
        "streaming_current": [item for _, item in streaming_current],
        "cinema_past": [item for _, item in cinema_past]
    }

if __name__ == "__main__":
    print("Scraper indítása adatlap-feldolgozással és duplikáció szűréssel...")
    movie_data = get_movies()
    target_dir = "/config/www"
    os.makedirs(target_dir, exist_ok=True)
    output_path = os.path.join(target_dir, "mozipremierek.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(movie_data, f, ensure_ascii=False, indent=2)
    print("Sikeres mentés!")
