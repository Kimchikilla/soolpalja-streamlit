import json
from .settings import ROOT


def load_catalog():
    return json.loads((ROOT / 'data/alcohols.json').read_text(encoding='utf-8'))


def load_documents():
    return json.loads((ROOT / 'data/documents.json').read_text(encoding='utf-8'))


def item_text(item):
    return f"이름: {item['name']}\n영문명: {item['name_en']}\n주종: {category_label(item['category'])} ({item['category']})\n항목 유형: {item.get('item_kind', 'drink_style')}\n설명: {item['description']}"


CATEGORIES = {'cocktail': '칵테일', 'whisky': '위스키', 'wine': '와인', 'tequila': '데킬라·메스칼',
              'rum': '럼·카샤사', 'soju': '소주', 'baijiu': '백주·고량주', 'brandy': '브랜디',
              'gin': '진', 'vodka': '보드카', 'beer': '맥주', 'traditional': '전통주·사케', 'liqueur': '리큐르'}


def category_label(key):
    return CATEGORIES.get(key, key)
