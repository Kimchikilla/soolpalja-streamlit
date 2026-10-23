"""Collect actual CC0 Wikidata records and revision-linked Wikipedia documents.

Run: python scripts/collect_data.py --limit 160
Network responses are cached, so interrupted collection can be resumed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import threading
from datetime import datetime, timezone
from urllib.parse import unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / 'data'
SESSION = requests.Session()
SESSION.headers['User-Agent'] = os.getenv('WIKIMEDIA_USER_AGENT', 'SoolPalja-Education/0.1 (SSAFY local educational prototype)')
SESSION.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], respect_retry_after_header=True)))
REQUEST_LOCK = threading.Lock()
NEXT_REQUEST = 0.0


def get(url, params):
    global NEXT_REQUEST
    cache = DATA / 'cache'
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = cache / f'{key}.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    # Concurrent downloads still start at most one request per second globally.
    with REQUEST_LOCK:
        time.sleep(max(0, NEXT_REQUEST - time.monotonic()))
        NEXT_REQUEST = time.monotonic() + 1
    response = SESSION.get(url, params=params, timeout=60)
    response.raise_for_status()
    result = response.json()
    if 'error' in result:
        raise RuntimeError(str(result['error']))
    path.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result


def save(name, value):
    DATA.mkdir(exist_ok=True)
    path = DATA / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def main(limit):
    existing = DATA / 'alcohols.json'
    if existing.exists() and any(x.get('category') != 'cocktail' for x in json.loads(existing.read_text(encoding='utf-8'))):
        raise SystemExit('확장된 데이터가 있어 칵테일 전용 수집으로 덮어쓰지 않습니다. expand_catalog.py와 supplement_korean.py를 사용하세요.')
    query = '''SELECT ?item ?itemLabel ?itemDescription ?article ?links WHERE {
      { SELECT DISTINCT ?item ?article ?links WHERE {
        ?item wdt:P31/wdt:P279* wd:Q134768; wikibase:sitelinks ?links .
        ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/> .
      } ORDER BY DESC(?links) LIMIT %d }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
    } ORDER BY DESC(?links)''' % limit
    rows = get('https://query.wikidata.org/sparql', {'query': query, 'format': 'json'})['results']['bindings']
    now = datetime.now(timezone.utc).isoformat()
    items = []
    for row in rows:
        url = row['article']['value']
        items.append({
            'id': row['item']['value'].rsplit('/', 1)[1],
            'name': row['itemLabel']['value'],
            'name_en': unquote(url.rsplit('/wiki/', 1)[1]).replace('_', ' '),
            'category': 'cocktail',
            'description': row.get('itemDescription', {}).get('value', ''),
            'source_url': row['item']['value'].replace('http:', 'https:').replace('/entity/', '/wiki/'),
            'document_url': url,
            'sitelinks': int(row['links']['value']),
            'license': 'CC0-1.0',
            'collected_at': now,
            'abv': None,
            'sweetness': None,
        })
    save('alcohols.json', items)
    documents = []
    errors = []
    for start in range(0, len(items), 15):
        batch = items[start:start + 15]
        try:
            response = get('https://en.wikipedia.org/w/api.php', {
                'action': 'query', 'format': 'json', 'redirects': 1,
                'prop': 'extracts|info|revisions', 'explaintext': 1, 'exlimit': 'max', 'exintro': 1,
                'inprop': 'url', 'rvprop': 'ids|timestamp',
                'titles': '|'.join(item['name_en'] for item in batch),
            })
            aliases = {x['from']: x['to'] for x in response['query'].get('normalized', [])}
            aliases.update({x['from']: x['to'] for x in response['query'].get('redirects', [])})
            pages = {p['title']: p for p in response['query']['pages'].values()}
            for item in batch:
                title = item['name_en']
                seen = set()
                while title in aliases and title not in seen:
                    seen.add(title)
                    title = aliases[title]
                page = pages.get(title)
                if not page or not page.get('extract', '').strip():
                    errors.append({'item_id': item['id'], 'reason': 'missing page or empty extract'})
                    continue
                revision = page['revisions'][0]
                documents.append({
                    'id': f"enwiki-{page['pageid']}", 'item_id': item['id'],
                    'title': page['title'], 'text': page['extract'],
                    'source_url': page['fullurl'],
                    'revision_url': f"https://en.wikipedia.org/w/index.php?oldid={revision['revid']}",
                    'revision_id': revision['revid'], 'revision_timestamp': revision['timestamp'],
                    'source_type': 'Wikipedia', 'language': 'en',
                    'license': 'CC-BY-SA-4.0', 'collected_at': now,
                    'attribution': f"English Wikipedia contributors, {page['title']}; see revision history at {page['fullurl']}?action=history",
                    'transformations': 'Lead section extracted as plain text via MediaWiki API; no translation or generated facts.',
                })
                item['document_id'] = documents[-1]['id']
            save('documents.json', documents)
            save('alcohols.json', items)
            print(f'Collected {len(items)} items / {len(documents)} documents', flush=True)
        except Exception as exc:
            errors.append({'batch_start': start, 'reason': type(exc).__name__})
            print(f'Batch {start} failed: {type(exc).__name__}', flush=True)
    report = {
        'collected_at': now, 'item_count': len(items), 'unique_item_count': len({x['id'] for x in items}),
        'document_count': len(documents), 'linked_item_count': sum('document_id' in x for x in items),
        'total_document_characters': sum(len(d['text']) for d in documents),
        'minimum_100_items': len(items) >= 100, 'all_items_have_documents': all('document_id' in x for x in items),
        'selection': 'Wikidata cocktail instances/subclasses with English Wikipedia, ordered by sitelinks; popularity proxy, not a verified mainstream ranking.',
        'errors': errors,
    }
    save('collection_report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['minimum_100_items'] or not report['all_items_have_documents']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=160)
    main(parser.parse_args().limit)
