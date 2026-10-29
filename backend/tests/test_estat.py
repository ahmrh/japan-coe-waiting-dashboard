from pathlib import Path

import pytest

from app.estat import (
    EXPECTED_FIELDS,
    SourceFormatError,
    _parse_integer,
    _parse_result_table,
    _period_from_name,
)

FIXTURE = Path(__file__).parent / "fixtures" / "estat_2026_08_live_fragment.html"
METADATA = {
    "100000": {
        "name": "総数",
        "hierarchy_type": "national_total",
        "parent_code": None,
        "seq_no": 10,
    },
    "101170": {
        "name": "東京出入国在留管理局管内",
        "hierarchy_type": "bureau_jurisdiction",
        "parent_code": None,
        "seq_no": 200,
    },
    "101180": {
        "name": "東京出入国在留管理局",
        "hierarchy_type": "office",
        "parent_code": "101170",
        "seq_no": 210,
    },
    "101210": {
        "name": "横浜支局",
        "hierarchy_type": "office",
        "parent_code": "101170",
        "seq_no": 240,
    },
}


def parse_fixture(html: str | None = None):
    source = html if html is not None else FIXTURE.read_text(encoding="utf-8")
    return _parse_result_table(
        source,
        "2026-08",
        METADATA,
        EXPECTED_FIELDS,
        "人",
    )


def test_live_shaped_source_rows_preserve_exact_fields_and_unit() -> None:
    observations, warnings = parse_fixture()
    national, tokyo, tokyo_office, yokohama = observations

    assert not warnings
    assert national.period == "2026-08"
    assert national.unit == "人"
    assert national.raw_values == {
        "受理_総数": 173583,
        "受理_旧受": 131402,
        "受理_新受": 42181,
        "既済_総数": 86718,
        "既済_交付": 77215,
        "既済_不交付": 8192,
        "既済_その他": 1311,
    }
    assert national.values["pending_calculated"] == 86865
    assert tokyo.values["pending_calculated"] == 52054
    assert tokyo.bureau.hierarchy_type == "bureau_jurisdiction"
    assert tokyo_office.bureau.parent_code == tokyo.bureau.code
    assert yokohama.bureau.parent_code == tokyo.bureau.code


def test_category_changes_are_reported_instead_of_silently_mapped() -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace("既済_その他", "既済_取消")
    with pytest.raises(SourceFormatError, match="category fields changed"):
        parse_fixture(html)


def test_partial_or_duplicate_bureau_rows_are_rejected() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    missing_start = html.index(
        '<tr>\n        <th class="js-dbview-rows" data-unique="101210">'
    )
    missing_end = html.index("</tr>", missing_start) + len("</tr>")
    with pytest.raises(SourceFormatError, match="Incomplete bureau rows"):
        parse_fixture(html[:missing_start] + html[missing_end:])

    duplicate_fragment = next(
        fragment
        for fragment in html.split("<tr>")
        if 'data-unique="101170"' in fragment
    ).split("</tr>", 1)[0]
    duplicate = html.replace(
        "</tbody>", f"<tr>{duplicate_fragment}</tr></tbody>"
    )
    with pytest.raises(SourceFormatError):
        parse_fixture(duplicate)


def test_count_parser_preserves_missing_distinct_from_zero() -> None:
    assert _parse_integer("***") is None
    assert _parse_integer("0") == 0
    with pytest.raises(SourceFormatError, match="Unexpected count"):
        _parse_integer("1.2")


def test_periods_are_discovered_from_official_month_labels() -> None:
    assert _period_from_name("2026年9月") == "2026-09"
    assert _period_from_name("2026年08月") == "2026-08"
    with pytest.raises(SourceFormatError, match="reporting period"):
        _period_from_name("2026年度")
