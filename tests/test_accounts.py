"""Тесты аккаунтов, профиля, избранного и фактов."""
from __future__ import annotations

import pytest

from app import db

from conftest import insert_lecture


def register(client, email="student@example.com", name="Анна", password="vector-pass-1"):
    return client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": password},
    )


@pytest.fixture(autouse=True)
def _fresh_cookies(client):
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture
def lecture() -> dict:
    return insert_lecture("api-lecture", "API-лекция")


class TestFacts:
    def test_facts_are_public_and_structured(self, client):
        response = client.get("/api/facts?limit=5")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 5
        assert len(payload["items"]) == 5
        for item in payload["items"]:
            assert item["id"] and item["category"] and item["text"]
            assert len(item["text"]) > 40

    def test_facts_limit_and_exclude(self, client):
        first = client.get("/api/facts?limit=1").json()["items"][0]
        second = client.get(f"/api/facts?limit=1&exclude={first['id']}").json()["items"][0]
        assert second["id"] != first["id"]


class TestAccounts:
    def test_register_creates_session(self, client):
        response = register(client)
        assert response.status_code == 201
        user = response.json()["user"]
        assert user["email"] == "student@example.com"
        assert user["name"] == "Анна"
        assert user["avatar"] == "lime"
        assert "password_hash" not in user
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["id"] == user["id"]
        assert client.cookies.get("vector_session")

    def test_register_duplicate_email(self, client):
        assert register(client).status_code == 201
        response = register(client, email="STUDENT@example.com")
        assert response.status_code == 409
        assert "уже существует" in response.json()["detail"]

    def test_register_validation(self, client):
        assert register(client, email="not-an-email").status_code == 422
        assert register(client, password="short").status_code == 422
        assert register(client, name="   ").status_code == 201

    def test_login_logout_flow(self, client):
        register(client, password="correct-pass")
        client.cookies.clear()
        assert client.get("/api/auth/me").status_code == 401
        bad = client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "wrong-pass"},
        )
        assert bad.status_code == 401
        good = client.post(
            "/api/auth/login",
            json={"email": "STUDENT@example.com", "password": "correct-pass"},
        )
        assert good.status_code == 200
        assert client.get("/api/auth/me").status_code == 200
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/auth/me").status_code == 401

    def test_profile_requires_auth(self, client):
        assert client.get("/api/profile").status_code == 401
        assert client.get("/api/favorites").status_code == 401
        assert client.post("/api/favorites/nope").status_code == 401

    def test_profile_update_and_avatar_validation(self, client):
        register(client)
        response = client.patch(
            "/api/auth/profile",
            json={"name": "  Анна   Петрова ", "bio": "Изучаю математику", "avatar": "violet"},
        )
        assert response.status_code == 200
        user = response.json()["user"]
        assert user["name"] == "Анна Петрова"
        assert user["bio"] == "Изучаю математику"
        assert user["avatar"] == "violet"
        assert client.patch("/api/auth/profile", json={"avatar": "rainbow"}).status_code == 422

    def test_password_change(self, client):
        register(client, password="old-password")
        wrong = client.post(
            "/api/auth/password",
            json={"current_password": "nope", "new_password": "new-password"},
        )
        assert wrong.status_code == 401
        changed = client.post(
            "/api/auth/password",
            json={"current_password": "old-password", "new_password": "new-password"},
        )
        assert changed.status_code == 200
        client.post("/api/auth/logout")
        assert client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "old-password"},
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "new-password"},
        ).status_code == 200

    def test_favorites_toggle_and_profile(self, client, lecture):
        register(client)
        assert client.get("/api/profile").json()["stats"]["favorites"] == 0
        toggled = client.post("/api/favorites/api-lecture")
        assert toggled.status_code == 200
        assert toggled.json()["favorited"] is True
        detail = client.get("/api/lectures/api-lecture").json()
        assert detail["is_favorite"] is True
        profile = client.get("/api/profile").json()
        assert profile["stats"]["favorites"] == 1
        assert profile["favorites"][0]["id"] == "api-lecture"
        assert profile["favorites"][0]["segments_count"] == 3
        listed = client.get("/api/favorites").json()
        assert listed["count"] == 1
        assert listed["items"][0]["is_favorite"] is True
        assert client.post("/api/favorites/api-lecture").json()["favorited"] is False
        assert client.get("/api/profile").json()["stats"]["favorites"] == 0

    def test_favorite_requires_existing_lecture(self, client):
        register(client)
        assert client.post("/api/favorites/missing").status_code == 404

    def test_owned_lectures_in_profile(self, client, lecture):
        user = register(client).json()["user"]
        with db.db() as conn:
            conn.execute(
                "UPDATE lectures SET owner_id=?, views=7 WHERE id=?",
                (user["id"], "api-lecture"),
            )
        profile = client.get("/api/profile").json()
        assert profile["stats"]["uploads"] == 1
        assert profile["stats"]["views"] == 7
        assert profile["lectures"][0]["id"] == "api-lecture"
        assert profile["lectures"][0]["is_favorite"] is False

    def test_favorite_removed_with_lecture(self, client, lecture):
        register(client)
        client.post("/api/favorites/api-lecture")
        assert client.delete("/api/lectures/api-lecture").status_code == 200
        assert client.get("/api/favorites").json()["count"] == 0
