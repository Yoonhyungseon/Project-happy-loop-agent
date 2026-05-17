import json
import os
import uuid
from typing import Any, Dict, Optional, Tuple

import boto3


BEDROCK_REGION = (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "ap-northeast-2"
)

BEDROCK_AGENT_ID = os.environ.get("BEDROCK_AGENT_ID", "")
BEDROCK_AGENT_ALIAS_ID = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "")

sts = boto3.client("sts")
agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=BEDROCK_REGION
)


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


def extract_json(raw_text: str) -> Optional[Any]:
    if not raw_text:
        return None

    text = raw_text.strip()

    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    json_text = text[start:end + 1]
    return json.loads(json_text)




def build_survey_generation_prompt(user_request: str) -> str:
    return f"""
너는 금융/디지털 서비스 고객경험 설문 생성 전문 AI Agent다.
아래 요청은 이미 DB 참고 문맥, 고객경험단계, 서비스품질 차원, 출력 스키마를 포함할 수 있다.
요청을 충실히 따르고, 반드시 JSON 하나만 반환해라.

[핵심 원칙]
1. 고객경험단계와 서비스품질 차원을 균형 있게 반영한다.
2. 참고 설문/응답/VOC/서비스 배경지식이 제공되면 이를 우선 사용한다.
3. 같은 문항을 반복하거나 참고 설문의 질문을 그대로 복사하지 않는다.
4. 개인정보 입력을 유도하지 않는다.
5. 모든 질문 객체는 code, type, category, text 필드만 가진다.
6. type은 SC5 또는 TXT만 사용한다.
7. SC5는 1~5점 만족도 척도로 답할 수 있는 문장으로 작성한다.
8. TXT는 개선 의견이나 불편 경험을 구체적으로 적도록 묻되 개인정보를 요구하지 않는다.

[사용자/시스템 요청]
{user_request}

[최종 출력]
설명, 마크다운, 코드블록 없이 아래 JSON 스키마를 만족하는 JSON 객체만 출력한다.
{{
  "type": "SURVEY",
  "title": "",
  "service": "",
  "surveyType": "VOC",
  "questions": [
    {{"code": "Q01", "type": "SC5", "category": "", "text": ""}},
    {{"code": "Q99", "type": "TXT", "category": "VOC | 개선의견 | 자유의견", "text": ""}}
  ]
}}
""".strip()


def build_prompt(payload: Dict[str, Any]) -> Tuple[str, str]:
    action = payload.get("action", "raw")

    if action == "createSurvey":
        user_request = payload.get("userRequest") or payload.get("prompt")

        if not user_request:
            raise ValueError("createSurvey action requires userRequest or prompt")

        return build_survey_generation_prompt(user_request.strip()), "SURVEY"

    if action == "generateReport":
        report_input = payload.get("reportInput")
    
        if not report_input:
            raise ValueError("generateReport action requires reportInput")
    
        report_input_text = json.dumps(report_input, ensure_ascii=False)
    
        prompt = f"""
    너는 금융 서비스 고객 경험(VOC) 분석 전문 AI Agent다.
    
    아래 REPORT_INPUT 데이터를 기반으로
    고객 응답 결과를 분석하고
    관리자용 VOC 분석 보고서를 생성해라.
    
    반드시 아래 규칙을 지켜라.
    
    [분석 규칙]
    1. 응답 데이터를 기반으로 전체 만족도를 분석한다.
    2. 긍정 의견과 부정 의견을 구분한다.
    3. 반복적으로 등장하는 핵심 키워드를 추출한다.
    4. 고객 불편사항(pain point)을 요약한다.
    5. 실제 운영자가 바로 참고할 수 있는 개선 액션을 제안한다.
    6. 과장된 표현 없이 데이터 기반으로 분석한다.
    7. 이름, 전화번호 등 개인정보는 출력하지 않는다.
    8. 반드시 JSON 형식으로만 응답한다.
    
    [REPORT_INPUT]
    {report_input_text}
    
    [응답 JSON 형식]
    {{
      "type": "REPORT",
      "title": "",
      "service": "",
      "n": 0,
      "overall": {{
        "avg": 0,
        "pos": 0,
        "neg": 0,
        "idx": "",
        "high": "",
        "low": ""
      }},
      "areas": [
        {{
          "cat": "",
          "avg": 0,
          "idx": "",
          "status": "GOOD"
        }}
      ],
      "summary": "",
      "point": [
        ""
      ],
      "action": [
        ""
      ],
      "conclusion": ""
    }}
    """.strip()
    
        return prompt, "REPORT"
    
    prompt = payload.get("prompt")

    if not prompt:
        raise ValueError("raw action requires prompt")

    return prompt.strip(), payload.get("expectedType", "")


def get_caller_info() -> Dict[str, Any]:
    identity = sts.get_caller_identity()

    return {
        "account": identity.get("Account"),
        "arn": identity.get("Arn"),
        "userId": identity.get("UserId")
    }


def invoke_agent(prompt: str, session_id: str) -> str:
    response = agent_runtime.invoke_agent(
        agentId=BEDROCK_AGENT_ID,
        agentAliasId=BEDROCK_AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=prompt,
        enableTrace=False
    )

    chunks = []

    for event in response.get("completion", []):
        chunk = event.get("chunk")

        if not chunk:
            continue

        chunk_bytes = chunk.get("bytes")

        if not chunk_bytes:
            continue

        chunks.append(chunk_bytes.decode("utf-8"))

    return "".join(chunks).strip()



def validate_survey(parsed_json: Dict[str, Any]) -> None:
    for field in ["type", "title", "service", "surveyType", "questions"]:
        if field not in parsed_json:
            raise ValueError(f"SURVEY response requires {field}")

    questions = parsed_json.get("questions")

    if not isinstance(questions, list):
        raise ValueError("SURVEY response requires questions array")

    if len(questions) < 3:
        raise ValueError("SURVEY questions array must contain at least 3 questions")

    if len(questions) > 20:
        raise ValueError("SURVEY questions array must contain at most 20 questions")

    seen_codes = set()
    txt_count = 0
    sc5_count = 0

    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("SURVEY question must be an object")

        allowed_fields = {"code", "type", "category", "text"}
        required_fields = {"code", "type", "category", "text"}

        missing_fields = required_fields - set(question.keys())

        if missing_fields:
            raise ValueError(f"SURVEY question missing fields: {sorted(missing_fields)}")

        extra_fields = set(question.keys()) - allowed_fields

        if extra_fields:
            raise ValueError(f"SURVEY question has unsupported fields: {sorted(extra_fields)}")

        code = str(question.get("code") or "").strip()
        category = str(question.get("category") or "").strip()
        text = str(question.get("text") or "").strip()

        if not code:
            raise ValueError("SURVEY question code is empty")

        if code in seen_codes:
            raise ValueError(f"duplicated question code: {code}")

        seen_codes.add(code)

        if not category:
            raise ValueError(f"SURVEY question category is empty: {code}")

        if not text:
            raise ValueError(f"SURVEY question text is empty: {code}")

        question_type = question.get("type")

        if question_type not in ["SC5", "TXT"]:
            raise ValueError(f"Invalid question type: {question_type}")

        if question_type == "TXT":
            txt_count += 1
        if question_type == "SC5":
            sc5_count += 1

    if sc5_count == 0:
        raise ValueError("SURVEY must contain at least one SC5 question")

    if txt_count == 0:
        raise ValueError("SURVEY must contain at least one TXT question")


def validate_report(parsed_json: Dict[str, Any]) -> None:
    required_fields = [
        "type",
        "title",
        "service",
        "n",
        "overall",
        "areas",
        "summary",
        "point",
        "action",
        "conclusion"
    ]

    for field in required_fields:
        if field not in parsed_json:
            raise ValueError(f"REPORT response requires {field}")

    overall = parsed_json.get("overall")

    if not isinstance(overall, dict):
        raise ValueError("REPORT overall must be an object")

    for field in ["avg", "pos", "neg", "idx", "high", "low"]:
        if field not in overall:
            raise ValueError(f"REPORT overall requires {field}")

    areas = parsed_json.get("areas")

    if not isinstance(areas, list):
        raise ValueError("REPORT areas must be an array")

    for area in areas:
        allowed_fields = {"cat", "avg", "idx", "status"}
        required_area_fields = {"cat", "avg", "idx", "status"}

        missing_fields = required_area_fields - set(area.keys())

        if missing_fields:
            raise ValueError(f"REPORT area missing fields: {sorted(missing_fields)}")

        extra_fields = set(area.keys()) - allowed_fields

        if extra_fields:
            raise ValueError(f"REPORT area has unsupported fields: {sorted(extra_fields)}")

        status = area.get("status")

        if status not in ["GOOD", "NORMAL", "WATCH", "BAD"]:
            raise ValueError(f"Invalid area status: {status}")


def validate_result(parsed_json: Any, expected_type: str) -> None:
    if not expected_type:
        return

    if not isinstance(parsed_json, dict):
        raise ValueError("Agent response is not a JSON object")

    actual_type = parsed_json.get("type")

    if actual_type != expected_type:
        raise ValueError(f"Invalid response type. expected={expected_type}, actual={actual_type}")

    if expected_type == "SURVEY":
        validate_survey(parsed_json)

    if expected_type == "REPORT":
        validate_report(parsed_json)


def build_debug_info(context: Any) -> Dict[str, Any]:
    caller_info = get_caller_info()

    return {
        "caller": caller_info,
        "bedrockRegion": BEDROCK_REGION,
        "agentId": BEDROCK_AGENT_ID,
        "agentAliasId": BEDROCK_AGENT_ALIAS_ID,
        "functionName": context.function_name if context else None,
        "functionArn": context.invoked_function_arn if context else None
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    debug_info = build_debug_info(context)

    if not BEDROCK_AGENT_ID:
        return {
            "statusCode": 500,
            "body": {
                "message": "BEDROCK_AGENT_ID environment variable is required",
                "debug": debug_info
            }
        }

    if not BEDROCK_AGENT_ALIAS_ID:
        return {
            "statusCode": 500,
            "body": {
                "message": "BEDROCK_AGENT_ALIAS_ID environment variable is required",
                "debug": debug_info
            }
        }

    try:
        payload = parse_event(event)
        prompt, expected_type = build_prompt(payload)
        session_id = payload.get("sessionId") or str(uuid.uuid4())

        raw_text = invoke_agent(
            prompt=prompt,
            session_id=session_id
        )

        parsed_json = extract_json(raw_text)

        if parsed_json is None:
            return {
                "statusCode": 502,
                "body": {
                    "message": "Agent response does not contain valid JSON",
                    "sessionId": session_id,
                    "debug": debug_info
                }
            }

        validate_result(parsed_json, expected_type)

        return {
            "statusCode": 200,
            "body": {
                "sessionId": session_id,
                "expectedType": expected_type,
                "json": parsed_json
            }
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "message": str(e),
                "debug": debug_info
            }
        }