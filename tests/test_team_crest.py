"""Team crest (re-encoded PNG, team-only) and kit colour, migration 0015."""

import io

from PIL import Image

from tests.conftest import register


def image_bytes(fmt="PNG", size=(600, 400), color=(220, 180, 60, 255)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" else "RGB", size, color if fmt == "PNG" else color[:3]).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, team, headers, data: bytes, name="crest.png", content_type="image/png"):
    return client.put(f"/api/teams/{team['id']}/crest", headers=headers, files={"crest": (name, data, content_type)})


def test_coach_uploads_a_crest_that_is_stored_as_a_clean_256_px_png(client, coach, team):
    assert team["crest_updated_at"] is None
    response = upload(client, team, coach["headers"], image_bytes("JPEG"), "escudo.jpg", "image/jpeg")
    assert response.status_code == 200, response.text
    assert response.json()["crest_updated_at"] is not None

    crest = client.get(f"/api/teams/{team['id']}/crest", headers=coach["headers"])
    assert crest.status_code == 200
    assert crest.headers["content-type"] == "image/png"
    assert crest.headers["x-content-type-options"] == "nosniff"
    picture = Image.open(io.BytesIO(crest.content))
    assert picture.format == "PNG" and picture.size == (256, 256)   # wide image fitted, margins transparent
    assert picture.getpixel((0, 0))[3] == 0 and picture.getpixel((128, 128))[3] == 255


def test_the_crest_is_only_for_people_of_the_team(client, coach, team, analyst):
    upload(client, team, coach["headers"], image_bytes())
    assert client.get(f"/api/teams/{team['id']}/crest", headers=analyst["headers"]).status_code == 200
    assert upload(client, team, analyst["headers"], image_bytes()).status_code == 403   # only the coach changes it
    stranger = register(client, "otro@test.com", "COACH")
    assert client.get(f"/api/teams/{team['id']}/crest", headers=stranger["headers"]).status_code in (403, 404)
    assert upload(client, team, stranger["headers"], image_bytes()).status_code in (403, 404)


def test_files_that_are_not_safe_images_are_rejected(client, coach, team):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for data, name, kind in ((svg, "escudo.svg", "image/svg+xml"), (b"not an image", "escudo.png", "image/png"),
                             (image_bytes("GIF"), "escudo.gif", "image/gif"), (b"", "vacio.png", "image/png")):
        response = upload(client, team, coach["headers"], data, name, kind)
        assert response.status_code == 400, name
        assert response.json()["code"] in ("CREST_FORMAT", "CREST_EMPTY")
    too_big = b"\x89PNG" + b"0" * (2 * 1024 * 1024)
    assert upload(client, team, coach["headers"], too_big).json()["code"] == "CREST_TOO_LARGE"
    assert client.get(f"/api/teams/{team['id']}/crest", headers=coach["headers"]).status_code == 404


def test_crest_can_be_replaced_and_removed(client, coach, team):
    upload(client, team, coach["headers"], image_bytes())
    first = client.get(f"/api/teams/{team['id']}/crest", headers=coach["headers"]).content
    upload(client, team, coach["headers"], image_bytes(color=(30, 60, 200, 255)))
    assert client.get(f"/api/teams/{team['id']}/crest", headers=coach["headers"]).content != first
    removed = client.delete(f"/api/teams/{team['id']}/crest", headers=coach["headers"])
    assert removed.status_code == 200 and removed.json()["crest_updated_at"] is None
    assert client.get(f"/api/teams/{team['id']}/crest", headers=coach["headers"]).status_code == 404


def test_kit_colour_is_saved_lowercase_and_validated(client, coach, team):
    saved = client.put(f"/api/teams/{team['id']}", headers=coach["headers"], json={"kit_color": "#E3B23C"})
    assert saved.status_code == 200 and saved.json()["kit_color"] == "#e3b23c"
    assert client.put(f"/api/teams/{team['id']}", headers=coach["headers"], json={"kit_color": "amarillo"}).status_code == 422
    cleared = client.put(f"/api/teams/{team['id']}", headers=coach["headers"], json={"kit_color": None})
    assert cleared.json()["kit_color"] is None
