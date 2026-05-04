# Project-happy-loop-agent

API 명세서 - Happyloop VOC Survey API

Base URL
https://wbf487tf0e.execute-api.ap-northeast-2.amazonaws.com

Endpoint
POST /survey

Content-Type
application/json

공통 요청 형식
{
  "action": "string"
}

공통 응답 형식
{
  "action": "string",
  "result": object
}
1. 설문 목록 조회

Action
listSurveys

Request
{
  "action": "listSurveys",
  "limit": 20
}

Response
{
  "action": "listSurveys",
  "result": {
    "surveys": [],
    "count": 0
  }
}
2. 설문 상세 조회

Action
getSurvey

Request
{
  "action": "getSurvey",
  "surveyId": "SURV-83D63FDCA5C6"
}

Response
{
  "action": "getSurvey",
  "result": {
    "surveyId": "SURV-83D63FDCA5C6",
    "survey": {
      "surveyId": "SURV-83D63FDCA5C6",
      "title": "스타뱅킹 모바일 앱 이용 고객 경험 후속 설문",
      "service": "스타뱅킹",
      "surveyType": "VOC",
      "questions": []
    }
  }
}
3. 일반 설문 생성

Action
createSurvey

Request
{
  "action": "createSurvey",
  "userRequest": "스타뱅킹용 VOC 설문지 만들어줘. 모바일 앱 최근 30일 이용 고객 대상이고, 5점 척도 6문항과 주관식 2문항으로 만들어줘."
}

Response
{
  "action": "createSurvey",
  "status": "STARTED",
  "executionArn": "arn:aws:states:...",
  "executionName": "create-survey-..."
}
4. 기존 응답 참고 후속 설문 생성

Action
createSurveyWithReference

Request
{
  "action": "createSurveyWithReference",
  "referenceSurveyId": "S001",
  "userRequest": "기존 응답 결과를 참고해서 스타뱅킹 후속 VOC 설문지를 만들어줘. 5점 척도 6문항과 주관식 2문항으로 만들어줘."
}

Response
{
  "action": "createSurveyWithReference",
  "status": "STARTED",
  "executionArn": "arn:aws:states:...",
  "executionName": "create-survey-ref-..."
}
5. 설문 응답 제출

Action
submitSurveyResponse

Request
{
  "action": "submitSurveyResponse",
  "surveyId": "SURV-83D63FDCA5C6",
  "answers": [
    {
      "questionCode": "Q01",
      "scoreValue": 4
    },
    {
      "questionCode": "Q07",
      "textValue": "계좌 조회가 빠르고 사용하기 편합니다."
    }
  ]
}

Response
{
  "action": "submitSurveyResponse",
  "result": {
    "surveyId": "SURV-83D63FDCA5C6",
    "responseId": "RESP-...",
    "saved": true
  }
}
6. 보고서 생성

Action
createReport

Request
{
  "action": "createReport",
  "surveyId": "S001"
}

Response
{
  "action": "createReport",
  "status": "STARTED",
  "executionArn": "arn:aws:states:...",
  "executionName": "create-report-..."
}
7. 실행 상태 조회

Action
getExecutionStatus

Request
{
  "action": "getExecutionStatus",
  "executionArn": "arn:aws:states:ap-northeast-2:956723945403:execution:kbds-happyloop-create-report-sfn:create-report-xxxx"
}

Response
{
  "action": "getExecutionStatus",
  "executionArn": "arn:aws:states:...",
  "status": "SUCCEEDED",
  "startDate": "2026-04-29T14:22:24.264000+00:00",
  "stopDate": "2026-04-29T14:22:33.901000+00:00",
  "output": {}
}
8. 최신 보고서 조회

Action
getLatestReport

Request
{
  "action": "getLatestReport",
  "surveyId": "S001"
}

Response
{
  "action": "getLatestReport",
  "result": {
    "surveyId": "S001",
    "found": true,
    "reportId": "RPT-C624B7573791",
    "createdAt": "2026-04-29 14:22:33.831914",
    "report": {}
  }
}
9. 보고서 목록 조회

Action
listReports

Request
{
  "action": "listReports",
  "surveyId": "S001"
}

Response
{
  "action": "listReports",
  "result": {
    "surveyId": "S001",
    "reports": [],
    "count": 0
  }
}
10. 보고서 단건 조회

Action
getReport

Request
{
  "action": "getReport",
  "reportId": "RPT-C624B7573791"
}

Response
{
  "action": "getReport",
  "result": {
    "found": true,
    "reportId": "RPT-C624B7573791",
    "surveyId": "S001",
    "report": {}
  }
}


=====================================================================================================
지금까지 한것
1. Bedrock Agent 생성
2. Knowledge Base 생성
3. S3 Vectors 기반 RAG 연결
4. 설문 생성 테스트 성공
5. 보고서 생성 테스트 성공
6. SURVEY JSON / REPORT JSON 최소 구조 확정
7. Comprehend 호출 Lambda 생성 테스트 성공
8. Bedrock Agent 호출 Lambda
9. Step Functions 워크플로우
10. Controller Lambda
11. API Gateway 또는 AppSync
12. RDS/Aurora
13. DB Handler Lambda
=====================================================================================================
[보고서 생성]

사용자 클릭
→ Controller Lambda
→ Step Functions
→ DB Handler Lambda로 RDS 조회
→ Analyze Text Lambda로 Comprehend 분석
→ DB Handler Lambda로 분석 결과 저장
→ DB Handler Lambda로 REPORT_INPUT 생성
→ Invoke Agent Lambda로 보고서 생성
→ DB Handler Lambda로 보고서 저장
→ Vue에 reportId 또는 report JSON 반환
