import os
import hashlib
import json
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .catalog import item_text, load_catalog, load_documents
from .settings import ROOT, config, embeddings


def chroma_path():
    from pathlib import Path
    return Path(os.environ.get('CHROMA_PATH', '/tmp/soolpalja-chroma' if os.environ.get('VERCEL') else str(ROOT / 'data/chroma')))


def stores():
    cfg = config()
    common = {'persist_directory': str(chroma_path()), 'embedding_function': embeddings()}
    return Chroma(collection_name=cfg['collection_meta'], **common), Chroma(collection_name=cfg['collection_docs'], **common)


def restore_deployment_index():
    """Restore bundled public-source vectors without embedding API calls."""
    import gzip
    import chromadb
    bundle = ROOT / 'data/deployment_index.json.gz'
    if not bundle.exists():
        return False
    client = chromadb.PersistentClient(path=str(chroma_path()))
    cfg = config()
    names = [cfg['collection_meta'], cfg['collection_docs'], cfg.get('collection_saju', 'saju_reference')]
    existing = {c.name: c for c in client.list_collections()}
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    marker = chroma_path() / 'deployment-bundle.sha256'
    if marker.exists() and marker.read_text() == digest and all(name in existing and existing[name].count() for name in names):
        return False
    with gzip.open(bundle, 'rt', encoding='utf-8') as source:
        payload = json.load(source)
    for collection in payload['collections']:
        target = client.get_or_create_collection(collection['name'])
        for start in range(0, len(collection['entries']), 64):
            batch = collection['entries'][start:start + 64]
            target.upsert(ids=[e['id'] for e in batch], documents=[e['document'] for e in batch],
                          metadatas=[e['metadata'] for e in batch], embeddings=[e['embedding'] for e in batch])
    marker.write_text(digest)
    return True


def index_counts():
    path = chroma_path()
    if not path.exists():
        return (0, 0)
    import chromadb
    client = chromadb.PersistentClient(path=str(path))
    names = {x.name for x in client.list_collections()}
    cfg = config()
    return tuple(client.get_collection(cfg[key]).count() if cfg[key] in names else 0 for key in ['collection_meta', 'collection_docs'])


def metadata(item):
    info = {'item_id': item['id'], 'title': item['name'], 'category': item['category'], 'item_kind': item.get('item_kind', 'drink_style'), 'source_url': item['source_url'], 'source_type': '항목 메타데이터', 'license': item['license']}
    if item.get('origin'):
        info['origin'] = item['origin']
    return info


def saju_store():
    return Chroma(collection_name=config().get('collection_saju', 'saju_reference'), persist_directory=str(chroma_path()), embedding_function=embeddings())


def index_saju():
    path = ROOT / 'data/saju_documents.json'
    if not path.exists():
        return 0
    cfg = config()
    splitter = RecursiveCharacterTextSplitter(chunk_size=cfg['chunk_size'], chunk_overlap=cfg['chunk_overlap'])
    store = saju_store()
    chunks, ids = [], []
    for doc in json.loads(path.read_text(encoding='utf-8')):
        for index, text in enumerate(splitter.split_text(doc['text'])):
            info = {k: doc[k] for k in ['title', 'source_url', 'source_type', 'license', 'revision_url', 'language']}
            chunks.append(Document(page_content=text, metadata=info))
            ids.append(f"{doc['id']}:{index}")
    for start in range(0, len(ids), 64):
        store.add_documents(chunks[start:start + 64], ids=ids[start:start + 64])
    stale = set(store.get()['ids']) - set(ids)
    if stale:
        store.delete(ids=sorted(stale))
    return len(store.get()['ids'])


def index_all():
    meta, docs = stores()
    items = load_catalog()
    meta.add_documents([Document(page_content=item_text(x), metadata=metadata(x)) for x in items], ids=[x['id'] for x in items])
    cfg = config()
    splitter = RecursiveCharacterTextSplitter(chunk_size=cfg['chunk_size'], chunk_overlap=cfg['chunk_overlap'])
    chunks, ids = [], []
    for document in load_documents():
        texts = splitter.split_text(document['text'])
        for index, text in enumerate(texts):
            key = f"{document['item_id']}:{document['id']}:{index}"
            info = {k: document[k] for k in ['item_id', 'title', 'source_url', 'source_type', 'license', 'revision_url', 'collected_at']}
            chunks.append(Document(page_content=text, metadata=info))
            ids.append(key)
    # Delete only stale IDs after adding the replacement chunks successfully.
    for start in range(0, len(chunks), 64):
        docs.add_documents(chunks[start:start + 64], ids=ids[start:start + 64])
    stale = set(docs.get()['ids']) - set(ids)
    if stale:
        docs.delete(ids=sorted(stale))
    stale_meta = set(meta.get()['ids']) - {x['id'] for x in items}
    if stale_meta:
        meta.delete(ids=sorted(stale_meta))
    # Full rebuild replaces on-demand chunks; invalidate only collection success markers.
    cache_dir = ROOT / 'data/cache/collection'
    if cache_dir.exists():
        for marker in cache_dir.glob('*.json'):
            marker.unlink()
    report = {'metadata_count': len(meta.get()['ids']), 'document_chunk_count': len(docs.get()['ids']), 'saju_chunk_count': index_saju(), 'config': cfg}
    (ROOT / 'data/index_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def retrieve(item, question):
    meta, docs = stores()
    cfg = config()
    selected = meta.get(ids=[item['id']])
    if not selected['ids']:
        raise ValueError('메타데이터 색인이 없습니다. 색인을 먼저 실행하세요.')
    evidence = [Document(page_content=selected['documents'][0], metadata=selected['metadatas'][0])]
    options = {'k': cfg['top_k'], 'filter': {'item_id': item['id']}}
    if cfg['search_type'] == 'mmr':
        found = docs.max_marginal_relevance_search(question, fetch_k=cfg['fetch_k'], **options)
    else:
        found = docs.similarity_search(question, **options)
    seen = set()
    unique = []
    for document in evidence + found:
        key = hashlib.sha256((document.metadata['source_url'] + document.page_content).encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(document)
    return unique
