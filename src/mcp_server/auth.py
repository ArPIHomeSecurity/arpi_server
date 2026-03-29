"""
JWT-based token verifier for MCP server authentication.
"""

import logging
import os

from datetime import datetime as dt
from dateutil.tz import UTC
from jose import jwt
import jose

from fastmcp.server.auth import AccessToken, TokenVerifier
from utils.constants import ROLE_ADMIN, ROLE_USER, USER_TOKEN_EXPIRY


logger = logging.getLogger("server")


class JWTVerifier(TokenVerifier):
    """
    JWT-based token verifier for MCP server authentication.
    """

    def __init__(self, secret: str | None = None, algorithm: str = "HS256"):
        super().__init__()
        self._secret = secret or os.environ.get("MCP_SECRET")
        self._algorithm = algorithm
        if not self._secret:
            raise ValueError("MCP_SECRET is required for JWT verification")

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jose.exceptions.JWTError:
            logger.info("JWT verification failed")
            return None

        timestamp = int(claims.get("timestamp", 0))
        ttl = claims.get("ttl", USER_TOKEN_EXPIRY)
        if ttl > 0 and timestamp < int(dt.now(tz=UTC).timestamp()) - ttl:
            return None

        role = claims.get("role")
        scopes = _role_to_scopes(role)
        client_id = claims.get("id") or claims.get("name") or claims.get("sub") or "unknown"
        expires_at = timestamp + ttl if ttl > 0 else None
        return AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=scopes,
            expires_at=expires_at,
            claims=claims,
        )


def _role_to_scopes(role: str | None) -> list[str]:
    """
    Convert a user role to a list of scopes.
    """
    if role == ROLE_ADMIN:
        return [ROLE_ADMIN, ROLE_USER]
    if role == ROLE_USER:
        return [ROLE_USER]

    return []
