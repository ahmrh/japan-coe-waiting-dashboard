from app.statistics import WorkloadCounts, calculate_workload


def test_month_end_balance_is_derived_only_after_both_totals_reconcile() -> None:
    result = calculate_workload(
        WorkloadCounts(
            accepted_total=100,
            old_receipts=60,
            new_receipts=40,
            completed_total=35,
            issued=25,
            not_issued=5,
            completed_other=5,
        )
    )

    assert result.pending_calculated == 65
    assert result.received_reconciles is True
    assert result.completed_reconciles is True
    assert result.discrepancies == ()


def test_mismatched_received_total_withholds_pending_balance() -> None:
    result = calculate_workload(
        WorkloadCounts(
            accepted_total=99,
            old_receipts=60,
            new_receipts=40,
            completed_total=35,
            issued=25,
            not_issued=5,
            completed_other=5,
        )
    )

    assert result.pending_calculated is None
    assert result.received_reconciles is False
    assert result.completed_reconciles is True
    assert "受理_総数" in result.discrepancies[0]


def test_mismatched_outcomes_withhold_pending_balance() -> None:
    result = calculate_workload(
        WorkloadCounts(
            accepted_total=100,
            old_receipts=60,
            new_receipts=40,
            completed_total=35,
            issued=24,
            not_issued=5,
            completed_other=5,
        )
    )

    assert result.pending_calculated is None
    assert result.completed_reconciles is False
    assert "既済_総数" in result.discrepancies[0]


def test_missing_values_are_not_replaced_with_zero() -> None:
    result = calculate_workload(
        WorkloadCounts(
            accepted_total=100,
            old_receipts=60,
            new_receipts=40,
            completed_total=None,
            issued=25,
            not_issued=None,
            completed_other=5,
        )
    )

    assert result.pending_calculated is None
    assert result.completed_reconciles is None
    assert result.discrepancies == ()


def test_negative_balance_is_withheld() -> None:
    result = calculate_workload(
        WorkloadCounts(
            accepted_total=10,
            old_receipts=5,
            new_receipts=5,
            completed_total=12,
            issued=7,
            not_issued=3,
            completed_other=2,
        )
    )

    assert result.pending_calculated is None
    assert "negative" in result.discrepancies[0]
