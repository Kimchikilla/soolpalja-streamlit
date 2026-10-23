"""Entertainment copy is separate from evidence-based alcohol facts."""
from datetime import date, time
from dataclasses import dataclass
from lunar_python import Solar, Lunar
from .saju import analyze_chart

MBTIS = [a + b + c + d for a in 'EI' for b in 'NS' for c in 'TF' for d in 'JP']
ELEMENTS = {'甲': '목', '乙': '목', '丙': '화', '丁': '화', '戊': '토', '己': '토', '庚': '금', '辛': '금', '壬': '수', '癸': '수'}
COPY = {
    '목': ('단톡방 번개 소집형', '집에 간다더니 다음 약속을 잡고 있는 사람.'),
    '화': ('입장 3분 만에 주인공형', '조용히 있겠다는 다짐은 현관에 두고 왔다.'),
    '토': ('술자리 인간 보조배터리형', '남의 고민 다 들어주고 정작 내 얘기는 못 했다.'),
    '금': ('안주 취향까지 면접관형', '아무거나 좋다면서 아무거나는 싫은 사람.'),
    '수': ('새벽 감성 장문 작성형', '보내기 전에 한 번만 더 읽자. 제발.'),
}


@dataclass(frozen=True)
class LunarDate:
    year: int
    month: int
    day: int


def create_persona(mbti: str, birthday: date | LunarDate, birthtime: time | None, *, calendar='solar', leap_month=False):
    if mbti not in MBTIS:
        raise ValueError('올바른 MBTI를 선택하세요.')
    known = birthtime is not None
    clock = birthtime or time(12, 0)
    # Library uses Chinese calendar solar terms. We explicitly label this approximation.
    if calendar not in ['solar', 'lunar']:
        raise ValueError('달력 기준을 확인하세요.')
    if calendar == 'lunar':
        lunar = Lunar.fromYmdHms(birthday.year, -birthday.month if leap_month else birthday.month, birthday.day, clock.hour, clock.minute, 0)
    else:
        lunar = Solar.fromYmdHms(birthday.year, birthday.month, birthday.day, clock.hour, clock.minute, 0).getLunar()
    chart = lunar.getEightChar()
    chart.setSect(2)
    analysis = analyze_chart(chart, known)
    element = ELEMENTS[chart.getDayGan()]
    title, description = COPY[element]
    if mbti[0] == 'I':
        description += ' 말은 안 해도 머릿속 단톡방은 이미 시끄럽다.'
    else:
        description += ' 처음 보는 사람도 일단 우리 테이블이다.'
    description += (' 한마디 들으면 혼자 시즌 3까지 쓴다.' if mbti[1] == 'N' else '분위기보다 안주가 식는 게 먼저 보인다.')
    description += (' 고민 상담인 줄 알았는데 해결책 발표회가 됐다.' if mbti[2] == 'T' else '친구 사연에 내가 먼저 과몰입했다.')
    description += (' 귀가 동선까지 짜놨지만 친구가 변수다.' if mbti[3] == 'J' else '계획은 없는데 다음 장소는 이미 정해졌다.')
    # Editorial character-to-drink motifs, not measured psychological preferences.
    style = [
        'classic refined gin vermouth' if mbti[0] == 'I' else 'party punch fruit rum',
        'unusual contrasting ingredients modern cocktail' if mbti[1] == 'N' else 'traditional familiar recipe',
        'minimal clear distinctive composition' if mbti[2] == 'T' else 'shared layered fruit floral ingredients',
        'balanced established classic' if mbti[3] == 'J' else 'playful variations tropical cocktail',
        {'목': 'herbal wine sake agave', '화': 'rum tequila brandy', '토': 'whisky bourbon soju baijiu', '금': 'dry gin vodka white wine', '수': 'aged whisky red wine dark rum'}[analysis['dominant_elements'][0]],
    ]
    return {
        'title': title, 'description': description, 'element': element, 'mbti': mbti,
        'style_query': ' '.join(style),
        'saju': analysis,
        'pillars': {'년주': chart.getYear(), '월주': chart.getMonth(), '일주': chart.getDay(), '시주': chart.getTime() if known else '시간 미상'},
        'notice': 'lunar-python의 절기·간지 계산을 사용합니다. 음력 입력은 윤달 여부를 적용해 변환합니다. 한국 표준시/중국 절기 시각 차이와 출생지 진태양시를 보정하지 않아 경계일은 달라질 수 있습니다. 시간 미상은 정오 가정의 년·월·일주만 사용하며 시주와 시주 오행은 집계에서 제외합니다.',
    }
