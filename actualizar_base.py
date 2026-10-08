#!/usr/bin/env python3
"""
CornerEdge · actualizador de la base de equipos
================================================
Descarga los resultados con córners de football-data.co.uk (LaLiga, Hypermotion, Premier, Serie A, Bundesliga, Ligue 1, Portugal, Championship, 2. Bundesliga, Eredivisie, Bélgica, Escocia),
recalcula la base ataque×defensa con el mismo método con el que se estimó el modelo (v33) y
reescribe el bloque de datos dentro del HTML de la app.

Uso:
    python3 actualizar_base.py CornerEdge_v33.html
    python3 actualizar_base.py CornerEdge_v33.html --temporada 2627 --previa 2526

Genera:  <nombre>_base-AAAA-MM-DD.html   (el original no se toca)
Requisitos: Python 3.8+ sin librerías externas.

v51 · Además guarda el DIBUJO de los últimos 3 partidos de liga de cada equipo (Flashscore), para que la app
marque sola «tres centrales con tres arriba». Si Flashscore falla, se conserva lo que hubiera: la base se actualiza igual.

v52 · Además guarda los PRÓXIMOS PARTIDOS de cada liga (9 días) con la cuota 1X2 de Bet365 que publica Flashscore y la
previsión de lluvia y temperatura a la hora del partido (Open-Meteo), para que en la app sólo haya que teclear la línea
y las cuotas de córners. Si algo falla, se conserva lo anterior.

Método (idéntico a la estimación):
  · a favor / concedidos en casa y fuera por equipo, temporada en curso
  · prior = temporada previa del mismo equipo en la misma liga (6 partidos) si jugó ≥5 como local/visitante;
    si no (ascendido, descendido, filial nuevo…) → media de liga (3 partidos)
  · medias de liga = temporada en curso con prior de la previa (150 partidos)
  · goles medios de liga (para la cadena del marcador cuando no hay 1X2) = temporada en curso + previa
"""
import csv, io, json, re, sys, urllib.request, datetime as dt, argparse, statistics as st, shutil, os

K_PREV, K_LG, K_LEAGUE = 6, 3, 150
# (código football-data, sufijo en la app, nº de equipos esperado)
LEAGUES = [('SP1', 'LL', 20), ('SP2', 'S2', 22), ('E0', 'E0', 20), ('I1', 'I1', 20), ('D1', 'D1', 18),
           ('F1', 'F1', 18), ('P1', 'P1', 18), ('E1', 'E1', 24), ('D2', 'D2', 18), ('N1', 'N1', 18), ('B1', 'B1', 18), ('SC0', 'SC0', 12)]
URL = 'https://www.football-data.co.uk/mmz4281/{season}/{league}.csv'


def season_code(today=None):
    d = today or dt.date.today()
    a = d.year if d.month >= 7 else d.year - 1
    return f'{a % 100:02d}{(a + 1) % 100:02d}', f'{(a - 1) % 100:02d}{a % 100:02d}'


def download(season, league):
    url = URL.format(season=season, league=league)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 CornerEdge-updater'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode('utf-8-sig', errors='replace')
    rows = []
    for x in csv.DictReader(io.StringIO(raw)):
        if not x.get('HomeTeam') or not x.get('HC') or not x.get('AC'):
            continue
        try:
            hc, ac = int(x['HC']), int(x['AC'])
            fmt = '%d/%m/%Y' if len(x['Date'].split('/')[-1]) == 4 else '%d/%m/%y'
            day = dt.datetime.strptime(x['Date'], fmt).date()
            hg, ag = int(x['FTHG']), int(x['FTAG'])
        except (ValueError, KeyError):
            continue
        rows.append(dict(h=x['HomeTeam'].strip(), a=x['AwayTeam'].strip(), hc=hc, ac=ac, hg=hg, ag=ag, day=day))
    return rows


def aggregate(rows):
    agg = {}
    for r in rows:
        H = agg.setdefault(r['h'], [0, 0, 0, 0, 0, 0])  # hf, haf, nh, vf, vaf, na
        A = agg.setdefault(r['a'], [0, 0, 0, 0, 0, 0])
        H[0] += r['hc']; H[1] += r['ac']; H[2] += 1
        A[3] += r['ac']; A[4] += r['hc']; A[5] += 1
    return agg


def build(cur, prev):
    if not cur:
        raise SystemExit('La temporada en curso no tiene partidos con córners todavía.')
    C, P = aggregate(cur), aggregate(prev)
    mh, ma = st.mean(r['hc'] for r in cur), st.mean(r['ac'] for r in cur)
    if prev:
        mh_p, ma_p = st.mean(r['hc'] for r in prev), st.mean(r['ac'] for r in prev)
    else:
        mh_p, ma_p = mh, ma
    n = len(cur); w = n / (n + K_LEAGUE)
    LH, LA = w * mh + (1 - w) * mh_p, w * ma + (1 - w) * ma_p
    db = {}
    for t in sorted(C):
        c, p = C[t], P.get(t)
        def est(s, n_, ps, pn, lgm):
            if p and pn >= 5:
                return (s + K_PREV * ps / pn) / (n_ + K_PREV)
            return (s + K_LG * lgm) / (n_ + K_LG)
        hf  = est(c[0], c[2], p[0] if p else 0, p[2] if p else 0, LH)
        haf = est(c[1], c[2], p[1] if p else 0, p[2] if p else 0, LA)
        vf  = est(c[3], c[5], p[3] if p else 0, p[5] if p else 0, LA)
        vaf = est(c[4], c[5], p[4] if p else 0, p[5] if p else 0, LH)
        prior = int(bool(p and p[2] >= 5 and p[5] >= 5))
        db[t] = [round(hf, 3), round(haf, 3), round(vf, 3), round(vaf, 3), c[2], c[5], prior]
    allg = cur + prev
    goals = [round(st.mean(r['hg'] for r in allg), 3), round(st.mean(r['ag'] for r in allg), 3)]
    return dict(db=db, lg=dict(hf=round(LH, 3), vf=round(LA, 3)), goals=goals, n=n,
                last=max(r['day'] for r in cur).isoformat(), raw_mean=round(mh + ma, 2),
                prev_mean=round(mh_p + ma_p, 2) if prev else None)


def validate(name, res, expected_teams):
    errs = []
    nt = len(res['db'])
    if nt != expected_teams:
        errs.append(f'{name}: {nt} equipos (se esperaban {expected_teams})')
    tot = res['lg']['hf'] + res['lg']['vf']
    if not 7.0 <= tot <= 12.0:
        errs.append(f'{name}: media de liga {tot:.2f} fuera de rango razonable')
    for t, v in res['db'].items():
        if not all(1.0 <= x <= 12.0 for x in v[:4]):
            errs.append(f'{name}: valores anómalos para {t}: {v[:4]}')
    if not all(0.5 <= g <= 3.0 for g in res['goals']):
        errs.append(f'{name}: goles medios anómalos {res["goals"]}')
    return errs


def js_block(R):
    def rows(lg):
        return ',\n'.join(f'  {json.dumps(t, ensure_ascii=False)}: {json.dumps(v)}' for t, v in R[lg]['db'].items())
    last = max(R[fd]['last'] for fd, _, _ in LEAGUES)
    out = (f"// Base de equipos generada desde football-data.co.uk (córners oficiales), hasta {last}.\n"
           "// [a favor casa, concedidos casa, a favor fuera, concedidos fuera, PJ casa, PJ fuera, prior temporada previa (1/0)]\n"
           "// Temporada en curso + temporada previa del mismo equipo en la misma liga como prior (6 partidos); sin previa → media de liga (3).\n")
    for fd, sfx, _ in LEAGUES:
        out += f"const DB_{sfx} = {{\n{rows(fd)}\n}};\n"
    for fd, sfx, _ in LEAGUES:
        out += f"const LG_{sfx} = {json.dumps(R[fd]['lg'])}, GOALS_{sfx} = {json.dumps(R[fd]['goals'])};\n"
    out += f"const DB_DATE = '{last}';\n"
    return out, last


BLOCK_RE = re.compile(r"// Base de equipos generada desde football-data\.co\.uk.*?\nconst DB_DATE = '[^']*';\n", re.S)

# ─────────────────────────────────────────────────────────────────────────────
# v51 · DIBUJOS RECIENTES (Flashscore)
# ─────────────────────────────────────────────────────────────────────────────
FS_SLUG = {'SP1': 'espana/laliga', 'SP2': 'espana/laliga-hypermotion', 'E0': 'inglaterra/premier-league', 'I1': 'italia/serie-a',
           'D1': 'alemania/bundesliga', 'F1': 'francia/ligue-1', 'P1': 'portugal/liga-portugal', 'E1': 'inglaterra/championship',
           'D2': 'alemania/2-bundesliga', 'N1': 'paises-bajos/eredivisie', 'B1': 'belgica/jupiler-pro-league', 'SC0': 'escocia/premiership'}
APP_KEY = {'SP1': 'll', 'SP2': 's2'}          # el resto usa el mismo código que football-data
FS_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
FORM_RE = re.compile(r"// Dibujos recientes \(Flashscore\).*?\nconst FORM_DATE = '[^']*';\n", re.S)
N_FORM = 3


def fs_get(url, feed=False):
    h = {'User-Agent': FS_UA}
    if feed:
        h['x-fsign'] = 'SW9D1eZo'
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:      # noqa
            last = e
    raise last


def fs_results(slug):
    """Partidos terminados de la temporada en curso (los ~100 más recientes): id, día, equipos y marcador."""
    html = fs_get(f'https://www.flashscore.es/futbol/{slug}/resultados/')
    out, seen = [], set()
    for m in re.finditer(r'~AA÷([A-Za-z0-9]{8})¬AD÷(\d+)(.*?)(?=~AA÷|~ZA÷|$)', html, re.S):
        if m.group(1) in seen:        # la página repite los partidos más recientes
            continue
        seen.add(m.group(1))
        rest = m.group(3)
        g = lambda k: (re.search('¬' + k + r'÷([^¬]*)', rest) or [None, None])[1]
        try:
            hg, ag = int(g('AG')), int(g('AH'))
        except (TypeError, ValueError):
            continue
        if g('AB') != '3' or not g('AE') or not g('AF'):
            continue
        ts = int(m.group(2))
        out.append(dict(id=m.group(1), ts=ts, day=dt.datetime.utcfromtimestamp(ts).date(), h=g('AE'), a=g('AF'), hg=hg, ag=ag))
    return out


def fs_formations(mid):
    """Dibujo de salida de local y visitante, sin el portero ('3-4-2-1'), o None."""
    li = fs_get(f'https://global.flashscore.ninja/2/x/feed/df_li_1_{mid}', feed=True)
    side = sec = None
    form = {}
    for blk in li.split('~'):
        d = dict(x.split('÷', 1) for x in blk.split('¬') if '÷' in x)
        if 'LB' in d: sec = d['LB']
        if 'LC' in d: side = d['LC']
        if 'LD' in d and sec == 'Starting Lineups' and side in ('1', '2'):
            form.setdefault(side, re.sub(r'^1-', '', d['LD']))
    return form.get('1'), form.get('2')


def build_forms(lg, cur):
    """{equipo (nombre football-data): [dibujos de sus últimos 3 partidos de liga, del más antiguo al más reciente]}"""
    from concurrent.futures import ThreadPoolExecutor
    fs = fs_results(FS_SLUG[lg])
    if not fs:
        raise RuntimeError('Flashscore no devuelve partidos')
    # nombres Flashscore → football-data: partidos con día (±1) y marcador únicos votan la equivalencia
    idx = {}
    for r in cur:
        idx.setdefault((r['hg'], r['ag']), []).append(r)
    cand = {m['id']: [r for r in idx.get((m['hg'], m['ag']), []) if abs((r['day'] - m['day']).days) <= 1] for m in fs}
    nm = {}
    for _ in range(4):            # 1ª vuelta: coincidencias únicas; siguientes: se descartan candidatos incompatibles con lo ya sabido
        vote, used = {}, set(nm.values())
        for m in fs:
            c = [r for r in cand[m['id']]
                 if nm.get(m['h'], r['h']) == r['h'] and nm.get(m['a'], r['a']) == r['a']
                 and (m['h'] in nm or r['h'] not in used) and (m['a'] in nm or r['a'] not in used)]
            if len(c) == 1:
                vote.setdefault(m['h'], {}).setdefault(c[0]['h'], 0); vote[m['h']][c[0]['h']] += 1
                vote.setdefault(m['a'], {}).setdefault(c[0]['a'], 0); vote[m['a']][c[0]['a']] += 1
        new = {k: max(v, key=v.get) for k, v in vote.items()}
        if new == nm:
            break
        nm = new
    per = {}
    for m in sorted(fs, key=lambda x: x['ts']):
        for side, name in ((0, m['h']), (1, m['a'])):
            if name in nm:
                per.setdefault(nm[name], []).append((m['id'], side))
    need = sorted({mid for L in per.values() for mid, _ in L[-N_FORM:]})
    with ThreadPoolExecutor(8) as ex:
        got = dict(zip(need, ex.map(lambda i: _safe(fs_formations, i), need)))
    res = {}
    for t, L in per.items():
        fl = [got[mid][side] for mid, side in L[-N_FORM:] if got.get(mid) and got[mid][side]]
        if fl:
            res[t] = fl
    NM[lg] = nm
    return res


NM = {}          # liga → {nombre Flashscore: nombre football-data}, lo rellena build_forms


def _safe(f, *a):
    try:
        return f(*a)
    except Exception:
        return None


def forms_block(html, R, cur_rows):
    """Devuelve el bloque JS de dibujos, conservando por liga lo anterior si Flashscore falla."""
    m = FORM_RE.search(html)
    if not m:
        return None, None
    old = {}
    g = re.search(r'const FORM_DB = (\{.*?\});\n', m.group(0), re.S)
    if g:
        try: old = json.loads(g.group(1))
        except Exception: old = {}
    new, fresh = {}, 0
    for lg, _sfx, _n in LEAGUES:
        key = APP_KEY.get(lg, lg)
        try:
            f = build_forms(lg, cur_rows[lg])
            teams = set(R[lg]['db'])
            f = {t: v for t, v in f.items() if t in teams}
            if len(f) < 0.7 * len(teams):
                raise RuntimeError(f'sólo {len(f)}/{len(teams)} equipos identificados')
            new[key] = dict(sorted(f.items())); fresh += 1
            print(f'  dibujos {lg}: {len(f)}/{len(teams)} equipos')
        except Exception as e:
            new[key] = old.get(key, {})
            print(f'  aviso: dibujos de {lg} no actualizados ({e}); se conservan los anteriores ({len(new[key])} equipos)')
    date = dt.date.today().isoformat() if fresh else (re.search(r"const FORM_DATE = '([^']*)'", m.group(0)).group(1))
    body = ',\n'.join(f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}' for k, v in new.items())
    block = ("// Dibujos recientes (Flashscore): últimos 3 partidos de liga de cada equipo, del más antiguo al más reciente.\n"
             f"const FORM_DB = {{\n{body}\n}};\nconst FORM_DATE = '{date}';\n")
    return block, m

# ─────────────────────────────────────────────────────────────────────────────
# v52 · PRÓXIMOS PARTIDOS: 1X2 de Bet365 (Flashscore) y previsión del tiempo (Open-Meteo)
# ─────────────────────────────────────────────────────────────────────────────
JOR_RE = re.compile(r"// Próximos partidos \(Flashscore\).*?\nconst JOR_TS = \d+;\n", re.S)
JOR_DIAS = 9
FS_ODDS = 'https://global.ds.lsapp.eu/odds/pq_graphql?_hash=oce&projectId=13&geoIpCode=ES&geoIpSubdivisionCode=ES&eventId='
# Coordenadas del estadio de cada equipo (nombre football-data). Equipo nuevo sin coordenadas → sin previsión (la app lo dice).
COORDS = {"SP1":{"Alaves":[42.85,-2.673],"Ath Bilbao":[43.263,-2.925],"Ath Madrid":[40.416,-3.703],"Barcelona":[41.389,2.159],"Betis":[37.383,-5.973],"Celta":[42.233,-8.723],"Elche":[38.262,-0.701],"Espanol":[41.35,2.083],"Getafe":[40.306,-3.733],"La Coruna":[43.371,-8.396],"Levante":[39.474,-0.38],"Malaga":[36.72,-4.42],"Osasuna":[42.817,-1.643],"Real Madrid":[40.416,-3.703],"Santander":[43.466,-3.805],"Sevilla":[37.383,-5.973],"Sociedad":[43.301,-1.974],"Valencia":[39.474,-0.38],"Vallecano":[40.327,-3.764],"Villarreal":[39.944,-0.103]},
          "SP2":{"Albacete":[38.994,-1.856],"Almeria":[36.838,-2.46],"Andorra":[42.535,1.58],"Burgos":[42.341,-3.702],"Cadiz":[36.527,-6.289],"Castellon":[39.999,0.026],"Celta B":[42.233,-8.723],"Ceuta":[35.889,-5.32],"Cordoba":[37.892,-4.773],"Eibar":[43.185,-2.472],"Eldense":[38.478,-0.792],"Girona":[41.983,2.825],"Granada":[37.188,-3.607],"Las Palmas":[28.102,-15.416],"Leganes":[40.327,-3.764],"Mallorca":[39.55,2.733],"Oviedo":[43.36,-5.845],"Sabadell":[41.543,2.109],"Sociedad B":[43.301,-1.974],"Sp Gijon":[43.536,-5.662],"Tenerife":[28.468,-16.255],"Valladolid":[41.655,-4.724]},
          "E0":{"Arsenal":[51.509,-0.126],"Aston Villa":[52.481,-1.9],"Bournemouth":[50.72,-1.879],"Brentford":[51.509,-0.126],"Brighton":[50.828,-0.139],"Chelsea":[51.509,-0.126],"Coventry":[52.407,-1.512],"Crystal Palace":[51.509,-0.126],"Everton":[53.411,-2.978],"Fulham":[51.509,-0.126],"Hull":[53.745,-0.335],"Ipswich":[52.059,1.155],"Leeds":[53.796,-1.548],"Liverpool":[53.411,-2.978],"Man City":[53.481,-2.237],"Man United":[53.481,-2.237],"Newcastle":[54.975,-1.622],"Nott'm Forest":[52.954,-1.15],"Sunderland":[54.905,-1.382],"Tottenham":[51.509,-0.126]},
          "I1":{"Atalanta":[45.696,9.667],"Bologna":[44.494,11.339],"Cagliari":[39.231,9.119],"Como":[45.808,9.083],"Fiorentina":[43.779,11.246],"Frosinone":[41.64,13.341],"Genoa":[44.405,8.944],"Inter":[45.464,9.19],"Juventus":[45.07,7.687],"Lazio":[41.892,12.511],"Lecce":[40.355,18.172],"Milan":[45.464,9.19],"Monza":[45.58,9.272],"Napoli":[40.852,14.268],"Parma":[44.799,10.326],"Roma":[41.892,12.511],"Sassuolo":[44.698,10.631],"Torino":[45.07,7.687],"Udinese":[46.069,13.237],"Venezia":[45.437,12.333]},
          "D1":{"Augsburg":[48.372,10.899],"Bayern Munich":[48.137,11.575],"Dortmund":[51.515,7.466],"Ein Frankfurt":[50.116,8.684],"Elversberg":[49.317,7.133],"FC Koln":[50.933,6.95],"Freiburg":[47.996,7.852],"Hamburg":[53.551,9.993],"Hoffenheim":[49.253,8.879],"Leverkusen":[51.03,6.984],"M'gladbach":[51.185,6.442],"Mainz":[49.982,8.28],"Paderborn":[51.719,8.754],"RB Leipzig":[51.34,12.371],"Schalke 04":[51.505,7.097],"Stuttgart":[48.782,9.177],"Union Berlin":[52.524,13.411],"Werder Bremen":[53.076,8.807]},
          "F1":{"Angers":[47.472,-0.552],"Auxerre":[47.8,3.57],"Brest":[48.39,-4.486],"Le Havre":[49.493,0.108],"Le Mans":[48.002,0.203],"Lens":[50.433,2.828],"Lille":[50.623,3.145],"Lorient":[47.748,-3.372],"Lyon":[45.749,4.848],"Marseille":[43.297,5.381],"Monaco":[43.731,7.419],"Nice":[43.703,7.266],"Paris FC":[48.853,2.349],"Paris SG":[48.853,2.349],"Rennes":[48.111,-1.674],"Strasbourg":[48.584,7.746],"Toulouse":[43.604,1.444],"Troyes":[48.301,4.085]},
          "P1":{"Academico Viseu":[40.662,-7.909],"Alverca":[38.899,-9.039],"Arouca":[40.931,-8.245],"Benfica":[38.725,-9.15],"Casa Pia":[39.337,-8.939],"Estoril":[38.706,-9.398],"Estrela":[38.754,-9.231],"Famalicao":[41.408,-8.52],"Gil Vicente":[41.532,-8.618],"Guimaraes":[41.444,-8.296],"Maritimo":[32.666,-16.925],"Moreirense":[41.387,-8.339],"Nacional":[32.666,-16.925],"Porto":[41.148,-8.611],"Rio Ave":[41.353,-8.745],"Santa Clara":[37.74,-25.669],"Sp Braga":[41.551,-8.423],"Sp Lisbon":[38.725,-9.15]},
          "E1":{"Birmingham":[52.481,-1.9],"Blackburn":[53.75,-2.483],"Bolton":[53.583,-2.433],"Bristol City":[51.455,-2.597],"Burnley":[53.8,-2.233],"Cardiff":[51.48,-3.18],"Charlton":[51.509,-0.126],"Derby":[52.923,-1.477],"Lincoln":[53.227,-0.538],"Middlesbrough":[54.576,-1.235],"Millwall":[51.509,-0.126],"Norwich":[52.628,1.298],"Portsmouth":[50.799,-1.091],"Preston":[53.763,-2.705],"QPR":[51.509,-0.126],"Sheffield United":[53.383,-1.466],"Southampton":[50.904,-1.404],"Stoke":[53.003,-2.179],"Swansea":[51.621,-3.943],"Watford":[51.655,-0.396],"West Brom":[52.519,-1.994],"West Ham":[51.509,-0.126],"Wolves":[52.585,-2.123],"Wrexham":[53.047,-2.991]},
          "D2":{"Bielefeld":[52.033,8.533],"Bochum":[51.482,7.216],"Braunschweig":[52.266,10.527],"Cottbus":[51.758,14.329],"Darmstadt":[49.872,8.65],"Dresden":[51.051,13.738],"Greuther Furth":[49.476,10.989],"Hannover":[52.371,9.733],"Heidenheim":[48.678,10.152],"Hertha":[52.524,13.411],"Holstein Kiel":[54.321,10.135],"Kaiserslautern":[49.443,7.772],"Karlsruhe":[49.009,8.404],"Magdeburg":[52.131,11.632],"Nurnberg":[49.454,11.078],"Osnabruck":[52.273,8.05],"St Pauli":[53.551,9.993],"Wolfsburg":[52.425,10.781]},
          "N1":{"AZ Alkmaar":[52.632,4.749],"Ajax":[52.374,4.89],"Cambuur":[53.203,5.81],"Den Haag":[52.078,4.289],"Excelsior":[51.922,4.479],"Feyenoord":[51.922,4.479],"For Sittard":[50.998,5.869],"Go Ahead Eagles":[52.255,6.164],"Groningen":[53.219,6.567],"Heerenveen":[52.959,5.919],"Nijmegen":[51.843,5.853],"PSV Eindhoven":[51.441,5.478],"Sparta Rotterdam":[51.922,4.479],"Telstar":[52.46,4.65],"Twente":[52.218,6.896],"Utrecht":[52.091,5.122],"Willem II":[51.556,5.091],"Zwolle":[52.513,6.094]},
          "B1":{"Anderlecht":[50.836,4.315],"Antwerp":[51.221,4.466],"Beveren":[51.212,4.256],"Cercle Brugge":[51.209,3.224],"Charleroi":[50.411,4.444],"Club Brugge":[51.209,3.224],"Genk":[50.965,5.501],"Gent":[51.05,3.717],"Kortrijk":[50.828,3.265],"Lommel SK":[51.231,5.313],"Mechelen":[51.026,4.478],"Oud-Heverlee Leuven":[50.864,4.696],"RAAL La Louviere":[50.487,4.188],"St Truiden":[50.817,5.186],"St. Gilloise":[50.85,4.349],"Standard":[50.634,5.567],"Waregem":[50.889,3.428],"Westerlo":[51.09,4.915]},
          "SC0":{"Aberdeen":[57.144,-2.098],"Celtic":[55.865,-4.258],"Dundee":[56.469,-2.975],"Dundee United":[56.469,-2.975],"Falkirk":[56.002,-3.785],"Hearts":[55.952,-3.196],"Hibernian":[55.952,-3.196],"Kilmarnock":[55.612,-4.496],"Motherwell":[55.789,-3.992],"Rangers":[55.865,-4.258],"St Johnstone":[56.395,-3.431],"St Mirren":[55.832,-4.433]}}


def fs_fixtures(slug):
    """Partidos por jugar de la temporada en curso: id, hora (UTC), equipos y sus identificadores."""
    html = fs_get(f'https://www.flashscore.es/futbol/{slug}/partidos/')
    out, seen = [], set()
    for m in re.finditer(r'~AA÷([A-Za-z0-9]{8})¬AD÷(\d+)(.*?)(?=~AA÷|~ZA÷|$)', html, re.S):
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        rest = m.group(3)
        g = lambda k: (re.search('¬' + k + r'÷([^¬]*)', rest) or [None, None])[1]
        if g('AB') != '1' or not g('AE') or not g('AF'):
            continue
        out.append(dict(id=m.group(1), ts=int(m.group(2)), h=g('AE'), a=g('AF'), ja=g('JA'), jb=g('JB')))
    return out


def fs_1x2(mid, ja, jb):
    """Cuota 1X2 de Bet365 (casa 16) tal como la muestra Flashscore España, o None."""
    j = _get_json(FS_ODDS + mid, timeout=20)
    for o in (((j.get('data') or {}).get('findOddsByEventId') or {}).get('odds') or []):
        if o.get('bookmakerId') == 16 and o.get('bettingType') == 'HOME_DRAW_AWAY' and o.get('bettingScope') == 'FULL_TIME':
            v = {i.get('eventParticipantId'): i.get('value') for i in o.get('odds', [])}
            try:
                r = [float(v[ja]), float(v[None]), float(v[jb])]
            except (KeyError, TypeError, ValueError):
                return None
            return r if all(x > 1 for x in r) else None
    return None


_WX = {}
_WX_FAILS = [0]          # tras 4 fallos seguidos de las dos fuentes se deja de pedir el tiempo en esta pasada


def _get_json(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CornerEdge-updater/1.0 (github.com/g3ruka76rr-stack)'}), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def forecast(lat, lon):
    """Previsión horaria (UTC) de lluvia y temperatura: {'2026-10-10T14:00': (mm, °C)}. Open-Meteo; si falla, MET Norway."""
    key = (lat, lon)
    if key in _WX:
        return _WX[key]
    if _WX_FAILS[0] >= 4:
        return {}
    res = {}
    try:
        h = _get_json(f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}'
                      '&hourly=precipitation,temperature_2m&forecast_days=10&timezone=UTC')['hourly']
        res = {t: (p, c) for t, p, c in zip(h['time'], h['precipitation'], h['temperature_2m'])}
    except Exception:
        try:      # MET Norway: horario las primeras ~60 h, luego cada 6 h (la lluvia de 6 h se reparte a partes iguales)
            ts = _get_json(f'https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat:.3f}&lon={lon:.3f}')['properties']['timeseries']
            for x in ts:
                t0 = dt.datetime.strptime(x['time'], '%Y-%m-%dT%H:%M:%SZ'); d = x['data']
                c = d['instant']['details'].get('air_temperature')
                if 'next_1_hours' in d:
                    res[t0.strftime('%Y-%m-%dT%H:00')] = (d['next_1_hours']['details'].get('precipitation_amount'), c)
                elif 'next_6_hours' in d:
                    p6 = d['next_6_hours']['details'].get('precipitation_amount')
                    for k in range(6):
                        res.setdefault((t0 + dt.timedelta(hours=k)).strftime('%Y-%m-%dT%H:00'), (None if p6 is None else p6 / 6, c))
        except Exception:
            res = {}
    _WX_FAILS[0] = 0 if res else _WX_FAILS[0] + 1
    _WX[key] = res
    return res


def prefetch_forecasts(points):
    """Una sola petición a Open-Meteo para todos los estadios de una liga (lo que falte se pide luego uno a uno)."""
    pts = sorted({p for p in points if p not in _WX})
    if not pts:
        return
    try:
        j = _get_json('https://api.open-meteo.com/v1/forecast?latitude=' + ','.join(str(a) for a, _ in pts) +
                      '&longitude=' + ','.join(str(b) for _, b in pts) + '&hourly=precipitation,temperature_2m&forecast_days=10&timezone=UTC', timeout=30)
        if isinstance(j, dict):
            j = [j]
        for p, x in zip(pts, j):
            h = x['hourly']
            _WX[p] = {t: (a, c) for t, a, c in zip(h['time'], h['precipitation'], h['temperature_2m'])}
    except Exception as e:
        print(f'    (previsión en bloque no disponible: {e}; se pide estadio a estadio)')


def weather_at(lat, lon, ts):
    """(mm de lluvia en las 3 horas desde el inicio, temperatura media) o (None, None)."""
    f = forecast(lat, lon)
    t0 = dt.datetime.utcfromtimestamp(ts).replace(minute=0, second=0)
    v = [f.get((t0 + dt.timedelta(hours=k)).strftime('%Y-%m-%dT%H:00')) for k in range(3)]
    if any(x is None or x[0] is None or x[1] is None for x in v):
        return None, None
    return round(sum(x[0] for x in v), 1), round(sum(x[1] for x in v) / 3, 1)


def build_jornada(lg, teams, now):
    from concurrent.futures import ThreadPoolExecutor
    nm = NM.get(lg) or {}
    fx = [m for m in fs_fixtures(FS_SLUG[lg]) if now - 7200 <= m['ts'] <= now + JOR_DIAS * 86400
          and nm.get(m['h']) in teams and nm.get(m['a']) in teams]
    fx.sort(key=lambda m: m['ts'])
    with ThreadPoolExecutor(6) as ex:
        odds = list(ex.map(lambda m: _safe(fs_1x2, m['id'], m['ja'], m['jb']), fx))
    prefetch_forecasts([tuple((COORDS.get(lg) or {}).get(nm[m['h']])) for m in fx if (COORDS.get(lg) or {}).get(nm[m['h']])])
    out = []
    for m, o in zip(fx, odds):
        h, a = nm[m['h']], nm[m['a']]
        c = (COORDS.get(lg) or {}).get(h)
        mm, tc = _safe(weather_at, c[0], c[1], m['ts']) or (None, None) if c else (None, None)
        out.append(dict(t=m['ts'], h=h, a=a, o=o, mm=mm, tc=tc))
    return out


def jornada_block(html, R, now=None):
    m = JOR_RE.search(html)
    if not m:
        return None, None
    now = now or int(dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).timestamp())
    old = {}
    g = re.search(r'const JORNADA = (\{.*?\});\n', m.group(0), re.S)
    if g:
        try: old = json.loads(g.group(1))
        except Exception: old = {}
    new, fresh = {}, 0
    for lg, _sfx, _n in LEAGUES:
        key = APP_KEY.get(lg, lg)
        try:
            j = build_jornada(lg, set(R[lg]['db']), now)
            new[key] = j; fresh += 1
            print(f'  jornada {lg}: {len(j)} partidos · con 1X2 {sum(1 for x in j if x["o"])} · con previsión {sum(1 for x in j if x["mm"] is not None)}')
        except Exception as e:
            new[key] = old.get(key, [])
            print(f'  aviso: próximos partidos de {lg} no actualizados ({e}); se conservan los anteriores')
    ts = now if fresh else int(re.search(r'const JOR_TS = (\d+);', m.group(0)).group(1))
    body = ',\n'.join(f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False, separators=(",", ":"))}' for k, v in new.items())
    block = ("// Próximos partidos (Flashscore): t = inicio (UTC, segundos), o = 1X2 de Bet365, mm = lluvia prevista en las 3 h del partido, tc = °C.\n"
             f"const JORNADA = {{\n{body}\n}};\nconst JOR_TS = {ts};\n")
    return block, m


def main():
    ap = argparse.ArgumentParser(description='Actualiza la base de equipos de CornerEdge')
    ap.add_argument('html', help='archivo HTML de la app (v33 o posterior)')
    cur_def, prev_def = season_code()
    ap.add_argument('--temporada', default=cur_def, help=f'código football-data de la temporada en curso (por defecto {cur_def})')
    ap.add_argument('--previa', default=prev_def, help=f'temporada previa (por defecto {prev_def})')
    ap.add_argument('--salida', help='archivo de salida (por defecto <nombre>_base-FECHA.html)')
    a = ap.parse_args()

    html = open(a.html, encoding='utf-8').read()
    m = BLOCK_RE.search(html)
    if not m:
        raise SystemExit('No encuentro el bloque de base de equipos en el HTML (¿es la v33 o posterior?).')
    old_teams = {}
    for _, sfx, _ in LEAGUES:
        key = f'DB_{sfx}'
        if f'const {key} = {{' in m.group(0):
            old_teams[key] = set(re.findall(r'^\s+"([^"]+)":', m.group(0).split(f'const {key} = {{')[1].split('};')[0], re.M))

    R, errs, CUR = {}, [], {}
    for lg, _sfx, nteams in LEAGUES:
        print(f'Descargando {lg} {a.temporada} y {a.previa}…')
        try:
            cur = download(a.temporada, lg)
        except Exception as e:
            raise SystemExit(f'No se pudo descargar {lg} {a.temporada} de football-data ({e}). Revisa la conexión o el código de temporada.')
        try:
            prev = download(a.previa, lg)
        except Exception as e:
            print(f'  aviso: sin temporada previa ({e}); prior = media de la temporada en curso')
            prev = []
        R[lg] = build(cur, prev)
        CUR[lg] = cur
        errs += validate(lg, R[lg], nteams)
        r = R[lg]
        print(f'  {r["n"]} partidos hasta {r["last"]} · media córners {r["raw_mean"]} (previa {r["prev_mean"]}) '
              f'→ liga {r["lg"]["hf"] + r["lg"]["vf"]:.2f} · goles {r["goals"][0]}–{r["goals"][1]} · '
              f'{sum(v[6] for v in r["db"].values())}/{len(r["db"])} equipos con prior de la temporada previa')
    if errs:
        print('\nVALIDACIÓN FALLIDA — no se escribe nada:'); [print('  ·', e) for e in errs]
        sys.exit(1)

    for lg, sfx, _ in LEAGUES:
        key = f'DB_{sfx}'
        if key not in old_teams: print(f'  {key}: liga nueva en la app ({len(R[lg]["db"])} equipos)'); continue
        new = set(R[lg]['db']); gone, added = old_teams[key] - new, new - old_teams[key]
        if gone or added:
            print(f'  {key}: equipos nuevos {sorted(added) or "—"} · retirados {sorted(gone) or "—"}')

    block, last = js_block(R)
    out = html[:m.start()] + block + html[m.end():]
    try:
        fblock, fm = forms_block(out, R, CUR)
        if fblock:
            out = out[:fm.start()] + fblock + out[fm.end():]
    except Exception as e:
        print(f'  aviso: no se actualizaron los dibujos ({e}); la base de córners sí')
    try:
        jblock, jm = jornada_block(out, R)
        if jblock:
            out = out[:jm.start()] + jblock + out[jm.end():]
    except Exception as e:
        print(f'  aviso: no se actualizaron los próximos partidos ({e}); la base de córners sí')
    dst = a.salida or re.sub(r'(_base-\d{4}-\d{2}-\d{2})?\.html$', f'_base-{last}.html', a.html)
    if os.path.abspath(dst) == os.path.abspath(a.html):
        shutil.copy(a.html, a.html + '.bak')
    open(dst, 'w', encoding='utf-8').write(out)
    print(f'\nOK → {dst}')


if __name__ == '__main__':
    main()
