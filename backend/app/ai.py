from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any

from openai import OpenAI

from .chat_memory import ChatTurn, chat_memory_store
from .config import settings
from .models import Book, BookStatus

logger = logging.getLogger(__name__)

PROMPT_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(all|previous|prior)\s+instructions", "Prompt-injection wording detected."),
    (r"(reveal|show|leak).*(system prompt|hidden prompt|secret)", "Attempt to extract protected prompts."),
    (r"(api key|secret key|token|password)", "Sensitive-data extraction attempt detected."),
    (r"(execute|run)\s+(command|shell|script)", "Command-execution request detected."),
]

STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "is",
    "are",
    "what",
    "which",
    "who",
    "name",
    "book",
    "books",
    "author",
    "title",
    "status",
    "do",
    "you",
    "have",
    "in",
    "on",
    "and",
    "by",
    "about",
}


def _openai_client() -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def _safe_text(value: Any, max_len: int = 700) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _fallback_enrichment(title: str, author: str) -> dict[str, Any]:
    tags = [word.lower() for word in re.findall(r"[A-Za-z]{4,}", f"{title} {author}")[:5]]
    summary = f"{title} by {author}. Auto-generated enrichment fallback."
    return {"summary": summary, "tags": list(dict.fromkeys(tags)) or ["general"]}


def _extract_metadata_snippet(metadata: dict[str, Any]) -> str:
    preferred_keys = ("description", "genre", "language", "publisher", "year", "isbn")
    details: list[str] = []

    for key in preferred_keys:
        if key in metadata:
            details.append(f"{key}: {_safe_text(metadata.get(key), 120)}")

    if not details:
        for key, value in list(metadata.items())[:5]:
            details.append(f"{_safe_text(key, 40)}: {_safe_text(value, 120)}")

    return "; ".join(details)


def _book_document(book: Book) -> dict[str, Any]:
    metadata = book.metadata_json if isinstance(book.metadata_json, dict) else {}
    snippet = _extract_metadata_snippet(metadata)
    text = _safe_text(
        f"title: {book.title}; author: {book.author}; status: {book.status.value}; metadata: {snippet}",
        2000,
    )
    return {
        "book_id": book.id,
        "title": _safe_text(book.title, 255),
        "author": _safe_text(book.author, 255),
        "status": book.status,
        "snippet": snippet or "No additional metadata.",
        "text": text,
        "score": 0.0,
    }


def _detect_prompt_injection(question: str) -> str | None:
    normalized = question.lower()
    for pattern, reason in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            return reason
    return None


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", value.lower())


def _meaningful_tokens(value: str) -> set[str]:
    return {token for token in _tokenize(value) if token not in STOPWORDS}


def _fuzzy_token_match(token_a: str, token_b: str) -> bool:
    if token_a == token_b:
        return True
    if abs(len(token_a) - len(token_b)) > 2:
        return False
    return SequenceMatcher(a=token_a, b=token_b).ratio() >= 0.82


def _fuzzy_overlap_count(tokens_a: set[str], tokens_b: set[str]) -> int:
    if not tokens_a or not tokens_b:
        return 0
    count = 0
    for token_a in tokens_a:
        if any(_fuzzy_token_match(token_a, token_b) for token_b in tokens_b):
            count += 1
    return count


def _keyword_score(question: str, document_text: str) -> float:
    q_tokens = _tokenize(question)
    if not q_tokens:
        return 0.0
    doc_tokens = set(_tokenize(document_text))
    overlap = sum(1 for token in q_tokens if token in doc_tokens)
    return overlap / len(q_tokens)


def _retrieve_keyword(question: str, books: Sequence[Book], top_k: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for book in books:
        doc = _book_document(book)
        doc["score"] = _keyword_score(question, doc["text"])
        ranked.append(doc)

    ranked.sort(key=lambda row: row["score"], reverse=True)
    return ranked[:top_k]


def _best_source_for_question(question: str, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not sources:
        return None

    q_tokens = _meaningful_tokens(question)
    if not q_tokens:
        return sources[0]

    def score_source(source: dict[str, Any]) -> tuple[int, float]:
        title_tokens = _meaningful_tokens(str(source.get("title", "")))
        overlap = _fuzzy_overlap_count(q_tokens, title_tokens)
        return overlap, float(source.get("score", 0.0))

    return max(sources, key=score_source)


def _description_from_snippet(snippet: str) -> str | None:
    if not snippet or snippet.strip().lower() == "no additional metadata.":
        return None
    match = re.search(r"(?:^|;\s*)description:\s*([^;]+)", snippet, flags=re.IGNORECASE)
    if match:
        return _safe_text(match.group(1), 260)
    return None


def _title_overlap_score(question: str, title: str) -> tuple[int, int]:
    q_tokens = _meaningful_tokens(question)
    title_tokens = _meaningful_tokens(title)
    overlap = _fuzzy_overlap_count(q_tokens, title_tokens)
    return overlap, len(title_tokens)


def _has_strong_title_match(question: str, source: dict[str, Any]) -> bool:
    title = str(source.get("title", "")).strip()
    if not title:
        return False
    overlap, title_size = _title_overlap_score(question, title)
    if title_size <= 2:
        return overlap >= 1
    return overlap >= 2


def _topic_terms(question: str) -> set[str]:
    # Keep meaningful user-intent terms and expand close semantic variants.
    base_terms = _meaningful_tokens(question)
    expanded = set(base_terms)
    synonyms: dict[str, tuple[str, ...]] = {
        "money": ("finance", "financial", "investing", "investment", "wealth", "capital"),
        "finance": ("money", "financial", "investing", "investment", "capital"),
        "investing": ("investment", "finance", "financial", "money", "stocks", "value"),
        "productivity": ("focus", "concentration", "deep", "work"),
        "programming": ("software", "code", "engineering", "developer"),
    }
    for term in list(base_terms):
        for synonym in synonyms.get(term, ()):
            expanded.add(synonym)
    return expanded


def _semantic_topic_matches(question: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = _topic_terms(question)
    if not terms:
        return []

    scored: list[tuple[tuple[int, float], dict[str, Any]]] = []
    for source in sources:
        text = f"{source.get('title', '')} {source.get('snippet', '')}"
        source_terms = _meaningful_tokens(text)
        overlap = _fuzzy_overlap_count(terms, source_terms)
        score = float(source.get("score", 0.0))
        if overlap > 0:
            scored.append(((overlap, score), source))

    scored.sort(key=lambda row: row[0], reverse=True)
    return [row[1] for row in scored]


def _genre_from_snippet(snippet: str) -> str | None:
    if not snippet or snippet.strip().lower() == "no additional metadata.":
        return None
    match = re.search(r"(?:^|;\s*)genre:\s*([^;]+)", snippet, flags=re.IGNORECASE)
    if match:
        return _safe_text(match.group(1), 80).lower()
    return None


def _is_catalog_overview_question(question: str) -> bool:
    normalized = question.lower()
    patterns = (
        r"\bwhat (type|types|kind|kinds|category|categories) of books\b",
        r"\bwhat books do you have\b",
        r"\bwhich books do you have\b",
        r"\bshow (me )?(all )?books\b",
        r"\bwhat is in (the )?(catalog|library)\b",
        r"\byour (catalog|library)\b.*\bbooks\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _small_talk_response(question: str) -> str | None:
    normalized = question.strip().lower()
    if re.fullmatch(r"(hi|hello|hey|hey there|good morning|good afternoon|good evening)[!. ]*", normalized):
        return "Hello. I can help with titles, authors, book content, and availability."
    if re.fullmatch(r"(thanks|thank you|thx)[!. ]*", normalized):
        return "You are welcome."
    if re.fullmatch(r"(ok|okay|cool|nice|great)[!. ]*", normalized):
        return "Great. Ask me any catalog question."
    return None


def _missing_title_from_assistant_text(assistant_text: str) -> str | None:
    normalized = assistant_text.strip()
    if not normalized:
        return None

    patterns = (
        r"do not have a book called ['\"]?([^'\"]+)['\"]?",
        r"could not find that exact title[: ]+['\"]?([^'\"]+)['\"]?",
        r"could not find ['\"]?([^'\"]+)['\"]? in the current catalog",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return _safe_text(match.group(1), 255)
    return None


def _category_from_source(source: dict[str, Any]) -> str | None:
    genre = _genre_from_snippet(str(source.get("snippet", "")))
    if genre:
        return genre

    title = str(source.get("title", "")).lower()
    description = (_description_from_snippet(str(source.get("snippet", ""))) or "").lower()
    text = f"{title} {description}"

    category_rules: list[tuple[tuple[str, ...], str]] = [
        (("code", "software", "frontend", "backend", "programming", "engineering"), "software engineering"),
        (("invest", "finance", "trading", "stock", "value"), "investing and finance"),
        (("novel", "story", "fiction", "romance", "stars"), "fiction"),
    ]
    for keywords, label in category_rules:
        if any(keyword in text for keyword in keywords):
            return label
    return None


def _catalog_overview_answer(sources: list[dict[str, Any]]) -> str:
    count = len(sources)
    categories: list[str] = []
    for source in sources:
        category = _category_from_source(source)
        if category and category not in categories:
            categories.append(category)

    if categories:
        top_categories = categories[:4]
        if len(top_categories) == 1:
            return f"Your catalog currently focuses on {top_categories[0]} ({count} books total)."
        if len(top_categories) == 2:
            return f"Your catalog currently includes {top_categories[0]} and {top_categories[1]} ({count} books total)."
        categories_text = ", ".join(top_categories[:-1]) + f", and {top_categories[-1]}"
        return f"Your catalog currently includes {categories_text} ({count} books total)."

    top_titles = [str(src.get("title", "")).strip() for src in sources[:3] if str(src.get("title", "")).strip()]
    if top_titles:
        return f"You currently have {count} books, including {', '.join(top_titles)}."
    return f"You currently have {count} books in the catalog."


def _deterministic_fact_answer(
    question: str,
    sources: list[dict[str, Any]],
    source_hint: str | None = None,
    preferred_source: dict[str, Any] | None = None,
) -> str | None:
    source = preferred_source or _best_source_for_question(source_hint or question, sources)
    if not source:
        return None

    normalized = question.lower()
    title = str(source["title"])
    author = str(source["author"])
    status = source["status"].value if isinstance(source["status"], BookStatus) else str(source["status"])

    asks_author = (
        "author" in normalized
        or "who wrote" in normalized
        or "who rote" in normalized
        or "written by" in normalized
        or "writer" in normalized
        or bool(re.search(r"\bwho\b.*\b(wrote|rote|writer|author)\b", normalized))
    )
    if asks_author:
        return f'The author of "{title}" is {author}.'

    asks_status = (
        "available" in normalized
        or "borrowed" in normalized
        or "status" in normalized
        or "checked out" in normalized
        or "checked in" in normalized
    )
    if asks_status and len(_meaningful_tokens(title)) > 0:
        return f'"{title}" is currently {status}.'

    asks_existence = (
        "do you have" in normalized
        or "is there" in normalized
        or bool(re.search(r"\bdo we have\b", normalized))
    )
    if asks_existence:
        plural_topic_query = bool(
            re.search(r"\bbooks?\s+(on|about|related to)\b", normalized)
            or re.search(r"\bany books?\b", normalized)
            or re.search(r"\bwhat books?\b", normalized)
        )
        if _has_strong_title_match(question, source):
            return f'Yes, we have "{title}". It is currently {status}.'

        if plural_topic_query:
            topic_matches = _semantic_topic_matches(question, sources)
            if topic_matches:
                top = topic_matches[:2]
                if len(top) == 1:
                    row = top[0]
                    row_title = str(row["title"])
                    row_status = row["status"].value if isinstance(row["status"], BookStatus) else str(row["status"])
                    return f'Yes, we have a relevant match: "{row_title}" ({row_status}).'
                first = top[0]
                second = top[1]
                first_title = str(first["title"])
                second_title = str(second["title"])
                return f'Yes, we have relevant books, including "{first_title}" and "{second_title}".'
            return "I could not find books matching that topic in the current catalog."

        return "I could not find that exact title in the current catalog."

    asks_content = (
        "content" in normalized
        or "about" in normalized
        or "summary" in normalized
        or "describe" in normalized
        or "topic" in normalized
        or "what is it about" in normalized
    )
    if asks_content:
        description = _description_from_snippet(str(source.get("snippet", "")))
        if description:
            return f'"{title}" is about {description}.'
        return f'I do not have enough description metadata for "{title}".'

    return None


def _resolve_followup_source(
    question: str,
    history: Sequence[ChatTurn],
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not _looks_like_followup(question) or not history or not sources:
        return None

    recent_turn = history[-1]
    reference_text = f"{recent_turn.user} {recent_turn.assistant}".lower()

    for source in sources:
        title = str(source.get("title", "")).strip().lower()
        if title and title in reference_text:
            return source

    previous_tokens = _meaningful_tokens(recent_turn.user)
    if not previous_tokens:
        return None

    def score_source(source: dict[str, Any]) -> int:
        title_tokens = _meaningful_tokens(str(source.get("title", "")))
        return _fuzzy_overlap_count(previous_tokens, title_tokens)

    ranked = sorted(sources, key=score_source, reverse=True)
    if ranked and score_source(ranked[0]) > 0:
        return ranked[0]
    return None


def _looks_like_followup(question: str) -> bool:
    normalized = question.lower()
    followup_patterns = (
        r"\bit\b",
        r"\bits\b",
        r"\btheir\b",
        r"\bthem\b",
        r"\bthis\b",
        r"\bthat\b",
        r"\bthis one\b",
        r"\bthat one\b",
        r"\bother one\b",
        r"\bsame one\b",
        r"\bwhat about\b",
        r"\band (what|who|when|where|is|are)\b",
    )
    return any(re.search(pattern, normalized) for pattern in followup_patterns)


def _build_effective_question(question: str, history: Sequence[ChatTurn]) -> str:
    if not history:
        return question

    recent_user_questions = [turn.user for turn in history[-3:] if turn.user]
    if not recent_user_questions:
        return question

    if _looks_like_followup(question):
        context = " | ".join(recent_user_questions[-2:])
        return _safe_text(f"Conversation context: {context}. Current question: {question}", 1200)

    return question


def _history_as_text(history: Sequence[ChatTurn]) -> str:
    if not history:
        return "No prior conversation."

    lines: list[str] = []
    for turn in history[-3:]:
        lines.append(f"User: {_safe_text(turn.user, 280)}")
        lines.append(f"Assistant: {_safe_text(turn.assistant, 280)}")
    return "\n".join(lines)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None

    # Direct JSON object response.
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # JSON wrapped in markdown fences.
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        candidate = fenced_match.group(1)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # First object-like substring fallback.
    object_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if object_match:
        candidate = object_match.group(0)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Robust parsing for outputs with trailing characters, duplicated braces, or prefixed text.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        candidate = stripped[match.start() :]
        try:
            parsed, _end = decoder.raw_decode(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _extract_chat_completion_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    message = getattr(choices[0], "message", None)
    if message is None:
        return ""

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content

    # Some SDK variants may return segmented content blocks.
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, dict):
                text = chunk.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            else:
                text = getattr(chunk, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return " ".join(parts).strip()

    return str(content or "")


def _generate_text_with_openai(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
) -> str:
    # Prefer Responses API when available, fallback to Chat Completions for older SDKs.
    if hasattr(client, "responses"):
        response = client.responses.create(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=max_output_tokens,
        )
        return _safe_text(getattr(response, "output_text", ""), 3000)

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_output_tokens,
        temperature=0.2,
    )
    return _safe_text(_extract_chat_completion_text(response), 3000)


def _source_selection_score(question: str, source: dict[str, Any]) -> tuple[int, float]:
    q_tokens = _meaningful_tokens(question)
    text_tokens = _meaningful_tokens(f"{source.get('title', '')} {source.get('snippet', '')}")
    overlap = _fuzzy_overlap_count(q_tokens, text_tokens) if q_tokens else 0
    return overlap, float(source.get("score", 0.0))


def _select_sources_for_display(
    question: str,
    sources: list[dict[str, Any]],
    used_book_ids: list[int] | None,
    max_display: int = 5,
) -> list[dict[str, Any]]:
    if not sources:
        return []

    # If model explicitly returns no evidence ids, do not show unrelated sources.
    if used_book_ids is not None:
        if len(used_book_ids) == 0:
            return []
        used_set = set(used_book_ids)
        selected = [source for source in sources if int(source.get("book_id", -1)) in used_set]
        if selected:
            return selected[:max_display]
        return []

    ranked = sorted(sources, key=lambda source: _source_selection_score(question, source), reverse=True)
    if _is_catalog_overview_question(question):
        return ranked[: min(max_display, 5)]

    # Hide noisy matches for non-catalog questions when lexical overlap is zero.
    if not any(_source_selection_score(question, source)[0] > 0 for source in ranked):
        return []

    if ranked and ranked[0].get("score", 0.0) > 0:
        return ranked[: min(max_display, 3)]
    return ranked[: max_display]


def _deterministic_display_sources(
    question: str,
    answer: str,
    sources: list[dict[str, Any]],
    followup_source: dict[str, Any] | None,
    best_source: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized = question.lower()
    plural_topic_query = bool(
        re.search(r"\bbooks?\s+(on|about|related to)\b", normalized)
        or re.search(r"\bany books?\b", normalized)
        or re.search(r"\bwhat books?\b", normalized)
    )
    asks_existence = (
        "do you have" in normalized
        or "is there" in normalized
        or bool(re.search(r"\bdo we have\b", normalized))
    )

    if asks_existence and plural_topic_query:
        topic_matches = _semantic_topic_matches(question, sources)
        if topic_matches:
            return topic_matches[:2]

    quoted_titles = re.findall(r'"([^"]+)"', answer)
    if quoted_titles:
        matched: list[dict[str, Any]] = []
        for quoted in quoted_titles:
            quoted_l = quoted.strip().lower()
            for source in sources:
                title_l = str(source.get("title", "")).lower()
                if quoted_l and quoted_l in title_l and source not in matched:
                    matched.append(source)
        if matched:
            return matched[:3]

    selected_source = followup_source or best_source
    if selected_source:
        return [selected_source]
    return sources[:1]


def _llm_chat_answer(
    client: OpenAI,
    question: str,
    history: Sequence[ChatTurn],
    sources: list[dict[str, Any]],
) -> tuple[str, list[int] | None]:
    history_text = _history_as_text(history)
    context_payload = json.dumps(
        [
            {
                "book_id": src["book_id"],
                "title": src["title"],
                "author": src["author"],
                "status": src["status"].value if isinstance(src["status"], BookStatus) else str(src["status"]),
                "snippet": src["snippet"],
            }
            for src in sources
        ],
        ensure_ascii=True,
    )

    system_prompt = (
        "You are a conversational library assistant with RAG context. "
        "Use only the provided catalog context for catalog facts. "
        "If user asks whether a title exists or is available, answer yes/no based on context evidence. "
        "If the user asks a follow-up with ambiguous pronouns (it/that/this) and no clear referenced title, "
        "ask a brief clarification question instead of guessing. "
        "If a requested title is not in catalog, state that clearly and do not suggest nearest matches "
        "unless the user explicitly asks for alternatives or recommendations. "
        "Be natural and concise (1-3 short sentences). Avoid rigid templates. "
        "Treat catalog fields as the only source of truth and never replace catalog title/author/status values "
        "with outside knowledge. "
        "If context is missing, say you do not have enough catalog data. "
        "Return exactly one JSON object and nothing else with keys: "
        "answer (string), used_book_ids (array of integers). "
        "If no catalog items were used, set used_book_ids to []."
    )
    user_prompt = (
        "Conversation history:\n"
        f"{history_text}\n\n"
        f"Question:\n{question}\n\n"
        "Catalog context (JSON array):\n"
        f"{context_payload}\n"
    )

    output_text = _safe_text(
        _generate_text_with_openai(
            client=client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=260,
        ),
        2000,
    )
    parsed = _extract_json_object(output_text)
    if not parsed:
        return output_text, None

    answer = _safe_text(parsed.get("answer", ""), 1500) or output_text
    used_book_ids: list[int] | None = None
    if "used_book_ids" in parsed:
        used_raw = parsed.get("used_book_ids", [])
        used_book_ids = []
        if isinstance(used_raw, list):
            for value in used_raw:
                try:
                    used_book_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
    return answer, used_book_ids


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _retrieve_embeddings(
    question: str,
    books: Sequence[Book],
    client: OpenAI,
    top_k: int,
) -> tuple[list[dict[str, Any]], str]:
    docs = [_book_document(book) for book in books]
    if not docs:
        return [], "openai_embeddings"

    inputs = [question] + [doc["text"] for doc in docs]
    try:
        response = client.embeddings.create(model=settings.openai_embedding_model, input=inputs)
    except Exception:
        logger.exception("Embedding retrieval failed; falling back to keyword retrieval")
        return _retrieve_keyword(question, books, top_k), "keyword_fallback"

    if len(response.data) != len(inputs):
        return _retrieve_keyword(question, books, top_k), "keyword_fallback"

    query_embedding = response.data[0].embedding
    for doc, embedding_item in zip(docs, response.data[1:]):
        doc["score"] = _cosine_similarity(query_embedding, embedding_item.embedding)

    docs.sort(key=lambda row: row["score"], reverse=True)
    return docs[:top_k], "openai_embeddings"


def _fallback_chat_answer(
    question: str,
    sources: list[dict[str, Any]],
    source_hint: str | None = None,
    preferred_source: dict[str, Any] | None = None,
) -> str:
    if not sources:
        return "I could not find relevant books for that question in the current catalog."

    deterministic = _deterministic_fact_answer(
        question,
        sources,
        source_hint=source_hint,
        preferred_source=preferred_source,
    )
    if deterministic:
        return deterministic

    top_sources = sources[:2]
    if len(top_sources) == 1:
        row = top_sources[0]
        return f'Most relevant match: "{row["title"]}" by {row["author"]}.'

    first = top_sources[0]
    second = top_sources[1]
    return f'Top matches: "{first["title"]}" by {first["author"]}, and "{second["title"]}" by {second["author"]}.'


def enrich_book_payload(title: str, author: str, metadata: dict[str, Any]) -> dict[str, Any]:
    client = _openai_client()
    if client is None:
        return _fallback_enrichment(title, author)

    system_prompt = (
        "You enrich book metadata. Return strict JSON only with keys summary (string) and tags "
        "(array of 3-6 short tags)."
    )
    user_prompt = f"Book title: {title}\\nAuthor: {author}\\nMetadata: {json.dumps(metadata)}"
    try:
        text = _generate_text_with_openai(
            client=client,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=250,
        )
    except Exception:
        logger.exception("Metadata enrichment failed; using fallback enrichment")
        return _fallback_enrichment(title, author)

    try:
        parsed = json.loads(text)
        summary = str(parsed.get("summary", "")).strip() or f"{title} by {author}"
        tags = [str(t).strip() for t in parsed.get("tags", []) if str(t).strip()]
        return {"summary": summary, "tags": tags[:6] or ["general"]}
    except json.JSONDecodeError:
        return {"summary": text.strip()[:400], "tags": ["general"]}


def chat_search_books(
    question: str,
    books: Sequence[Book],
    conversation_id: str | None = None,
    reset: bool = False,
) -> dict[str, Any]:
    if reset:
        chat_memory_store.clear(conversation_id)
    conv_id, history = chat_memory_store.get_history(conversation_id)
    clean_question = _safe_text(question, 1200)
    effective_question = _build_effective_question(clean_question, history)
    guard_reason = _detect_prompt_injection(clean_question)
    if guard_reason:
        return {
            "answer": "I can only help with library catalog questions. Please rephrase your request.",
            "sources": [],
            "blocked": True,
            "reason": guard_reason,
            "retrieval_method": "guard_blocked",
            "conversation_id": conv_id,
        }

    client = _openai_client()
    small_talk_answer = _small_talk_response(clean_question)
    if small_talk_answer:
        chat_memory_store.append_turn(conv_id, clean_question, small_talk_answer)
        return {
            "answer": small_talk_answer,
            "sources": [],
            "blocked": False,
            "reason": None,
            "retrieval_method": "small_talk",
            "conversation_id": conv_id,
        }

    top_k = max(1, min(settings.ai_rag_top_k, 10))

    if client is not None:
        ranked_docs, retrieval_method = _retrieve_embeddings(effective_question, books, client, top_k)
    else:
        ranked_docs = _retrieve_keyword(effective_question, books, top_k)
        retrieval_method = "keyword"

    sources = [
        {
            "book_id": int(doc["book_id"]),
            "title": str(doc["title"]),
            "author": str(doc["author"]),
            "status": doc["status"],
            "score": round(float(doc["score"]), 4),
            "snippet": _safe_text(doc["snippet"], 260),
        }
        for doc in ranked_docs
    ]

    if not sources:
        answer = "I could not find relevant books in this catalog."
        chat_memory_store.append_turn(conv_id, clean_question, answer)
        return {
            "answer": answer,
            "sources": [],
            "blocked": False,
            "reason": None,
            "retrieval_method": retrieval_method,
            "conversation_id": conv_id,
        }

    if history and _looks_like_followup(clean_question):
        missing_title = _missing_title_from_assistant_text(history[-1].assistant)
        if missing_title:
            answer = (
                f'I still do not have "{missing_title}" in the catalog. '
                "If you want, I can suggest similar available titles."
            )
            chat_memory_store.append_turn(conv_id, clean_question, answer)
            return {
                "answer": answer,
                "sources": [],
                "blocked": False,
                "reason": None,
                "retrieval_method": f"{retrieval_method}_missing_title_followup",
                "conversation_id": conv_id,
            }

    if client is not None:
        try:
            answer, used_book_ids = _llm_chat_answer(client, clean_question, history, sources)
            if not answer:
                raise ValueError("Empty LLM answer")
            display_sources = _select_sources_for_display(clean_question, sources, used_book_ids, max_display=5)
            chat_memory_store.append_turn(conv_id, clean_question, answer)
            return {
                "answer": answer,
                "sources": display_sources,
                "blocked": False,
                "reason": None,
                "retrieval_method": f"{retrieval_method}_conversational",
                "conversation_id": conv_id,
            }
        except Exception:
            logger.exception("Conversational LLM call failed")
            # In LLM-first mode, avoid deterministic template fallback when model calls fail.
            # Return a transparent message plus top semantic matches instead.
            model_unavailable_answer = (
                "I could not reach the conversational model right now. "
                "Here are the closest matches from the catalog."
            )
            display_sources = _select_sources_for_display(clean_question, sources, used_book_ids=None, max_display=3)
            chat_memory_store.append_turn(conv_id, clean_question, model_unavailable_answer)
            return {
                "answer": model_unavailable_answer,
                "sources": display_sources,
                "blocked": False,
                "reason": None,
                "retrieval_method": f"{retrieval_method}_llm_unavailable",
                "conversation_id": conv_id,
            }

    # Deterministic fallback path when OpenAI is unavailable.
    if _is_catalog_overview_question(clean_question):
        overview_answer = _catalog_overview_answer(sources)
        chat_memory_store.append_turn(conv_id, clean_question, overview_answer)
        return {
            "answer": overview_answer,
            "sources": sources[: min(5, len(sources))],
            "blocked": False,
            "reason": None,
            "retrieval_method": f"{retrieval_method}_catalog_overview",
            "conversation_id": conv_id,
        }

    followup_source = _resolve_followup_source(clean_question, history, sources)
    best_source = _best_source_for_question(effective_question, sources)
    deterministic = _deterministic_fact_answer(
        clean_question,
        sources,
        source_hint=effective_question,
        preferred_source=followup_source,
    )
    if deterministic:
        chat_memory_store.append_turn(conv_id, clean_question, deterministic)
        focused_sources = _deterministic_display_sources(
            clean_question,
            deterministic,
            sources,
            followup_source,
            best_source,
        )
        return {
            "answer": deterministic,
            "sources": focused_sources,
            "blocked": False,
            "reason": None,
            "retrieval_method": f"{retrieval_method}_deterministic",
            "conversation_id": conv_id,
        }

    answer = _fallback_chat_answer(
        clean_question,
        sources,
        source_hint=effective_question,
        preferred_source=followup_source,
    )
    chat_memory_store.append_turn(conv_id, clean_question, answer)
    return {
        "answer": answer,
        "sources": sources,
        "blocked": False,
        "reason": None,
        "retrieval_method": retrieval_method,
        "conversation_id": conv_id,
    }
