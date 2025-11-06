"""
OpenAI 기반 그래프 추출/질의응답 서비스
-------------------------------------

이 모듈은 OpenAI API를 활용해 텍스트로부터 노드/엣지(그래프 구성요소)를 추출하고,
그래프 컨텍스트(스키마 텍스트)와 질문을 기반으로 답변을 생성하는 기능을 제공합니다.

핵심 기능:
- 긴 텍스트(≥2000자) 청킹 처리 후 각 청크에서 노드/엣지 추출
- 추출된 노드의 description과 문장 임베딩 간 유사도 기반으로 original_sentences 산출
- 스키마 텍스트를 생성하여 LLM 질의응답에 활용
- 답변의 맨 끝(JSON 영역)에서 referenced_nodes를 파싱하여 노드 참조 목록을 추출

환경 변수:
- OPENAI_API_KEY: OpenAI API 호출에 사용 (dotenv를 통해 로드)

주의:
- 본 모듈은 외부 API 호출을 포함하므로, 장애/요금/레이트 리밋 고려가 필요합니다.
- 임베딩/유사도 계산(threshold)은 휴리스틱으로, 도메인에 맞게 조정하세요.
"""


import logging
from openai import OpenAI           # OpenAI 클라이언트 임포트
import json
from .base_ai_service import BaseAIService
from typing import List
from .manual_chunking_sentences import manual_chunking
import numpy as np
import os
from dotenv import load_dotenv  # dotenv 추가
from . import embedding_service
from sklearn.metrics.pairwise import cosine_similarity



# ✅ .env 파일에서 환경 변수 로드
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

if not openai_api_key:
    raise ValueError("❌ OpenAI API Key가 설정되지 않았습니다. generate_answerㅎ.env 파일을 확인하세요.")

# ✅ OpenAI 클라이언트 설정 (노드/엣지 추출에 활용)
# client = OpenAI(api_key=openai_api_key)
client = OpenAI(api_key=openai_api_key)


class OpenAIService(BaseAIService) :
    """OpenAI API를 사용해 그래프 추출/QA를 수행하는 서비스 구현체."""
    def __init__(self, model_name="gpt-4o"):
        # 인스턴스 속성으로 클라이언트 할당
        self.client = OpenAI(api_key=openai_api_key)
        self.model_name = model_name  # 모델명 저장

    def extract_referenced_nodes(self,llm_response: str) -> List[str]:
        """
        LLM 응답 문자열에서 EOF 뒤의 JSON을 파싱하여 referenced_nodes만 추출합니다.

        - '레이블-노드' 형식일 경우 레이블과 '-'을 제거하고 노드 이름만 반환
        - EOF 이후 JSON이 없거나 파싱 실패 시 빈 리스트 반환
        """
        parts = llm_response.split("EOF")
        if len(parts) < 2:
            return []

        json_part = parts[-1].strip()
        try:
            payload = json.loads(json_part)
            # payload가 리스트인 경우 빈 리스트 반환
            if isinstance(payload, list):
                return []
            # payload가 딕셔너리인 경우에만 get() 호출
            raw_nodes = payload.get("referenced_nodes", [])
            cleaned = [
                node.split("-", 1)[1] if "-" in node else node
                for node in raw_nodes
            ]
            return cleaned
        except json.JSONDecodeError:
            return []
            
    def generate_referenced_nodes(self, llm_response: str, brain_id: str) -> List[str]:
        """
        LLM이 생성한 답변을 임베딩하여 일정 유사도 이상의 노드들을 참고한 노드로 반환
        
        Args:
            llm_response: LLM이 생성한 답변 텍스트
            brain_id: 검색할 brain의 ID
        
        Returns:
            유사도 0.7 이상인 노드들의 name 리스트
        """
        # 지식그래프에 정보가 없다는 응답인 경우 빈 리스트 반환
        if "지식그래프에 해당 정보가 없습니다" in llm_response:
            logging.info("지식그래프에 정보 없음 - 빈 리스트 반환")
            return []
        
        try:
         
            # LLM 응답을 임베딩
            response_embedding = embedding_service.encode_text(llm_response)
            
            # 벡터DB에서 유사한 노드 검색 (threshold 0.7)
            # search_similar_nodes는 (nodes, score_avg) 튜플을 반환
            similar_nodes, avg_score = embedding_service.search_similar_nodes(
                embedding=response_embedding, 
                brain_id=brain_id,
                limit=20,  # limit 파라미터 사용 (top_k가 아님)
                threshold=0.7  # threshold 명시
            )
            
            if not similar_nodes:
                logging.info("답변과 유사한 노드를 찾지 못했습니다.")
                return []
            
            # 유사도 0.7 이상인 노드만 필터링
            threshold = 0.7
            referenced_nodes = []
            
            for node in similar_nodes:
                # node는 {"name": ..., "score": ...} 형태
                if node.get("score", 0) >= threshold:
                    referenced_nodes.append(node["name"])
            
            logging.info(f"✅ 유사도 {threshold} 이상인 {len(referenced_nodes)}개 노드를 참조 노드로 선정")
            if referenced_nodes:
                # 상위 10개만 반환 (너무 많은 노드 방지)
                if len(referenced_nodes) > 10:
                    referenced_nodes = referenced_nodes[:10]
                    logging.info("상위 10개 노드만 선택")
                
                logging.info(f"선정된 노드: {', '.join(referenced_nodes[:5])}{'...' if len(referenced_nodes) > 5 else ''}")
            
            return referenced_nodes
            
        except Exception as e:
            logging.error(f"generate_referenced_nodes 처리 중 오류 발생: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return []

    def _remove_duplicate_nodes(self, nodes: list) -> list:
        """중복된 노드를 제거합니다.

        - 동일 (name, label) 조합을 하나로 합치고, descriptions는 병합합니다.
        """
        seen = set()
        unique_nodes = []
        for node in nodes:
            node_key = (node["name"], node["label"])
            if node_key not in seen:
                seen.add(node_key)
                unique_nodes.append(node)
            else:
                # 같은 이름의 노드가 있으면 descriptions만 추가
                for existing_node in unique_nodes:
                    if existing_node["name"] == node["name"] and existing_node["label"] == node["label"]:
                        existing_node["descriptions"].extend(node["descriptions"])
        return unique_nodes

    def _remove_duplicate_edges(self, edges: list) -> list:
        """중복된 엣지를 제거합니다. (source, target, relation) 동일 시 하나만 유지"""
        seen = set()
        unique_edges = []
        for edge in edges:
            edge_key = (edge["source"], edge["target"], edge["relation"])
            if edge_key not in seen:
                seen.add(edge_key)
                unique_edges.append(edge)
        return unique_edges

    def generate_answer(self, schema_text: str, question: str) -> str:
        """
        지식그래프 컨텍스트와 질문을 기반으로 AI를 호출하여 최종 답변을 생성합니다.
        """
        logging.info("🚀 OpenAI API 호출 - 모델: %s", self.model_name)
        
        prompt = (
            "Please answer the question below in natural language, using only the information explicitly provided in the knowledge graph context or that can be reasonably inferred from the relationships. "
            "If relevant information exists, explain it as fully as possible. If the context provides no relevant information, respond with: 'The knowledge graph does not contain this information.'"
            "Knowledge Graph Context Format:\n"
            "1. Relationships: start_name -> relation_label -> end_name\n"
            "2. Nodes: NODE: {node_name} | DESCRIPTION: {desc_str}"
            "Knowledge Graph Context:\n{schema_text}\n"
            "Question: {question}\n"
            "Output:\n[Provide a detailed answer based on the knowledge graph, or write 'The knowledge graph does not contain this information.']"
            )


        try:
        
            response = client.chat.completions.create(
                model=self.model_name,  # 동적 모델 선택
                messages=[{"role": "user", "content": prompt}]
            )
            response = response.choices[0].message.content

            print("response: ", response)
            final_answer = response
            return final_answer
        except Exception as e:
            logging.error("GPT 응답 오류: %s", str(e))
            raise RuntimeError("GPT 응답 생성 중 오류 발생")
    

    def generate_schema_text(self, nodes, related_nodes, relationships) -> str:
        """
        위: start_name -> relation_label -> end_name (한 줄씩, 중복 제거)
        아래: 모든 노드(관계 있든 없든) 중복 없이
            {node_name}: {desc_str}
        desc_str는 original_sentences[].original_sentence를 모아 공백 정리 및 중복 제거
        """
        


        def to_dict(obj):
            """입력 객체를 dict로 관용적으로 변환(Neo4j 레코드/객체 호환용)."""
            try:
                if obj is None:
                    return {}
                if hasattr(obj, "items"):
                    return dict(obj.items())
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            return {}

        def normalize_space(s: str) -> str:
            """연속 공백을 단일 공백으로 정규화."""
            return " ".join(str(s).split())

        def filter_node(node_obj):
            """노드 레코드/객체에서 name/label/original_sentences만 추출/정규화."""
            d = to_dict(node_obj)
            name = normalize_space(d.get("name", "알 수 없음") or "")
            label = normalize_space(d.get("label", "알 수 없음") or "")
            original_sentences = d.get("original_sentences", []) or []
            parsed = []
            # 문자열이면 JSON 파싱 시도
            if isinstance(original_sentences, str):
                try:
                    original_sentences = [json.loads(original_sentences)]
                except Exception:
                    original_sentences = []
            # 리스트 요소들 정규화
            for item in original_sentences:
                if isinstance(item, str):
                    try:
                        obj = json.loads(item)
                        if isinstance(obj, dict):
                            parsed.append(obj)
                    except Exception:
                        continue
                elif isinstance(item, dict):
                    parsed.append(item)
            return {"name": name, "label": label, "original_sentences": parsed}

        logging.info(
            "generating schema text: %d개 노드, %d개 관련 노드, %d개 관계",
            len(nodes) if isinstance(nodes, list) else 0,
            len(related_nodes) if isinstance(related_nodes, list) else 0,
            len(relationships) if isinstance(relationships, list) else 0,
        )

        # 1) 모든 노드 수집 (name 키로 합치기)
        all_nodes = {}
        if isinstance(nodes, list):
            for n in nodes or []:
                if n is None: continue
                nd = filter_node(n)
                if nd["name"]:
                    all_nodes[nd["name"]] = nd
        if isinstance(related_nodes, list):
            for n in related_nodes or []:
                if n is None: continue
                nd = filter_node(n)
                if nd["name"] and nd["name"] not in all_nodes:
                    all_nodes[nd["name"]] = nd

        # 2) 관계 줄 만들기: "start -> relation -> end"
        relation_lines = []
        connected_names = set()
        if isinstance(relationships, list):
            for rel in relationships:
                try:
                    if rel is None:
                        continue
                    start_d = to_dict(getattr(rel, "start_node", {}))
                    end_d   = to_dict(getattr(rel, "end_node", {}))
                    start_name = normalize_space(start_d.get("name", "") or "알 수 없음")
                    end_name   = normalize_space(end_d.get("name", "") or "알 수 없음")

                    # relation label: props.relation 우선, 없으면 type, 없으면 "관계"
                    try:
                        rel_props = dict(rel)
                    except Exception:
                        rel_props = {}
                    relation_type = getattr(rel, "type", None)
                    relation_label = rel_props.get("relation") or relation_type or "관계"
                    relation_label = normalize_space(relation_label)

                    relation_lines.append(f"{start_name} -> {relation_label} -> {end_name}")
                    connected_names.update([start_name, end_name])
                except Exception as e:
                    logging.exception("관계 처리 오류: %s", e)
                    continue

        # 관계 중복 제거 + 정렬
        relation_lines = sorted(set(relation_lines))

        # 3) 노드 설명 만들기: 모든 노드(관계 여부 무관)
        def extract_desc_str(node_data):
            # original_sentences[].original_sentence 모아 공백 정리 + 중복 제거
            seen = set()
            pieces = []
            for d in node_data.get("original_sentences", []):
                if isinstance(d, dict):
                    t = normalize_space(d.get("original_sentence", "") or "")
                    if t and t not in seen:
                        seen.add(t)
                        pieces.append(t)
            if not pieces:
                return ""
            s = " ".join(pieces)
            
            return s

        node_lines = []
        for name in sorted(all_nodes.keys()):  # ✅ 관계 없어도 모든 노드 출력
            nd = all_nodes.get(name) or {}
            desc = extract_desc_str(nd)
            if desc:
                node_lines.append(f"{name}: {desc}")
            else:
                node_lines.append(f"{name}:")  # 설명이 비면 콜론만

        # 4) 최종 출력: 위엔 관계들, 아래엔 노드들
        top = "\n".join(relation_lines)
        bottom = "\n".join(node_lines)

        if top and bottom:
            raw_schema_text = f"{top}\n\n{bottom}"
        elif top:
            raw_schema_text = top
        elif bottom:
            raw_schema_text = bottom
        else:
            raw_schema_text = "컨텍스트에서 해당 정보를 찾을 수 없습니다."

        logging.info("컨텍스트 텍스트 생성 완료 (%d자)", len(raw_schema_text))
        return raw_schema_text


    def chat(self, message: str) -> str:
        """
        단일 프롬프트를 Ollama LLM에 보내고,
        모델 응답 문자열만 리턴합니다.
        """
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,  # 동적 모델 선택
                messages=[{"role": "user", "content": message}],
                stream=False
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"chat 오류: {e}")
            raise
