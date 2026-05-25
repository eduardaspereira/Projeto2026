#!/usr/bin/env python3
import bz2
import os
import tempfile
import shutil
import urllib.parse
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD, OWL
import sqlite3
import argparse
import json
import math
import PyPDF2
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

    entity_classes = {
        'dre:EntidadeEmissora', 'dre:OrgaoSoberano', 'dre:Ministerio', 
        'dre:EntidadeLocal', 'dre:EntidadeRegional', 'dre:EntidadePublicaEmpresarial', 'dre:Tribunal'
    }

    # --- 1. PESQUISA DE ENTIDADES ---
    entidades_results = []
    if not (categoria or serie or vigor != "" or ano_ini or ano_fim):
        ent_conds, ent_params = [], []
        if q:
            ent_conds.append("nome LIKE ?")
            ent_params.append(f"%{q}%")
        if entidade:
            ent_conds.append("nome LIKE ?")
            ent_params.append(f"%{entidade}%")
        if owl_class:
            if owl_class in entity_classes:
                ent_conds.append("tipo = ?")
                ent_params.append(owl_class)
            else:
                ent_conds.append("1 = 0") # Se filtrou por "Lei", não mostra entidades

        ent_where = "WHERE " + " AND ".join(ent_conds) if ent_conds else ""
        ents = db.execute(f"SELECT id, nome, tipo FROM entidade_emissora {ent_where} LIMIT 20", ent_params).fetchall()
        
        for e in ents:
            entidades_results.append({
                "id": e["id"],
                "claint": "—",
                "doc_type": "Entidade",
                "owl_class": e["tipo"] or "dre:EntidadeEmissora",
                "categoria": "Entidade",
                "numero": "—",
                "dr_number": "—",
                "serie": "—",
                "data": "—",
                "sumario": e["nome"],
                "in_force": 1,
                "url_pdf": "",
                "is_entity": True
            })

    # --- 2. PESQUISA DE DOCUMENTOS NORMAL ---
    conds, params = [], []

    if owl_class:
        if owl_class in entity_classes:
            # CORREÇÃO: Se clicou numa classe de Entidade (ex: dre:Ministerio),
            # NÃO queremos misturar os documentos emitidos por ela. Apenas a Entidade!
            conds.append("1 = 0")
        else:
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
        fts_ids = db.execute("SELECT rowid FROM documento_fts WHERE documento_fts MATCH ? LIMIT 5000", (q + "*",)).fetchall()
        if fts_ids:
            id_list = ",".join(str(r[0]) for r in fts_ids)
            conds.append(f"d.id IN ({id_list})")
        else:
            conds.append("1 = 0")

    where = "WHERE " + " AND ".join(conds) if conds else ""
    
    if "1 = 0" in conds and not entidades_results:
        return jsonify({"results": [], "total": 0, "page": page, "pages": 0})
        
    total_row = db.execute(f"SELECT COUNT(*) FROM documento d {where}", params).fetchone()
    total_docs = total_row[0] if total_row else 0

    offset = (page - 1) * per_page
    docs_to_fetch = per_page
    
    if page == 1 and entidades_results:
        docs_to_fetch = max(0, per_page - len(entidades_results))
        
    rows = []
    if docs_to_fetch > 0 and "1 = 0" not in conds:
        rows = db.execute(f"""
            SELECT d.id, d.claint, d.doc_type, d.owl_class, d.categoria,
                   d.numero, d.dr_number, d.serie, d.data, d.sumario,
                   d.in_force, d.url_pdf
            FROM documento d
            {where}
            ORDER BY d.data DESC
            LIMIT ? OFFSET ?
        """, params + [docs_to_fetch, offset]).fetchall()

    results = entidades_results if page == 1 else []
    results.extend([dict(r) for r in rows])
    
    total_all = total_docs + len(entidades_results)
    pages = math.ceil(total_all / per_page) if per_page else 1

    return jsonify({"results": results, "total": total_all, "page": page, "pages": pages})

@app.route("/api/rdf/classe", methods=["POST"])
def api_add_rdf_classe():
    """Cria uma nova classe OWL na ontologia (.ttl)"""
    body = request.get_json()
    nome_classe = body.get("nome_classe", "").strip()
    super_classe_uri = body.get("super_classe", "").strip()
    label = body.get("label", "").strip()

    if not nome_classe or not super_classe_uri:
        return jsonify({"ok": False, "error": "Nome da classe e Superclasse são obrigatórios."}), 400

    try:
        g = Graph()
        with open(RDF_FILE, "r", encoding="utf-8") as f:
            g.parse(f, format="turtle")
            
        # Garante que não tem espaços (URL Encode)
        safe_name = urllib.parse.quote(nome_classe.replace(" ", ""))
        nova_classe_uri = DRE_NS[safe_name]
        
        # Injeta os triplos estruturais
        g.add((nova_classe_uri, RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")))
        g.add((nova_classe_uri, RDFS.subClassOf, URIRef(super_classe_uri)))
        
        if label:
            g.add((nova_classe_uri, RDFS.label, Literal(label, lang="pt")))

        # Guarda atómicamente no .ttl em modo binário ('wb')
        fd, temp_path = tempfile.mkstemp(suffix=".ttl")
        os.close(fd) 
        
        with open(temp_path, "wb") as f_out:
            g.serialize(destination=f_out, format="turtle")
            
        shutil.move(temp_path, RDF_FILE)
        
        return jsonify({"ok": True, "uri": str(nova_classe_uri)})

    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"ok": False, "error": f"Erro interno: {str(e)}"}), 500

@app.route("/api/rdf/entidade", methods=["POST"])
def api_add_rdf_entidade():
    """Injeta um novo triplo semântico no .ttl E sincroniza com o SQLite com o tipo correto"""
    body = request.get_json()
    nome = body.get("nome", "").strip()
    tipo_uri = body.get("tipo_uri", "").strip()

    if not nome or not tipo_uri:
        return jsonify({"ok": False, "error": "Nome e Tipo da Entidade são obrigatórios."}), 400

    try:
        # Normaliza a classe para o formato curto do SQLite (ex: dre:Ministerio)
        owl_class_db = tipo_uri.replace("http://dre.pt/ontology#", "dre:")

        # 1. ESCRITA NO SQLITE (Garante tipagem correta para os contadores e filtros)
        db = get_db()
        db.execute("INSERT INTO entidade_nova (nome, tipo) VALUES (?, ?)", (nome, owl_class_db))
        db.execute("""
            INSERT INTO entidade_emissora (nome, tipo) VALUES (?, ?)
            ON CONFLICT(nome) DO UPDATE SET tipo=?
        """, (nome, owl_class_db, owl_class_db))
        db.commit()

        # 2. ESCRITA NO GRAFO RDF (.ttl)
        g = Graph()
        with open(RDF_FILE, "r", encoding="utf-8") as f:
            g.parse(f, format="turtle")
            
        safe_name = urllib.parse.quote(nome.replace(" ", "_"))
        nova_entidade_uri = DRE_NS[safe_name]
        
        g.add((nova_entidade_uri, RDF.type, URIRef(tipo_uri)))
        g.add((nova_entidade_uri, DRE_NS.nome, Literal(nome)))

        fd, temp_path = tempfile.mkstemp(suffix=".ttl")
        os.close(fd) 
        
        with open(temp_path, "wb") as f_out:
            g.serialize(destination=f_out, format="turtle")
            
        shutil.move(temp_path, RDF_FILE)
        return jsonify({"ok": True, "uri": str(nova_entidade_uri)})

    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"ok": False, "error": f"Erro interno: {str(e)}"}), 500


@app.route("/api/rdf/documento", methods=["POST"])
def api_add_rdf_documento():
    """Gera e injeta os triplos no .ttl E guarda no SQLite com tratamento para NameError"""
    body = request.get_json()
    
    # Secção A - RESOLUÇÃO DO NameError: Garantir recolha de todas as variáveis
    tipo_uri = body.get("tipo_uri", "").strip()
    numero = body.get("numero", "").strip()
    data_pub = body.get("data_publicacao", "").strip()
    sumario = body.get("sumario", "").strip()
    dr_number = body.get("dr_number", "").strip()
    url_pdf = body.get("url_pdf", "").strip()
    
    # Secção B
    nome_entidade = body.get("emitido_por_nome", "").strip()
    label_documento = body.get("revoga_label", "").strip()
    assuntos = [a.strip() for a in body.get("assunto", "").split(",") if a.strip()]

    if not tipo_uri or not numero or not data_pub:
        return jsonify({"ok": False, "error": "Tipo, número e data são obrigatórios."}), 400

    try:
        db = get_db()
        
        # CORREÇÃO DA DUPLICAÇÃO: Converte a URI para o prefixo dre: esperado pelo SQLite
        owl_class_db = tipo_uri.replace("http://dre.pt/ontology#", "dre:")
        doc_type_short = tipo_uri.split("#")[-1] if "#" in tipo_uri else tipo_uri.split(":")[-1]
        
        # Extrair ano para consistência do dump original
        ano = int(data_pub[:4]) if data_pub and len(data_pub) >= 4 else None

        # 1. SALVAR NO SQLITE
        cur = db.execute("""
            INSERT INTO documento (doc_type, owl_class, numero, dr_number, data, ano, sumario, entidades, url_pdf, timestamp, in_force)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)
        """, (doc_type_short, owl_class_db, numero, dr_number, data_pub, ano, sumario, nome_entidade, url_pdf))
        
        rowid = cur.lastrowid
        
        db.execute("""
            INSERT INTO documento_novo (doc_type, owl_class, numero, data, sumario, entidades, url_pdf)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (doc_type_short, owl_class_db, numero, data_pub, sumario, nome_entidade, url_pdf))
        
        db.execute("""
            INSERT INTO documento_fts(rowid, claint, doc_type, numero, sumario, entidades) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (rowid, None, doc_type_short, numero, sumario, nome_entidade))
        
        if nome_entidade:
            db.execute("INSERT OR IGNORE INTO entidade_emissora(nome) VALUES (?)", (nome_entidade,))
            eid_row = db.execute("SELECT id FROM entidade_emissora WHERE nome=?", (nome_entidade,)).fetchone()
            if eid_row:
                db.execute("INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)", (rowid, eid_row[0]))
                
        db.commit()

        # 2. SALVAR NO FICHEIRO GRAPH RDF (.ttl)
        g = Graph()
        with open(RDF_FILE, "r", encoding="utf-8") as f:
            g.parse(f, format="turtle")
            
        safe_num = urllib.parse.quote(numero.replace("/", "_").replace(" ", ""))
        doc_uri = DRE_NS[f"Doc_{safe_num}_{data_pub.replace('-','')}"]
        
        g.add((doc_uri, RDF.type, URIRef(tipo_uri)))
        g.add((doc_uri, DRE_NS.numero, Literal(numero, datatype=XSD.string)))
        g.add((doc_uri, DRE_NS.dataPublicacao, Literal(data_pub, datatype=XSD.date)))
        if sumario:
            g.add((doc_uri, DRE_NS.sumario, Literal(sumario, datatype=XSD.string)))
        if dr_number:
            g.add((doc_uri, DRE_NS.numeroDR, Literal(dr_number, datatype=XSD.string)))
        if url_pdf:
            g.add((doc_uri, DRE_NS.urlPDF, Literal(url_pdf, datatype=XSD.anyURI)))

        if nome_entidade:
            safe_ent = urllib.parse.quote(nome_entidade.replace(" ", "_"))
            g.add((doc_uri, DRE_NS.emitidoPor, DRE_NS[safe_ent]))
            g.add((DRE_NS[safe_ent], DRE_NS.emitiu, doc_uri))
            
        if label_documento and "nº" in label_documento:
            try:
                partes = label_documento.split(" nº ")
                num_antigo = partes[1].split(" ")[0]
                data_antiga = partes[1].split("(")[1].replace(")", "").strip()
                safe_num_antigo = urllib.parse.quote(num_antigo.replace("/", "_").replace(" ", ""))
                old_doc_uri = DRE_NS[f"Doc_{safe_num_antigo}_{data_antiga.replace('-','')}"]
                
                g.add((doc_uri, DRE_NS.revoga, old_doc_uri))
                g.add((old_doc_uri, DRE_NS.revogadoPor, doc_uri))
            except Exception:
                pass

        for assunto in assuntos:
            g.add((doc_uri, DRE_NS.tema, Literal(assunto, datatype=XSD.string)))

        fd, temp_path = tempfile.mkstemp(suffix=".ttl")
        os.close(fd) 
        
        with open(temp_path, "wb") as f_out:
            g.serialize(destination=f_out, format="turtle")
            
        shutil.move(temp_path, RDF_FILE)
        return jsonify({"ok": True, "uri": str(doc_uri)})

    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"ok": False, "error": f"Erro interno: {str(e)}"}), 500

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

    inverse_map = {
        'revoga': 'revogadoPor',
        'revogadoPor': 'revoga',
    }
    rel_list = []
    for r in rels:
        rr = dict(r)
        if rr.get('doc_origem') == doc_id:
            rr['tipo_exibicao'] = rr.get('tipo_relacao')
            rr['direcao'] = 'origem'
        else:
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

    try:
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

        rowid = cur.lastrowid

        if entidades:
            for nome in [e.strip() for e in entidades.split("|") if e.strip()]:
                try:
                    db.execute("INSERT OR IGNORE INTO entidade_emissora(nome) VALUES (?)", (nome,))
                    eid = db.execute("SELECT id FROM entidade_emissora WHERE nome=?", (nome,)).fetchone()[0]
                    db.execute("INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)", (rowid, eid))
                except Exception:
                    pass

        try:
            db.execute("INSERT INTO documento_fts(rowid, claint, doc_type, numero, sumario, entidades) VALUES (?, ?, ?, ?, ?, ?)",
                       (rowid, None, doc_type_short, numero, sumario, entidades))
        except Exception:
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

        cur = db.execute("""
            INSERT INTO entidade_nova (nome, tipo, descricao)
            VALUES (?,?,?)
        """, (nome, tipo, descricao))
        entidade_nova_id = cur.lastrowid

        row = db.execute("SELECT id FROM entidade_emissora WHERE UPPER(nome)=UPPER(?)", (nome,)).fetchone()
        linked = 0
        if row:
            eid = row[0]
        else:
            db.execute("INSERT INTO entidade_emissora(nome) VALUES (?)", (nome,))
            eid = db.execute("SELECT id FROM entidade_emissora WHERE UPPER(nome)=UPPER(?)", (nome,)).fetchone()[0]

        target = normalize(nome)
        
        if target:
            docs = db.execute("SELECT id, entidades FROM documento WHERE entidades LIKE ?", (f'%{nome}%',)).fetchall()
            for d in docs:
                tokens = split_entity_tokens(d['entidades'])
                if len(tokens) == 1 and tokens[0] == target:
                    try:
                        db.execute("INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)", (d['id'], eid))
                        linked += 1
                    except Exception:
                        pass

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
    
    row = db.execute('SELECT nome, tipo, descricao, id FROM entidade_nova WHERE id=?', (ent_id,)).fetchone()
    if row:
        nome = row[0]
        entity_tipo = row[1]
        target = normalize(nome)
        
        rows = db.execute("""
            SELECT d.id, d.claint, d.doc_type, d.owl_class, d.categoria,
                   d.numero, d.dr_number, d.serie, d.data, d.sumario,
                   d.in_force, d.url_pdf, d.entidades
            FROM documento d
            WHERE d.entidades IS NOT NULL AND d.entidades LIKE ?
            ORDER BY d.data DESC
        """, ('%'+nome+'%',)).fetchall()
        
        docs = []
        for r in rows:
            rec = dict(r)
            tokens = split_entity_tokens(rec['entidades'])
            if len(tokens) != 1 or tokens[0] != target:
                continue
                
            # CORREÇÃO DEFINITIVA: Mudado de entity_id para entidade_id aqui também
            linked = db.execute("""
                SELECT 1 FROM documento_entidade 
                WHERE doc_id=? AND entidade_id IN (SELECT id FROM entidade_emissora WHERE nome=?)
            """, (rec['id'], nome)).fetchone()
            
            rec['matched_by'] = 'linked' if linked else 'text_match'
            rec['class_match'] = bool(entity_tipo and rec.get('owl_class') and rec.get('owl_class') == entity_tipo)
            
            rec.pop('entidades', None)
            docs.append(rec)
            
        return jsonify({'entity': nome, 'entity_tipo': entity_tipo, 'docs': docs})
    
    row2 = db.execute('SELECT nome FROM entidade_emissora WHERE id=?', (ent_id,)).fetchone()
    if row2:
        nome = row2[0]
        target = normalize(nome)
        tipo_row = db.execute('SELECT tipo FROM entidade_nova WHERE UPPER(nome)=UPPER(?) ORDER BY criado_em DESC LIMIT 1', (nome,)).fetchone()
        entity_tipo = tipo_row[0] if tipo_row else None
        
        rows = db.execute('''
            SELECT d.id, d.claint, d.doc_type, d.owl_class, d.categoria,
                   d.numero, d.dr_number, d.serie, d.data, d.sumario,
                   d.in_force, d.url_pdf, d.entidades,
                   1 AS linked
            FROM documento d
            JOIN documento_entidade de ON de.doc_id = d.id
            WHERE de.entidade_id = ?
            ORDER BY d.data DESC
        ''', (ent_id,)).fetchall()
        
        docs = []
        for r in rows:
            rec = dict(r)
            tokens = split_entity_tokens(rec.get('entidades') or '')
            if len(tokens) != 1 or tokens[0] != target:
                continue
                
            rec['matched_by'] = 'linked'
            rec['class_match'] = bool(entity_tipo and rec.get('owl_class') and rec.get('owl_class') == entity_tipo)
            rec.pop('entidades', None)
            docs.append(rec)
            
        return jsonify({'entity': nome, 'entity_tipo': entity_tipo, 'docs': docs})

    return jsonify({'entity': None, 'docs': []})


@app.route('/api/entidade/<int:ent_id>/link/<int:doc_id>', methods=['POST'])
def api_link_document(ent_id, doc_id):
    db = get_db()
    try:
        nome_row = db.execute('SELECT nome FROM entidade_nova WHERE id=?', (ent_id,)).fetchone()
        real_ent_id = ent_id
        if nome_row:
            emissora = db.execute('SELECT id FROM entidade_emissora WHERE UPPER(nome)=UPPER(?)', (nome_row[0],)).fetchone()
            if emissora:
                real_ent_id = emissora[0]

        db.execute('INSERT OR IGNORE INTO documento_entidade(doc_id, entidade_id) VALUES (?,?)', (doc_id, real_ent_id))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/entidade/<int:ent_id>/link/<int:doc_id>', methods=['DELETE'])
def api_unlink_document(ent_id, doc_id):
    db = get_db()
    try:
        nome_row = db.execute('SELECT nome FROM entidade_nova WHERE id=?', (ent_id,)).fetchone()
        real_ent_id = ent_id
        if nome_row:
            emissora = db.execute('SELECT id FROM entidade_emissora WHERE UPPER(nome)=UPPER(?)', (nome_row[0],)).fetchone()
            if emissora:
                real_ent_id = emissora[0]

        db.execute('DELETE FROM documento_entidade WHERE doc_id=? AND entidade_id=?', (doc_id, real_ent_id))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route("/api/owl-classes")
def api_owl_classes():
    db = get_db()
    
    # 1. Conta as classes dos Documentos
    rows_docs = db.execute("""
        SELECT owl_class, COUNT(*) as count FROM documento 
        WHERE owl_class IS NOT NULL GROUP BY owl_class
    """).fetchall()
    
    # 2. Conta as classes das Novas Entidades
    rows_ents = db.execute("""
        SELECT tipo as owl_class, COUNT(*) as count FROM entidade_nova 
        WHERE tipo IS NOT NULL GROUP BY tipo
    """).fetchall()
    
    counts = {}
    for r in rows_docs:
        counts[r["owl_class"]] = counts.get(r["owl_class"], 0) + r["count"]
        
    for r in rows_ents:
        # Garante que agrupa corretamente convertendo http://... para dre:
        cls = r["owl_class"].replace("http://dre.pt/ontology#", "dre:")
        counts[cls] = counts.get(cls, 0) + r["count"]
        
    # 3. Conta as Entidades Emissoras base do Dump (que por defeito são dre:EntidadeEmissora)
    base_ents = db.execute("SELECT COUNT(*) FROM entidade_emissora").fetchone()[0]
    if base_ents > 0:
        counts["dre:EntidadeEmissora"] = counts.get("dre:EntidadeEmissora", 0) + base_ents
        
    result = [{"owl_class": k, "count": v} for k, v in counts.items()]
    # Ordenar pelos que têm mais contagem
    result.sort(key=lambda x: x["count"], reverse=True)
    return jsonify(result)


@app.route("/api/owl-classes-all")
def api_owl_classes_all():
    """Retorna todas as classes OWL lidas diretamente do ficheiro TTL.

    Cada entrada inclui:
      - cls: forma curta (ex: dre:Ministerio)
      - uri: URI completa
      - label: rótulo legível (se existir)
      - parents: array de classes parent (forma curta)
    """
    try:
        g = Graph()
        g.parse(RDF_FILE, format='turtle')
    except Exception as e:
        return jsonify({'error': 'Não foi possível ler o ficheiro TTL', 'detail': str(e)}), 500

    classes = set()
    # 1) classes explicitamente declaradas como owl:Class
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef):
            classes.add(s)

    # 2) classes usadas como tipo (rdf:type) para instâncias no grafo
    for o in g.objects(None, RDF.type):
        if isinstance(o, URIRef):
            classes.add(o)

    # 3) incluir classes que aparecem nas tabelas SQLite (usadas no DB)
    db = get_db()
    used_classes = db.execute("SELECT DISTINCT owl_class FROM documento WHERE owl_class IS NOT NULL").fetchall()
    for row in used_classes:
        cls = row[0]
        if cls and cls.startswith('dre:'):
            uri = str(DRE_NS[cls.split(':', 1)[1]])
            classes.add(URIRef(uri))

    result = []
    for c in sorted(classes, key=lambda u: str(u)):
        # obter label e parents
        label_lit = g.value(c, RDFS.label)
        label = str(label_lit) if label_lit else (str(c).split('#')[-1] if '#' in str(c) else str(c))
        parents = []
        for p in g.objects(c, RDFS.subClassOf):
            if isinstance(p, URIRef):
                if str(p).startswith(str(DRE_NS)):
                    parents.append('dre:' + str(p).split('#')[-1])
                else:
                    parents.append(str(p))
        short = 'dre:' + str(c).split('#')[-1] if str(c).startswith(str(DRE_NS)) else str(c)
        # Evita chamar g.value com três posicionais (pode causar erro em algumas versões do rdflib)
        declared = (c, RDF.type, OWL.Class) in g
        result.append({'cls': short, 'uri': str(c), 'label': label, 'parents': parents, 'declared': declared})

    # ordenar por label legível
    result.sort(key=lambda x: x.get('label') or x.get('cls'))
    return jsonify(result)


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
        db.execute('DELETE FROM relacao_documento WHERE doc_origem=? OR doc_destino=?', (doc_id, doc_id))
        db.execute('DELETE FROM documento_entidade WHERE doc_id=?', (doc_id,))
        db.execute('DELETE FROM documento WHERE id=?', (doc_id,))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/entidade/<int:ent_id>', methods=['DELETE'])
def api_delete_entidade(ent_id):
    db = get_db()
    try:
        cur = db.execute('DELETE FROM entidade_nova WHERE id=?', (ent_id,))
        if cur.rowcount and cur.rowcount > 0:
            db.commit()
            return jsonify({'ok': True, 'deleted_from': 'entidade_nova'})

        cur2 = db.execute('SELECT id FROM entidade_emissora WHERE id=?', (ent_id,)).fetchone()
            
        if cur2:
            db.execute('DELETE FROM documento_entidade WHERE entidade_id=?', (ent_id,))
            db.execute('DELETE FROM entidade_emissora WHERE id=?', (ent_id,))
            db.commit()
            return jsonify({'ok': True, 'deleted_from': 'entidade_emissora'})

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

# ─────────────────────────────────────────────────────────────────────────────
# Integração Direta com Ficheiro RDF (.bz2)
# ─────────────────────────────────────────────────────────────────────────────

RDF_FILE = "dre_ontologia.ttl"
DRE_NS = Namespace("http://dre.pt/ontology#")



@app.route("/api/extract-pdf", methods=["POST"])
def api_extract_pdf():
    """Lê um PDF, extrai texto e tenta adivinhar metadados."""
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum ficheiro enviado."}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nenhum ficheiro selecionado."}), 400

    try:
        reader = PyPDF2.PdfReader(file)
        text = ""
        # Extrair texto das primeiras 3 páginas (geralmente chega para sumário, data e entidade)
        for i in range(min(3, len(reader.pages))):
            extracted = reader.pages[i].extract_text()
            if extracted:
                text += extracted + "\n"

        # Lógica Simples de "IA" / Regex para pré-preencher
        # 1. Adivinhar Data (ex: 14 de maio de 2026)
        data_encontrada = ""
        match_data = re.search(r'(\d{1,2})\s+de\s+([a-zA-Zçço]+)\s+de\s+(\d{4})', text, re.IGNORECASE)
        if match_data:
            meses = {"janeiro":"01", "fevereiro":"02", "março":"03", "abril":"04", "maio":"05", "junho":"06",
                     "julho":"07", "agosto":"08", "setembro":"09", "outubro":"10", "novembro":"11", "dezembro":"12"}
            dia = match_data.group(1).zfill(2)
            mes_str = match_data.group(2).lower()
            ano = match_data.group(3)
            mes = meses.get(mes_str, "01")
            data_encontrada = f"{ano}-{mes}-{dia}"

        # 2. Adivinhar Sumário
        sumario = ""
        # Procura a palavra "Sumário:" e captura até à quebra de linha dupla
        match_sumario = re.search(r'Sumário:\s*(.*?)(?:\n\n|\Z)', text, re.IGNORECASE | re.DOTALL)
        if match_sumario:
            sumario = match_sumario.group(1).strip().replace('\n', ' ')
        else:
            # Fallback: se não tiver a palavra Sumário, pega nos primeiros 200 caracteres de texto limpo
            texto_limpo = re.sub(r'\s+', ' ', text).strip()
            sumario = texto_limpo[:200] + "..." if len(texto_limpo) > 200 else texto_limpo

        # 3. Adivinhar Entidade Emissora (cruzar texto com SQLite)
        db = get_db()
        entidades_bd = db.execute("SELECT nome FROM entidade_emissora").fetchall()
        entidade_sugerida = ""
        for r in entidades_bd:
            # Se o nome exato da entidade existir no texto do PDF, sugere-a
            if r["nome"].lower() in text.lower():
                entidade_sugerida = r["nome"]
                break

        return jsonify({
            "ok": True,
            "data_publicacao": data_encontrada,
            "sumario": sumario,
            "emitido_por_nome": entidade_sugerida
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao processar o PDF: {str(e)}"}), 500


# Função auxiliar para encontrar subclasses no Grafo
def get_subclasses(g, root_uri):
    query = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?sub WHERE { ?sub rdfs:subClassOf* <%s> . FILTER(?sub != <%s>) }
    """ % (root_uri, root_uri)
    return [str(res.sub) for res in g.query(query)]

@app.route("/api/rdf/classes", methods=["GET"])
def api_rdf_classes_fast():
    """Lê o .ttl para buscar classes que herdam de Entidade."""
    try:
        g = Graph()
        with open(RDF_FILE, "r", encoding="utf-8") as f:
            g.parse(f, format="turtle")
        
        # Busca recursiva de subclasses de EntidadeEmissora
        subs = get_subclasses(g, "http://dre.pt/ontology#EntidadeEmissora")
        
        result = []
        for s in subs:
            label = s.split("#")[-1] # Tenta obter o nome curto
            result.append({"uri": s, "label": label})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rdf/form-options", methods=["GET"])
def api_rdf_form_options_fast():
    """Lê o .ttl para buscar classes que herdam de Documento."""
    try:
        g = Graph()
        with open(RDF_FILE, "r", encoding="utf-8") as f:
            g.parse(f, format="turtle")
            
        # Busca recursiva de subclasses de DocumentoOficial
        subs = get_subclasses(g, "http://dre.pt/ontology#DocumentoOficial")
        
        classes_doc = [{"uri": s, "label": s.split("#")[-1]} for s in subs]

        # Entidades (para o dropdown da Secção B)
        # Usamos uma query para buscar todas as instâncias de sub-classes de EntidadeEmissora
        query_ents = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?ent ?nome WHERE {
                ?ent rdf:type ?type .
                ?type rdfs:subClassOf* <http://dre.pt/ontology#EntidadeEmissora> .
                OPTIONAL { ?ent <http://dre.pt/ontology#nome> ?nome }
            }
        """
        entidades = []
        for r in g.query(query_ents):
            ent_uri = str(r.ent)
            ent_nome = str(r.nome or ent_uri.split("#")[-1])
            entidades.append({"uri": ent_uri, "label": ent_nome})

        return jsonify({"classes_doc": classes_doc, "entidades": entidades, "documentos": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

        


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="dre.db", help="Caminho para a base de dados SQLite")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    DB_PATH = args.db
    print(f"🇵🇹 DRE Ontologia — http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)