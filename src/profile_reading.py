"""Analyze the supplied profile before retrieving or naming any drink."""
import json
from typing import Literal
from pydantic import BaseModel
from .settings import model


class ProfileReport(BaseModel):
    saju_analysis: str
    mbti_analysis: str
    combined_analysis: str
    summary: str


def profile_facts(persona):
    saju = persona.get('saju', {})
    master = saju.get('day_master', {})
    return {
        'mbti': persona['mbti'],
        'day_master': {key: master[key] for key in ['name', 'element', 'polarity', 'image', 'motif'] if key in master},
        'element_counts': saju.get('element_counts', {}),
        'yin_yang': saju.get('yin_yang', {}),
        'known_birth_time': saju.get('known_birth_time', False),
        'ten_gods': list(dict.fromkeys(row['천간 십신'] for row in saju.get('pillar_details', []) if row['천간 십신'] not in ['日主', '일주 자신'])),
    }


def analyze_persona(persona, *, on_progress=None):
    if on_progress:
        on_progress('analysis', '사주 계산 결과와 MBTI를 먼저 분석 중입니다.', {})
    response = model().with_structured_output(ProfileReport).invoke([
        ('system', '''사용자의 사주 계산 결과와 MBTI를 분석한 독립적인 리포트를 작성한다. 아직 추천 대상은 정해지지 않았다. 술, 음식, 주문, 메뉴 선택을 예로 들지 않는다. 추천을 정당화하려는 성격이나 취향을 만들어내지 않는다.
saju_analysis: 2개 문단, 합계 250~450자. 먼저 입력 일간·음양·이미지의 전통적 의미를 설명하고, 그 의미를 자기표현·관계·결정 방식에서 어떻게 읽는지 구체적으로 풀어 쓴다. 표면 오행/음양 집계는 실제 숫자만 인용한다. 표면 글자 수로 목 기운이 강하다거나 수가 부족하다고 판단하지 않는다. 월령·지장간·합충·신강신약·용신은 계산하지 않았으므로 분석한 것처럼 쓰지 않는다. 시간 미상이면 시주 제외를 정확히 밝힌다. 계산된 사실과 전통적 해석을 구분한다.
mbti_analysis: 2개 문단, 합계 220~350자. 네 지표를 각각 설명하고, 평소 결정·일처리·거리두기에서 나타날 수 있는 장점과 불편한 지점을 구체적으로 설명한다. I인데 외향적이라거나 P인데 반드시 계획적이라는 식으로 지표를 뒤집지 않는다. 술의 이름이나 특징을 끼워 넣지 않는다.
combined_analysis: 2개 문단, 합계 220~350자. 앞의 두 분석에서 공통으로 나타나는 성향과 서로 다른 방향으로 작용할 수 있는 지점을 설명한다. 억지로 모순을 만들거나 모든 사용자를 고집 센 사람으로 묘사하지 않는다. 심리 진단·미래 예언이 아닌 재미용 해석임을 전제로 구체적인 일상 장면을 사용한다. 내용은 예리하되 조롱, 억지 직업명, 너는/당신은 같은 직접 호칭을 쓰지 않는다.
summary: 종합 성향을 2문장으로 압축한다. 단정적인 취향 추측이나 특정 추천 대상은 포함하지 않는다.
설명은 담백한 '-합니다/-입니다'로 통일한다. 세 분석은 같은 문장을 반복하지 않는다. 생년월일·출생시각·전체 사주 기둥을 추측하지 않는다. 입력에 없는 계산과 운세를 만들어내지 않는다.'''),
        ('human', json.dumps(profile_facts(persona), ensure_ascii=False)),
    ])
    return response.model_dump()


class RecommendationReason(BaseModel):
    item_id: str
    profile_key: Literal['saju_analysis', 'mbti_analysis', 'combined_analysis', 'summary']
    fact_index: int
    reason: str


class RecommendationReasons(BaseModel):
    recommendations: list[RecommendationReason]


def attach_recommendation_reasons(result, profile_report, *, on_progress=None):
    if not result['picks']:
        return result
    if on_progress:
        on_progress('writing', '확정된 성향과 검증된 술 정보를 비교 중입니다.', {})
    drinks = [{'item_id': pick['item']['id'], 'name': pick['item']['name'], 'verified_facts': pick.get('verified_facts') or [pick['reason']]} for pick in result['picks']]
    response = model().with_structured_output(RecommendationReasons).invoke([
        ('system', """이미 확정된 성향 분석과 원문에서 검증한 주류 특징을 비교해 추천 이유만 작성한다. 성향 분석을 다시 쓰거나 특정 술에 맞춰 새 성격을 만들지 않는다.
profile_key는 참고한 분석 항목의 키를 선택한다. fact_index는 해당 술의 verified_facts 배열에서 참고한 원문의 0부터 시작하는 번호다. 원문과 분석을 다시 만들어 쓰지 말고 제공된 항목을 선택한다. reason은 3문장으로 작성한다. 첫 문장에서 분석에서 드러난 선택·관계·결정의 핵심 성향을 짚고, 다음 문장에서 선택한 원문의 실제 주류 특징을 설명하고, 마지막에 그 두 기준에서 이 술을 추천하는 이유를 정리한다. 원문에 없는 재료·맛·비율·숙성·도수·효능은 추가하지 않는다. 술이 고집을 부린다거나 자신의 기준을 고수한다는 식으로 술을 의인화하지 않는다. '목이라 라임/수 부족이라 토닉/양이라 깔끔한 맛' 같은 오행과 성분의 가짜 대응은 금지한다. 사주·MBTI가 실제 입맛을 증명한다고 주장하지 않는다. 공통점이 약하면 솔직히 성향을 참고한 탐색 후보이며 실제 취향 확인이 필요하다고 쓴다. 약한 연결을 억지로 설명하는 것보다 정확한 구분이 우선이다. 원문 인용문에 담긴 사실만 사용하고 비유를 사실처럼 단정하지 않는다. '-합니다/-입니다'로 담백하게 쓴다. 모든 입력 item_id에 한 번씩 작성한다."""),
        ('human', json.dumps({'independent_analysis': profile_report, 'drinks': drinks}, ensure_ascii=False)),
    ])
    mapped = {r.item_id: r for r in response.recommendations}
    for pick, context in zip(result['picks'], drinks):
        reason = mapped.get(pick['item']['id'])
        if reason and reason.profile_key in profile_report and 0 <= reason.fact_index < len(context['verified_facts']):
            text = reason.reason
            source_fact = context['verified_facts'][reason.fact_index]
            basis = profile_report[reason.profile_key]
        else:
            text = '성향 분석을 참고해 원문에서 특징을 확인한 후보입니다. 성격만으로 실제 맛의 선호를 판단하지 않으며, 아래 주류 정보를 함께 확인할 수 있습니다.'
            source_fact = context['verified_facts'][0]
            basis = profile_report['summary']
        pick['reading'] = {'type_name': '사주·MBTI 기반 추천', 'tagline': '분석한 성향을 기준으로 검토한 추천입니다.', 'connection': text, 'profile_basis': basis, 'source_fact': source_fact}
        if on_progress:
            on_progress('character', f"{pick['item']['name']} 추천 이유 확인 완료", {})
    return result
