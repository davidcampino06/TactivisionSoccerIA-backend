"""Logs: one format, security events, and no secret ever written."""

import io
import logging

import pytest
from conftest import DEFAULT_PASSWORD, register

from log_setup import REDACTED, RedactSecretsFilter, mask_email, redact


@pytest.mark.parametrize(("text", "secret"), [
    ("connecting to postgresql://neondb_owner:npg_abc123XYZ@ep-x.neon.tech/neondb", "npg_abc123XYZ"),
    ("postgresql+psycopg2://user:s3cr3t@localhost/db", "s3cr3t"),
    ("headers={'Authorization': 'Bearer abc.def-ghi'}", "abc.def-ghi"),
    ("token eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1MSJ9.c2lnbmF0dXJl expired", "eyJzdWIiOiJ1MSJ9"),
    ("body password=rsa:QUJDREVGR0hJSktMTU5PUFFSU1RVVldY", "QUJDREVGR0hJSktMTU5P"),
    ("brevo key xkeysib-0123456789abcdef-AbCdEf rejected", "0123456789abcdef"),
    ("hash $2b$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ01234 stored", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    ("login password='Tactica#2026' api_key=abc123 secret: shh", "Tactica#2026"),
])
def test_secrets_are_redacted(text, secret):
    cleaned = redact(text)
    assert secret not in cleaned
    assert REDACTED in cleaned


def test_normal_text_is_left_alone():
    text = "Analysis 1f2e failed in the AI Service: timeout after 900 s (team=abc)"
    assert redact(text) == text


def test_mask_email():
    assert mask_email("mateo@club.com") == "m***@club.com"
    assert mask_email("") == "?"
    assert mask_email("not-an-email") == "?"


def test_the_filter_cleans_arguments_and_exceptions():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactSecretsFilter())
    logger = logging.getLogger("tactivision.test-redaction")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning("Database %s unreachable", "postgresql://u:hunter2@db/x")
        try:
            raise RuntimeError("bad Authorization: Bearer tok.en.value")
        except RuntimeError:
            logger.exception("Request failed")
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert "hunter2" not in output and "tok.en.value" not in output
    assert "Database postgresql://u:[REDACTED]@db/x unreachable" in output
    assert "RuntimeError" in output  # the error is still there, only the secret is gone


def test_security_events_name_the_user_but_never_the_password(client, caplog):
    caplog.set_level(logging.INFO, logger="tactivision.security")
    created = register(client, "mateo@club.com", "COACH")
    client.post("/api/auth/login", json={"email": "mateo@club.com", "password": "Otra#Clave1"})
    messages = [record.getMessage() for record in caplog.records if record.name == "tactivision.security"]
    assert any(f"Account created user={created['user']['id']}" in message for message in messages)
    assert any("Login failed for m***@club.com (4 attempts left)" in message for message in messages)
    joined = "\n".join(messages)
    assert "mateo@club.com" not in joined
    assert DEFAULT_PASSWORD not in joined and "Otra#Clave1" not in joined
