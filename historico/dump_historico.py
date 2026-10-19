# Vuelca las estadísticas crudas (feed df_st_1) de los partidos terminados de la temporada en curso
# de las 14 ligas. No interpreta nada: guarda el texto tal cual para parsearlo después.
import json, os, sys, time, datetime as dt
sys.path.insert(0, os.getcwd())
from actualizar_base import fs_results, fs_get, FS_SLUG

salida = 'salida_historico'
os.makedirs(salida, exist_ok=True)
resumen = {'ts': dt.datetime.utcnow().isoformat() + 'Z', 'ligas': {}}
for lg in FS_SLUG:
    try:
        partidos = fs_results(FS_SLUG[lg])
    except Exception as e:
        resumen['ligas'][lg] = f'ERROR lista: {e}'
        continue
    filas = []
    ok = err = vacias = 0
    primer_error = None
    for m in partidos:
        try:
            crudo = fs_get(f"https://global.flashscore.ninja/2/x/feed/df_st_1_{m['id']}", feed=True)
        except Exception as e:
            crudo = f'ERROR: {e}'
        if crudo.startswith('ERROR') or not crudo:
            err += 1
            if primer_error is None:
                primer_error = crudo[:300]
        elif len(crudo) < 500:
            vacias += 1
        else:
            ok += 1
        filas.append({'id': m['id'], 'day': str(m['day']), 'h': m['h'], 'a': m['a'],
                      'hg': m['hg'], 'ag': m['ag'], 'stats_crudo': crudo})
        time.sleep(0.5)
    with open(os.path.join(salida, f'{lg}.json'), 'w', encoding='utf-8') as f:
        json.dump(filas, f, ensure_ascii=False)
    resumen['ligas'][lg] = len(filas)
    print(f'{lg}: {len(filas)} partidos · con datos {ok} · vacías {vacias} · error {err}', flush=True)
    if primer_error:
        print(f'  primer error {lg}: {primer_error}', flush=True)
with open(os.path.join(salida, 'resumen.json'), 'w', encoding='utf-8') as f:
    json.dump(resumen, f, ensure_ascii=False, indent=1)
