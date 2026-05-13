#!/usr/bin/env python3
"""
app.py — Aplicação Web DRE Ontologia
Exploração, consulta e enriquecimento da ontologia do Diário da República.

Instalar dependências:
    pip install flask

Executar:
    python3 app.py --db dre.db [--port 5000]
"""

import sqlite3
import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from flask import (
  Flask, render_template, request, jsonify, g, redirect, url_for
)
import unicodedata
import re

app = Flask(__name__)
DB_PATH = "dre.db"
PER_PAGE = 25

# ─────────────────────────────────────────────────────────────────────────────
# Base de dados

# Nota: todo o HTML/CSS/JS foi movido para `templates/index.html` e `static/`.
# Aqui ficam helpers mínimos de acesso à base de dados usados pelas rotas.
def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def normalize(text):
    if not text:
        return ''
    # remover acentos, normalizar espaços e passar para lower
    nf = unicodedata.normalize('NFKD', text)
    without_accents = ''.join([c for c in nf if not unicodedata.combining(c)])
    s = re.sub(r"[\s]+", ' ', without_accents).strip().lower()
    return s


def split_entity_tokens(field):
    # divide por separadores comuns (pipe, vírgula, ponto-e-vírgula) e por ' | '
    if not field:
        return []
    parts = re.split(r"\||,|;|\/", field)
    return [normalize(p) for p in parts if p and p.strip()]


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
# ─────────────────────────────────────────────────────────────────────────────
# Rotas
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
  return render_template('index.html')


@app.route("/api/search")
def api_search():
    db = get_db()
    q = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "")
    serie = request.args.get("serie", "")
    vigor = request.args.get("vigor", "")
    ano_ini = request.args.get("ano_ini", "")
    ano_fim = request.args.get("ano_fim", "")
    entidade = request.args.get("entidade", "").strip()
    owl_class = request.args.get("owl_class", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = int(request.args.get("per_page", PER_PAGE))

    conds, params = [], []

    if owl_class:
        conds.append("d.owl_class = ?")
        params.append(owl_class)
    if categoria:
        conds.append("d.categoria = ?")
        params.append(categoria)
    if serie:
        conds.append("d.serie = ?")
        params.append(int(serie))
    if vigor != "":
        conds.append("d.in_force = ?")
        params.append(int(vigor))
    if ano_ini:
        conds.append("d.ano >= ?")
        params.append(int(ano_ini))
    if ano_fim:
        conds.append("d.ano <= ?")
        params.append(int(ano_fim))
    if entidade:
        conds.append("""
            EXISTS (
                SELECT 1 FROM documento_entidade de2
                JOIN entidade_emissora e2 ON e2.id = de2.entidade_id
                WHERE de2.doc_id = d.id AND e2.nome LIKE ?
            )
        """)
        params.append(f"%{entidade}%")

    if q:
        # FTS
        fts_ids = db.execute(
            "SELECT rowid FROM documento_fts WHERE documento_fts MATCH ? LIMIT 5000",
            (q + "*",)
        ).fetchall()
        if fts_ids:
            id_list = ",".join(str(r[0]) for r in fts_ids)
            conds.append(f"d.id IN ({id_list})")
        else:
            return jsonify({"results": [], "total": 0, "page": page, "pages": 0})

    where = "WHERE " + " AND ".join(conds) if conds else ""

    total_row = db.execute(
        f"SELECT COUNT(*) FROM documento d {where}", params
    ).fetchone()
    total = total_row[0] if total_row else 0

    offset = (page - 1) * per_page
    rows = db.execute(f"""
        SELECT d.id, d.claint, d.doc_type, d.owl_class, d.categoria,
               d.numero, d.dr_number, d.serie, d.data, d.sumario,
               d.in_force, d.url_pdf
        FROM documento d
        {where}
        ORDER BY d.data DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset]).fetchall()

    results = [dict(r) for r in rows]
    pages = math.ceil(total / per_page) if per_page else 1

    return jsonify({"results": results, "total": total, "page": page, "pages": pages})


@app.route("/api/documento/<int:doc_id>")
def api_documento(doc_id):
    db = get_db()
    row = db.execute("SELECT * FROM documento WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return jsonify({"error": "Não encontrado"}), 404
    d = dict(row)

    entidades = db.execute("""
        SELECT e.nome FROM entidade_emissora e
        JOIN documento_entidade de ON de.entidade_id = e.id
        WHERE de.doc_id = ?
    """, (doc_id,)).fetchall()
    d["entidades"] = [r[0] for r in entidades]

    rels = db.execute("""
        SELECT r.tipo_relacao,
               r.id AS rel_id,
               r.doc_origem, r.doc_destino,
               d2.claint AS claint_destino, d2.numero AS numero_destino,
               d1.claint AS claint_origem,  d1.numero AS numero_origem
        FROM relacao_documento r
        LEFT JOIN documento d2 ON d2.id = r.doc_destino
        LEFT JOIN documento d1 ON d1.id = r.doc_origem
        WHERE r.doc_origem = ? OR r.doc_destino = ?
    """, (doc_id, doc_id)).fetchall()

    # construir representação com rótulo de exibição que depende da direção
    inverse_map = {
        'revoga': 'revogadoPor',
        'revogadoPor': 'revoga',
    }
    rel_list = []
    for r in rels:
        rr = dict(r)
        # determinar se o documento atual é origem ou destino
        if rr.get('doc_origem') == doc_id:
            rr['tipo_exibicao'] = rr.get('tipo_relacao')
            rr['direcao'] = 'origem'
        else:
            # destino: inverter o rótulo quando possível
            rr['tipo_exibicao'] = inverse_map.get(rr.get('tipo_relacao'), rr.get('tipo_relacao'))
            rr['direcao'] = 'destino'
        rel_list.append(rr)
    d["relacoes"] = rel_list

    return jsonify(d)


@app.route("/api/relacao", methods=["POST"])
def api_relacao():
    db = get_db()
    body = request.get_json()
    doc_id = body.get("doc_id")
    tipo = body.get("tipo_relacao")
    claint_dest = body.get("claint_destino")
    doc_destino = body.get("doc_destino")

    dest_id = None
    if claint_dest is not None:
        dest_row = db.execute(
            "SELECT id FROM documento WHERE claint=?", (claint_dest,)).fetchone()
        if dest_row:
            dest_id = dest_row[0]
    # fallback: accept explicit document id
    if dest_id is None and doc_destino is not None:
        dest_id = int(doc_destino)

    if dest_id is None:
        return jsonify({"ok": False, "error": "Documento destino não encontrado (forneça claint_destino ou doc_destino)"})

    db.execute("""
        INSERT INTO relacao_documento (doc_origem, tipo_relacao, doc_destino)
        VALUES (?, ?, ?)
    """, (doc_id, tipo, dest_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/documento", methods=["POST"])
def api_add_documento():
    db = get_db()
    body = request.get_json()

    # Inserir numa tabela de rascunho (documento_novo) e também adicionar
    # uma entrada mínima na tabela `documento` e no índice FTS para que
    # o documento apareça imediatamente nas pesquisas.
    try:
        # guardar na tabela de documentos novos (mantemos comportamento antigo)
        db.execute("""
            INSERT INTO documento_novo (doc_type, owl_class, numero, data, sumario, entidades, fonte, url_pdf)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            body.get("owl_class", "").split(":")[-1],
            body.get("owl_class"),
            body.get("numero"),
            body.get("data"),
            body.get("sumario"),
            body.get("entidades"),
            body.get("fonte"),
            body.get("url_pdf"),
        ))

        # Inserção mínima na tabela principal `documento`.
        doc_type_short = (body.get("owl_class") or "").split(":")[-1]
        owl_class_full = body.get("owl_class")
        numero = body.get("numero")
        data_val = body.get("data")
        sumario = body.get("sumario")
        entidades = body.get("entidades")
        fonte = body.get("fonte")
        url_pdf = body.get("url_pdf")

        cur = db.execute("""
            INSERT INTO documento (doc_type, owl_class, numero, data, sumario, entidades, fonte, url_pdf, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (doc_type_short, owl_class_full, numero, data_val, sumario, entidades, fonte, url_pdf))

        # Obter rowid do documento inserido
        rowid = cur.lastrowid

        # Atualizar mapeamentos de entidades (opcional: tenta manter consistência)
        if entidades:
            # entidades podem vir como 'A | B | C' ou lista; tratamos string
            for nome in [e.strip() for e in entidades.split("|") if e.strip()]:
                try:
                    db.execute("INSERT OR IGNORE INTO entidade_emissora(nome) VALUES (?)", (nome,))
                    eid = db.execute("SELECT id FROM entidade_emissora WHERE nome=?", (nome,)).fetchone()[0]
                    db.execute("INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)", (rowid, eid))
                except Exception:
                    pass

        # Inserir também no índice FTS para pesquisa imediata
        try:
            db.execute("INSERT INTO documento_fts(rowid, claint, doc_type, numero, sumario, entidades) VALUES (?, ?, ?, ?, ?, ?)",
                       (rowid, None, doc_type_short, numero, sumario, entidades))
        except Exception:
            # Se a tabela FTS não existir por algum motivo, ignoramos (ela será reconstruída mais tarde)
            pass

        db.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/entidade", methods=["POST"])
def api_add_entidade():
    db = get_db()
    body = request.get_json()
    try:
        nome = (body.get("nome") or "").strip()
        tipo = body.get("tipo")
        descricao = body.get("descricao")

        # enregistrar na tabela de sugestões (mantemos histórico)
        cur = db.execute("""
            INSERT INTO entidade_nova (nome, tipo, descricao)
            VALUES (?,?,?)
        """, (nome, tipo, descricao))
        entidade_nova_id = cur.lastrowid

        # Verificar se já existe uma entidade canónica com este nome
        row = db.execute("SELECT id FROM entidade_emissora WHERE UPPER(nome)=UPPER(?)", (nome,)).fetchone()
        linked = 0
        if row:
            eid = row[0]
            # associar (INSERT OR IGNORE) todos os documentos cujo campo `entidades`
            # contenha o token exacto do nome (tokenizado/normalizado)
            target = normalize(nome)
            docs = db.execute("SELECT id, entidades FROM documento WHERE entidades IS NOT NULL").fetchall()
            for d in docs:
                tokens = split_entity_tokens(d['entidades'])
                if target in tokens:
                    try:
                        db.execute("INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)", (d['id'], eid))
                        linked += 1
                    except Exception:
                        pass
        else:
            # criar nova entidade canónica
            db.execute("INSERT INTO entidade_emissora(nome) VALUES (?)", (nome,))
            eid = db.execute("SELECT id FROM entidade_emissora WHERE UPPER(nome)=UPPER(?)", (nome,)).fetchone()[0]

        db.commit()
        return jsonify({"ok": True, "linked_documents": linked, "entity_id": entidade_nova_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/adicionados")
def api_adicionados():
    db = get_db()
    docs = db.execute(
        "SELECT * FROM documento_novo ORDER BY criado_em DESC LIMIT 20"
    ).fetchall()
    ents = db.execute(
        "SELECT * FROM entidade_nova ORDER BY criado_em DESC LIMIT 20"
    ).fetchall()
    return jsonify({"docs": [dict(r) for r in docs], "entidades": [dict(r) for r in ents]})


@app.route('/api/entidade/<int:ent_id>/docs')
def api_entidade_docs(ent_id):
    db = get_db()
    
    # Prioridade: procurar primeiro na entidade_nova (entidades adicionadas)
    row = db.execute('SELECT nome, tipo, descricao FROM entidade_nova WHERE id=?', (ent_id,)).fetchone()
    if row:
        nome = row[0]
        entity_tipo = row[1]
        rows = db.execute("""
            SELECT d.id, d.claint, d.doc_type, d.owl_class, d.categoria,
                   d.numero, d.dr_number, d.serie, d.data, d.sumario,
                   d.in_force, d.url_pdf
            FROM documento d
            WHERE d.entidades IS NOT NULL AND UPPER(d.entidades) LIKE UPPER(?)
            ORDER BY d.data DESC
        """, ('%'+nome+'%',)).fetchall()
        docs = []
        for r in rows:
            rec = dict(r)
            linked = db.execute('SELECT 1 FROM documento_entidade WHERE doc_id=? AND entidade_id IN (SELECT id FROM entidade_emissora WHERE nome=?)', (rec['id'], nome)).fetchone()
            rec['matched_by'] = 'linked' if linked else 'text_match'
            rec['class_match'] = bool(entity_tipo and rec.get('owl_class') and rec.get('owl_class') == entity_tipo)
            docs.append(rec)
        return jsonify({'entity': nome, 'entity_tipo': entity_tipo, 'docs': docs})
    
    # Fallback: procurar na entidade_emissora (entidades canónicas)
    row2 = db.execute('SELECT nome FROM entidade_emissora WHERE id=?', (ent_id,)).fetchone()
    if row2:
        nome = row2[0]
        tipo_row = db.execute('SELECT tipo FROM entidade_nova WHERE UPPER(nome)=UPPER(?) ORDER BY criado_em DESC LIMIT 1', (nome,)).fetchone()
        entity_tipo = tipo_row[0] if tipo_row else None
        rows = db.execute('''
            SELECT d.id, d.claint, d.doc_type, d.owl_class, d.categoria,
                   d.numero, d.dr_number, d.serie, d.data, d.sumario,
                   d.in_force, d.url_pdf,
                   1 AS linked
            FROM documento d
            JOIN documento_entidade de ON de.doc_id = d.id
            WHERE de.entidade_id = ?
            ORDER BY d.data DESC
        ''', (ent_id,)).fetchall()
        docs = []
        for r in rows:
            rec = dict(r)
            rec['matched_by'] = 'linked'
            rec['class_match'] = bool(entity_tipo and rec.get('owl_class') and rec.get('owl_class') == entity_tipo)
            docs.append(rec)
        return jsonify({'entity': nome, 'entity_tipo': entity_tipo, 'docs': docs})

    return jsonify({'entity': None, 'docs': []})


@app.route('/api/entidade/<int:ent_id>/link/<int:doc_id>', methods=['POST'])
def api_link_document(ent_id, doc_id):
    db = get_db()
    try:
        # garantir que a entidade existe
        if not db.execute('SELECT 1 FROM entidade_emissora WHERE id=?', (ent_id,)).fetchone():
            return jsonify({'ok': False, 'error': 'Entidade canónica não encontrada'})
        db.execute('INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)', (doc_id, ent_id))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/entidade/<int:ent_id>/link/<int:doc_id>', methods=['DELETE'])
def api_unlink_document(ent_id, doc_id):
    db = get_db()
    try:
        db.execute('DELETE FROM documento_entidade WHERE doc_id=? AND entidade_id=?', (doc_id, ent_id))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route("/api/owl-classes")
def api_owl_classes():
    db = get_db()
    rows = db.execute("""
        SELECT owl_class, COUNT(*) as count FROM documento
        GROUP BY owl_class ORDER BY count DESC
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/quickstats")
def api_quickstats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM documento").fetchone()[0]
    em_vigor = db.execute("SELECT COUNT(*) FROM documento WHERE in_force=1").fetchone()[0]
    serie_1 = db.execute("SELECT COUNT(*) FROM documento WHERE serie=1").fetchone()[0]
    serie_2 = db.execute("SELECT COUNT(*) FROM documento WHERE serie=2").fetchone()[0]
    com_pdf = db.execute("SELECT COUNT(*) FROM documento WHERE url_pdf!='' AND pdf_error=0").fetchone()[0]
    entidades = db.execute("SELECT COUNT(*) FROM entidade_emissora").fetchone()[0]
    return jsonify({"total": total, "em_vigor": em_vigor, "serie_1": serie_1,
                    "serie_2": serie_2, "com_pdf": com_pdf, "entidades": entidades})


@app.route("/api/stats")
def api_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM documento").fetchone()[0]
    em_vigor = db.execute("SELECT COUNT(*) FROM documento WHERE in_force=1").fetchone()[0]
    n_entidades = db.execute("SELECT COUNT(*) FROM entidade_emissora").fetchone()[0]
    com_pdf = db.execute(
        "SELECT COUNT(*) FROM documento WHERE url_pdf!='' AND pdf_error=0").fetchone()[0]

    ano_min = db.execute("SELECT MIN(ano) FROM documento WHERE ano IS NOT NULL").fetchone()[0]
    ano_max = db.execute("SELECT MAX(ano) FROM documento WHERE ano IS NOT NULL").fetchone()[0]
    anos_cobertura = (ano_max - ano_min + 1) if ano_min and ano_max else 0

    top_tipos = [{"label": r[0], "count": r[1]} for r in db.execute("""
        SELECT doc_type, COUNT(*) c FROM documento
        GROUP BY doc_type ORDER BY c DESC LIMIT 15
    """).fetchall()]

    top_entidades = [{"label": r[0], "count": r[1]} for r in db.execute("""
        SELECT e.nome, COUNT(*) c FROM entidade_emissora e
        JOIN documento_entidade de ON de.entidade_id = e.id
        GROUP BY e.nome ORDER BY c DESC LIMIT 15
    """).fetchall()]

    por_serie = db.execute("""
        SELECT serie, COUNT(*) FROM documento WHERE serie IS NOT NULL
        GROUP BY serie ORDER BY serie
    """).fetchall()

    por_decada = [{"label": r[0], "count": r[1]} for r in db.execute("""
        SELECT (ano/10*10)||'s' as decada, COUNT(*) c
        FROM documento WHERE ano IS NOT NULL
        GROUP BY decada ORDER BY decada
    """).fetchall()]

    return jsonify({
        "total": total, "em_vigor": em_vigor, "n_entidades": n_entidades,
        "com_pdf": com_pdf, "anos_cobertura": anos_cobertura,
        "top_tipos": top_tipos, "top_entidades": top_entidades,
        "por_serie": [list(r) for r in por_serie], "por_decada": por_decada
    })


@app.route('/api/documento/<int:doc_id>', methods=['DELETE'])
def api_delete_documento(doc_id):
    db = get_db()
    try:
        # remover relações onde participa
        db.execute('DELETE FROM relacao_documento WHERE doc_origem=? OR doc_destino=?', (doc_id, doc_id))
        # remover ligações documento -> entidade
        db.execute('DELETE FROM documento_entidade WHERE doc_id=?', (doc_id,))
        # remover o próprio documento (apenas rascunhos podem ser removidos normalmente, mas suportamos aqui)
        db.execute('DELETE FROM documento WHERE id=?', (doc_id,))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/entidade/<int:ent_id>', methods=['DELETE'])
def api_delete_entidade(ent_id):
    db = get_db()
    try:
        # Tentamos primeiro eliminar da tabela de sugestões (entidade_nova)
        cur = db.execute('DELETE FROM entidade_nova WHERE id=?', (ent_id,))
        if cur.rowcount and cur.rowcount > 0:
            db.commit()
            return jsonify({'ok': True, 'deleted_from': 'entidade_nova'})

        # Caso não exista nas sugestões, pode tratar-se de uma entidade canónica
        # remover ligações documento <-> entidade e depois a própria entidade
        cur2 = db.execute('SELECT id FROM entidade_emissora WHERE id=?', (ent_id,)).fetchone()
        if cur2:
            # remover ligações
            db.execute('DELETE FROM documento_entidade WHERE entidade_id=?', (ent_id,))
            db.execute('DELETE FROM entidade_emissora WHERE id=?', (ent_id,))
            db.commit()
            return jsonify({'ok': True, 'deleted_from': 'entidade_emissora'})

        # não encontrado
        return jsonify({'ok': False, 'error': 'Entidade não encontrada'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/relacao/<int:rel_id>', methods=['DELETE'])
def api_delete_relacao(rel_id):
    db = get_db()
    try:
        db.execute('DELETE FROM relacao_documento WHERE id=?', (rel_id,))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/documento_novo/<int:doc_id>', methods=['DELETE'])
def api_delete_documento_novo(doc_id):
    db = get_db()
    try:
        db.execute('DELETE FROM documento_novo WHERE id=?', (doc_id,))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/documento_novo/<int:doc_id>')
def api_get_documento_novo(doc_id):
    db = get_db()
    row = db.execute('SELECT * FROM documento_novo WHERE id=?', (doc_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Não encontrado'}), 404
    return jsonify(dict(row))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="dre.db", help="Caminho para a base de dados SQLite")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    DB_PATH = args.db
    print(f"🇵🇹 DRE Ontologia — http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)

