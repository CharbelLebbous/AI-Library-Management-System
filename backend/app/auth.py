from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Role, User

bearer_scheme = HTTPBearer(auto_error=False)
ROLE_CLAIM = "https://library-ai.example.com/roles"


@dataclass
class AuthUser:
    id: str
    email: str
    role: Role


def _parse_dev_token(token: str) -> AuthUser:
    try:
        role_part, email = token.split(":", 1)
        role = Role(role_part.strip().lower())
        user_id = email.strip().lower()
        if not user_id:
            raise ValueError("Email is required")
        return AuthUser(id=user_id, email=user_id, role=role)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid development token format") from exc


@lru_cache(maxsize=1)
def _auth0_jwks() -> dict:
    if not settings.auth0_domain:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH0_DOMAIN is required when JWT verification is enabled.",
        )

    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    try:
        with urlopen(jwks_url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Auth0 signing keys.",
        ) from exc


def _extract_role_from_claims(claims: dict) -> Role:
    roles = claims.get(ROLE_CLAIM) or claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]

    for candidate in roles:
        normalized = str(candidate).lower()
        if normalized in Role._value2member_map_:
            return Role(normalized)
    return Role.member


def _decode_jwt(token: str) -> AuthUser:
    try:
        if settings.auth_disable_jwt_verification:
            claims = jwt.get_unverified_claims(token)
        else:
            if not settings.auth0_domain or not settings.auth0_audience:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="AUTH0_DOMAIN and AUTH0_AUDIENCE are required for JWT verification.",
                )

            unverified_header = jwt.get_unverified_header(token)
            token_kid = unverified_header.get("kid")
            if not token_kid:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing key identifier.")

            jwks = _auth0_jwks()
            signing_key = next((key for key in jwks.get("keys", []) if key.get("kid") == token_kid), None)
            if not signing_key:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signing key.")

            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=settings.auth0_audience,
                issuer=f"https://{settings.auth0_domain}/",
            )

        user_id = claims.get("sub")
        email = claims.get("email") or claims.get("upn") or user_id
        role = _extract_role_from_claims(claims)

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub claim")

        return AuthUser(id=str(user_id), email=str(email), role=role)
    except HTTPException:
        raise
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    token = credentials.credentials
    parsed = _parse_dev_token(token) if settings.auth_disable_jwt_verification else _decode_jwt(token)

    user = db.scalar(select(User).where(User.id == parsed.id))
    if not user:
        user = User(id=parsed.id, email=parsed.email, role=parsed.role)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = parsed.email
        user.role = parsed.role
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


def require_roles(*allowed_roles: Role):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency
