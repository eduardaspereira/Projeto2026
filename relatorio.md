# Relatório Técnico — DRE Ontologia

**Projeto de Engenharia de Linguagens · 2º Semestre 2026**

---

## 1. Introdução

O projeto DRE Ontologia é uma aplicação web que permite explorar, consultar e enriquecer o corpus legislativo do Diário da República Eletrónico (DRE) de Portugal. O sistema ingere um dataset público do DRE em formato JSON comprimido, organiza os documentos segundo uma ontologia OWL formal, e expõe uma interface de pesquisa e gestão com suporte a relações entre documentos e entidades emissoras.

O sistema cobre documentos desde 1910 e classifica-os em três grandes categorias: Atos Normativos, Atos Administrativos e Atos Informativos. A aplicação permite não apenas consultar este acervo, mas também enriquecê-lo — criando novas entidades, adicionando documentos e estabelecendo relações entre diplomas (revogação, alteração, retificação, etc.).

---

## 2. Arquitetura do Sistema

O sistema divide-se em quatro componentes principais que colaboram em camadas.

### 2.1 Ontologia (`dre_ontologia.ttl`)

A ontologia define a estrutura conceptual do domínio em OWL/RDF, com o prefixo `dre: <http://dre.pt/ontologia#>`. A hierarquia de classes parte de `dre:DocumentoOficial` como raiz, com três ramos principais:

- `dre:AtoNormativo` — Lei, LeiOrgânica, DecretoLei, Decreto, DecretoRegulamentar, Portaria, Regulamento, Resolucao, Rectificacao
- `dre:AtoAdministrativo` — Despacho, DespachoExtrato, Deliberacao, Contrato, Louvor, Declaracao
- `dre:AtoInformativo` — Aviso, AvisoExtrato, AvisoContumax, AnuncioProcedimento, Anuncio, Edital

As três categorias são declaradas disjuntas (`owl:disjointWith`), garantindo que um documento não pertence a mais do que uma. A ontologia define ainda propriedades de dados como `dre:claint`, `dre:dataPublicacao`, `dre:sumario`, `dre:urlPDF`, e propriedades de objeto como `dre:emitidoPor`, `dre:revoga`, `dre:alteradoPor`, `dre:desenvolve`, `dre:transponeDiretiva`.

### 2.2 Carregador de Dados (`script.py`)

O `script.py` é responsável por ingerir o dataset DRE (ficheiro `.bz2` ou JSON simples) e popular a base de dados SQLite. O processo funciona assim:

1. Abre o ficheiro com `bz2.open` e faz `json.load` de todos os registos de uma vez.
2. Para cada registo, normaliza o `doc_type` via `get_owl_class()`, que faz lookup no dicionário `DOC_TYPE_MAP` — mapeando strings como `"decreto-lei"` para `"dre:DecretoLei"`.
3. Insere os documentos em lotes de 5 000 registos (`flush_batch`) para não esgotar memória.
4. Gere entidades emissoras com cache em memória (`entidade_cache`) para evitar `SELECT` repetidos.
5. No final, constrói o índice FTS5 em blocos de 1 000 registos para suporte a pesquisa de texto livre.

O esquema SQLite criado inclui as tabelas `documento`, `entidade_emissora`, `documento_entidade` (relação N:N), `relacao_documento` (para relações entre diplomas), `entidade_nova` e `documento_novo` (para enriquecimento via web app), e a tabela virtual `documento_fts` com FTS5.

### 2.3 Servidor Web (`app.py`)

O `app.py` é uma aplicação Flask que expõe a base de dados via API REST. As rotas principais são:

| Rota | Método | Função |
|------|--------|--------|
| `/api/search` | GET | Pesquisa com filtros (categoria, série, vigor, ano, entidade, texto livre via FTS) |
| `/api/documento/<id>` | GET | Detalhe de um documento com entidades e relações |
| `/api/documento` | POST | Adicionar novo documento |
| `/api/documento/<id>` | DELETE | Remover documento |
| `/api/relacao` | POST | Criar relação entre documentos |
| `/api/relacao/<id>` | DELETE | Remover relação |
| `/api/owl-classes` | GET | Contagens por classe OWL |
| `/api/quickstats` | GET | Estatísticas rápidas (total, em vigor, séries, PDFs, entidades) |
| `/api/stats` | GET | Estatísticas detalhadas com top tipos e entidades, distribuição por década |
| `/api/entidade/<id>/link/<doc_id>` | POST/DELETE | Ligar/desligar entidade a documento |

A pesquisa combina FTS5 com filtros SQL convencionais. Quando há texto na query, o servidor obtém primeiro os `rowid` via `documento_fts MATCH ?` e injeta-os como subcondição `IN (...)` na query principal, mantendo os restantes filtros ativos.

### 2.4 Interface Web (`index.html` + `style.css` + `app.js`)

A interface é uma Single Page Application construída em HTML/CSS/JS puro, renderizada pelo Flask via Jinja2. O layout divide-se num painel lateral fixo (filtros e formulários) e num painel direito com scroll para resultados.

O `style.css` define um sistema de design próprio com variáveis CSS (verde escuro, ouro, creme) inspirado na identidade visual do DRE, com tipografia serifada (`Libre Baskerville`) nos títulos e mono (`IBM Plex Mono`) nas etiquetas técnicas. O `app.js` gere toda a interação com a API, incluindo paginação, modais de detalhe, formulários de adição e gestão de relações.

---

## 3. Ontologia em Detalhe

### 3.1 Hierarquia de Classes

A ontologia segue uma hierarquia de três níveis. `DocumentoOficial` é a raiz abstrata. Dela derivam os três tipos de ato. Cada tipo desdobra-se em subclasses concretas — por exemplo, `LeiOrganica` é subclasse de `Lei`, que é subclasse de `AtoNormativo`. `DecretoRegulamentar` é subclasse de `Decreto`. `DespachoExtrato` é subclasse de `Despacho`. `AvisoExtrato` é subclasse de `Aviso`.

### 3.2 Propriedades de Objeto (Relações)

A ontologia define relações explícitas entre documentos com domínio e alcance formais:

- `dre:revoga` / `dre:revogadoPor` — inversas entre si (`owl:inverseOf`)
- `dre:alteradoPor` — liga um documento a outro que o alterou
- `dre:rectificadoPor` — com alcance restrito a `dre:Rectificacao`
- `dre:suspensoPor` — suspensão por outro diploma
- `dre:desenvolve` — diploma regulamentar que desenvolve outro
- `dre:transponeDiretiva` — liga diploma nacional a diretiva europeia

### 3.3 Restrições OWL

A ontologia impõe restrições de cardinalidade sobre `DocumentoOficial`:

- `dre:emitidoPor` com `owl:minCardinality 1` — pelo menos uma entidade emissora
- `dre:dataPublicacao` com `owl:cardinality 1` — exatamente uma data
- `dre:claint` com `owl:cardinality 1` — identificador único obrigatório
- `dre:urlPDF` com `owl:maxCardinality 1` — no máximo um PDF

---

## 4. Base de Dados e Mapeamento

### 4.1 Mapeamento doc_type → OWL

O carregador normaliza os tipos de documento do dataset para classes OWL através do dicionário `DOC_TYPE_MAP`. A normalização remove acentos, converte para minúsculas e faz trim. Se não houver correspondência exata, tenta correspondência parcial; se ainda falhar, atribui `dre:DocumentoOficial` como fallback.

### 4.2 Pesquisa FTS5

O índice FTS5 (`documento_fts`) indexa os campos `claint`, `doc_type`, `numero`, `sumario` e `entidades`. As queries usam o operador `MATCH` com prefixo `*` para suportar pesquisa parcial. O índice é construído em blocos após a inserção de todos os documentos para evitar degradação de performance durante o carregamento.

### 4.3 Enriquecimento

O sistema permite enriquecer a base de dados de três formas:

- Adicionar novos documentos via `/api/documento` (POST) — guardados em `documento_novo`
- Adicionar novas entidades — guardadas em `entidade_nova`
- Criar relações entre documentos via `/api/relacao` — guardadas em `relacao_documento`

As relações têm lógica de inversão no `app.py`: quando um documento é o destino de uma relação `revoga`, a API apresenta-a como `revogadoPor` no contexto desse documento.

---

## 5. Decisões de Design

**SQLite em vez de triple store.** Apesar de o domínio ser modelado em OWL, a aplicação usa SQLite como backend operacional. Esta decisão sacrifica a capacidade de fazer inferência RDFS/OWL mas ganha simplicidade de deployment, performance em leituras e suporte nativo a FTS5.

**FTS combinado com filtros relacionais.** A pesquisa de texto livre e os filtros estruturados (ano, série, categoria, entidade) são combinados numa única query SQL, o que permite resultados consistentes e paginação correta sem múltiplos round-trips à base de dados.

**Enriquecimento não-destrutivo.** Os novos documentos e entidades criados via interface ficam em tabelas separadas (`documento_novo`, `entidade_nova`), não misturados com os dados originais do dataset. Isto preserva a integridade do corpus original e facilita auditoria.

**Normalização de strings.** Tanto o carregador como o servidor usam normalização Unicode (NFKD + remoção de diacríticos + lowercase) para pesquisa e mapeamento, tornando o sistema robusto a variações ortográficas nos dados de origem.

---

## 6. Conclusão

O sistema DRE Ontologia demonstra como uma ontologia OWL pode ser usada como modelo conceptual de um domínio legislativo sem exigir uma triple store como backend. A ontologia define a estrutura, as restrições e as relações; o SQLite garante performance e simplicidade; a API REST expõe tudo de forma uniforme. O resultado é uma aplicação funcional de exploração e enriquecimento de legislação portuguesa, extensível tanto ao nível da ontologia como ao nível da interface.