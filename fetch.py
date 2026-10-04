"""Descarga los partidos de los clubes de CLUBES y genera un .json y un .ics por club.

Sin dependencias: solo biblioteca estandar.
"""
import json
import sys
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Hora local con VTIMEZONE en vez de convertir a UTC: sin tzdata, sin aritmetica de
# horario de verano, y el .ics conserva la hora tal cual la publica la federacion.
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Madrid
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".splitlines()

OUT = Path(__file__).parent / "docs"
RFEVB = "https://rfevb.fontventa.com"
FMV = "https://intranet.fmvoley.com"

# Cada club se reconoce por su id en cada federacion. El nombre del equipo lleva
# patrocinador ("COX CV Collado Villalba", "HOGARES CV GUADARRAMA NEGRO") y puede
# cambiar a mitad de temporada; el id no. Filtrar solo por nombre dejaria el feed a
# cero sin avisar y Google borraria los eventos del calendario. "clave" es el nombre
# de respaldo y lo que la web resalta en negrita.
# grupos: (etiqueta, host de la API, grupoId). Un grupoId puede repetirse entre clubes
# (Villalba y Majadahonda A comparten el 34075), pero no dentro del mismo club.
CLUBES = [
    {
        "slug": "collado-villalba",
        "nombre": "CV Collado Villalba",
        "clave": "collado villalba",
        "ids": {RFEVB: "9371", FMV: "21"},
        # Este club conserva los nombres de fichero originales: ya hay gente suscrita
        # a calendario.ics y cambiar la URL le vaciaria el calendario.
        "json": "partidos.json",
        "ics": "calendario.ics",
        "grupos": [
            ("Masculino SM2 - Grupo C", RFEVB, 87),
            ("Femenino SF2 - Grupo C", RFEVB, 226),
            ("Senior Fem. 2a Aut. Preferente - Grupo A", FMV, 34075),
            ("Junior Fem. 1a Aut. Preferente - Unico", FMV, 33941),
        ],
    },
    {
        "slug": "majadahonda",
        "nombre": "CV Majadahonda senior femenino",
        "clave": "majadahonda",
        "ids": {FMV: "19"},
        "grupos": [
            ("Senior Fem. 2a Aut. Preferente - Grupo A", FMV, 34075),  # equipo A
            ("Senior Fem. 1a Aut. Zonal - Grupo A", FMV, 34222),       # equipo B
        ],
    },
    {
        "slug": "guadarrama",
        "nombre": "CV Guadarrama senior femenino",
        "clave": "guadarrama",
        "ids": {FMV: "155"},
        "grupos": [
            ("Senior Fem. 1a Aut. Zonal - Grupo A", FMV, 34222),  # equipo Negro
            ("Senior Fem. 2a Aut. Zonal - Unico", FMV, 34229),    # equipo Rojo
        ],
    },
]


def ficheros(club):
    """Los dos nombres de salida del club, con el slug como valor por defecto."""
    return (club.get("json", f'{club["slug"]}.json'),
            club.get("ics", f'{club["slug"]}.ics'))


def normaliza(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def descarga(host, grupo_id):
    url = f"{host}/api/competiciones/getJornadasCalendario?grupoId={grupo_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "calendario-cv"})
    with urllib.request.urlopen(req, timeout=30) as r:
        datos = json.loads(r.read().decode("utf-8"))
    if not datos.get("content"):
        raise SystemExit(f"{host} grupo {grupo_id}: sin calendario ({datos.get('Error')})")
    return datos["content"]


def filtra(club, etiqueta, host, grupo_id, jornadas):
    """Los partidos del club en un grupo, por id de partido. Sin red, para poder probarlo."""
    club_id = club["ids"].get(host)
    clave = club["clave"]
    encontrados = {}
    for jornada in jornadas:
        for p in jornada["partidos"]:
            local, visitante = p["equipo_local"], p["equipo_visitante"]
            # En los grupos con numero impar de equipos la federacion publica una fila
            # "Descansa..." con clubId 0 por jornada. No es un partido: ni evento ni
            # cuenta para el feed. Se descarta por el id, y por el nombre de respaldo.
            if any(str(p.get(c)) == "0" or normaliza(e).startswith("descansa")
                   for c, e in (("clubLocalId", local), ("clubVisitanteId", visitante))):
                continue
            casa = str(p.get("clubLocalId")) == club_id or clave in normaliza(local)
            if not (casa or str(p.get("clubVisitanteId")) == club_id
                    or clave in normaliza(visitante)):
                continue
            dia, _, hora = p["fecha_hora"].partition(" ")
            d, m, a = (int(x) for x in dia.split("/"))
            h, _, mi = hora.partition(":")
            # La federacion publica 00:00 mientras no cierra el horario. El pabellon
            # suele llegar a la vez, pero si llega solo la hora ya es dato firme.
            confirmado = bool(int(h))
            # Por id: un partido recolocado puede asomar en dos jornadas a la vez, y
            # dos VEVENT con el mismo UID dejan el calendario en estado indefinido.
            encontrados[f'{grupo_id}-{p["id"]}'] = {
                "id": f'{grupo_id}-{p["id"]}',
                "competicion": etiqueta,
                "jornada": jornada["numero"],
                "fecha": date(a, m, d).isoformat(),
                "hora": f"{int(h):02d}:{int(mi):02d}" if confirmado else None,
                "local": local,
                "visitante": visitante,
                "pabellon": (p["pabellon"] or "").strip(),
                "casa": casa,
                "confirmado": confirmado,
                # esAplazado es un partido suspendido, sin fecha nueva. Distinto de
                # fechaAplazada, que es un partido ya recolocado en otra jornada con
                # fecha y pabellon firmes: ese no lleva aviso, solo la procedencia.
                "aplazado": bool(p.get("esAplazado")),
                "proviene": (p.get("jornadaProviene") or "")
                if p.get("fechaAplazada") or p.get("esDeOtraJornada") else "",
            }
    # Cero partidos = grupoId caducado, club cambiado de grupo o API vacia. Publicar el
    # feed recortado haria que Google borrase esos eventos del calendario sin avisar.
    if not encontrados:
        raise SystemExit(f'{club["slug"]} / {etiqueta}: 0 partidos del club, '
                         "no publico un feed incompleto")
    return encontrados


def recoge(club):
    grupos = club["grupos"]
    assert len({g[2] for g in grupos}) == len(grupos), "grupoId repetido: los UID chocarian"
    partidos = {}
    for etiqueta, host, grupo_id in grupos:
        partidos.update(filtra(club, etiqueta, host, grupo_id, descarga(host, grupo_id)))
    return sorted(partidos.values(), key=lambda p: (p["fecha"], p["hora"] or "00:00"))


def sin_sello(texto):
    """El texto sin las lineas DTSTAMP, que cambian en cada ejecucion."""
    return "\n".join(l for l in texto.splitlines() if not l.startswith("DTSTAMP:"))


def esc(texto):
    for viejo, nuevo in (("\\", "\\\\"), (";", "\;"), (",", "\,"), ("\n", "\n")):
        texto = texto.replace(viejo, nuevo)
    return texto


def plegar(linea):
    """RFC 5545: maximo 75 octetos por linea, continuacion con espacio inicial."""
    crudo = linea.encode("utf-8")
    if len(crudo) <= 75:
        return linea
    trozos, actual = [], b""
    for char in linea:
        b = char.encode("utf-8")
        if len(actual) + len(b) > (75 if not trozos else 74):
            trozos.append(actual)
            actual = b""
        actual += b
    trozos.append(actual)
    return "\r\n ".join(t.decode("utf-8") for t in trozos)


def ics(partidos, calname="CV Collado Villalba (en casa)"):
    ahora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lineas = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//calendario-cv//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        plegar(f"X-WR-CALNAME:{esc(calname)}"), "X-WR-TIMEZONE:Europe/Madrid",
    ] + VTIMEZONE
    for p in partidos:
        titulo = f'{p["local"]} - {p["visitante"]}'
        if p["aplazado"]:
            titulo = "APLAZADO: " + titulo
        elif not p["confirmado"]:
            titulo = "POR CONFIRMAR: " + titulo
        descripcion = f'{p["competicion"]} - Jornada {p["jornada"]}'
        if p["proviene"]:
            descripcion += f' (recolocado, venia de la {p["proviene"]})'
        lineas += ["BEGIN:VEVENT", f'UID:{p["id"]}@calendario-cv', f"DTSTAMP:{ahora}"]
        if p["confirmado"]:
            h, mi = (int(x) for x in p["hora"].split(":"))
            inicio = datetime.fromisoformat(p["fecha"]).replace(hour=h, minute=mi)
            fin = inicio + timedelta(hours=2)
            lineas += [
                f'DTSTART;TZID=Europe/Madrid:{inicio.strftime("%Y%m%dT%H%M%S")}',
                f'DTEND;TZID=Europe/Madrid:{fin.strftime("%Y%m%dT%H%M%S")}',
            ]
        else:
            dia = date.fromisoformat(p["fecha"])
            lineas += [
                f'DTSTART;VALUE=DATE:{dia.strftime("%Y%m%d")}',
                f'DTEND;VALUE=DATE:{(dia + timedelta(days=1)).strftime("%Y%m%d")}',
            ]
        lineas += [
            plegar(f"SUMMARY:{esc(titulo)}"),
            plegar(f"DESCRIPTION:{esc(descripcion)}"),
            "STATUS:" + ("CONFIRMED" if p["confirmado"] and not p["aplazado"] else "TENTATIVE"),
        ]
        if p["pabellon"]:
            lineas.append(plegar(f'LOCATION:{esc(p["pabellon"])}'))
        lineas.append("END:VEVENT")
    lineas.append("END:VCALENDAR")
    return "\r\n".join(lineas) + "\r\n"


def demo():
    p = [{
        "id": "1-2", "competicion": "Test; con coma, y punto y coma", "jornada": "1",
        "fecha": "2026-10-11", "hora": None, "local": "A", "visitante": "B",
        "pabellon": "", "casa": True, "confirmado": False, "aplazado": False,
        "proviene": "",
    }, {
        "id": "1-3", "competicion": "Test", "jornada": "2", "fecha": "2026-10-11",
        "hora": "16:30", "local": "A", "visitante": "B", "pabellon": "LOS CANTOS",
        "casa": True, "confirmado": True, "aplazado": False, "proviene": "J6",
    }]
    salida = ics(p)
    assert "DTSTART;VALUE=DATE:20261011" in salida
    assert "SUMMARY:POR CONFIRMAR: A - B" in salida
    assert "DTSTART;TZID=Europe/Madrid:20261011T163000" in salida
    assert "DTEND;TZID=Europe/Madrid:20261011T183000" in salida
    assert "TZID:Europe/Madrid" in salida
    assert "DESCRIPTION:Test\; con coma\, y punto y coma - Jornada 1" in salida
    # Un partido recolocado con fecha firme sigue confirmado: solo anota su origen.
    assert "SUMMARY:A - B\r\n" in salida and "APLAZADO" not in salida
    assert "(recolocado\, venia de la J6)" in salida
    assert salida.count("STATUS:CONFIRMED") == 1
    assert all(len(l.encode()) <= 75 for l in salida.split("\r\n"))
    assert normaliza("CIRCE FISIOTERAPIA CV COLLADO VILLALBA").count("collado villalba") == 1

    # La configuracion real: un slug y dos ficheros por club, sin grupoId repetido
    # dentro de un club. Dos clubes con el mismo fichero se sobreescribirian.
    for c in CLUBES:
        assert len({g[2] for g in c["grupos"]}) == len(c["grupos"]), c["slug"]
        assert c["clave"] == normaliza(c["clave"]), c["slug"]
    assert len({c["slug"] for c in CLUBES}) == len(CLUBES)
    assert len({n for c in CLUBES for n in ficheros(c)}) == 2 * len(CLUBES)
    assert ficheros(CLUBES[0]) == ("partidos.json", "calendario.ics"), "URL historica"

    # El fichero, no solo la cadena: en Windows sin newline="" saldrian \r\r\n.
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "t.ics"
    tmp.write_text(salida, encoding="utf-8", newline="")
    crudo = tmp.read_bytes()
    assert b"\r\r" not in crudo, "saltos de linea traducidos"
    assert crudo.count(b"\n") == crudo.count(b"\r\n"), "hay \\n sin su \\r"
    assert all(len(l) <= 75 for l in crudo.split(b"\r\n"))

    # Dos generaciones con distinto DTSTAMP tienen que compararse iguales, o el cron
    # commitearia a diario; y una diferencia real tiene que detectarse igualmente.
    otro = salida.replace("DTSTAMP:2", "DTSTAMP:1")
    assert otro != salida and sin_sello(otro) == sin_sello(salida)
    assert sin_sello(ics(p[:1])) != sin_sello(salida)

    # Lo que la federacion cambia sobre la marcha. En todos los casos tiene que salir
    # UN evento con el mismo UID, para que Google lo actualice en vez de duplicarlo.
    FM = FMV
    CT = {"slug": "test", "clave": "collado villalba", "ids": {FM: "21"}}
    fila = lambda **kw: [{"numero": "1", "partidos": [dict(
        {"id": 7, "equipo_local": "CV COLLADO VILLALBA", "equipo_visitante": "B",
         "clubLocalId": "21", "clubVisitanteId": "99",
         "fecha_hora": "11/10/2026 0:00", "pabellon": ""}, **kw)]}]
    firme = {"fecha_hora": "11/10/2026 16:30", "pabellon": "LOS CANTOS"}
    sin_hora = filtra(CT, "T", FM, 5, fila())
    con_hora = filtra(CT, "T", FM, 5, fila(**firme))
    movido = filtra(CT, "T", FM, 5, fila(**dict(firme, fecha_hora="18/10/2026 19:00")))
    assert list(sin_hora) == list(con_hora) == list(movido) == ["5-7"]
    assert not sin_hora["5-7"]["confirmado"] and con_hora["5-7"]["confirmado"]
    assert "DTSTART;VALUE=DATE:20261011" in ics(sin_hora.values())
    assert "DTSTART;TZID=Europe/Madrid:20261011T163000" in ics(con_hora.values())
    assert "DTSTART;TZID=Europe/Madrid:20261018T190000" in ics(movido.values())
    # Cierran la hora pero aun no el pabellon: la hora ya vale, el evento no lleva sitio.
    solo_hora = filtra(CT, "T", FM, 5, fila(fecha_hora="11/10/2026 16:30"))
    assert solo_hora["5-7"]["confirmado"] and "LOCATION" not in ics(solo_hora.values())
    # Cambia el patrocinador y el nombre deja de decir Collado Villalba: el clubId no.
    patro = filtra(CT, "T", FM, 5, fila(equipo_local="NUEVO PATROCINADOR C.V."))
    assert list(patro) == ["5-7"] and patro["5-7"]["casa"]
    # Fuera de casa: mismo partido, pero no entra en el feed.
    fuera = filtra(CT, "T", FM, 5, fila(equipo_local="B", clubLocalId="99",
                                    equipo_visitante="CV COLLADO VILLALBA",
                                    clubVisitanteId="21"))
    assert not fuera["5-7"]["casa"]
    # El mismo partido asomando en dos jornadas: un solo evento, sin UID repetido.
    doble = fila()[0]["partidos"]
    dedup = filtra(CT, "T", FM, 5, [{"numero": "1", "partidos": doble},
                                {"numero": "9", "partidos": doble}])
    assert ics(dedup.values()).count("BEGIN:VEVENT") == 1
    # La jornada de descanso de un grupo impar: la fila no es un partido.
    desc = fila(equipo_visitante="Descansa...", clubVisitanteId="0")
    real = fila(**dict(firme, id=8))
    assert list(filtra(CT, "T", FM, 5, [{"numero": "1", "partidos":
        desc[0]["partidos"] + real[0]["partidos"]}])) == ["5-8"]
    # Otro club: mismo grupo, pero cada feed lleva solo lo suyo. El de Villalba y el
    # de Majadahonda comparten el grupo 34075, asi que el mismo partido sale en los
    # dos feeds; son calendarios distintos en Google, no se pisan.
    MJ = {"slug": "test2", "clave": "majadahonda", "ids": {FM: "19"}}
    choque = fila(equipo_visitante="CV MAJADAHONDA A", clubVisitanteId="19", **firme)
    assert filtra(CT, "T", FM, 5, choque)["5-7"]["casa"]
    assert not filtra(MJ, "T", FM, 5, choque)["5-7"]["casa"]
    assert "X-WR-CALNAME:Nombre con coma\, y mas" in ics([], "Nombre con coma, y mas")
    # Suspendido de verdad, sin fecha nueva.
    susp = ics(filtra(CT, "T", FM, 5, fila(esAplazado=True, **firme)).values())
    assert "SUMMARY:APLAZADO: " in susp and "STATUS:CONFIRMED" not in susp
    # Grupo que se queda sin partidos del club: parar, no publicar un feed recortado.
    for vacio in ([], [{"numero": "1", "partidos": []}],
                  fila(equipo_local="OTRO", equipo_visitante="OTRO", clubLocalId="1")):
        try:
            filtra(CT, "T", FM, 5, vacio)
        except SystemExit:
            pass
        else:
            raise AssertionError("un grupo sin partidos del club tiene que parar")
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        OUT.mkdir(exist_ok=True)
        indice, salidas = [], {}
        for club in CLUBES:
            partidos = recoge(club)
            fjson, fics = ficheros(club)
            # El .ics solo lleva los partidos en casa, que son a los que se va a ir.
            # El .json lleva todos para que la web pueda quitar el filtro.
            en_casa = [p for p in partidos if p["casa"]]
            salidas[OUT / fjson] = json.dumps(partidos, ensure_ascii=False, indent=1)
            salidas[OUT / fics] = ics(en_casa, f'{club["nombre"]} (en casa)')
            indice.append({"slug": club["slug"], "nombre": club["nombre"],
                           "clave": club["clave"], "json": fjson, "ics": fics})
            print(f'{club["slug"]}: {len(partidos)} partidos, {len(en_casa)} en casa '
                  f'al .ics, {sum(1 for p in en_casa if not p["confirmado"])} por confirmar')
        # La web saca de aqui el selector de club: un club nuevo no toca el HTML.
        salidas[OUT / "clubes.json"] = json.dumps(indice, ensure_ascii=False, indent=1)
        # Comparamos ignorando DTSTAMP, lo unico que cambia en cada ejecucion: asi no
        # commiteamos a diario sin motivo, pero cualquier otra diferencia si se
        # reescribe, incluido un cambio de formato del .ics o un fichero que falte.
        if all(f.exists() and sin_sello(f.read_text(encoding="utf-8")) == sin_sello(t)
               for f, t in salidas.items()):
            print("sin cambios")
            sys.exit()
        for f, t in salidas.items():
            # newline="" desactiva la traduccion de saltos de linea: en Windows los
            # \r\n del iCalendar se escribirian como \r\r\n y el fichero saldria roto.
            f.write_text(t, encoding="utf-8", newline="" if f.suffix == ".ics" else "\n")
        print(f"escritos {len(salidas)} ficheros")
