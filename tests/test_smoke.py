"""Smoke tests for the Flask UI and health endpoints."""

from __future__ import annotations

import pytest

from app import EMBEDDED_UI_CSS, UI_ASSET_VERSION, app


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_health_json(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_build_info(client):
    res = client.get("/api/build-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["app"] == "thumbnail-studio"
    assert data["ui_version"] == UI_ASSET_VERSION
    assert data["embedded_css_chars"] == len(EMBEDDED_UI_CSS)
    assert data.get("has_route_studio") is True
    assert data.get("has_route_health") is True


def test_home_embedded_pro_ui(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Thumbnail Studio Pro" in html
    assert 'id="ts-embedded-ui"' in html
    assert "data-ui-mode" in html and "embedded-css" in html
    assert ":root" in html
    assert ".app-shell--guest" in html or ".auth-page" in html or ".auth-brand" in html


def test_studio_public_no_login_required(client):
    res = client.get("/studio")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Create your thumbnail" in html
    assert 'id="tsg-canvas"' in html
    assert 'id="tsg-embedded-css"' in html
    assert 'id="tsg-embedded-js"' in html
    assert "initThumbnailStudio" in html
    assert 'src="/static/js/thumbnail-studio.js"' not in html


def test_studio_generator_alias_redirect(client):
    res = client.get("/generator", follow_redirects=False)
    assert res.status_code == 302
    assert "/studio" in (res.headers.get("Location") or "")


def test_studio_renders_when_logged_in(client):
    with client.session_transaction() as sess:
        sess["user_email"] = "demo@example.com"
    res = client.get("/studio")
    assert res.status_code == 200
    assert b"Create your thumbnail" in res.data
