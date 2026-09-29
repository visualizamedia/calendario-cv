# Calendario CV Collado Villalba

Genera un calendario unificado con los partidos de los cuatro equipos del club,
a partir de las APIs publicas de la RFEVB y la Federacion de Madrid.

## Puesta en marcha

1. Crea un repositorio en GitHub y sube esta carpeta a la rama `main`.
2. Settings → Pages → Source: **Deploy from a branch**, rama `main`, carpeta `/docs`.
3. Settings → Actions → General → Workflow permissions: **Read and write permissions**.

La accion programada se ejecuta cada dia a las 05:00 UTC y vuelve a publicar
`docs/partidos.json` y `docs/calendario.ics` solo si algo ha cambiado.

## Suscribir en Google Calendar

Otros calendarios → Añadir por URL:

```
https://<usuario>.github.io/<repo>/calendario.ics
```

El feed lleva **solo los partidos en casa**, que son a los que se va a ir.
`partidos.json` conserva los 88 para que la web pueda quitar el filtro; para
llevarte un partido de fuera al calendario, usa el boton **+ Google** de esa
fila. Si algun dia quieres el feed completo, quita el filtro `en_casa` del
bloque final de `fetch.py`.

Google relee el feed cada 12-24 horas por su cuenta; no es instantaneo.
Para un partido concreto y al momento, usa el boton **+ Google** de cada fila
en la web, que crea el evento directamente.

## Partidos sin confirmar

Las federaciones publican los partidos aun sin cerrar con hora `00:00` y sin
pabellon. Esos salen como evento de dia completo marcado `POR CONFIRMAR`, y se
convierten en evento con hora en cuanto la federacion lo publica.

## Equipos y grupos

| Equipo | API | grupoId |
|---|---|---|
| Masculino SM2 Grupo C | rfevb.fontventa.com | 87 |
| Femenino SF2 Grupo C | rfevb.fontventa.com | 226 |
| Senior Fem. 2a Aut. Preferente Grupo A | intranet.fmvoley.com | 34075 |
| Junior Fem. 1a Aut. Preferente Unico | intranet.fmvoley.com | 33941 |

Cambian cada temporada. Para localizar los nuevos: abre la pagina del grupo en
esvoley.es o fmvoley.com y mira el parametro `grupoId` de las llamadas a
`/api/competiciones/` en la pestaña Red del navegador. Luego edita `GRUPOS` en
`fetch.py`.

## Local

```
python fetch.py --demo   # autocomprobacion
python fetch.py          # regenera docs/
```

Sin dependencias: solo biblioteca estandar.
