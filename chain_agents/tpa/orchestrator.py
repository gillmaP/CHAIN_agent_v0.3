"""Opt-in integration for the pinned CHAIN reference Engine, not an Agent result.

Import only in a CHAIN Host. The standalone Agent has no CHAIN/Temporal dependency.
"""
import copy
from chain_demo.engine import Engine
from chain_demo.agent_requests import scope_snapshot
from chain_demo.contracts import validate_hitl_request, validate_hitl_resume_shape
from chain_demo.validation import canonical_hash, timestamp

CHECKPOINT = 'HITL_2_THROMBOLYSIS'
REFERENCE = 'tpa_decision_support.final'


def ct_ready(snapshot):
    facts = snapshot['facts']
    names = ('ncct_completed','ncct_order_id','ct_order_id')
    if any(name not in facts or facts[name]['status'] not in {'AVAILABLE','COMPLETED','CONFIRMED','CONSISTENT'} for name in names):
        return False
    order = facts['ct_order_id']['value']
    return facts['ncct_completed']['value'] is True and isinstance(order, str) and bool(order.strip()) and order == facts['ncct_order_id']['value']


def validate_source_only(request, snapshot, results):
    if request['checkpoint'] != CHECKPOINT or request['result_ids'] or results or not ct_ready(snapshot):
        raise ValueError('Source-only review requires matching completed NCCT and no fabricated Agent results')


class EvidenceFirstEngine(Engine):
    def __init__(self, *args, evidence_first_enabled=True, **kwargs):
        if type(evidence_first_enabled) is not bool:
            raise ValueError('evidence_first_enabled must be boolean')
        self.evidence_first_enabled = evidence_first_enabled
        self.tpa_execution = {}
        self.review_refresh_commands = {}
        super().__init__(*args, **kwargs)

    def _consume(self, consumer):
        if not self.evidence_first_enabled:
            return super()._consume(consumer)
        if not consumer.get('cross_state') and consumer['generation'] != self.generation:
            return
        if consumer['kind'] == 'agent' and consumer['alias'] == 'tpa_decision_support':
            # Current facts are sufficient input. A02/model success is not a gate.
            scope = self.wf['agents'][consumer['alias']]['scopes'][consumer['mode']]
            snapshot = scope_snapshot(self.context.snapshot(), scope)
            self._start_agent(consumer['alias'], consumer['mode'], snapshot, consumer, 'agent')
            return
        if consumer['kind'] != 'hitl' or consumer['checkpoint'] != CHECKPOINT:
            return super()._consume(consumer)
        if self.wf['hitl_checkpoints'][CHECKPOINT]['after'] != REFERENCE:
            raise ValueError('Evidence-first adapter only supports the declared tPA final checkpoint')
        wait = self.hitl_waits.get(CHECKPOINT)
        if wait and wait['generation'] == self.generation and wait['status'] in {'WAITING','REOPENING','FAILED'}:
            if wait['status'] != 'REOPENING' or consumer.get('resume_token') != wait.get('resume_token'):
                return
            if any(seq <= wait['through_sequence'] for seq in self._source_positions.values()):
                self._defer(consumer)
                return
        scope = self.wf['agents']['tpa_decision_support']['scopes']['final']
        snapshot = scope_snapshot(self.context.snapshot(), scope)
        previous = self.open_hitl.get(CHECKPOINT)
        if previous and previous['status'] == 'OPEN':
            if previous['snapshot']['snapshot_id'] == snapshot['snapshot_id']:
                return
            previous.update(status='INVALIDATED', invalidated_reason='SCOPED_INPUT_CHANGED')
            self._log('HITL_INVALIDATED', checkpoint=CHECKPOINT, request_id=previous['request']['request_id'], reason='SCOPED_INPUT_CHANGED')
        if not ct_ready(snapshot):
            return
        self._open_evidence_first(snapshot)
        if consumer.get('resume_token'):
            self._finish_hitl_resume(CHECKPOINT)

    def _open_evidence_first(self, snapshot):
        spec = self.wf['hitl_checkpoints'][CHECKPOINT]
        record = self.results.get(REFERENCE)
        valid = record and record['generation'] == self.generation and record['snapshot']['snapshot_id'] == snapshot['snapshot_id']
        results = [copy.deepcopy(record['output'])] if valid else []
        refs = {canonical_hash(ref):copy.deepcopy(ref) for fact in snapshot['facts'].values()
                for ref in fact.get('dependencies',[fact['source_ref']])}
        request = {'contract_schema':'chain-hitl-request/v0.3', 'request_id':self._id('hitl'),
            'checkpoint':CHECKPOINT, 'evidence_snapshot_id':snapshot['snapshot_id'],
            'dependencies':[refs[key] for key in sorted(refs)], 'result_ids':[r['request_id'] for r in results],
            **{key:copy.deepcopy(spec[key]) for key in ('roles','options','required_confirmations','confirmations_on_decisions','question')}}
        if not results:
            request['evidence_mode'] = 'SOURCE_SNAPSHOT'
        validate_hitl_request(request, snapshot, results)
        review = {'status':'OPEN','state':self.state,'generation':self.generation,
                  'request':request,'snapshot':copy.deepcopy(snapshot),'results':results,'requested_at':self.now}
        if self.source_documents_enabled:
            review['source_documents'] = self.context.freeze_source_documents(request, snapshot, frozen_at=self.now)
        self.open_hitl[CHECKPOINT] = review
        self.hitl_history[request['request_id']] = review
        self._log('HITL_REQUESTED', checkpoint=CHECKPOINT, request_id=request['request_id'],
                  evidence_snapshot_id=snapshot['snapshot_id'], result_ids=request['result_ids'], evidence_first=True)

    def _complete_agent(self, command, reply):
        super()._complete_agent(command, reply)
        if command['alias'] == 'tpa_decision_support' and self._latest.get(f"{command['alias']}.{command['mode']}") == command['id']:
            accepted = command['id'] in self.agent_outputs
            self.tpa_execution[command['mode']] = {'request_id':command['id'],
                'input_snapshot_id':command['job']['snapshot']['snapshot_id'],
                'status':'SUCCESS' if accepted else 'FAILED',
                'error':None if accepted else str(reply.get('error','RESULT_REJECTED'))}
        # An Agent completion never rewrites an already open decision bundle.

    def refresh_tpa_review(self, request, now):
        self._time(now)
        try:
            validate_hitl_resume_shape(request)
            if timestamp(request['requested_at']) > timestamp(now):
                raise ValueError('Refresh timestamp is in the future')
            existing = self.review_refresh_commands.get(request['command_id'])
            if existing:
                if existing != request:
                    raise ValueError('Conflicting refresh command ID')
                return self._commands()
            current = self.open_hitl.get(CHECKPOINT)
            if not self.evidence_first_enabled or not current or current['status'] != 'OPEN' or self.terminal:
                raise ValueError('No open tPA review')
            if current['request']['request_id'] != request['prior_request_id']:
                raise ValueError('Refresh refers to a superseded request')
            if request['actor']['role'] not in current['request']['roles']:
                raise ValueError('Unauthorized refresh role')
            current.update(status='INVALIDATED', invalidated_reason='EXPLICIT_REVIEW_REFRESH')
            self.review_refresh_commands[request['command_id']] = copy.deepcopy(request)
            self._log('HITL_INVALIDATED',checkpoint=CHECKPOINT,request_id=request['prior_request_id'],reason='EXPLICIT_REVIEW_REFRESH')
            self._consume({'kind':'hitl','checkpoint':CHECKPOINT,'generation':self.generation})
        except (ValueError, KeyError, TypeError) as error:
            self._reject_input('HITL_REFRESH_REJECTED',str(error),command_id=request.get('command_id') if isinstance(request,dict) else None)
        return self._commands()

    def snapshot(self):
        result = super().snapshot()
        result['tpa_execution'] = copy.deepcopy(self.tpa_execution)
        for command in self.pending.values():
            if command.get('alias') == 'tpa_decision_support' and command.get('purpose') == 'agent':
                if self._latest.get(f"tpa_decision_support.{command['mode']}") == command['id']:
                    result['tpa_execution'][command['mode']] = {'status':'RUNNING','request_id':command['id'],
                        'input_snapshot_id':command['job']['snapshot']['snapshot_id'],'error':None}
        return result
