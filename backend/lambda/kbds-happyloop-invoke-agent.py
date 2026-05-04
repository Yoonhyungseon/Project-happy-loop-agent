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


def build_prompt(payload: Dict[str, Any]) -> Tuple[str, str]:
    action = payload.get("action", "raw")

    if action == "createSurvey":
        user_request = payload.get("userRequest") or payload.get("prompt")

        if not user_request:
            raise ValueError("createSurvey action requires userRequest or prompt")

        return user_request.strip(), "SURVEY"

    if action == "generateReport":
        report_input = payload.get("reportInput")

        if not report_input:
            raise ValueError("generateReport action requires reportInput")

        report_input_text = json.dumps(report_input, ensure_ascii=False)

        prompt = f"""
아래 REPORT_INPUT을 바탕으로 VOC 응답 분석 보고서를 생성해줘.

REPORT_INPUT:
{report_input_text}
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
    questions = parsed_json.get("questions")

    if not isinstance(questions, list):
        raise ValueError("SURVEY response requires questions array")

    if len(questions) == 0:
        raise ValueError("SURVEY questions array is empty")

    for question in questions:
        allowed_fields = {"code", "type", "category", "text"}
        required_fields = {"code", "type", "category", "text"}

        missing_fields = required_fields - set(question.keys())

        if missing_fields:
            raise ValueError(f"SURVEY question missing fields: {sorted(missing_fields)}")

        extra_fields = set(question.keys()) - allowed_fields

        if extra_fields:
            raise ValueError(f"SURVEY question has unsupported fields: {sorted(extra_fields)}")

        question_type = question.get("type")

        if question_type not in ["SC5", "TXT"]:
            raise ValueError(f"Invalid question type: {question_type}")


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