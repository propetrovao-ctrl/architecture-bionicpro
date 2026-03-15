"""API отчётов: отдаёт витрину по user из JWT."""
import os
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="Reports API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
security = HTTPBearer(auto_error=False)

KEYCLOAK_ISSUER = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8080/realms/reports-realm")
KEYCLOAK_JWKS_URL = os.environ.get("KEYCLOAK_JWKS_URL", "http://keycloak:8080/realms/reports-realm/protocol/openid-connect/certs")
OLAP_DSN = os.environ.get(
    "OLAP_DSN",
    "postgresql://olap_user:olap_password@olap_db:5432/olap_db",
)
jwks_client = PyJWKClient(KEYCLOAK_JWKS_URL)


class ReportRow(BaseModel):
    user_id: str
    period_from: str
    period_to: str
    full_name: Optional[str]
    email: Optional[str]
    total_usage_mins: int
    total_events: int
    updated_at: str


class ReportResponse(BaseModel):
    user_id: str
    reports: list[ReportRow]
    message: Optional[str] = None


def get_olap_conn():
    return psycopg2.connect(OLAP_DSN, cursor_factory=RealDictCursor)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Проверяет Bearer и отдаёт payload."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            issuer=KEYCLOAK_ISSUER,
        )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_username(payload: dict) -> str:
    return payload.get("preferred_username") or payload.get("sub") or ""


@app.get("/reports", response_model=ReportResponse)
def get_reports(payload: dict = Depends(verify_token)):
    """Отчёт по текущему user_id из витрины. 404 если данных ещё нет."""
    username = get_username(payload)
    if not username:
        raise HTTPException(status_code=403, detail="User identity not found")

    conn = get_olap_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, period_from::text, period_to::text, full_name, email,
                       total_usage_mins, total_events, updated_at::text
                FROM report_mart
                WHERE user_id = %s
                ORDER BY period_to DESC
                LIMIT 12
                """,
                (username,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No report for this period yet.")

    reports = [
        ReportRow(
            user_id=r["user_id"],
            period_from=str(r["period_from"]),
            period_to=str(r["period_to"]),
            full_name=r["full_name"],
            email=r["email"],
            total_usage_mins=r["total_usage_mins"] or 0,
            total_events=r["total_events"] or 0,
            updated_at=str(r["updated_at"]),
        )
        for r in rows
    ]
    return ReportResponse(user_id=username, reports=reports)


@app.get("/health")
def health():
    return {"status": "ok"}
