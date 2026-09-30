#!/usr/bin/env python3
"""
CornerEdge · rellenar córners finales del registro de análisis
==============================================================
1. En la app: Historial → Registro de análisis → «Exportar análisis (CSV)»
2. python3 rellenar_resultados.py cornerEdge_analisis_AAAA-MM-DD.csv
3. En la app: «Importar resultados» con el archivo *_con_resultados.csv generado

Busca cada partido en football-data.co.uk (LaLiga SP1, Hypermotion SP2, Premier E0, Serie A I1, Bundesliga D1) por liga, equipos y fecha (±1 día)
y rellena 'final' = córners totales del partido (HC + AC). Sólo toca la columna 'final'.
Los nombres de equipo de la app son los de football-data, así que el cruce es directo.
Requisitos: Python 3.8+ sin librerías externas.
"""
import csv, io, sys, urllib.request, datetime as dt, collections

LIGA = {'La Liga': 'SP1', 'Segunda': 'SP2', 'Premier': 'E0', 'Serie A': 'I1', 'Bundesliga': 'D1',
        'Ligue 1': 'F1', 'Portugal': 'P1', 'Championship': 'E1', '2. Bundesliga': 'D2', 'Eredivisie': 'N1', 'Bélgica': 'B1', 'Escocia': 'SC0'}
URL = 'https://www.football-data.co.uk/mmz4281/{season}/{league}.csv'


def season_of(day):
    a = day.year if day.month >= 7 else day.year - 1
    return f'{a % 100:02d}{(a + 1) % 100:02d}'


_cache = {}
def fd_rows(season, league):
    key = (season, league)
    if key not in _cache:
        req = urllib.request.Request(URL.format(season=season, league=league), headers={'User-Agent': 'Mozilla/5.0 CornerEdge'})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode('utf-8-sig', errors='replace')
        idx = {}
        for x in csv.DictReader(io.StringIO(raw)):
            try:
                fmt = '%d/%m/%Y' if len(x['Date'].split('/')[-1]) == 4 else '%d/%m/%y'
                d = dt.datetime.strptime(x['Date'], fmt).date()
                idx[(x['HomeTeam'].strip(), x['AwayTeam'].strip(), d)] = int(x['HC']) + int(x['AC'])
            except (ValueError, KeyError, TypeError):
                continue
        _cache[key] = idx
    return _cache[key]


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python3 rellenar_resultados.py cornerEdge_analisis_AAAA-MM-DD.csv')
    src = sys.argv[1]
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    if not rows or 'final' not in rows[0]:
        raise SystemExit('El CSV no parece un export del registro de análisis de CornerEdge.')
    st = collections.Counter()
    for r in rows:
        if r.get('final', '').strip() != '':
            st['ya tenían resultado'] += 1; continue
        lg = LIGA.get(r.get('liga', ''))
        if not lg:
            st['modo manual / liga desconocida (no se puede cruzar)'] += 1; continue
        try:
            day = dt.date.fromisoformat(r['fecha'])
        except ValueError:
            st['fecha no válida'] += 1; continue
        try:
            idx = fd_rows(season_of(day), lg)
        except Exception as e:
            st[f'descarga fallida {lg}'] += 1; continue
        val = None
        for dd in (0, -1, 1):
            val = idx.get((r['local'].strip(), r['visit'].strip(), day + dt.timedelta(days=dd)))
            if val is not None: break
        if val is None:
            st['sin datos todavía en football-data (partido reciente o no jugado)'] += 1; continue
        seen = int(float(r.get('cL') or 0)) + int(float(r.get('cV') or 0))
        if val < seen:
            st['INCOHERENTE: final < córners ya vistos (revisar a mano)'] += 1; continue
        r['final'] = str(val); st['rellenados'] += 1
    dst = src.rsplit('.', 1)[0] + '_con_resultados.csv'
    with open(dst, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_ALL)
        w.writeheader(); w.writerows(rows)
    for k, v in st.most_common(): print(f'  {k}: {v}')
    print(f'OK → {dst}')


if __name__ == '__main__':
    main()
