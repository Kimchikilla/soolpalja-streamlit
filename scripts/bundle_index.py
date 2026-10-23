"""Embed changed public records and export only the static source index."""
import gzip
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.catalog import item_text, load_catalog, load_documents
from src.settings import ROOT, config
from src.store import stores, saju_store, metadata, restore_deployment_index


def main():
    restore_deployment_index()
    cfg = config()
    splitter = RecursiveCharacterTextSplitter(chunk_size=cfg['chunk_size'], chunk_overlap=cfg['chunk_overlap'])
    meta, docs = stores()
    expected = []
    expected.append((meta, [(x['id'], item_text(x), metadata(x)) for x in load_catalog()]))
    rows = []
    for doc in load_documents():
        info = {k: doc[k] for k in ['item_id', 'title', 'source_url', 'source_type', 'license', 'revision_url', 'collected_at']}
        rows.extend((f"{doc['item_id']}:{doc['id']}:{i}", text, info) for i, text in enumerate(splitter.split_text(doc['text'])))
    expected.append((docs, rows))
    rows = []
    for doc in json.loads((ROOT / 'data/saju_documents.json').read_text(encoding='utf-8')):
        info = {k: doc[k] for k in ['title', 'source_url', 'source_type', 'license', 'revision_url', 'language']}
        rows.extend((f"{doc['id']}:{i}", text, info) for i, text in enumerate(splitter.split_text(doc['text'])))
    expected.append((saju_store(), rows))
    payload = {'collections': []}
    for store, rows in expected:
        old = store.get()
        previous = {key: (text, info) for key, text, info in zip(old['ids'], old['documents'], old['metadatas'])}
        changed = [(key, text, info) for key, text, info in rows if previous.get(key) != (text, info)]
        for start in range(0, len(changed), 64):
            batch = changed[start:start + 64]
            store.add_documents([Document(page_content=text, metadata=info) for _, text, info in batch], ids=[key for key, _, _ in batch])
        saved = store.get(ids=[key for key, _, _ in rows], include=['documents', 'metadatas', 'embeddings'])
        entries = [dict(id=key, document=text, metadata=info, embedding=vector.tolist())
                   for key, text, info, vector in zip(saved['ids'], saved['documents'], saved['metadatas'], saved['embeddings'])]
        payload['collections'].append({'name': store._collection.name, 'entries': entries})
        print(store._collection.name, 'total', len(entries), 'updated', len(changed), flush=True)
    destination = ROOT / 'data/deployment_index.json.gz'
    temporary = destination.with_suffix('.tmp.gz')
    with gzip.open(temporary, 'wt', encoding='utf-8') as out:
        json.dump(payload, out, ensure_ascii=False, separators=(',', ':'))
    temporary.replace(destination)


if __name__ == '__main__':
    main()
