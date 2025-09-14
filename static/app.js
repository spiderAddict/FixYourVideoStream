// static/app.js
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

async function loadList(){
  const list = document.getElementById('fileList');
  list.innerHTML = "";
  const files = await api('/api/files');

  for (let f of files){
    const statusTag = f.analyzed_at
      ? `<span class="tag is-success">✓</span>`
      : `<span class="tag is-warning">⏳</span>`;

    const langTag = f.language
      ? `<span class="tag is-info">${f.language}</span>`
      : `<span class="tag is-light">?</span>`;

    const html = renderTemplate("list-item-template", {
      id: f.id,
      filename: f.filename,
      status: statusTag,
      language: langTag
    });

    const wrapper = document.createElement("li");
    wrapper.innerHTML = html;
    wrapper.querySelector("a").onclick = ()=>showDetail(f);
    list.appendChild(wrapper);
  }
}

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
      await api(`/api/files/${file.id}/reanalyze`, {method:'POST'});
      await loadList();
      showDetail(file);
    };
  }
  else {
     document.getElementById('analyze').onclick = async ()=>{
      await api(`/api/files/analyze`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({path:`${file.path}`,filename: `${file.filename}`}),
      });
      await loadList();
      showDetail(file);
    };
  }

  // Si le fichier a été analysé, proposer de la définir en français
  if (file.analyzed_at)
  {
    document.getElementById('setFr').onclick = async ()=>{
      await api(`/api/files/${file.id}/set_language`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({language:'fra'})
      });
      await loadList();
      showDetail(file);
    };
  }
  else 
    document.getElementById('setFr').disabled = true;
}

document.getElementById('analyzeAll').onclick = async () => {
    await api('/api/analyze_all', { method: 'POST' });
    await loadList();
};

document.getElementById('analyzeNew').onclick = async () => {
    await api('/api/analyze_new', { method: 'POST' });
    await loadList();
};

async function loadTheme(){
  const res = await api('/api/theme');
  document.body.dataset.theme = res.theme;
  document.getElementById('themeSelector').value = res.theme;
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
loadList().catch(e=>console.error(e));
loadTheme().catch(e=>console.error(e));


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