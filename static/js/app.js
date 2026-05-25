let currentPage = 1;
let currentDocId = null;
let currentEntityId = null; 

function showView(id, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('view-' + id).classList.add('active');
  if (btn) btn.classList.add('active');
  if (id === 'estatisticas') loadStats();
  if (id === 'adicionar') { 
    loadAddedItems();
    loadOntologyClasses();  // Carregar classes quando o utilizador abrir esta aba
    loadRdfParentClasses();  // Carregar classes mãe para o formulário de criar classe
  }
  if (id === 'ontologia') renderOntologyTree();
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

  // Validar se classe foi selecionada
  if (!body.classe_owl) {
    showToast('Por favor, selecione ou crie uma classe OWL', true);
    return;
  }

  // Se é nova classe, extrair e guardar os dados
  let newClassInfo = null;
  if (body.classe_owl === '__NEW__') {
    const name = (document.getElementById('new-class-name').value || '').trim();
    const parent = document.getElementById('new-class-parent').value;
    const label = (document.getElementById('new-class-label').value || '').trim();
    
    if (!name) {
      showToast('Por favor, introduza o nome da nova classe', true);
      return;
    }
    
    newClassInfo = {
      name: name,
      parent: parent,
      label: label
    };
    
    // Usar o valor final preenchido
    body.tipo = document.getElementById('owl-class-final').value;
  } else {
    body.tipo = body.classe_owl;
  }

  const res = await fetch('/api/entidade', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(body)
  });
  
  const d = await res.json();
  if (d.ok) {
    // Se criou nova classe, adicionar à ontologia
    if (newClassInfo) {
      saveCustomClass(newClassInfo.name, newClassInfo.parent, newClassInfo.label);
      // Re-renderizar árvore se a vista ontologia estiver ativa
      if (document.getElementById('view-ontologia').classList.contains('active')) {
        renderOntologyTree();
      }
    }

    let msg = 'Entidade adicionada!';
    if (d.linked_documents && d.linked_documents > 0) {
      msg += ` ${d.linked_documents} documento(s) ligados automaticamente à entidade.`;
    }
    showToast(msg);
    e.target.reset();
    
    // Limpar campos
    document.getElementById('class-selector').value = '';
    document.getElementById('new-class-fields').style.display = 'none';
    document.getElementById('new-class-name').value = '';
    document.getElementById('new-class-label').value = '';
    document.getElementById('new-class-preview').style.display = 'none';
    document.getElementById('owl-class-final').value = '';
    
    loadAddedItems();
  } else {
    showToast('Erro: ' + (d.error||''), true);
  }
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

function renderResults(data) {
  const tbody = document.getElementById('results-tbody');
  const info  = document.getElementById('result-info');
  const pag   = document.getElementById('pagination');

  if (!data.results || !data.results.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--cinza3);padding:2rem">
      Nenhum resultado encontrado.</td></tr>`;
    info.innerHTML = '<span>0 resultados</span>';
    pag.innerHTML = '';
    return;
  }

  info.innerHTML = `<strong>${data.total.toLocaleString('pt-PT')}</strong> resultados
    — página <strong>${data.page}</strong> de <strong>${data.pages}</strong>`;

  tbody.innerHTML = data.results.map(r => {
    // Definir estilos consoante seja um documento ou uma entidade
    const badgeClass = r.is_entity ? 'badge-gold' 
                     : r.categoria === 'Ato Normativo' ? 'badge-norm'
                     : r.categoria === 'Ato Administrativo' ? 'badge-adm'
                     : r.categoria === 'Ato Informativo' ? 'badge-info' : 'badge-outro';
    
    const rowColor = r.is_entity ? 'background-color: #ffffff;' : ''; 
    const vigencia = r.is_entity ? '—' : (r.in_force ? '<span class="vigente">● Em vigor</span>' : '<span class="revogado">○ Revogado</span>');
    const pdf = r.url_pdf ? `<a href="${r.url_pdf}" target="_blank" class="link-doc" title="Abrir PDF">📄</a>` : '—';
    const shortSumario = (r.sumario||'').length > 120 ? r.sumario.slice(0,120) + '…' : (r.sumario||'—');

    // Botões de ação dinâmicos
    let actionsHtml = '';
    if (r.is_entity) {
        actionsHtml = `<button class="btn btn-gold" onclick="openEntity(event, ${r.id})">🏛️ Entidade</button>`;
    } else {
        actionsHtml = `
            <button class="btn btn-secondary" onclick="openDocFromTable(event, ${r.id})">Abrir</button>
            <button class="btn btn-danger" onclick="removeDoc(event, ${r.id})">Remover</button>
        `;
    }

    return `<tr style="cursor:pointer; ${rowColor}">
      <td><span style="font-family:var(--mono);font-size:.75rem">${r.claint||'—'}</span></td>
      <td><span class="badge ${badgeClass}" ${r.is_entity ? 'style="background:var(--ouro);color:#fff;"' : ''}>${r.is_entity ? '🏛️ Entidade' : (r.doc_type||'').slice(0,22)}</span></td>
      <td style="font-family:var(--mono);font-size:.75rem">${r.numero||'—'}</td>
      <td style="font-family:var(--mono);font-size:.75rem;white-space:nowrap">${r.data||'—'}</td>
      <td style="text-align:center;font-family:var(--mono)">${r.serie && r.serie !== '—' ? 'S'+r.serie : '—'}</td>
      <td style="max-width:320px;font-size:.78rem; ${r.is_entity ? 'font-weight:600; color:var(--verde2);' : ''}">${shortSumario}</td>
      <td>${vigencia}</td>
      <td>${pdf}</td>
      <td style="white-space:nowrap;">${actionsHtml}</td>
    </tr>`;
  }).join('');

  // Paginação padrão mantida
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


async function openRascunho(ev, id) {
  ev.stopPropagation();
  const res = await fetch('/api/documento_novo/' + id);
  if (!res.ok) { showToast('Rascunho não encontrado', true); return; }
  const d = await res.json();

  document.getElementById('modal-title').textContent = (d.owl_class || 'Documento') + (d.numero ? ' n.º ' + d.numero : '');
  
  // O código abaixo garante a renderização do botão PDF
  let pdfButton = d.url_pdf ? `<a href="${d.url_pdf}" target="_blank" class="btn btn-primary" style="font-size:.8rem;text-decoration:none">📄 Ver PDF</a>` : '';

  document.getElementById('modal-body').innerHTML = `
    <div class="meta-grid">
      <dl class="meta-item"><dt>Classe OWL</dt><dd><span class="badge badge-norm">${d.owl_class||'—'}</span></dd></dl>
      <dl class="meta-item"><dt>Número</dt><dd>${d.numero||'—'}</dd></dl>
      <dl class="meta-item"><dt>Data</dt><dd>${d.data||'—'}</dd></dl>
      <dl class="meta-item"><dt>Entidade(s)</dt><dd style="font-size:.8rem">${(d.entidades||'') || '—'}</dd></dl>
    </div>
    ${d.sumario ? `<div class="sumario-box">${d.sumario}</div>` : ''}
    
    <div style="display:flex;gap:.5rem;margin:.75rem 0;flex-wrap:wrap">
      ${pdfButton}
    </div>

    <div style="font-family:var(--mono);font-size:.68rem;color:var(--cinza3);margin-top:1rem">
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

function saveCustomClass(localname, parent, label, uri = null) {
  const classes = getCustomClasses();
  const fullClass = 'dre:' + localname;
  const fullParent = parent ? 'dre:' + parent : 'dre:EntidadeEmissora';
  if (!classes.find(c => c.cls === fullClass)) {
    classes.push({ 
      cls: fullClass, 
      parent: fullParent, 
      label: label || localname,
      uri: uri || null  // Armazenar URI se disponível
    });
    localStorage.setItem(CUSTOM_CLASSES_KEY, JSON.stringify(classes));
  }

}

function renderCustomClassesTree() {
  // Função agora integrada em renderOntologyTree()
  // Esta função é mantida por compatibilidade
}

async function removeCustomClass(cls) {
  if (!confirm('⚠️ Remover a classe ' + cls + ' da ontologia permanentemente? Esta ação não pode ser desfeita.')) return;
  
  try {
    // Obter a classe personalizada para extrair o URI
    const customClasses = getCustomClasses();
    const customClass = customClasses.find(c => c.cls === cls);
    
    if (!customClass) {
      showToast('Classe não encontrada', true);
      return;
    }
    
    console.log('A remover classe:', cls);
    
    // Remover da ontologia (.ttl) através do backend
    const res = await fetch('/api/rdf/classe', { 
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ class_name: cls })
    });
    
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      showToast('Erro do servidor: ' + res.status + ' — ' + (errorData.error || 'Erro desconhecido'), true);
      return;
    }
    
    const data = await res.json();
    
    if (data.ok) {
      // Remover do localStorage também
      const classes = getCustomClasses().filter(c => c.cls !== cls);
      localStorage.setItem(CUSTOM_CLASSES_KEY, JSON.stringify(classes));
      renderOntologyTree();  // Re-renderizar a árvore
      showToast('✓ Classe ' + cls + ' removida da ontologia');
    } else {
      showToast('Erro ao remover classe: ' + (data.error || 'Erro desconhecido'), true);
    }
  } catch (err) {
    console.error('Erro ao remover classe:', err);
    showToast('Erro de comunicação: ' + err.message, true);
  }
}

// ─── Seleção de classes OWL e gerenciar nova classe ────────────────────────

async function loadOntologyClasses() {
  try {
    // Carregar todas as classes disponíveis para os selectors e optgroups
    const res = await fetch('/api/owl-classes-all');
    if (!res.ok) {
      console.error('Erro ao carregar classes:', res.status);
      return;
    }
    const classes = await res.json();
    if (!Array.isArray(classes)) return;

    const rdfClassSel = document.getElementById('rdf-class-selector');
    const rdfDocType = document.getElementById('rdf-doc-type');
    const rdfParent = document.getElementById('rdf-parent-class');
    const classSelector = document.getElementById('class-selector');

    const uriOptions = classes.map(c => `<option value="${c.uri}">${c.label}</option>`).join('');
    if (rdfClassSel) rdfClassSel.innerHTML = `<option value="">Selecione uma classe...</option>` + uriOptions;
    if (rdfDocType) rdfDocType.innerHTML = `<option value="">Selecione tipo de documento...</option>` + uriOptions;
    if (rdfParent) rdfParent.innerHTML = `<option value="">Selecione classe mãe...</option>` + uriOptions;

    // Popular selector usado na criação de entidades (usa forma curta dre:...)
    if (classSelector) {
      const entityClasses = classes.filter(c => Array.isArray(c.parents) && c.parents.includes('dre:EntidadeEmissora'));
      const otherClasses = classes.filter(c => !(Array.isArray(c.parents) && c.parents.includes('dre:EntidadeEmissora')));

      const entOptions = entityClasses.map(c => `<option value="${c.cls}">${c.label}</option>`).join('');
      const otherOptions = otherClasses.map(c => `<option value="${c.cls}">${c.label}</option>`).join('');

      classSelector.innerHTML = `
        <option value="">Selecione ou crie uma classe...</option>
        <option value="__NEW__">-- Criar nova classe --</option>
        <optgroup label="Entidades">${entOptions}</optgroup>
        <optgroup label="Outras Classes" id="other-classes-group">${otherOptions}</optgroup>
      `;
    }
  } catch (err) {
    console.error('Erro ao carregar ontologia:', err);
  }
}

function toggleCustomClassFields() {
  const selector = document.getElementById('class-selector');
  const value = selector.value;
  const fieldsContainer = document.getElementById('new-class-fields');
  const finalInput = document.getElementById('owl-class-final');
  
  if (value === '__NEW__') {
    // Mostrar campos para nova classe
    fieldsContainer.style.display = 'block';
    finalInput.value = '';  // Será preenchido quando validar
  } else if (value) {
    // Usar classe existente
    fieldsContainer.style.display = 'none';
    finalInput.value = value;
    // Limpar campos de nova classe
    document.getElementById('new-class-name').value = '';
    document.getElementById('new-class-label').value = '';
    document.getElementById('new-class-preview').style.display = 'none';
  } else {
    fieldsContainer.style.display = 'none';
    finalInput.value = '';
  }
}

function updateNewClassPreview() {
  const name = (document.getElementById('new-class-name').value || '').trim();
  const parent = document.getElementById('new-class-parent').value;
  const label = (document.getElementById('new-class-label').value || '').trim();
  const preview = document.getElementById('new-class-preview');
  const finalInput = document.getElementById('owl-class-final');
  
  if (!name) {
    preview.style.display = 'none';
    finalInput.value = '';
    return;
  }
  
  const fullClass = 'dre:' + name;
  finalInput.value = fullClass;
  
  let previewText = `${fullClass} a owl:Class ;\n`;
  previewText += `  rdfs:subClassOf ${parent} ;\n`;
  if (label) {
    previewText += `  rdfs:label "${label}"@pt .`;
  }
  
  preview.textContent = previewText;
  preview.style.display = 'block';
}

// ─── Árvore de Ontologia Dinâmica ────────────────────────────────────────────

async function renderOntologyTree() {
  try {
    const res = await fetch('/api/owl-classes-all');
    if (!res.ok) {
      console.error('Erro ao buscar classes OWL:', res.status);
      return;
    }
    let allClasses = await res.json();
    
    // Remover duplicados por 'cls'
    const seen = new Set();
    allClasses = allClasses.filter(c => {
      if (seen.has(c.cls)) return false;
      seen.add(c.cls);
      return true;
    });
  
  // Definir a hierarquia: map de classe -> [subclasses]
  const hierarchy = {
    'dre:DocumentoOficial': [
      'dre:AtoNormativo',
      'dre:AtoAdministrativo',
      'dre:AtoInformativo'
    ],
    'dre:AtoNormativo': [
      'dre:Lei',
      'dre:DecretoLei',
      'dre:Decreto',
      'dre:Portaria',
      'dre:Regulamento',
      'dre:Resolucao',
      'dre:Rectificacao'
    ],
    'dre:Lei': ['dre:LeiOrganica'],
    'dre:Decreto': ['dre:DecretoRegulamentar'],
    'dre:AtoAdministrativo': [
      'dre:Despacho',
      'dre:Deliberacao',
      'dre:Contrato',
      'dre:Louvor',
      'dre:Declaracao'
    ],
    'dre:Despacho': ['dre:DespachoExtrato'],
    'dre:AtoInformativo': [
      'dre:Aviso',
      'dre:AvisoContumax',
      'dre:AnuncioProcedimento',
      'dre:Anuncio',
      'dre:Edital'
    ],
    'dre:Aviso': ['dre:AvisoExtrato']
  };

  // Adicionar classes personalizadas à hierarquia
  const customClasses = getCustomClasses();
  customClasses.forEach(c => {
    // Encontrar a classe mãe (extrair apenas o nome curto)
    const parentShort = c.parent ? c.parent.replace('dre:', '') : 'DocumentoOficial';
    const parentFull = c.parent || 'dre:DocumentoOficial';
    
    if (!hierarchy[parentFull]) {
      hierarchy[parentFull] = [];
    }
    if (!hierarchy[parentFull].includes(c.cls)) {
      hierarchy[parentFull].push(c.cls);
    }
  });

  // Criar map de classe -> label para lookup rápido
  const classMap = new Map(allClasses.map(c => [c.cls, c.label]));
  
  // Adicionar classes personalizadas ao mapa
  customClasses.forEach(c => {
    if (!classMap.has(c.cls)) {
      classMap.set(c.cls, c.label || c.cls.replace('dre:', ''));
    }
  });
  
  // Renderizar a árvore
  let html = `<div style="font-family: monospace; font-size: 0.9rem; line-height: 1.6;">`;
  
  // Raiz: DocumentoOficial
  html += `<div style="padding-left: 0;">🌳 dre:DocumentoOficial</div>`;
  
  // Função recursiva para renderizar subclasses
  function renderChildren(parentClass, level) {
    const children = hierarchy[parentClass] || [];
    if (!children.length) return '';
    
    let html = '';
    const indentSize = level * 2; // 2em por nível
    
    children.forEach((child, idx) => {
      const isLastChild = idx === children.length - 1;
      const icon = isLastChild ? '└─' : '├─';
      const label = classMap.get(child) || child.replace('dre:', '');
      const isCustom = customClasses.some(c => c.cls === child);
      const customClass = isCustom ? customClasses.find(c => c.cls === child) : null;
      
      let classHtml = `<div style="padding-left: ${indentSize}em; display: flex; justify-content: space-between; align-items: center; ${level > 3 ? 'opacity: 0.85;' : ''}">`;
      classHtml += `<span style="flex: 1;">`;
      classHtml += `${icon} <span style="font-weight:500;${isCustom ? 'color:var(--verde2)' : ''}">${child}</span> <span style="font-size:.75rem;color:var(--cinza3)">— ${label}</span>`;
      classHtml += `</span>`;
      
      if (isCustom && customClass) {
        classHtml += `<button onclick="removeCustomClass('${child}')" style="background:none;border:none;cursor:pointer;color:var(--vermelho);font-size:.7rem;padding:0 .2rem;margin-left:.5rem;flex-shrink:0;" title="Remover classe">✕</button>`;
      }
      
      classHtml += `</div>`;
      html += classHtml;
      
      // Renderizar filhos deste filho
      html += renderChildren(child, level + 1);
    });
    
    return html;
  }
  
  // Renderizar subclasses de DocumentoOficial
  html += renderChildren('dre:DocumentoOficial', 1);
  html += `</div>`;
  
  document.getElementById('ontology-tree').innerHTML = html;
  } catch (err) {
    console.error('Erro ao renderizar ontologia:', err);
    document.getElementById('ontology-tree').innerHTML = `<div style="color:var(--vermelho);padding:1rem">Erro ao carregar hierarquia</div>`;
  }
}

// ─── Classes OWL (sidebar) ────────────────────────────────────────────────────

async function loadOwlClasses() {
  try {
    // Carregar TODAS as classes para exibição na sidebar 
    const res = await fetch('/api/owl-classes-all');
    if (!res.ok) throw new Error('Erro ao buscar classes');
    let allClasses = await res.json();
    
    // Remover duplicados por 'cls' 
    const seen = new Set();
    allClasses = allClasses.filter(c => {
      if (seen.has(c.cls)) return false;
      seen.add(c.cls);
      return true;
    });
    
    // Também carregar as contagens de documentos por classe
    const res2 = await fetch('/api/owl-classes');
    if (!res2.ok) throw new Error('Erro ao buscar contagens');
    let usedClasses = await res2.json();
    
    // Remover duplicados das contagens
    const seenCounts = new Set();
    usedClasses = usedClasses.filter(c => {
      if (seenCounts.has(c.owl_class)) return false;
      seenCounts.add(c.owl_class);
      return true;
    });
    
    const countMap = new Map(usedClasses.map(c => [c.owl_class, c.count]));
    
    // Combinar dados: mostrar classes que têm contagem > 0 OU que são explicitamente declaradas
    const classList = document.getElementById('owl-class-list');
    if (classList) {
      const displayed = allClasses.filter(c => (countMap.get(c.cls) || 0) > 0 || c.declared);
      classList.innerHTML = displayed.map(c => {
        const count = countMap.get(c.cls) || 0;
        return `<div class="onto-class" onclick="filterByClass('${c.cls}', this)" title="${c.cls}" style="opacity: ${count > 0 ? 1 : 0.6}">
          <span class="cls-name">${c.label}</span>
          <span class="cls-count">${count > 0 ? count.toLocaleString('pt-PT') : '—'}</span>
        </div>`;
      }).join('');
    }
  } catch (err) {
    console.error('Erro ao carregar classes para sidebar:', err);
  }
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

async function removeRelacao(ev, rel_id) {
  ev.stopPropagation();
  if (!confirm('Eliminar esta relação?')) return;
  const res = await fetch('/api/relacao/' + rel_id, { method: 'DELETE' });
  const d = await res.json();
  if (d.ok) { showToast('Relação removida'); openDoc(currentDocId); }
  else showToast('Erro: ' + (d.error||''), true);
}

// --- Lógica do Dropdown Adicionar ---
function toggleAddDropdown(ev) {
  ev.stopPropagation();
  document.getElementById("addDropdownContainer").classList.toggle("show");
}

// Fecha o dropdown se clicares fora
window.addEventListener('click', function(e) {
  if (!e.target.matches('#addDropdownContainer button')) {
    const dropdown = document.getElementById("addDropdownContainer");
    if (dropdown && dropdown.classList.contains('show')) {
      dropdown.classList.remove('show');
    }
  }
});

function openAddView(type, ev) {
  if (ev) ev.preventDefault();
  
  const navBtn = document.querySelector('#addDropdownContainer button');
  showView('adicionar', navBtn);

  const panelDoc = document.getElementById('panel-add-doc');
  const panelEnt = document.getElementById('panel-add-ent');
  const panelClass = document.getElementById('panel-add-class'); 

  // Esconder todos por defeito
  panelDoc.style.display = 'none';
  panelEnt.style.display = 'none';
  panelClass.style.display = 'none';

  // Mostrar o selecionado e carregar respetivos dados
  if (type === 'documento') {
    panelDoc.style.display = 'block';
    loadRdfDocumentOptions();
  } else if (type === 'entidade') {
    panelEnt.style.display = 'block';
    loadRdfEntityClasses(); 
  } else if (type === 'classe') {
    panelClass.style.display = 'block';
    loadRdfParentClasses();
  }
}


// --- Lógica de Criação de Classes OWL ---

async function loadRdfParentClasses() {
  const sel = document.getElementById('rdf-parent-class');
  sel.innerHTML = '<option value="">A carregar opções...</option>';
  
  try {
    // Procurar opções de classes mãe
    const res = await fetch('/api/rdf/form-options');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    let html = '<option value="">— selecione a superclasse mãe —</option>';
    
    // Documentos
    if (data.classes_doc && data.classes_doc.length > 0) {
      html += '<optgroup label="Hierarquia de Documentos">';
      html += '<option value="http://dre.pt/ontologia#DocumentoOficial">📄 Documento Oficial (Raiz)</option>';
      data.classes_doc.forEach(c => {
        if (c.uri !== "http://dre.pt/ontologia#DocumentoOficial") {
          html += `<option value="${c.uri}">${c.label}</option>`;
        }
      });
      html += '</optgroup>';
    }
    
    // Entidades
    if (data.entidades && data.entidades.length > 0) {
      html += '<optgroup label="Hierarquia de Entidades">';
      html += '<option value="http://dre.pt/ontologia#EntidadeEmissora">🏛️ Entidade Emissora (Raiz)</option>';
      data.entidades.forEach(c => {
        if (c.uri !== "http://dre.pt/ontologia#EntidadeEmissora") {
          html += `<option value="${c.uri}">${c.label}</option>`;
        }
      });
      html += '</optgroup>';
    }

    sel.innerHTML = html;
    updateClassPreview();
  } catch (err) {
    console.error('Erro ao carregar classes mãe:', err);
    sel.innerHTML = '<option value="">Erro ao carregar (ver consola)</option>';
  }
}

function updateClassPreview() {
  const form = document.querySelector('#panel-add-class form');
  const nome = form.nome_classe.value.trim().replace(/\s+/g, ''); // Força remoção de espaços
  const parent = form.super_classe.value;
  const label = form.label.value.trim();
  const preview = document.getElementById('new-class-preview');

  if (!nome || !parent) {
    preview.textContent = "Preenche o nome e escolhe a superclasse para ver os triplos gerados.";
    return;
  }

  const parentShort = parent.split('#').pop();
  let text = `dre:${nome} a owl:Class ;\n`;
  text += `    rdfs:subClassOf dre:${parentShort} ;\n`;
  if (label) text += `    rdfs:label "${label}"@pt .\n`;
  else text += `    .\n`;

  preview.textContent = text;
}

async function addRDFClass(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-rdf-class');
  btn.textContent = 'A injetar classe no grafo...';
  btn.disabled = true;

  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd);

  try {
    const res = await fetch('/api/rdf/classe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    
    const d = await res.json();
    if (d.ok) {
      showToast('✓ Nova Classe OWL adicionada à ontologia!');
      
      // Guardar a classe personalizada com o URI retornado
      const localname = body.nome_classe;
      const parent = body.super_classe.split('#')[1] || body.super_classe;  // Extrair nome curto
      const label = body.label;
      const uri = d.uri;
      
      saveCustomClass(localname, parent, label, uri);
      
      e.target.reset();
      updateClassPreview();
    } else {
      showToast('Erro: ' + (d.error || 'Falha na inserção'), true);
    }
  } catch(err) {
    console.error('Erro:', err);
    showToast('Erro de comunicação com o servidor.', true);
  } finally {
    btn.textContent = '💾 Gravar Nova Classe no .ttl';
    btn.disabled = false;
  }
}


async function loadRdfDocumentOptions() {
  const selType = document.getElementById('rdf-doc-type');
  const listEnt = document.getElementById('rdf-entities-list');
  
  try {
    const res = await fetch('/api/rdf/form-options');
    if (!res.ok) throw new Error('Falha na resposta do servidor');
    
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    // 1. Tipos de Documento
    selType.innerHTML = '<option value="">— selecione o tipo —</option>' + 
      (data.classes_doc && data.classes_doc.length > 0 
        ? data.classes_doc.map(c => `<option value="${c.uri}">${c.label}</option>`).join('')
        : '<option value="" disabled>Nenhum tipo disponível</option>');

    // 2. Entidades Emissoras (Injeta o rótulo legível diretamente no value para a pesquisa funcionar)
    if (listEnt) {
      listEnt.innerHTML = (data.entidades && data.entidades.length > 0)
        ? data.entidades.map(e => `<option value="${e.label}"></option>`).join('')
        : '';
    }

  } catch (err) {
    console.error('Erro ao carregar dados do formulário:', err);
    showToast('Erro ao carregar dados do SQLite para o formulário.', true);
  }
}

async function addRDFDocument(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-rdf-doc');
  btn.textContent = 'A gerar triplos e a comprimir...';
  btn.disabled = true;

  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd);

  try {
    const res = await fetch('/api/rdf/documento', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    
    const d = await res.json();
    if (d.ok) {
      showToast('Documento injetado na ontologia com sucesso!');
      e.target.reset();
    } else {
      showToast('Erro: ' + (d.error || 'Falha na inserção'), true);
    }
  } catch(err) {
    showToast('Erro de comunicação com o servidor.', true);
  } finally {
    btn.textContent = '💾 Gerar Triplos e Guardar';
    btn.disabled = false;
  }
}

// --- Fetch & Inserção RDF ---
async function loadRdfEntityClasses() {
  const sel = document.getElementById('rdf-class-selector');
  sel.innerHTML = '<option value="">A carregar opções...</option>';
  
  try {
    const res = await fetch('/api/rdf/classes');
    if (!res.ok) throw new Error('Falha na resposta do servidor');
    
    const classes = await res.json();
    if (classes.error) throw new Error(classes.error);

    sel.innerHTML = '<option value="">— selecione a classe mãe —</option>' + 
      classes.map(c => `<option value="${c.uri}">${c.label}</option>`).join('');
  } catch (err) {
    showToast('Erro ao carregar classes RDF da base de dados.', true);
    sel.innerHTML = '<option value="">Erro ao carregar opções</option>';
  }
}

async function addRDFEntity(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-rdf');
  btn.textContent = 'A injetar triplos e a comprimir...';
  btn.disabled = true;

  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd);

  try {
    const res = await fetch('/api/rdf/entidade', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    
    const d = await res.json();
    if (d.ok) {
      showToast('Entidade injetada com sucesso no ficheiro .bz2!');
      e.target.reset();
    } else {
      showToast('Erro: ' + (d.error || 'Falha na inserção'), true);
    }
  } catch(err) {
    showToast('Erro de comunicação com o servidor.', true);
  } finally {
    btn.textContent = '💾 Injetar no Ficheiro .bz2';
    btn.disabled = false;
  }
}
// --- Lógica de Extração PDF ---
async function extractFromPDF() {
  const fileInput = document.getElementById('pdf-upload');
  const file = fileInput.files[0];
  
  if (!file) {
    showToast('Por favor, seleciona um ficheiro PDF primeiro.', true);
    return;
  }

  const btn = document.getElementById('btn-extract-pdf');
  const feedback = document.getElementById('pdf-feedback');
  
  btn.textContent = 'A processar...';
  btn.disabled = true;
  feedback.textContent = 'A analisar texto do documento...';
  feedback.style.color = 'var(--cinza3)';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/extract-pdf', {
      method: 'POST',
      body: formData 
    });

    const data = await res.json();
    
    if (data.ok) {
      // Injetar nos campos do formulário se tiver encontrado inf
      if (data.data_publicacao) {
        document.querySelector('input[name="data_publicacao"]').value = data.data_publicacao;
      }
      if (data.sumario) {
        document.querySelector('textarea[name="sumario"]').value = data.sumario;
      }
      if (data.emitido_por_nome) {
        document.querySelector('input[name="emitido_por_nome"]').value = data.emitido_por_nome;
      }

      showToast('Dados do PDF extraídos com sucesso!');
      feedback.textContent = 'Campos preenchidos automaticamente. Por favor, valida a informação.';
      feedback.style.color = 'var(--verde2)';
    } else {
      showToast(data.error || 'Erro na extração', true);
      feedback.textContent = 'Erro ao extrair dados. Preenche manualmente.';
      feedback.style.color = 'var(--vermelho)';
    }
  } catch (err) {
    showToast('Erro de comunicação com o servidor ao processar PDF.', true);
    feedback.textContent = 'Falha na ligação.';
  } finally {
    btn.textContent = 'Extrair Dados';
    btn.disabled = false;
  }
}