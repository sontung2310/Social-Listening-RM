# AI/Topic_detection/Topic_detection.py
from __future__ import annotations
import sys
import os
import json
import re
from typing import Dict, List, Tuple
from collections import Counter

# Add the AI directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_dir = os.path.dirname(current_dir)
sys.path.insert(0, ai_dir)

_WORD = re.compile(r"[A-Za-z0-9]+")

_STOP = {
    "the","a","an","and","or","but","if","then","else","when","while","is","of","to","in","for",
    "on","by","with","as","at","from","that","this","it","its","be","are","was","were","has","had",
    "have","not","no","we","you","they","he","she","them","his","her","their","our","i",
    "will","would","can","could","may","might","should","also","about","into","over","under"
}

def detect_topic_simple(text: str, max_terms: int = 4) -> str:
    """
    Picks top informative terms as a compact topic label.
    """
    toks = [t.lower() for t in _WORD.findall(text or "") if t]
    toks = [t for t in toks if t not in _STOP and len(t) > 2]
    if not toks:
        return ""
    freq = Counter(toks)
    top = [w for w,_ in freq.most_common(8)]
    # de-duplicate stems crudely
    seen = set()
    label_terms = []
    for w in top:
        stem = w[:5]
        if stem not in seen:
            seen.add(stem)
            label_terms.append(w)
        if len(label_terms) >= max_terms:
            break
    return " ".join(label_terms).title()

class TopicDetector:
    """Advanced topic detection system with multiple strategies"""

    def __init__(self, strategy: str = "nlp", max_chunk_size: int = 3000, use_topic_modeling: bool = True):
        """
        Initialize the topic detector

        Args:
            strategy: Detection strategy - 'nlp' (default), 'llm', or 'hybrid'
            max_chunk_size: Maximum words per chunk for long documents
            use_topic_modeling: Use LDA/NMF topic modeling for better results (NLP only)
        """
        self.strategy = strategy
        self.max_chunk_size = max_chunk_size
        self.use_topic_modeling = use_topic_modeling

    def detect_topics(self, text: str) -> Dict:
        """
        Main method to detect topics from text

        Args:
            text: Input text document

        Returns:
            Dictionary with main_topics, subtopics, and keywords
        """
        if not text or len(text.strip()) == 0:
            return {
                "main_topics": [],
                "subtopics": {},
                "keywords": []
            }

        if self.strategy == "llm":
            return self._llm_based_detection(text)
        elif self.strategy == "nlp":
            return self._nlp_based_detection(text)
        else:  # hybrid
            return self._hybrid_detection(text)

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split long text into manageable chunks

        Args:
            text: Input text

        Returns:
            List of text chunks
        """
        words = text.split()
        chunks = []

        for i in range(0, len(words), self.max_chunk_size):
            chunk = " ".join(words[i:i + self.max_chunk_size])
            chunks.append(chunk)

        return chunks

    def _llm_based_detection(self, text: str) -> Dict:
        """
        Use LLM (Groq API) to detect topics

        Args:
            text: Input text

        Returns:
            Topic detection results
        """
        chunks = self._chunk_text(text)
        all_results = []

        for i, chunk in enumerate(chunks):
            prompt = f"""You are an expert topic detection system. Analyze the following text and identify:
1. Main topics (high-level themes)
2. Subtopics for each main topic
3. Important keywords

Text to analyze:
{chunk}

Respond ONLY with valid JSON in this exact format:
{{
  "main_topics": ["topic1", "topic2"],
  "subtopics": {{
    "topic1": ["subtopic1", "subtopic2"],
    "topic2": ["subtopic1", "subtopic2"]
  }},
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}

Do not include any explanation or additional text. Only return the JSON."""

            try:
                response = load_model(prompt, max_tokens=1000, temperature=0.3, stream=False)

                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    all_results.append(result)

            except Exception as e:
                print(f"[LLM Detection Error] Chunk {i+1}: {e}")
                continue

        # Merge results from all chunks
        return self._merge_results(all_results)

    def _nlp_based_detection(self, text: str) -> Dict:
        """
        Use advanced NLP techniques (LDA, TF-IDF, NER, noun extraction) to detect topics
        NO API CALLS - completely offline

        Args:
            text: Input text

        Returns:
            Topic detection results
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
            from sklearn.decomposition import LatentDirichletAllocation, NMF
            import nltk
            from nltk.tokenize import sent_tokenize, word_tokenize
            from nltk.corpus import stopwords
            from nltk import pos_tag
            import numpy as np

            # Download required NLTK data
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                nltk.download('punkt', quiet=True)

            try:
                nltk.data.find('corpora/stopwords')
            except LookupError:
                nltk.download('stopwords', quiet=True)

            try:
                nltk.data.find('taggers/averaged_perceptron_tagger')
            except LookupError:
                nltk.download('averaged_perceptron_tagger', quiet=True)

            # Tokenize into sentences
            sentences = sent_tokenize(text)
            if len(sentences) < 2:
                sentences = [text]

            # ===== TOPIC MODELING WITH LDA =====
            main_topics_lda = []
            if self.use_topic_modeling and len(sentences) >= 3:
                try:
                    # Use CountVectorizer for LDA
                    count_vectorizer = CountVectorizer(
                        max_features=100,
                        stop_words='english',
                        ngram_range=(1, 3),
                        min_df=1,
                        max_df=0.95
                    )

                    count_matrix = count_vectorizer.fit_transform(sentences)
                    feature_names = count_vectorizer.get_feature_names_out()

                    # Determine optimal number of topics
                    n_topics = min(5, max(2, len(sentences) // 3))

                    # LDA topic modeling
                    lda = LatentDirichletAllocation(
                        n_components=n_topics,
                        max_iter=20,
                        learning_method='online',
                        random_state=42,
                        n_jobs=-1
                    )

                    lda.fit(count_matrix)

                    # Extract top words from each topic
                    for topic_idx, topic in enumerate(lda.components_):
                        top_indices = topic.argsort()[-3:][::-1]
                        topic_words = [feature_names[i] for i in top_indices]
                        # Create topic phrase from top words
                        main_topics_lda.append(' '.join(topic_words[:2]))

                except Exception as e:
                    print(f"[LDA Warning] Topic modeling skipped: {e}")

            # ===== TF-IDF KEYWORD EXTRACTION =====
            keywords = []
            try:
                # Adjust parameters based on document size
                n_sentences = len(sentences)
                min_df_param = 1
                max_df_param = 0.95 if n_sentences > 5 else 1.0

                tfidf_vectorizer = TfidfVectorizer(
                    max_features=100,
                    stop_words='english',
                    ngram_range=(1, 3),
                    min_df=min_df_param,
                    max_df=max_df_param
                )

                tfidf_matrix = tfidf_vectorizer.fit_transform(sentences)
                feature_names = tfidf_vectorizer.get_feature_names_out()

                # Sum TF-IDF scores across all documents
                tfidf_scores = np.asarray(tfidf_matrix.sum(axis=0)).ravel()

                # Get top keywords
                top_indices = tfidf_scores.argsort()[-30:][::-1]
                keywords = [feature_names[i] for i in top_indices]

            except Exception as e:
                # If TF-IDF fails, fall back to word frequency
                pass

            # ===== NOUN PHRASE EXTRACTION =====
            words = word_tokenize(text.lower())
            stop_words = set(stopwords.words('english'))

            # Extract noun phrases from all sentences
            noun_phrases = []
            named_entities = []

            for sentence in sentences:
                try:
                    words_sent = word_tokenize(sentence)
                    pos_tags = pos_tag(words_sent)

                    # Extract noun phrases (NN + NN, JJ + NN patterns)
                    current_phrase = []
                    for word, tag in pos_tags:
                        if tag.startswith('NN') or tag.startswith('JJ'):
                            if word.lower() not in stop_words and len(word) > 2:
                                current_phrase.append(word.lower())
                        else:
                            if len(current_phrase) >= 2:
                                phrase = ' '.join(current_phrase)
                                noun_phrases.append(phrase)
                            elif len(current_phrase) == 1 and tag.startswith('NNP'):
                                # Single proper noun (potential named entity)
                                named_entities.append(current_phrase[0])
                            current_phrase = []

                except Exception as e:
                    continue

            # ===== KEYWORD BASED TOPICS =====
            filtered_words = [w for w in words if w.isalnum() and w not in stop_words and len(w) > 3]
            word_freq = Counter(filtered_words)
            common_words = [word for word, _ in word_freq.most_common(15)]

            # ===== COMBINE ALL TOPIC SOURCES =====
            phrase_freq = Counter(noun_phrases)
            main_topics_phrases = [phrase for phrase, count in phrase_freq.most_common(10) if count >= 2]

            # Merge all topic sources
            all_topics = []
            all_topics.extend(main_topics_lda)
            all_topics.extend(main_topics_phrases[:7])

            # Add high-frequency keywords as topics if needed
            if len(all_topics) < 5:
                all_topics.extend(common_words[:5])

            # Deduplicate and clean
            seen = set()
            main_topics = []
            for topic in all_topics:
                topic_clean = topic.strip().lower()
                if topic_clean and topic_clean not in seen and len(topic_clean) > 2:
                    main_topics.append(topic_clean)
                    seen.add(topic_clean)
                    if len(main_topics) >= 10:
                        break

            # ===== CREATE SUBTOPICS MAPPING =====
            subtopics = {}
            for topic in main_topics[:7]:  # Top 7 main topics
                related_keywords = []
                topic_words = set(topic.split())

                # Find keywords that relate to this topic
                for kw in keywords[:30]:
                    kw_words = set(kw.split())
                    if topic_words & kw_words:  # Intersection
                        related_keywords.append(kw)
                    if len(related_keywords) >= 5:
                        break

                # If no related keywords, use general top keywords
                if not related_keywords:
                    related_keywords = keywords[:5]

                subtopics[topic] = related_keywords[:5]

            # ===== ENHANCE KEYWORDS WITH NAMED ENTITIES =====
            entity_freq = Counter(named_entities)
            top_entities = [entity for entity, _ in entity_freq.most_common(5)]

            # Merge keywords with entities
            final_keywords = []
            seen_kw = set()

            # Add top TF-IDF keywords
            for kw in keywords[:20]:
                if kw not in seen_kw:
                    final_keywords.append(kw)
                    seen_kw.add(kw)

            # Add named entities
            for entity in top_entities:
                if entity not in seen_kw:
                    final_keywords.append(entity)
                    seen_kw.add(entity)

            return {
                "main_topics": main_topics[:7],
                "subtopics": subtopics,
                "keywords": final_keywords[:20]
            }

        except ImportError as e:
            print(f"[NLP Detection Error] Missing dependencies: {e}")
            print("Please install required packages: pip install scikit-learn nltk")
            return {
                "main_topics": [],
                "subtopics": {},
                "keywords": []
            }
        except Exception as e:
            print(f"[NLP Detection Error] {e}")
            import traceback
            traceback.print_exc()
            return {
                "main_topics": [],
                "subtopics": {},
                "keywords": []
            }

    def _hybrid_detection(self, text: str) -> Dict:
        """
        Combine LLM and NLP approaches for best results

        Args:
            text: Input text

        Returns:
            Topic detection results
        """
        # Get results from both methods
        llm_results = self._llm_based_detection(text)
        nlp_results = self._nlp_based_detection(text)

        # Merge and deduplicate
        main_topics = list(set(
            llm_results.get("main_topics", []) +
            nlp_results.get("main_topics", [])
        ))[:7]  # Keep top 7 unique topics

        keywords = list(set(
            llm_results.get("keywords", []) +
            nlp_results.get("keywords", [])
        ))[:20]  # Keep top 20 unique keywords

        # Merge subtopics
        subtopics = {}
        all_subtopic_keys = set(
            list(llm_results.get("subtopics", {}).keys()) +
            list(nlp_results.get("subtopics", {}).keys())
        )

        for topic in all_subtopic_keys:
            llm_subs = llm_results.get("subtopics", {}).get(topic, [])
            nlp_subs = nlp_results.get("subtopics", {}).get(topic, [])
            subtopics[topic] = list(set(llm_subs + nlp_subs))[:5]

        return {
            "main_topics": main_topics,
            "subtopics": subtopics,
            "keywords": keywords
        }

    def _merge_results(self, results: List[Dict]) -> Dict:
        """
        Merge topic detection results from multiple chunks

        Args:
            results: List of detection results

        Returns:
            Merged results
        """
        if not results:
            return {
                "main_topics": [],
                "subtopics": {},
                "keywords": []
            }

        all_main_topics = []
        all_keywords = []
        all_subtopics = {}

        for result in results:
            all_main_topics.extend(result.get("main_topics", []))
            all_keywords.extend(result.get("keywords", []))

            for topic, subs in result.get("subtopics", {}).items():
                if topic not in all_subtopics:
                    all_subtopics[topic] = []
                all_subtopics[topic].extend(subs)

        # Count frequencies and keep most common
        topic_counter = Counter(all_main_topics)
        main_topics = [topic for topic, _ in topic_counter.most_common(7)]

        keyword_counter = Counter(all_keywords)
        keywords = [kw for kw, _ in keyword_counter.most_common(20)]

        # Deduplicate subtopics
        subtopics = {}
        for topic, subs in all_subtopics.items():
            subtopics[topic] = list(set(subs))[:5]

        return {
            "main_topics": main_topics,
            "subtopics": subtopics,
            "keywords": keywords
        }


# Convenience functions for backward compatibility
def detect_topics(text: str, strategy: str = "nlp", use_topic_modeling: bool = True) -> Dict:
    """
    Detect topics from text using specified strategy
    NO TOKEN LIMITS - runs completely offline with NLP (default)

    Args:
        text: Input text document
        strategy: Detection strategy - 'nlp' (default, no API), 'llm', or 'hybrid'
        use_topic_modeling: Use LDA topic modeling for better results (default: True)

    Returns:
        Dictionary with main_topics, subtopics, and keywords
    """
    detector = TopicDetector(strategy=strategy, use_topic_modeling=use_topic_modeling)
    return detector.detect_topics(text)


def detect_topics_json(text: str, strategy: str = "nlp", use_topic_modeling: bool = True) -> str:
    """
    Detect topics and return as JSON string
    NO TOKEN LIMITS - runs completely offline with NLP (default)

    Args:
        text: Input text document
        strategy: Detection strategy - 'nlp' (default, no API), 'llm', or 'hybrid'
        use_topic_modeling: Use LDA topic modeling for better results (default: True)

    Returns:
        JSON string with detection results
    """
    result = detect_topics(text, strategy, use_topic_modeling)
    return json.dumps(result, indent=2)
