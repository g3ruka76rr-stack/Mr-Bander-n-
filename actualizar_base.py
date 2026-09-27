#!/usr/bin/env python3
"""
CornerEdge · actualizador de la base de equipos
================================================
Descarga los resultados con córners de football-data.co.uk (LaLiga SP1, Hypermotion SP2, Premier E0, Serie A I1, Bundesliga D1),
recalcula la base ataque×defensa con el mismo método con el que se estimó el modelo (v33) y
reescribe el bloque de datos dentro del HTML de la app.

Uso:
    python3 actualizar_base.py CornerEdge_v33.html
    python3 actualizar_base.py CornerEdge_v33.html --temporada 2627 --previa 2526

Genera:  <nombre>_base-AAAA-MM-DD.html   (el original no se toca)
Requisitos: Python 3.8+ sin librerías externas.

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
LEAGUES = [('SP1', 'LL', 20), ('SP2', 'S2', 22), ('E0', 'E0', 20), ('I1', 'I1', 20), ('D1', 'D1', 18)]
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

    R, errs = {}, []
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
    dst = a.salida or re.sub(r'(_base-\d{4}-\d{2}-\d{2})?\.html$', f'_base-{last}.html', a.html)
    if os.path.abspath(dst) == os.path.abspath(a.html):
        shutil.copy(a.html, a.html + '.bak')
    open(dst, 'w', encoding='utf-8').write(out)
    print(f'\nOK → {dst}')


if __name__ == '__main__':
    main()
