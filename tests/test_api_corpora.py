import uuid


def test_create_and_list_a_corpus(client):
    name = f"roman-empire-{uuid.uuid4()}"

    created = client.post("/corpora", json={"name": name, "description": "primary sources"})
    assert created.status_code == 201
    assert created.json()["name"] == name

    listed = client.get("/corpora").json()
    assert created.json()["id"] in [c["id"] for c in listed]


def test_duplicate_corpus_name_is_rejected(client):
    name = f"dup-{uuid.uuid4()}"
    assert client.post("/corpora", json={"name": name}).status_code == 201

    conflict = client.post("/corpora", json={"name": name})
    assert conflict.status_code == 409
