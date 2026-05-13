#!/usr/bin/env python3
"""
dre_loader.py
Carrega o dataset DRE (JSON.bz2) para uma base de dados SQLite
que suporta a aplicação web de exploração da ontologia DRE.

Uso:
    python3 dre_loader.py <ficheiro.bz2> [--output dre.db] [--limit N]
"""

import bz2
import json
import sqlite3
import argparse
import sys
import re
import unicodedata
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento doc_type → classe OWL (conforme a ontologia dre_ontologia.ttl)
# ─────────────────────────────────────────────────────────────────────────────
DOC_TYPE_MAP = {
    # Atos Normativos
    "lei": "dre:Lei",
    "lei orgânica": "dre:LeiOrganica",
    "decreto-lei": "dre:DecretoLei",
    "decreto lei": "dre:DecretoLei",
    "decreto": "dre:Decreto",
    "decreto regulamentar": "dre:DecretoRegulamentar",
    "portaria": "dre:Portaria",
    "regulamento": "dre:Regulamento",
    "resolução do conselho de ministros": "dre:Resolucao",
    "resolução da assembleia da república": "dre:Resolucao",
    "resolução": "dre:Resolucao",
    "rectificação": "dre:Rectificacao",
    "retificação": "dre:Rectificacao",
    "declaração de retificação": "dre:Rectificacao",
    # Atos Administrativos
    "despacho": "dre:Despacho",
    "despacho (extracto)": "dre:DespachoExtrato",
    "despacho (extrato)": "dre:DespachoExtrato",
    "deliberação": "dre:Deliberacao",
    "deliberação (extracto)": "dre:Deliberacao",
    "deliberação (extrato)": "dre:Deliberacao",
    "contrato": "dre:Contrato",
    "louvor": "dre:Louvor",
    "declaração": "dre:Declaracao",
    # Atos Informativos
    "aviso": "dre:Aviso",
    "aviso (extracto)": "dre:AvisoExtrato",
    "aviso (extrato)": "dre:AvisoExtrato",
    "aviso de contumácia": "dre:AvisoContumax",
    "aviso de prorrogação de prazo": "dre:Aviso",
    "anúncio de procedimento": "dre:AnuncioProcedimento",
    "anúncio": "dre:Anuncio",
    "edital": "dre:Edital",
}

CATEGORY_MAP = {
    "dre:Lei": "Ato Normativo",
    "dre:LeiOrganica": "Ato Normativo",
    "dre:DecretoLei": "Ato Normativo",
    "dre:Decreto": "Ato Normativo",
    "dre:DecretoRegulamentar": "Ato Normativo",
    "dre:Portaria": "Ato Normativo",
    "dre:Regulamento": "Ato Normativo",
    "dre:Resolucao": "Ato Normativo",
    "dre:Rectificacao": "Ato Normativo",
    "dre:Despacho": "Ato Administrativo",
    "dre:DespachoExtrato": "Ato Administrativo",
    "dre:Deliberacao": "Ato Administrativo",
    "dre:Contrato": "Ato Administrativo",
    "dre:Louvor": "Ato Administrativo",
    "dre:Declaracao": "Ato Administrativo",
    "dre:Aviso": "Ato Informativo",
    "dre:AvisoExtrato": "Ato Informativo",
    "dre:AvisoContumax": "Ato Informativo",
    "dre:AnuncioProcedimento": "Ato Informativo",
    "dre:Anuncio": "Ato Informativo",
    "dre:Edital": "Ato Informativo",
}


def normalize(s: str) -> str:
    """Normaliza string para lookup no mapa de tipos."""
    s = unicodedata.normalize("NFC", s.lower().strip())
    return s


def get_owl_class(doc_type: str) -> str:
    key = normalize(doc_type)
    cls = DOC_TYPE_MAP.get(key)
    if cls:
        return cls
    # fallback parcial
    for k, v in DOC_TYPE_MAP.items():
        if k in key or key in k:
            return v
    return "dre:DocumentoOficial"


def create_schema(conn: sqlite3.Connection):
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS documento (
            id          INTEGER PRIMARY KEY,
            claint      INTEGER UNIQUE,
            doc_type    TEXT,
            owl_class   TEXT,
            categoria   TEXT,
            numero      TEXT,
            dr_number   TEXT,
            serie       INTEGER,
            data        TEXT,
            ano         INTEGER,
            sumario     TEXT,
            entidades   TEXT,
            fonte       TEXT,
            dre_key     TEXT,
            in_force    INTEGER,
            conditional INTEGER,
            processing  INTEGER,
            url_pdf     TEXT,
            url_texto   TEXT,
            pdf_error   INTEGER,
            timestamp   TEXT
        );

        CREATE TABLE IF NOT EXISTS entidade_emissora (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            nome    TEXT UNIQUE,
            tipo    TEXT DEFAULT 'dre:EntidadeEmissora'
        );

        CREATE TABLE IF NOT EXISTS documento_entidade (
            doc_id      INTEGER REFERENCES documento(id),
            entidade_id INTEGER REFERENCES entidade_emissora(id),
            PRIMARY KEY (doc_id, entidade_id)
        );

        -- Tabela para relações entre documentos (a preencher via web app)
        CREATE TABLE IF NOT EXISTS relacao_documento (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_origem  INTEGER REFERENCES documento(id),
            tipo_relacao TEXT,  -- revoga, altera, rectifica, desenvolve, etc.
            doc_destino INTEGER REFERENCES documento(id),
            criado_em   TEXT DEFAULT (datetime('now'))
        );

        -- Tabela para novas entidades adicionadas via web app
        CREATE TABLE IF NOT EXISTS entidade_nova (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            tipo        TEXT,
            descricao   TEXT,
            criado_em   TEXT DEFAULT (datetime('now'))
        );

        -- Tabela para novos documentos adicionados via web app
        CREATE TABLE IF NOT EXISTS documento_novo (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_type    TEXT,
            owl_class   TEXT,
            numero      TEXT,
            data        TEXT,
            sumario     TEXT,
            entidades   TEXT,
            fonte       TEXT,
            url_pdf     TEXT,
            criado_em   TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_doc_claint   ON documento(claint);
        CREATE INDEX IF NOT EXISTS idx_doc_type     ON documento(doc_type);
        CREATE INDEX IF NOT EXISTS idx_doc_owl      ON documento(owl_class);
        CREATE INDEX IF NOT EXISTS idx_doc_data     ON documento(data);
        CREATE INDEX IF NOT EXISTS idx_doc_ano      ON documento(ano);
        CREATE INDEX IF NOT EXISTS idx_doc_force    ON documento(in_force);
        CREATE INDEX IF NOT EXISTS idx_doc_serie    ON documento(serie);
        CREATE INDEX IF NOT EXISTS idx_entidade     ON entidade_emissora(nome);

        -- FTS para pesquisa de texto livre
        CREATE VIRTUAL TABLE IF NOT EXISTS documento_fts USING fts5(
            claint,
            doc_type,
            numero,
            sumario,
            entidades,
            content='documento',
            content_rowid='id'
        );
    """)
    conn.commit()
    # Garantir que a coluna 'entidades' existe (para compatibilidade com versões antigas)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(documento)").fetchall()]
    if 'entidades' not in cols:
        conn.execute("ALTER TABLE documento ADD COLUMN entidades TEXT")
        conn.commit()


def load_data(filepath: str, db_path: str, limit: int = None):
    print(f"A abrir {filepath} ...")
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    entidade_cache = {}
    batch_docs = []
    batch_ent_doc = []
    batch_size = 5000
    count = 0
    skipped = 0

    def flush_batch():
        if not batch_docs:
            return

        # Inserir documentos e ligações documento->entidade
        conn.executemany("""
            INSERT OR IGNORE INTO documento
            (claint, doc_type, owl_class, categoria, numero, dr_number, serie,
             data, ano, sumario, entidades, fonte, dre_key, in_force, conditional,
             processing, url_pdf, url_texto, pdf_error, timestamp)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch_docs)

        conn.executemany("""
            INSERT OR IGNORE INTO documento_entidade (doc_id, entidade_id)
            SELECT d.id, ?
            FROM documento d WHERE d.claint = ?
        """, batch_ent_doc)
        # Não actualizar FTS por batch (fazemos build do FTS no final em blocos).
        conn.commit()
        batch_docs.clear()
        batch_ent_doc.clear()

    def get_or_create_entidade(nome: str) -> int:
        if nome in entidade_cache:
            return entidade_cache[nome]
        cur = conn.execute(
            "INSERT OR IGNORE INTO entidade_emissora(nome) VALUES (?)", (nome,))
        conn.commit()
        row = conn.execute(
            "SELECT id FROM entidade_emissora WHERE nome=?", (nome,)).fetchone()
        eid = row[0]
        entidade_cache[nome] = eid
        return eid

    print("A carregar dados ...")
    # O ficheiro pode estar comprimido em bz2 ou ser um JSON plain.
    # Tentamos abrir com bz2 e, se falhar com OSError, abrimos normalmente.
    try:
        with bz2.open(filepath, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        with open(filepath, "rt", encoding="utf-8") as f:
            data = json.load(f)

    total = len(data)
    print(f"Total de registos: {total:,}")

    for rec in data:
        if limit and count >= limit:
            break

        try:
            claint = rec.get("claint")
            doc_type = rec.get("doc_type", "") or ""
            numero = rec.get("number", "") or ""
            dr_number = rec.get("dr_number", "") or ""
            serie = rec.get("series")
            data_pub = rec.get("date", "") or ""
            ano = int(data_pub[:4]) if data_pub and len(data_pub) >= 4 else None
            sumario = rec.get("notes", "") or ""
            fonte = rec.get("source", "") or ""
            dre_key = rec.get("dre_key", "") or ""
            in_force = 1 if rec.get("in_force") else 0
            conditional = 1 if rec.get("conditional") else 0
            processing = 1 if rec.get("processing") else 0
            url_texto = rec.get("plain_text", "") or ""
            url_pdf = rec.get("dre_pdf", "") or ""
            pdf_error = 1 if rec.get("pdf_error") else 0
            timestamp = rec.get("timestamp", "") or ""
            bodies = rec.get("emiting_body", []) or []

            owl_class = get_owl_class(doc_type)
            categoria = CATEGORY_MAP.get(owl_class, "Outro")

            entidades_str = ' | '.join([n.strip() for n in bodies if n]) if bodies else ''
            batch_docs.append((
                claint, doc_type, owl_class, categoria, numero, dr_number,
                serie, data_pub, ano, sumario, entidades_str, fonte, dre_key,
                in_force, conditional, processing,
                url_pdf, url_texto, pdf_error, timestamp
            ))

            for nome in bodies:
                if nome:
                    eid = get_or_create_entidade(nome.strip())
                    batch_ent_doc.append((eid, claint))

            count += 1

            if count % batch_size == 0:
                flush_batch()
                pct = count / total * 100
                print(f"  {count:>8,} / {total:,}  ({pct:.1f}%)  entidades: {len(entidade_cache):,}")

        except Exception as e:
            skipped += 1
            if skipped <= 10:
                print(f"  AVISO: registo ignorado ({e}): claint={rec.get('claint')}")

    flush_batch()

    # Após inserir todos os documentos, construir a tabela FTS em blocos
    try:
        print("Construindo índice FTS em blocos...")
        # Recolher todos os ids e dados necessários em blocos para não esgotar memória
        cur = conn.execute("SELECT COUNT(*) FROM documento")
        total_docs = cur.fetchone()[0]
        batch = 1000
        for offset in range(0, total_docs, batch):
            rows = conn.execute("""
                SELECT d.id, d.claint, d.doc_type, d.numero, d.sumario,
                       (SELECT GROUP_CONCAT(e.nome, ' | ') FROM documento_entidade de JOIN entidade_emissora e ON e.id = de.entidade_id WHERE de.doc_id = d.id)
                FROM documento d
                ORDER BY d.id LIMIT ? OFFSET ?
            """, (batch, offset)).fetchall()
            if rows:
                # apagar entradas antigas para estes rowids e inserir as novas
                rowids = [(r[0],) for r in rows]
                conn.executemany("DELETE FROM documento_fts WHERE rowid = ?", rowids)
                conn.executemany("INSERT INTO documento_fts(rowid, claint, doc_type, numero, sumario, entidades) VALUES (?, ?, ?, ?, ?, ?)", rows)
                conn.commit()
        print("FTS construído com sucesso.")
    except Exception as e:
        print("AVISO: falha ao construir FTS:", e)

    print("\nConcluído!")
    print(f"  Documentos carregados : {count:,}")
    print(f"  Documentos ignorados  : {skipped:,}")
    print(f"  Entidades emissoras   : {len(entidade_cache):,}")

    # Estatísticas finais
    stats = conn.execute("""
        SELECT owl_class, COUNT(*) FROM documento GROUP BY owl_class ORDER BY COUNT(*) DESC LIMIT 15
    """).fetchall()
    print("\nTop classes OWL:")
    for cls, n in stats:
        print(f"  {cls:<40} {n:>10,}")

    conn.close()
    print(f"\nBase de dados: {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carregador do dataset DRE")
    parser.add_argument("ficheiro", help="Ficheiro .bz2 do dataset DRE")
    parser.add_argument("--output", default="dre.db", help="Ficheiro SQLite de saída")
    parser.add_argument("--limit", type=int, default=None, help="Limitar nº de registos (para testes)")
    args = parser.parse_args()

    load_data(args.ficheiro, args.output, args.limit)