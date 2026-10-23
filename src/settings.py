import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
if os.getenv('GMS_KEY') and not os.getenv('OPENAI_API_KEY'):
    os.environ['OPENAI_API_KEY'] = os.environ['GMS_KEY']


def config():
    values = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    if not 0 <= values['chunk_overlap'] < values['chunk_size']:
        raise ValueError('청크 중복 길이는 청크 크기보다 작아야 합니다.')
    if values['top_k'] < 1:
        raise ValueError('Top-k는 1 이상이어야 합니다.')
    return values


def api_ready():
    load_dotenv(ROOT / '.env', override=True)
    if os.getenv('GMS_KEY'):
        os.environ['OPENAI_API_KEY'] = os.environ['GMS_KEY']
    return bool(os.getenv('OPENAI_API_KEY', '').strip())


def model():
    api_ready()
    from langchain_openai import ChatOpenAI
    options = {'model': os.getenv('CHAT_MODEL', 'gpt-4o-mini'), 'temperature': 0.3, 'timeout': 60, 'max_retries': 2}
    if os.getenv('OPENAI_BASE_URL'):
        options['base_url'] = os.environ['OPENAI_BASE_URL']
    return ChatOpenAI(**options)


def embeddings():
    api_ready()
    from langchain_openai import OpenAIEmbeddings
    options = {'model': os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')}
    if os.getenv('OPENAI_BASE_URL'):
        options['base_url'] = os.environ['OPENAI_BASE_URL']
    return OpenAIEmbeddings(**options)
