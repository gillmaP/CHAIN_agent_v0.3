"""Standalone HTML report for typed S1 Summary comparisons."""
import argparse
import html
import json
from pathlib import Path

from .history_s1_contract import canonical_value, normalize_text, validate_final_items
from .history_s1_cases import cases
from .history_s1_experiment import METHODS, MODELS, _sources

MODEL_NAMES = {
    'qwen35_9b': 'Qwen3.5-9B',
    'gemma4_12b_it': 'Gemma4-12B-it',
    'medgemma15_4b_it': 'MedGemma1.5-4B-it',
}
METHOD_NAMES = {'direct': '기존 순서 · 한 번 호출', 'evidence_first': '인용 우선 순서 · 한 번 호출'}


def _matches_value(question, actual, gold):
    return canonical_value(actual, question) == canonical_value(gold, question)


def _alt_keys(question, item):
    return sorted(json.dumps(canonical_value(x.get('value'), question), sort_keys=True, ensure_ascii=False)
                  for x in item.get('alternatives', []) if isinstance(x, dict))


def _semantic_match(question, actual, gold):
    if not isinstance(actual, dict) or actual.get('status') != gold['status']:
        return False
    if gold['status'] == 'conflicting':
        expected = sorted(json.dumps(canonical_value(x['value'], question), sort_keys=True, ensure_ascii=False)
                          for x in gold['alternatives'])
        return _alt_keys(question, actual) == expected
    if gold['status'] == 'documented':
        return _matches_value(question, actual.get('value'), gold['value'])
    return actual.get('value') is None


def _evidence_list(item):
    if not isinstance(item, dict):
        return []
    result = list(item.get('evidence', [])) if isinstance(item.get('evidence'), list) else []
    for alternative in item.get('alternatives', []):
        if isinstance(alternative, dict):
            if isinstance(alternative.get('evidence'), list):
                result.extend(alternative['evidence'])
    return result


def _evidence_valid(item, sources):
    if not isinstance(item, dict) or 'source_ref' not in item:
        return False
    ref = item['source_ref']
    if ref not in sources:
        return False
    if set(item) == {'source_ref', 'quote'}:
        quote = item.get('quote')
        return isinstance(quote, str) and bool(quote.strip()) and normalize_text(quote) in normalize_text(sources[ref].get('text', ''))
    if set(item) == {'source_ref', 'record'}:
        source = sources[ref]
        return any(item['record'] in source.get(key, []) for key in ('medications', 'conditions', 'encounters')
                   if isinstance(source.get(key), list))
    return False


def _evidence_recall(actual, gold):
    expected = _evidence_list(gold)
    predicted = _evidence_list(actual)
    if not expected:
        return (0, 0)
    matched = 0
    for target in expected:
        if set(target) == {'source_ref', 'record'}:
            found = any(p == target for p in predicted)
        else:
            target_quote = normalize_text(target.get('quote', ''))
            found = any(isinstance(p, dict) and p.get('source_ref') == target.get('source_ref') and
                        set(p) == {'source_ref', 'quote'} and
                        (normalize_text(p.get('quote', '')) in target_quote or target_quote in normalize_text(p.get('quote', '')))
                        for p in predicted)
        if found:
            matched += 1
    return matched, len(expected)


def evaluate_case(case, run):
    reader, resources, _ = _sources(case)
    result = run.get('result')
    actual_items = result.get('items', []) if isinstance(result, dict) else []
    by_question = {x.get('question'): x for x in actual_items if isinstance(x, dict)}
    validation_error = None
    try:
        validate_final_items(actual_items, case['questions'], resources)
    except Exception as exc:
        validation_error = f'{type(exc).__name__}: {exc}'
    field_rows = {}
    totals = {'exact': 0, 'status_correct': 0, 'documented_values': 0,
              'documented_value_correct': 0, 'expected_evidence': 0,
              'matched_evidence': 0, 'predicted_quotes': 0, 'valid_quotes': 0}
    for gold in case['gold_items']:
        q = gold['question']
        actual = by_question.get(q)
        exact = _semantic_match(q, actual, gold)
        status_ok = isinstance(actual, dict) and actual.get('status') == gold['status']
        totals['exact'] += int(exact)
        totals['status_correct'] += int(status_ok)
        if gold['status'] == 'documented':
            totals['documented_values'] += 1
            totals['documented_value_correct'] += int(isinstance(actual, dict) and actual.get('status') == 'documented' and _matches_value(q, actual.get('value'), gold['value']))
        matched, expected = _evidence_recall(actual, gold)
        totals['matched_evidence'] += matched
        totals['expected_evidence'] += expected
        predicted_evidence = _evidence_list(actual)
        totals['predicted_quotes'] += len(predicted_evidence)
        valid = sum(1 for e in predicted_evidence if _evidence_valid(e, resources))
        totals['valid_quotes'] += valid
        field_rows[q] = {'gold': gold, 'actual': actual, 'exact': exact,
                         'status_correct': status_ok, 'evidence_matched': matched,
                         'evidence_expected': expected}
    return {'case_id': case['case_id'], 'field_rows': field_rows,
            'validation_error': validation_error,
            'schema_valid': validation_error is None,
            'complete': result is not None and len(by_question) == len(case['questions']),
            'totals': totals}


def _load_runs(root):
    result = {}
    for method in METHODS:
        result[method] = {}
        for model in MODELS:
            path = root / f'{method}_{model}.json'
            if path.exists():
                result[method][model] = {r['case_id']: r for r in json.loads(path.read_text(encoding='utf-8'))['results']}
            else:
                result[method][model] = {}
    return result


def _aggregate(cases_data, runs):
    output = {}
    for method in METHODS:
        output[method] = {}
        for model in MODELS:
            not_run = len(runs[method][model]) == 0
            case_evals = {}
            totals = {'exact': 0, 'status_correct': 0, 'documented_values': 0,
                      'documented_value_correct': 0, 'expected_evidence': 0,
                      'matched_evidence': 0, 'predicted_quotes': 0, 'valid_quotes': 0,
                      'completed': 0, 'schema_valid': 0, 'all_questions': 0,
                      'tokens': 0, 'seconds': 0, 'failures': 0, 'caps': 0, 'generation_calls': 0, 'order_followed_facts': 0, 'order_checked_facts': 0}
            for case in cases_data:
                run = runs[method][model].get(case['case_id'], {'result': None, 'generation': {}, 'failure': {'detail': 'run file missing'}})
                metrics = evaluate_case(case, run)
                case_evals[case['case_id']] = metrics
                for key in ('exact', 'status_correct', 'documented_values', 'documented_value_correct',
                            'expected_evidence', 'matched_evidence', 'predicted_quotes', 'valid_quotes'):
                    totals[key] += metrics['totals'][key]
                totals['completed'] += int(metrics['complete'])
                totals['schema_valid'] += int(metrics['schema_valid'])
                totals['all_questions'] += int(metrics['totals']['exact'] == len(case['questions']))
                run_gen = run.get('generation') or {}
                totals['tokens'] += run_gen.get('generated_tokens', 0)
                totals['seconds'] += run.get('elapsed_seconds', 0)
                totals['failures'] += int(run.get('failure') is not None)
                totals['caps'] += int(bool(run_gen.get('cap_reached')))
                totals['generation_calls'] += run.get('generation_calls', 0)
                detail = run.get('details') or {}
                totals['order_checked_facts'] += detail.get('order_checked_facts', 0)
                totals['order_followed_facts'] += detail.get('order_followed_facts', 0)
            totals['fields_total'] = len(cases_data) * len(cases_data[0]['questions'])
            totals['field_accuracy'] = totals['exact'] / totals['fields_total'] if totals['fields_total'] else 0
            totals['status_accuracy'] = totals['status_correct'] / totals['fields_total'] if totals['fields_total'] else 0
            totals['documented_value_accuracy'] = totals['documented_value_correct'] / totals['documented_values'] if totals['documented_values'] else 0
            totals['evidence_recall'] = totals['matched_evidence'] / totals['expected_evidence'] if totals['expected_evidence'] else 1
            totals['quote_validity'] = totals['valid_quotes'] / totals['predicted_quotes'] if totals['predicted_quotes'] else 1
            totals['all_questions'] = f'{totals["all_questions"]}/{len(cases_data)}'
            totals['not_run'] = not_run
            output[method][model] = {'summary': totals, 'cases': case_evals}
    return output


def render(root):
    root = Path(root)
    case_data = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
    runs = _load_runs(root)
    evaluation = _aggregate(case_data, runs)
    (root / 'evaluation.json').write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def esc(value):
        return html.escape(str(value))

    def pre(value):
        return '<pre>' + esc(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre>'

    def badge(ok):
        return '<span class="badge ' + ('ok' if ok else 'bad') + '">' + ('맞음' if ok else '불일치/누락') + '</span>'

    out = ['''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>S1 Summary typed fields · two models / single call / field order only</title><style>
*{box-sizing:border-box}body{margin:0;background:#eef3f8;color:#1c2d40;font:15px/1.65 system-ui,sans-serif}main{max-width:1900px;padding:24px;margin:auto}h1{font-size:29px}h2{font-size:22px}.card{background:white;border:1px solid #d6e1ee;border-radius:12px;margin:20px 0;padding:24px}.scroll{overflow-x:auto;padding-top:4px}table{border-collapse:collapse;width:100%;min-width:850px}th,td{border:1px solid #dce4ee;padding:11px;vertical-align:top;text-align:left}th{background:#e4eef9}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,Consolas,monospace;background:#f4f7fb;padding:12px;border-radius:6px;margin:8px 0}.compare{min-width:1350px;table-layout:fixed}.compare th,.compare td{width:33.333%}.badge{display:inline-block;padding:3px 8px;border-radius:5px;font-weight:700}.ok{background:#def2e4}.bad{background:#ffebe5}.pending{background:#e8edf2;color:#465564}.note{background:#fff4d9;border-left:4px solid #e4ad36;padding:12px 15px}.muted{color:#5d6c7c}.case{scroll-margin-top:12px}.question{font:600 15px ui-monospace,Consolas,monospace;margin:26px 0 8px}summary{padding:10px;background:#eaf0f8;cursor:pointer;font-weight:650}details{margin:12px 0}select{padding:9px;margin:5px}.hide{display:none!important}a{color:#195fb3}.metric{white-space:nowrap}
</style><main><h1>S1 Summary — GT 전수 검토 후 GPU 2·3 병렬 재실험</h1>
<p>오케스트레이터가 S1에서 한 번 전달하는 고정 질문 목록을 기준으로 8개 합성 사례를 재주석하고 평가했습니다. `assertion`을 없애고 예/아니요 항목은 `status=documented`와 Boolean `value`로 통일했습니다. 두 방식 모두 문서 전체를 받아 LLM을 정확히 한 번 호출합니다. 프롬프트는 필드 이름 나열 순서만 다릅니다: question → status → value → evidence / question → evidence → status → value. 이번 두 순서 사이에는 입력·수정 GT·검증·모델 환경·출력 토큰 상한이 같습니다. 이전 실행과 비교하면 GT 1개와 공통 상태 규칙을 수정했으므로, 이전 대비 변화 전체를 출력 순서의 효과로 해석하면 안 됩니다. 예전 두 단계 실험 결과는 포함하지 않습니다.</p>
<div class="card"><details><summary>질문형·공통 속성 규칙 보기</summary><h2>설계한 질문형</h2><div class="scroll"><table><tr><th>Question ID</th><th>형식</th><th>value schema</th><th>질문 범위와 의미 규칙</th></tr>''']
    from .history_s1_contract import QUESTION_CATALOG
    for question, spec in QUESTION_CATALOG.items():
        schema = spec.get('value_schema')
        schema_text = json.dumps(schema, ensure_ascii=False, indent=2) if isinstance(schema, (dict, list)) else str(schema)
        out.append('<tr><td><code>' + esc(question) + '</code></td><td>' + esc(spec['type']) + '</td><td><pre>' + esc(schema_text) + '</pre></td><td>' + esc(spec['scope']) + '<br>' + esc(spec['rules']) + '</td></tr>')
    out.append('''</table></div><p class="note"><b>레거시 질문 분해:</b> 계획서의 `recent_surgery_or_bleeding`은 수술과 출혈 중 한쪽만 기록된 경우를 단일 Boolean으로 정확히 나타낼 수 없어 `recent_surgery`, `recent_bleeding` 두 항목으로 확장했습니다. 항응고제·항혈소판제 사용 질문은 같은 Boolean 규칙을 사용합니다. 약 이름·용량은 이 질문의 `value`가 아니라 근거 인용에 남으며, 별도 질문으로 요청될 때 독립 필드가 되어야 합니다.</p>
<h2>의사결정에 연결할 때의 해석 범위</h2><p>이 평가는 계획서의 초기 S1 추출 질문을 대상으로 한 프로토타입 평가이며, 치료 적격성 규칙의 완성본은 아닙니다. LKW와 증상 발견 시각은 각각 별도 정보로 보존해야 합니다. AHA/ASA는 onset이 불명확하거나 wake-up stroke인 경우 LKW 이후 시간이 길어도 영상 기준 등으로 선별할 수 있는 경우를 설명하고, EMS 지침은 LKW와 symptom discovery를 따로 수집하도록 합니다. 따라서 LLM은 원문 시각·출처·정밀도와 명시된 불확실성만 추출하고, 시간 경계가 실제 rule에 어떻게 반영되는지는 임상팀이 승인한 deterministic rule이 결정해야 합니다. <a href="https://www.ahajournals.org/doi/10.1161/STR.0000000000000513" target="_blank" rel="noreferrer">AHA/ASA 2026 급성 허혈성 뇌졸중 지침</a> · <a href="https://www.stroke.org/-/media/Stroke-Files/EMS-Resources/EMS-Algorithm-Acute-Stroke-Triage-and-Routing.pdf?sc_lang=es" target="_blank" rel="noreferrer">AHA/ASA EMS 지침</a>.</p>
<p>현재 <code>anticoagulant_use</code>는 사용 여부만 나타냅니다. 실제 rule이 특정 약제, 용량, 마지막 복용 시각을 참조한다면 그 속성을 별도 질문/필드로 정의해야 합니다. 수술·출혈도 Boolean만으로 임상적으로 충분하다고 가정하지 않습니다. 따라서 이 실험의 점수는 “요청된 S1 질문의 추출” 성능이지, tPA 판단에 필요한 정보가 빠짐없이 갖춰졌다는 성능은 아닙니다.</p>
<h2>공통 속성 규칙</h2><p><code>documented</code>는 원문에 답이 기록되어 있다는 뜻입니다. 명시적 부정은 Boolean 질문에서 <code>value:false</code>입니다. <code>not_stated</code>는 모든 제공 문서를 검토해도 언급이 없는 경우로 <code>value:null</code>, 근거 없음입니다. 원문이 모름·확인 불가·미문진이라고 명시하면 <code>explicitly_unknown</code>에 근거를 둡니다. 서로 다른 답은 <code>conflicting</code>과 값별 근거가 붙은 <code>alternatives</code>로 보존합니다. 모델은 근거 있는 진술과 명시적 미언급 marker를 낼 수 있습니다. 미언급 marker는 value:null, evidence:[]이며 모든 필수 키가 있어야 합니다. 코드는 더 강한 문서·구조화 근거를 우선하고 최종 미언급 판정과 충돌 결합을 결정합니다.</p>
<p>인용의 원문 존재와 값에 대한 의미적 충분성은 별개입니다. 자동 점수는 인용이 입력 원문에 있고 GT 인용 구간과 겹치는지를 확인하며, 임상 전문가의 근거 타당성 판정을 대체하지 않습니다. 기록은 모두 합성 데이터이며 임상 성능 검증이나 외부 기관의 GT 승인을 의미하지 않습니다.</p></details></div>
<div class="card"><h2>전체 결과</h2><div class="scroll"><table><tr><th>방식</th><th>모델</th><th>성공 / 스키마 유효</th><th>status+value 정확</th><th>status 정확</th><th>documented value 정확</th><th>GT 근거 recall</th><th>입력과 일치하는 근거</th><th>모든 질문 정답 사례</th><th>실제 LLM 호출</th><th>필드 순서 준수</th><th>토큰</th><th>실행시간</th></tr>''')
    for method in METHODS:
        for model in MODELS:
            stat = evaluation[method][model]['summary']
            if stat.get('not_run'):
                out.append('<tr><td>' + esc(METHOD_NAMES[method]) + '</td><td>' + esc(MODEL_NAMES[model]) + '</td>' +
                           '<td colspan="11"><span class="badge pending">미실행 — 사용자 요청에 따라 실행 보류</span></td></tr>')
                continue
            out.append('<tr><td>' + esc(METHOD_NAMES[method]) + '</td><td>' + esc(MODEL_NAMES[model]) + '</td>' +
                       '<td>' + str(stat['completed']) + '/8 · ' + str(stat['schema_valid']) + '/8</td>' +
                       '<td><b>' + str(stat['exact']) + '/' + str(stat['fields_total']) + '</b> (' + f'{stat["field_accuracy"]:.1%}' + ')</td>' +
                       '<td>' + f'{stat["status_correct"]}/{stat["fields_total"]} ({stat["status_accuracy"]:.1%})' + '</td>' +
                       '<td>' + f'{stat["documented_value_correct"]}/{stat["documented_values"]} ({stat["documented_value_accuracy"]:.1%})' + '</td>' +
                       '<td>' + f'{stat["matched_evidence"]}/{stat["expected_evidence"]} ({stat["evidence_recall"]:.1%})' + '</td>' +
                       '<td>' + f'{stat["valid_quotes"]}/{stat["predicted_quotes"]} ({stat["quote_validity"]:.1%})' + '</td>' +
                       '<td>' + stat['all_questions'] + '</td><td>' + str(stat['generation_calls']) + '</td><td>' + f'{stat["order_followed_facts"]}/{stat["order_checked_facts"]}' + '</td><td>' + str(stat['tokens']) + '</td><td>' + f'{stat["seconds"]:.1f}s' + '</td></tr>')
    out.append('</table></div><p class="muted">각 항목 정확도는 질문별 `status`와 타입에 맞는 `value`를 비교하며, LKW는 kind·precision·정규화 시각을 비교합니다. 근거 일치와 입력 자료 내 출처 검증은 별도 지표입니다. `status=documented,value=true`와 `value=false`는 서로 다른 답으로 채점합니다.</p>')
    out.append('<details><summary>고정 실행 설정 및 질문 카탈로그</summary>' + pre(json.loads((root / 'manifest.json').read_text(encoding='utf-8'))) + pre(QUESTION_CATALOG) +
               '<h3>한 번 호출 프롬프트</h3>' + pre((root / 'direct_prompt.txt').read_text(encoding='utf-8')) +
               '<h3>인용 우선 순서 프롬프트 — 동일한 한 번 호출</h3>' + pre((root / 'evidence_first_prompt.txt').read_text(encoding='utf-8')) + '</details></div>')
    audit_path = root / 'comparison_audit.json'
    if audit_path.exists():
        out.append('<div class="card"><details><summary>비교 조건 검증 및 코드 검사 상태</summary>' +
                   pre(json.loads(audit_path.read_text(encoding='utf-8'))) + '</details></div>')

    out.append('<div class="card"><h2>순서 변경 전후 — 사례별 정답 필드 수</h2><p>각 칸은 6개 질문 중 맞춘 개수입니다. 검증 오류로 최종 결과 전체가 거부되면 0/6으로 표시됩니다. 인용 유효성 지표는 통과한 최종 결과의 근거만 대상으로 하므로 원시 출력 전체의 인용 정확도로 해석하지 마세요.</p><div class="scroll"><table><tr><th>사례</th><th>Qwen 기존</th><th>Qwen 인용 우선</th><th>Gemma 기존</th><th>Gemma 인용 우선</th></tr>')
    for case in case_data:
        out.append('<tr><td>' + esc(case['case_id']) + '</td>')
        for model in MODELS:
            for method in METHODS:
                metric = evaluation[method][model]['cases'][case['case_id']]
                run = runs[method][model].get(case['case_id'], {})
                failure = run.get('failure')
                out.append('<td><b>' + str(metric['totals']['exact']) + '/6</b>' +
                           ('<br><span class="bad">' + esc(failure.get('detail')) + '</span>' if failure else '') + '</td>')
        out.append('</tr>')
    out.append('</table></div></div>')

    out.append('<div class="card"><h2>사례별 정확도</h2><p>각 방식 아래에서 GT와 두 모델의 최종 출력 JSON을 나란히 비교합니다. 최종 저장 객체는 코드가 공통 순서로 구성하므로, 실제 모델의 생성 순서는 아래 raw 생성과 parsed_payload에서 확인하세요. 오류로 거부된 케이스는 전체 최종 결과가 없어 6개 필드 모두 실패로 집계됩니다. 따라서 이 점수에는 형식 검증의 영향도 포함됩니다. 사례 선택은 해당 사례만 펼쳐 봅니다.</p><label>사례 <select id="case">' + '<option value="all">전체</option>' + ''.join('<option value="' + esc(c['case_id']) + '">' + esc(c['case_id'] + ' — ' + c['purpose']) + '</option>' for c in case_data) + '</select></label>')
    for case in case_data:
        case_id = case['case_id']
        reader, resources, docs = _sources(case)
        out.append('<section class="card case" data-case="' + esc(case_id) + '"><h2>' + esc(case_id + ' · ' + case['purpose']) + '</h2><p>' + esc(case['annotation_note']) + '</p>')
        out.append('<details><summary>S1 요청 JSON 및 확장된 질문 ID</summary>' + pre(case['request']) + pre({'expanded_question_ids': case['questions']}) + '</details>')
        for ref, document in docs.items():
            out.append('<h3>' + esc(ref) + '</h3><p class="muted">saved_time: ' + esc(document.get('saved_time')) + '</p><pre>' + esc(document['text']) + '</pre>')
        structured = {k: v for k, v in resources.items() if not k.startswith('document:')}
        if structured:
            out.append('<details><summary>오케스트레이터가 지정한 구조화 입력 (코드 처리)</summary>' + pre(structured) + '</details>')
        out.append('<details><summary>재설계한 GT 전체 JSON</summary>' + pre(case['gold_items']) + '</details>')
        for method in METHODS:
            out.append('<h3>' + esc(METHOD_NAMES[method]) + '</h3><div class="scroll"><table class="compare"><tr><th>Question / GT</th>' + ''.join('<th>' + esc(MODEL_NAMES[m]) + '</th>' for m in MODELS) + '</tr>')
            run_evals = {m: evaluation[method][m]['cases'].get(case_id) for m in MODELS}
            for gold in case['gold_items']:
                q = gold['question']
                cells = ['<b>' + esc(q) + '</b>' + pre(gold)]
                for model in MODELS:
                    metrics = run_evals[model]
                    if evaluation[method][model]['summary'].get('not_run'):
                        cells.append('<span class="badge pending">미실행</span>' + pre({'execution_status': '사용자 요청에 따라 아직 실행하지 않음'}))
                        continue
                    row = metrics['field_rows'].get(q) if metrics else None
                    actual = row['actual'] if row else None
                    cells.append((badge(row['exact']) if row else badge(False)) + pre(actual if actual is not None else {'error': (runs[method][model].get(case_id, {}).get('failure') or {}).get('detail', '실행 결과 없음')}) +
                                 ('<p class="muted">GT 인용 구간 일치: ' + str(row['evidence_matched']) + '/' + str(row['evidence_expected']) + '</p>' if row else ''))
                    run_detail = runs[method][model].get(case_id, {}).get('details') or {}
                    parsed = run_detail.get('parsed_payload') or {}
                    candidates = parsed.get('facts', []) if isinstance(parsed, dict) else []
                    if actual is None and isinstance(candidates, list):
                        candidates = [f for f in candidates if isinstance(f, dict) and f.get('question') == q]
                        if candidates:
                            cells[-1] += '<p><b>검증 전 모델 후보 — 최종 저장 결과 아님</b></p>' + pre(candidates)
                out.append('<tr><td>' + cells[0] + '</td>' + ''.join('<td>' + x + '</td>' for x in cells[1:]) + '</tr>')
            out.append('</table></div>')
        for method in METHODS:
            for model in MODELS:
                run = runs[method][model].get(case_id)
                if not run:
                    continue
                generation = run.get('generation') or {}
                out.append('<details><summary>' + esc(METHOD_NAMES[method] + ' · ' + MODEL_NAMES[model]) + ' — raw 생성 (' + str(generation.get('generated_tokens', 0)) + ' tokens)</summary>' +
                           '<p>실행시간 ' + f'{run.get("elapsed_seconds", 0):.1f}s' + ' · cap_reached=' + str(generation.get('cap_reached')) + ' · 실패=' + esc(run.get('failure')) + '</p>' +
                           pre(generation) + pre(run.get('details')) + pre(run.get('result')) + '</details>')
        out.append('</section>')
    out.append('''</div></main><script>
const filter=document.getElementById('case');
function apply(){document.querySelectorAll('.case').forEach(x=>x.classList.toggle('hide',filter.value!=='all'&&x.dataset.case!==filter.value));}
filter.addEventListener('change',apply);document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',()=>{filter.value='all';apply();}));
</script></html>''')
    path = root / 'comparison.html'
    rendered = ''.join(out)
    review_path = root / 'gt_review.json'
    if review_path.exists():
        from .history_s1_gt_audit import PRIOR_ROOT
        review = json.loads(review_path.read_text(encoding='utf-8'))
        prior_runs = _load_runs(PRIOR_ROOT)
        rescored = _aggregate(case_data, prior_runs)
        published = json.loads((PRIOR_ROOT / 'evaluation.json').read_text(encoding='utf-8'))
        (root / 'prior_outputs_GT_only_rescore.json').write_text(json.dumps(rescored, ensure_ascii=False, indent=2), encoding='utf-8')
        card = ['<div class="card"><h2>GT 전수 검토: 48개 중 1개 수정</h2><p>입력 원문은 그대로 두고 48개 정답을 질문 의미와 원문에 대조했습니다. 두 모델의 공통 오답도 다시 살폈습니다. 아래 검토는 에이전트의 합성 사례 검토이며 임상 전문가의 독립 판정은 아닙니다.</p><table><tr><th>원문의 의미</th><th>status</th><th>value</th><th>evidence</th></tr><tr><td>과거 뇌졸중 병력이 없다</td><td>documented</td><td>false</td><td>명시적 부정 인용</td></tr><tr><td>병력을 문진에서 다루지 않았다 / 확인하지 못했다</td><td>explicitly_unknown</td><td>null</td><td>미문진·미확인 인용</td></tr><tr><td>관련 항목을 전혀 언급하지 않는다</td><td>not_stated</td><td>null</td><td>[]</td></tr></table>']
        for row in review['all_field_reviews']:
            if row['decision'] == 'corrected':
                card.append('<h3>' + esc(row['case_id'] + ' / ' + row['question']) + '</h3><p>' + esc(row['reason']) + '</p><div class="scroll"><table><tr><th>기존 GT</th><th>수정 GT</th></tr><tr><td>' + pre(row['previous_GT']) + '</td><td>' + pre(row['reviewed_GT']) + '</td></tr></table></div>')
        card.append('<h3>공통 규칙도 수정한 부분</h3><p>5번의 recent_bleeding=not_stated는 GT가 맞았습니다. 예전에는 모델이 이 상태를 직접 출력했다는 이유로 거부했습니다. 이제 완전한 네 키와 null/빈 근거 형식이면 수용합니다. 단, 미문진은 explicitly_unknown이며, 필수 키 생략과 원문을 바꿔 쓴 인용은 계속 오류입니다. 약물 질문에서 무조건 null 금지로 읽힐 수 있던 설명도 다른 질문과 같은 상태별 규칙으로 통일했습니다.</p>')
        card.append('<details><summary>두 모델의 공통 오답을 원문으로 재검토한 내역</summary>' + pre(review['prior_both_models_wrong']) + '</details><details><summary>48개 GT 전체 검토표</summary><div class="scroll"><table><tr><th>사례 / 질문</th><th>판정</th><th>원문 기준 이유</th><th>확정 GT</th></tr>')
        for row in review['all_field_reviews']:
            card.append('<tr><td>' + esc(row['case_id'] + ' / ' + row['question']) + '</td><td>' + esc(row['decision']) + '</td><td>' + esc(row['reason']) + '</td><td>' + pre(row['reviewed_GT']) + '</td></tr>')
        card.append('</table></div></details><h3>GT 수정만으로 바뀐 점수와 실제 재실행 점수</h3><p>중간 열은 이전 최종 JSON을 그대로 두고 GT만 수정해 재채점한 값입니다. 마지막 열은 공통 규칙까지 수정한 새 추론 결과입니다. 모두 48개 필드 기준이며, 이전 파이프라인에서 거부되어 저장 결과가 없던 사례를 복구해 채점하지는 않습니다.</p><table><tr><th>모델 / 순서</th><th>이전 발표 점수</th><th>같은 출력 + GT만 수정</th><th>이번 실제 재실행</th></tr>')
        for model in MODELS:
            for method in METHODS:
                card.append('<tr><td>' + esc(MODEL_NAMES[model] + ' / ' + METHOD_NAMES[method]) + '</td>' + ''.join('<td>' + str(e[method][model]['summary']['exact']) + '/48</td>' for e in (published, rescored, evaluation)) + '</tr>')
        card.append('</table></div>')
        rendered = rendered.replace('<div class="card"><h2>전체 결과</h2>', ''.join(card) + '<div class="card"><h2>전체 결과</h2>', 1)
    path.write_text(rendered, encoding='utf-8')
    return evaluation, path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    args = parser.parse_args()
    evaluation, path = render(args.root)
    print(json.dumps({'html': str(path), 'summary': {method: {model: data['summary'] for model, data in values.items()} for method, values in evaluation.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
