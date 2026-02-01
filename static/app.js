// static/app.js

// Charge la version de l'application
async function loadVersion() {
  try {
    const data = await api('/api/version');
    document.getElementById('appVersion').textContent = data.version;
  } catch (err) {
    console.error('Erreur lors du chargement de la version:', err);
    document.getElementById('appVersion').textContent = 'erreur';
  }
}

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

function renderTemplate(templateId, data){
  let tpl = document.getElementById(templateId).innerHTML;
  for (let key in data){
    const regex = new RegExp(`{{${key}}}`, 'g');
    tpl = tpl.replace(regex, data[key]);
  }
  return tpl;
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

    if (status === "analyzed") statusOk = !!f.analyzed_at;
    if (status === "not_analyzed") statusOk = !f.analyzed_at;
    if (lang) langOk = (f.language === lang);
    if (name) nameOk = f.filename.toLowerCase().includes(name);

    return statusOk && langOk && nameOk;
  });
}

function renderList() {
  const list = document.getElementById('fileList');
  list.innerHTML = "";
  const filteredFiles = getFilteredFiles();
  const start = (currentPage - 1) * pageSize;
  const end = start + pageSize;
  const files = filteredFiles.slice(start, end);

  for (let f of files) {
    const statusTag = f.analyzed_at
      ? `<span class="tag is-success">✓</span>`
      : `<span class="tag is-warning">⏳</span>`;

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
  // Charge la version
  loadVersion();
  
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

async function showDetail(file){
  const pane = document.getElementById('detailPane');
  pane.classList.remove('is-hidden');

  const analyzedTag = file.analyzed_at 
    ? `<span class="tag is-success">Oui</span>` 
    : `<span class="tag is-warning">Non</span>`;

  const languageTag = file.language 
    ? `<span class="tag is-info">${file.language}</span>` 
    : `<span class="tag is-light">Inconnue</span>`;

  pane.innerHTML = renderTemplate("detail-template", {
    filename: file.filename,
    path: file.path,
    analyzed: analyzedTag,
    language: languageTag
  });
  
  // Si le fichier n'a pas été analysé, proposer de le réanalyser
  if (file.analyzed_at){
    document.getElementById('analyze').onclick = async ()=>{
      try {
        showLoader();
        await api(`/api/files/${file.id}/reanalyze`, {method:'POST'});
        await loadList();
        showDetail(file);
      } catch (e) {
        showNotification("Erreur : " + e.message, "error");
      } finally {
        hideLoader();
      }
    };
  }
  else {
     document.getElementById('analyze').onclick = async ()=>{
      try {
        showLoader();
        await api(`/api/files/${file.id}/analyze`, {method:'POST'});
        await loadList();
        showDetail(file);
      } catch (e) {
        showNotification("Erreur : " + e.message, "error");
      } finally {
        hideLoader();
      }
    };
  }

  // Si le fichier a été analysé, proposer de la définir en français
  if (file.analyzed_at)
  {
    document.getElementById('setFr').onclick = async ()=>{
      try {
        showLoader();
        await api(`/api/files/${file.id}/set_language`, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({language:'fra'})
        });
        await loadList();
        showDetail(file);
      } catch (e) {
        showNotification("Erreur : " + e.message, "error");
      } finally {
        hideLoader();
      }
    };
  }
  else 
    document.getElementById('setFr').disabled = true;
}

document.getElementById('analyzeAll').onclick = async () => {
    try {
      showLoader();
      await api('/api/analyze_all', { method: 'POST' });
      await loadList();
    } catch (e) {
      showNotification("Erreur : " + e.message, "error");
    } finally {
      hideLoader();
    }
};

document.getElementById('rescan').onclick = async () => {
    try {
      showLoader();
      await api('/api/rescan', { method: 'POST' });
      await loadList();
    } catch (e) {
      showNotification("Erreur : " + e.message, "error");
    } finally {
      hideLoader();
    }
};

document.getElementById('analyzeNew').onclick = async () => {
    try {
      showLoader();
      await api('/api/analyze_new', { method: 'POST' });
      await loadList();
    } catch (e) {
      showNotification("Erreur : " + e.message, "error");
    } finally {
      hideLoader();
    }
};

async function loadTheme(){
  const res = await api('/api/theme');
  document.body.dataset.theme = res.theme;
  document.getElementById('themeSelector').value = res.theme;
}

async function loadList() {
  try {
    allFiles = await api('/api/files');
    currentPage = 1;
    renderList();
  } catch (e) {
    showNotification("Erreur lors du chargement de la liste : " + e.message, "error");
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