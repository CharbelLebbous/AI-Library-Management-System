from conftest import auth_header


def test_unauthorized_without_token(client):
    response = client.get("/api/books")
    assert response.status_code == 401


def test_member_cannot_create_or_delete_book(client):
    create_resp = client.post(
        "/api/books",
        headers=auth_header("member"),
        json={"title": "Domain-Driven Design", "author": "Evans", "metadata": {}},
    )
    assert create_resp.status_code == 403

    admin_create = client.post(
        "/api/books",
        headers=auth_header("admin", "admin@example.com"),
        json={"title": "Clean Architecture", "author": "Robert Martin", "metadata": {}},
    )
    book_id = admin_create.json()["id"]

    delete_resp = client.delete(f"/api/books/{book_id}", headers=auth_header("member"))
    assert delete_resp.status_code == 403


def test_current_user_endpoint_returns_role(client):
    response = client.get("/api/me", headers=auth_header("librarian", "lib@example.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "lib@example.com"
    assert body["role"] == "librarian"
