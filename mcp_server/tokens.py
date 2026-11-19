"""Pre-shared bearer tokens for the HTTP transport (ADR-0004).

The token file holds each token's id, scopes and SHA-256, never the token:
a token is 32 random bytes, so its unsalted hash cannot be reversed by
guessing. The file is reread when it changes, so a revoked token stops
working without a restart. Stdio has no tokens.
"""

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from mcp.server.auth.provider import AccessToken

READ, REVIEW = "read", "review"
SCOPES = (READ, REVIEW)
# review includes read: a reviewer reads its own result
IMPLIED = {REVIEW: {READ, REVIEW}, READ: {READ}}
ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def effective_scopes(scopes) -> List[str]:
    out = set()
    for s in scopes:
        out |= IMPLIED.get(s, set())
    return sorted(out)


class TokenStore:
    """The token file: {"tokens": [{"id", "sha256", "scopes", "created_utc"}]}."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._stamp = None
        self._entries: list = []

    def entries(self) -> list:
        try:
            st = self.path.stat()
        except FileNotFoundError:
            self._stamp, self._entries = None, []
            return []
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp != self._stamp:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = [e for e in data.get("tokens", [])
                             if isinstance(e, dict) and e.get("id") and e.get("sha256")]
            self._stamp = stamp
        return list(self._entries)

    def verify(self, token: str) -> Optional[dict]:
        """The entry whose hash matches token, compared in constant time."""
        if not token:
            return None
        digest = token_hash(token)
        found = None
        for entry in self.entries():
            if hmac.compare_digest(digest, str(entry["sha256"])):
                found = entry
        return found

    def _write(self, entries: list) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"tokens": entries}, indent=2), encoding="utf-8")
        if os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def add(self, token_id: str, scopes: List[str]) -> str:
        """Mint a token for token_id and store its hash; returns the token,
        which is never stored."""
        if not token_id or len(token_id) > 64 or set(token_id) - ID_CHARS:
            raise ValueError("a token id is 1-64 of letters, digits, '.', '_' and '-'")
        bad = [s for s in scopes if s not in SCOPES]
        if bad or not scopes:
            raise ValueError(f"scopes must be among {', '.join(SCOPES)}")
        entries = self.entries()
        if any(e["id"] == token_id for e in entries):
            raise ValueError(f"a token named {token_id!r} exists; revoke it first")
        token = secrets.token_urlsafe(32)
        entries.append({"id": token_id, "sha256": token_hash(token),
                        "scopes": sorted(set(scopes)),
                        "created_utc": datetime.now(timezone.utc).isoformat()})
        self._write(entries)
        return token

    def revoke(self, token_id: str) -> bool:
        entries = self.entries()
        kept = [e for e in entries if e["id"] != token_id]
        if len(kept) == len(entries):
            return False
        self._write(kept)
        return True


class StaticTokenVerifier:
    """The SDK's TokenVerifier over a TokenStore. The access token carries
    the hash, not the token, so the token itself stays out of server state."""

    def __init__(self, store: TokenStore):
        self.store = store

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        entry = self.store.verify(token)
        if entry is None:
            return None
        return AccessToken(token="sha256:" + entry["sha256"][:12], client_id=entry["id"],
                           scopes=effective_scopes(entry.get("scopes", [])))
