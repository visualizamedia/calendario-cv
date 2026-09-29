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

## Cambios que hacen las federaciones

Cada partido tiene un id propio y estable: al moverlo de fecha, de hora o de
jornada la federacion conserva ese id, asi que el UID del evento no cambia y
Google actualiza el evento en su sitio en vez de duplicarlo. El .ics es el
estado completo, no un historico: un partido que desaparece del calendario
federativo desaparece del feed y Google lo borra.

| Cambio | Resultado |
|---|---|
| Cierran la hora de un `00:00` | El evento de dia completo pasa a evento con hora |
| Cierran la hora pero aun no el pabellon | Evento con hora, sin sitio |
| Cambian el dia o la hora | El evento se mueve, mismo UID |
| Lo recolocan en otra jornada | Igual, y la descripcion anota de que jornada venia |
| Lo suspenden (`esAplazado`) | Titulo `APLAZADO:` y estado tentativo |
| El mismo partido asoma en dos jornadas | Un solo evento, sin UID repetido |
| Cambia el patrocinador del equipo | Se sigue reconociendo por id de club |

Dos frenos para no publicar un feed incompleto, que le haria borrar eventos a
Google sin avisar: la descarga para si un grupo devuelve el calendario vacio, y
`filtra` para si un grupo no trae ni un partido del club (grupoId caducado,
club movido de grupo o nombre irreconocible). En ambos casos la accion sale en
rojo y GitHub avisa por correo; el feed publicado se queda como estaba.

Todo esto lo cubre `python fetch.py --demo`, que es el primer paso de la accion.

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
`fetch.py`. Los `grupoId` tienen que ser distintos entre si, o los UID chocarian;
`recoge` lo comprueba. Los id de club de `CLUB` (9371 en la RFEVB, 21 en la
madrileña) no cambian de temporada.

## Local

```
python fetch.py --demo   # autocomprobacion
python fetch.py          # regenera docs/
```

Sin dependencias: solo biblioteca estandar.
