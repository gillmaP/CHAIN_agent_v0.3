"""Research rules, not a hospital-approved protocol or complete IVT assessment."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    version: str = 'tpa-rules-prototype-0.1.0'
    standard_window_seconds: int = 16200
    platelet_min_per_ul: int = 100000
    inr_max: float = 1.7
    sbp_limit: int = 185
    dbp_limit: int = 110
    bp_recheck_seconds: int = 300  # Local demo freshness policy, not a guideline.
    glucose_mock_low: int = 50
    glucose_mock_high: int = 400  # CHAIN mock range, not a universal contraindication.


POLICY = Policy()
REQUIRED_FIELDS = ('lkw', 'ncct_completed', 'ncct_order_id', 'ct_order_id',
                   'platelet_count', 'inr', 'anticoagulant', 'weight_kg')
LIMITATIONS = (
    'RESEARCH_PROTOTYPE_NOT_SITE_APPROVED',
    'NCCT_COMPLETION_IS_NOT_A_NEGATIVE_HEMORRHAGE_READ',
    'NO_EVIDENCE_IS_NOT_CONFIRMED_ABSENCE',
    'DISABLING_DEFICIT_AND_COMPLETE_CONTRAINDICATION_HISTORY_REQUIRE_PHYSICIAN_REVIEW',
    'PENDING_LAB_DATA_IS_NOT_AN_INSTRUCTION_TO_DELAY_TREATMENT',
    'EXTENDED_OR_UNKNOWN_ONSET_IMAGING_SELECTION_IS_OUTSIDE_THIS_PROTOTYPE',
)
