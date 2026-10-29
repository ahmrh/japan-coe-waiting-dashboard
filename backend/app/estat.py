from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from .config import ESTAT_TABLE_ID, ESTAT_URL, request_timeout_seconds
from .statistics import WorkloadCounts, calculate_workload, validate_nonnegative_counts


PARSER_VERSION = "1.0.0"
EXPECTED_FIELDS = {
    "受理_総数": "accepted_total",
    "受理_旧受": "old_receipts",
    "受理_新受": "new_receipts",
    "既済_総数": "completed_total",
    "既済_交付": "issued",
    "既済_不交付": "not_issued",
    "既済_その他": "completed_other",
    "未済": "pending_official",
}
EXPECTED_FIELD_NAMES = frozenset(EXPECTED_FIELDS)
PERIOD_PATTERN = re.compile(r"(?P<year>20\d{2})年\s*(?P<month>0?[1-9]|1[0-2])月")
PUBLICATION_PATTERN = re.compile(
    r"公開年月日時分.{0,180}?(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})",
    re.DOTALL,
)


class SourceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Bureau:
    code: str
    name: str
    hierarchy_type: str
    parent_code: str | None
    sequence_number: int


@dataclass(frozen=True)
class Observation:
    period: str
    bureau: Bureau
    values: dict[str, int | None]
    raw_values: dict[str, int | None]
    unit: str


@dataclass(frozen=True)
class Dataset:
    observations: tuple[Observation, ...]
    publication_date: str | None
    latest_period: str
    content_hash: str
    raw_response: bytes
    warnings: tuple[str, ...]
    source_title: str


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_target_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.cell_tag = ""
        self.cell_attributes: dict[str, str] = {}
        self.cell_text: list[str] = []
        self.current_row: list[tuple[str, dict[str, str], str]] = []
        self.rows: list[list[tuple[str, dict[str, str], str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "table":
            classes = attributes.get("class", "").split()
            if "js-dbview-display-table-view" in classes:
                self.in_target_table = True
                self.table_depth = 1
            elif self.in_target_table:
                self.table_depth += 1
        elif self.in_target_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag in {"th", "td"}:
            self.in_cell = True
            self.cell_tag = tag
            self.cell_attributes = attributes
            self.cell_text = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_cell and tag == self.cell_tag:
            text = " ".join("".join(self.cell_text).split())
            self.current_row.append((self.cell_tag, self.cell_attributes, text))
            self.in_cell = False
        if self.in_target_table and tag == "tr" and self.in_row:
            self.rows.append(self.current_row)
            self.in_row = False
        if self.in_target_table and tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_target_table = False


def _read_response(
    opener: urllib.request.OpenerDirector,
    url: str,
    data: bytes | None = None,
) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Japan-COE-Workload-Dashboard/1.0 (public statistics viewer)",
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST" if data is not None else "GET",
    )
    with opener.open(request, timeout=request_timeout_seconds()) as response:
        if response.status != 200:
            raise SourceFormatError(f"e-Stat returned HTTP {response.status}.")
        body = response.read(10_000_001)
        if len(body) > 10_000_000:
            raise SourceFormatError("e-Stat response exceeded the 10 MB limit.")
        return body


def _post_json(opener: urllib.request.OpenerDirector, endpoint: str) -> dict[str, Any]:
    payload = _read_response(opener, f"https://www.e-stat.go.jp/dbview/{endpoint}?sid={ESTAT_TABLE_ID}", b"")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceFormatError("e-Stat returned malformed JSON metadata.") from error
    if not isinstance(value, dict):
        raise SourceFormatError("e-Stat returned an unexpected metadata shape.")
    return value


def _selected_items(dimension: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in dimension["listData"].values()
        if item.get("selected") is True
    ]


def _dimension_request(dimension: dict[str, Any]) -> dict[str, Any]:
    items = _selected_items(dimension)
    return {
        "matterId": dimension["matterId"],
        "tableName": dimension["tableName"],
        "dispTableName": dimension["dispTableName"],
        "positionNum": dimension["positionNum"],
        "listData": [
            {
                "name": item["name"],
                "code": item["code"],
                "unit": item.get("unitName"),
                "explanation": item.get("explanation"),
            }
            for item in items
        ],
        "allSelected": int(len(items) == dimension["number"]),
    }


def _encode_dimension_list(value: list[dict[str, Any]]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(gzip.compress(encoded, mtime=0)).decode("ascii")


def _result_payload(
    model: dict[str, Any], month_dimension: dict[str, Any], selected_period: dict[str, Any]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    cols: list[dict[str, Any]] = []
    tops: list[dict[str, Any]] = []
    api_tops: list[dict[str, Any]] = []

    for dimension in model["matters"].values():
        request_dimension = _dimension_request(dimension)
        position = dimension["position"]
        if dimension["matterId"] == month_dimension["matterId"]:
            api_tops.append(request_dimension)
            picked = {
                "name": selected_period["name"],
                "code": selected_period["code"],
                "explanation": selected_period.get("explanation"),
            }
            request_dimension = {**request_dimension, "listData": [picked]}
            tops.append(request_dimension)
        elif position == "row":
            rows.append(request_dimension)
        elif position == "col":
            cols.append(request_dimension)
        else:
            api_tops.append(request_dimension)
            selected = _selected_items(dimension)
            if not selected:
                raise SourceFormatError(f"No selected value in {dimension['matterName']}.")
            top = {
                **request_dimension,
                "listData": [
                    {
                        "name": selected[0]["name"],
                        "code": selected[0]["code"],
                        "explanation": selected[0].get("explanation"),
                    }
                ],
            }
            tops.append(top)

    payload = {
        key: model[key]
        for key in (
            "inputNumberOfRows",
            "inputNumberOfCols",
            "movementId",
            "annotationFlg",
            "rowNoDataDispFlg",
            "colNoDataDispFlg",
            "commaType",
            "replaceSpChars",
            "rightMoveFlg",
            "underMoveFlg",
            "leftMoveFlg",
            "upMoveFlg",
            "graphType",
            "graphTitle",
            "graphBasis",
            "graphAxis",
            "graphSort",
        )
    }
    payload.update(
        {
            "rows": _encode_dimension_list(rows),
            "cols": _encode_dimension_list(cols),
            "tops": _encode_dimension_list(tops),
            "apiTops": _encode_dimension_list(api_tops),
            "currentCols": "",
            "currentRows": "",
            "mode": "table",
        }
    )
    return payload


def _parse_integer(value: str) -> int | None:
    normalized = value.replace(",", "").strip()
    if normalized in {"", "***", "－", "…", "―", "-"}:
        return None
    if not re.fullmatch(r"\d+", normalized):
        raise SourceFormatError(f"Unexpected count value in e-Stat table: {value!r}.")
    return int(normalized)


def _parse_result_table(
    html: str,
    period: str,
    bureau_metadata: dict[str, dict[str, Any]],
    expected_fields: dict[str, str],
    unit: str,
) -> tuple[list[Observation], list[str]]:
    parser = _TableParser()
    parser.feed(html)
    column_codes: list[str] = []
    column_names: dict[str, str] = {}
    rows: list[Observation] = []
    warnings: list[str] = []

    for row in parser.rows:
        headers = [
            (attributes, text)
            for tag, attributes, text in row
            if tag == "th" and "js-dbview-cols" in attributes.get("class", "").split()
        ]
        if headers:
            column_codes = [attributes.get("data-unique", "") for attributes, _ in headers]
            column_names = {
                attributes.get("data-unique", ""): text for attributes, text in headers
            }
            labels = set(column_names.values())
            expected_labels = set(expected_fields) - {"未済"}
            if labels != expected_labels:
                raise SourceFormatError(
                    "e-Stat category fields changed: "
                    + ", ".join(sorted(labels))
                )
            continue

        bureau_cells = [
            (attributes, text)
            for tag, attributes, text in row
            if tag == "th" and "js-dbview-rows" in attributes.get("class", "").split()
        ]
        if not bureau_cells:
            continue
        if len(bureau_cells) != 1 or not column_codes:
            raise SourceFormatError("Unexpected bureau row or missing category headers.")
        attributes, bureau_name = bureau_cells[0]
        code = attributes.get("data-unique", "").split("@")[0]
        if code not in bureau_metadata:
            raise SourceFormatError(f"Unrecognized e-Stat bureau code {code!r}.")
        values = [
            text for tag, _, text in row if tag == "td"
        ]
        if len(values) != len(column_codes):
            raise SourceFormatError(
                f"Expected {len(column_codes)} values for {bureau_name}; received {len(values)}."
            )
        raw_values: dict[str, int | None] = {}
        for column_code, text in zip(column_codes, values, strict=True):
            japanese_name = column_names[column_code]
            raw_values[japanese_name] = _parse_integer(text)
        if bureau_metadata[code]["name"] != bureau_name:
            raise SourceFormatError(
                f"Bureau label changed for {code}: {bureau_name!r}."
            )
        mapped = {
            expected_fields[name]: value
            for name, value in raw_values.items()
            if name in expected_fields
        }
        validate_nonnegative_counts(mapped)
        result = calculate_workload(
            WorkloadCounts(
                accepted_total=mapped.get("accepted_total"),
                old_receipts=mapped.get("old_receipts"),
                new_receipts=mapped.get("new_receipts"),
                completed_total=mapped.get("completed_total"),
                issued=mapped.get("issued"),
                not_issued=mapped.get("not_issued"),
                completed_other=mapped.get("completed_other"),
                pending_official=mapped.get("pending_official"),
            )
        )
        warnings.extend(f"{bureau_name} {period}: {message}" for message in result.discrepancies)
        rows.append(
            Observation(
                period=period,
                bureau=Bureau(
                    code=code,
                    name=bureau_name,
                    hierarchy_type=bureau_metadata[code]["hierarchy_type"],
                    parent_code=bureau_metadata[code]["parent_code"],
                    sequence_number=bureau_metadata[code]["seq_no"],
                ),
                values={**mapped, "pending_calculated": result.pending_calculated},
                raw_values=raw_values,
                unit=unit,
            )
        )

    if not rows:
        raise SourceFormatError("e-Stat result contained no bureau observations.")
    seen = {row.bureau.code for row in rows}
    expected = set(bureau_metadata)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise SourceFormatError(
            f"Incomplete bureau rows (missing={missing}, extra={extra})."
        )
    if len(seen) != len(rows):
        raise SourceFormatError("Duplicate bureau rows in e-Stat result.")
    return rows, warnings


def _period_from_name(name: str) -> str:
    match = PERIOD_PATTERN.search(name)
    if not match:
        raise SourceFormatError(f"Unrecognized reporting period {name!r}.")
    return f"{match.group('year')}-{int(match.group('month')):02d}"


def _hierarchy(model: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    dimensions = model.get("matters", {})
    bureau_dimension = next(
        (
            dimension
            for dimension in dimensions.values()
            if dimension.get("matterName") == "地方出入国在留管理局・支局"
        ),
        None,
    )
    measure_dimension = next(
        (
            dimension
            for dimension in dimensions.values()
            if dimension.get("matterName") == "表章項目"
        ),
        None,
    )
    category_dimension = next(
        (
            dimension
            for dimension in dimensions.values()
            if dimension.get("matterName") == "在留資格審査の受理・処理"
        ),
        None,
    )
    month_dimension = next(
        (
            dimension
            for dimension in dimensions.values()
            if dimension.get("matterName") == "時間軸（月次）"
        ),
        None,
    )
    if not all((bureau_dimension, measure_dimension, category_dimension, month_dimension)):
        raise SourceFormatError("e-Stat dimension names changed unexpectedly.")

    selected_measures = _selected_items(measure_dimension)
    if (
        len(selected_measures) != 1
        or selected_measures[0].get("name") != "在留資格認定証明書交付人員"
    ):
        raise SourceFormatError("Unexpected e-Stat table measure.")
    unit = selected_measures[0].get("unitName")
    if unit != "人":
        raise SourceFormatError(f"Unexpected source unit {unit!r}; expected '人'.")

    category_names = {
        item["name"]
        for item in _selected_items(category_dimension)
    }
    if category_names != set(EXPECTED_FIELD_NAMES - {"未済"}):
        raise SourceFormatError(
            "e-Stat receipt/outcome category set changed: "
            + ", ".join(sorted(category_names))
        )
    bureau_items = list(bureau_dimension["listData"].values())
    if not bureau_items or len(bureau_items) > 100:
        raise SourceFormatError("Unexpected number of bureau/jurisdiction rows.")
    metadata: dict[str, dict[str, Any]] = {}
    current_parent: str | None = None
    for item in sorted(bureau_items, key=lambda row: row["seqNo"]):
        code = item["code"]
        name = item["name"]
        if code == "100000" or name == "総数":
            hierarchy_type = "national_total"
            current_parent = None
        elif name.endswith("管内"):
            hierarchy_type = "bureau_jurisdiction"
            current_parent = code
        else:
            hierarchy_type = "office"
        metadata[code] = {
            "name": name,
            "hierarchy_type": hierarchy_type,
            "parent_code": current_parent if hierarchy_type == "office" else None,
            "seq_no": int(item["seqNo"]),
            "class_level": int(item["classLevel"]),
        }
    if sum(item["hierarchy_type"] == "national_total" for item in metadata.values()) != 1:
        raise SourceFormatError("e-Stat national total row is missing or ambiguous.")
    if not any(item["hierarchy_type"] == "bureau_jurisdiction" for item in metadata.values()):
        raise SourceFormatError("e-Stat jurisdiction aggregate rows are missing.")
    return metadata, month_dimension


def fetch_dataset() -> Dataset:
    import http.cookiejar

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    page = _read_response(opener, ESTAT_URL)
    model = _post_json(opener, "api_get_model")
    bureau_metadata, month_dimension = _hierarchy(model)
    period_items = _selected_items(month_dimension)
    if not period_items or len(period_items) > 24:
        raise SourceFormatError(
            f"Unexpected number of available months ({len(period_items)})."
        )

    all_observations: list[Observation] = []
    warnings: list[str] = []
    raw_parts = [page]
    for index, item in enumerate(period_items):
        period = _period_from_name(item["name"])
        payload = _result_payload(model, month_dimension, item)
        body = urllib.parse.urlencode(payload).encode()
        response_body = _read_response(
            opener,
            f"https://www.e-stat.go.jp/dbview/api_get_result?sid={ESTAT_TABLE_ID}",
            body,
        )
        try:
            result = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceFormatError("e-Stat returned malformed result JSON.") from error
        if not isinstance(result, dict) or result.get("error"):
            raise SourceFormatError("e-Stat rejected the table data request.")
        table_html = result.get("table")
        if not isinstance(table_html, str) or not table_html:
            raise SourceFormatError("e-Stat returned an empty table.")
        rows, month_warnings = _parse_result_table(
            table_html,
            period,
            bureau_metadata,
            EXPECTED_FIELDS,
            "人",
        )
        all_observations.extend(rows)
        warnings.extend(month_warnings)
        raw_parts.append(response_body)
        if index < len(period_items) - 1:
            time.sleep(0.15)

    periods = {observation.period for observation in all_observations}
    if len(periods) != len(period_items):
        raise SourceFormatError("e-Stat reporting periods are duplicated.")
    raw_response = json.dumps(
        [part.decode("utf-8") for part in raw_parts],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    page_text = page.decode("utf-8", "replace")
    publication_match = PUBLICATION_PATTERN.search(page_text)
    publication_date = publication_match.group(1) if publication_match else None
    title_match = re.search(r'<title>(.*?)</title>', page_text, re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    latest_period = max(periods)
    return Dataset(
        observations=tuple(all_observations),
        publication_date=publication_date,
        latest_period=latest_period,
        content_hash=hashlib.sha256(raw_response).hexdigest(),
        raw_response=raw_response,
        warnings=tuple(warnings),
        source_title=title,
    )
