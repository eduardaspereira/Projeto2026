// JS principal extraído do template HTML
let currentPage = 1;
let currentDocId = null;
let currentEntityId = null; // Mantido no escopo global

function showView(id, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('view-' + id).classList.add('active');
  if (btn) btn.classList.add('active');
  if (id === 'estatisticas') loadStats();
  if (id === 'adicionar') loadAddedItems();
}

function showToast(msg, err=false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (err ? ' error' : '');
  setTimeout(() => t.className = 'toast', 3000);
}

async function search(page=1) {
  currentPage = page;
  const q = document.getElementById('q').value;
  const categoria = document.getElementById('f-categoria').value;
  const serie = document.getElementById('f-serie').value;
  const vigor = document.getElementById('f-vigor').value;
  const anoIni = document.getElementById('f-ano-ini').value;
  const anoFim = document.getElementById('f-ano-fim').value;
  const entidade = document.getElementById('f-entidade').value;

  const params = new URLSearchParams({q, categoria, serie, vigor,
    ano_ini: anoIni, ano_fim: anoFim, entidade, page, per_page: 25});

  document.getElementById('result-info').innerHTML =
    'A pesquisar... <span class="loader"></span>';

  const res = await fetch('/api/search?' + params);
  const data = await res.json();
  renderResults(data);
}

function renderResults(data) {
  const tbody = document.getElementById('results-tbody');
  const info  = document.getElementById('result-info');
  const pag   = document.getElementById('pagination');

  if (!data.results.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--cinza3);padding:2rem">
      Nenhum resultado encontrado.</td></tr>`;
    info.innerHTML = '<span>0 resultados</span>';
    pag.innerHTML = '';
    return;
  }

  info.innerHTML = `<strong>${data.total.toLocaleString('pt-PT')}</strong> resultados
    — página <strong>${data.page}</strong> de <strong>${data.pages}</strong>`;

  tbody.innerHTML = data.results.map(r => {
    const badgeClass = r.categoria === 'Ato Normativo' ? 'badge-norm'
                     : r.categoria === 'Ato Administrativo' ? 'badge-adm'
                     : r.categoria === 'Ato Informativo' ? 'badge-info' : 'badge-outro';
    const vigencia = r.in_force
      ? '<span class="vigente">● Em vigor</span>'
      : '<span class="revogado">○ Revogado</span>';
    const pdf = r.url_pdf
      ? `<a href="${r.url_pdf}" target="_blank" class="link-doc" title="Abrir PDF">📄</a>` : '—';
    const shortSumario = (r.sumario||'').length > 120
      ? r.sumario.slice(0,120) + '…' : (r.sumario||'—');

    return `<tr style="cursor:pointer">
      <td><span style="font-family:var(--mono);font-size:.75rem">${r.claint||'—'}</span></td>
      <td><span class="badge ${badgeClass}">${(r.doc_type||'').slice(0,22)}</span></td>
      <td style="font-family:var(--mono);font-size:.75rem">${r.numero||'—'}</td>
      <td style="font-family:var(--mono);font-size:.75rem;white-space:nowrap">${r.data||'—'}</td>
      <td style="text-align:center;font-family:var(--mono)">S${r.serie||'?'}</td>
      <td style="max-width:320px;font-size:.78rem">${shortSumario}</td>
      <td>${vigencia}</td>
      <td>${pdf}</td>
      <td>
        <button class="btn btn-secondary" onclick="openDocFromTable(event, ${r.id})">Abrir</button>
        <button class="btn btn-danger" onclick="removeDoc(event, ${r.id})">Remover</button>
      </td>
    </tr>`;
  }).join('');

  // Paginação
  const pages = data.pages;
  const cur = data.page;
  let pagHtml = '';
  if (cur > 1) pagHtml += `<button class="page-btn" onclick="search(${cur-1})">‹ Anterior</button>`;
  const start = Math.max(1, cur-3), end = Math.min(pages, cur+3);
  if (start > 1) pagHtml += `<button class="page-btn" onclick="search(1)">1</button><span>…</span>`;
  for (let p = start; p <= end; p++) {
    pagHtml += `<button class="page-btn ${p===cur?'current':''}" onclick="search(${p})">${p}</button>`;
  }
  if (end < pages) pagHtml += `<span>…</span><button class="page-btn" onclick="search(${pages})">${pages}</button>`;
  if (cur < pages) pagHtml += `<button class="page-btn" onclick="search(${cur+1})">Seguinte ›</button>`;
  pag.innerHTML = pagHtml;
}

function openDocFromTable(ev, id) {
  ev.stopPropagation();
  openDoc(id);
}

async function removeDoc(ev, id) {
  ev.stopPropagation();
  if (!confirm('Eliminar documento e todas as suas ligações?')) return;
  const res = await fetch('/api/documento/' + id, { method: 'DELETE' });
  const d = await res.json();
  if (d.ok) { showToast('Documento removido'); search(currentPage); }
  else showToast('Erro: ' + (d.error||''), true);
}

async function openDoc(id) {
  currentDocId = id;
  const res = await fetch('/api/documento/' + id);
  const d = await res.json();

  document.getElementById('modal-title').textContent =
    (d.doc_type || 'Documento') + (d.numero ? ' n.º ' + d.numero : '');

  const badgeClass = d.categoria === 'Ato Normativo' ? 'badge-norm'
                   : d.categoria === 'Ato Administrativo' ? 'badge-adm'
                   : 'badge-info';

  const rels = (d.relacoes || []).map(r => {
    let otherClaint = '';
    let otherNumero = '';
    let suffix = '';
    if (r.direcao === 'origem') {
      otherClaint = r.claint_destino;
      otherNumero = r.numero_destino;
      suffix = ' (destino)';
    } else {
      otherClaint = r.claint_origem;
      otherNumero = r.numero_origem;
      suffix = ' (origem)';
    }
    const badge = r.tipo_exibicao || r.tipo_relacao;
    let relationText = '';
    if (badge === 'revoga') {
      relationText = `${r.claint_destino || '—'} — ${r.numero_destino || '—'}`;
    } else if (badge === 'revogadoPor') {
      relationText = `${r.claint_origem || '—'} — ${r.numero_origem || '—'}`;
    } else {
      const origemTxt = `Origem: ${r.claint_origem || '—'} — ${r.numero_origem || '—'}`;
      const destinoTxt = `Destino: ${r.claint_destino || '—'} — ${r.numero_destino || '—'}`;
      relationText = `${origemTxt} → ${destinoTxt}`;
    }
    return `<div class="rel-item">
      <span class="rel-tipo">${badge}</span>
      <div style="margin-left:0.5rem;font-size:.9rem;color:var(--cinza3)">${relationText}</div>
      <button class="btn btn-danger" style="margin-left:auto" onclick="removeRelacao(event, ${r.rel_id})">Remover</button>
    </div>`;
  }).join('') || '<span style="color:var(--cinza3);font-size:.8rem">Sem relações registadas</span>';

  document.getElementById('modal-body').innerHTML = `
    <div class="meta-grid">
      <dl class="meta-item"><dt>Claint</dt><dd style="font-family:var(--mono)">${d.claint||'—'}</dd></dl>
      <dl class="meta-item"><dt>Classe OWL</dt><dd><span class="badge ${badgeClass}">${d.owl_class||'—'}</span></dd></dl>
      <dl class="meta-item"><dt>Número</dt><dd>${d.numero||'—'}</dd></dl>
      <dl class="meta-item"><dt>DR / Número</dt><dd style="font-family:var(--mono)">${d.dr_number||'—'}</dd></dl>
      <dl class="meta-item"><dt>Série</dt><dd>Série ${d.serie||'—'}</dd></dl>
      <dl class="meta-item"><dt>Data</dt><dd>${d.data||'—'}</dd></dl>
      <dl class="meta-item"><dt>Vigência</dt><dd>${d.in_force ? '✅ Em vigor' : '❌ Revogado'}</dd></dl>
      <dl class="meta-item"><dt>Entidade(s)</dt><dd style="font-size:.8rem">${(d.entidades||[]).join('<br>') || '—'}</dd></dl>
    </div>
    ${d.sumario ? `<div class="sumario-box">${d.sumario}</div>` : ''}
    <div style="display:flex;gap:.5rem;margin:.75rem 0;flex-wrap:wrap">
      ${d.url_pdf ? `<a href="${d.url_pdf}" target="_blank" class="btn btn-primary" style="font-size:.8rem;text-decoration:none">📄 Ver PDF</a>` : ''}
      ${d.url_texto ? `<a href="${d.url_texto}" target="_blank" class="btn btn-secondary" style="font-size:.8rem;text-decoration:none">📝 Texto integral</a>` : ''}
    </div>
    <div class="rel-section">
      <h4>🔗 Relações com outros documentos</h4>
      ${rels}
      <div class="rel-form">
        <select id="rel-tipo">
          <option value="revoga">revoga</option>
          <option value="revogadoPor">revogado por</option>
          <option value="alteradoPor">alterado por</option>
          <option value="rectificadoPor">retificado por</option>
          <option value="suspensoPor">suspenso por</option>
          <option value="desenvolve">desenvolve</option>
        </select>
        <input type="number" id="rel-claint" placeholder="claint destino" style="width:130px">
        <button class="btn btn-primary" onclick="addRelacao()">Adicionar</button>
      </div>
    </div>
    <div style="font-family:var(--mono);font-size:.68rem;color:var(--cinza3);margin-top:1rem">
      Fonte: ${d.fonte||'—'}<br>Criado: ${d.timestamp||'—'}
    </div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
}

async function addRelacao() {
  const tipo = document.getElementById('rel-tipo').value;
  const claint = document.getElementById('rel-claint').value;
  if (!claint) { showToast('Introduza o claint do documento destino', true); return; }
  const res = await fetch('/api/relacao', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({doc_id: currentDocId, tipo_relacao: tipo, claint_destino: parseInt(claint)})
  });
  const d = await res.json();
  if (d.ok) { showToast('Relação adicionada!'); openDoc(currentDocId); }
  else showToast('Erro: ' + (d.error||''), true);
}

async function addDocument(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd);
  const res = await fetch('/api/documento', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  const d = await res.json();
  if (d.ok) {
    showToast('Documento adicionado à ontologia!');
    e.target.reset();
    loadAddedItems();
  } else showToast('Erro: ' + (d.error||''), true);
}

async function addEntity(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd);

  // Recolher campos da classe OWL personalizada
  const localname = (document.getElementById('owl-class-localname')?.value || '').trim();
  const parent    = (document.getElementById('owl-class-parent')?.value || '').trim();
  const label     = (document.getElementById('owl-class-label')?.value || '').trim();

  // Garantir que o campo tipo tem o valor correcto (dre:NomeClasse)
  if (localname) {
    body.tipo = 'dre:' + localname;
  }

  const res = await fetch('/api/entidade', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  const d = await res.json();
  if (d.ok) {
    // Injetar a nova classe na árvore de ontologia (persistida em localStorage)
    if (localname) {
      saveCustomClass(localname, parent, label);
    }

    let msg = 'Entidade adicionada!';
    if (d.linked_documents && d.linked_documents > 0) {
      msg += ` ${d.linked_documents} documento(s) ligados automaticamente à entidade.`;
    }
    showToast(msg);
    e.target.reset();
    // Limpar campos manuais e pré-visualização
    if (document.getElementById('owl-class-localname')) document.getElementById('owl-class-localname').value = '';
    if (document.getElementById('owl-class-parent'))    document.getElementById('owl-class-parent').value = '';
    if (document.getElementById('owl-class-label'))     document.getElementById('owl-class-label').value = '';
    if (document.getElementById('owl-preview'))         { document.getElementById('owl-preview').style.display='none'; }
    if (document.getElementById('owl-class-final'))     document.getElementById('owl-class-final').value = 'dre:EntidadeEmissora';
    loadAddedItems();
  } else showToast('Erro: ' + (d.error||''), true);
}

async function loadAddedItems() {
  const res = await fetch('/api/adicionados');
  const d = await res.json();

  document.getElementById('new-docs-list').innerHTML = d.docs.length
    ? d.docs.map(doc => `
      <div style="display:flex;gap:.75rem;align-items:flex-start;padding:.5rem 0;border-bottom:1px solid var(--cinza1)">
        <span class="badge badge-norm">${doc.owl_class}</span>
        <div>
          <div style="font-size:.82rem;font-weight:500">${doc.numero||'—'} <span style="font-family:var(--mono);font-size:.7rem;color:var(--cinza3)">${doc.data||''}</span></div>
          <div style="font-size:.75rem;color:var(--cinza3)">${(doc.sumario||'').slice(0,100)}</div>
        </div>
        <div style="margin-left:auto;display:flex;gap:.3rem">
          <button class="btn btn-secondary" onclick="openRascunho(event, ${doc.id})">Abrir</button>
          <button class="btn btn-danger" onclick="removeAddedDoc(event, ${doc.id})">Remover</button>
        </div>
      </div>`).join('')
    : '<div style="font-size:.8rem;color:var(--cinza3)">Nenhum documento adicionado ainda.</div>';

  document.getElementById('new-entities-list').innerHTML = d.entidades.length
    ? d.entidades.map(e => `
      <div style="padding:.3rem 0;border-bottom:1px solid var(--cinza1)">
        <span style="font-family:var(--mono);font-size:.72rem;color:var(--verde2)">${e.tipo}</span>
        <div style="font-size:.82rem;font-weight:500">${e.nome}</div>
        ${e.descricao ? `<div style="font-size:.73rem;color:var(--cinza3)">${e.descricao}</div>` : ''}
        <div style="margin-top:.3rem">
          <button class="btn btn-secondary" onclick="openEntity(null, ${e.id})">Abrir</button>
          <button class="btn btn-danger" onclick="removeAddedEntity(event, ${e.id})">Remover</button>
        </div>
      </div>`).join('')
    : '<div style="font-size:.8rem;color:var(--cinza3)">Nenhuma entidade adicionada ainda.</div>';
}

async function removeAddedDoc(ev, id) {
  ev.stopPropagation();
  if (!confirm('Eliminar documento adicionado?')) return;
  const res = await fetch('/api/documento_novo/' + id, { method: 'DELETE' });
  const d = await res.json();
  if (d.ok) { showToast('Documento removido'); loadAddedItems(); search(currentPage); }
  else showToast('Erro: ' + (d.error||''), true);
}

async function openRascunho(ev, id) {
  ev.stopPropagation();
  const res = await fetch('/api/documento_novo/' + id);
  if (!res.ok) { showToast('Rascunho não encontrado', true); return; }
  const d = await res.json();

  document.getElementById('modal-title').textContent = (d.owl_class || 'Documento') + (d.numero ? ' n.º ' + d.numero : '');
  document.getElementById('modal-body').innerHTML = `
    <div class="meta-grid">
      <dl class="meta-item"><dt>Classe OWL</dt><dd><span class="badge badge-norm">${d.owl_class||'—'}</span></dd></dl>
      <dl class="meta-item"><dt>Número</dt><dd>${d.numero||'—'}</dd></dl>
      <dl class="meta-item"><dt>Data</dt><dd>${d.data||'—'}</dd></dl>
      <dl class="meta-item"><dt>Entidade(s)</dt><dd style="font-size:.8rem">${(d.entidades||'') || '—'}</dd></dl>
    </div>
    ${d.sumario ? `<div class="sumario-box">${d.sumario}</div>` : ''}
    <div style="font-family:var(--mono);font-size:.68rem;color:var(--cinza3);margin-top:1rem">
      Fonte: ${d.fonte||'—'}<br>
      Criado: ${d.criado_em||'—'}
    </div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

async function removeAddedEntity(ev, id) {
  ev.stopPropagation();
  if (!confirm('Eliminar entidade adicionada?')) return;
  const res = await fetch('/api/entidade/' + id, { method: 'DELETE' });
  const d = await res.json();
  if (d.ok) { showToast('Entidade removida'); loadAddedItems(); }
  else showToast('Erro: ' + (d.error||''), true);
}

async function openEntity(ev, id) {
  if (ev && typeof ev.stopPropagation === 'function') ev.stopPropagation();
  currentEntityId = id;
  
  const res = await fetch('/api/entidade/' + id + '/docs');
  const d = await res.json();
  const title = d.entity || 'Entidade';
  const docs = d.docs || [];
  const entityTipo = d.entity_tipo;
  
  document.getElementById('modal-title').textContent = `Entidade: ${title}` + (entityTipo ? ` — ${entityTipo}` : '');
  
  if (!docs.length) {
    document.getElementById('modal-body').innerHTML = '<div style="color:var(--cinza3);padding:1rem 0">Sem documentos associados.</div>';
  } else {
    document.getElementById('modal-body').innerHTML = `
      <div style="display:flex;flex-direction:column;gap:.5rem">
        ${docs.map(doc => `
          <div style="display:flex;align-items:center;gap:.5rem;border-bottom:1px solid var(--cinza1);padding:.5rem 0">
            <div style="flex:1">
              <div style="font-weight:600">${doc.doc_type || doc.owl_class || 'Documento' } ${doc.numero ? '— ' + doc.numero : ''}</div>
              <div style="font-size:.85rem;color:var(--cinza3)">${(doc.sumario||'').slice(0,140)}</div>
              <div style="display:flex;gap:.5rem;margin-top:.25rem;align-items:center">
                <div style="font-size:.75rem;color:var(--cinza4)">${doc.matched_by === 'linked' ? 'Ligado explicitamente à entidade' : 'Correspondência por texto no campo entidades'}</div>
                ${doc.class_match ? `<div style="background:#efe; color:#060; padding:.12rem .4rem;border-radius:.25rem;font-size:.72rem">Classe igual à entidade</div>` : ''}
              </div>
            </div>
            <div style="margin-left:auto;display:flex;gap:.4rem;flex-direction:column;align-items:flex-end">
              <button class="btn btn-secondary" onclick="openDocFromTable(event, ${doc.id})">Abrir</button>
              ${doc.matched_by === 'linked' 
                ? `<button class="btn btn-danger" style="margin-top:.35rem" onclick="unlinkDoc(event, ${doc.id})">Desassociar</button>`
                : `<button class="btn btn-gold" style="margin-top:.35rem" onclick="linkDoc(event, ${doc.id})">Associar</button>`
              }
            </div>
          </div>`).join('')}
      </div>`;
  }
  document.getElementById('modal-overlay').classList.add('open');
}

function clearFilters() {
  document.getElementById('f-categoria').value = '';
  document.getElementById('f-serie').value = '';
  document.getElementById('f-vigor').value = '';
  document.getElementById('f-ano-ini').value = '';
  document.getElementById('f-ano-fim').value = '';
  document.getElementById('f-entidade').value = '';
  document.getElementById('q').value = '';
  search(1);
}

async function linkDoc(ev, docId) {
  if (ev && typeof ev.stopPropagation === 'function') ev.stopPropagation();
  if (!currentEntityId) { showToast('Entidade não definida', true); return; }
  
  const linkRes = await fetch(`/api/entidade/${currentEntityId}/link/${docId}`, { method: 'POST' });
  const linkData = await linkRes.json();
  if (linkData.ok) { 
    showToast('Documento associado'); 
    openEntity(null, currentEntityId); 
  }
  else showToast('Erro: ' + (linkData.error||''), true);
}

async function unlinkDoc(ev, docId) {
  if (ev && typeof ev.stopPropagation === 'function') ev.stopPropagation();
  if (!currentEntityId) { showToast('Entidade não definida', true); return; }
  
  const delRes = await fetch(`/api/entidade/${currentEntityId}/link/${docId}`, { method: 'DELETE' });
  const delData = await delRes.json();
  if (delData.ok) { 
    showToast('Ligação removida'); 
    openEntity(null, currentEntityId); 
  }
  else showToast('Erro: ' + (delData.error||''), true);
}

async function loadStats() {
  const res = await fetch('/api/stats');
  const d = await res.json();

  document.getElementById('stats-cards').innerHTML = `
    <div class="stat-card">
      <div class="big-num">${d.total.toLocaleString('pt-PT')}</div>
      <div class="label">Total de Documentos</div>
    </div>
    <div class="stat-card">
      <div class="big-num">${d.em_vigor.toLocaleString('pt-PT')}</div>
      <div class="label">Em Vigor</div>
    </div>
    <div class="stat-card red">
      <div class="big-num">${(d.total - d.em_vigor).toLocaleString('pt-PT')}</div>
      <div class="label">Revogados</div>
    </div>
    <div class="stat-card gold">
      <div class="big-num">${d.n_entidades.toLocaleString('pt-PT')}</div>
      <div class="label">Entidades Emissoras</div>
    </div>
    <div class="stat-card">
      <div class="big-num">${d.anos_cobertura}</div>
      <div class="label">Anos de Cobertura</div>
    </div>
    <div class="stat-card gold">
      <div class="big-num">${d.com_pdf.toLocaleString('pt-PT')}</div>
      <div class="label">Com PDF Disponível</div>
    </div>
  `;

  renderBarChart('chart-tipos', d.top_tipos, 15);
  renderBarChart('chart-entidades', d.top_entidades, 15);
  renderBarChart('chart-series', d.por_serie.map(r => ({label:'Série '+r[0], count:r[1]})), 3);
  renderBarChart('chart-anos', d.por_decada, 12);
}

function renderBarChart(elemId, items, max) {
  if (!items || !items.length) return;
  const maxVal = Math.max(...items.map(i => i.count || i[1] || 0));
  document.getElementById(elemId).innerHTML = items.slice(0, max).map(item => {
    const label = item.label || item[0] || '';
    const count = item.count || item[1] || 0;
    const pct = maxVal ? count / maxVal * 100 : 0;
    return `<div class="bar-item">
      <div class="bar-label" title="${label}">${label}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="bar-num">${count.toLocaleString('pt-PT')}</div>
    </div>`;
  }).join('');
}

// ─── Classes OWL personalizadas ───────────────────────────────────────────────

const CUSTOM_CLASSES_KEY = 'dre_custom_owl_classes';

function getCustomClasses() {
  try { return JSON.parse(localStorage.getItem(CUSTOM_CLASSES_KEY) || '[]'); }
  catch { return []; }
}

function saveCustomClass(localname, parent, label) {
  const classes = getCustomClasses();
  const fullClass = 'dre:' + localname;
  const fullParent = parent ? 'dre:' + parent : 'dre:EntidadeEmissora';
  if (!classes.find(c => c.cls === fullClass)) {
    classes.push({ cls: fullClass, parent: fullParent, label: label || localname });
    localStorage.setItem(CUSTOM_CLASSES_KEY, JSON.stringify(classes));
  }
  renderCustomClassesTree();
}

function renderCustomClassesTree() {
  const classes = getCustomClasses();
  const container = document.getElementById('custom-owl-classes-tree');
  if (!container) return;
  if (!classes.length) { container.innerHTML = ''; return; }

  let html = `<div class="level1" style="margin-top:.5rem;border-top:1px dashed var(--cinza2);padding-top:.5rem;color:var(--cinza3);font-size:.75rem">
    ✦ Classes personalizadas</div>`;
  classes.forEach(c => {
    html += `<div class="level2" style="display:flex;justify-content:space-between;align-items:center">
      <span>├─ <span style="color:var(--verde2);font-weight:500">${c.cls}</span>
        <span style="font-size:.68rem;color:var(--cinza3);font-family:var(--sans)">
          ⊂ ${c.parent}${c.label ? ' — ' + c.label : ''}</span>
      </span>
      <button onclick="removeCustomClass('${c.cls}')"
        style="background:none;border:none;cursor:pointer;color:var(--vermelho);font-size:.75rem;padding:.1rem .3rem"
        title="Remover classe">✕</button>
    </div>`;
  });
  container.innerHTML = html;
}

function removeCustomClass(cls) {
  if (!confirm('Remover a classe ' + cls + ' da árvore?')) return;
  const classes = getCustomClasses().filter(c => c.cls !== cls);
  localStorage.setItem(CUSTOM_CLASSES_KEY, JSON.stringify(classes));
  renderCustomClassesTree();
  showToast('Classe removida da árvore');
}

function updateOwlPreview() {
  const localname = (document.getElementById('owl-class-localname')?.value || '').trim();
  const parent    = (document.getElementById('owl-class-parent')?.value || '').trim();
  const label     = (document.getElementById('owl-class-label')?.value || '').trim();
  const preview   = document.getElementById('owl-preview');
  const hidden    = document.getElementById('owl-class-final');

  if (!localname) {
    if (preview) { preview.style.display = 'none'; preview.textContent = ''; }
    if (hidden)  hidden.value = 'dre:EntidadeEmissora';
    return;
  }

  const fullClass  = 'dre:' + localname;
  const fullParent = parent ? 'dre:' + parent : 'dre:EntidadeEmissora';
  if (hidden) hidden.value = fullClass;
  if (preview) {
    preview.style.display = 'block';
    preview.innerHTML =
      `<strong>${fullClass}</strong> a owl:Class ;<br>` +
      `&nbsp;&nbsp;rdfs:subClassOf <strong>${fullParent}</strong> ;<br>` +
      (label ? `&nbsp;&nbsp;rdfs:label "${label}"@pt .` : '');
  }
}

// ─── Classes OWL (sidebar) ────────────────────────────────────────────────────

async function loadOwlClasses() {
  const res = await fetch('/api/owl-classes');
  const d = await res.json();
  document.getElementById('owl-class-list').innerHTML = d.map(c =>
    `<div class="onto-class" onclick="filterByClass('${c.owl_class}', this)" title="${c.owl_class}">
      <span class="cls-name">${c.owl_class.replace('dre:','')}</span>
      <span class="cls-count">${c.count.toLocaleString('pt-PT')}</span>
    </div>`).join('');
}

function filterByClass(cls, el) {
  document.querySelectorAll('.onto-class').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('q').value = '';
  const params = new URLSearchParams({owl_class: cls, page: 1, per_page: 25});
  fetch('/api/search?' + params).then(r=>r.json()).then(renderResults);
  showView('pesquisa', document.querySelector('nav button'));
}

async function loadQuickStats() {
  const res = await fetch('/api/quickstats');
  const d = await res.json();
  // Se houver elementos de sumário rápido no index, preenche aqui opcionalmente.
}

loadOwlClasses();
loadQuickStats();
renderCustomClassesTree();

async function removeRelacao(ev, rel_id) {
  ev.stopPropagation();
  if (!confirm('Eliminar esta relação?')) return;
  const res = await fetch('/api/relacao/' + rel_id, { method: 'DELETE' });
  const d = await res.json();
  if (d.ok) { showToast('Relação removida'); openDoc(currentDocId); }
  else showToast('Erro: ' + (d.error||''), true);
}