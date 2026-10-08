from test_product import tx, post_tx, upload, finalize


def test_search_exact_combined_filters_and_stable_pagination(client, household):
    path = household["path"]
    c1, c2 = [c["id"] for c in household["data"]["categories"][:2]]
    a1, a2 = [a["id"] for a in household["data"]["accounts"][:2]]
    for index, (amount, date, account) in enumerate([(10001, "2026-09-30", a1), (12345, "2026-10-01", a2), (20002, "2026-10-02", a2)]):
        response = post_tx(
            client,
            household,
            tx(
                household,
                amount=amount,
                date=date,
                account_id=account,
                description="Zakupy wspólne",
                allocations=[{"category_id": c1, "amount": amount - 1}, {"category_id": c2, "amount": 1}],
            ),
            key=f"search-{index}-key",
        )
        assert response.status_code == 201
    result = client.get(
        path
        + f"/transactions?date_from=2026-09-01&date_to=2026-10-31&category_id={c2}&account_id={a2}&min_amount=12345&max_amount=20002&search=Zakupy&kind=expense&sort=amount_asc&limit=1"
    ).json()
    assert len(result["items"]) == 1 and result["items"][0]["amount"] == 12345 and result["has_more"]
    assert len(result["items"][0]["allocations"]) == 2
    second = client.get(path + f"/transactions?category_id={c2}&account_id={a2}&sort=amount_asc&limit=1&offset=1").json()
    assert second["items"][0]["amount"] == 20002 and not second["has_more"]
    assert len(client.get(path + "/transactions?month=2026-10").json()["items"]) == 2
    assert client.get(path + "/transactions?sort=oldest").json()["items"][0]["amount"] == 10001
    assert client.get(path + "/transactions?sort=amount_desc").json()["items"][0]["amount"] == 20002


def test_search_receipt_products_and_literal_wildcards(client, household):
    receipt = upload(client, household).json()
    confirmed = client.post(household["path"] + "/receipts/" + receipt["id"] + "/finalize", json=finalize(household, receipt)).json()
    product = receipt["items"][0]["name"]
    result = client.get(household["path"] + "/transactions", params={"search": product}).json()
    assert [row["id"] for row in result["items"]] == [confirmed["id"]]
    assert post_tx(client, household, tx(household, description="Rabat 10%_literal"), key="literal-search-key").status_code == 201
    assert len(client.get(household["path"] + "/transactions", params={"search": "%_"}).json()["items"]) == 1
    assert not client.get(household["path"] + "/transactions", params={"search": "%_other"}).json()["items"]


def test_search_destination_account_and_invalid_filters(client, household):
    a1, a2 = [a["id"] for a in household["data"]["accounts"][:2]]
    assert (
        post_tx(client, household, tx(household, kind="transfer", allocations=[], destination_id=a2), key="search-transfer").status_code
        == 201
    )
    assert len(client.get(household["path"] + f"/transactions?account_id={a2}").json()["items"]) == 1
    for query in [
        "min_amount=101&max_amount=100",
        "date_from=2026-10-02&date_to=2026-10-01",
        "sort=unsafe",
        "min_amount=0.1",
        "date_from=1999-01-01",
        "kind=unknown",
        "limit=101",
        "offset=-1",
    ]:
        assert client.get(household["path"] + "/transactions?" + query).status_code == 422
    assert client.get(household["path"] + "/transactions?category_id=foreign").status_code == 404
    assert client.get(household["path"] + "/transactions?account_id=foreign").status_code == 404
    assert len(client.get(household["path"] + f"/transactions?account_id={a1}").json()["items"]) == 1
