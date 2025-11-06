"""
청크로부터 노드&엣지 생성모듈
----------------------------------------

청킹 함수로부터 분할된 작은 텍스트 그룹(청크)에서 노드와 엣지를 추출합니다.
청킹함수가 생성한 지식그래프의 뺘대와 연결되어 하나의 그래프로 병합됩니다.

구성 요소 개요:
- `extract_keywords_by_tfidf`: 각 청크 토큰에서 TF-IDF 상위 키워드 추출
- `lda_keyword_and_similarity`: LDA를 통해 전체/부분 토픽 추정 및 토픽 분포 유사도 행렬 계산
- `recurrsive_chunking`: 유사도 기반 재귀 청킹(종료 조건/깊이/토큰 수 등 고려)
- `extract_graph_components`: 전체 파이프라인 실행 → 노드/엣지 구축
- `manual_chunking`: 소스 없는(-1) 케이스에 대한 청킹 결과만 반환

주의:
- 형태소 분석기(Okt), gensim LDA 등 외부 라이브러리에 의존합니다. 대형 텍스트에서는 시간이 소요될 수 있습니다.
- 재귀 청킹은 종료 조건(depth, 토큰 수, 유사도 행렬 유효성 등)을 통해 무한 분할을 방지합니다.
"""
import logging

#pip install konlpy, pip install transformers torch scikit-learn

import re
from collections import defaultdict
from typing import List, Dict
from konlpy.tag import Okt
from sklearn.metrics.pairwise import cosine_similarity
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from tqdm import tqdm
import spacy
from .embedding_service import store_embeddings
from .embedding_service import get_embeddings_batch
import langid


stopwords = set([
    "사실", "경우", "시절", "내용", "점", "것", "수", "때", "정도", "이유", "상황", "뿐", "매우", "아주", "또한", "그리고", "그러나", "대한", "관한"
])

stopwords_en= set([
    "the", "an", "which", "they", "this", "you", "me"
])


# 한국어용 형태소 분석기
okt = Okt()

# 영어용 spaCy 모델 
nlp_en = spacy.load("en_core_web_sm")


def extract_noun_phrases_ko(sentence: str) -> list[str]:
    """
    문장을 입력 받으면 명사구를 추출하고
    추출한 명사구들의 리스트로 토큰화하여 반환합니다. 
    """
    #문장을 품사를 태깅한 단어의 리스트로 변환합니다.
    words = okt.pos(sentence, norm=True, stem=True)
    phrases=[]
    current_phrase=[]

    for word, tag in words:
        if '\n' in word:
            continue
        elif tag in ["Noun", "Alpha"]:
            if word not in stopwords and len(word) > 1:
                current_phrase.append(word)
        elif tag in ["Adjective", "Verb"] and len(word)>1 and word[-1] not in '다요죠며지만':
            current_phrase.append(word)
        else:
            if current_phrase:
                phrase = " ".join(current_phrase)
                phrases.append(phrase)
                current_phrase = []

    if current_phrase:
        phrase = " ".join(current_phrase)
        phrases.append(phrase)

    return phrases

def extract_noun_phrases_en(sentence: str) -> list[str]:
    """
    Extracts noun phrases from an English sentence.
    """
    doc = nlp_en(sentence)
    phrases = []

    # Use spaCy's noun_chunks
    for chunk in doc.noun_chunks:
        phrase = chunk.text.strip()
        phrase=phrase.lower()
        if phrase  not in stopwords_en and len(phrase)>=2:
            phrases.append(phrase)

    return phrases


    
def compute_phrase_embedding(
    phrase: str,
    indices: List[int],
    sentences: List[str],
    lang:str
) -> tuple[str, tuple[float, np.ndarray], np.ndarray]:
    """
    Gets the embeddings of sentences containing a specific phrase and returns their average vector.
    - phrase: The current word/phrase being processed.
    - indices: List of sentence indices where the phrase appears.
    - sentences: The complete list of sentences.
    Returns: (phrase, avg_emb, embeddings)
    """
    # Highlighting
    highlighted_texts = [sentences[idx].replace(phrase, f"[{phrase}]") for idx in indices]

    # Sentence embeddings
    embeddings = get_embeddings_batch(highlighted_texts, lang)  # shape: (N, D)
    embeddings = np.atleast_2d(embeddings)

    # Calculate average vector
    avg_emb = np.mean(embeddings, axis=0)
    avg_emb = np.ravel(avg_emb)  # shape (D,)

    return phrase, avg_emb, embeddings

# Function to calculate the importance score of each keyword
# Calculates centrality score by similarity to the central vector and multiplies by tf score to derive importance score.
def compute_scores(
    phrase_info: List[dict], 
    sentences: List[str],
    lang:str,
    tfidf:dict
) -> tuple[Dict[str, tuple[float, np.ndarray]], List[str], np.ndarray]:
    scores = {}
    all_embeddings = {}
    total_sentences = len(sentences)

    phrase_embeddings = {}
    central_vecs = []

    # Embed sentences where each keyword appears, then average them to create a semantic vector for each keyword.
    # Also, calculates the tf score for each keyword (Note: TF-IDF is retrieved from the input dict).
    with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(compute_phrase_embedding, phrase, indices, sentences, lang)
                for phrase, indices in phrase_info.items()
            ]

            for future in tqdm(as_completed(futures), total=len(futures), desc="Embedding phrases"):
                phrase, avg_emb, embedded_vec = future.result()
                phrase_embeddings[phrase] =  avg_emb
                all_embeddings[phrase]=embedded_vec
                central_vecs.append(avg_emb)

    # Calculate the central vector representing the chunk's topic by averaging the embedding values of all sentences in the chunk.
    central_vec = np.mean(central_vecs, axis=0)

    # Calculate the centrality score for each keyword by computing similarity with the central vector.
    # Finally, calculate the importance score of each keyword by multiplying with the tf score.
    # The top 5 keywords by importance score will be selected as nodes (Note: This function provides scores; selection happens elsewhere).
    phrases = list(phrase_embeddings.keys())
    tf_list = []
    emb_list = []

    for phrase in phrases:
        emb = phrase_embeddings[phrase]
        tf_adj = tfidf[phrase] * cosine_similarity([emb], [central_vec])[0][0]
        scores[phrase] = [tf_adj, emb]
        tf_list.append(tf_adj)
        emb_list.append(emb)

    emb_array = np.stack(emb_list)
    sim_matrix = cosine_similarity(emb_array)

    return scores, phrases, sim_matrix, all_embeddings


#유사도를 기반으로 각 명사구를 그룹으로 묶음
#상위 5개의 노드를 먼저 선별하고 걔네끼리만 유사도를 계산하면 더 빠를듯
def group_phrases(
    phrases: List[str],
    phrase_scores: List[dict],
    sim_matrix: np.ndarray,
    threshold: float = 0.98
) ->dict:
    ungrouped = list(range(len(phrases)))  # 인덱스 기반으로
    groups = []

    while ungrouped:
        i = ungrouped.pop()
        group = [i]
        to_check = set()

        for j in ungrouped:
            if sim_matrix[i][j] >= threshold:
                to_check.add(j)

        #같은 그룹이 되기 위해서는 그룹 내 모든 명사구들과 유사도가 임계값 이상이어야함
        valid_members = []
        for j in to_check:
            if all(sim_matrix[j][k] >= threshold for k in group):
                valid_members.append(j)

        for j in valid_members:
            group.append(j)
            ungrouped.remove(j)

        groups.append(group)

    # 대표 명사구 설정: 중심성 점수가 가장 높은 것
    group_infos = {}
    for group in groups:
        sorted_group =sorted(group, key=lambda idx: phrase_scores[phrases[idx]][0], reverse=True)
        representative=sorted_group[0]
        group_infos[phrases[representative]]=sorted_group[1:]

    return group_infos


def make_edges(sentences:list[str], source_keyword:str, target_keywords:list[str], phrase_info):
    """
    Takes the root node (source keyword) and surrounding nodes (target keywords - multiple) as input,
    and generates edges between them.
    """
    edges=[]
    source=source_keyword[:-1] if source_keyword[-1] == "*" else source_keyword
    if source in phrase_info.keys():
        source_idx = [idx for idx in phrase_info[source]]
    else:
        source_idx=[]
    for t in target_keywords:
        if t != source:
            target_idx=[idx for idx in phrase_info[t]]
            relation=""
            cnt=0
            for s_idx in source_idx:
                if cnt>=4:
                    break
                if s_idx in target_idx:
                    edges.append({"source":source_keyword, 
                    "target":t,
                    "relation":sentences[s_idx]})
                    cnt+=1
            
            if cnt==0:
                edges.append({"source":source_keyword, 
                    "target":t,
                    "relation":"Related"})
        
    return edges

def make_node(name, phrase_info, sentences:list[str], id:tuple, embeddings):
    """
    노드를 만들 키워드와 키워드의 등장 위치를 입력 받아 노드를 생성합니다.
    args:   name: 노드를 만들 키워드
            phrase_info: 해당 키워드의 등장 인덱스
            sentences: 전체 텍스트가 문장 단위로 분해된 string의  list
            source_id: 입력 문서의 고유 source_id       
    """
    description=[]
    ori_sentences=[]
    s_indices=[idx for idx in phrase_info[name]]
    brain_id, source_id=id

    if len(s_indices)<=2:
        for idx in s_indices:
            description.append({"description":sentences[idx],
                            "source_id":source_id})
            ori_sentences.append({"original_sentence":sentences[idx],
                            "source_id":source_id,
                            "score": 1.0})   

    else:
        description.append({"description":"",
                        "source_id":source_id})
        ori_sentences.append({"original_sentence":"",
                        "source_id":source_id,
                        "score": 1.0})   
    
    node={"label":name, "name":name,"source_id":source_id, "descriptions":description, "original_sentences":ori_sentences}
    store_embeddings(node, brain_id, embeddings)

    return node


def split_into_tokenized_sentence(text: str) -> tuple[List, List[str]]:
    """
    Splits the text into sentences.
   
    Logic:
    1. Split the text into text chunks and \n based on the newline character (\n).
    2. Iterate through the text chunks. When a \n is encountered, check the length of the *preceding text* chunk.
    3. If the length is 25 characters or less, treat \n as a valid sentence separator.
       (This is to detect titles/subheadings.)
    4. If the length is over 25 characters, ignore the \n (replace it with a space) and merge it with the next text chunk.
       (This is considered a case where a sentence continues onto the next line.)
    5. For these reconstructed text chunks (merged_lines),
       apply the intra_line_pattern regex to perform the final sentence splitting.
    """
    
    tokenized_sentences: List[dict] = [] # Changed to List[dict] to match the return type
    final_sentences: List[str] = []
    
    cleaned_text = text.strip()
    if not cleaned_text:
        return (tokenized_sentences, final_sentences)
   
    intra_line_pattern = r'(?<=[.!?])\s+|(?<=[다요]\.)\s*|(?<=[^a-zA-Z가-힣\s,()[]{}=-%^$@])\s+'
    
    # [ List marker split pattern ]
    list_marker_split_pattern = r'(?=[0-9a-zA-Z가-힣]\.\s+)'
    list_marker_pattern_for_removal = r'\s+[0-9a-zA-Z가-힣]\.'
   
    # [ Step 1: Newline Handling ]
    blocks = re.split(r'(\n)', cleaned_text)
    
    merged_lines = []
    current_line = ""
    
    for block in blocks:
        if block == '\n':
            # When \n is encountered, check the currently accumulated current_line
            stripped_line = current_line.strip()
            
            if not stripped_line:
                # Handle empty lines (consecutive \n)
                current_line = ""
                continue
            
            # [Core Logic]
            # Only recognize \n as a separator if the previous text chunk is 25 characters or less
            if len(stripped_line) <= 25:
                merged_lines.append(stripped_line) # Recognized as a separator (added as a separate chunk)
                current_line = ""                 # Start a new chunk
            else:
                # If over 25 chars, replace \n with a space and connect to the next chunk
                current_line += " " 
        else:
            # If it's a text chunk (not \n), add it to the current line
            current_line += block
            
    # Process the last remaining text chunk after the loop finishes
    stripped_last_line = current_line.strip()
    if stripped_last_line:
        merged_lines.append(stripped_last_line)
   
    # [ Step 2: Sentence splitting with regex ]
    candidate_sentences = []
    for line in merged_lines:
        # Both short lines (<= 25 chars) and long merged lines (> 25 chars)
        # attempt to split them further using intra_line_pattern
        sub_sentences = re.split(intra_line_pattern, line)
        candidate_sentences.extend(sub_sentences)
   
   
    # [Step 3: List Filtering]
    # Apply filtering logic to all sentence candidates
    for s in candidate_sentences:
        s = s.strip()
        if not s:
            continue
   
        # Perform additional splitting before list markers (1., a., etc.)
        sub_fragments = re.split(list_marker_split_pattern, s)
   
        for fragment in sub_fragments:
            fragment = fragment.strip()
   
            # Detect and remove list markers ("1. ", "a. ")
            fragment = re.sub(list_marker_pattern_for_removal, '', fragment)
            fragment = fragment.strip() # Remove any remaining whitespace after marker removal
            
            if not fragment:
                continue
   
            # Original filtering logic (length, actual character count)
            real_chars = re.sub(r'[^a-zA-Z0-9가-힣]', '', fragment)
            if len(fragment) <= 1 or len(real_chars) <= 1:
                continue
            
            # Final sentence fragment that passed filtering
            final_sentences.append(fragment)
   
    texts = final_sentences
    
    lang="en"
    # Detect the language of each sentence and embed using the appropriate embedding model
    for idx, sentence in enumerate(texts):
        lang = check_lang(sentence)
   
        # Call Korean embedding model
        if lang == "ko":
            tokens = extract_noun_phrases_ko(sentence)
        # Call English embedding model
        elif lang == "en":
            tokens = extract_noun_phrases_en(sentence)
        else:
            tokens = [sentence.strip()]
   
        if not tokens:
            tokens = [sentence.strip()]
            logging.error(f"Text included that is neither Korean nor English: {sentence}")
   
        tokenized_sentences.append({"tokens": tokens, "index": idx})
   
    return tokenized_sentences, texts


        

def _extract_from_chunk(phrases:list[list[str]], sentences: list[str], id:tuple ,keyword: str, already_made:list[str], tfidf:dict) -> tuple[dict, dict, list[str]]:
    """
    Called with the finally divided (finalized) chunk as input.
    Calculates importance scores for keywords within the chunk and generates nodes and edges based on these scores.
    Connects the generated nodes to the {topic keyword node passed from the chunking function} via edges,
    linking them to the knowledge graph created by the chunking function.
    """
    nodes=[]
    edges=[]

    # To enable searching for all sentence indices where a specific noun phrase appears,
    # create a dictionary where each noun phrase is a key, 
    # and the value is a list of indices of sentences where it appeared.
    phrase_info = defaultdict(set)
    lang ="en"

    for idx, p in enumerate(phrases):
        for token in p:
            phrase_info[token].add(idx)
    
    # Calculate the importance score for each keyword
    phrase_scores, phrases, sim_matrix, all_embeddings = compute_scores(phrase_info, sentences, lang, tfidf)
    # Group highly similar keywords; if one keyword in a group is selected as a node, other members become child nodes.
    groups=group_phrases(phrases, phrase_scores, sim_matrix)

    # Sort the topic keywords by score
    sorted_keywords = sorted(phrase_scores.items(), key=lambda x: x[1][0], reverse=True)
    sorted_keywords=[k[0] for k in sorted_keywords]

    contents=phrase_info.keys()

    # Create a node for the chunk's topic keyword (received from the chunking function)
    cnt=0
    if keyword != "":
        if keyword[-1]=="*":
            find = keyword[:-1]
        else:
            find = keyword
        if find in contents:
            nodes.append(make_node(keyword, list(phrase_info[find]), sentences, id, all_embeddings[find]))
        else:
            return [], [], already_made

    # Create nodes for the top 5 high-scoring keywords, excluding duplicates (those already created as nodes)
    for t in sorted_keywords:
        # Create edges between {the chunk's topic keyword node} and {the top-scoring keywords within the chunk}
        if keyword != "":
            edges+=make_edges(sentences, keyword, [t], phrase_info)

        else:
            break
        if t not in already_made:
            nodes.append(make_node(t, list(phrase_info[t]), sentences, id, all_embeddings[t]))
            already_made.append(t)
            cnt+=1
            
            # If there are keywords highly similar to the selected node, create them as child nodes
            if t in groups:
                related_keywords=[]
                for idx in range(min(len(groups[t]), 5)):
                    if phrases[idx] not in already_made:
                        related_keywords.append(phrases[idx])
                        already_made.append(phrases[idx])
                        node=make_node(phrases[idx], list(phrase_info[t]), sentences, id, all_embeddings[phrases[idx]])
                        nodes.append(node)
                        edge=make_edges(sentences, t, related_keywords, phrase_info)
                        edges+=edge  
                    
        if cnt==5:
            break
    return nodes, edges, already_made

def check_lang(text:str):
    lang, _ =langid.classify(text)
    return lang