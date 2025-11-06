"""
Recursive Chunking and Graph Backbone Generation Module
------------------------------------------------------

This module splits/tokenizes text into sentences using a rule-based (manual) approach,
and recursively chunks it using LDA/TF-IDF/adjacency similarity, etc.,
to generate keyword nodes/edges.

Component Overview:
- `extract_keywords_by_tfidf`: Extracts top TF-IDF keywords from each chunk's tokens
- `lda_keyword_and_similarity`: Estimates full/partial topics via LDA and calculates the topic distribution similarity matrix
- `recurrsive_chunking`: Similarity-based recursive chunking (considers termination conditions/depth/token count, etc.)
- `extract_graph_components`: Executes the entire pipeline -> Builds nodes/edges
- `manual_chunking`: Returns only chunking results for source-less (-1) cases

Notes:
- Depends on external libraries such as morphological analyzers (Okt) and gensim LDA. It may take time on large texts.
- Recursive chunking prevents infinite division through termination conditions (depth, token count, similarity matrix validity, etc.).
"""

import logging
import re
from gensim import corpora, models
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from collections import defaultdict
from .node_gen_ver5 import _extract_from_chunk
from .node_gen_ver5 import split_into_tokenized_sentence
from .node_gen_ver5 import store_embeddings

stopwords_en= [
    "the", "an", "which", "they", "this", "you", "me", "I"
]


def extract_keywords_by_tfidf(tokenized_chunks: list[list[str]]):
       """Extracts top TF-IDF keywords from a list of tokenized chunks.
   
       Args:
           tokenized_chunks: A list of token lists for each group.
   
       Returns:
           all_sorted_keywords: A list of keyword lists for each group.
       """
       # 1. Define Vectorizer
       vectorizer = TfidfVectorizer(
           stop_words=stopwords_en,
           max_features=1000,
           tokenizer=lambda x: x,      # Use the input (token list) as is
           preprocessor=lambda x: x,  # Skip preprocessing
           token_pattern=None,        # Prevent warning
           lowercase=False            # Prevents 'list' object has no attribute 'lower' error when skipping preprocessing/tokenization
       )
       # 2. Calculate TF-IDF
       try:
           tfidf_matrix = vectorizer.fit_transform(tokenized_chunks)
       except ValueError as e:
           # Case where all documents consist of stop words or are empty, resulting in an empty vocabulary
           if "empty vocabulary" in str(e):
               return [[] for _ in tokenized_chunks]
           else:
               raise e
   
       feature_names = vectorizer.get_feature_names_out()
   
       # 3. Sort keywords by group
       all_sorted_keywords = []
       for i in range(tfidf_matrix.shape[0]):
           row = tfidf_matrix[i].toarray().flatten()
   
           # Sort indices in descending order of TF-IDF score
           sorted_indices = row.argsort()[::-1]
   
           # Add 'all' keywords with a score greater than 0, in order
           sorted_keywords = [
               feature_names[j] 
               for j in sorted_indices  # Removed top_n slicing
               if row[j] > 0            # Exclude words with a score of 0
           ]
   
           all_sorted_keywords.append(sorted_keywords)
   
       return all_sorted_keywords


def grouping_into_smaller_chunks(chunk:list[int], similarity_matrix:np.ndarray, threshold:int):
    """
    Creates smaller groups from the input group based on a threshold.
    It references the similarity matrix and groups consecutive sentences if their similarity is at or above the threshold.
    The threshold is set to the minimum of {the threshold passed for the current depth} and {the 9th smallest similarity value between consecutive sentences}.
    This is to prevent more than 10 child nodes from being generated at a single level.

    Args:
        chunk: The input group, a list of sentence indices.
        similarity_matrix: The matrix storing similarity values between sentences.
        threshold: The threshold value used as the criterion for grouping.

    returns:
        new_chunk_groups: The newly created smaller groups.
    """
    num_sentences = len(chunk)
    # Case where there are more than 10 sentences
    if num_sentences >10:
        # Extract similarities of consecutive sentences and sort them in ascending order
        gaps = []
        for i in range(1, num_sentences):
            sim = similarity_matrix[chunk[i]][chunk[i-1]]
            gaps.append(sim)
        gaps.sort()
        threshold=min(threshold, gaps[8])
        
    new_chunk_groups = []
    visited = set()
    for idx in range(len(chunk)):
        if idx in visited:
            continue
        new_chunk = [idx]
        visited.add(idx)
        for next_idx in range(idx + 1, len(chunk)):
            if next_idx in visited:
                continue
            if similarity_matrix[chunk[next_idx]][chunk[next_idx-1]]>=threshold:
                new_chunk.append(next_idx)
                visited.add(next_idx)
            else:
                break
        new_chunk_groups.append(new_chunk)

    return new_chunk_groups


def check_termination_condition(chunk: list[dict], depth:int):
    """
    Checks if the termination condition for the recursive function is met and returns a flag.
        flag 1: chunk size is 15 tokens or less
        flag 2: depth is 5 or more and chunk size is 500 tokens or less
        flag 3: depth is 5 or more and chunk size exceeds 500 tokens

    """
    flag=-1
    size = sum([len(c["tokens"]) for c in chunk])
    # flag 1: If the chunk size is 15 tokens or less, do not split further
    if size<=15:
        flag=1
    
    # If depth is 5 or more, do not search deeper
    if(depth >= 5):
        flag=2
        # If depth is 5 or more but size is over 500 tokens, split up to 5 times based on similarity (flag 3 logic)
        if (size>500):
            flag=3

    return flag


def nonrecurrsive_chunking(chunk:list[dict], similarity_matrix:np.ndarray, top_keyword:str):
    """
    depth 5 이상인데 청크가 500토큰 이하인 경우,
    최대 5개의 그룹으로 분할하여 반환합니다.
    이렇게 생성된 5개의 그룹은 지식 그래프의 깊이가 너무 깊어지는 것을 방지하기 위해
    각 청크를 위한 키워드를 생성하지 않고 입력 청크의 키워드(top_keyword)를 해당 그룹의 키워드로 합니다.

    Args:
        chunk: 입력 청크
        similarity_matrix: 각 문장간 유사도를 저장한 행렬
        top_keyword: 입력 청크의 키워드
    
    Return:
        result: 분할한 그룹을 저장한 리스트, 각 그룹을 구성하는 문장 인덱스
    """
    length=len(chunk)
    num_chunks= length if length<5 else 5
    consec_similarity=[] #현재 청크 내부의 연속적인 index간의 유사도만 저장
    for i in range(length-1):
        current=chunk[i]["index"]
        next=chunk[i+1]["index"]
        consec_similarity.append(similarity_matrix[current][next]) 
    consec_similarity=sorted(consec_similarity, key=lambda x:x[0], reverse=True)[:num_chunks]
    consec_similarity=sorted(consec_similarity, key=lambda x:x[1], reverse=True)

    for _, idx in consec_similarity:
            result+=[{ "chunks": [c["index"] for c in chunk if c["index"]<=idx],
                    "keyword": top_keyword}]
    
    return result


def gen_node_edges_for_new_groups(chunk:list[dict], new_chunk_groups, top_keyword, already_made, source_id):
    """
    Converts groups, represented as index lists, into the chunk format for the next recursive call.
    Extracts keywords from each chunk to create nodes.
    Creates edges connecting the generated nodes to the keyword node of the current depth.

    Args:
        chunk: Full chunk information for the current depth.
        new_chunk_groups: Newly generated group information represented as a list of sentence indices.
        already_made: A list storing the names of already created nodes.
    """

    # Generate go_chunk and get_topics based on the sentence indices stored in new_chunk_group
    # go_chunk is the argument for the recursively called function to perform chunking again
    # get_topics is the argument for the function to extract core keywords from the newly divided chunk groups
    go_chunk = []
    get_topics = []
    for group in new_chunk_groups:
        go_chunk_temp = []
        get_topics_temp = []
        for mem in group:
            get_topics_temp += chunk[mem]["tokens"]
            go_chunk_temp.append(chunk[mem])
        go_chunk.append(go_chunk_temp)
        get_topics.append(get_topics_temp)


    # Create nodes and edges based on the chunking results from this step
    keywords=[]
    nodes=[]
    edges=[]

    chunk_topics=extract_keywords_by_tfidf(get_topics)
    # Select one non-duplicate topic keyword extracted via TF-IDF as the representative keyword for each chunk
    # Create a node with the representative keyword of each chunk
    for idx, topics in enumerate(chunk_topics):
        for t_idx in range(len(topics)):
            # If the topic keyword is not an already created node keyword, create a node
            if topics[t_idx] not in already_made:
                # If the length of the sentences from which the topic keyword is derived is 15 tokens or less, save the sentences as the description
                if sum([len(sentence["tokens"]) for sentence in go_chunk[idx]])< 15:
                    chunk_node={"label":topics[t_idx],"name":topics[t_idx],
                                "descriptions":[c["index"] for c in go_chunk[idx]],
                                "source_id":source_id}
                    edge={"source": top_keyword, "target": topics[t_idx], "relation":"Related"}
                    keywords.append(topics[t_idx])
                # If the length of the sentences from which the topic keyword is derived is long, create a node with an empty description
                else:
                    connective_node=topics[t_idx]+"*"
                    chunk_node={"label":topics[t_idx],"name":connective_node,"descriptions":[], "source_id":source_id}
                    edge={"source": top_keyword, "target": connective_node, "relation":"Related"}
                    keywords.append(connective_node)
                nodes.append(chunk_node)
                edges.append(edge)
                already_made.append(topics[t_idx])
                break
    
    # If the number of topic keywords is less than the number of chunks due to keyword duplication, etc.
    check_num_t=len(go_chunk)-len(keywords)
    if check_num_t > 0:
        keywords+=check_num_t*["none"]

    
    return nodes, edges, go_chunk, keywords


def recurrsive_chunking(chunk: list[int], source_id:str ,depth: int, top_keyword:str ,already_made:list[str], similarity_matrix, threshold: int):
    """Recursive chunking based on similarity/keywords.

    Logic Summary:
      - At depth=0, estimate the main topic keyword (top_keyword) for the entire text using LDA and calculate the initial threshold.
      - At depth>0, determine termination based on adjacent similarity, token count, or depth limit.
      - If termination conditions are not met, group based on similarity and recursively split.
      - At each step, construct representative keyword nodes and child keyword nodes/edges.

    Args:
        chunk: A list of (tokenized sentence, index) pairs ({"tokens", "index"}) to be split at the current step.
        source_id: Source identifier (for graph node metadata).
        depth: Current recursion depth (starts at 0).
        already_made: A name cache to prevent duplicate node creation.
        top_keyword: The representative keyword passed from the parent step (or estimated by LDA at depth=0).
        threshold: The similarity threshold for adjacent sentences (initial value calculated at depth=0).
        lda_model, dictionary, num_topics: Parameters related to LDA estimation.

    Returns:
        Tuple[list[dict], dict, list[str]]: (List of chunking results, {"nodes", "edges", "keyword"}, updated already_made)
    """
    result=[]
    nodes_and_edges={"nodes":[], "edges":[]}
    chunk_indices=[c["index"] for c in chunk] # Create a list storing only the indices of sentences within the current group


    if depth == 0:
        # Use LDA to find the keywords of the entire text and the similarity between topics of each chunk
        # If depth is 0, the topic inferred by LDA for the entire text becomes the top keyword for this chunk (==full text)
        top_keyword, similarity_matrix = lda_keyword_and_similarity(chunk)
        already_made.append(top_keyword)
        top_keyword+="*"
        # Create the root node of the knowledge graph
        top_node={"label":top_keyword,
            "name":top_keyword,
            "descriptions":[],
            "source_id":source_id
            }
        nodes_and_edges["nodes"].append(top_node)
        
        # Set the bottom 25% value of the similarity matrix as the initial threshold
        # Afterwards, it is multiplied by 1.1 as the depth increases
        # The smaller of this threshold and {the 10th percentile similarity value of the chunk} becomes the grouping criterion
        # To limit the number of child nodes created in one step to a maximum of 10
        try:
            if similarity_matrix.size > 0:
                flattened = similarity_matrix[np.triu_indices_from(similarity_matrix, k=1)]
                threshold = np.quantile(flattened, 0.25)
            else:
                logging.error("similarity_matrix creation error: empty or invalid matrix")
                return [], {}, []
                
        except Exception as e:
            logging.error(f"Error during threshold calculation: {e}")
            threshold = 0.5  # Set default value

    else:
        # If depth is not 0
        # Check termination condition
        flag = check_termination_condition(chunk, depth)

        if flag==3:
            result = nonrecurrsive_chunking(chunk, similarity_matrix, top_keyword)
            return result, nodes_and_edges, already_made
        
        # Terminate recursion if fetching similarity between chunks fails
        # If depth is 1 or more, the top_keyword is the keyword passed from the previous step (derived from tf-idf)

        # If the chunk size is 3 sentences or less, or 20 tokens or less, do not save the chunk
        # This is because this chunk does not need to generate any more knowledge graph
        elif flag==1:
            logging.info(f"depth {depth} chunking terminated, flag:{flag}")
            return result , nodes_and_edges, already_made

        # If other termination conditions are met
        elif flag != -1:
            result += [{ "chunks":chunk_indices, "keyword": top_keyword}]
            logging.info(f"depth {depth} chunking terminated, flag:{flag}")
            return result , nodes_and_edges, already_made


    # Split the input group into smaller groups
    new_chunk_groups = grouping_into_smaller_chunks(chunk_indices, similarity_matrix, threshold)

    # Extract keywords for the newly created small groups and generate nodes & edges
    nodes, edges, go_chunk, keywords = gen_node_edges_for_new_groups(chunk, new_chunk_groups, top_keyword, already_made, source_id)
    nodes_and_edges["nodes"]+=nodes
    nodes_and_edges["edges"]+=edges
    
    # Recursively call the function to further subdivide the created groups
    current_result = []
    for idx, c in enumerate(go_chunk):
        if idx > len(keywords)-1 or len(keywords)==0:
            logging.error(f"keyword generation error\nkeywords:{keywords}\nnumber of chunks:{len(go_chunk)}")
            break
        result, graph, already_made_updated = recurrsive_chunking(c, source_id ,depth+1, keywords[idx], already_made, similarity_matrix, threshold*1.1,)
        # Update already_made to prevent duplicate nodes from being created
        already_made=already_made_updated
        current_result+=(result)
        nodes_and_edges["nodes"]+=graph["nodes"]
        nodes_and_edges["edges"]+=graph["edges"]

    return current_result, nodes_and_edges, already_made


def lda_keyword_and_similarity(chunk:list[dict]):
    """
    Uses gensim's LDA model to extract topic keywords from the chunk
    and generates topic vectors for each sentence composing the chunk.
    It calculates the similarity between each sentence's topic vectors to create a similarity matrix.
    Returns the extracted topic keyword, the generated LDA model, and the similarity matrix.

    Args:
        chunk: A list of {"tokens": List[str], "index": int}
        lda_model: Reusable LDA model (if not provided, it's trained)
        dictionary: Reusable gensim Dictionary (if not provided, it's created)

    Returns:
        Tuple[str, models.LdaModel, np.ndarray]: (top_keyword, lda_model, similarity_matrix)
    """
    tokens = [c["tokens"] for c in chunk]

    # If the LDA model doesn't exist, train it; otherwise, reuse it
    try:
        dictionary = corpora.Dictionary(tokens)
        corpus = [dictionary.doc2bow(text) for text in tokens]
        lda_model = models.LdaModel(corpus, num_topics=5, id2word=dictionary, passes=20, iterations=400, random_state=8)

    except Exception as e:
        logging.error(f"Error occurred during LDA processing: {e}")
        return "", lda_model, np.array([])

    corpus = [dictionary.doc2bow(text) for text in tokens]

    topic_distributions = []
    for bow in corpus:
        dist = lda_model.get_document_topics(bow, minimum_probability=0)
        dense_vec = [prob for _, prob in sorted(dist, key=lambda x: x[0])]
        topic_distributions.append(dense_vec)

    topic_vectors = np.array(topic_distributions)
    sim_matrix = cosine_similarity(topic_vectors)

    # Extract the top keyword(s) for the first topic from the LDA model
    top_topic_terms = lda_model.show_topic(0, topn= 1)
    # Check if top_topic_terms is not empty and the first element exists
    # (Prevents error if the LDA model failed to generate topics)
    top_keyword = top_topic_terms[0][0] if top_topic_terms and len(top_topic_terms) > 0 else ""

    return top_keyword, sim_matrix


def all_chunks_tf_idf_(tokenized_chunks:list[list[list[str]]]):
    vectorizer = TfidfVectorizer(
        stop_words=stopwords_en,
        max_features=5000,
        tokenizer=lambda x: x,      # Use the input (token list) as is
        preprocessor=lambda x: x,  # Skip preprocessing
        token_pattern=None,        # Prevent warning
        lowercase=False            # Prevents 'list' object has no attribute 'lower' error when skipping preprocessing/tokenization
    )
    flattened_chunks = []
    for chunk in tokenized_chunks:
        # chunk = [ [s1_token1, s1_token2], [s2_token1] ]
        # doc_tokens = [ s1_token1, s1_token2, s2_token1 ]
        doc_tokens = [token for sentence in chunk for token in sentence]
        flattened_chunks.append(doc_tokens)
    try:
        tfidf_matrix = vectorizer.fit_transform(flattened_chunks)

    except ValueError as e:
        # Case where all documents consist of stop words or are empty, resulting in an empty vocabulary
        if "empty vocabulary" in str(e):
            return [[] for _ in tokenized_chunks]
        else:
            raise e
        
    # 1. Get the list of all unique tokens (features).
    feature_names = vectorizer.get_feature_names_out()
    
    # 2. List to store the results.
    tfidf_results = []

    # 3. Iterate through the tfidf_matrix one row at a time.
    #    Each row corresponds to one group.
    for i in range(tfidf_matrix.shape[0]):
        row = tfidf_matrix[i]
        
        # 4. Create a dictionary of scores for tokens that exist only in this row (document).
        #    row.indices: Indices (in feature_names) of tokens present in this document.
        #    row.data: The TF-IDF scores for those tokens.
        chunk_dict = {
            feature_names[col_idx]: score
            for col_idx, score in zip(row.indices, row.data)
        }
        
        tfidf_results.append(chunk_dict)

    return tfidf_results


def extract_graph_components(text: str, id: tuple):
    """Executes the entire pipeline to generate nodes/edges.

    Steps:
      1) Sentence splitting and noun phrase-based tokenization
      2) Decide whether to use recursive chunking based on text length
      3) Generate nodes/edges based on chunking results and sentence indices

    Returns:
      Tuple[List[Dict], List[Dict]]: (List of nodes, List of edges)

    Recursively chunks long texts.
    Short texts extract topics on their own and treat the entire text as a single chunk.
    Extracts and returns nodes and edges from each chunk.
    """
    
    brain_id, source_id = id

    # List to store all nodes and edges
    all_nodes = []
    all_edges = []
    chunks=[]
    
    tokenized, sentences = split_into_tokenized_sentence(text)


    # If the text is 2000 characters or longer, call the recursive chunking function
    if len(text)>=2000:
        chunks, nodes_and_edges, already_made = recurrsive_chunking(tokenized, source_id, 0, "", [],  None, 0)
        if chunks==[]:
            logging.info("Chunking failed.")
            
        logging.info("Chunking completed.")
        all_nodes=nodes_and_edges["nodes"]
        all_edges=nodes_and_edges["edges"]

    # If the text is 1000 characters or less, do not call the recursive chunking function.
    else:
        top_keyword, _ =lda_keyword_and_similarity(tokenized)
        if len(top_keyword)<1:
            logging.error("Failed to extract LDA keyword.")
        already_made=[top_keyword]
        top_keyword+="*"
        chunk=list(range(len(sentences)))
        chunks=[{"chunks":chunk, "keyword":top_keyword}]
        logging.info("Extracting nodes and edges without chunking.")
    

    # For chunks with 3 sentences or less, treat the chunk itself as a node (Note: This comment seems to describe a logic, the next part implements description conversion)
    # Convert each node's description from a list of sentence indices to actual text
    for node in all_nodes:
        resolved_description=""
        if node["descriptions"] != []:
            resolved_description="".join([sentences[idx] for idx in node["descriptions"]])

        node["original_sentences"]=[{"original_sentence":resolved_description,
                                     "source_id":source_id,
                                     "score": 1.0}]
        node["descriptions"]=[{"description":resolved_description, "source_id":source_id}]

        store_embeddings(node, brain_id, None)
    
    chunk_keywords=[]
    chunk_sentences=[]
    tokenized_chunks=[]
    
    for c in chunks:
        chunk_tokens =[]
        chunk_sent=[]
        if "chunks" in c:
            for s_idx in c["chunks"]:
                chunk_tokens.append(tokenized[s_idx]['tokens'])
                chunk_sent.append(sentences[s_idx])
                chunk_keywords.append(c["keyword"])
            tokenized_chunks.append(chunk_tokens)
            chunk_sentences.append(chunk_sent)
    chunk_tfidf = all_chunks_tf_idf_(tokenized_chunks)

    for c_idx in range(len(tokenized_chunks)):
        if chunk_keywords[c_idx] != "":
            nodes, edges, already_made = _extract_from_chunk(tokenized_chunks[c_idx],chunk_sentences[c_idx], id, chunk_keywords[c_idx], already_made, chunk_tfidf[c_idx])
        all_nodes += nodes
        all_edges += edges

    logging.info(f"✅ Total {len(all_nodes)} nodes and {len(all_edges)} edges extracted.")
    return all_nodes, all_edges


def manual_chunking(text:str):
    """
    지식 그래프 생성에 GPT 모델을 사용하기 위해 텍스트를 적절한 크기로 청킹합니다.

    소스 없이 텍스트만 받아 수동 청킹 결과를 반환합니다.

    Returns:
        List[str]: 재귀 청킹 결과(각 청크의 텍스트)
    """

    tokenized, sentences = split_into_tokenized_sentence(text)
    chunks, _, _ =recurrsive_chunking(tokenized, "-1" , 0, [], None, 0, None, None)
    #chunking 결과를 바탕으로, 더 이상 chunking하지 않는 chunk들은 node/edge를

    final_chunks=[]
    for c in chunks:
        chunk=""
        # 각 청크의 문장 인덱스들을 실제 텍스트로 변환
        for idx in c["chunks"]:
            # 인덱스가 sentences 배열의 범위 내에 있는지 확인
            # (인덱스 오류 방지)
            if idx < len(sentences):
                chunk+=sentences[idx]
        final_chunks.append(chunk)

    return final_chunks
