"""Transparent traditional correspondences; counts do not diagnose strength/useful gods."""
import json
from collections import Counter
from .settings import ROOT


def rules():
    return json.loads((ROOT / 'data/saju_rules.json').read_text(encoding='utf-8'))


def analyze_chart(chart, known_time):
    data = rules()
    positions = [('년주', 'Year'), ('월주', 'Month'), ('일주', 'Day')]
    if known_time:
        positions.append(('시주', 'Time'))
    elements, polarities, rows = Counter(), Counter(), []
    for label, method in positions:
        pair = getattr(chart, f'get{method}')()
        stem, branch = data['stems'][pair[0]], data['branches'][pair[1]]
        elements.update([stem['element'], branch['element']])
        polarities.update([stem['polarity'], branch['polarity']])
        god = '日主' if method == 'Day' else getattr(chart, f'get{method}ShiShenGan')()
        rows.append({'기둥': label, '간지': pair, '한글': stem['name'] + branch['name'],
                     '천간 오행': stem['element'], '지지 오행': branch['element'],
                     '천간 십신': data['ten_gods'].get(god, god)})
    counts = {x: elements[x] for x in ['목', '화', '토', '금', '수']}
    dominant = [x for x, n in counts.items() if n == max(counts.values())]
    absent = [x for x, n in counts.items() if n == 0]
    day_stem = chart.getDayGan()
    day = data['stems'][day_stem]
    summary = f"일간 {day_stem}({day['name']}) · {day['polarity']}{day['element']}. 표면 글자 {sum(counts.values())}개에서 {'·'.join(dominant)}이 가장 많이 등장합니다."
    return {'day_master': {'character': day_stem, **day}, 'pillar_details': rows,
            'element_counts': counts, 'yin_yang': {x: polarities[x] for x in ['양', '음']},
            'dominant_elements': dominant, 'unrepresented_elements': absent,
            'known_birth_time': known_time, 'counted_characters': sum(counts.values()),
            'summary': summary,
            'method_note': '천간·지지 대표 오행을 각 1개로 센 단순 집계입니다. 지장간 가중치·계절 세력·격국·용신·신강신약 판단은 하지 않습니다. 0개는 미표시일 뿐 실제 기운 부족 진단이 아닙니다.'}


def reference_documents():
    path = ROOT / 'data/saju_documents.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


def retrieve_references():
    """Concept-only retrieval; does not send a birth chart to an embedding API."""
    from .store import saju_store
    store = saju_store()
    if not store.get(limit=1)['ids']:
        return []
    return store.max_marginal_relevance_search('사주팔자 천간 지지 오행 음양 four pillars heavenly stems earthly branches five phases', k=5, fetch_k=30, lambda_mult=0.35)
