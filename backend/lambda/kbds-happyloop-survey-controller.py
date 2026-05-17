import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import boto3


CREATE_SURVEY_SFN_ARN = os.environ.get("CREATE_SURVEY_SFN_ARN", "")
CREATE_REPORT_SFN_ARN = os.environ.get("CREATE_REPORT_SFN_ARN", "")
DB_HANDLER_FUNCTION_NAME = os.environ.get("DB_HANDLER_FUNCTION_NAME", "kbds-happyloop-survey-db-handler")

sfn = boto3.client("stepfunctions")
lambda_client = boto3.client("lambda")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST"
        },
        "body": json.dumps(body, ensure_ascii=False)
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


def start_execution(state_machine_arn: str, input_payload: Dict[str, Any], name_prefix: str) -> Dict[str, Any]:
    if not state_machine_arn:
        raise ValueError("state machine ARN environment variable is required")

    execution_name = f"{name_prefix}-{uuid.uuid4().hex[:12]}"

    result = sfn.start_execution(
        stateMachineArn=state_machine_arn,
        name=execution_name,
        input=json.dumps(input_payload, ensure_ascii=False)
    )

    return {
        "executionArn": result.get("executionArn"),
        "startDate": result.get("startDate").isoformat() if result.get("startDate") else None,
        "executionName": execution_name
    }


def invoke_db_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not DB_HANDLER_FUNCTION_NAME:
        raise ValueError("DB_HANDLER_FUNCTION_NAME environment variable is required")

    result = lambda_client.invoke(
        FunctionName=DB_HANDLER_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )

    raw_payload = result.get("Payload").read().decode("utf-8")
    parsed_payload = json.loads(raw_payload) if raw_payload else {}

    body = parsed_payload.get("body")

    if isinstance(body, str):
        try:
            parsed_payload["body"] = json.loads(body)
        except json.JSONDecodeError:
            pass

    return parsed_payload



SURVEY_SFN_INPUT_KEYS = {
    "userRequest",
    "referenceSurveyId",
    "service",
    "serviceName",
    "surveyType",
    "targetCustomer",
    "goal",
    "purpose",
    "categories",
    "customerExperienceStages",
    "serviceQualityDimensions",
    "questionCount",
    "includeVoc",
    "adminUserId"
}


def build_create_survey_input(payload: Dict[str, Any], require_reference: bool = False) -> Dict[str, Any]:
    user_request = payload.get("userRequest")

    if not user_request:
        raise ValueError("userRequest is required")

    reference_survey_id = payload.get("referenceSurveyId")

    if require_reference and not reference_survey_id:
        raise ValueError("referenceSurveyId is required")

    sfn_input = {}

    for key in SURVEY_SFN_INPUT_KEYS:
        if key in payload and payload.get(key) is not None:
            sfn_input[key] = payload.get(key)

    sfn_input["userRequest"] = user_request
    sfn_input["generationMode"] = "REFERENCE" if reference_survey_id else "DIRECT"

    return sfn_input



def create_survey(payload: Dict[str, Any]) -> Dict[str, Any]:
    sfn_input = build_create_survey_input(payload, require_reference=False)

    name_prefix = "create-survey-ref" if sfn_input.get("referenceSurveyId") else "create-survey"

    result = start_execution(
        state_machine_arn=CREATE_SURVEY_SFN_ARN,
        input_payload=sfn_input,
        name_prefix=name_prefix
    )

    return response(200, {
        "action": "createSurvey",
        "status": "STARTED",
        "input": sfn_input,
        "recommendation": None if sfn_input.get("referenceSurveyId") else "referenceSurveyId를 함께 보내면 기존 설문/응답/VOC/서비스 배경지식을 참고해 더 정교하게 생성됩니다.",
        **result
    })


def create_survey_with_reference(payload: Dict[str, Any]) -> Dict[str, Any]:
    sfn_input = build_create_survey_input(payload, require_reference=True)
    sfn_input["generationMode"] = "REFERENCE"

    result = start_execution(
        state_machine_arn=CREATE_SURVEY_SFN_ARN,
        input_payload=sfn_input,
        name_prefix="create-survey-ref"
    )

    return response(200, {
        "action": "createSurveyWithReference",
        "status": "STARTED",
        "input": sfn_input,
        **result
    })


def create_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    sfn_input = {
        "surveyId": survey_id
    }

    result = start_execution(
        state_machine_arn=CREATE_REPORT_SFN_ARN,
        input_payload=sfn_input,
        name_prefix="create-report"
    )

    return response(200, {
        "action": "createReport",
        "status": "STARTED",
        "input": sfn_input,
        **result
    })


def get_execution_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    execution_arn = payload.get("executionArn")

    if not execution_arn:
        raise ValueError("executionArn is required")

    result = sfn.describe_execution(
        executionArn=execution_arn
    )

    output = result.get("output")
    parsed_output = None

    if output:
        parsed_output = json.loads(output)

    return response(200, {
        "action": "getExecutionStatus",
        "executionArn": execution_arn,
        "status": result.get("status"),
        "startDate": result.get("startDate").isoformat() if result.get("startDate") else None,
        "stopDate": result.get("stopDate").isoformat() if result.get("stopDate") else None,
        "output": parsed_output
    })


def get_survey(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    result = invoke_db_handler({
        "action": "getSurvey",
        "surveyId": survey_id
    })

    return response(result.get("statusCode", 200), {
        "action": "getSurvey",
        "result": result.get("body")
    })


def get_latest_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    result = invoke_db_handler({
        "action": "getLatestReport",
        "surveyId": survey_id
    })

    return response(result.get("statusCode", 200), {
        "action": "getLatestReport",
        "result": result.get("body")
    })

def list_surveys(payload: Dict[str, Any]) -> Dict[str, Any]:
    result = invoke_db_handler({
        "action": "listSurveys",
        "limit": payload.get("limit", 20)
    })

    return response(result.get("statusCode", 200), {
        "action": "listSurveys",
        "result": result.get("body")
    })


def list_reports(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")

    if not survey_id:
        raise ValueError("surveyId is required")

    result = invoke_db_handler({
        "action": "listReports",
        "surveyId": survey_id
    })

    return response(result.get("statusCode", 200), {
        "action": "listReports",
        "result": result.get("body")
    })


def get_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_id = payload.get("reportId")

    if not report_id:
        raise ValueError("reportId is required")

    result = invoke_db_handler({
        "action": "getReport",
        "reportId": report_id
    })

    return response(result.get("statusCode", 200), {
        "action": "getReport",
        "result": result.get("body")
    })

def submit_survey_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    survey_id = payload.get("surveyId")
    answers = payload.get("answers")
    response_id = payload.get("responseId")

    if not survey_id:
        raise ValueError("surveyId is required")

    if not isinstance(answers, list) or len(answers) == 0:
        raise ValueError("answers must be a non-empty array")

    db_payload = {
        "action": "submitSurveyResponse",
        "surveyId": survey_id,
        "answers": answers
    }

    if response_id:
        db_payload["responseId"] = response_id

    result = invoke_db_handler(db_payload)

    return response(result.get("statusCode", 200), {
        "action": "submitSurveyResponse",
        "result": result.get("body")
    })

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        if event.get("requestContext") and event.get("httpMethod") == "OPTIONS":
            return response(200, {
                "message": "OK"
            })

        payload = parse_event(event)
        action = payload.get("action")

        if action == "createSurvey":
            return create_survey(payload)

        if action == "createSurveyWithReference":
            return create_survey_with_reference(payload)

        if action == "createSurveyFromReference":
            return create_survey_with_reference(payload)

        if action == "createReport":
            return create_report(payload)

        if action == "getExecutionStatus":
            return get_execution_status(payload)

        if action == "getSurvey":
            return get_survey(payload)

        if action == "getLatestReport":
            return get_latest_report(payload)
            
        if action == "listSurveys":
            return list_surveys(payload)

        if action == "listReports":
            return list_reports(payload)

        if action == "getReport":
            return get_report(payload)

        if action == "submitSurveyResponse":
            return submit_survey_response(payload)
            
        return response(400, {
            "message": f"Unsupported action: {action}"
        })

    except Exception as e:
        return response(500, {
            "message": str(e),
            "timestamp": now_iso()
        })