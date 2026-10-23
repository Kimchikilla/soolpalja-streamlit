"""On-demand search terms -> candidate selection -> linked external document indexing."""
import hashlib
import json
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .settings import ROOT, config, model
from .prompts import SEARCH, SELECT
from .store import stores
from scripts.collect_data import get


class SearchTerms(BaseModel):
    terms: list[str] = Field(default_factory=list)


class SelectedTitles(BaseModel):
    titles: list[str] = Field(default_factory=list)


def collect_for_question(item, question):
    language = item.get('document_language', 'en')
    own_title = item.get('document_title', item['name_en'])
    endpoint = f'https://{language}.wikipedia.org/w/api.php'
    cache_dir = ROOT / 'data/cache/collection'
    cache_dir.mkdir(parents=True, exist_ok=True)
    question_key = hashlib.sha256(f"question:{item['id']}:{question.strip()}".encode()).hexdigest()
    question_marker = cache_dir / f'{question_key}.json'
    if question_marker.exists():
        return {**json.loads(question_marker.read_text(encoding='utf-8')), 'cached': True}
    terms = model().with_structured_output(SearchTerms).invoke([
        ('system', SEARCH), ('human', f"항목: {item['name_en']}\n질문: {question}"),
    ]).terms[:3]
    terms = list(dict.fromkeys([own_title] + terms))
    candidates = {own_title: {'title': own_title, 'snippet': item['description']}}
    pending = []
    for term in terms:
        key = hashlib.sha256(f"{item['id']}:{term.casefold()}".encode()).hexdigest()
        marker = cache_dir / f'{key}.json'
        if marker.exists():
            continue
        result = get(endpoint, {'action': 'query', 'format': 'json', 'list': 'search', 'srsearch': term, 'srlimit': 5})
        for row in result['query']['search']:
            candidates[row['title']] = {'title': row['title'], 'snippet': row['snippet']}
        pending.append(marker)
    if not pending:
        result = {'cached': True, 'terms': terms, 'titles': []}
        question_marker.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        return result
    selected = model().with_structured_output(SelectedTitles).invoke([
        ('system', SELECT), ('human', json.dumps({'item': item['name_en'], 'question': question, 'candidates': list(candidates.values())}, ensure_ascii=False)),
    ]).titles
    titles = list(dict.fromkeys([own_title] + [x for x in selected if x in candidates]))[:6]
    cfg = config()
    splitter = RecursiveCharacterTextSplitter(chunk_size=cfg['chunk_size'], chunk_overlap=cfg['chunk_overlap'])
    _, store = stores()
    collected = []
    for title in titles:
        payload = get(endpoint, {'action': 'query', 'format': 'json', 'prop': 'extracts|info|revisions', 'explaintext': 1, 'inprop': 'url', 'rvprop': 'ids|timestamp', 'redirects': 1, 'titles': title})
        page = next(iter(payload['query']['pages'].values()))
        text = page.get('extract', '')
        if not text.strip():
            if title == own_title:
                raise ValueError('선택한 주류 자체의 문서를 확보하지 못했습니다.')
            continue
        revision = page['revisions'][0]['revid']
        info = {'item_id': item['id'], 'title': page['title'], 'source_url': page['fullurl'], 'source_type': 'Wikipedia', 'license': 'CC-BY-SA-4.0', 'revision_url': f'https://{language}.wikipedia.org/w/index.php?oldid={revision}'}
        chunks = splitter.split_text(text)
        ids = [f"{item['id']}:{language}wiki-{page['pageid']}:{i}" for i in range(len(chunks))]
        for start in range(0, len(chunks), 64):
            store.add_documents([Document(page_content=x, metadata=info) for x in chunks[start:start + 64]], ids=ids[start:start + 64])
        # Remove old tail chunks if the source was shortened.
        existing = store.get(where={'$and': [{'item_id': item['id']}, {'source_url': page['fullurl']}]})['ids']
        stale = set(existing) - set(ids)
        if stale:
            store.delete(ids=list(stale))
        collected.append(page['title'])
    result = {'cached': False, 'terms': terms, 'titles': collected}
    # Write success markers only after collection and embeddings have completed.
    for marker in pending:
        marker.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    question_marker.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result
