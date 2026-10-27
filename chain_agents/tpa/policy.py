"""Research rules, not a hospital-approved protocol or complete IVT assessment."""
from dataclasses import asdict, dataclass, fields
import math


@dataclass(frozen=True)
class Policy:
    version: str = 'tpa-rules-prototype-0.2.0'
    protocol_id: str = 'RESEARCH-DEMO'
    approval_status: str = 'RESEARCH'
    approved_by: str = ''
    site_id: str = ''
    standard_window_seconds: int = 16200
    platelet_min_per_ul: int = 100000
    inr_max: float = 1.7
    sbp_limit: int = 185
    dbp_limit: int = 110
    bp_recheck_seconds: int = 300  # Local demo freshness policy, not a guideline.
    glucose_mock_low: int = 50
    glucose_mock_high: int = 400  # CHAIN mock range, not a universal contraindication.
    alteplase_mg_per_kg: float = 0.9
    alteplase_max_mg: float = 90
    alteplase_bolus_fraction: float = 0.1
    tenecteplase_mg_per_kg: float = 0.25
    tenecteplase_max_mg: float = 25

    def __post_init__(self):
        if self.approval_status not in {'RESEARCH', 'SITE_APPROVED'}:
            raise ValueError('Unknown protocol approval status')
        if not self.protocol_id or not self.version:
            raise ValueError('Protocol ID and version are required')
        if self.approval_status == 'SITE_APPROVED' and (not self.approved_by or not self.site_id or self.protocol_id == 'RESEARCH-DEMO'):
            raise ValueError('Site protocol requires explicit site and approval provenance')
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name in {'version', 'protocol_id', 'approval_status', 'approved_by', 'site_id'}:
                if not isinstance(value, str):
                    raise ValueError('Protocol identity must be text')
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Protocol parameters must be finite positive numbers')
        if self.glucose_mock_low >= self.glucose_mock_high or self.alteplase_bolus_fraction >= 1:
            raise ValueError('Inconsistent protocol parameters')

    def identity(self):
        return {key: asdict(self)[key] for key in ('protocol_id', 'version', 'approval_status', 'site_id', 'approved_by')}


def resolve_policy(services):
    """Deployment-owned configuration, never model output or a patient request."""
    configured = getattr(services, 'ivt_protocol', None)
    if configured is None:
        return POLICY
    if isinstance(configured, Policy):
        return configured
    if not isinstance(configured, dict) or set(configured) - {item.name for item in fields(Policy)}:
        raise ValueError('Invalid ivt_protocol configuration')
    return Policy(**configured)


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
