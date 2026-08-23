import pytest
import io

def test_parse_csv_endpoint(client, auth_headers, monkeypatch):
    async def mock_analyze(headers, sample_row):
        return {"name_col": "item_title_v2", "desc_col": "long_desc_raw"}
        
    monkeypatch.setattr("server.ai_engine.analyze_csv_mapping", mock_analyze)
    
    csv_data = "item_title_v2,long_desc_raw,price,sku\nEspresso Machine,Dual boiler professional machine,599.00,SKU-100\nCoffee Grinder,Conical burr grinder,199.00,SKU-101\n"
    
    response = client.post(
        "/api/catalog/parse-csv",
        files={"file": ("inventory.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "Espresso Machine"
    assert data["items"][0]["desc"] == "Dual boiler professional machine"
    assert data["mapping_used"]["name_col"] == "item_title_v2"
