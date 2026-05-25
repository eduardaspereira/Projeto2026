# DRE Ontologia

Aplicação para explorar, pesquisar e enriquecer o corpus do Diário da República Eletrónico (DRE).

Descrição curta
- Ingestão de um dataset público do DRE (JSON `.bz2`) para SQLite, modelado segundo uma ontologia OWL.
- API REST em Flask para consulta, gestão e enriquecimento dos dados.
- Interface web para pesquisa, visualização e edição.

Funcionalidades (resumo completo)
- Carregador de dados: `script.py`
  - Lê ficheiros JSON comprimidos com `bz2` e popula um ficheiro SQLite (`dre.db`).
  - Normaliza `doc_type` → classes OWL via `DOC_TYPE_MAP`.
  - Cria esquema (tabelas, índices, FTS5) e importa em lotes para eficiência.

- Servidor web: `app.py` (Flask)
  - Página principal: `GET /` — interface SPA (`templates/index.html`).
  - Pesquisa: `GET /api/search` — pesquisa full-text (FTS5) combinada com filtros: `q`, `categoria`, `serie`, `vigor` (`in_force`), `ano_ini`, `ano_fim`, `entidade`, `owl_class`, paginação (`page`, `per_page`).
  - Gestão RDF / Ontologia (escrita em `dre_dados.ttl`):
    - `POST /api/rdf/classe` — criar nova classe OWL nos dados.
    - `DELETE /api/rdf/classe` — remover classe dos dados.
    - `POST /api/rdf/entidade` — adicionar entidade no grafo e sincronizar com SQLite.
    - `POST /api/rdf/documento` — adicionar documento RDF (inserção nos dados).
  - Gestão documental e enriquecimento (SQLite):
    - `GET /api/documento/<id>` — detalhe de documento (entidades, relações).
    - `POST /api/documento` — adicionar novo documento (guardado em `documento_novo`).
    - `DELETE /api/documento/<id>` — remover documento.
    - `POST /api/relacao` — criar relação entre documentos (ex.: revoga, altera, rectifica, desenvolve).
    - `DELETE /api/relacao/<rel_id>` — apagar relação.
  - Entidades e ligações:
    - `POST /api/entidade` — criar entidade (DB).
    - `GET /api/entidade/<int:ent_id>/docs` — listar documentos associados a uma entidade.
    - `POST /api/entidade/<int:ent_id>/link/<int:doc_id>` — associar entidade a documento.
    - `DELETE /api/entidade/<int:ent_id>/link/<int:doc_id>` — remover associação.
    - `DELETE /api/entidade/<int:ent_id>` — remover entidade.
  - Ontologia / classes:
    - `GET /api/owl-classes` — classes OWL com contagens (resumo).
    - `GET /api/owl-classes-all` — lista completa de classes.
  - Estatísticas:
    - `GET /api/quickstats` — estatísticas rápidas (totais, em vigor, PDFs, entidades).
    - `GET /api/stats` — estatísticas detalhadas (top tipos, distribuição por década).
  - Endpoints auxiliares:
    - `GET /api/adicionados` — listar documentos/entidades adicionados via UI.

- Interface web (front-end)
  - `templates/index.html` + `static/js/app.js` + `static/css/style.css`.
  - SPA com painel lateral de filtros, paginação, modais para detalhe, formulários de adição e gestão de relações.


Recomenda-se criar um virtualenv e instalar com:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install Flask rdflib PyPDF2
```

Como usar
- Carregar o dataset DRE (exemplo):

```bash
python script.py /caminho/para/dataset.json.bz2 --output dre.db
```

- Iniciar o servidor:

```bash
python app.py --db dre.db --host 127.0.0.1 --port 5000
# Depois abrir http://127.0.0.1:5000
```

Estrutura do projecto (ficheiros principais)
- `dre_ontologia.ttl` — ontologia mestre OWL (classes e propriedades).
- `dre_dados.ttl` — instâncias / dados RDF geridos pela aplicação.
- `script.py` — carregador/importador para SQLite + índice FTS.
- `app.py` — servidor Flask com API e endpoints de gestão.
- `templates/index.html`, `static/js/app.js`, `static/css/style.css` — interface web.

Notas e recomendações
- O projeto usa SQLite (ficheiro `dre.db`) em vez de uma triple store — vantagem de simplicidade e FTS5 para pesquisa de texto.
- As alterações RDF realizadas via API são guardadas em `dre_dados.ttl` (dados) — a ontologia mestre (`dre_ontologia.ttl`) não é alterada automaticamente.
