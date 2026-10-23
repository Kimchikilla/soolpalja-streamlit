"""Refresh Korean products from revision-pinned articles and a maker release."""
import html
import re
from datetime import datetime, timezone
from collect_data import DATA, get, save


TARGETS = {
    '참이슬': 'soju', '청하 (술)': 'traditional', '처음처럼 (술)': 'soju',
    '한라산 (술)': 'soju', '백세주': 'traditional', '복분자주': 'traditional',
    '클라우드 (맥주)': 'beer', '하이트 (맥주)': 'beer',
}


def main():
    import json
    items = {x['id']: x for x in json.loads((DATA / 'alcohols.json').read_text(encoding='utf-8'))}
    docs = {x['item_id']: x for x in json.loads((DATA / 'documents.json').read_text(encoding='utf-8'))}
    now = datetime.now(timezone.utc).isoformat()
    for title, category in TARGETS.items():
        response = get('https://ko.wikipedia.org/w/api.php', {
            'action': 'query', 'format': 'json', 'prop': 'info|pageprops|revisions',
            'inprop': 'url', 'rvprop': 'ids|timestamp', 'titles': title,
        })
        page = next(iter(response['query']['pages'].values()))
        qid = page['pageprops']['wikibase_item']
        rev = page['revisions'][0]
        parsed = get('https://ko.wikipedia.org/w/api.php', {
            'action': 'parse', 'format': 'json', 'oldid': rev['revid'], 'prop': 'text',
        })['parse']['text']['*']
        paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', parsed, re.S)
        text = '\n\n'.join(html.unescape(re.sub('<[^>]+>', '', p)).strip() for p in paragraphs)
        text = re.sub(r'\[\d+\]', '', text).strip()
        if len(text) < 40:
            raise ValueError(f'Insufficient product text: {title}')
        entity = get('https://www.wikidata.org/w/api.php', {
            'action': 'wbgetentities', 'format': 'json', 'ids': qid,
            'languages': 'ko|en', 'props': 'labels|descriptions|sitelinks',
        })['entities'][qid]
        name = title.split(' (')[0]
        docid = f"kowiki-{page['pageid']}"
        items[qid] = dict(id=qid, name=name,
            name_en=entity.get('labels', {}).get('en', {'value': name})['value'],
            category=category, item_kind='brand_or_style', origin='KR',
            description=entity.get('descriptions', {}).get('ko', {'value': text.split('\n')[0]})['value'],
            source_url=f'https://www.wikidata.org/wiki/{qid}', document_url=page['fullurl'],
            document_id=docid, document_language='ko', document_title=title,
            sitelinks=len(entity.get('sitelinks', {})), license='CC0-1.0', collected_at=now,
            abv=None, sweetness=None)
        docs[qid] = dict(id=docid, item_id=qid, title=title, text=text,
            source_url=page['fullurl'], revision_url=f"https://ko.wikipedia.org/w/index.php?oldid={rev['revid']}",
            revision_id=rev['revid'], revision_timestamp=rev['timestamp'], source_type='Wikipedia',
            language='ko', license='CC-BY-SA-4.0', collected_at=now,
            attribution=f"한국어 위키백과 기여자, {title}; {page['fullurl']}?action=history",
            transformations='Paragraph text extracted from revision-pinned MediaWiki HTML; reference numbers removed; no generated facts.')
        print(name, qid, len(text), flush=True)
    # The maker's release concerns the drink, unlike the existing Jinro company entry.
    # Short factual paraphrase, not a copied press release or a current ABV claim.
    qid = 'kr-jinro-soju'
    url = 'https://www.newswire.co.kr/newsRead.php?no=959487'
    items[qid] = dict(id=qid, name='진로', name_en='Jinro soju', category='soju',
        item_kind='brand_or_style', origin='KR', description='하이트진로의 소주 제품. 회사 항목과 구분한 제품 단위 데이터.',
        source_url=url, document_url=url, document_id='hitejinro-release-959487',
        document_language='ko', document_title='하이트진로, 제로슈거 진로 첫 출고',
        document_source_type='Manufacturer',
        sitelinks=0, license='CC0-1.0', collected_at=now, abv=None, sweetness=None)
    docs[qid] = dict(id='hitejinro-release-959487', item_id=qid,
        title='진로 소주 — 제조사 발표 요약',
        text='진로는 하이트진로의 소주 제품이다. 하이트진로는 2023년 1월 10일 이천공장에서 제로슈거 진로를 처음 출고했다고 발표했다. 해당 발표는 과당을 사용하지 않은 리뉴얼 제품을 소개한다. 제조사는 제품의 깔끔한 맛과 두꺼비 캐릭터를 소개했다. 이 문서는 당시 발표의 요약이며 현재 판매 제품의 도수·성분표를 보증하지 않는다.',
        source_url=url, revision_url=url, source_type='Manufacturer', language='ko',
        license='CC0-1.0', collected_at=now,
        attribution='하이트진로 공식 보도자료(뉴스와이어 배포), 2023-01-10. 사실 요약은 프로젝트 작성.',
        transformations='Project-authored factual paraphrase of the maker release; no full-text redistribution.')
    for key in ['Q16189004', 'Q21710543', 'Q12625660', 'Q27952203', 'Q85986988']:
        if key in items:
            items[key]['origin'] = 'KR'
    save('alcohols.json', list(items.values()))
    save('documents.json', list(docs.values()))
    print('Total:', len(items), flush=True)


if __name__ == '__main__':
    main()
