<img width="3000" height="500" alt="Brain Trace (3)" src="https://github.com/user-attachments/assets/8f92baaa-158e-4475-b34a-5f1f440649ac" />

<p align="center"><i>A Knowledge Management System Utilizing Knowledge Graphs</i></p>

Brain Trace System (BrainT) converts documents of various formats, such as PDF, TXT, DOCX, and Markdown, into a knowledge graph through a GraphRAG pipeline upon upload. It extracts key concepts and their relationships from the documents, organizing them into a node-edge structure. Based on this, it provides inferential search, source tracing, and visual exploration within a single, streamlined flow.

When a user inputs a query, BrainT identifies relevant concepts from the knowledge graph to form context. It then retrieves similar document chunks to generate a Q&A response grounded in both this context and supporting evidence. This entire process can be operated selectively in either local or cloud environments, allowing for flexible configuration as needed and supporting security-friendly operation where information does not leave internal servers.

As more documents are added, the graph becomes increasingly sophisticated, and both search and exploration grow smarter. Scattered information becomes organically connected, allowing knowledge not just to accumulate, but to evolve into a structured, living entity.

---

## System Architecture

![시스템 아키텍처](https://github.com/user-attachments/assets/232bcdbe-6238-4b5b-8e5d-cace17a23d94)

---

## Knowledge Graph Generation Pipeline

<p>BrainTrace converts various types of learning materials into a knowledge graph through the following five steps.</p>

<img width="2048" height="800" alt="flowchart_height_800" src="https://github.com/user-attachments/assets/f8efb47b-f155-466f-809b-d4ff0568e508" />

1.** Text Extraction**:
   Extracts text from sources such as PDFs, text files, memos, Markdown, and DOCX files.

   ```python
# backend/routers/brain_graph.py (Excerpt)
@router.get("/getSourceContent",
    summary="Get text content of a source file",
    description="Returns the text content based on the file type for a given source_id.")
async def get_source_content(source_id: str, brain_id: str):
    db = SQLiteHandler()
    pdf = db.get_pdf(int(source_id))
    textfile = db.get_textfile(int(source_id))
    memo = db.get_memo(int(source_id))
    md = db.get_mdfile(int(source_id))
    docx = db.get_docxfile(int(source_id))
    if pdf:
        content = pdf.get('pdf_text', '')
        title = pdf.get('pdf_title', '')
        file_type = 'pdf'
    elif textfile:
        content = textfile.get('txt_text', '')
        title = textfile.get('txt_title', '')
        file_type = 'textfile'
    # ... (Title inclusion for memo/md/docx branches as well)
    return {"content": content, "title": title, "type": file_type}
   ```

2. **Tokenization**:
   Splits the extracted text into meaningful units (e.g., sentences, noun phrases).

   ```python
   # backend/services/node_gen_ver5.py (Excerpt)
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
          return tokenized_sentences, texts
      ```

3. **Chunking**:
      Groups similar sentences by topic, splitting the entire text into chunks between 1000 and 2000 characters. This process generates the backbone of the knowledge graph.

   ```python
   # backend/services/manual_chunking_sentences.py (Exerpt)
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
   ```

4. **Node and Edge Generation from final chunks**:
   Extracts concepts (nodes) and relationships (edges) from each chunk.

   ```python
   # backend/services/node_gen_ver5.py (Exerpt)
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
    lang ="ko"

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
   ```

5. **Graph Merging**:
   Merges the nodes/edges from all chunks into a unified knowledge graph.
   ```python
   # backend/neo4j_db/Neo4jHandler.py (Exerpt)
   def insert_nodes_and_edges(self, nodes, edges, brain_id):
           """Batch saves (MERGE) nodes and edges to Neo4j.
   
           - descriptions/original_sentences are normalized and saved as a list of JSON strings.
           - Merges lists ensuring no duplication with existing items.
           """
           def _insert(tx, nodes, edges, brain_id):
               # Save nodes
               for node in nodes:
                   # Convert descriptions to JSON strings
                   new_descriptions = []
                   for desc in node.get("descriptions", []):
                       if isinstance(desc, dict):
                           new_descriptions.append(json.dumps(desc, ensure_ascii=False))
   
                   # Convert original_sentences to JSON strings
                   new_originals = []
                   for orig in node.get("original_sentences", []):
                       if isinstance(orig, dict):
                           new_originals.append(json.dumps(orig, ensure_ascii=False))
   
                   tx.run(
                       """
                       MERGE (n:Node {name: $name, brain_id: $brain_id})
                       ON CREATE SET
                           n.label = $label,
                           n.brain_id = $brain_id,
                           n.descriptions = $new_descriptions,
                           n.original_sentences = $new_originals
                       ON MATCH SET 
                           n.label = $label, 
                           n.brain_id = $brain_id,
                           n.descriptions = CASE 
                               WHEN n.descriptions IS NULL THEN $new_descriptions 
                               ELSE n.descriptions + [item IN $new_descriptions WHERE NOT item IN n.descriptions] 
                           END,
                           n.original_sentences = CASE
                               WHEN n.original_sentences IS NULL THEN $new_originals
                               ELSE n.original_sentences + [item IN $new_originals WHERE NOT item IN n.original_sentences]
                           END
                       """,
                       name=node["name"],
                       label=node["label"],
                       new_descriptions=new_descriptions,
                       new_originals=new_originals,
                       brain_id=brain_id
                   )
   
               # Save edges
               for edge in edges:
                   tx.run(
                       """
                       MATCH (a:Node {name: $source, brain_id: $brain_id})
                       MATCH (b:Node {name: $target, brain_id: $brain_id})
                       MERGE (a)-[r:REL {relation: $relation, brain_id: $brain_id}]->(b)
                       """,
                       source=edge["source"],
                       target=edge["target"],
                       relation=edge["relation"],
                       brain_id=brain_id
                   )
      ```

---

## Chunking Function Process
<p>The chunking function is called recursively and repeats the following actions.</p>

<img width="960" height="460" alt="image" src="https://github.com/user-attachments/assets/ce93db48-6e44-4520-8d28-b4c3d6ea2623" />

1. **Noun Phrase Extraction**: Splits the text into sentences and extracts noun phrases.

   ```python
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
   ```

2. **Topic Vector Conversion & Similarity Calculation**: Converts each sentence into a topic vector and calculates the similarity between vectors, storing them in a matrix.

   ```python
   # backend/services/manual_chunking_sentences.py (발췌)
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
   ```

3. **Grouping**: Forms chunks by setting boundaries between thematically different sentences.

    ```python
    # backend/services/manual_chunking_sentences.py (Excerpt)
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
    ```

4. **Generate Nodes and Edges from Each Chunk**: Extracts TF-IDF keywords from each chunk and generates nodes and edges.

   ```python
   # backend/services/manual_chunking_sentences.py (Excerpt)
def extract_keywords_by_tfidf(tokenized_chunks: list[list[str]]):
    """Extracts top TF-IDF keywords from a list of tokenized chunks.

    Args:
        tokenized_chunks: A list of token lists for each group.

    Returns:
        all_sorted_keywords: A list of keyword lists for each group.
    """
    # 1. Define Vectorizer
    vectorizer = TfidfVectorizer(
        stop_words=stop_words,
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
    ```

For a more detailed explanation of the knowledge graph, please see KNOWLEDGE_GRAPH.md.

---

## Results

<div style="margin-left:20px;">

<details open>
<summary>&nbsp;<b>Home</b></summary>

![Home](https://github.com/user-attachments/assets/4b7aaf24-4aa0-48e2-9a05-6552227d85d6)

</details>

<details open>
<summary>&nbsp;<b>Main page</b></summary>

![Main Page](https://github.com/user-attachments/assets/787208fc-36d7-4942-9e6f-c9cf88ac3151)

</details>

</div>

### Main Feature Demo

<table style="background-color:#ffffff; border-collapse:separate; border-spacing:10px;">
  <tr>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/97312636-239b-4b67-89b2-0d66bee06c63" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Create New Project</b></div>
      <div align="center"><sub>You can start a new project by selecting its name and environment.</sub></div>
    </td>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/d6da0b94-91fd-403b-98a8-176905c8f4e9" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Graph Generation on Upload</b></div>
      <div align="center"><sub>When you upload a file, nodes and edges are automatically generated and reflected in the graph.</sub></div>
    </td>
  </tr>
  <tr><td colspan="2" style="height:16px;"></td></tr>
  <tr style="background-color:#ffffff;">
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/cfa1261a-5c2b-4205-ab56-88d42dc13f73" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Source Highlighting</b></div>
      <div align="center"><sub>You can click a specific source to view its content and highlight it.</sub></div>
    </td>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/3037ef1f-a1ae-4eea-9316-9d440bdc0d97" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Nodes Referenced After Q&A</b></div>
      <div align="center"><sub>Nodes used in the answer can be viewed in the graph.</sub></div>
    </td>
  </tr>
  <tr><td colspan="2" style="height:16px;"></td></tr>
  <tr style="background-color:#ffffff;">
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/1993ab88-c964-4a55-870d-432dd724c602" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>View Sources</b></div>
      <div align="center"><sub>Check which sources the nodes used in the answer referred to.</sub></div>
    </td>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/1e08bce0-c322-43b0-8f8c-91e231e8bee5" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>View Source Nodes</b></div>
      <div align="center"><sub>View nodes generated by a specific source in the graph.</sub></div>
    </td>
  </tr>
  <tr><td colspan="2" style="height:16px;"></td></tr>
  <tr style="background-color:#ffffff;">
    <td width="50%" valign="top" style="padding:8px; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/1c7bebe5-246b-4495-9fda-9758d610740a" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Create Memo and Add as Source</b></div>
      <div align="center"><sub>You can write a memo and convert it into a source to be reflected in the graph.</sub></div>
    </td> 
    <td width="50%" valign="top" style="padding:8px; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/afe3a647-cb89-47ec-a024-0b2516f154c9" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Create Memo from Voice</b></div>
      <div align="center"><sub>Converts recorded audio to text and saves it as a memo.</sub></div>
    </td>
  </tr>
  <tr><td colspan="2" style="height:16px;"></td></tr>
  <tr style="background-color:#ffffff;">
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/79a58805-a6b2-4e08-88ff-6dfe9d301acd" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Delete Source</b></div>
      <div align="center"><sub>Deleting a specific source also deletes the nodes generated from that source.</sub></div>
    </td>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/8497e9c6-d81d-4419-8509-8336fb8ab666" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Explore Feature</b></div>
      <div align="center"><sub>Find similar sources by file content or keywords.</sub></div>
    </td>
  </tr>
  <tr><td colspan="2" style="height:16px;"></td></tr>
  <tr>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://github.com/user-attachments/assets/921bb0fd-0812-4e5a-ad12-fcb24cec4b76" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Graph view Light Mode: Node Search</b></div>
      <div align="center"><sub>Move the camera to the desired node using node search.</sub></div>
    </td>
    <td width="50%" valign="top" style="padding:0; background-color:#ffffff; border:2px solid #000000;">
      <img src="https://raw.githubusercontent.com/yes6686/portfolio/main/전체화면 다크모드.gif" width="100%" style="border:4px solid #cfd8e3;border-radius:8px;" />
      <div align="center"><b>Graph View Dark Mode</b></div>
      <div align="center"><sub>Explore the graph in a dark theme and freely adjust its properties.</sub></div>
    </td>
  </tr>
</table>

---

## Demonstration Video

<div align="center">
  <a href="https://youtu.be/CkKStA9WHhY" target="_blank">
    <img src="https://img.youtube.com/vi/CkKStA9WHhY/maxresdefault.jpg" alt="데모 비디오" style="width:70%; max-width:500px; border:2px solid #ddd; border-radius:10px; box-shadow:0 4px 8px rgba(0,0,0,0.2); transition: transform 0.2s;" />
  </a>
</div>

---

## Team

|                         President / Full Stack                         |                                Backend                                 |                               DevOps                               |                                AI                                 |
| :---------------------------------------------------------------: | :--------------------------------------------------------------------: | :----------------------------------------------------------------: | :---------------------------------------------------------------: |
| <img src="https://github.com/yes6686.png?size=200" width="100" /> | <img src="https://github.com/kimdonghyuk0.png?size=200" width="100" /> | <img src="https://github.com/Mieulchi.png?size=200" width="100" /> | <img src="https://github.com/selyn-a.png?size=200" width="100" /> |
|               [안예찬](https://github.com/yes6686)                |               [김동혁](https://github.com/kimdonghyuk0)                |               [유정균](https://github.com/Mieulchi)                |               [장세린](https://github.com/selyn-a)                |

---

For licensing information, please see the LICENSE file in the repository.
