"""Eight new synthetic Summary cases, independently annotated before inference."""
QUESTIONS=['anticoagulant_use','antiplatelet_use','recent_surgery_or_bleeding','previous_stroke','lkw_records']

def fact(q,a,ref,quote,value=None):return dict(question=q,assertion=a,value=value,source_ref=ref,quote=quote)
def expected(anti,platelet,surgery,history,lkw):
    return {q:{'status':x[0],'value':x[1]} for q,x in zip(QUESTIONS,[anti,platelet,surgery,history,lkw])}
NO=('NO_EVIDENCE',False);PAST_NO=('NONE_DOCUMENTED',False);YES=('PRESENT',True);UNKNOWN=('UNKNOWN',None);UNCERTAIN=('UNCERTAIN',None)

def cases():
 out=[]
 def add(cid,purpose,texts,gold,final,structured=None,note=''):
  pid='SYN-'+cid;eid='ENC-'+cid
  refs=[];responses={}
  for i,text in enumerate(texts):
   ref=f'document:{cid}-{i+1}@1';refs.append(ref)
   responses[f'GET /documents/{cid}-{i+1}?version=1']={'document_id':f'{cid}-{i+1}','version':1,'patient_id':pid,'encounter_id':eid,'document_type':'ED_INITIAL_NOTE' if i==0 else 'ED_TRIAGE_NOTE','status':'CURRENT','saved_time':'2026-10-08T19:30:00+09:00','text':text,'provenance':{'source_system':'SYNTHETIC_EMR','source_record_id':f'{cid}-{i+1}'}}
  if structured:
   for ref,endpoint,data in structured:
    refs.insert(0,ref);responses[f'GET /patients/{pid}/{endpoint}']={'patient_id':pid,'as_of':'2026-10-08T19:00:00+09:00',**data}
  gs=[]
  for q,a,doc_index,quote,v in gold:gs.append(fact(q,a,f'document:{cid}-{doc_index}@1',quote,v))
  out.append({'case_id':cid,'purpose':purpose,'annotation_note':note,'request':{'episode_id':'EP-'+cid,'encounter_id':eid,'patient_id':pid,'trigger':{'state_enter':'S1'},'input_references':refs,'questions':QUESTIONS.copy()},'api_responses':responses,'gold_facts':gs,'gold_final':final})
 add('01_positive_use','항응고제·항혈소판제 구분, 과거 뇌졸중, 두 출처 LKW',[
  '2026-10-08. 환자는 현재 항응고제 apixaban 5 mg bid를 복용 중이다. 항혈소판제로 아스피린 100mg qd도 현재 복용한다. 최근 6개월 수술과 출혈은 모두 없었다. 환자는 2021년 뇌졸중 병력이 있다. 마지막 정상 확인 시각은 오늘 09:10이다. 증상 발견은 10:00이다.',
  '2026-10-08 간호기록. 딸에게 확인한 마지막 정상 시각은 오늘 09:10이다. 증상 발견 10:00.'],[
  ('anticoagulant_use','present',1,'현재 항응고제 apixaban 5 mg bid를 복용 중이다','apixaban 5 mg bid'),
  ('antiplatelet_use','present',1,'항혈소판제로 아스피린 100mg qd도 현재 복용한다','아스피린 100mg qd'),
  ('recent_surgery_or_bleeding','absent',1,'최근 6개월 수술과 출혈은 모두 없었다',None),
  ('previous_stroke','present',1,'환자는 2021년 뇌졸중 병력이 있다',None),
  ('lkw_records','present',1,'마지막 정상 확인 시각은 오늘 09:10이다','2026-10-08T09:10:00+09:00'),
  ('lkw_records','present',2,'마지막 정상 시각은 오늘 09:10이다','2026-10-08T09:10:00+09:00')],expected(YES,('PRESENT','aspirin 100 mg qd'),NO,YES,('CONSISTENT','2026-10-08T09:10:00+09:00')))
 add('02_explicit_unknown','명시적 모름을 없음으로 바꾸지 않기',[
  '환자는 항응고제 복용 여부를 모르며 확인 불가하다. 항혈소판제 복용 여부도 모른다. 최근 수술이나 출혈이 있었는지는 확인할 수 없다. 과거 뇌졸중 병력 여부는 알 수 없다. 마지막 정상 시각은 환자와 보호자 모두 모른다.'],[
  ('anticoagulant_use','unknown',1,'항응고제 복용 여부를 모르며 확인 불가하다',None),
  ('antiplatelet_use','unknown',1,'항혈소판제 복용 여부도 모른다',None),
  ('recent_surgery_or_bleeding','unknown',1,'최근 수술이나 출혈이 있었는지는 확인할 수 없다',None),
  ('previous_stroke','unknown',1,'과거 뇌졸중 병력 여부는 알 수 없다',None),
  ('lkw_records','unknown',1,'마지막 정상 시각은 환자와 보호자 모두 모른다',None)],expected(UNCERTAIN,UNCERTAIN,UNCERTAIN,UNCERTAIN,UNKNOWN),note='현재 최종 결합 계약은 unknown 진술을 일반 항목에서 UNCERTAIN, LKW에서 UNKNOWN으로 표현한다. 원문 추출의 unknown은 별도로 검사한다.')
 add('03_family_current','아버지 과거력·현재 의심 진단과 환자 과거력 분리',[
  '2026-10-08. 아버지는 과거 뇌졸중 병력이 있다. 이번 환자의 현재 진단은 possible acute ischemic stroke이다. 환자 개인의 과거 뇌졸중 병력은 이번 문진에서 다루지 않았다. 현재 항응고제와 항혈소판제는 모두 복용하지 않는다. 최근 수술 및 출혈은 모두 없었다. 오늘 마지막 정상 확인은 06:00이고, 증상 발견은 07:30이다.'],[
  ('anticoagulant_use','absent',1,'현재 항응고제와 항혈소판제는 모두 복용하지 않는다',None),
  ('antiplatelet_use','absent',1,'현재 항응고제와 항혈소판제는 모두 복용하지 않는다',None),
  ('recent_surgery_or_bleeding','absent',1,'최근 수술 및 출혈은 모두 없었다',None),
  ('lkw_records','present',1,'오늘 마지막 정상 확인은 06:00','2026-10-08T06:00:00+09:00')],expected(NO,NO,NO,UNKNOWN,('RECORDED','2026-10-08T06:00:00+09:00')),note='환자 과거력 미문진은 unknown을 명시한 진술이 아니라 제공 정보 부재이다. previous_stroke fact를 만들지 않는다.')
 add('04_conflicting_sources','동일 현재 복용 여부·LKW에 대한 두 출처의 상충',[
  '2026-10-08. 현재 복용약 확인: 환자는 오늘도 항응고제 warfarin을 복용 중이라고 진술했다. 항혈소판제는 현재 복용하지 않는다고 한다. 최근 수술과 출혈은 모두 없었다. 과거 뇌졸중 병력은 없다. 이번 사건의 마지막 정상 시각은 오늘 09:10이라고 환자가 말한다.',
  '2026-10-08. 동일 사건 보호자 확인: 보호자는 환자가 현재 항응고제를 전혀 복용하지 않는다고 진술한다. 보호자는 이번 사건의 마지막 정상 시각이 오늘 09:40이라고 진술한다. 어느 진술이 맞는지는 아직 결정하지 못했다.'],[
  ('anticoagulant_use','present',1,'환자는 오늘도 항응고제 warfarin을 복용 중이라고 진술했다','warfarin'),
  ('anticoagulant_use','absent',2,'환자가 현재 항응고제를 전혀 복용하지 않는다고 진술한다',None),
  ('antiplatelet_use','absent',1,'항혈소판제는 현재 복용하지 않는다고 한다',None),
  ('recent_surgery_or_bleeding','absent',1,'최근 수술과 출혈은 모두 없었다',None),
  ('previous_stroke','absent',1,'과거 뇌졸중 병력은 없다',None),
  ('lkw_records','present',1,'마지막 정상 시각은 오늘 09:10이라고 환자가 말한다','2026-10-08T09:10:00+09:00'),
  ('lkw_records','present',2,'마지막 정상 시각이 오늘 09:40이라고 진술한다','2026-10-08T09:40:00+09:00')],expected(('CONFLICTING',None),NO,NO,PAST_NO,('CONFLICTING',None)),note='현재 두 출처를 보존한다. 어느 한쪽으로 덮어쓰거나 불확실하다는 이유로 구체적 후보를 지우지 않는다.')
 out[-1]['gold_final']['anticoagulant_use']['alternatives']=[True,False]
 out[-1]['gold_final']['lkw_records']['alternatives']=['2026-10-08T09:10:00+09:00','2026-10-08T09:40:00+09:00']
 add('05_external_vs_local','본원 목록에 없어도 타원 복용·수술 진술을 유지',[
  '2026-10-08. 본원 처방 목록에는 없지만 현재 타원 처방 항응고제 rivaroxaban을 매일 복용 중이라고 환자와 딸이 확인했다. 과거 apixaban은 중단했고 현재는 rivaroxaban만 복용한다. 항혈소판제는 현재 복용하지 않는다. 2주 전 타원에서 수술을 받았다고 한다. 과거 뇌졸중이나 TIA는 없었다. 마지막 정상 확인은 오늘 11:45이다.'],[
  ('anticoagulant_use','present',1,'현재 타원 처방 항응고제 rivaroxaban을 매일 복용 중이라고 환자와 딸이 확인했다','rivaroxaban 매일'),
  ('antiplatelet_use','absent',1,'항혈소판제는 현재 복용하지 않는다',None),
  ('recent_surgery_or_bleeding','present',1,'2주 전 타원에서 수술을 받았다고 한다',None),
  ('previous_stroke','absent',1,'과거 뇌졸중이나 TIA는 없었다',None),
  ('lkw_records','present',1,'마지막 정상 확인은 오늘 11:45이다','2026-10-08T11:45:00+09:00')],expected(YES,NO,YES,PAST_NO,('RECORDED','2026-10-08T11:45:00+09:00')),structured=[
  ('medication:active','medications?status=active',{'coverage':'본원 활성 처방만 제공, 타원 DUR 미연동','medications':[]}),
  ('condition:problem_list','conditions',{'conditions':[{'code':'I63.9','category':'ENCOUNTER_DIAGNOSIS','status':'PROVISIONAL'}]}),
  ('encounter_history:6m','encounters?months=6',{'window_months':6,'encounters':[{'encounter_id':'LOCAL-OLD','surgery':False,'bleeding_event':False,'procedures':[]}]})],note='본원에서 찾지 못함은 명시적 부정 진술이 아니다. 타원 진술과 충돌로 만들지 않는다.')
 add('06_partial_negation','수술만 부정했을 때 출혈까지 부정하지 않기, 대략적 LKW',[
  '2026-10-08. 항응고제와 항혈소판제는 현재 모두 복용하지 않는다. 최근 수술은 없었다. 출혈 여부는 문진하지 않았다. 과거 뇌졸중 병력은 없다. 마지막 정상은 오늘 15시쯤으로 추정되며 정확한 시각은 확인할 수 없다.'],[
  ('anticoagulant_use','absent',1,'항응고제와 항혈소판제는 현재 모두 복용하지 않는다',None),
  ('antiplatelet_use','absent',1,'항응고제와 항혈소판제는 현재 모두 복용하지 않는다',None),
  ('previous_stroke','absent',1,'과거 뇌졸중 병력은 없다',None),
  ('lkw_records','uncertain',1,'마지막 정상은 오늘 15시쯤으로 추정되며 정확한 시각은 확인할 수 없다',None)],expected(NO,NO,UNKNOWN,PAST_NO,UNKNOWN),note='현재 프롬프트대로 수술과 출혈 모두 부정되지 않으면 combined absent fact를 만들지 않는다. 대략적 LKW는 uncertain/null이다.')
 add('07_silent_records','관련 정보가 전혀 없을 때 사실을 만들어내지 않기',[
  '2026-10-08 18:10 응급실 기록. 환자는 현재 말이 어눌하다. 활력징후 BP 150/90 mmHg. CT 촬영을 준비 중이다.',
  '2026-10-08 18:20 간호기록. 정맥로 확보 완료. 보호자에게 대기 장소 안내.'],[],expected(UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN,UNKNOWN),note='모든 문서를 reviewed_documents에 넣되 facts는 빈 배열이다. 증상·문서 시각을 LKW로 바꾸지 않는다.')
 add('08_alias_midnight','ASA 동의어, TIA 과거력, 날짜 경계 LKW, 출혈만 양성',[
  '2026-10-08 초진. 현재 항응고제는 복용하지 않는다. 항혈소판제로 ASA(아스피린) 100mg을 1일 1회 복용한다. 최근 수술은 없었지만 어제 출혈이 있었다. 환자 본인은 2017년 TIA 병력이 있다. 마지막 정상은 전날 23:50 딸과 전화통화할 때였다. 오늘 00:20에 증상을 발견했다.',
  '2026-10-08 간호기록. LKW는 2026-10-07 23:50으로 보호자에게 확인했다. 증상 발견은 2026-10-08 00:20이다.'],[
  ('anticoagulant_use','absent',1,'현재 항응고제는 복용하지 않는다',None),
  ('antiplatelet_use','present',1,'항혈소판제로 ASA(아스피린) 100mg을 1일 1회 복용한다','ASA 100mg 1일 1회'),
  ('recent_surgery_or_bleeding','present',1,'최근 수술은 없었지만 어제 출혈이 있었다',None),
  ('previous_stroke','present',1,'환자 본인은 2017년 TIA 병력이 있다',None),
  ('lkw_records','present',1,'마지막 정상은 전날 23:50 딸과 전화통화할 때였다','2026-10-07T23:50:00+09:00'),
  ('lkw_records','present',2,'LKW는 2026-10-07 23:50으로 보호자에게 확인했다','2026-10-07T23:50:00+09:00')],expected(NO,('PRESENT','aspirin 100 mg qd'),YES,YES,('CONSISTENT','2026-10-07T23:50:00+09:00')))
 return out
