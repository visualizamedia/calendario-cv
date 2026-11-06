/**
 * Marcador de la federación en una hoja de Google, para vMix.
 *
 * Instalación: en la hoja, Extensiones > Apps Script, pegar esto, poner PARTIDO y
 * HOST, y en "Activadores" añadir uno de tipo tiempo cada minuto sobre marcador().
 *
 * Aviso: el activador de Apps Script no baja de 1 minuto, y vMix además cachea la
 * hoja, así que por aquí el marcador llega con un retraso de minutos. Para el
 * marcador en directo usa marcador.py, que escribe un CSV local cada pocos
 * segundos. Esta hoja vale para lo que no corre: clasificación, alineaciones,
 * ficha del partido, o para tener el histórico a mano.
 */

var PARTIDO = 58089;
var HOST = 'https://intranet.fmvoley.com';   // nacional: https://rfevb.fontventa.com

function marcador() {
  var url = HOST + '/api/competiciones/getPartido?partidoId=' + PARTIDO;
  var p = JSON.parse(UrlFetchApp.fetch(url).getContentText()).content;
  // Los sets de getPartido cuentan tambien el set que se esta jugando, y se lo apuntan
  // a quien va ganando: con el partido en marcha no valen. Se cuentan los cerrados.
  var sl = 0, sv = 0;
  for (var i = 1; i <= 5; i++) {
    var l = Number(p['puntos_local_juego_' + i]), v = Number(p['puntos_visitante_juego_' + i]);
    var meta = (i === 5) ? 15 : 25;
    if (Math.max(l, v) >= meta && Math.abs(l - v) >= 2) { if (l > v) sl++; else sv++; }
  }
  var sets = sl + sv;
  // El set en juego es el siguiente a los ya cerrados; si alguien llega a 3, el último.
  var n = (sl < 3 && sv < 3) ? Math.min(sets + 1, 5) : Math.max(sets, 1);
  var fila = [
    new Date(), p.equipo_local, p.equipo_visitante, sl, sv, n,
    Number(p['puntos_local_juego_' + n]), Number(p['puntos_visitante_juego_' + n])
  ];
  for (var i = 1; i <= 5; i++) {
    fila.push(Number(p['puntos_local_juego_' + i]), Number(p['puntos_visitante_juego_' + i]));
  }
  var h = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  if (h.getLastRow() === 0) {
    h.appendRow(['hora', 'local', 'visitante', 'sets_local', 'sets_visitante', 'set',
                 'puntos_local', 'puntos_visitante', 's1l', 's1v', 's2l', 's2v',
                 's3l', 's3v', 's4l', 's4v', 's5l', 's5v']);
  }
  // La fila 2 es siempre el marcador actual: vMix lee siempre la misma celda.
  if (h.getLastRow() < 2) h.appendRow(fila);
  else h.getRange(2, 1, 1, fila.length).setValues([fila]);
}

/** La clasificación del grupo en la segunda hoja. Con llamarla una vez al día sobra. */
function clasificacion() {
  var GRUPO = 34075;
  var url = HOST + '/api/competiciones/getClasificacionGrupo?grupoId=' + GRUPO;
  var tabla = JSON.parse(UrlFetchApp.fetch(url).getContentText()).content;
  var filas = [['posicion', 'equipo', 'puntos', 'jugados', 'ganados', 'perdidos',
                'sets_favor', 'sets_contra']];
  tabla.forEach(function (e) {
    filas.push([e.posicion, e.nombre, e.puntos, e.jugados, e.ganados, e.perdidos,
                e.sets_a_favor, e.sets_en_contra]);
  });
  var libro = SpreadsheetApp.getActiveSpreadsheet();
  var h = libro.getSheetByName('clasificacion') || libro.insertSheet('clasificacion');
  h.clear();
  h.getRange(1, 1, filas.length, filas[0].length).setValues(filas);
}
