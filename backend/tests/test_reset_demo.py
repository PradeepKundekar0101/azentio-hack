import pytest

from app.core.config import Settings
from scripts.reset_demo import reset_demo
from scripts.seed_reference import load_reference_rows


def test_reset_demo_empties_data_and_reloads_reference(settings: Settings, sql) -> None:
    sql("insert into providers (provider_id, name, city) values ('PRV-9999', 'Stale', 'Nowhere')")
    sql(
        """
        insert into import_batches (uploaded_by, files, status, counts) values ('demo', '[]', 'completed', '{}');
        insert into policies (policy_number, policyholder_name, insured_member_ids, product_name,
            benefit_period_start, benefit_period_end, overall_limit, deductible_amount, deductible_basis,
            copay_percent)
        values ('POL-000001', 'A', '{MEM-001}', 'Silver', '2026-01-01', '2026-12-31', 300000, 0, 'per_claim', 0);
        """
    )

    reset_demo(settings, confirm=True)

    service_codes, providers = load_reference_rows()
    assert sql("select count(*) from policies")[0][0] == 0
    assert sql("select count(*) from import_batches")[0][0] == 0
    assert sql("select count(*) from providers")[0][0] == len(providers)
    assert sql("select count(*) from service_codes")[0][0] == len(service_codes)


def test_reset_demo_refuses_without_confirmation(settings: Settings) -> None:
    with pytest.raises(SystemExit):
        reset_demo(settings, confirm=False)
