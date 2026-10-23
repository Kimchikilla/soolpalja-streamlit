from pydantic import BaseModel, Field
import re
from .settings import model
from .store import stores
from .rag import format_evidence, cited_evidence
from .prompts import RECOMMEND
from .catalog import load_catalog


class Pick(BaseModel):
    item_id: str
    reason: str
    checks: list['ConditionProof']


class ConditionProof(BaseModel):
    condition_index: int
    satisfied: bool
    evidence_number: int
    quote: str


class Ingredient(BaseModel):
    name: str
    aliases: list[str]


class Conditions(BaseModel):
    search_query: str
    conditions: list[str]
    required_ingredients: list[Ingredient]
    excluded_ingredients: list[Ingredient]


class Picks(BaseModel):
    picks: list[Pick] = Field(default_factory=list)
    message: str


def recommend(conditions, diagnostics=None, *, persona=None, category=None, on_progress=None):
    def report(stage, message, **details):
        if on_progress:
            on_progress(stage, message, details)

    report('search', 'MBTI·사주 모티브와 연결할 술을 검색 중입니다.')
    default_recommendation = not conditions.strip()
    meta, docs = stores()
    if not meta.get(limit=1)['ids'] or not docs.get(limit=1)['ids']:
        raise ValueError('색인이 없습니다. 데이터 색인을 먼저 실행하세요.')
    plan = Conditions(search_query='alcoholic drink whisky wine tequila rum soju baijiu characteristics', conditions=['원료·제조법·숙성·스타일 중 하나 이상의 특징이 문서에 명시되어 있음'], required_ingredients=[], excluded_ingredients=[]) if not conditions.strip() else model().with_structured_output(Conditions).invoke([
        ('system', '주류 검색 조건을 원자 조건으로 분해하라. AND 조건을 빠짐없이 분리한다. search_query는 영어 검색어다. 재료가 반드시 포함/제외되어야 한다면 required_ingredients/excluded_ingredients에 해당 재료와 원문에 나타날 영어·한국어 별칭을 기록한다. 사용자가 명시하지 않은 조건이나 재료는 추가하지 않는다.'),
        ('human', conditions),
    ])
    plan.conditions.extend(f'제외 재료: {x.name}' for x in plan.excluded_ingredients)
    if not plan.conditions:
        return {'picks': [], 'message': '확인할 취향 조건을 입력해주세요.'}
    query = persona['style_query'] if default_recommendation and persona else plan.search_query
    search_filter = {'category': category} if category else None
    candidates = meta.similarity_search(query, k=24, filter=search_filter)
    # Search both item metadata and actual descriptions; append metadata for external hits.
    external = docs.similarity_search(query, k=12)
    ids = {d.metadata['item_id'] for d in candidates + external}
    catalog = load_catalog()
    catalog = [x for x in catalog if x.get('item_kind') != 'producer' and (not category or x['category'] == category)]
    lookup = {x['id']: x for x in catalog}
    ids &= set(lookup)
    if default_recommendation:
        ids = {x['id'] for x in catalog if x['id'] in ids} if persona else {x['id'] for x in catalog[:6]}
        # Preserve semantic relevance; worldwide article counts buried local products.
        ranked = list(dict.fromkeys(d.metadata['item_id'] for d in candidates + external if d.metadata['item_id'] in ids))
        ids = set(ranked[:8]) if persona else ids
        if persona and not category:
            domestic = meta.similarity_search(query, k=2, filter={'origin': 'KR'})
            ids.update(d.metadata['item_id'] for d in domestic if d.metadata['item_id'] in lookup)
    report('candidates', f'1차 후보 {len(ids)}개 검색 완료. 원문을 확인합니다.', names=[lookup[i]['name'] for i in sorted(ids)])
    evidence = []
    for item_id in sorted(ids):
        if item_id not in lookup:
            continue
        first = docs.get(ids=[f"{item_id}:{lookup[item_id]['document_id']}:0"])
        if not first['ids']:
            continue
        recipe = first['documents'][0]
        report('evidence', f"{lookup[item_id]['name']} · 원료·제조법·스타일 확인 중", name=lookup[item_id]['name'], excerpt=recipe[:350], source_url=first['metadatas'][0].get('source_url', ''))
        if not all(has_alias(recipe, x) for x in plan.required_ingredients) or any(has_alias(recipe, x) for x in plan.excluded_ingredients):
            continue
        from langchain_core.documents import Document
        # Metadata supplies candidate names; ingredient proofs use external text only.
        # Always include the indexed introductory recipe, not only history/variants.
        if first['ids']:
            evidence.append(Document(page_content=first['documents'][0], metadata=first['metadatas'][0]))
        evidence.extend(docs.similarity_search(query, k=2, filter={'item_id': item_id}))
    seen_evidence = set()
    unique_evidence = []
    for document in evidence:
        key = (document.metadata['item_id'], document.page_content)
        if key not in seen_evidence:
            seen_evidence.add(key)
            unique_evidence.append(document)
    evidence = unique_evidence
    ids = {d.metadata['item_id'] for d in evidence}
    if not ids:
        return {'picks': [], 'message': '수집한 근거에서 모든 조건 충족을 확인한 후보가 없습니다.'}
    ids_text = '\n'.join(f"{i}: {lookup[i]['name']}" for i in sorted(ids) if i in lookup)
    report('selection', f'후보 {len(ids)}개 · 원문 조각 {len(evidence)}개 확보. 어울리는 술 3개를 고르는 중.')
    response = model().with_structured_output(Picks).invoke([
        ('system', RECOMMEND + '\n칵테일뿐 아니라 위스키·와인·소주 등 단일 주종과 브랜드도 후보에 포함된다. 해당 주종의 원료·제조법·숙성·스타일 중 문서에서 확인한 특징으로 소개한다. 브랜드 전체를 특정 연산·도수의 한 제품으로 단정하지 않는다. 각 후보마다 모든 원자 조건을 0부터 번호를 붙여 checks에 검증한다. 하나라도 불충족/불명확하면 추천에서 제외한다. checks.quote는 해당 술의 외부 문서에서 그대로 복사한 원문이며 해당 조건을 입증해야 한다. 메타데이터만으로 재료를 입증하지 않는다. 진이 있다는 사실만으로 진+토닉워터 조건을 충족하지 않는다. 이유에도 외부 문서 근거를 인용한다.'),
        ('human', f'취향 조건: {conditions}\n원자 조건: {plan.conditions}\n캐릭터 연출 키워드(취향 조건이 아닌 비유): {persona["description"] if persona else "없음"}\n후보 ID:\n{ids_text}\n\n근거:\n{format_evidence(evidence)}'),
    ])
    if diagnostics is not None:
        diagnostics.update(plan=plan.model_dump(), response=response.model_dump())
    output = []
    seen = set()
    for pick in response.picks:
        used = cited_evidence(pick.reason, evidence)
        valid = validate_pick(pick, plan, evidence)
        if diagnostics is not None:
            diagnostics.setdefault('validation', []).append({'id': pick.item_id, 'valid': valid, 'sources': used,
                'proof_documents': [{'number': p.evidence_number, 'item_id': evidence[p.evidence_number - 1].metadata['item_id'], 'text': evidence[p.evidence_number - 1].page_content} for p in pick.checks if 1 <= p.evidence_number <= len(evidence)]})
        if pick.item_id in ids and pick.item_id not in seen and used and valid and any(x['source_type'] in {'Wikipedia', 'Manufacturer'} for x in used) and all(x['item_id'] == pick.item_id for x in used):
            seen.add(pick.item_id)
            output.append({'item': lookup[pick.item_id], 'reason': pick.reason, 'sources': used, 'verified_facts': list(dict.fromkeys(proof.quote for proof in pick.checks))})
    if default_recommendation and not output:
        # No taste constraints: show traceable catalogue introductions even if the
        # model's citation formatting fails; never silently return an empty screen.
        for item in [x for x in catalog if x['id'] in ids][:3]:
            numbered = next(((i, d) for i, d in enumerate(evidence, 1) if d.metadata['item_id'] == item['id']), None)
            if numbered:
                number, document = numbered
                excerpt = document.page_content.split('\n')[0]
                output.append({'item': item, 'reason': f'취향 제한 없이 고른 기본 도감 추천입니다. 원문 소개: {excerpt} [근거 {number}]', 'sources': [{'number': number, **document.metadata}], 'verified_facts': [excerpt]})
    message = '문서로 모든 조건을 확인한 후보입니다.' if output else '수집한 근거에서 모든 조건 충족을 확인한 후보가 없습니다.'
    if default_recommendation:
        message = 'MBTI·오행 캐릭터를 문서에 확인된 술의 특징과 연결했습니다.' if persona else '취향을 입력하지 않아 대표 칵테일을 소개합니다.'
    report('selected', f'근거 확인 완료. 최종 후보 {min(len(output), 3)}개를 선정했습니다.', names=[p['item']['name'] for p in output[:3]])
    return {'picks': output[:3], 'message': message}


def has_alias(text, ingredient):
    return any(re.search(r'(?<!\w)' + re.escape(alias.casefold()) + r'(?!\w)', text.casefold()) for alias in [ingredient.name] + ingredient.aliases if alias.strip())


def validate_pick(pick, plan, evidence):
    if len(pick.checks) != len(plan.conditions) or {x.condition_index for x in pick.checks} != set(range(len(plan.conditions))):
        return False
    quotes = []
    for proof in pick.checks:
        if not proof.satisfied or not 1 <= proof.evidence_number <= len(evidence):
            return False
        document = evidence[proof.evidence_number - 1]
        if document.metadata['item_id'] != pick.item_id or document.metadata['source_type'] not in {'Wikipedia', 'Manufacturer'}:
            return False
        quote = ' '.join(proof.quote.split())
        if not quote or quote.casefold() not in ' '.join(document.page_content.split()).casefold():
            return False
        quotes.append(quote)
    quoted = '\n'.join(quotes)
    return all(has_alias(quoted, x) for x in plan.required_ingredients) and not any(has_alias(quoted, x) for x in plan.excluded_ingredients)
