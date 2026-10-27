"""Pure-Python fallback for ``openjarvis_rust`` on Windows/systems without Rust/MSVC.

Provides full implementations of:
- ``SQLiteMemory`` (SQLite3 + FTS5 full-text search)
- ``BM25Memory`` (in-memory Okapi BM25 ranking)
- ``SecretScanner`` & ``PIIScanner`` (regex-based secret/PII detection & redaction)
- ``CapabilityPolicy`` (glob-based RBAC permission checks)
- ``RateLimiter`` (thread-safe token bucket)
- ``is_sensitive_file`` (glob-based sensitive path check)

For tool classes that already have pure-Python implementations in their own
modules (``CalculatorTool``, ``FileReadTool``, ``FileWriteTool``, ``ShellExecTool``,
``HttpRequestTool``, ``ThinkTool``, ``GitStatusTool``, etc.), ``__getattr__`` raises
``ImportError`` so those callers transparently fall through to their native
Python code paths.
"""

from __future__ import annotations

import fnmatch
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SQLiteMemory:
    """Pure-Python SQLite + FTS5 memory backend matching ``openjarvis_rust.SQLiteMemory``."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._has_fts5 = self._init_schema()

    def _init_schema(self) -> bool:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                )
                """
            )
            has_fts = False
            try:
                self._conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                    USING fts5(doc_id UNINDEXED, content, source, tokenize='porter unicode61')
                    """
                )
                has_fts = True
            except sqlite3.OperationalError:
                has_fts = False
            self._conn.commit()
            return has_fts

    def store(self, content: str, source: str = "", metadata_json: Optional[str] = None) -> str:
        doc_id = uuid.uuid4().hex[:16]
        meta_str = metadata_json if metadata_json else "{}"
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (id, content, source, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                (doc_id, content, source or "", meta_str, now),
            )
            if self._has_fts5:
                self._conn.execute(
                    "INSERT INTO documents_fts (doc_id, content, source) VALUES (?, ?, ?)",
                    (doc_id, content, source or ""),
                )
            self._conn.commit()
        return doc_id

    def replace_source(
        self,
        source: str,
        documents: List[Tuple[str, Optional[str]]],
    ) -> List[str]:
        doc_ids: List[str] = []
        now = time.time()
        with self._lock:
            if self._has_fts5:
                self._conn.execute("DELETE FROM documents_fts WHERE source = ?", (source,))
            self._conn.execute("DELETE FROM documents WHERE source = ?", (source,))
            for content, meta_json in documents:
                doc_id = uuid.uuid4().hex[:16]
                meta_str = meta_json if meta_json else "{}"
                self._conn.execute(
                    "INSERT INTO documents (id, content, source, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, content, source or "", meta_str, now),
                )
                if self._has_fts5:
                    self._conn.execute(
                        "INSERT INTO documents_fts (doc_id, content, source) VALUES (?, ?, ?)",
                        (doc_id, content, source or ""),
                    )
                doc_ids.append(doc_id)
            self._conn.commit()
        return doc_ids

    def retrieve(self, query: str, top_k: int = 5) -> str:
        tokens = [re.sub(r"[^\w]", "", t) for t in query.split()]
        tokens = [t for t in tokens if t]
        if not tokens:
            return "[]"

        results: List[Dict[str, Any]] = []
        with self._lock:
            if self._has_fts5:
                fts_query = " OR ".join(f'"{t}"' for t in tokens)
                try:
                    rows = self._conn.execute(
                        """
                        SELECT d.content, d.source, d.metadata, bm25(documents_fts) as rank
                        FROM documents_fts f
                        JOIN documents d ON d.id = f.doc_id
                        WHERE documents_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_query, top_k),
                    ).fetchall()
                    for content, source, meta_str, rank in rows:
                        score = 1.0 / (1.0 + abs(float(rank or 0.0)))
                        results.append(
                            {
                                "content": content,
                                "score": score,
                                "source": source,
                                "metadata": meta_str,
                            }
                        )
                except sqlite3.OperationalError:
                    pass

            if not results:
                rows = self._conn.execute(
                    "SELECT content, source, metadata FROM documents ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
                scored = []
                q_lower = [t.lower() for t in tokens]
                for content, source, meta_str in rows:
                    c_lower = content.lower()
                    hits = sum(1 for t in q_lower if t in c_lower)
                    if hits > 0:
                        scored.append(
                            (
                                hits / len(q_lower),
                                {
                                    "content": content,
                                    "score": hits / len(q_lower),
                                    "source": source,
                                    "metadata": meta_str,
                                },
                            )
                        )
                scored.sort(key=lambda x: x[0], reverse=True)
                results = [item for _, item in scored[:top_k]]

        return json.dumps(results)

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            if self._has_fts5:
                self._conn.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM documents")
            if self._has_fts5:
                self._conn.execute("DELETE FROM documents_fts")
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()
            return int(row[0]) if row else 0


class BM25Memory:
    """Pure-Python in-memory BM25 backend matching ``openjarvis_rust.BM25Memory``."""

    def __init__(self) -> None:
        self._docs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def store(self, content: str, source: str = "", metadata_json: Optional[str] = None) -> str:
        doc_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._docs[doc_id] = {
                "id": doc_id,
                "content": content,
                "source": source or "",
                "metadata": metadata_json or "{}",
                "tokens": content.lower().split(),
            }
        return doc_id

    def retrieve(self, query: str, top_k: int = 5) -> str:
        q_tokens = query.lower().split()
        if not q_tokens:
            return "[]"
        with self._lock:
            docs = list(self._docs.values())
        if not docs:
            return "[]"

        n_docs = len(docs)
        avgdl = sum(len(d["tokens"]) for d in docs) / max(n_docs, 1)
        k1 = 1.5
        b = 0.75

        scored = []
        for d in docs:
            tokens = d["tokens"]
            dl = len(tokens)
            score = 0.0
            for qt in q_tokens:
                tf = tokens.count(qt)
                if tf == 0:
                    continue
                df = sum(1 for doc in docs if qt in doc["tokens"])
                idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / max(avgdl, 1e-6)))))
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "content": d["content"],
                            "score": score,
                            "source": d["source"],
                            "metadata": d["metadata"],
                        },
                    )
                )
        scored.sort(key=lambda x: x[0], reverse=True)
        return json.dumps([item for _, item in scored[:top_k]])

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            return self._docs.pop(doc_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._docs.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._docs)


class _RegexScanner:
    """Shared regex scanner implementation for SecretScanner and PIIScanner."""

    PATTERNS: Dict[str, Tuple[str, str, str]] = {}

    def scan(self, text: str) -> str:
        findings = []
        for name, (pattern, level, desc) in self.PATTERNS.items():
            for match in re.finditer(pattern, text):
                findings.append(
                    {
                        "pattern_name": name,
                        "matched_text": match.group(0),
                        "threat_level": level,
                        "start": match.start(),
                        "end": match.end(),
                        "description": desc,
                    }
                )
        return json.dumps({"findings": findings})

    def redact(self, text: str) -> str:
        result = text
        for name, (pattern, _, _) in self.PATTERNS.items():
            result = re.sub(pattern, f"[REDACTED:{name}]", result)
        return result


class SecretScanner(_RegexScanner):
    PATTERNS = {
        "openai_key": (r"sk-[A-Za-z0-9_-]{20,}", "critical", "OpenAI API key"),
        "anthropic_key": (r"sk-ant-[A-Za-z0-9_-]{20,}", "critical", "Anthropic API key"),
        "aws_access_key": (r"AKIA[0-9A-Z]{16}", "critical", "AWS access key"),
        "github_token": (r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}", "critical", "GitHub token"),
        "password_assignment": (r"""(?:password|passwd|pwd)\s*[=:]\s*['"]([^'"]{4,})['"]""", "high", "Password assignment"),
        "db_connection_string": (r"(?:postgres|mysql|mongodb|redis)://[^\s]{10,}", "high", "Database connection string"),
        "private_key": (r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "critical", "Private key"),
        "slack_token": (r"xox[bpors]-[A-Za-z0-9\-]{10,}", "high", "Slack token"),
        "stripe_key": (r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{20,}", "critical", "Stripe key"),
        "generic_api_key": (r"""(?:api_key|secret_key|auth_token)\s*[=:]\s*['"]([^'"]{8,})['"]""", "high", "Generic API key/secret"),
    }


class PIIScanner(_RegexScanner):
    PATTERNS = {
        "email": (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "medium", "Email address"),
        "us_ssn": (r"\b\d{3}-\d{2}-\d{4}\b", "critical", "US Social Security Number"),
        "credit_card_visa": (r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "critical", "Visa credit card"),
        "credit_card_mastercard": (r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "critical", "Mastercard credit card"),
        "credit_card_amex": (r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b", "critical", "Amex credit card"),
        "us_phone": (r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "medium", "US phone number"),
        "ipv4_public": (
            r"\b(?!10\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)(?!192\.168\.)(?!127\.)(?!0\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            "low",
            "Public IPv4 address",
        ),
    }


class CapabilityPolicy:
    """Pure-Python RBAC policy matching ``openjarvis_rust.CapabilityPolicy``."""

    def __init__(self, default_deny: bool = False) -> None:
        self._default_deny = default_deny
        self._grants: Dict[str, List[Tuple[str, str]]] = {}
        self._denies: Dict[str, List[str]] = {}

    def grant(self, agent_id: str, capability: str, pattern: str = "*") -> None:
        self._grants.setdefault(agent_id, []).append((capability, pattern))

    def deny(self, agent_id: str, capability: str) -> None:
        self._denies.setdefault(agent_id, []).append(capability)

    def check(self, agent_id: str, capability: str, resource: str = "") -> bool:
        if agent_id not in self._grants and agent_id not in self._denies:
            return not self._default_deny

        for denied in self._denies.get(agent_id, []):
            if fnmatch.fnmatch(capability, denied):
                return False

        for cap_pat, res_pat in self._grants.get(agent_id, []):
            if fnmatch.fnmatch(capability, cap_pat):
                if resource and res_pat != "*":
                    if fnmatch.fnmatch(resource, res_pat):
                        return True
                else:
                    return True

        return not self._default_deny


class RateLimiter:
    """Pure-Python token-bucket rate limiter matching ``openjarvis_rust.RateLimiter``."""

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10) -> None:
        self._rate = max(requests_per_minute, 1) / 60.0
        self._capacity = max(burst_size, 1)
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, float]:
        with self._lock:
            now = time.monotonic()
            tokens, last = self._buckets.get(key, (float(self._capacity), now))
            elapsed = max(0.0, now - last)
            tokens = min(float(self._capacity), tokens + elapsed * self._rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            wait = (1.0 - tokens) / self._rate
            self._buckets[key] = (tokens, now)
            return False, wait

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._buckets.pop(key, None)
            else:
                self._buckets.clear()


_SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "*.env",
    ".secret",
    "*.secrets",
    "credentials.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "id_rsa",
    "id_ed25519",
    ".htpasswd",
    ".pgpass",
    ".netrc",
    ".git-credentials",
    "credentials",
    "shadow",
    "gshadow",
    "pass.txt",
    "password.txt",
    "passwords.txt",
)


def is_sensitive_file(path_str: str) -> bool:
    p = Path(path_str)
    name = p.name
    for pattern in _SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(p), pattern):
            return True
    return False


def __getattr__(name: str) -> Any:
    raise ImportError(
        f"openjarvis_rust.{name} is not compiled; falling back to pure-Python implementation."
    )
