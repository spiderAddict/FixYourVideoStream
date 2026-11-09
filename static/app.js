// static/app.js

// Fonctions pour gérer le loader
function showLoader() {
  document.getElementById('loadingOverlay').classList.remove('is-hidden');
}

function hideLoader() {
  document.getElementById('loadingOverlay').classList.add('is-hidden');
}

async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) {
        const t = await r.text();
        throw new Error(t || r.statusText);
    }
    return r.json();
}

// Signale les fichiers en erreur après une analyse en masse
function notifyAnalysisErrors(res){
  if (res.errors) showNotification(`${res.errors} fichier(s) en erreur d'analyse`, "error");
}

// Crée un élément dont le contenu est posé en texte : les noms de fichiers, chemins
// et métadonnées viennent du disque et ne doivent jamais être interprétés comme du HTML
function el(tag, className, text){
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

// Pastille de statut d'analyse dans la liste
const STATUS_TAGS = {
  analyzed: {className: 'tag is-success', title: 'Analysé', text: '✓'},
  not_analyzed: {className: 'tag is-warning', title: 'Pas encore analysé', text: '⏳'},
  error: {className: 'tag is-danger', title: "Erreur d'analyse", text: '✗'}
};

function statusTag(status){
  const def = STATUS_TAGS[status];
  const tag = el('span', def.className, def.text);
  tag.title = def.title;
  return tag;
}

// Pastille de langue ; `unknownText` si aucune langue n'est renseignée
function languageTag(language, unknownText){
  return language ? el('span', 'tag is-info', language) : el('span', 'tag is-light', unknownText);
}

// Valeur du filtre de langue pour les fichiers sans langue renseignée
const NO_LANGUAGE = '__none__';
const languageNames = new Intl.DisplayNames(['fr'], {type: 'language'});

// Libellé lisible d'un code langue ISO 639 (« fra » -> « français (fra) »)
function languageLabel(code){
  if (code === 'und') return `indéterminée (${code})`;
  let name = code;
  try { name = languageNames.of(code); } catch (e) { /* code non reconnu */ }
  return name === code ? code : `${name} (${code})`;
}

// Construit le filtre de langue à partir des codes réellement présents
// (ffprobe renvoie des codes ISO 639-2 comme « fra », « eng »)
function refreshLanguageFilter(){
  const select = document.getElementById('filterLang');
  const current = select.value;
  const codes = [...new Set(allFiles.map(f => f.language).filter(Boolean))]
    .sort((a, b) => languageLabel(a).localeCompare(languageLabel(b), 'fr'));

  select.innerHTML = '';
  select.add(new Option('Toutes les langues', ''));
  for (const code of codes) select.add(new Option(languageLabel(code), code));
  if (allFiles.some(f => !f.language)) select.add(new Option('Inconnue', NO_LANGUAGE));

  // Conserve la sélection si la langue existe toujours
  select.value = [...select.options].some(o => o.value === current) ? current : '';
}

let allFiles = [];
// Nombre de lignes ajoutées à chaque clic sur « Plus de films »
let pageSize = 10;
// Nombre de lignes affichées ; conservé lors d'un rechargement de la liste
let visibleCount = pageSize;

// Repart du premier lot quand le contenu de la liste change (filtre, taille de lot)
function resetVisibleCount() {
  visibleCount = pageSize;
  renderList();
}

function renderListFooter(shown, total) {
  document.getElementById('listCount').textContent = total === 0
    ? 'Aucun film'
    : `${shown} / ${total} film(s) affiché(s)`;
  document.getElementById('loadMore').classList.toggle('is-hidden', shown >= total);
}

function getFilteredFiles() {
  const status = document.getElementById('filterStatus').value;
  const lang = document.getElementById('filterLang').value;
  const name = document.getElementById('filterName').value.toLowerCase();

  return allFiles.filter(f => {
    let statusOk = true;
    let langOk = true;
    let nameOk = true;

    if (status) statusOk = (f.status === status);
    if (lang === NO_LANGUAGE) langOk = !f.language;
    else if (lang) langOk = (f.language === lang);
    if (name) nameOk = f.filename.toLowerCase().includes(name);

    return statusOk && langOk && nameOk;
  });
}

function renderList() {
  const list = document.getElementById('fileList');
  list.innerHTML = "";
  const filteredFiles = getFilteredFiles();
  const files = filteredFiles.slice(0, visibleCount);

  for (let f of files) {
    const link = el('a', 'file-item', f.filename);
    link.dataset.id = f.id;
    link.onclick = () => showDetail(f);

    const row = document.createElement('tr');
    for (const content of [link, statusTag(f.status), languageTag(f.language, '?')]) {
      row.appendChild(el('td')).appendChild(content);
    }
    list.appendChild(row);
  }
  renderListFooter(files.length, filteredFiles.length);
}

// Mets à jour la liste quand on change un filtre
document.addEventListener('DOMContentLoaded', () => {
  const pageSizeSelect = document.getElementById('pageSize');
  pageSizeSelect.value = pageSize;
  pageSizeSelect.onchange = (e) => {
    pageSize = parseInt(e.target.value);
    resetVisibleCount();
  };
  document.getElementById('loadMore').onclick = () => {
    visibleCount += pageSize;
    renderList();
  };
  document.getElementById('filterStatus').onchange = resetVisibleCount;
  document.getElementById('filterLang').onchange = resetVisibleCount;
  document.getElementById('filterName').oninput = resetVisibleCount;

  // Fermeture de la modale : fond, croix, touche Échap
  document.querySelectorAll('[data-close-detail]').forEach(e => { e.onclick = closeDetail; });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && currentDetailId !== null) closeDetail();
  });
});

// Id du fichier affiché dans la modale de détail
let currentDetailId = null;

function openDetailModal() {
  document.getElementById('detailModal').classList.add('is-active');
  // Bloque le défilement de la liste sous la modale
  document.documentElement.classList.add('is-clipped');
}

function closeDetail() {
  currentDetailId = null;
  document.getElementById('detailModal').classList.remove('is-active');
  document.documentElement.classList.remove('is-clipped');
}

async function showDetail(file){
  currentDetailId = file.id;
  const pane = document.getElementById('detailPane');
  openDetailModal();

  // Le template est statique ; les données sont ensuite posées en texte dans ses emplacements
  pane.innerHTML = document.getElementById('detail-template').innerHTML;
  const field = name => pane.querySelector(`[data-field="${name}"]`);
  field('filename').textContent = file.filename;
  field('path').textContent = file.path;

  const analyzed = field('analyzed');
  if (file.status === 'error') {
    analyzed.append(el('span', 'tag is-danger', 'Erreur'), ' ' + (file.analysis_error || ''));
  } else {
    analyzed.append(file.status === 'analyzed'
      ? el('span', 'tag is-success', 'Oui')
      : el('span', 'tag is-warning', 'Non'));
  }
  field('language').append(languageTag(file.language, 'Inconnue'));

  if (file.path.toLowerCase().endsWith('.avi')) {
    const convertButton = el('button', 'button is-info', 'Convertir en MKV');
    convertButton.type = 'button';
    convertButton.onclick = async () => {
      try {
        showLoader();
        await api(`/api/files/${file.id}/convert_to_mkv`, {method:'POST'});
        await loadList();
        showNotification('Conversion en MKV terminée.', 'success');
      } catch (e) {
        showNotification("Erreur : " + e.message, "error");
      } finally {
        hideLoader();
      }
    };
    pane.querySelector('.detail-actions').appendChild(convertButton);
  }

  // Analyse si jamais faite, réanalyse sinon
  const analyzeUrl = file.analyzed_at
    ? `/api/files/${file.id}/reanalyze`
    : `/api/files/${file.id}/analyze`;
  document.getElementById('analyze').onclick = async ()=>{
    try {
      showLoader();
      const res = await api(analyzeUrl, {method:'POST'});
      if (res.error) showNotification("Analyse en échec : " + res.error, "error");
      await loadList();
    } catch (e) {
      showNotification("Erreur : " + e.message, "error");
    } finally {
      hideLoader();
    }
  };

  // Forcer le français sur la piste audio choisie
  document.getElementById('setFr').onclick = async ()=>{
    const selected = document.querySelector('input[name="audioTrack"]:checked');
    if (!selected) return;
    try {
      showLoader();
      await api(`/api/files/${file.id}/set_language`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({language:'fra', track: parseInt(selected.value)})
      });
      await loadList();
    } catch (e) {
      showNotification("Erreur : " + e.message, "error");
    } finally {
      hideLoader();
    }
  };

  await loadTracks(file);
}

// Affiche les pistes audio du fichier et active « Forcer FR » si le conteneur le permet
async function loadTracks(file){
  const container = document.getElementById('tracks');
  const setFr = document.getElementById('setFr');
  let data;
  try {
    data = await api(`/api/files/${file.id}/tracks`);
  } catch (e) {
    container.textContent = "Impossible de lire les pistes audio.";
    return;
  }
  // Le panneau a pu être réaffiché pour un autre fichier entre-temps
  if (document.getElementById('tracks') !== container) return;

  container.innerHTML = '';
  if (data.tracks.length === 0) {
    container.textContent = "Aucune piste audio.";
    return;
  }
  for (const t of data.tracks) {
    const label = document.createElement('label');
    label.className = 'radio is-block';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'audioTrack';
    radio.value = t.track;
    // Présélectionne la piste principale (celle lue par défaut)
    radio.checked = t.default || (t.track === 0 && !data.tracks.some(x => x.default));
    label.appendChild(radio);
    const desc = [`#${t.track}`, t.language || '?', t.codec, t.title, t.default ? '(défaut)' : null]
      .filter(Boolean).join(' · ');
    label.appendChild(document.createTextNode(' ' + desc));
    container.appendChild(label);
  }

  if (data.language_editable) {
    setFr.disabled = false;
  } else {
    const warn = document.createElement('p');
    warn.className = 'is-size-7 has-text-danger';
    warn.textContent = "Ce format de fichier ne permet pas d'enregistrer la langue des pistes.";
    container.appendChild(warn);
  }
}

const DEFAULT_LOADER_TEXT = "Chargement en cours...";

function setLoaderText(text) {
  document.querySelector('#loadingOverlay .loading-text').textContent = text;
}

// Suit l'analyse en masse côté serveur jusqu'à sa fin, avec l'avancement dans le loader
async function followJob() {
  try {
    showLoader();
    let job = await api('/api/jobs/current');
    while (job.running) {
      setLoaderText(`Analyse en cours : ${job.done} / ${job.total}`);
      await new Promise(resolve => setTimeout(resolve, 1000));
      job = await api('/api/jobs/current');
    }
    if (job.error) showNotification(`Analyse interrompue après ${job.done} / ${job.total} fichier(s) : ${job.error}`, "error");
    else notifyAnalysisErrors(job);
    await loadList();
  } catch (e) {
    showNotification("Erreur : " + e.message, "error");
  } finally {
    setLoaderText(DEFAULT_LOADER_TEXT);
    hideLoader();
  }
}

// Démarre une analyse en masse (tâche de fond) puis suit son avancement
async function startBulkAnalysis(url) {
  try {
    // Une analyse lancée ailleurs (autre onglet) est suivie au lieu d'être refusée
    const current = await api('/api/jobs/current');
    if (!current.running) await api(url, { method: 'POST' });
  } catch (e) {
    showNotification("Erreur : " + e.message, "error");
    return;
  }
  await followJob();
}

document.getElementById('analyzeAll').onclick = () => startBulkAnalysis('/api/analyze_all');

document.getElementById('rescan').onclick = async () => {
    try {
      showLoader();
      const res = await api('/api/rescan', { method: 'POST' });
      showNotification(`${res.count} fichier(s) ajouté(s), ${res.removed} retiré(s)`, "success");
      if (res.purge_skipped) {
        showNotification("Répertoire vidéo absent ou vide (volume non monté ?) : fichiers disparus conservés", "error");
      }
      await loadList();
    } catch (e) {
      showNotification("Erreur : " + e.message, "error");
    } finally {
      hideLoader();
    }
};

document.getElementById('analyzeNew').onclick = () => startBulkAnalysis('/api/analyze_new');

async function loadVersion(){
  const res = await api('/api/version');
  document.getElementById('appVersion').textContent = res.version;
}

async function loadTheme(){
  const res = await api('/api/theme');
  document.body.dataset.theme = res.theme;
  document.getElementById('themeSelector').value = res.theme;
}

// Recharge la liste en gardant les lignes déjà affichées, et le détail ouvert à jour
async function loadList() {
  try {
    allFiles = await api('/api/files');
    refreshLanguageFilter();
    renderList();
    await refreshDetail();
  } catch (e) {
    showNotification("Erreur lors du chargement de la liste : " + e.message, "error");
  }
}

// Réaffiche le détail ouvert avec les données rechargées, ou le ferme si le fichier a été retiré
async function refreshDetail() {
  if (currentDetailId === null) return;
  const file = allFiles.find(f => f.id === currentDetailId);
  if (file) {
    await showDetail(file);
  } else {
    closeDetail();
  }
}
document.getElementById('themeSelector').onchange = async (e)=>{
  const theme = e.target.value;
  await api('/api/theme', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({theme})
  });
  document.body.dataset.theme = theme;
  showNotification(`Thème ${theme} appliqué !`, "success");
};

// Charger la liste et le thème au démarrage
document.addEventListener('DOMContentLoaded', () => {
  loadList().catch(e => console.error(e));
  loadTheme().catch(e => console.error(e));
  loadVersion().catch(e => console.error(e));
  // Reprend le suivi d'une analyse en masse lancée avant le rechargement de la page
  api('/api/jobs/current')
    .then(job => { if (job.running) followJob(); })
    .catch(e => console.error(e));
});

/**
 * Afficher une notification temporaire
 * @param {*} message 
 * @param {*} type 
 * Exemple d'utilisation :
 * showNotification("Analyse terminée avec succès !", "success");
 * showNotification("Erreur lors de l'analyse.", "error");
 */
function showNotification(message, type = "success") {
  const container = document.getElementById("notification-container");
  const notif = document.createElement("div");
  notif.className = `notification-message ${type}`;
  notif.textContent = message;
  container.appendChild(notif);
  setTimeout(() => {
    notif.remove();
  }, 3500);
}
