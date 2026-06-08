"""
Cache persistente em SQLite para resultados de consulta de EAN.

Funciona como camada L2 (disco) por trás do cache L1 em memória do
EANPicturesService: sobrevive a reinícios do servidor, evitando refazer
consultas externas (que são lentas e têm limites diários).

Thread-safe: uma única conexão com `check_same_thread=False` protegida por
lock — suficiente para o servidor Flask (threaded) e simples de testar.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path


class SqliteCache:
    """Cache chave→produto (dict) persistido em SQLite, com expiração por linha."""

    def __init__(self, path: str | Path, ttl: int = 3600) -> None:
        """
        path: arquivo do banco (criado se não existir; ":memory:" para testes).
        ttl:  tempo de vida padrão em segundos (0 = nunca expira).
        """
        self.path = str(path)
        self.ttl = ttl
        self._lock = threading.Lock()
        # check_same_thread=False: a conexão é compartilhada entre threads do
        # Flask; a serialização fica por conta do nosso _lock.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> dict | None:
        """Devolve o produto guardado, ou None se ausente/expirado."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            value, expires_at = row
            # expires_at == 0 significa "sem expiração".
            if expires_at and time.time() > expires_at:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        """Grava (ou substitui) o produto sob a chave, aplicando o TTL."""
        effective_ttl = self.ttl if ttl is None else ttl
        expires_at = time.time() + effective_ttl if effective_ttl else 0
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, payload, expires_at),
            )
            self._conn.commit()

    def clear(self) -> None:
        """Esvazia todo o cache."""
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()

    def purge_expired(self) -> int:
        """Remove linhas expiradas; devolve quantas foram apagadas."""
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM cache WHERE expires_at != 0 AND expires_at < ?", (now,)
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
