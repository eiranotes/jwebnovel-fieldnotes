"""Request, sampled-feature and immutable trace contracts; no model-estimated rewards."""
from __future__ import annotations
import hashlib
import math
from datetime import datetime
from pathlib import Path
from preference_state import digest, load, save, state_lock, code_revision, SCORING_COHORT_ID
from rebuild_work_index import canonical

CONTRACT_VERSION = '2.0'
ROOT = Path(__file__).resolve().parent.parent


def request_hash(request: dict) -> str:
    validate_request(request)
    return digest(request)


def validate_request(request: dict) -> None:
    allowed={'context_id','profile_id','intent','hard_filters','soft_preferences','reference_works','anti_reference_works','explicit_dimensions','analysis_confirmed','review_budget','minimum_base_score','length_exception','sampling_plan','scout_lanes','revisit'}
    if isinstance(request,dict) and set(request)-allowed:
        raise ValueError('unknown/private fields in public request snapshot')
    if not isinstance(request, dict) or not request.get('context_id') or not request.get('profile_id'):
        raise ValueError('frozen request requires context_id and profile_id')
    if not isinstance(request.get('hard_filters'), dict):
        raise ValueError('hard_filters must be explicit, including empty lists')
    if request.get('analysis_confirmed') is not True or not isinstance(request.get('explicit_dimensions'), list):
        raise ValueError('review the request/fingerprint and declare explicit_dimensions before ranking')
    if request['hard_filters'].get('min_chars') is not None:
        finite_number(request['hard_filters']['min_chars'],1,1e12,'min_chars')
    if not isinstance(request.get('length_exception',{}),dict):
        raise ValueError('length_exception must be an object')
    finite_number(request.get('minimum_base_score',60),0,100,'minimum_base_score')
    budget=request.get('review_budget',5)
    if isinstance(budget,bool) or not isinstance(budget,int) or budget<0:
        raise ValueError('review_budget must be a nonnegative integer')
    if any(not isinstance(x, str) or not x.strip() for x in request['explicit_dimensions']):
        raise ValueError('invalid explicit dimension')


def protected_dimensions(request: dict) -> set[str]:
    protected = set(request['explicit_dimensions'])
    # Structured and common explicit phrasing are protected even if a worker misses a dimension.
    text = str(request.get('intent') or '')
    if any(x in text for x in ('느린','느리','빠른','빠르','정치극')): protected.add('pacing')
    soft = request.get('soft_preferences') or {}
    if isinstance(soft, dict):
        protected.update(k for k,v in soft.items() if v and k in {'pacing','protagonist','romance','worldbuilding','tone','prose','characters'})
    if (request.get('hard_filters') or {}).get('genres'):
        protected.update(('genre','romance'))
    return protected


def finite_number(value, lo: float, hi: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{name} must be a finite number in [{lo}, {hi}]')
    return float(value)


def features(candidate: dict) -> list[dict]:
    raw = candidate.get('preference_features', [])
    if not isinstance(raw, list): raise ValueError('preference_features must be an array of objects')
    rows=[]; seen=set()
    for feature in raw:
        if not isinstance(feature,dict): raise ValueError('feature must be an object with sample evidence')
        key=feature.get('atom')
        if not isinstance(key,str) or not key or key in seen: raise ValueError('empty or duplicate atom feature')
        seen.add(key)
        value=finite_number(feature.get('value'),-1,1,'feature value')
        confidence=finite_number(feature.get('confidence'),0,1,'feature confidence')
        if not feature.get('evidence') or not feature.get('sample_id'):
            raise ValueError('feature requires exact sample quotation and sample_id')
        rows.append({**feature,'atom':key,'value':value,'confidence':confidence})
    return rows


def eligibility(candidate: dict, request: dict) -> tuple[bool,str]:
    receipt=candidate.get('eligibility_receipt') or {}
    if candidate.get('eligible') is not True: return False,'eligibility_not_passed'
    if receipt.get('request_hash') != request_hash(request) or receipt.get('candidate_key') != canonical(candidate):
        return False,'receipt_identity_mismatch'
    filters=request['hard_filters'];checks=receipt.get('checks') or {}
    minimum=filters.get('min_chars') if filters.get('min_chars') is not None else 300000
    try: length=finite_number(candidate.get('length_chars'),0,1e12,'length_chars')
    except ValueError:return False,'unknown_length'
    underlength=length<minimum
    exception=request.get('length_exception') or {}
    explicit=exception.get('explicit_minimum', filters.get('min_chars') is not None)
    fit=checks.get('length_exception_fit') or {}
    allowed_exception=(underlength and minimum==300000 and exception.get('enabled') is True
        and explicit is False and candidate.get('length_exception') is True
        and fit.get('status')=='pass' and fit.get('evidence') and fit.get('source_url'))
    if underlength and not allowed_exception:return False,'length'
    # The min_chars receipt states the measured truth. A separately authorized exception
    # waives that failed condition; it never requires a false "pass" receipt.
    required=['min_chars']
    for field,value in filters.items():
        if field=='min_chars' or value in (None,[],{},'',False):continue
        if isinstance(value,list): required.extend(f'{field}:{i}' for i in range(len(value)))
        else:required.append(field)
    for key in required:
        check=checks.get(key) or {}
        expected='fail' if key=='min_chars' and allowed_exception else 'pass'
        if check.get('status') != expected or not check.get('evidence') or not check.get('source_url'):
            return False,'missing_or_failed_check:'+key
    platforms=filters.get('platforms') or []
    if platforms and candidate.get('platform') not in platforms:return False,'platform'
    genres=filters.get('genres') or []
    if genres and not set(genres).intersection(candidate.get('genres') or []):return False,'genre'
    if candidate.get('must_not_violations') or candidate.get('must_missing'):return False,'explicit_violation'
    return True,'pass'


def verify_samples(candidate: dict, root: Path) -> list[dict]:
    samples=candidate.get('samples') or []
    if not samples:raise ValueError('candidate requires accessible pre-ranking body samples')
    by_id={}; verified=[]
    workspace=(root/'workspace').resolve()
    for sample in samples:
        ident=sample.get('sample_id');path=(root/str(sample.get('path') or '')).resolve()
        if not ident or ident in by_id or not path.is_relative_to(workspace) or not path.is_file():
            raise ValueError('sample identity/path is invalid')
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if sha != sample.get('sha256') or not sample.get('source_url'):raise ValueError('sample hash/source missing or changed')
        text=raw.decode('utf-8'); by_id[ident]=text
        verified.append(dict(sample,sha256=sha))
    for feature in features(candidate):
        text=by_id.get(feature['sample_id'])
        start,end=feature.get('start'),feature.get('end')
        if text is None or not isinstance(start,int) or not isinstance(end,int) or not 0 <= start < end <= len(text) or text[start:end] != feature['evidence']:
            raise ValueError('feature evidence is not the exact sampled text span')
    return verified


def trace_valid(trace: dict) -> bool:
    if trace.get('schema_version') != CONTRACT_VERSION:return False
    body={k:v for k,v in trace.items() if k!='trace_hash'}
    return bool(trace.get('trace_hash')) and digest(body)==trace['trace_hash']


class PreparedTraces(dict):
    """Validated once per learning transaction; never persisted into historical evidence."""
    def __init__(self, data):
        super().__init__(data)
        self.valid_contexts={k for k,v in data.get('contexts',{}).items() if trace_valid(v)}


def trace_cohort(trace: dict) -> str:
    return trace.get('scoring_cohort_id') or 'legacy-code:' + str((trace.get('model_snapshot') or {}).get('code_revision','unknown'))


def prospective_trace(traces: dict, pair: dict, *, active_cohort: bool = True) -> dict | None:
    trace=(traces.get('contexts') or {}).get(pair.get('context_id')) or {}
    valid=pair.get('context_id') in traces.valid_contexts if isinstance(traces,PreparedTraces) else trace_valid(trace)
    if not valid or not trace.get('model_revision') or not trace.get('request_hash'):return None
    if active_cohort and trace_cohort(trace)!=SCORING_COHORT_ID:return None
    if trace.get('profile_id') != pair.get('profile_id'):return None
    try:
        created=datetime.fromisoformat(trace['created_at'])
        if any(datetime.fromisoformat(pair[k]) <= created for k in ('winner_created_at','loser_created_at')):return None
    except (KeyError,TypeError,ValueError):return None
    rows=trace.get('candidates') or {}
    if any(not (rows.get(pair[k]) or {}).get('selected') for k in ('winner','loser')):return None
    return trace


def validate_entry(entry: dict, traces: dict) -> None:
    if not str(entry.get('schema_version','')).startswith('2') and not (entry.get('preference_policy') or {}).get('required_trace'):return
    trace=(traces.get('contexts') or {}).get(entry.get('entry_id')) or {}
    if not trace_valid(trace) or entry.get('ranking_trace_hash') != trace.get('trace_hash'):
        raise ValueError('completed entry requires its immutable ranking trace')
    if digest(entry.get('ranking_request')) != trace.get('request_hash'):
        raise ValueError('entry request changed after ranking')
    frozen=trace.get('request') or {}
    for field,default in [('hard_filters',{}),('soft_preferences',{}),('reference_works',[])]:
        if entry.get(field,default)!=frozen.get(field,default):
            raise ValueError('entry request projection changed after ranking: '+field)
    if entry.get('profile_id') != trace.get('profile_id'):raise ValueError('entry profile differs from trace')
    selected=[canonical(x) for x in selected_candidates(entry)]
    for bucket,exception in [('shortlist',False),('length_exceptions',True)]:
        expected_bucket=[k for k in trace.get('selected_order',[]) if bool(trace['candidates'][k].get('length_exception'))==exception]
        if [canonical(x) for x in entry.get('results',{}).get(bucket,[])]!=expected_bucket:
            raise ValueError('entry bucket differs from frozen selected slate')
    expected=trace.get('selected_order') or []
    if selected != expected:raise ValueError('entry shortlist differs from frozen selected slate')


def selected_candidates(entry: dict) -> list[dict]:
    results=entry.get('results') or {}
    rows=list(results.get('shortlist',[]))+list(results.get('length_exceptions',[]))
    if str(entry.get('schema_version','')).startswith('2'):
        return sorted(rows,key=lambda x:x.get('preference_rank',0))
    return rows


def finalize_entry(root: Path, context_id: str) -> dict:
    """Publish only safe metadata from an already frozen slate; never regenerate a trace."""
    path=root/'data/entries'/f'{context_id}.json'
    with state_lock(root/'workspace'):
        entry=load(path,{})
        trace=(load(root/'workspace/preference-ranking-traces.json',{}).get('contexts') or {}).get(context_id) or {}
        if not trace_valid(trace):raise ValueError('a verified ranking trace is required before entry finalization')
        frozen=trace['request']
        if entry.get('profile_id')!=trace['profile_id']:raise ValueError('draft profile differs from trace')
        if entry.get('ranking_request') and digest(entry['ranking_request'])!=trace['request_hash']:
            raise ValueError('draft request does not match ranking trace')
        safe_fields={'title','author','platform','url','length_chars','episodes','status','why','difference',
                     'rank','publication_tier','publication_note','length_exception','selection_mode','preference_rank','sample_priority'}
        rows=[]
        for index,key in enumerate(trace['selected_order'],1):
            row=trace['candidates'][key]
            clean={k:v for k,v in row.items() if k in safe_fields}
            clean['rank']=f'A{index}';rows.append(clean)
        entry.update(hard_filters=frozen['hard_filters'],soft_preferences=frozen.get('soft_preferences',{}),reference_works=frozen.get('reference_works',[]))
        entry.update(schema_version='2.0',profile_id=trace['profile_id'],ranking_request=frozen,
                     ranking_trace_hash=trace['trace_hash'],status='complete')
        entry.setdefault('preference_policy',{})['required_trace']=True
        entry.setdefault('results',{})['shortlist']=[x for x in rows if not x.get('length_exception')]
        entry['results']['length_exceptions']=[x for x in rows if x.get('length_exception')]
        validate_entry(entry,{'contexts':{context_id:trace}})
        save(path,entry)
        return entry
