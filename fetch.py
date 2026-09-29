"""Descarga los partidos de CV Collado Villalba y genera partidos.json + calendario.ics.

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
EQUIPO = "collado villalba"

# El nombre del equipo lleva patrocinador ("COX CV Collado Villalba") y puede cambiar
# a mitad de temporada; el id de club en cada federacion no. Filtrar solo por nombre
# dejaria el feed a cero sin avisar y Google borraria los eventos del calendario.
CLUB = {
    "https://rfevb.fontventa.com": "9371",
    "https://intranet.fmvoley.com": "21",
}

# (etiqueta, host de la API, grupoId)
GRUPOS = [
    ("Masculino SM2 - Grupo C", "https://rfevb.fontventa.com", 87),
    ("Femenino SF2 - Grupo C", "https://rfevb.fontventa.com", 226),
    ("Senior Fem. 2a Aut. Preferente - Grupo A", "https://intranet.fmvoley.com", 34075),
    ("Junior Fem. 1a Aut. Preferente - Unico", "https://intranet.fmvoley.com", 33941),
]


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


def filtra(etiqueta, host, grupo_id, jornadas):
    """Los partidos del club en un grupo, por id de partido. Sin red, para poder probarlo."""
    club = CLUB.get(host)
    encontrados = {}
    for jornada in jornadas:
        for p in jornada["partidos"]:
            local, visitante = p["equipo_local"], p["equipo_visitante"]
            casa = str(p.get("clubLocalId")) == club or EQUIPO in normaliza(local)
            if not (casa or str(p.get("clubVisitanteId")) == club
                    or EQUIPO in normaliza(visitante)):
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
        raise SystemExit(f"{etiqueta}: 0 partidos del club, no publico un feed incompleto")
    return encontrados


def recoge():
    assert len({g[2] for g in GRUPOS}) == len(GRUPOS), "grupoId repetido: los UID chocarian"
    partidos = {}
    for etiqueta, host, grupo_id in GRUPOS:
        partidos.update(filtra(etiqueta, host, grupo_id, descarga(host, grupo_id)))
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


def ics(partidos):
    ahora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lineas = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//calendario-cv//ES",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:CV Collado Villalba (en casa)", "X-WR-TIMEZONE:Europe/Madrid",
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
    assert normaliza("CIRCE FISIOTERAPIA CV COLLADO VILLALBA").count(EQUIPO) == 1

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
    FM = "https://intranet.fmvoley.com"
    fila = lambda **kw: [{"numero": "1", "partidos": [dict(
        {"id": 7, "equipo_local": "CV COLLADO VILLALBA", "equipo_visitante": "B",
         "clubLocalId": "21", "clubVisitanteId": "99",
         "fecha_hora": "11/10/2026 0:00", "pabellon": ""}, **kw)]}]
    firme = {"fecha_hora": "11/10/2026 16:30", "pabellon": "LOS CANTOS"}
    sin_hora = filtra("T", FM, 5, fila())
    con_hora = filtra("T", FM, 5, fila(**firme))
    movido = filtra("T", FM, 5, fila(**dict(firme, fecha_hora="18/10/2026 19:00")))
    assert list(sin_hora) == list(con_hora) == list(movido) == ["5-7"]
    assert not sin_hora["5-7"]["confirmado"] and con_hora["5-7"]["confirmado"]
    assert "DTSTART;VALUE=DATE:20261011" in ics(sin_hora.values())
    assert "DTSTART;TZID=Europe/Madrid:20261011T163000" in ics(con_hora.values())
    assert "DTSTART;TZID=Europe/Madrid:20261018T190000" in ics(movido.values())
    # Cierran la hora pero aun no el pabellon: la hora ya vale, el evento no lleva sitio.
    solo_hora = filtra("T", FM, 5, fila(fecha_hora="11/10/2026 16:30"))
    assert solo_hora["5-7"]["confirmado"] and "LOCATION" not in ics(solo_hora.values())
    # Cambia el patrocinador y el nombre deja de decir Collado Villalba: el clubId no.
    patro = filtra("T", FM, 5, fila(equipo_local="NUEVO PATROCINADOR C.V."))
    assert list(patro) == ["5-7"] and patro["5-7"]["casa"]
    # Fuera de casa: mismo partido, pero no entra en el feed.
    fuera = filtra("T", FM, 5, fila(equipo_local="B", clubLocalId="99",
                                    equipo_visitante="CV COLLADO VILLALBA",
                                    clubVisitanteId="21"))
    assert not fuera["5-7"]["casa"]
    # El mismo partido asomando en dos jornadas: un solo evento, sin UID repetido.
    doble = fila()[0]["partidos"]
    dedup = filtra("T", FM, 5, [{"numero": "1", "partidos": doble},
                                {"numero": "9", "partidos": doble}])
    assert ics(dedup.values()).count("BEGIN:VEVENT") == 1
    # Suspendido de verdad, sin fecha nueva.
    susp = ics(filtra("T", FM, 5, fila(esAplazado=True, **firme)).values())
    assert "SUMMARY:APLAZADO: " in susp and "STATUS:CONFIRMED" not in susp
    # Grupo que se queda sin partidos del club: parar, no publicar un feed recortado.
    for vacio in ([], [{"numero": "1", "partidos": []}],
                  fila(equipo_local="OTRO", equipo_visitante="OTRO", clubLocalId="1")):
        try:
            filtra("T", FM, 5, vacio)
        except SystemExit:
            pass
        else:
            raise AssertionError("un grupo sin partidos del club tiene que parar")
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        partidos = recoge()
        OUT.mkdir(exist_ok=True)
        # El .ics solo lleva los partidos en casa, que son a los que se va a ir.
        # partidos.json mantiene los 88 para que la web pueda quitar el filtro.
        en_casa = [p for p in partidos if p["casa"]]
        salidas = {
            OUT / "partidos.json": json.dumps(partidos, ensure_ascii=False, indent=1),
            OUT / "calendario.ics": ics(en_casa),
        }
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
        print(f"{len(partidos)} partidos, {len(en_casa)} en casa al .ics, "
              f'{sum(1 for p in en_casa if not p["confirmado"])} de ellos por confirmar')
