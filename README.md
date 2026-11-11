# Calendario de partidos de voleibol

Genera un calendario por club con los partidos de sus equipos, a partir de las
APIs publicas de la RFEVB y la Federacion de Madrid. Ahora mismo hay tres:

| Club | Equipos | Feed |
|---|---|---|
| CV Collado Villalba | los cuatro del club | `calendario.ics` |
| CV Majadahonda | senior femenino A | `majadahonda.ics` |
| CV Guadarrama | senior femenino Negro | `guadarrama.ics` |

La web es una sola pagina con un selector de club. Cada club tiene su propia
direccion para guardarla en marcadores: `?club=collado-villalba`,
`?club=majadahonda`, `?club=guadarrama`.

## Puesta en marcha

1. Crea un repositorio en GitHub y sube esta carpeta a la rama `main`.
2. Settings → Pages → Source: **Deploy from a branch**, rama `main`, carpeta `/docs`.
3. Settings → Actions → General → Workflow permissions: **Read and write permissions**.

La accion programada se ejecuta cada dia a las 05:00 UTC y vuelve a publicar
los ficheros de `docs/` solo si algo ha cambiado.

## Suscribir en Google Calendar

Otros calendarios → Añadir por URL:

```
https://<usuario>.github.io/<repo>/calendario.ics     # CV Collado Villalba
https://<usuario>.github.io/<repo>/majadahonda.ics    # CV Majadahonda
https://<usuario>.github.io/<repo>/guadarrama.ics     # CV Guadarrama
```

Son tres calendarios independientes: puedes suscribirte a uno, a dos o a los
tres, y en Google aparecen como calendarios separados que se pueden ocultar por
separado.

Cada feed lleva **solo los partidos en casa**, que son a los que se va a ir.
El `.json` de cada club conserva todos para que la web pueda quitar el filtro; para
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

## Arbitros

La descripcion de cada evento lleva la designacion, y mientras no hay nadie
apuntado pone `Arbitros: sin designar`: lo normal es que no llegue hasta los dias
previos al partido. Se actualiza en cada ejecucion.

La ficha del partido tiene cuatro huecos de designacion. La federacion los
publica como `Arbitro 1`, `Arbitro 2` y `Anotador`, asi que el tercero sale
aparte y los demas como arbitros:

    Arbitros: JOSE MANUEL TORRES TORRES, ALFONSO LOPEZ DIAZ - Anotador: JAIME RODRIGUEZ PEREZ

Un partido puede tener arbitro 1 y anotador sin arbitro 2, de modo que no vale
contar cuantos nombres vienen: hay que mirar en que hueco esta cada uno.

Los arbitros no vienen en el calendario del grupo, hay que pedir la ficha de cada
partido (`getPartido?partidoId=`), asi que solo se piden los de los partidos en
casa, que son los que van al `.ics`. Son unas 65 peticiones extra y la
ejecucion completa pasa de 3 a unos 20 segundos.

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
| Jornada de descanso (`Descansa...`, clubId 0) | No es partido: no genera evento |
| Designan o cambian a los arbitros | La descripcion del evento se actualiza |

Dos frenos para no publicar un feed incompleto, que le haria borrar eventos a
Google sin avisar: la descarga para si un grupo devuelve el calendario vacio, y
`filtra` para si un grupo no trae ni un partido del club (grupoId caducado,
club movido de grupo o nombre irreconocible). En ambos casos la accion sale en
rojo y GitHub avisa por correo; el feed publicado se queda como estaba.

Todo esto lo cubre `python fetch.py --demo`, que es el primer paso de la accion.

## Clubes, equipos y grupos

| Club | id de club | Equipo | API | grupoId |
|---|---|---|---|---|
| Collado Villalba | 9371 RFEVB / 21 Madrid | Masculino SM2 Grupo C | rfevb.fontventa.com | 87 |
| Collado Villalba | | Femenino SF2 Grupo C | rfevb.fontventa.com | 226 |
| Collado Villalba | | Senior Fem. 2a Aut. Preferente Grupo A | intranet.fmvoley.com | 34075 |
| Collado Villalba | | Junior Fem. 1a Aut. Preferente Unico | intranet.fmvoley.com | 33941 |
| Majadahonda | 19 Madrid | Senior Fem. 2a Aut. Preferente Grupo A (equipo A) | intranet.fmvoley.com | 34075 |
| Majadahonda | | ~~Senior Fem. 1a Aut. Zonal Grupo A (equipo B)~~ retirado | intranet.fmvoley.com | 34222 |
| Guadarrama | 155 Madrid | Senior Fem. 1a Aut. Zonal Grupo A (Negro) | intranet.fmvoley.com | 34222 |
| Guadarrama | | ~~Senior Fem. 2a Aut. Zonal Unico (Rojo)~~ retirado | intranet.fmvoley.com | 34229 |

El equipo B de Majadahonda y el Rojo de Guadarrama estan fuera de sus
calendarios por ahora: sus lineas siguen en `CLUBES`, comentadas, para
recuperarlos descomentandolas.

Ni Majadahonda ni Guadarrama tienen equipo senior femenino en competicion
nacional, asi que sus dos calendarios solo usan la API de la federacion
madrileña. Un mismo `grupoId` puede aparecer en dos clubes (Villalba y
Majadahonda A comparten el 34075); lo que no puede es repetirse dentro de un
club, y `recoge` lo comprueba.

Los `grupoId` cambian cada temporada. Para localizar los nuevos: abre la pagina
del grupo en esvoley.es o fmvoley.com y mira el parametro `grupoId` de las
llamadas a `/api/competiciones/` en la pestaña Red del navegador. Luego edita
`CLUBES` en `fetch.py`. Los id de club no cambian de temporada.

## Añadir un club

En `fetch.py`, un elemento mas en `CLUBES`: `slug`, `nombre`, `clave` (el
nombre en minusculas y sin tildes, que se usa como respaldo si el id de club
falla y es lo que la web resalta), `ids` por federacion y la lista de `grupos`.
Los ficheros de salida se llaman como el slug, y la web se entera por
`docs/clubes.json`: no hay que tocar el HTML.

## Local

```
python fetch.py --demo   # autocomprobacion
python fetch.py          # regenera docs/
```

Sin dependencias: solo biblioteca estandar.

## Marcador en vivo para vMix

`marcador.py` no tiene nada que ver con el calendario: lee el marcador de un
partido concreto y lo deja en CSV para usarlo como Data Source de vMix. Dos
fuentes, las dos publicas:

- `getPartido?partidoId=` da los sets y los parciales de cada set.
- `/Public/ResumenPartido.aspx?Id=` da el acta electronica: estado del partido,
  hora de comienzo, alineaciones con dorsal y nombre, colores de camiseta,
  tarjetas y el punto a punto con el minuto de cada accion. Solo existe desde
  que el arbitro abre el acta, y el punto a punto solo lo lleva la federacion
  madrileña (en las competiciones nacionales el acta no lo trae).

```
python marcador.py --hoy                     # partidos de hoy y su partidoId
python marcador.py --partido 58089 --bucle    # escribe vmix/*.csv cada 5 s
python marcador.py --partido 58089 --bucle --grupo 34075   # + clasificacion
python marcador.py --demo                     # autocomprobacion
```

En `vmix/` quedan `marcador.csv` (una fila con el estado), `jugadores.csv`,
`eventos.csv`, `clasificacion.csv` y `registro.csv` (el historico de la sesion,
para medir el retraso). Cada fichero se escribe en un temporal y se renombra
encima, asi vMix nunca lee uno a medias. En vMix: Settings > Data Sources > Add
> CSV, apuntar al fichero y poner el refresco en 1 s.

`hoja.gs` hace lo mismo contra una hoja de Google, para lo que no corra: el
activador de Apps Script no baja de un minuto.

Aviso: `getPartido` devuelve `finalizado: false` siempre, incluso semanas
despues del partido. El estado bueno es el del acta.
