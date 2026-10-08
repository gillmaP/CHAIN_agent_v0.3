import copy
import json
import unittest
from datetime import timedelta
from types import SimpleNamespace

from chain_agents.common import canonical_hash
from chain_agents.tpa.agent import invoke
from chain_agents.tpa.demo import sample
from chain_agents.tpa.dose import calculate
from chain_agents.tpa.facts import timestamp
from examples.support import sample as starter_sample, services


def bind(request, snapshot):
    snapshot['snapshot_id'] = canonical_hash({k: v for k, v in snapshot.items() if k != 'snapshot_id'})
    request['input_snapshot_id'] = snapshot['snapshot_id']
    request['scope'] = list(snapshot['facts'])
    request['dependencies'] = [copy.deepcopy(ref) for fact in snapshot['facts'].values()
                               for ref in fact.get('dependencies', [fact['source_ref']])]


class TpaTests(unittest.TestCase):
    def setUp(self):
        self.request, self.snapshot = sample()

    def change(self, field, **updates):
        self.snapshot['facts'][field].update(updates)
        bind(self.request, self.snapshot)

    def output(self):
        return invoke(self.request, self.snapshot, SimpleNamespace())

    def checks(self):
        return {check['check_id']: check for check in self.output()['assessment']['checks']}

    def test_modes_and_exact_domain_keys(self):
        for mode in ('interim', 'final'):
            with self.subTest(mode=mode):
                request, snapshot = sample(mode)
                output = invoke(request, snapshot, services())
                self.assertEqual(set(output), {'mode', 'evidence_package', 'assessment', 'mock_only'})
                self.assertEqual(output['mode'], mode)
                self.assertTrue(output['mock_only'])
                self.assertEqual(output['evidence_package'], snapshot['facts'])
                json.dumps(output, allow_nan=False)

    def test_input_and_output_objects_are_isolated(self):
        before = copy.deepcopy((self.request, self.snapshot))
        output = self.output()
        self.assertEqual((self.request, self.snapshot), before)
        output['evidence_package']['age']['value'] = 1
        output['assessment']['checks'][0]['evidence'][0]['source_ref']['version'] = 99
        self.assertEqual((self.request, self.snapshot), before)

    def test_no_eligible_state_or_autonomous_action(self):
        output = self.output()
        assessment = output['assessment']
        self.assertEqual(assessment['status'], 'PHYSICIAN_REVIEW_REQUIRED')
        self.assertTrue(assessment['physician_decision_required'])
        self.assertFalse(assessment['dose_preview']['auto_order'])
        self.assertFalse(assessment['dose_preview']['auto_administration'])
        self.assertNotIn('dose_suggestion', output)
        self.assertNotIn('confidence', output)

    def test_partial_starter_input_still_works(self):
        request, snapshot = starter_sample('final')
        output = invoke(request, snapshot, services())
        self.assertEqual(output['assessment']['status'], 'INCOMPLETE_PENDING_DATA')
        self.assertEqual(output['assessment']['dose_preview']['options'], [])

    def test_wrong_mode_fails(self):
        self.request['mode'] = 'unknown-stage'
        with self.assertRaises(ValueError):
            self.output()

    def test_wrong_snapshot_fails(self):
        self.request['input_snapshot_id'] = 'wrong'
        with self.assertRaises(ValueError):
            self.output()

    def test_wrong_scope_fails(self):
        self.request['scope'] = ['age']
        with self.assertRaises(ValueError):
            self.output()

    def test_explicit_evaluation_time_required(self):
        self.request.pop('evaluated_at')
        with self.assertRaises(ValueError):
            self.output()

    def test_timestamp_requires_timezone(self):
        self.request['evaluated_at'] = '2026-10-06T15:36:00'
        with self.assertRaises(ValueError):
            self.output()

    def test_future_evidence_and_snapshot_are_rejected(self):
        for location, key in (('fact', 'source_time'), ('fact', 'known_at'), ('snapshot', 'known_at')):
            with self.subTest(location=location, key=key):
                self.setUp()
                target = self.snapshot['facts']['age'] if location == 'fact' else self.snapshot
                target[key] = '2026-10-06T16:00:00+09:00'
                bind(self.request, self.snapshot)
                with self.assertRaises(ValueError):
                    self.output()

    def test_check_ids_and_scoped_provenance(self):
        checks = self.output()['assessment']['checks']
        self.assertEqual(len(checks), 12)
        self.assertEqual(len({check['check_id'] for check in checks}), 12)
        scoped = {canonical_hash(ref) for ref in self.request['dependencies']}
        for check in checks:
            for evidence in check['evidence']:
                for ref in evidence.get('dependencies', [evidence['source_ref']]):
                    self.assertIn(canonical_hash(ref), scoped)
                self.assertIn('source_time', evidence)
                self.assertIn('known_at', evidence)

    def test_fact_metadata_and_dependencies_are_preserved(self):
        fact = self.snapshot['facts']['platelet_count']
        fact.update(confirmation_status='PHYSICIAN_CONFIRMED', dependencies=[copy.deepcopy(fact['source_ref'])])
        bind(self.request, self.snapshot)
        evidence = self.checks()['C03_PLATELET_GE_100K']['evidence'][0]
        self.assertEqual(evidence['dependencies'], fact['dependencies'])
        self.assertEqual(evidence['confirmation_status'], fact['confirmation_status'])

    def test_unavailable_statuses_do_not_use_their_stale_values(self):
        for status in ('UNKNOWN', 'PENDING', 'CONFLICT', 'UNAVAILABLE', 'ERROR', 'RETRACTED', 'INVALIDATED'):
            with self.subTest(status=status):
                self.change('platelet_count', value=214000, status=status)
                result = self.checks()['C03_PLATELET_GE_100K']['result']
                self.assertEqual(result, 'CONFLICT' if status == 'CONFLICT' else 'PENDING')
                self.assertEqual(self.output()['evidence_package']['platelet_count']['status'], status)

    def test_derived_fact_keeps_original_dependencies(self):
        fact = self.snapshot['facts']['lkw']
        fact['dependencies'] = [copy.deepcopy(fact['source_ref'])]
        fact['source_ref'] = {'system': 'SYNTHETIC_SUMMARY', 'record_id': 'DERIVED-001', 'version': 1, 'field': 'lkw'}
        bind(self.request, self.snapshot)
        evidence = self.checks()['C01_TIME_WINDOW']['evidence'][0]
        self.assertEqual(evidence['source_ref'], fact['source_ref'])
        self.assertEqual(evidence['dependencies'], fact['dependencies'])

    def test_unknown_status_is_not_interpreted_as_available(self):
        self.change('inr', status='CUSTOM_UNREVIEWED_STATUS', value=1.0)
        self.assertEqual(self.checks()['C04_INR_LE_1_7']['result'], 'PENDING')

    def test_null_is_missing(self):
        self.change('weight_kg', value=None)
        self.assertEqual(self.output()['assessment']['dose_preview']['options'], [])
        self.assertIn('weight_kg', self.output()['assessment']['missing_information'])

    def test_interim_uses_only_the_supplied_snapshot(self):
        request, snapshot = sample('interim')
        output = invoke(request, snapshot, services())
        self.assertEqual(output['assessment']['status'], 'INCOMPLETE_PENDING_DATA')
        checks = {check['check_id']: check for check in output['assessment']['checks']}
        for key in ('C02_NO_ICH_ON_NCCT', 'C03_PLATELET_GE_100K', 'C04_INR_LE_1_7', 'C10_NIHSS'):
            self.assertEqual(checks[key]['result'], 'PENDING')

    def test_time_window_boundary_and_selected_extension(self):
        now = timestamp(self.request['evaluated_at'])
        for elapsed, expected in ((16200, 'PASS'), (16201, 'REQUIRES_PHYSICIAN_REVIEW')):
            with self.subTest(elapsed=elapsed):
                self.change('lkw', value=(now - timedelta(seconds=elapsed)).isoformat())
                self.assertEqual(self.checks()['C01_TIME_WINDOW']['result'], expected)

    def test_future_lkw_is_invalid(self):
        self.change('lkw', value='2026-10-06T16:00:00+09:00')
        with self.assertRaises(ValueError):
            self.output()

    def test_completed_ncct_requires_a_physician_read(self):
        self.assertEqual(self.checks()['C02_NO_ICH_ON_NCCT']['result'], 'REQUIRES_PHYSICIAN_READ')

    def test_upstream_completed_status_is_scoped_to_ncct(self):
        self.change('ncct_completed', status='COMPLETED', confirmation_status='PHYSICIAN_READ_REQUIRED')
        before = copy.deepcopy(self.snapshot)
        output = self.output()
        checks = {item['check_id']: item for item in output['assessment']['checks']}
        self.assertEqual(checks['C02_NO_ICH_ON_NCCT']['result'], 'REQUIRES_PHYSICIAN_READ')
        self.assertNotIn('ncct_completed', output['assessment']['missing_information'])
        self.assertEqual(output['evidence_package'], before['facts'])
        self.assertEqual(self.snapshot, before)
        self.change('ncct_order_id', value='OTHER-ORDER')
        self.assertEqual(self.checks()['C02_NO_ICH_ON_NCCT']['result'], 'CONFLICT')
        self.change('platelet_count', status='COMPLETED')
        self.assertEqual(self.checks()['C03_PLATELET_GE_100K']['result'], 'PENDING')

    def test_ncct_order_mismatch_is_conflict(self):
        self.change('ncct_order_id', value='OTHER-ORDER')
        self.assertEqual(self.checks()['C02_NO_ICH_ON_NCCT']['result'], 'CONFLICT')

    def test_ncct_false_is_not_missing_or_a_negative_read(self):
        self.change('ncct_completed', value=False)
        self.assertEqual(self.checks()['C02_NO_ICH_ON_NCCT']['value']['completed'], False)
        self.assertEqual(self.output()['assessment']['status'], 'INCOMPLETE_PENDING_DATA')

    def test_ncct_boolean_not_text(self):
        self.change('ncct_completed', value='true')
        with self.assertRaises(ValueError):
            self.output()

    def test_platelet_threshold_and_units(self):
        for value, unit, expected in ((100000, '/uL', 'PASS'), (99999, '/uL', 'FAIL'),
                                      (214, '10^9/L', 'PASS'), (99, '10^3/uL', 'FAIL')):
            with self.subTest(value=value, unit=unit):
                self.change('platelet_count', value=value, unit=unit)
                self.assertEqual(self.checks()['C03_PLATELET_GE_100K']['result'], expected)

    def test_units_are_not_guessed(self):
        for field, check_id in (('platelet_count', 'C03_PLATELET_GE_100K'),
                                ('sbp', 'C06_BP_LT_185_110'), ('glucose', 'C07_GLUCOSE_50_400')):
            with self.subTest(field=field):
                self.setUp()
                self.snapshot['facts'][field].pop('unit')
                bind(self.request, self.snapshot)
                self.assertEqual(self.checks()[check_id]['result'], 'REQUIRES_PHYSICIAN_REVIEW')

    def test_inr_threshold(self):
        for value, expected in ((1.7, 'PASS'), (1.71, 'FAIL')):
            with self.subTest(value=value):
                self.change('inr', value=value)
                self.assertEqual(self.checks()['C04_INR_LE_1_7']['result'], expected)

    def test_blocking_lab_finding_is_reported(self):
        self.change('platelet_count', value=90000)
        self.assertEqual(self.output()['assessment']['status'], 'BLOCKING_FINDING_IDENTIFIED')

    def test_anticoagulant_absence_requires_confirmation(self):
        for value in (False, 'NO_EVIDENCE', 'NONE_DOCUMENTED'):
            with self.subTest(value=value):
                self.change('anticoagulant', value=value)
                self.assertEqual(self.checks()['C05_NO_ANTICOAGULANT']['result'], 'PASS_UNCONFIRMED')
        self.change('anticoagulant', value=False, confirmation_status='PHYSICIAN_CONFIRMED')
        self.assertEqual(self.checks()['C05_NO_ANTICOAGULANT']['result'], 'PASS')

    def test_upstream_no_evidence_status_remains_unconfirmed(self):
        for confirmation in ('UNCONFIRMED', 'PHYSICIAN_CONFIRMED'):
            with self.subTest(confirmation=confirmation):
                self.change('anticoagulant', value=False, status='NO_EVIDENCE', confirmation_status=confirmation)
                output = self.output()
                checks = {item['check_id']: item for item in output['assessment']['checks']}
                self.assertEqual(checks['C05_NO_ANTICOAGULANT']['result'], 'PASS_UNCONFIRMED')
                self.assertNotIn('anticoagulant', output['assessment']['missing_information'])
                self.assertEqual(output['evidence_package'], self.snapshot['facts'])
        self.change('anticoagulant', value=True)
        self.assertEqual(self.checks()['C05_NO_ANTICOAGULANT']['result'], 'REQUIRES_PHYSICIAN_REVIEW')
        self.change('anticoagulant', value=None)
        self.assertEqual(self.checks()['C05_NO_ANTICOAGULANT']['result'], 'PENDING')
        self.change('platelet_count', status='NO_EVIDENCE')
        self.assertEqual(self.checks()['C03_PLATELET_GE_100K']['result'], 'PENDING')

    def test_anticoagulant_exposure_is_review_not_automatic_exclusion(self):
        for value in (True, 'PRESENT', 'apixaban', {'drug': 'warfarin', 'last_dose': None}):
            with self.subTest(value=value):
                self.change('anticoagulant', value=value)
                self.assertEqual(self.checks()['C05_NO_ANTICOAGULANT']['result'], 'REQUIRES_PHYSICIAN_REVIEW')

    def test_bp_boundaries_and_staleness(self):
        for sbp, dbp, expected in ((184, 109, 'PASS'), (185, 100, 'REQUIRES_PHYSICIAN_REVIEW'),
                                   (170, 110, 'REQUIRES_PHYSICIAN_REVIEW')):
            with self.subTest(sbp=sbp, dbp=dbp):
                self.change('sbp', value=sbp)
                self.change('dbp', value=dbp)
                self.assertEqual(self.checks()['C06_BP_LT_185_110']['result'], expected)
        self.change('sbp', value=170, source_time='2026-10-06T15:30:59+09:00')
        self.change('dbp', value=90)
        self.assertEqual(self.checks()['C06_BP_LT_185_110']['result'], 'PASS_WITH_FLAG')

    def test_glucose_units_and_mock_boundaries(self):
        for value, unit, expected in ((50, 'mg/dL', 'PASS'), (400, 'mg/dL', 'PASS'),
                                      (49, 'mg/dL', 'REQUIRES_PHYSICIAN_REVIEW'),
                                      (401, 'mg/dL', 'REQUIRES_PHYSICIAN_REVIEW'), (5, 'mmol/L', 'PASS')):
            with self.subTest(value=value, unit=unit):
                self.change('glucose', value=value, unit=unit)
                self.assertEqual(self.checks()['C07_GLUCOSE_50_400']['result'], expected)

    def test_age_and_nihss_never_automatically_exclude(self):
        for age, nihss in ((95, 0), (85, 42)):
            with self.subTest(age=age, nihss=nihss):
                self.change('age', value=age)
                self.change('nihss', value=nihss)
                checks = self.checks()
                self.assertEqual(checks['C12_AGE']['result'], 'INFO')
                self.assertEqual(checks['C10_NIHSS']['result'], 'INFO')

    def test_pediatric_case_requires_review(self):
        self.change('age', value=17)
        self.assertEqual(self.checks()['C12_AGE']['result'], 'REQUIRES_PHYSICIAN_REVIEW')

    def test_history_outside_scope_has_no_fabricated_evidence(self):
        checks = self.checks()
        for key in ('C08_NO_RECENT_SURGERY_BLEED', 'C09_NO_PRIOR_ICH_OR_RECENT_STROKE', 'C11_ANTIPLATELET'):
            self.assertEqual(checks[key]['result'], 'NOT_IN_SCOPE')
            self.assertEqual(checks[key]['evidence'], [])

    def test_scoped_history_is_displayed_without_nlp(self):
        self.snapshot['facts']['antiplatelet'] = copy.deepcopy(self.snapshot['facts']['anticoagulant'])
        self.snapshot['facts']['antiplatelet']['source_ref']['field'] = 'antiplatelet'
        self.snapshot['facts']['antiplatelet']['value'] = 'aspirin 100 mg daily'
        bind(self.request, self.snapshot)
        check = self.checks()['C11_ANTIPLATELET']
        self.assertEqual(check['value'], 'aspirin 100 mg daily')
        self.assertNotEqual(check['result'], 'FAIL')

    def test_invalid_numbers_raise_value_error(self):
        for field, value in (('age', True), ('age', 3.5), ('age', 131), ('nihss', 43),
                             ('nihss', 1.5), ('weight_kg', 0), ('weight_kg', -1),
                             ('weight_kg', '67'), ('platelet_count', False), ('inr', -1),
                             ('glucose', -1), ('sbp', 0), ('inr', 0)):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.change(field, value=value)
                with self.assertRaises(ValueError):
                    self.output()

    def test_nonfinite_values_are_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                self.snapshot['facts']['inr']['value'] = value
                with self.assertRaises(ValueError):
                    self.output()

    def test_bad_fact_metadata_is_value_error(self):
        self.snapshot['facts']['age'].pop('source_time')
        with self.assertRaises(ValueError):
            self.output()

    def test_weight_unit_conflict_is_rejected(self):
        self.change('weight_kg', unit='g')
        with self.assertRaises(ValueError):
            self.output()

    def test_no_service_side_effects(self):
        class ForbiddenServices:
            def __getattr__(self, name):
                raise AssertionError('Unexpected service access: ' + name)
        invoke(self.request, self.snapshot, ForbiddenServices())


class DoseTests(unittest.TestCase):
    def test_67kg_exact_arithmetic_and_half_up_display(self):
        alteplase, tenecteplase = calculate(67)
        self.assertEqual((alteplase['total_mg'], alteplase['bolus_mg'], alteplase['infusion_mg']), (60.3, 6.03, 54.27))
        self.assertEqual(tenecteplase['total_mg'], 16.75)
        self.assertEqual(tenecteplase['display_rounded_mg']['total'], 16.8)

    def test_dose_caps(self):
        alteplase, tenecteplase = calculate(120)
        self.assertEqual((alteplase['total_mg'], alteplase['bolus_mg'], alteplase['infusion_mg']), (90, 9, 81))
        self.assertEqual(tenecteplase['total_mg'], 25)

    def test_invalid_weights(self):
        for value in (None, 0, -1, True, '67', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(value)


if __name__ == '__main__':
    unittest.main()
