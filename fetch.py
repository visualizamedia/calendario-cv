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
        return json.loads(r.read().decode("utf-8"))["content"]


def recoge():
    partidos = []
    for etiqueta, host, grupo_id in GRUPOS:
        for jornada in descarga(host, grupo_id):
            for p in jornada["partidos"]:
                local, visitante = p["equipo_local"], p["equipo_visitante"]
                if EQUIPO not in normaliza(local + " " + visitante):
                    continue
                dia, _, hora = p["fecha_hora"].partition(" ")
                d, m, a = (int(x) for x in dia.split("/"))
                h, _, mi = hora.partition(":")
                # La federacion publica 00:00 y pabellon vacio mientras no confirma.
                confirmado = bool(int(h)) and bool((p["pabellon"] or "").strip())
                partidos.append({
                    "id": f'{grupo_id}-{p["id"]}',
                    "competicion": etiqueta,
                    "jornada": jornada["numero"],
                    "fecha": date(a, m, d).isoformat(),
                    "hora": f"{int(h):02d}:{int(mi):02d}" if confirmado else None,
                    "local": local,
                    "visitante": visitante,
                    "pabellon": (p["pabellon"] or "").strip(),
                    "casa": EQUIPO in normaliza(local),
                    "confirmado": confirmado,
                    "aplazado": bool(p.get("esAplazado") or p.get("fechaAplazada")),
                })
    partidos.sort(key=lambda p: (p["fecha"], p["hora"] or "00:00"))
    return partidos


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
        "X-WR-CALNAME:CV Collado Villalba", "X-WR-TIMEZONE:Europe/Madrid",
    ] + VTIMEZONE
    for p in partidos:
        titulo = f'{p["local"]} - {p["visitante"]}'
        if p["aplazado"]:
            titulo = "APLAZADO: " + titulo
        elif not p["confirmado"]:
            titulo = "POR CONFIRMAR: " + titulo
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
            plegar(f'DESCRIPTION:{esc(p["competicion"])} - Jornada {p["jornada"]}'),
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
    }, {
        "id": "1-3", "competicion": "Test", "jornada": "2", "fecha": "2026-10-11",
        "hora": "16:30", "local": "A", "visitante": "B", "pabellon": "LOS CANTOS",
        "casa": True, "confirmado": True, "aplazado": False,
    }]
    salida = ics(p)
    assert "DTSTART;VALUE=DATE:20261011" in salida
    assert "SUMMARY:POR CONFIRMAR: A - B" in salida
    assert "DTSTART;TZID=Europe/Madrid:20261011T163000" in salida
    assert "DTEND;TZID=Europe/Madrid:20261011T183000" in salida
    assert "TZID:Europe/Madrid" in salida
    assert "DESCRIPTION:Test\; con coma\, y punto y coma - Jornada 1" in salida
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
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        partidos = recoge()
        OUT.mkdir(exist_ok=True)
        destino = OUT / "partidos.json"
        nuevo = json.dumps(partidos, ensure_ascii=False, indent=1)
        # DTSTAMP cambia en cada ejecucion, asi que no reescribimos si los datos son
        # identicos: evita un commit diario sin cambios reales.
        if destino.exists() and destino.read_text(encoding="utf-8") == nuevo:
            print("sin cambios")
            sys.exit()
        # newline="" desactiva la traduccion de saltos de linea: en Windows los
        # \r\n del iCalendar se escribirian como \r\r\n y el fichero saldria roto.
        destino.write_text(nuevo, encoding="utf-8", newline="\n")
        (OUT / "calendario.ics").write_text(ics(partidos), encoding="utf-8", newline="")
        print(f"{len(partidos)} partidos, "
              f'{sum(1 for p in partidos if not p["confirmado"])} por confirmar')
