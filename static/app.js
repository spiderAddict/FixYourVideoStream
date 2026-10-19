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

function escapeHtml(text){
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Signale les fichiers en erreur après une analyse en masse
function notifyAnalysisErrors(res){
  if (res.errors) showNotification(`${res.errors} fichier(s) en erreur d'analyse`, "error");
}

function renderTemplate(templateId, data){
  let tpl = document.getElementById(templateId).innerHTML;
  for (let key in data){
    const regex = new RegExp(`{{${key}}}`, 'g');
    tpl = tpl.replace(regex, data[key]);
  }
  return tpl;
}

// Pastille de statut d'analyse dans la liste
const STATUS_TAGS = {
  analyzed: `<span class="tag is-success" title="Analysé">✓</span>`,
  not_analyzed: `<span class="tag is-warning" title="Pas encore analysé">⏳</span>`,
  error: `<span class="tag is-danger" title="Erreur d'analyse">✗</span>`
};

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
let currentPage = 1;
let pageSize = 10;

function renderPagination(total, page, pageSize) {
  const pageCount = Math.ceil(total / pageSize);
  const paginationList = document.getElementById('paginationList');
  paginationList.innerHTML = '';
  for (let i = 1; i <= pageCount; i++) {
    const li = document.createElement('li');
    li.innerHTML = `<a class="pagination-link${i === page ? ' is-current' : ''}" data-page="${i}">${i}</a>`;
    paginationList.appendChild(li);
  }
  document.getElementById('prevPage').disabled = (page === 1);
  document.getElementById('nextPage').disabled = (page === pageCount || pageCount === 0);

  // Ajout des événements
  paginationList.querySelectorAll('.pagination-link').forEach(link => {
    link.onclick = (e) => {
      currentPage = parseInt(e.target.dataset.page);
      renderList();
    };
  });
  document.getElementById('prevPage').onclick = () => {
    if (currentPage > 1) {
      currentPage--;
      renderList();
    }
  };
  document.getElementById('nextPage').onclick = () => {
    const pageCount = Math.ceil(allFiles.length / pageSize);
    if (currentPage < pageCount) {
      currentPage++;
      renderList();
    }
  };
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
  // Après un rechargement, la page courante peut ne plus exister (fichiers retirés)
  const pageCount = Math.max(1, Math.ceil(filteredFiles.length / pageSize));
  currentPage = Math.min(currentPage, pageCount);
  const start = (currentPage - 1) * pageSize;
  const end = start + pageSize;
  const files = filteredFiles.slice(start, end);

  for (let f of files) {
    const statusTag = STATUS_TAGS[f.status];

    const langTag = f.language
      ? `<span class="tag is-info">${f.language}</span>`
      : `<span class="tag is-light">?</span>`;

    const html = `
      <tr>
        <td>
          <a class="file-item" data-id="${f.id}" style="cursor:pointer">${f.filename}</a>
        </td>
        <td>${statusTag}</td>
        <td>${langTag}</td>
      </tr>
    `;

    const wrapper = document.createElement("tr");
    wrapper.innerHTML = html;
    wrapper.querySelector(".file-item").onclick = () => showDetail(f);
    list.appendChild(wrapper);
  }
  renderPagination(filteredFiles.length, currentPage, pageSize);
}

// Mets à jour la liste quand on change un filtre
document.addEventListener('DOMContentLoaded', () => {  
  const pageSizeSelect = document.getElementById('pageSize');
  if (pageSizeSelect) {
    pageSizeSelect.value = pageSize;
    pageSizeSelect.onchange = (e) => {
      pageSize = parseInt(e.target.value);
      currentPage = 1;
      renderList();
    };
  }
  document.getElementById('filterStatus').onchange = () => {
    currentPage = 1;
    renderList();
  };
  document.getElementById('filterLang').onchange = () => {
    currentPage = 1;
    renderList();
  };
  document.getElementById('filterName').oninput = () => {
    currentPage = 1;
    renderList();
  };
});

// Id du fichier affiché dans le panneau de détail
let currentDetailId = null;

async function showDetail(file){
  currentDetailId = file.id;
  const pane = document.getElementById('detailPane');
  pane.classList.remove('is-hidden');

  const analyzedTag = {
    analyzed: `<span class="tag is-success">Oui</span>`,
    not_analyzed: `<span class="tag is-warning">Non</span>`,
    error: `<span class="tag is-danger">Erreur</span> ${escapeHtml(file.analysis_error || '')}`
  }[file.status];

  const languageTag = file.language 
    ? `<span class="tag is-info">${file.language}</span>` 
    : `<span class="tag is-light">Inconnue</span>`;

  pane.innerHTML = renderTemplate("detail-template", {
    filename: file.filename,
    path: file.path,
    analyzed: analyzedTag,
    language: languageTag
  });
  
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

async function loadTheme(){
  const res = await api('/api/theme');
  document.body.dataset.theme = res.theme;
  document.getElementById('themeSelector').value = res.theme;
}

// Recharge la liste en gardant la page courante, et le détail ouvert à jour
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
    document.getElementById('detailPane').classList.add('is-hidden');
    currentDetailId = null;
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
