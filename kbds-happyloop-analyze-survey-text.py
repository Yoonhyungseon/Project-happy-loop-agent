import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List

import boto3


comprehend = boto3.client("comprehend")


KEYWORD_MIN_SCORE = 0.85
TOP_KEYWORD_LIMIT = 10


STOP_KEYWORDS = {
    "기능",
    "서비스",
    "앱",
    "화면",
    "고객",
    "사용",
    "사용하기",
    "자주",
    "정도",
    "부분",
    "관련",
    "점",
    "것",
    "때",
    "후",
    "중",
    "위치",
    "방식"
}


KEYWORD_ALIASES = {
    "이체 단계가": "이체 단계",
    "이체 단계는": "이체 단계",
    "이체 단계를": "이체 단계",
    "계좌 조회가": "계좌 조회",
    "계좌 조회는": "계좌 조회",
    "거래내역을": "거래내역",
    "메뉴가": "메뉴",
    "메뉴를": "메뉴",
    "로그인 방식이": "로그인 방식",
    "첫 화면 로딩이": "첫 화면 로딩",
    "앱 실행 후": "앱 실행"
}


def normalize_key_phrase(text: str) -> str:
    phrase = (text or "").strip()
    phrase = re.sub(r"[.,!?;:()\[\]{}\"']", "", phrase).strip()

    if phrase in KEYWORD_ALIASES:
        return KEYWORD_ALIASES[phrase]

    suffixes = [
        "으로", "에서", "에게", "하고", "이며", "이고",
        "까지", "부터", "보다", "처럼", "하면", "해서",
        "가", "이", "은", "는", "을", "를", "도", "만", "에"
    ]

    for suffix in suffixes:
        if len(phrase) > len(suffix) + 1 and phrase.endswith(suffix):
            phrase = phrase[: -len(suffix)].strip()
            break

    if phrase in KEYWORD_ALIASES:
        return KEYWORD_ALIASES[phrase]

    return phrase


def is_valid_keyword(keyword: str, score: float) -> bool:
    if not keyword:
        return False

    if score < KEYWORD_MIN_SCORE:
        return False

    if keyword in STOP_KEYWORDS:
        return False

    if len(keyword) < 2:
        return False

    return True


def safe_text(text: str) -> str:
    value = (text or "").strip()

    if len(value) > 4500:
        value = value[:4500]

    return value


def analyze_text(text: str) -> Dict[str, Any]:
    value = safe_text(text)

    sentiment_response = comprehend.detect_sentiment(
        Text=value,
        LanguageCode="ko"
    )

    key_phrase_response = comprehend.detect_key_phrases(
        Text=value,
        LanguageCode="ko"
    )

    sentiment_score = sentiment_response.get("SentimentScore", {})

    keywords = []
    seen = set()

    for item in key_phrase_response.get("KeyPhrases", []):
        raw_keyword = item.get("Text", "")
        score = round(float(item.get("Score", 0)), 4)
        keyword = normalize_key_phrase(raw_keyword)

        if not is_valid_keyword(keyword, score):
            continue

        if keyword in seen:
            continue

        seen.add(keyword)
        keywords.append({
            "text": keyword,
            "score": score
        })

    return {
        "sentiment": sentiment_response.get("Sentiment"),
        "scores": {
            "pos": round(float(sentiment_score.get("Positive", 0)), 4),
            "neu": round(float(sentiment_score.get("Neutral", 0)), 4),
            "neg": round(float(sentiment_score.get("Negative", 0)), 4),
            "mix": round(float(sentiment_score.get("Mixed", 0)), 4)
        },
        "keywords": keywords
    }


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    sentiment_counter = Counter()
    keyword_counter = Counter()
    category_sentiment_counter = defaultdict(Counter)
    category_keyword_counter = defaultdict(Counter)

    valid_count = 0

    for result in results:
        if result.get("error"):
            continue

        valid_count += 1

        category = result.get("category") or "UNKNOWN"
        sentiment = result.get("sentiment")

        if sentiment:
            sentiment_counter[sentiment] += 1
            category_sentiment_counter[category][sentiment] += 1

        for keyword in result.get("keywords", []):
            keyword_text = keyword.get("text")

            if not keyword_text:
                continue

            keyword_counter[keyword_text] += 1
            category_keyword_counter[category][keyword_text] += 1

    top_keywords = [
        {
            "keyword": keyword,
            "count": count
        }
        for keyword, count in keyword_counter.most_common(TOP_KEYWORD_LIMIT)
    ]

    by_category = []

    for category, counter in category_sentiment_counter.items():
        top_category_keywords = [
            {
                "keyword": keyword,
                "count": count
            }
            for keyword, count in category_keyword_counter[category].most_common(5)
        ]

        by_category.append({
            "category": category,
            "sentimentSummary": {
                "POSITIVE": counter.get("POSITIVE", 0),
                "NEUTRAL": counter.get("NEUTRAL", 0),
                "NEGATIVE": counter.get("NEGATIVE", 0),
                "MIXED": counter.get("MIXED", 0)
            },
            "topKeywords": top_category_keywords
        })

    return {
        "validCount": valid_count,
        "sentimentSummary": {
            "POSITIVE": sentiment_counter.get("POSITIVE", 0),
            "NEUTRAL": sentiment_counter.get("NEUTRAL", 0),
            "NEGATIVE": sentiment_counter.get("NEGATIVE", 0),
            "MIXED": sentiment_counter.get("MIXED", 0)
        },
        "topKeywords": top_keywords,
        "byCategory": by_category
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    answers = event.get("answers", [])

    if not isinstance(answers, list):
        return {
            "statusCode": 400,
            "body": {
                "message": "answers must be a list"
            }
        }

    results = []

    for answer in answers:
        answer_id = answer.get("answerId")
        survey_id = answer.get("surveyId")
        question_code = answer.get("questionCode")
        category = answer.get("category")
        text = answer.get("text", "")

        if not text or not text.strip():
            results.append({
                "answerId": answer_id,
                "surveyId": survey_id,
                "questionCode": question_code,
                "category": category,
                "error": "empty text"
            })
            continue

        try:
            analysis = analyze_text(text)

            results.append({
                "answerId": answer_id,
                "surveyId": survey_id,
                "questionCode": question_code,
                "category": category,
                "text": text,
                "sentiment": analysis["sentiment"],
                "scores": analysis["scores"],
                "keywords": analysis["keywords"]
            })

        except Exception as e:
            results.append({
                "answerId": answer_id,
                "surveyId": survey_id,
                "questionCode": question_code,
                "category": category,
                "text": text,
                "error": str(e)
            })

    summary = build_summary(results)

    return {
        "statusCode": 200,
        "body": {
            "count": len(results),
            "summary": summary,
            "results": results
        }
    }