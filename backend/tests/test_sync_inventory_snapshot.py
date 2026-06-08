import os
import sys
from pathlib import Path

os.environ["DEBUG"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import sync_inventory_snapshot as inv_sync


def test_aggregate_inventory_rows_preserves_sku_inventory_and_reserved_totals():
    rows = [
        {
            "Item SkuCode": "an17374",
            "Category Name": "BOYS SUMMER JOGGER",
            "Color": "BLACK",
            "Size": "6-12 MONTHS",
            "Brand": "Anthrilo",
            "Inventory": "12",
            "Open Sale": "5",
            "Inventory Blocked": "7",
            "Cost Price": "220.00",
            "MRP": "1199.00",
            "Enabled": "true",
        },
        {
            "Item SkuCode": "AN17374",
            "Inventory": "3",
            "Open Sale": "1",
            "Inventory Blocked": "2",
        },
    ]

    result = inv_sync._aggregate_inventory_rows(rows, "anthrilo")

    assert result["fetched_rows"] == 2
    assert result["unique_rows"] == 1
    assert result["duplicate_rows"] == 1
    assert result["missing_sku_rows"] == 0
    assert result["total_real_inventory"] == 15
    assert result["total_virtual_inventory"] == 15
    assert result["rows"][0]["sku"] == "AN17374"


def test_validate_inventory_snapshot_rejects_missing_sku_rows():
    preview = {
        "rows_fetched": 28724,
        "unique_rows": 28497,
        "missing_sku_rows": 227,
    }

    error = inv_sync._validate_inventory_snapshot_for_sync(preview, existing_total_rows=28724)

    assert error is not None
    assert "without SKU" in error


def test_validate_inventory_snapshot_rejects_suspicious_row_count_drop():
    preview = {
        "rows_fetched": 25000,
        "unique_rows": 25000,
        "missing_sku_rows": 0,
    }

    error = inv_sync._validate_inventory_snapshot_for_sync(preview, existing_total_rows=28724)

    assert error is not None
    assert "row count dropped" in error


def test_validate_inventory_snapshot_accepts_full_snapshot():
    preview = {
        "rows_fetched": 28724,
        "unique_rows": 28724,
        "missing_sku_rows": 0,
    }

    error = inv_sync._validate_inventory_snapshot_for_sync(preview, existing_total_rows=28744)

    assert error is None
