import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3


DB_CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN", "")
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")
DB_NAME = os.environ.get("DB_NAME", "postgres")

rds_data = boto3.client("rds-data")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success(body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": 200,
        "body": body
    }


def error(message: str, status_code: int = 500) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": {
            "message": message
        }
    }


def parse_event(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")

    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return event

    if isinstance(body, dict):
        return body

    return event


def get_body(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    body = value.get("body")

    if isinstance(body, dict):
        return body

    if isinstance(body, str):
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

    return value


def param_string(name: str, value: Optional[str]) -> Dict[str, Any]:
    if value is None:
        return {
            "name": name,
            "value": {
                "isNull": True
            }
        }

    return {
        "name": name,
        "value": {
            "stringValue": str(value)
        }
    }


def param_long(name: str, value: Optional[int]) -> Dict[str, Any]:
    if value is None:
        return {
            "name": name,
            "value": {
                "isNull": True
            }
        }

    return {
        "name": name,
        "value": {
            "longValue": int(value)
        }
    }


def param_double(name: str, value: Optional[float]) -> Dict[str, Any]:
    if value is None:
        return {
            "name": name,
            "value": {
                "isNull": True
            }
        }

    return {
        "name": name,
        "value": {
            "doubleValue": float(value)
        }
    }


def field_to_value(field: Dict[str, Any]) -> Any:
    if field.get("isNull"):
        return None

    if "stringValue" in field:
        return field["stringValue"]

    if "longValue" in field:
        return field["longValue"]

    if "doubleValue" in field:
        return field["doubleValue"]

    if "booleanValue" in field:
        return field["booleanValue"]

    if "blobValue" in field:
        return field["blobValue"]

    if "arrayValue" in field:
        return field["arrayValue"]

    return None


def execute_sql(sql: str, parameters: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not DB_CLUSTER_ARN:
        raise ValueError("DB_CLUSTER_ARN environment variable is required")

    if not DB_SECRET_ARN:
        raise ValueError("DB_SECRET_ARN environment variable is required")

    max_attempts = 6
    wait_seconds = 5

    for attempt in range(1, max_attempts + 1):
        try:
            return rds_data.execute_statement(
                resourceArn=DB_CLUSTER_ARN,
                secretArn=DB_SECRET_ARN,
                database=DB_NAME,
                sql=sql,
                parameters=parameters or [],
                includeResultMetadata=True
            )
        except rds_data.exceptions.DatabaseResumingException:
            if attempt == max_attempts:
                raise

            time.sleep(wait_seconds)


def query_rows(sql: str, parameters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    response = execute_sql(sql, parameters)
    records = response.get("records", [])
    metadata = response.get("columnMetadata", [])

    column_names = []
    for column in metadata:
        column_names.append(column.get("label") or column.get("name"))

    rows = []

    for record in records:
        row = {}

        for index, field in enumerate(record):
            column_name = column_names[index] if index < len(column_names) else f"col_{index}"
            row[column_name] = field_to_value(field)

        rows.append(row)

    return rows


def execute_write(sql: str, parameters: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    response = execute_sql(sql, parameters)

    return {
        "numberOfRecordsUpdated": response.get("numberOfRecordsUpdated", 0),
        "generatedFields": response.get("generatedFields", [])
    }




# =========================================================
# Survey Agent generation helpers
# =========================================================

DEFAULT_CX_STAGES = [
    "인지/탐색",
    "가입/시작",
    "핵심 이용/처리",
    "문제해결/지원",
    "완료/재이용"
]

DEFAULT_SERVICE_QUALITY_DIMENSIONS = [
    "신뢰성",
    "응답성",
    "확신성/안전성",
    "공감성",
    "디지털 유형성",
    "접근성/편의성"
]


def get_lambda_body(value: Any) -> Dict[str, Any]:
    """Step Functions Lambda Invoke 결과와 직접 Lambda 결과를 모두 body dict로 정규화한다."""
    if not isinstance(value, dict):
        return {}

    if isinstance(value.get("Payload"), dict):
        return get_body(value.get("Payload"))

    return get_body(value)


def get_nested(value: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    current = value

    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default

    return current


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        if not value.strip():
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    return [value]


def unique_strings(values: List[Any]) -> List[str]:
    seen = set()
    result = []

    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)

    return result


def json_text(value: Any, limit: int = 12000) -> str:
    text = json.dumps(value or {}, ensure_ascii=False, default=str)
    if len(text) > limit:
        return text[:limit] + "...<truncated>"
    return text


def pick_service_from_payload(payload: Dict[str, Any], reference_context: Optional[Dict[str, Any]] = None) -> str:
    service = payload.get("service") or payload.get("serviceName")

    if not service and isinstance(reference_context, dict):
        service = get_nested(reference_context, ["referenceSurvey", "service"])

    profile = payload.get("profile")
    if not service and isinstance(profile, dict):
        service = profile.get("service") or profile.get("serviceName")

    return str(service or "").strip()


def categories_from_reference(reference_context: Dict[str, Any]) -> List[str]:
    categories = []

    for question in as_list(reference_context.get("questions")):
        if isinstance(question, dict):
            categories.append(question.get("category"))

    score_summary = reference_context.get("scoreSummary") or {}
    for item in as_list(score_summary.get("lowScoreResults")):
        if isinstance(item, dict):
            categories.append(item.get("category"))

    for item in as_list(score_summary.get("scoreResults")):
        if isinstance(item, dict):
            categories.append(item.get("category"))

    return unique_strings(categories)


def table_exists(table_name: str) -> bool:
    rows = query_rows(
        """
        SELECT to_regclass(:table_name)::text AS table_name
        """,
        [param_string("table_name", table_name)]
    )

    if not rows:
        return False

    return bool(rows[0].get("table_name"))


def get_report_base_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    survey_rows = query_rows(
        """
        SELECT
            survey_id,
            title,
            service,
            survey_type
        FROM survey
        WHERE survey_id = :survey_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    if not survey_rows:
        raise ValueError(f"survey not found: {survey_id}")

    survey_row = survey_rows[0]

    survey = {
        "surveyId": survey_row.get("survey_id"),
        "title": survey_row.get("title"),
        "service": survey_row.get("service"),
        "surveyType": survey_row.get("survey_type")
    }

    question_rows = query_rows(
        """
        SELECT
            question_code,
            question_type,
            category,
            question_text,
            display_order
        FROM survey_question
        WHERE survey_id = :survey_id
        ORDER BY display_order
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    questions = []

    for row in question_rows:
        questions.append({
            "code": row.get("question_code"),
            "type": row.get("question_type"),
            "category": row.get("category"),
            "text": row.get("question_text")
        })

    response_count_rows = query_rows(
        """
        SELECT
            COUNT(DISTINCT response_id) AS response_count
        FROM survey_response
        WHERE survey_id = :survey_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    response_count = 0
    if response_count_rows:
        response_count = response_count_rows[0].get("response_count") or 0

    score_rows = query_rows(
        """
        SELECT
            q.category AS category,
            ROUND(AVG(a.score_value)::numeric, 2)::text AS avg_score,
            ROUND(
                100.0 * SUM(CASE WHEN a.score_value IN (4, 5) THEN 1 ELSE 0 END) / COUNT(a.score_value),
                1
            )::text AS positive_rate,
            ROUND(
                100.0 * SUM(CASE WHEN a.score_value IN (1, 2) THEN 1 ELSE 0 END) / COUNT(a.score_value),
                1
            )::text AS negative_rate,
            ROUND(
                (
                    100.0 * SUM(CASE WHEN a.score_value IN (4, 5) THEN 1 ELSE 0 END) / COUNT(a.score_value)
                )
                -
                (
                    100.0 * SUM(CASE WHEN a.score_value IN (1, 2) THEN 1 ELSE 0 END) / COUNT(a.score_value)
                ),
                1
            )::text AS satisfaction_index,
            MIN(q.display_order) AS display_order
        FROM survey_question q
        JOIN survey_answer a
            ON q.survey_id = a.survey_id
           AND q.question_code = a.question_code
        WHERE q.survey_id = :survey_id
          AND q.question_type = 'SC5'
          AND a.score_value IS NOT NULL
        GROUP BY q.category
        ORDER BY MIN(q.display_order)
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    score_results = []

    for row in score_rows:
        score_results.append({
            "category": row.get("category"),
            "avgScore": float(row.get("avg_score") or 0),
            "positiveRate": float(row.get("positive_rate") or 0),
            "negativeRate": float(row.get("negative_rate") or 0),
            "satisfactionIndex": float(row.get("satisfaction_index") or 0)
        })

    overall_rows = query_rows(
        """
        SELECT
            ROUND(AVG(score_value)::numeric, 2)::text AS avg_score,
            ROUND(
                100.0 * SUM(CASE WHEN score_value IN (4, 5) THEN 1 ELSE 0 END) / COUNT(score_value),
                1
            )::text AS positive_rate,
            ROUND(
                100.0 * SUM(CASE WHEN score_value IN (1, 2) THEN 1 ELSE 0 END) / COUNT(score_value),
                1
            )::text AS negative_rate,
            ROUND(
                (
                    100.0 * SUM(CASE WHEN score_value IN (4, 5) THEN 1 ELSE 0 END) / COUNT(score_value)
                )
                -
                (
                    100.0 * SUM(CASE WHEN score_value IN (1, 2) THEN 1 ELSE 0 END) / COUNT(score_value)
                ),
                1
            )::text AS satisfaction_index
        FROM survey_answer
        WHERE survey_id = :survey_id
          AND answer_type = 'SC5'
          AND score_value IS NOT NULL
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    overall_avg = 0
    overall_positive_rate = 0
    overall_negative_rate = 0
    overall_satisfaction_index = 0

    if overall_rows:
        overall_avg = float(overall_rows[0].get("avg_score") or 0)
        overall_positive_rate = float(overall_rows[0].get("positive_rate") or 0)
        overall_negative_rate = float(overall_rows[0].get("negative_rate") or 0)
        overall_satisfaction_index = float(overall_rows[0].get("satisfaction_index") or 0)

    highest_category = ""
    lowest_category = ""

    if score_results:
        highest_category = max(score_results, key=lambda x: x.get("satisfactionIndex", 0)).get("category", "")
        lowest_category = min(score_results, key=lambda x: x.get("satisfactionIndex", 0)).get("category", "")

    aggregation = {
        "responseCount": response_count,
        "overall": {
            "avg": overall_avg,
            "positiveRate": overall_positive_rate,
            "negativeRate": overall_negative_rate,
            "satisfactionIndex": overall_satisfaction_index,
            "highestCategory": highest_category,
            "lowestCategory": lowest_category
        },
        "scoreResults": score_results
    }

    text_answer_rows = query_rows(
        """
        SELECT
            a.answer_id,
            a.survey_id,
            a.question_code,
            a.category,
            a.text_value
        FROM survey_answer a
        WHERE a.survey_id = :survey_id
          AND a.answer_type = 'TXT'
          AND a.text_value IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM text_analysis t
              WHERE t.answer_id = a.answer_id
          )
        ORDER BY a.answer_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    text_answers = []

    for row in text_answer_rows:
        text_answers.append({
            "answerId": row.get("answer_id"),
            "surveyId": row.get("survey_id"),
            "questionCode": row.get("question_code"),
            "category": row.get("category"),
            "text": row.get("text_value")
        })

    return success({
        "surveyId": survey_id,
        "survey": survey,
        "questions": questions,
        "aggregation": aggregation,
        "textAnswers": text_answers,
        "queriedAt": now_iso()
    })


def save_text_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")
    text_analysis_result = payload.get("textAnalysisResult")

    if not survey_id:
        raise ValueError("surveyId is required")

    analysis_body = get_body(text_analysis_result)
    results = analysis_body.get("results", [])
    summary = analysis_body.get("summary", {})

    if not isinstance(results, list):
        results = []

    saved_count = 0

    for result in results:
        if result.get("error"):
            continue

        scores = result.get("scores", {})
        keywords = result.get("keywords", [])

        execute_write(
            """
            INSERT INTO text_analysis (
                answer_id,
                survey_id,
                question_code,
                category,
                sentiment,
                pos_score,
                neu_score,
                neg_score,
                mix_score,
                keywords,
                analyzed_at
            )
            VALUES (
                :answer_id,
                :survey_id,
                :question_code,
                :category,
                :sentiment,
                :pos_score,
                :neu_score,
                :neg_score,
                :mix_score,
                CAST(:keywords AS JSONB),
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (answer_id)
            DO UPDATE SET
                sentiment = EXCLUDED.sentiment,
                pos_score = EXCLUDED.pos_score,
                neu_score = EXCLUDED.neu_score,
                neg_score = EXCLUDED.neg_score,
                mix_score = EXCLUDED.mix_score,
                keywords = EXCLUDED.keywords,
                analyzed_at = CURRENT_TIMESTAMP
            """,
            [
                param_string("answer_id", result.get("answerId")),
                param_string("survey_id", result.get("surveyId")),
                param_string("question_code", result.get("questionCode")),
                param_string("category", result.get("category")),
                param_string("sentiment", result.get("sentiment")),
                param_double("pos_score", scores.get("pos")),
                param_double("neu_score", scores.get("neu")),
                param_double("neg_score", scores.get("neg")),
                param_double("mix_score", scores.get("mix")),
                param_string("keywords", json.dumps(keywords, ensure_ascii=False))
            ]
        )

        saved_count += 1

    return success({
        "surveyId": survey_id,
        "saved": True,
        "savedCount": saved_count,
        "analysisSummary": summary,
        "savedAt": now_iso()
    })


def build_report_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    base_data_result = payload.get("baseDataResult")
    base_data_body = get_body(base_data_result)

    survey = base_data_body.get("survey", {})
    aggregation = base_data_body.get("aggregation", {})

    sentiment_rows = query_rows(
        """
        SELECT
            sentiment,
            COUNT(*) AS count
        FROM text_analysis
        WHERE survey_id = :survey_id
        GROUP BY sentiment
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    sentiment_summary = {
        "POSITIVE": 0,
        "NEUTRAL": 0,
        "NEGATIVE": 0,
        "MIXED": 0
    }

    for row in sentiment_rows:
        sentiment = row.get("sentiment")
        count = row.get("count") or 0

        if sentiment in sentiment_summary:
            sentiment_summary[sentiment] = count

    keyword_rows = query_rows(
        """
        SELECT
            keyword_item ->> 'text' AS keyword,
            COUNT(*) AS count
        FROM text_analysis,
             jsonb_array_elements(keywords) AS keyword_item
        WHERE survey_id = :survey_id
        GROUP BY keyword_item ->> 'text'
        ORDER BY count DESC, keyword ASC
        LIMIT 10
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    text_keywords = []

    for row in keyword_rows:
        text_keywords.append({
            "keyword": row.get("keyword"),
            "count": row.get("count") or 0
        })

    text_sentiment = {
        "pos": sentiment_summary.get("POSITIVE", 0),
        "neu": sentiment_summary.get("NEUTRAL", 0),
        "neg": sentiment_summary.get("NEGATIVE", 0),
        "mix": sentiment_summary.get("MIXED", 0)
    }

    top_issues = []

    for keyword in text_keywords:
        keyword_text = keyword.get("keyword")

        if not keyword_text:
            continue

        if keyword_text in ["메뉴", "이체 단계", "앱 실행", "첫 화면 로딩"]:
            top_issues.append(f"{keyword_text} 관련 불편 의견이 확인됨")

    if not top_issues:
        top_issues = [
            "메뉴 탐색이 어렵다",
            "이체 단계가 복잡하다",
            "앱 실행과 화면 전환이 느리다"
        ]

    report_input = {
        "type": "REPORT_INPUT",
        "survey": {
            "title": survey.get("title", "스타뱅킹 모바일 앱 이용 고객 경험 설문"),
            "service": survey.get("service", "스타뱅킹"),
            "surveyType": survey.get("surveyType", "VOC")
        },
        "aggregation": {
            "responseCount": aggregation.get("responseCount", 0),
            "overall": aggregation.get("overall", {}),
            "scoreResults": aggregation.get("scoreResults", []),
            "textSentiment": text_sentiment,
            "textKeywords": text_keywords,
            "topIssues": top_issues
        }
    }

    return success({
        "surveyId": survey_id,
        "reportInput": report_input,
        "builtAt": now_iso()
    })



def get_survey_reference_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    reference_survey_id = payload.get("referenceSurveyId")

    if not reference_survey_id:
        raise ValueError("referenceSurveyId is required")

    base_result = get_report_base_data({
        "surveyId": reference_survey_id
    })

    base_body = get_body(base_result)

    sentiment_rows = query_rows(
        """
        SELECT
            sentiment,
            COUNT(*) AS count
        FROM text_analysis
        WHERE survey_id = :survey_id
        GROUP BY sentiment
        """,
        [
            param_string("survey_id", reference_survey_id)
        ]
    )

    sentiment_summary = {
        "POSITIVE": 0,
        "NEUTRAL": 0,
        "NEGATIVE": 0,
        "MIXED": 0
    }

    for row in sentiment_rows:
        sentiment = row.get("sentiment")
        count = row.get("count") or 0

        if sentiment in sentiment_summary:
            sentiment_summary[sentiment] = count

    keyword_rows = query_rows(
        """
        SELECT
            keyword_item ->> 'text' AS keyword,
            COUNT(*) AS count
        FROM text_analysis,
             jsonb_array_elements(keywords) AS keyword_item
        WHERE survey_id = :survey_id
        GROUP BY keyword_item ->> 'text'
        ORDER BY count DESC, keyword ASC
        LIMIT 15
        """,
        [
            param_string("survey_id", reference_survey_id)
        ]
    )

    keywords = []

    for row in keyword_rows:
        keywords.append({
            "keyword": row.get("keyword"),
            "count": row.get("count") or 0
        })

    report_rows = query_rows(
        """
        SELECT
            report_id,
            report_json::text AS report_json,
            created_at::text AS created_at
        FROM survey_report
        WHERE survey_id = :survey_id
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [
            param_string("survey_id", reference_survey_id)
        ]
    )

    latest_report = {}

    if report_rows:
        report_json_text = report_rows[0].get("report_json")

        if report_json_text:
            latest_report = json.loads(report_json_text)

    low_score_results = []
    category_signals = []

    aggregation = base_body.get("aggregation", {})
    score_results = aggregation.get("scoreResults", [])

    for item in score_results:
        avg_score = item.get("avgScore", 0)
        negative_rate = item.get("negativeRate", 0)
        satisfaction_index = item.get("satisfactionIndex", 0)
        category = item.get("category")

        signal = {
            "category": category,
            "avgScore": avg_score,
            "positiveRate": item.get("positiveRate", 0),
            "negativeRate": negative_rate,
            "satisfactionIndex": satisfaction_index,
            "priority": "NORMAL"
        }

        if avg_score < 3.3 or negative_rate >= 25 or satisfaction_index < 20:
            signal["priority"] = "HIGH"
            low_score_results.append(item)

        category_signals.append(signal)

    reference_context = {
        "referenceSurvey": base_body.get("survey", {}),
        "questions": base_body.get("questions", []),
        "scoreSummary": {
            "responseCount": aggregation.get("responseCount", 0),
            "overall": aggregation.get("overall", {}),
            "lowScoreResults": low_score_results,
            "scoreResults": score_results,
            "categorySignals": category_signals
        },
        "textSummary": {
            "sentiment": {
                "pos": sentiment_summary.get("POSITIVE", 0),
                "neu": sentiment_summary.get("NEUTRAL", 0),
                "neg": sentiment_summary.get("NEGATIVE", 0),
                "mix": sentiment_summary.get("MIXED", 0)
            },
            "keywords": keywords
        },
        "latestReport": {
            "reportId": report_rows[0].get("report_id") if report_rows else None,
            "createdAt": report_rows[0].get("created_at") if report_rows else None,
            "summary": latest_report.get("summary"),
            "point": latest_report.get("point"),
            "action": latest_report.get("action"),
            "conclusion": latest_report.get("conclusion")
        },
        "generationHints": {
            "recommendedFocusCategories": unique_strings([item.get("category") for item in low_score_results]),
            "reuseReferenceQuestionStyle": True,
            "avoidDuplicatingExactQuestions": True
        }
    }

    return success({
        "referenceSurveyId": reference_survey_id,
        "referenceContext": reference_context,
        "queriedAt": now_iso()
    })


def get_service_category_knowledge(payload: Dict[str, Any]) -> Dict[str, Any]:
    """서비스/카테고리별 배경지식을 DB에서 가져온다.

    필요한 테이블은 001_service_category_knowledge.sql에 포함되어 있다.
    테이블이 아직 없으면 빈 knowledgeItems를 반환해 Step Function이 실패하지 않도록 한다.
    """
    reference_data_body = get_lambda_body(payload.get("referenceDataResult"))
    reference_context = reference_data_body.get("referenceContext", {})

    service = pick_service_from_payload(payload, reference_context)
    categories = unique_strings(
        as_list(payload.get("categories"))
        + categories_from_reference(reference_context)
    )
    limit = int(payload.get("limit", 30))

    if not table_exists("public.service_category_knowledge"):
        return success({
            "service": service,
            "categories": categories,
            "knowledgeItems": [],
            "found": False,
            "message": "service_category_knowledge table does not exist. Run 001_service_category_knowledge.sql first.",
            "queriedAt": now_iso()
        })

    if service:
        rows = query_rows(
            """
            SELECT
                knowledge_id,
                service,
                category,
                stage,
                quality_dimension,
                background_text,
                tags::text AS tags,
                priority,
                updated_at::text AS updated_at
            FROM service_category_knowledge
            WHERE is_active = TRUE
              AND service = :service
            ORDER BY priority DESC, updated_at DESC
            LIMIT :limit
            """,
            [
                param_string("service", service),
                param_long("limit", limit)
            ]
        )
    else:
        rows = query_rows(
            """
            SELECT
                knowledge_id,
                service,
                category,
                stage,
                quality_dimension,
                background_text,
                tags::text AS tags,
                priority,
                updated_at::text AS updated_at
            FROM service_category_knowledge
            WHERE is_active = TRUE
            ORDER BY priority DESC, updated_at DESC
            LIMIT :limit
            """,
            [param_long("limit", limit)]
        )

    category_set = set(categories)

    def rank(row: Dict[str, Any]) -> int:
        score = int(row.get("priority") or 0)
        if category_set and row.get("category") in category_set:
            score += 1000
        return score

    rows = sorted(rows, key=rank, reverse=True)[:limit]

    knowledge_items = []
    for row in rows:
        tags = []
        tags_text = row.get("tags")
        if tags_text:
            try:
                tags = json.loads(tags_text)
            except json.JSONDecodeError:
                tags = []

        knowledge_items.append({
            "knowledgeId": row.get("knowledge_id"),
            "service": row.get("service"),
            "category": row.get("category"),
            "stage": row.get("stage"),
            "qualityDimension": row.get("quality_dimension"),
            "backgroundText": row.get("background_text"),
            "tags": tags,
            "priority": row.get("priority") or 0,
            "updatedAt": row.get("updated_at")
        })

    return success({
        "service": service,
        "categories": categories,
        "knowledgeItems": knowledge_items,
        "found": len(knowledge_items) > 0,
        "queriedAt": now_iso()
    })


def build_survey_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_request = payload.get("userRequest")
    reference_data_result = payload.get("referenceDataResult")
    service_knowledge_result = payload.get("serviceKnowledgeResult")
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload

    if not user_request:
        raise ValueError("userRequest is required")

    reference_data_body = get_lambda_body(reference_data_result)
    reference_context = reference_data_body.get("referenceContext", {})

    service_knowledge_body = get_lambda_body(service_knowledge_result)
    service_knowledge_context = {
        "service": service_knowledge_body.get("service") or pick_service_from_payload(profile, reference_context),
        "categories": service_knowledge_body.get("categories", []),
        "knowledgeItems": service_knowledge_body.get("knowledgeItems", []),
        "found": service_knowledge_body.get("found", False)
    }

    cx_stages = unique_strings(as_list(profile.get("customerExperienceStages"))) or DEFAULT_CX_STAGES
    quality_dimensions = unique_strings(as_list(profile.get("serviceQualityDimensions"))) or DEFAULT_SERVICE_QUALITY_DIMENSIONS
    requested_question_count = profile.get("questionCount") or profile.get("requestedQuestionCount") or 10
    include_voc = profile.get("includeVoc")
    if include_voc is None:
        include_voc = True

    reference_context_text = json_text(reference_context)
    service_knowledge_text = json_text(service_knowledge_context)

    use_reference = bool(reference_context)

    reference_rule = """
[참고 설문 반영 규칙]
1. REFERENCE_CONTEXT의 기존 설문 문항 구조와 카테고리를 참고하되, 같은 문장을 그대로 복제하지 않는다.
2. lowScoreResults, categorySignals.priority=HIGH, latestReport.point/action을 우선 반영한다.
3. textSummary.keywords에 반복 등장한 불편 키워드는 최소 2개 이상 문항에 자연스럽게 반영한다.
4. SERVICE_CATEGORY_KNOWLEDGE의 배경지식은 해당 서비스 특성/카테고리 맥락으로 사용한다.
""" if use_reference else """
[무참고 생성 규칙]
1. referenceSurveyId가 없으므로 DB 참고 설문 없이 생성한다.
2. 그래도 고객경험단계와 서비스품질 축은 반드시 반영한다.
3. 이 방식은 초기 초안용이며, 실제 운영에서는 참고 설문/서비스 배경지식을 연결하는 것을 권장한다.
"""

    survey_request = f"""
너는 KBDS HappyLoop의 금융/디지털 서비스 VOC 설문 생성 Agent다.
아래 사용자 요청을 바탕으로 관리자 화면에 저장 가능한 설문 JSON을 생성해라.

[사용자 요청]
{user_request}

[생성 목표]
- 고객 경험 단계와 서비스품질 차원을 균형 있게 반영한다.
- 단순 만족도 문항이 아니라, 실제 서비스 접점에서 개선 액션을 뽑을 수 있는 문항을 만든다.
- 참고 설문이 있을 때는 기존 설문양식, 응답 분석, VOC 키워드, 최신 보고서의 개선 포인트를 후속 설문 설계에 반영한다.
- 서비스 카테고리 배경지식이 있을 때는 해당 서비스의 업무/이용 맥락을 문항에 녹인다.

[고객경험단계]
{json.dumps(cx_stages, ensure_ascii=False)}

[서비스품질 차원]
{json.dumps(quality_dimensions, ensure_ascii=False)}

[문항 설계 규칙]
1. 총 {requested_question_count}개 내외로 생성하되, 최소 8개 이상 최대 12개 이하로 구성한다.
2. SC5 척도 문항을 중심으로 만들고, 마지막에는 TXT 주관식/VOC 문항을 1~2개 포함한다.
3. SC5 문항은 1점 매우 불만족 ~ 5점 매우 만족 기준으로 답할 수 있어야 한다.
4. category는 "고객경험단계 | 서비스품질차원 | 세부카테고리" 형태로 작성한다.
5. 개인정보, 이름, 전화번호, 계좌번호 등 민감정보 입력을 유도하지 않는다.
6. 문항은 한 번에 하나의 경험만 묻고, 이중 질문을 피한다.
7. 운영자가 바로 액션을 뽑을 수 있도록 메뉴, 속도, 안내, 오류, 상담/지원, 재이용 같은 구체 접점을 포함한다.
{reference_rule}

[REFERENCE_CONTEXT]
{reference_context_text}

[SERVICE_CATEGORY_KNOWLEDGE]
{service_knowledge_text}

[반드시 지켜야 할 출력 형식]
설명 없이 JSON 하나만 출력한다.
질문 객체에는 code, type, category, text 4개 필드만 넣는다.
허용 type은 "SC5" 또는 "TXT"뿐이다.

{{
  "type": "SURVEY",
  "title": "",
  "service": "",
  "surveyType": "VOC",
  "questions": [
    {{"code": "Q01", "type": "SC5", "category": "핵심 이용/처리 | 신뢰성 | 거래 처리", "text": ""}},
    {{"code": "Q02", "type": "SC5", "category": "문제해결/지원 | 응답성 | 고객 지원", "text": ""}},
    {{"code": "Q99", "type": "TXT", "category": "VOC | 개선의견 | 자유의견", "text": ""}}
  ]
}}
""".strip()

    return success({
        "userRequest": survey_request,
        "referenceContext": reference_context,
        "serviceKnowledgeContext": service_knowledge_context,
        "qualityFramework": {
            "customerExperienceStages": cx_stages,
            "serviceQualityDimensions": quality_dimensions
        },
        "useReference": use_reference,
        "builtAt": now_iso()
    })


def list_surveys(payload: Dict[str, Any]) -> Dict[str, Any]:
    limit = int(payload.get("limit", 20))

    rows = query_rows(
        """
        SELECT
            s.survey_id,
            s.title,
            s.service,
            s.survey_type,
            s.created_at::text AS created_at,
            COUNT(DISTINCT q.question_code) AS question_count,
            COUNT(DISTINCT r.response_id) AS response_count
        FROM survey s
        LEFT JOIN survey_question q
            ON s.survey_id = q.survey_id
        LEFT JOIN survey_response r
            ON s.survey_id = r.survey_id
        GROUP BY
            s.survey_id,
            s.title,
            s.service,
            s.survey_type,
            s.created_at
        ORDER BY s.created_at DESC
        LIMIT :limit
        """,
        [
            param_long("limit", limit)
        ]
    )

    surveys = []

    for row in rows:
        surveys.append({
            "surveyId": row.get("survey_id"),
            "title": row.get("title"),
            "service": row.get("service"),
            "surveyType": row.get("survey_type"),
            "createdAt": row.get("created_at"),
            "questionCount": row.get("question_count") or 0,
            "responseCount": row.get("response_count") or 0
        })

    return success({
        "surveys": surveys,
        "count": len(surveys)
    })


def list_reports(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    rows = query_rows(
        """
        SELECT
            report_id,
            survey_id,
            report_json ->> 'title' AS title,
            report_json ->> 'service' AS service,
            report_json ->> 'summary' AS summary,
            report_json -> 'overall' ->> 'avg' AS overall_avg,
            report_json -> 'overall' ->> 'idx' AS overall_idx,
            created_at::text AS created_at
        FROM survey_report
        WHERE survey_id = :survey_id
        ORDER BY created_at DESC
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    reports = []

    for row in rows:
        reports.append({
            "reportId": row.get("report_id"),
            "surveyId": row.get("survey_id"),
            "title": row.get("title"),
            "service": row.get("service"),
            "summary": row.get("summary"),
            "overallAvg": float(row.get("overall_avg") or 0),
            "overallIdx": float(row.get("overall_idx") or 0),
            "createdAt": row.get("created_at")
        })

    return success({
        "surveyId": survey_id,
        "reports": reports,
        "count": len(reports)
    })


def get_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_id = payload.get("reportId")

    if not report_id:
        raise ValueError("reportId is required")

    rows = query_rows(
        """
        SELECT
            report_id,
            survey_id,
            report_json::text AS report_json,
            created_at::text AS created_at
        FROM survey_report
        WHERE report_id = :report_id
        """,
        [
            param_string("report_id", report_id)
        ]
    )

    if not rows:
        return success({
            "found": False,
            "report": None
        })

    row = rows[0]
    report_json_text = row.get("report_json")
    report = json.loads(report_json_text) if report_json_text else None

    return success({
        "found": True,
        "reportId": row.get("report_id"),
        "surveyId": row.get("survey_id"),
        "createdAt": row.get("created_at"),
        "report": report
    })

def save_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")
    agent_result = payload.get("agentResult")

    if not survey_id:
        raise ValueError("surveyId is required")

    agent_body = get_body(agent_result)
    report = agent_body.get("json")

    if not report:
        raise ValueError("agentResult.body.json is required")

    report_id = payload.get("reportId") or f"RPT-{uuid.uuid4().hex[:12].upper()}"

    execute_write(
        """
        INSERT INTO survey_report (
            report_id,
            survey_id,
            report_json,
            created_at
        )
        VALUES (
            :report_id,
            :survey_id,
            CAST(:report_json AS JSONB),
            CURRENT_TIMESTAMP
        )
        """,
        [
            param_string("report_id", report_id),
            param_string("survey_id", survey_id),
            param_string("report_json", json.dumps(report, ensure_ascii=False))
        ]
    )

    return success({
        "surveyId": survey_id,
        "reportId": report_id,
        "saved": True,
        "report": report,
        "savedAt": now_iso()
    })

def get_survey(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    survey_rows = query_rows(
        """
        SELECT
            survey_id,
            title,
            service,
            survey_type,
            created_at::text AS created_at
        FROM survey
        WHERE survey_id = :survey_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    if not survey_rows:
        raise ValueError(f"survey not found: {survey_id}")

    survey_row = survey_rows[0]

    question_rows = query_rows(
        """
        SELECT
            question_code,
            question_type,
            category,
            question_text,
            display_order
        FROM survey_question
        WHERE survey_id = :survey_id
        ORDER BY display_order
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    questions = []

    for row in question_rows:
        questions.append({
            "code": row.get("question_code"),
            "type": row.get("question_type"),
            "category": row.get("category"),
            "text": row.get("question_text"),
            "displayOrder": row.get("display_order")
        })

    return success({
        "surveyId": survey_id,
        "survey": {
            "surveyId": survey_row.get("survey_id"),
            "title": survey_row.get("title"),
            "service": survey_row.get("service"),
            "surveyType": survey_row.get("survey_type"),
            "createdAt": survey_row.get("created_at"),
            "questions": questions
        }
    })


def get_latest_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    report_rows = query_rows(
        """
        SELECT
            report_id,
            survey_id,
            report_json::text AS report_json,
            created_at::text AS created_at
        FROM survey_report
        WHERE survey_id = :survey_id
        ORDER BY created_at DESC
        LIMIT 1
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    if not report_rows:
        return success({
            "surveyId": survey_id,
            "found": False,
            "report": None
        })

    report_row = report_rows[0]
    report_json_text = report_row.get("report_json")
    report = json.loads(report_json_text) if report_json_text else None

    return success({
        "surveyId": survey_id,
        "found": True,
        "reportId": report_row.get("report_id"),
        "createdAt": report_row.get("created_at"),
        "report": report
    })    


def save_survey(payload: Dict[str, Any]) -> Dict[str, Any]:
    agent_result = payload.get("agentResult")

    agent_body = get_body(agent_result)
    survey_json = agent_body.get("json")

    if not survey_json:
        raise ValueError("agentResult.body.json is required")

    if survey_json.get("type") != "SURVEY":
        raise ValueError("agentResult.body.json.type must be SURVEY")

    questions = survey_json.get("questions")

    if not isinstance(questions, list):
        raise ValueError("survey questions must be an array")

    survey_id = payload.get("surveyId") or f"SURV-{uuid.uuid4().hex[:12].upper()}"

    execute_write(
        """
        INSERT INTO survey (
            survey_id,
            title,
            service,
            survey_type,
            created_at
        )
        VALUES (
            :survey_id,
            :title,
            :service,
            :survey_type,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (survey_id)
        DO UPDATE SET
            title = EXCLUDED.title,
            service = EXCLUDED.service,
            survey_type = EXCLUDED.survey_type
        """,
        [
            param_string("survey_id", survey_id),
            param_string("title", survey_json.get("title")),
            param_string("service", survey_json.get("service")),
            param_string("survey_type", survey_json.get("surveyType"))
        ]
    )

    execute_write(
        """
        DELETE FROM survey_question
        WHERE survey_id = :survey_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    for index, question in enumerate(questions, start=1):
        execute_write(
            """
            INSERT INTO survey_question (
                survey_id,
                question_code,
                question_type,
                category,
                question_text,
                display_order
            )
            VALUES (
                :survey_id,
                :question_code,
                :question_type,
                :category,
                :question_text,
                :display_order
            )
            """,
            [
                param_string("survey_id", survey_id),
                param_string("question_code", question.get("code")),
                param_string("question_type", question.get("type")),
                param_string("category", question.get("category")),
                param_string("question_text", question.get("text")),
                param_long("display_order", index)
            ]
        )

    return success({
        "surveyId": survey_id,
        "saved": True,
        "survey": {
            "type": survey_json.get("type"),
            "title": survey_json.get("title"),
            "service": survey_json.get("service"),
            "surveyType": survey_json.get("surveyType"),
            "questions": questions
        },
        "questionCount": len(questions),
        "savedAt": now_iso()
    })

def submit_survey_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")
    answers = payload.get("answers")

    if not survey_id:
        raise ValueError("surveyId is required")

    if not isinstance(answers, list) or len(answers) == 0:
        raise ValueError("answers must be a non-empty array")

    survey_rows = query_rows(
        """
        SELECT
            survey_id
        FROM survey
        WHERE survey_id = :survey_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    if not survey_rows:
        raise ValueError(f"survey not found: {survey_id}")

    question_rows = query_rows(
        """
        SELECT
            question_code,
            question_type,
            category
        FROM survey_question
        WHERE survey_id = :survey_id
        """,
        [
            param_string("survey_id", survey_id)
        ]
    )

    question_map = {}

    for row in question_rows:
        question_map[row.get("question_code")] = {
            "type": row.get("question_type"),
            "category": row.get("category")
        }

    response_id = payload.get("responseId") or f"RESP-{uuid.uuid4().hex[:12].upper()}"

    execute_write(
        """
        INSERT INTO survey_response (
            response_id,
            survey_id,
            submitted_at
        )
        VALUES (
            :response_id,
            :survey_id,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (response_id)
        DO NOTHING
        """,
        [
            param_string("response_id", response_id),
            param_string("survey_id", survey_id)
        ]
    )

    saved_answers = []

    for answer in answers:
        question_code = answer.get("questionCode") or answer.get("code")

        if not question_code:
            raise ValueError("questionCode is required")

        question = question_map.get(question_code)

        if not question:
            raise ValueError(f"question not found: {question_code}")

        question_type = question.get("type")
        category = question.get("category")

        score_value = None
        text_value = None

        if question_type == "SC5":
            score_value = answer.get("scoreValue")

            if score_value is None:
                score_value = answer.get("score")

            if score_value is None:
                raise ValueError(f"scoreValue is required for {question_code}")

            score_value = int(score_value)

            if score_value < 1 or score_value > 5:
                raise ValueError(f"scoreValue must be between 1 and 5 for {question_code}")

        elif question_type == "TXT":
            text_value = answer.get("textValue")

            if text_value is None:
                text_value = answer.get("text")

            if text_value is None:
                text_value = ""

        else:
            raise ValueError(f"unsupported question type: {question_type}")

        answer_id = f"{response_id}-{question_code}"

        execute_write(
            """
            INSERT INTO survey_answer (
                answer_id,
                response_id,
                survey_id,
                question_code,
                category,
                answer_type,
                score_value,
                text_value,
                created_at
            )
            VALUES (
                :answer_id,
                :response_id,
                :survey_id,
                :question_code,
                :category,
                :answer_type,
                :score_value,
                :text_value,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (answer_id)
            DO UPDATE SET
                category = EXCLUDED.category,
                answer_type = EXCLUDED.answer_type,
                score_value = EXCLUDED.score_value,
                text_value = EXCLUDED.text_value,
                created_at = CURRENT_TIMESTAMP
            """,
            [
                param_string("answer_id", answer_id),
                param_string("response_id", response_id),
                param_string("survey_id", survey_id),
                param_string("question_code", question_code),
                param_string("category", category),
                param_string("answer_type", question_type),
                param_long("score_value", score_value),
                param_string("text_value", text_value)
            ]
        )

        saved_answers.append({
            "answerId": answer_id,
            "questionCode": question_code,
            "type": question_type,
            "category": category
        })

    return success({
        "surveyId": survey_id,
        "responseId": response_id,
        "saved": True,
        "answerCount": len(saved_answers),
        "answers": saved_answers,
        "submittedAt": now_iso()
    })

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        payload = parse_event(event)
        action = payload.get("action")

        if action == "getReportBaseData":
            return get_report_base_data(payload)

        if action == "saveTextAnalysis":
            return save_text_analysis(payload)

        if action == "buildReportInput":
            return build_report_input(payload)

        if action == "getSurveyReferenceData":
            return get_survey_reference_data(payload)

        if action == "getServiceCategoryKnowledge":
            return get_service_category_knowledge(payload)

        if action == "buildSurveyRequest":
            return build_survey_request(payload)

        if action == "getSurvey":
            return get_survey(payload)

        if action == "getLatestReport":
            return get_latest_report(payload)

        if action == "saveReport":
            return save_report(payload)

        if action == "saveSurvey":
            return save_survey(payload)
        
        if action == "listSurveys":
            return list_surveys(payload)

        if action == "listReports":
            return list_reports(payload)

        if action == "getReport":
            return get_report(payload)

        if action == "submitSurveyResponse":
            return submit_survey_response(payload)

        return error(f"Unsupported action: {action}", 400)

    except Exception as e:
        return error(str(e), 500)