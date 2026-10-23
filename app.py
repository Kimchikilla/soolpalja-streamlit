"""술 팔자: guided input, full-width results and separate catalogue/chat/admin."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path
import logging
import streamlit as st
from src.catalog import load_catalog, load_documents, category_label
from src.persona import create_persona, LunarDate
from src.settings import api_ready

st.set_page_config(page_title='술 팔자 · 네 술자리 본성을 까준다', page_icon='🥃', layout='wide', initial_sidebar_state='collapsed')
st.markdown(f'<style>{(Path(__file__).parent / "assets/app.css").read_text(encoding="utf-8")}</style>', unsafe_allow_html=True)
items, documents = load_catalog(), load_documents()
lookup = {x['id']: x for x in items}
doc_lookup = {x['item_id']: x for x in documents}
state = st.session_state
for key, value in {'route': 'fortune', 'stage': 0, 'conversations': {}, 'selected_id': items[0]['id']}.items():
    state.setdefault(key, value)


def navigate(route):
    state['route'] = route


def saved(key, default):
    return state.get('draft_inputs', {}).get(key, default)


def remember(key, value):
    state.setdefault('draft_inputs', {})[key] = value
    return value


def step(number):
    state['stage'] = number
    st.rerun()


def section_label(text):
    st.markdown(f'<div class="eyebrow">{escape(text)}</div>', unsafe_allow_html=True)


def show_sources(sources):
    if not sources:
        st.caption('이 답변에 인용된 근거가 없습니다.')
    for source in sources:
        st.markdown(f"[근거 {source['number']}] [{source['title']}]({source['source_url']}) · {source['source_type']}")
        if source.get('revision_url'):
            st.caption(f"{source.get('license', '')} · [수집 시점 원문]({source['revision_url']})")


def open_chat(item_id):
    state['selected_id'] = item_id
    state['chat_item'] = item_id
    navigate('chat')


def progress(current):
    names = ['MBTI', '생일과 시간']
    segments = ''.join(f'<span class="step {"active" if i == current else "done" if i < current else ""}"><b>{i:02d}</b> {name}</span>' for i, name in enumerate(names, 1))
    st.markdown(f'<div class="steps">{segments}</div>', unsafe_allow_html=True)


def landing():
    if st.button('술을 좋아하세요?', key='intro_start', width='stretch'):
        step(1)


def wizard():
    current = state['stage']
    _, center, _ = st.columns([1, 5, 1])
    with center:
        progress(current)
        if current == 1:
            st.title('MBTI 선택')
            previous = saved('mbti', 'INTJ')
            axes = [('에너지 방향', ['E', 'I']), ('정보를 보는 방식', ['S', 'N']), ('판단하는 방식', ['T', 'F']), ('생활하는 방식', ['J', 'P'])]
            selected = []
            for index, (column, (label, choices)) in enumerate(zip(st.columns(4), axes)):
                with column:
                    selected.append(st.radio(label, choices, index=choices.index(previous[index]), horizontal=True, key=f'input_mbti_{index}'))
            mbti = remember('mbti', ''.join(selected))
            st.subheader(mbti)
            labels = {'I': '관찰부터 하는 편', 'E': '말부터 거는 편', 'N': '상상이 먼저', 'S': '눈앞의 사실부터', 'T': '원인과 해결책', 'F': '사람과 마음', 'J': '계획이 편해', 'P': '흐름을 타는 편'}
            st.markdown('<div class="trait-chips">' + ''.join(f'<span><b>{x}</b> {labels[x]}</span>' for x in mbti) + '</div>', unsafe_allow_html=True)
            back, forward = st.columns(2)
            with back:
                if st.button('← 처음으로', width='stretch'):
                    step(0)
            with forward:
                if st.button('다음 · 생일 보기 →', type='primary', width='stretch'):
                    step(2)
        elif current == 2:
            st.title('생년월일 입력')
            st.caption('출생 시각은 선택 사항입니다.')
            calendar = remember('calendar', st.radio('생일 달력 기준', ['양력', '음력'], index=0 if saved('calendar', '양력') == '양력' else 1, horizontal=True, key='input_calendar'))
            today = datetime.now(ZoneInfo('Asia/Seoul')).date()
            leap = False
            if calendar == '음력':
                y, m, d = st.columns(3)
                with y:
                    year = remember('lunar_year', st.number_input('음력 생년', min_value=1930, max_value=today.year, value=saved('lunar_year', 2000), step=1, key='input_lunar_year'))
                with m:
                    month = remember('lunar_month', st.selectbox('음력 생월', list(range(1, 13)), index=saved('lunar_month', 1)-1, key='input_lunar_month'))
                with d:
                    day = remember('lunar_day', st.number_input('음력 생일', min_value=1, max_value=30, value=saved('lunar_day', 1), step=1, key='input_lunar_day'))
                birthday = LunarDate(year, month, day)
                leap = remember('leap', st.checkbox('음력 윤달 생일이에요', value=saved('leap', False), key='input_leap'))
            else:
                birthday = remember('birthday', st.date_input('생년월일 · 양력', value=saved('birthday', date(2000, 1, 1)), min_value=date(1930, 1, 1), max_value=today, key='input_birthday'))
            known = remember('known_time', st.checkbox('태어난 시간을 알고 있어요', value=saved('known_time', False), key='input_known_time'))
            birthtime = remember('birthtime', st.time_input('출생 시각', value=saved('birthtime', None), disabled=not known, key='input_birthtime'))
            st.caption('입력한 생년월일·시각은 파일에 저장하거나 AI 모델에 보내지 않습니다.')
            consent_attempt = state.get('consent_attempt', 0)
            consent_invalid = state.get('consent_invalid', False)
            consent_key = f'consent_required_{consent_attempt}' if consent_invalid else 'consent_normal'
            with st.container(key=consent_key):
                adult = remember('adult', st.checkbox('성인이며, 재미용 성향 해석임을 확인했어요.', value=saved('adult', False), key='input_adult'))
            if adult:
                state['consent_invalid'] = False

            back, forward = st.columns(2)
            with back:
                if st.button('← MBTI 다시 보기', width='stretch'):
                    step(1)
            with forward:
                submitted = st.button('내 본성까지 까보기 ↗', type='primary', width='stretch')
            if submitted:
                if not adult:
                    state['consent_invalid'] = True
                    state['consent_attempt'] = state.get('consent_attempt', 0) + 1
                    st.rerun()
                try:
                    state['persona'] = create_persona(saved('mbti', 'INTJ'), birthday, birthtime if known else None, calendar='lunar' if calendar == '음력' else 'solar', leap_month=leap)
                except Exception:
                    st.error('날짜와 음력·윤달 여부를 확인해주세요. 해당 달력에 없는 날짜는 계산할 수 없습니다.')
                    return
                state.pop('recommendations', None)
                step(5)


def searching():
    if not state.get('persona'):
        step(1)
    if api_ready():
        try:
            st.subheader('나에게 맞는 술을 찾는 중')
            st.caption('후보 검색 → 원문 확인 → 성격 해석')
            st.caption('진행 바는 단계별 완료 표시이며 남은 시간을 뜻하지 않아요. 작성 중 문구는 최종 검수 전 초안입니다.')
            timeline = []
            meter = st.progress(0, text='술 데이터 검색 중')
            live_draft = st.empty()
            milestones = {'search': 5, 'candidates': 15, 'evidence': 30, 'selection': 45, 'selected': 60, 'references': 65, 'writing': 75, 'character': 90}
            with st.status('추천 진행 과정', expanded=True) as status:
                def report(stage, message, details):
                    if stage == 'draft':
                        live_draft.info(details['preview'])
                        return
                    timeline.append({'stage': stage, 'message': message, **details})
                    meter.progress(milestones[stage], text=message)
                    status.update(label=message)
                    if stage == 'evidence':
                        with st.expander(message):
                            st.write(details['excerpt'])
                            if details.get('source_url'):
                                st.link_button('확인 중인 원문 보기 ↗', details['source_url'], width='stretch')
                    else:
                        st.write(message)
                        if details.get('names'):
                            st.markdown(' · '.join(details['names']))
                        if details.get('roast'):
                            st.info(details['roast'])
                from src.store import restore_deployment_index
                restore_deployment_index()
                from src.recommend import recommend
                from src.reading import attach_readings
                result = recommend('', persona=state['persona'], category=None, on_progress=report)
                state['recommendations'] = attach_readings(result, state['persona'], on_progress=report)
                state['recommendations']['search_timeline'] = timeline
                live_draft.empty()
                meter.progress(100, text='추천 완료')
                status.update(label='추천 완료', state='complete', expanded=False)
        except Exception:
            logging.getLogger(__name__).exception('Recommendation failed at generation stage')
            live_draft.empty()
            st.error('결과 생성이 중단됐습니다. 다시 시도해주세요.')
            if st.button('다시 찾기', type='primary', width='stretch'):
                st.rerun()
            if st.button('입력으로 돌아가기', width='stretch'):
                step(2)
            return
    step(4)


def saju_details(persona, result):
    with st.expander('사주 계산과 해석에 사용한 자료'):
        analysis = persona.get('saju')
        if analysis:
            st.write(analysis['summary'])
            st.dataframe(analysis['pillar_details'], hide_index=True, width='stretch')
            st.bar_chart({'오행': list(analysis['element_counts']), '표면 글자 수': list(analysis['element_counts'].values())}, x='오행', y='표면 글자 수')
            st.caption(analysis['method_note'])
        st.caption(persona['notice'])
        for source in result.get('saju_sources', []):
            st.markdown(f"[{source['title']}]({source['source_url']}) · {source['license']}")


def reading_body(pick, persona):
    reading = pick.get('reading')
    if reading:
        section_label('WHY THIS DRINK IS YOU')
        st.subheader('왜 하필 이 술이 너냐면.')
        st.write(reading['connection'])
        st.markdown('### 너는 이런 사람')
        for number, trait in enumerate(reading['personality'], 1):
            st.markdown(f'<div class="personality-line"><span>{number:02d}</span><p>{escape(trait)}</p></div>', unsafe_allow_html=True)
        scene, friend = st.columns(2, gap='large')
        with scene:
            st.markdown('#### 술자리에서 들키는 순간')
            st.write(reading['scene'])
        with friend:
            st.markdown('#### 잘 맞는 술친구')
            st.write(reading['companion'])
        with st.expander('MBTI와 사주로 풀어본 캐릭터'):
            st.markdown(f"**{persona['mbti']}에서 읽은 너**")
            st.write(reading['mbti_reading'])
            st.markdown('**사주에서 가져온 모티브**')
            st.write(reading['saju_reading'])
    with st.expander('이 술의 실제 특징과 추천 근거'):
        st.write(pick['reason'])
        show_sources(pick['sources'])


def results():
    persona = state.get('persona')
    if not persona:
        step(0)
    result = state.get('recommendations', {})
    picks = result.get('picks', [])
    if result.get('search_timeline'):
        with st.expander('방금 어떤 과정을 거쳐 찾았는지 다시 보기'):
            for event in result['search_timeline']:
                st.write(event['message'])
                if event.get('names'):
                    st.caption(' · '.join(event['names']))
    if not picks:
        section_label('YOUR CHARACTER')
        st.title(persona['title'])
        st.write(persona['description'])
        st.info('네 캐릭터와 연결할 근거를 충분히 찾지 못했어. 다시 시도하거나 도감에서 한 잔을 골라봐.' if api_ready() else '성격 카드는 먼저 열어봤어요. 술 추천은 잠시 준비 중이니 도감에서 한 잔을 골라보세요.')
        if st.button('다시 찾아보기', type='primary', width='stretch'):
            step(2)
        st.button('술 도감 둘러보기', on_click=navigate, args=('catalog',), width='stretch')
        saju_details(persona, result)
        return
    main = picks[0]
    reading = main.get('reading', {})
    title = reading.get('type_name', persona['title'])
    tagline = reading.get('tagline', persona['description'])
    st.markdown(f'''<div class="result-hero"><div class="eyebrow">YOUR DRINK PERSONA · {escape(persona['mbti'])}</div>
    <div class="result-type">너는 <b>{escape(title)}</b></div><h1>{escape(main['item']['name'])}</h1>
    <p>{escape(tagline)}</p><div class="result-tag">{escape(category_label(main['item']['category']))} &nbsp; / &nbsp; 네 성격을 닮은 한 잔</div></div>''', unsafe_allow_html=True)
    if reading:
        st.markdown(f'<div class="roast"><span>친구한테 들키면 끝</span><p>“{escape(reading["roast"])}”</p></div>', unsafe_allow_html=True)
    share = f"🥃 술 팔자\n{persona['mbti']} · {title}\n나의 술: {main['item']['name']}\n{tagline}\n{reading.get('roast', '')}\nMBTI·사주를 소재로 한 재미용 캐릭터 해석"
    a, b, c = st.columns(3)
    with a:
        st.download_button('내 결과 저장 ↓', share, file_name='술팔자_결과.txt', width='stretch')
    with b:
        st.button('이 술에게 물어보기 →', on_click=open_chat, args=(main['item']['id'],), width='stretch', type='primary')
    with c:
        if st.button('다시 까보기 ↻', width='stretch'):
            step(1)
    st.caption('MBTI·사주는 재미용 캐릭터 해석입니다. 실제 술 정보는 아래 원문 근거에서 확인하세요.')
    st.divider()
    reading_body(main, persona)
    if len(picks) > 1:
        st.divider()
        section_label('YOUR OTHER SIDES')
        st.subheader('너에게 이런 면도 있더라.')
        for pick in picks[1:]:
            other = pick.get('reading', {})
            with st.expander(f"{pick['item']['name']} · {other.get('type_name', '또 다른 한 잔')}"):
                st.markdown(f"**{other.get('tagline', '')}**")
                reading_body(pick, persona)
                st.button('이 술과 대화하기 →', key=f"other-{pick['item']['id']}", on_click=open_chat, args=(pick['item']['id'],), width='stretch')
    saju_details(persona, result)


def catalogue():
    section_label('THE DRINK LIBRARY')
    st.title('술 도감')
    search, category = st.columns([2, 1])
    with search:
        term = st.text_input('주류 이름·영문명 검색', placeholder='화요, 위스키, Martini…')
    with category:
        selected = st.selectbox('주종별 보기', ['all'] + sorted({x['category'] for x in items}), format_func=lambda x: '모든 주종' if x == 'all' else category_label(x))
    found = [x for x in items if (selected == 'all' or x['category'] == selected) and term.casefold() in f"{x['name']} {x['name_en']} {category_label(x['category'])} {x['description']}".casefold()]
    st.caption(f'{len(found)}개 항목 · 브랜드와 스타일에 따라 개별 제품의 도수·특징은 다를 수 있습니다.')
    pages = max(1, (len(found) + 11) // 12)
    page = st.number_input('페이지', min_value=1, max_value=pages, value=1, step=1, key=f'catalog_page_{selected}_{term}')
    columns = st.columns(3)
    for index, item in enumerate(found[(page - 1) * 12:page * 12]):
        with columns[index % 3], st.container(border=True):
            section_label(category_label(item['category']))
            st.subheader(item['name'])
            st.caption(item['name_en'])
            st.write(item['description'] or '설명은 연결된 원문에서 확인하세요.')
            if item.get('item_kind') == 'producer':
                st.caption('생산자 정보 · 추천에서는 제외합니다.')
            with st.expander('술 정보와 원문 읽기'):
                doc = doc_lookup.get(item['id'])
                if doc:
                    st.write(doc['text'])
                    st.markdown(f"[원문]({doc['source_url']}) · [수집 시점]({doc['revision_url']})")
                    st.caption(f"{doc['attribution']} · {doc['license']}")
            st.button('이 술에게 물어보기 →', key=item['id'], on_click=open_chat, args=(item['id'],), width='stretch')


def chat():
    section_label('ASK YOUR DRINK')
    st.title('술 정보 질문')
    state.setdefault('chat_item', state['selected_id'])
    selected = st.selectbox('대화할 술', list(lookup), format_func=lambda x: lookup[x]['name'], key='chat_item')
    state['selected_id'] = selected
    history = state['conversations'].setdefault(selected, [])
    st.caption('재료·유래·제조법을 질문하면 원문 근거와 함께 답변합니다.')
    from src.store import index_counts
    try:
        count, _ = index_counts()
    except Exception:
        count = 0
    ready = api_ready() and count > 0
    if not ready:
        st.info('대화를 준비 중입니다. 도감에서 술 정보를 먼저 살펴보세요.')
    for message in history:
        with st.chat_message(message['role']):
            st.write(message['content'])
            if message['role'] == 'assistant':
                with st.expander('답변의 근거 보기'):
                    show_sources(message.get('sources', []))
    question = st.chat_input('이 술, 뭐가 궁금해?', disabled=not ready)
    if question:
        try:
            with st.status('문서를 찾아 한 잔 더 알아보는 중…', expanded=False) as status:
                from src.collection import collect_for_question
                from src.rag import build_graph
                collect_for_question(lookup[selected], question)
                answer = build_graph().invoke({'item': lookup[selected], 'question': question, 'history': history})
                history.extend([{'role': 'user', 'content': question}, {'role': 'assistant', 'content': answer['answer'], 'sources': answer['used_evidence']}])
                status.update(label='답변을 찾았어요.', state='complete')
            st.rerun()
        except Exception:
            st.error('답변을 가져오지 못했어요. 잠시 후 다시 시도해주세요.')


def admin():
    section_label('WORKSPACE')
    st.title('서비스 관리')
    from src.store import index_counts, index_all
    from src.saju import reference_documents
    try:
        meta_count, chunk_count = index_counts()
    except Exception:
        meta_count, chunk_count = 0, 0
    one, two, three = st.columns(3)
    one.metric('주류 항목', len(items))
    two.metric('설명 문서', len(documents))
    three.metric('사주 개념 원문', len(reference_documents()))
    st.write(f'현재 색인: 주류 {meta_count}건 / 문서 청크 {chunk_count}건')
    if api_ready():
        st.success('AI 연결 설정 있음')
        if st.button('데이터 색인 / 갱신', width='stretch'):
            try:
                with st.status('데이터를 임베딩하고 있습니다.', expanded=True) as status:
                    st.write(index_all())
                    status.update(label='색인 완료', state='complete')
            except Exception:
                st.error('GMS 설정·모델 권한·네트워크를 확인하세요.')
    else:
        st.info('.env에 GMS_KEY를 설정해주세요.')
    st.caption('색인·검색 설정은 config.json에서 관리합니다. 키와 프롬프트 전문은 화면에 표시하지 않습니다.')


if state['route'] == 'fortune' and state['stage'] == 0:
    landing()
    st.stop()

with st.container(key=f"screen_{state['route']}_{state['stage']}"):
    if state['route'] == 'fortune':
        if state['stage'] == 0:
            landing()
        elif state['stage'] in [1, 2, 3]:
            if state['stage'] == 3:
                state['stage'] = 2
            wizard()
        elif state['stage'] == 5:
            searching()
        else:
            results()
    elif state['route'] == 'catalog':
        catalogue()
    elif state['route'] == 'chat':
        chat()
    elif state['route'] == 'admin':
        admin()
st.markdown('<div class="footer"><small>Wikidata CC0 · Wikipedia contributors CC BY-SA 4.0</small></div>', unsafe_allow_html=True)

with st.expander('술 도감 · 더 보기'):
    library, conversation, workspace = st.columns(3)
    with library:
        st.button('술 도감', key='nav_catalog', on_click=navigate, args=('catalog',), width='stretch')
    with conversation:
        st.button('채팅', key='nav_chat', on_click=navigate, args=('chat',), width='stretch')
    with workspace:
        st.button('관리', key='nav_admin', on_click=navigate, args=('admin',), width='stretch')
