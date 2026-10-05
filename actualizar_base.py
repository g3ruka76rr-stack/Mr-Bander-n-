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
    return res


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
    dst = a.salida or re.sub(r'(_base-\d{4}-\d{2}-\d{2})?\.html$', f'_base-{last}.html', a.html)
    if os.path.abspath(dst) == os.path.abspath(a.html):
        shutil.copy(a.html, a.html + '.bak')
    open(dst, 'w', encoding='utf-8').write(out)
    print(f'\nOK → {dst}')


if __name__ == '__main__':
    main()
