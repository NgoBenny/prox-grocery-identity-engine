import pytest
from fastapi.testclient import TestClient

from prox_match.api import create_app
from prox_match.cli import main


@pytest.fixture(scope="module")
def client(engine):
    return TestClient(create_app(engine))


def test_health(client):
    body = client.get("/health").json()
    assert body["catalog_count"] >= 40 and body["listing_count"] >= 80
    assert body["retailer_count"] == 3
    assert ["C107", "C108"] in body["catalog_duplicate_clusters"]


def test_match_post(client):
    listing = {"listing_id": "A1", "retailer": "FreshTown", "raw_name": "Heritage Chicken Broth",
               "brand_raw": "Heritage", "size_raw": "32 fl oz",
               "retailer_category": "Meat", "price_cents": 299}
    body = client.post("/match", json=listing).json()
    assert body["canonical_id"] == "C104" and body["assigned_category"] == "PANTRY"


def test_match_with_simulated_upstream_timeout(client):
    listing = {"listing_id": "A2", "retailer": "FreshTown", "raw_name": "Farmhouse Chicken Breast",
               "brand_raw": "Farmhouse", "size_raw": "1 lb"}
    body = client.post("/match?upstream=timeout", json=listing).json()
    assert body["assigned_category"] == "MEAT" and "UPSTREAM_TIMEOUT" in body["reason_codes"]


def test_search_endpoint(client):
    body = client.get("/search", params={"q": "chicken breast", "retailer": "FreshTown"}).json()
    assert body["results"][0]["canonical_id"] == "C103"


@pytest.mark.parametrize("method,url,payload,status", [
    ("post", "/match", {"listing_id": "B", "retailer": "R", "raw_name": "Milk",
                        "price_cents": "abc"}, 422),
    ("post", "/match", {"listing_id": "B", "retailer": "R", "raw_name": ""}, 422),
    ("post", "/match", {"listing_id": "B", "retailer": "R", "raw_name": "Milk",
                        "price_cents": -5}, 422),
    ("post", "/match?upstream=confident", {"listing_id": "B", "retailer": "R",
                                           "raw_name": "Milk"}, 400),
    ("get", "/search?q=", None, 422),
    ("get", "/search?q=chicken&retailer=NoSuchMart", None, 400),
    ("get", "/search?q=chicken&limit=0", None, 422),
    ("get", "/match/NOPE", None, 404),
])
def test_bad_input_is_a_structured_4xx(client, method, url, payload, status):
    response = getattr(client, method)(url, json=payload) if payload else getattr(client, method)(url)
    assert response.status_code == status
    assert "detail" in response.json()


def test_cli_bad_input_exits_2(tmp_path, capsys):
    assert main(["match", "--listing-id", "NOPE"]) == 2
    assert main(["search", "-q", "chicken", "--retailer", "NoSuchMart"]) == 2
    other = tmp_path / "other.jsonl"
    other.write_text('{"listing_id": "Z1", "retailer": "R", "raw_name": "Milk"}\n',
                     encoding="utf-8")
    assert main(["demo", "--listings", str(other)]) == 2


def test_cli_match_file(tmp_path, capsys):
    f = tmp_path / "rows.jsonl"
    f.write_text('{"listing_id": "F1", "retailer": "R", "raw_name": "Baby Spinach",'
                 ' "size_raw": "5 oz"}\n', encoding="utf-8")
    assert main(["match", "--file", str(f)]) == 0
    assert '"canonical_id": "C110"' in capsys.readouterr().out
