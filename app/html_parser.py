"""Generic table parsing; portal-specific mapping requires an observed HTML response."""
from datetime import datetime
from math import isfinite

from bs4 import BeautifulSoup

from app.models import clean


def parse_html_table(
    html: str,
    *,
    table_index: int = 0,
    numeric_columns: tuple[str, ...] = (),
    datetime_columns: dict[str, str] | None = None,
) -> list[dict]:
    """Parse one table with an explicit header row into JSON-compatible records.

    Column conversions are explicit so meter IDs and serials retain leading zeros.
    Date formats must be supplied from source evidence; no locale is guessed.
    Ambiguous headers, merged/nested tables, and ragged rows fail rather than
    silently assigning values to the wrong columns.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    tables = soup.find_all("table")
    if table_index < 0 or table_index >= len(tables):
        raise ValueError("Requested HTML table was not found")
    table = tables[table_index]
    if table.find("table"):
        raise ValueError("Nested HTML tables require an explicit source mapping")
    rows = table.find_all("tr")
    if not rows:
        raise ValueError("HTML table has no header row")
    if any(cell.get("rowspan", "1") != "1" or cell.get("colspan", "1") != "1"
           for cell in table.find_all(["th", "td"])):
        raise ValueError("Merged HTML cells require an explicit source mapping")
    header_cells = rows[0].find_all("th", recursive=False)
    if not header_cells or len(header_cells) != len(rows[0].find_all(["th", "td"], recursive=False)):
        raise ValueError("HTML table needs an explicit header row")
    headers = [clean(cell.get_text(" ", strip=True)) for cell in header_cells]
    if None in headers or len(set(headers)) != len(headers):
        raise ValueError("HTML table headers must be nonempty and unique")
    datetime_columns = datetime_columns or {}
    requested = set(numeric_columns) | set(datetime_columns)
    if not requested.issubset(headers) or set(numeric_columns) & set(datetime_columns):
        raise ValueError("Invalid HTML column conversion configuration")
    records = []
    for row in rows[1:]:
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        values = [clean(cell.get_text(" ", strip=True)) for cell in cells]
        if values == headers and all(cell.name == "th" for cell in cells):
            continue  # Repeated table header, not a data record.
        if len(values) != len(headers):
            raise ValueError("HTML table row does not match its headers")
        record = dict(zip(headers, values))
        for column in numeric_columns:
            if record[column] is not None:
                number = float(record[column])
                if not isfinite(number):
                    raise ValueError("HTML numeric value must be finite")
                record[column] = number
        for column, date_format in datetime_columns.items():
            if record[column] is not None:
                record[column] = datetime.strptime(record[column], date_format).isoformat()
        records.append(record)
    return records
