"""Build a clean size-wise + style-wise SKU report from raw data.

Usage:
  python scripts/build_sku_style_report.py --input raw_data.xlsx --output report.xlsx
  python scripts/build_sku_style_report.py --input raw_data.csv --output report.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Iterable

import pandas as pd


OUTPUT_COLUMNS = [
    "Item SKU",
    "Name",
    "Type",
    "Tags",
    "Size",
    "MRP",
    "COST",
    "Sale (Size-wise)",
    "Return (Size-wise)",
    "Cancelled (Size-wise)",
    "Net Sale (Size-wise)",
    "Net Sale in Amount (Size-wise)",
    "Sale (Style-wise)",
    "Return (Style-wise)",
    "Cancelled (Style-wise)",
    "Net Sale (Style-wise)",
    "Net Sale in Amount (Style-wise)",
    "Good Inventory (Size-wise)",
    "Good Inventory (Style-wise)",
    "Virtual Inventory (Size-wise)",
    "Virtual Inventory (Style-wise)",
]


REQUIRED_ALIASES = {
    "sku": ["Variant SKU", "Item SKU", "SKU"],
    "title": ["Title", "Name"],
    "type": ["Type"],
    "tags": ["Tags"],
    "size": ["Option1 Value (Size)", "Option1 Value", "Size"],
    "cost": ["Cost per item", "COST", "Cost", "MRP"],
    "sale_size": ["Sale size wise", "Sale (Size-wise)"],
    "good_inventory_size": [
        "GOOD INVENTORY (size-wise)",
        "GOOD INVENTORY",
        "Good Inventory (Size-wise)",
    ],
}


OPTIONAL_ALIASES = {
    "return_size": ["Return (Size-wise)", "Return size wise", "Return"],
    "cancelled_size": ["Cancelled (Size-wise)", "Cancelled size wise", "Cancelled"],
    "virtual_inventory_size": [
        "Virtual Inventory (Size-wise)",
        "VIRTUAL INVENTORY (size-wise)",
        "Virtual Inventory",
    ],
}


def _canon(name: str) -> str:
    """Normalize a column name for alias matching."""
    lowered = str(name).strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _column_lookup(columns: Iterable[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in columns:
        key = _canon(column)
        if key and key not in lookup:
            lookup[key] = column
    return lookup


def _resolve_column(
    lookup: dict[str, str],
    aliases: list[str],
    *,
    required: bool,
    logical_name: str,
) -> str | None:
    for alias in aliases:
        key = _canon(alias)
        if key in lookup:
            return lookup[key]
    if required:
        raise ValueError(f"Missing required input column for '{logical_name}': expected one of {aliases}")
    return None


def _to_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.fillna(default)


def _load_input(input_path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(input_path)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(input_path, sheet_name=sheet_name)
    raise ValueError("Unsupported file format. Use CSV or Excel (.xlsx/.xlsm/.xls)")


def _ensure_output_path(input_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path
    return input_path.with_name(f"{input_path.stem}_clean_report.xlsx")


def generate_report_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    lookup = _column_lookup(raw_df.columns)

    resolved_required = {
        logical: _resolve_column(lookup, aliases, required=True, logical_name=logical)
        for logical, aliases in REQUIRED_ALIASES.items()
    }
    resolved_optional = {
        logical: _resolve_column(lookup, aliases, required=False, logical_name=logical)
        for logical, aliases in OPTIONAL_ALIASES.items()
    }

    df = pd.DataFrame()
    df["Item SKU"] = raw_df[resolved_required["sku"]].astype(str).str.strip()
    df["Name"] = raw_df[resolved_required["title"]].astype(str).str.strip()
    df["Type"] = raw_df[resolved_required["type"]].astype(str).str.strip()
    df["Tags"] = raw_df[resolved_required["tags"]].astype(str).str.strip()
    df["Size"] = raw_df[resolved_required["size"]].astype(str).str.strip()

    cost_series = _to_numeric(raw_df[resolved_required["cost"]])
    df["MRP"] = cost_series
    df["COST"] = cost_series

    df["Sale (Size-wise)"] = _to_numeric(raw_df[resolved_required["sale_size"]])

    if resolved_optional["return_size"] is None:
        df["Return (Size-wise)"] = 0.0
    else:
        df["Return (Size-wise)"] = _to_numeric(raw_df[resolved_optional["return_size"]])

    if resolved_optional["cancelled_size"] is None:
        df["Cancelled (Size-wise)"] = 0.0
    else:
        df["Cancelled (Size-wise)"] = _to_numeric(raw_df[resolved_optional["cancelled_size"]])

    df["Net Sale (Size-wise)"] = (
        df["Sale (Size-wise)"] - df["Return (Size-wise)"] - df["Cancelled (Size-wise)"]
    )
    df["Net Sale in Amount (Size-wise)"] = df["Net Sale (Size-wise)"] * df["MRP"]

    df["Good Inventory (Size-wise)"] = _to_numeric(raw_df[resolved_required["good_inventory_size"]])

    if resolved_optional["virtual_inventory_size"] is None:
        df["Virtual Inventory (Size-wise)"] = 0.0
    else:
        df["Virtual Inventory (Size-wise)"] = _to_numeric(raw_df[resolved_optional["virtual_inventory_size"]])

    # Remove duplicate SKU+Size records as requested.
    df = df.drop_duplicates(subset=["Item SKU", "Size"], keep="first").reset_index(drop=True)

    grouped = df.groupby("Name", dropna=False)
    df["Sale (Style-wise)"] = grouped["Sale (Size-wise)"].transform("sum")
    df["Return (Style-wise)"] = grouped["Return (Size-wise)"].transform("sum")
    df["Cancelled (Style-wise)"] = grouped["Cancelled (Size-wise)"].transform("sum")
    df["Net Sale (Style-wise)"] = grouped["Net Sale (Size-wise)"].transform("sum")
    df["Net Sale in Amount (Style-wise)"] = grouped["Net Sale in Amount (Size-wise)"].transform("sum")
    df["Good Inventory (Style-wise)"] = grouped["Good Inventory (Size-wise)"].transform("sum")
    df["Virtual Inventory (Style-wise)"] = grouped["Virtual Inventory (Size-wise)"].transform("sum")

    return df[OUTPUT_COLUMNS].copy()


def export_report(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix == ".csv":
        df.to_csv(output_path, index=False)
        return
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df.to_excel(output_path, index=False)
        return
    raise ValueError("Unsupported output format. Use .csv or .xlsx/.xlsm/.xls")


def build_sku_style_report(
    input_path: str,
    output_path: str | None = None,
    *,
    sheet_name: str | int = 0,
) -> Path:
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    out_file = _ensure_output_path(input_file, Path(output_path) if output_path else None)
    raw_df = _load_input(input_file, sheet_name=sheet_name)
    report_df = generate_report_dataframe(raw_df)
    export_report(report_df, out_file)
    return out_file


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate size-wise and style-wise SKU report.")
    parser.add_argument("--input", required=True, help="Input CSV/XLSX file path")
    parser.add_argument("--output", required=False, help="Output CSV/XLSX file path")
    parser.add_argument(
        "--sheet",
        default=0,
        help="Excel sheet name or index for input workbooks (default: 0)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    sheet: str | int
    if isinstance(args.sheet, str) and args.sheet.isdigit():
        sheet = int(args.sheet)
    else:
        sheet = args.sheet

    output = build_sku_style_report(args.input, args.output, sheet_name=sheet)
    print(f"Report generated: {output}")


if __name__ == "__main__":
    main()
