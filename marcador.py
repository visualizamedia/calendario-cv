#!/usr/bin/env python3
"""Marcador en vivo de las federaciones a CSV, para usarlo como Data Source de vMix.

Dos fuentes, las dos publicas y sin login:

  1. /api/competiciones/getPartido?partidoId=  ->  sets y parciales.
  2. /Public/ResumenPartido.aspx?Id=           ->  el acta electronica completa:
     estado del partido, hora de comienzo, puntos y fallos por jugadora, colores
     de camiseta, tarjetas, rotaciones y el punto a punto con el minuto de cada
     accion. El acta solo existe desde que el arbitro la abre.

Uso:
    python marcador.py --hoy                      # que partidos hay hoy y su id
    python marcador.py --partido 58089            # una lectura y a la pantalla
    python marcador.py --partido 58089 --bucle    # cada 5 s escribe los CSV
    python marcador.py --partido 1346 --host rfevb --bucle --cada 10
    python marcador.py --partido 58089 --bucle --grupo 34075   # + clasificacion
    python marcador.py --demo                     # autocomprobacion sin red

Los CSV se escriben en ./vmix (se puede cambiar con --salida). Cada fichero se
escribe en un temporal y se renombra encima, asi vMix nunca lee un fichero a
medias.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

HOSTS = {"fmv": "https://intranet.fmvoley.com", "rfevb": "https://rfevb.fontventa.com"}

# Con un User-Agent que no sea de navegador, ResumenPartido.aspx devuelve solo el
# armazon de la pagina (13 KB sin datos). Con este devuelve el acta entera.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}

DEC = json.JSONDecoder()


def baja(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def api(host, consulta):
    return json.loads(baja(f"{host}/api/competiciones/{consulta}")).get("content")


def dicts(v):
    """Todos los diccionarios de un arbol ya parseado, el de dentro tambien."""
    if isinstance(v, dict):
        yield v
        for x in v.values():
            yield from dicts(x)
    elif isinstance(v, list):
        for x in v:
            yield from dicts(x)


def objetos(js):
    """Los objetos JSON incrustados en el init de ExtNet que trae el acta.

    La pagina no hace ninguna llamada JSON: los datos vienen dentro de un script
    generado con un GUID por peticion. raw_decode se encarga de las comillas y
    las llaves que haya dentro de las cadenas; luego hay que bajar a los objetos
    anidados porque las jugadoras y los sets vienen colgados de otro mas grande.
    """
    i = 0
    while (i := js.find('{"', i)) >= 0:
        try:
            o, fin = DEC.raw_decode(js, i)
        except ValueError:
            i += 2
            continue
        i = fin
        yield from dicts(o)


def acta(host, partido_id):
    """El acta del partido, o None si el arbitro todavia no la ha abierto."""
    armazon = baja(f"{host}/Public/ResumenPartido.aspx?Id={partido_id}")
    guid = re.search(r"extnet-init-js/ext\.axd\?([0-9a-f]+)", armazon)
    if not guid:
        return None
    datos = {"cabecera": None, "sets": [], "jugadores": [], "eventos": []}
    vistos = set()
    for o in objetos(baja(f"{host}/extnet/extnet-init-js/ext.axd?{guid.group(1)}")):
        # El init repite cada objeto en varios sitios, y PersonaId viene a 0 en el
        # acta publica, asi que lo unico que distingue a dos jugadoras es el objeto
        # entero.
        clave = json.dumps(o, sort_keys=True, ensure_ascii=False)
        if clave in vistos:
            continue
        vistos.add(clave)
        if "Estado" in o and "EquipoLocal" in o:
            datos["cabecera"] = o
        elif "NumSet" in o:
            datos["sets"].append(o)
        elif "PuntosTotales" in o:
            datos["jugadores"].append(o)
        elif "EventoId" in o:
            datos["eventos"].append(o)
    datos["sets"].sort(key=lambda s: s["NumSet"])
    # Los eventos no dicen a que set pertenecen: el orden bueno es el de los sets.
    if datos["sets"]:
        datos["eventos"] = [dict(e, NumSet=s["NumSet"])
                            for s in datos["sets"] for e in s.get("EventosSet") or []]
    return datos if datos["cabecera"] else None


def acabado(n, local, visitante):
    """Un set esta cerrado cuando alguien llega a 25 (15 en el quinto) con dos de ventaja."""
    meta = 15 if n == 5 else 25
    return max(local, visitante) >= meta and abs(local - visitante) >= 2


def marcador(ficha, datos):
    """Una fila con el estado del partido. La ficha de la API es el respaldo del acta."""
    cab = (datos or {}).get("cabecera") or {}
    par = [(int(cab.get(f"PuntosLocalJuego{n}", ficha[f"puntos_local_juego_{n}"])),
            int(cab.get(f"PuntosVisitanteJuego{n}", ficha[f"puntos_visitante_juego_{n}"])))
           for n in range(1, 6)]
    if cab:
        sets_l = int(cab["ResultadoLocal"])
        sets_v = int(cab["ResultadoVisitante"])
    else:
        # Los sets de getPartido cuentan tambien el set que se esta jugando, y se lo
        # apuntan a quien va ganando: con el partido en marcha no valen. Se sacan de
        # los parciales, contando solo los sets ya cerrados.
        cerrados = [(n, l, v) for n, (l, v) in enumerate(par, 1) if acabado(n, l, v)]
        sets_l = sum(1 for _, l, v in cerrados if l > v)
        sets_v = sum(1 for _, l, v in cerrados if v > l)

    # El set en juego es el siguiente al de los sets ya ganados. Si alguien llega a
    # tres, el partido ha acabado y el set que se muestra es el ultimo jugado.
    jugados = sets_l + sets_v
    vivo = sets_l < 3 and sets_v < 3
    nset = min(jugados + 1, 5) if vivo else max(jugados, 1)
    puntos_l, puntos_v = par[nset - 1]

    # Si los parciales van por detras, el ultimo punto del acta manda.
    puntos = [e for e in (datos or {}).get("eventos", []) if e.get("Evento") == "Marcar un punto"]
    if puntos and (puntos_l, puntos_v) == (0, 0):
        puntos_l = puntos[-1]["MarcadorEquipoLocal"]
        puntos_v = puntos[-1]["MarcadorEquipoVisitante"]

    # getPartido trae finalizado=False siempre, incluso semanas despues, asi que el
    # estado sale del acta y, si no hay acta, de los propios sets.
    estado = cab.get("Estado") or ("Finalizado" if not vivo else
                                   "En juego" if jugados or puntos_l or puntos_v else
                                   "No comenzado")
    fila = {
        "estado": estado,
        "local": cab.get("EquipoLocal") or ficha["equipo_local"],
        "visitante": cab.get("EquipoVisitante") or ficha["equipo_visitante"],
        "sets_local": sets_l,
        "sets_visitante": sets_v,
        "set": nset,
        "puntos_local": puntos_l,
        "puntos_visitante": puntos_v,
        "marcador": f"{sets_l}-{sets_v}",
        "parcial": f"{puntos_l}-{puntos_v}",
    }
    for n in range(1, 6):
        fila[f"set{n}_local"], fila[f"set{n}_visitante"] = par[n - 1]
    fila.update({
        "amarillas_local": cab.get("numTarjetasAmarillasEquipoLocal", ""),
        "amarillas_visitante": cab.get("numTarjetasAmarillasEquipoVisitante", ""),
        "color_local": cab.get("colorCamisetaLocal", ""),
        "color_visitante": cab.get("colorCamisetaVisitante", ""),
        "competicion": (cab.get("Competicion") or "").strip(),
        "pabellon": cab.get("Pabellon") or ficha.get("pabellon", ""),
        "hora_prevista": ficha.get("fecha_hora", ""),
        "hora_comienzo": cab.get("fechaComienzoPartido", ""),
        "arbitro": ficha.get("arb1", ""),
        "actualizado": time.strftime("%H:%M:%S"),
    })
    return fila


def jugadores(datos):
    # La ficha de cada jugadora no dice de que equipo es: lo unico que las separa es
    # el color de camiseta, y la cabecera dice de quien es cada color.
    cab = (datos or {}).get("cabecera") or {}
    equipos = {}
    for lado in ("Local", "Visitante"):
        for campo in (f"colorCamiseta{lado}", f"colorCamisetaLibero{lado}"):
            equipos.setdefault(cab.get(campo), cab.get(f"Equipo{lado}", ""))
    for j in (datos or {}).get("jugadores", []):
        yield {
            "equipo": equipos.get(j.get("ColorCamiseta"), ""),
            "puesto": j.get("TipoParticipante", ""),
            "dorsal": j.get("Dorsal", ""),
            "nombre": f'{j.get("NombreParticipante", "")} {j.get("ApellidosParticipante", "")}'.strip(),
            "puntos": j.get("PuntosTotales", ""),
            "fallos": j.get("FallosTotales", ""),
            "capitana": j.get("EsCapitan", ""),
            "libero": j.get("EsLibero", ""),
            "color": j.get("ColorCamiseta", ""),
        }


def eventos(datos, ultimos=20):
    todos = (datos or {}).get("eventos", [])
    for e in reversed(todos[-ultimos:]):
        yield {
            "set": e.get("NumSet", ""),
            "minuto": e.get("FechaMinuto", ""),
            "evento": e.get("Evento", ""),
            "equipo": e.get("Equipo", ""),
            "dorsal": e.get("Dorsal", ""),
            "jugadora": e.get("Miembro", ""),
            "marcador": f'{e.get("MarcadorEquipoLocal")}-{e.get("MarcadorEquipoVisitante")}',
        }


def escribe(destino, filas):
    """CSV con cabecera, en UTF-8 con BOM para que Excel y vMix lean los acentos."""
    filas = list(filas)
    if not filas:
        return
    tmp = destino.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    os.replace(tmp, destino)


def paso(host, partido_id, salida, grupo_id=None):
    ficha = api(host, f"getPartido?partidoId={partido_id}")
    datos = acta(host, partido_id)
    fila = marcador(ficha, datos)
    escribe(salida / "marcador.csv", [fila])
    escribe(salida / "jugadores.csv", jugadores(datos))
    escribe(salida / "eventos.csv", eventos(datos))
    if grupo_id:
        escribe(salida / "clasificacion.csv", [
            {"posicion": e["posicion"], "equipo": e["nombre"], "puntos": e["puntos"],
             "jugados": e["jugados"], "ganados": e["ganados"], "perdidos": e["perdidos"],
             "sets_favor": e["sets_a_favor"], "sets_contra": e["sets_en_contra"]}
            for e in api(host, f"getClasificacionGrupo?grupoId={grupo_id}")])

    # Registro de la sesion: sirve para ver con que retraso se mueve el marcador.
    registro = salida / "registro.csv"
    nuevo = not registro.exists()
    with registro.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["hora", "estado", "sets", "parcial", "set", "eventos_acta"])
        w.writerow([fila["actualizado"], fila["estado"], fila["marcador"], fila["parcial"],
                    fila["set"], len((datos or {}).get("eventos", []))])
    return fila


def dia_partidos(dia):
    """Los partidos de ese dia de nuestros clubes, con el id que pide --partido."""
    sys.path.insert(0, str(Path(__file__).parent))
    from fetch import CLUBES, ficheros  # noqa: E402  (solo para el mapa grupo -> host)

    donde = {str(g[2]): g[1] for c in CLUBES for g in c["grupos"]}
    atras = {v: k for k, v in HOSTS.items()}
    ahora = dia
    for club in CLUBES:
        fjson, _ = ficheros(club)
        ruta = Path(__file__).parent / "docs" / fjson
        if not ruta.exists():
            continue
        for p in json.loads(ruta.read_text(encoding="utf-8")):
            if p["fecha"] != ahora:
                continue
            grupo, partido = p["id"].split("-")
            host = donde.get(grupo, "")
            print(f'--partido {partido} --host {atras.get(host, "fmv")} --grupo {grupo}'
                  f'   # {p["hora"]} {p["local"]} - {p["visitante"]}')


def demo():
    js = ('var x = {"Id": 1, "EquipoLocal": "A {ojo}", "EquipoVisitante": "B", '
          '"ResultadoLocal": 1, "ResultadoVisitante": 0, "Estado": "En juego", '
          '"PuntosLocalJuego1": 25, "PuntosVisitanteJuego1": 20, "PuntosLocalJuego2": 7, '
          '"PuntosVisitanteJuego2": 9, "PuntosLocalJuego3": 0, "PuntosVisitanteJuego3": 0, '
          '"PuntosLocalJuego4": 0, "PuntosVisitanteJuego4": 0, "PuntosLocalJuego5": 0, '
          '"PuntosVisitanteJuego5": 0, "numTarjetasAmarillasEquipoLocal": 1};'
          '{"NumSet": 1, "EventosSet": [{"Evento": "Marcar un punto", "EventoId": 30, '
          '"Dorsal": "7", "Equipo": "A", "Miembro": "", "FechaMinuto": "07:33", '
          '"MarcadorEquipoLocal": 7, "MarcadorEquipoVisitante": 9}]};'
          '{"PersonaId": 9, "NombreParticipante": "ANA", "ApellidosParticipante": "PEREZ", '
          '"Dorsal": "7", "PuntosTotales": 12, "FallosTotales": 3, "EsCapitan": true, '
          '"EsLibero": false, "ColorCamiseta": "#AFB42B", "TipoParticipante": "Jugador"};')
    hallados = list(objetos(js))
    # La llave dentro de una cadena no parte el objeto, y el evento colgado del set
    # tambien sale: tres objetos de primer nivel mas el evento anidado.
    assert len(hallados) == 4, hallados
    assert hallados[0]["EquipoLocal"] == "A {ojo}"
    assert [o for o in hallados if "EventoId" in o][0]["Dorsal"] == "7"

    datos = {"cabecera": hallados[0], "sets": [hallados[1]],
             "eventos": [o for o in hallados if "EventoId" in o],
             "jugadores": [o for o in hallados if "PuntosTotales" in o]}
    vacia = {"sets_local": 0, "sets_visitante": 0, "equipo_local": "", "equipo_visitante": "",
             **{f"puntos_{d}_juego_{n}": 0 for d in ("local", "visitante") for n in range(1, 6)}}
    f = marcador(vacia, datos)
    # 1-0 en sets: el set en juego es el segundo y su parcial es 7-9.
    assert (f["set"], f["parcial"], f["marcador"]) == (2, "7-9", "1-0"), f
    assert f["estado"] == "En juego" and f["amarillas_local"] == 1

    # Sin acta manda la ficha de la API, que no sabe el estado.
    ficha = dict(vacia, sets_local=3, sets_visitante=1, equipo_local="A", equipo_visitante="B",
                 puntos_local_juego_1=25, puntos_visitante_juego_1=23,
                 puntos_local_juego_2=25, puntos_visitante_juego_2=20,
                 puntos_local_juego_3=20, puntos_visitante_juego_3=25,
                 puntos_local_juego_4=25, puntos_visitante_juego_4=23)
    f = marcador(ficha, None)
    assert (f["estado"], f["set"], f["parcial"], f["marcador"]) == ("Finalizado", 4, "25-23", "3-1"), f

    # Partido en marcha y sin acta: getPartido da 0-1 en sets porque cuenta el set en
    # juego a favor de quien va ganando. El tercer set sigue abierto a 6-7.
    f = marcador(dict(vacia, sets_local=0, sets_visitante=3, equipo_local="A", equipo_visitante="B",
                      puntos_local_juego_1=15, puntos_visitante_juego_1=25,
                      puntos_local_juego_2=22, puntos_visitante_juego_2=25,
                      puntos_local_juego_3=6, puntos_visitante_juego_3=7), None)
    assert (f["marcador"], f["set"], f["parcial"]) == ("0-2", 3, "6-7"), f
    # El quinto set se cierra a 15, no a 25.
    assert acabado(5, 15, 10) and not acabado(4, 15, 10) and not acabado(5, 15, 14)

    # Un partido que no ha empezado no es un partido finalizado.
    f = marcador(dict(vacia, equipo_local="A", equipo_visitante="B"), None)
    assert (f["estado"], f["set"], f["parcial"]) == ("No comenzado", 1, "0-0"), f

    # Con el acta a medias y los parciales en blanco, el ultimo punto del acta manda.
    cab = dict(hallados[0], PuntosLocalJuego2=0, PuntosVisitanteJuego2=0)
    f = marcador(vacia, dict(datos, cabecera=cab))
    assert f["parcial"] == "7-9", f

    assert list(jugadores(datos))[0]["nombre"] == "ANA PEREZ"
    assert list(eventos(datos))[0]["marcador"] == "7-9"
    print("demo ok")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--partido", help="partidoId de la federacion")
    p.add_argument("--host", default="fmv", choices=list(HOSTS))
    p.add_argument("--grupo", help="grupoId, para escribir tambien la clasificacion")
    p.add_argument("--salida", default=str(Path(__file__).parent / "vmix"))
    p.add_argument("--cada", type=int, default=5, help="segundos entre lecturas (def. 5)")
    p.add_argument("--bucle", action="store_true")
    p.add_argument("--hoy", action="store_true", help="lista los partidos del dia y sus ids")
    p.add_argument("--dia", default=date.today().isoformat(), help="dia de --hoy (AAAA-MM-DD)")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()

    if a.demo:
        demo()
    elif a.hoy:
        dia_partidos(a.dia)
    elif not a.partido:
        p.error("hace falta --partido (o --hoy para verlos)")
    else:
        destino = Path(a.salida)
        destino.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                f = paso(HOSTS[a.host], a.partido, destino, a.grupo)
                print(f'{f["actualizado"]}  {f["estado"]:<12} {f["local"]} {f["marcador"]} '
                      f'{f["visitante"]}  set {f["set"]}: {f["parcial"]}')
            except Exception as e:  # una caida de red no puede tumbar la retransmision
                print(f'{time.strftime("%H:%M:%S")}  error: {e}', file=sys.stderr)
            if not a.bucle:
                break
            time.sleep(a.cada)
