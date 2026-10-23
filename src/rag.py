import re
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.documents import Document
from .settings import model
from .prompts import ANSWER
from .store import retrieve


class State(TypedDict):
    item: dict
    question: str
    history: list
    evidence: list[Document]
    answer: str
    used_evidence: list


def format_evidence(evidence):
    return '\n\n'.join(f"[근거 {i}] 유형: {d.metadata['source_type']} / 제목: {d.metadata['title']}\n{d.page_content}" for i, d in enumerate(evidence, 1))


def cited_evidence(answer, evidence):
    numbers = {int(x) for x in re.findall(r'\[근거\s+(\d+)\]', answer)}
    return [{'number': i, **d.metadata} for i, d in enumerate(evidence, 1) if i in numbers]


def retrieve_node(state):
    return {'evidence': retrieve(state['item'], state['question'])}


def generate_node(state):
    evidence = state['evidence']
    if not evidence:
        return {'answer': '수집한 문서에서 확인되지 않습니다.', 'used_evidence': []}
    # Date of birth and MBTI are never sent to the factual Q&A model.
    messages = [('system', ANSWER)]
    messages.extend((x['role'], x['content']) for x in state.get('history', [])[-6:])
    messages.append(('human', f"질문: {state['question']}\n\n근거:\n{format_evidence(evidence)}"))
    answer = model().invoke(messages).content
    return {'answer': answer, 'used_evidence': cited_evidence(answer, evidence)}


def build_graph():
    graph = StateGraph(State)
    graph.add_node('retrieve', retrieve_node)
    graph.add_node('generate', generate_node)
    graph.add_edge(START, 'retrieve')
    graph.add_edge('retrieve', 'generate')
    graph.add_edge('generate', END)
    return graph.compile()
