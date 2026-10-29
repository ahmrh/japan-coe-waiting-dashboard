from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class WorkloadCounts:
    accepted_total: int | None
    old_receipts: int | None
    new_receipts: int | None
    completed_total: int | None
    issued: int | None
    not_issued: int | None
    completed_other: int | None
    pending_official: int | None = None


@dataclass(frozen=True)
class WorkloadCalculation:
    pending_calculated: int | None
    received_reconciles: bool | None
    completed_reconciles: bool | None
    discrepancies: tuple[str, ...]


def calculate_workload(counts: WorkloadCounts) -> WorkloadCalculation:
    discrepancies: list[str] = []
    received_reconciles: bool | None = None
    completed_reconciles: bool | None = None

    receipt_values = (counts.accepted_total, counts.old_receipts, counts.new_receipts)
    if all(value is not None for value in receipt_values):
        received_reconciles = (
            counts.accepted_total == counts.old_receipts + counts.new_receipts
        )
        if not received_reconciles:
            discrepancies.append("受理_総数 does not equal 受理_旧受 + 受理_新受")

    completed_values = (
        counts.completed_total,
        counts.issued,
        counts.not_issued,
        counts.completed_other,
    )
    if all(value is not None for value in completed_values):
        completed_reconciles = (
            counts.completed_total
            == counts.issued + counts.not_issued + counts.completed_other
        )
        if not completed_reconciles:
            discrepancies.append(
                "既済_総数 does not equal 既済_交付 + 既済_不交付 + 既済_その他"
            )

    pending: int | None = None
    if counts.pending_official is not None:
        pending = counts.pending_official
    elif (
        received_reconciles is True
        and completed_reconciles is True
        and counts.accepted_total is not None
        and counts.completed_total is not None
    ):
        candidate = counts.accepted_total - counts.completed_total
        if candidate >= 0:
            pending = candidate
        else:
            discrepancies.append("Calculated pending balance would be negative")

    return WorkloadCalculation(
        pending_calculated=pending,
        received_reconciles=received_reconciles,
        completed_reconciles=completed_reconciles,
        discrepancies=tuple(discrepancies),
    )


def validate_nonnegative_counts(values: Mapping[str, int | None]) -> None:
    for field, value in values.items():
        if value is not None and value < 0:
            raise ValueError(f"{field} must not be negative.")
