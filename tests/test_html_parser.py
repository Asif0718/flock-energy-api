"""Synthetic generic HTML cases, not representations claimed to come from Urja."""
import pytest

from app.html_parser import parse_html_table


def test_html_normalization_and_explicit_types():
    html = """<table><tr><th>Meter ID</th><th>kwh</th><th>timestamp</th><th>note</th></tr>
    <tr><td><b>00123</b></td><td> 124.50 </td><td>24/06/2026 00:00</td>
    <td> A&nbsp; <span> B </span><script>secret()</script></td></tr>
    <tr><td>00456</td><td>N/A</td><td>-</td><td> </td></tr></table>"""
    rows = parse_html_table(html, numeric_columns=("kwh",),
                            datetime_columns={"timestamp": "%d/%m/%Y %H:%M"})
    assert rows == [
        {"Meter ID": "00123", "kwh": 124.5, "timestamp": "2026-06-24T00:00:00", "note": "A B"},
        {"Meter ID": "00456", "kwh": None, "timestamp": None, "note": None},
    ]


def test_multiple_tables_repeated_headers_and_empty_results():
    html = "<table><tr><th>other</th></tr></table><table><tr><th>id</th></tr><tr><th>id</th></tr><tr><td>01</td></tr></table>"
    assert parse_html_table(html) == []
    assert parse_html_table(html, table_index=1) == [{"id": "01"}]


@pytest.mark.parametrize("html", [
    "<html><form>Login</form></html>",
    "<table></table>",
    "<table><tr><td>no headers</td></tr></table>",
    "<table><tr><th>x</th><th>x</th></tr></table>",
    "<table><tr><th> </th></tr></table>",
    "<table><tr><th>x</th><th>y</th></tr><tr><td>1</td></tr></table>",
    '<table><tr><th colspan="2">x</th></tr></table>',
    "<table><tr><th>x</th></tr><tr><td><table></table></td></tr></table>",
])
def test_ambiguous_or_non_table_html_rejected(html):
    with pytest.raises(ValueError):
        parse_html_table(html)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "not a number"])
def test_invalid_numbers_rejected(value):
    with pytest.raises(ValueError):
        parse_html_table(f"<table><tr><th>kwh</th></tr><tr><td>{value}</td></tr></table>", numeric_columns=("kwh",))


def test_invalid_date_rejected():
    with pytest.raises(ValueError):
        parse_html_table("<table><tr><th>date</th></tr><tr><td>31/02/2026</td></tr></table>",
                         datetime_columns={"date": "%d/%m/%Y"})
