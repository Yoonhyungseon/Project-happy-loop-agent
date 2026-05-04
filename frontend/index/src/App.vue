<template>
  <main class="app">
    <section class="header">
      <h1>Happyloop VOC 테스트 화면</h1>
      <p>API Gateway → Controller Lambda → Step Functions/RDS 연동 확인용 Vue 화면</p>
    </section>

    <div class="grid">
      <section>
        <div class="card">
          <h2>공통 설정</h2>

          <div class="form-row">
            <label>API URL</label>
            <input v-model="apiUrl" />
          </div>

          <div class="form-row">
            <label>Survey ID</label>
            <input v-model="surveyId" />
          </div>

          <div class="form-row">
            <label>Reference Survey ID</label>
            <input v-model="referenceSurveyId" />
          </div>

          <div class="form-row">
            <label>Execution ARN</label>
            <input v-model="executionArn" placeholder="createSurvey/createReport 응답의 executionArn" />
          </div>

          <div class="form-row">
            <label>Report ID</label>
            <input v-model="reportId" placeholder="RPT-..." />
          </div>

          <div :class="['status', statusType]">
            현재 화면: {{ activeViewLabel }} / {{ statusMessage }}
          </div>
        </div>

        <div class="card">
          <h2>설문 기능</h2>
          <div class="button-group">
            <button @click="listSurveys">설문 목록</button>
            <button @click="getSurvey">설문 상세</button>
            <button class="primary" @click="createSurvey">일반 설문 생성</button>
            <button class="primary" @click="createSurveyWithReference">기존 응답 참고 설문 생성</button>
            <button @click="submitSurveyResponse">응답 제출</button>
          </div>
        </div>

        <div class="card">
          <h2>보고서 기능</h2>
          <div class="button-group">
            <button class="primary" @click="createReport">보고서 생성</button>
            <button @click="getExecutionStatus">실행 상태 조회</button>
            <button @click="getLatestReport">최신 보고서</button>
            <button @click="listReports">보고서 목록</button>
            <button @click="getReport">보고서 단건</button>
          </div>
        </div>

        <div class="card">
          <h2>요청 프롬프트</h2>
          <div class="form-row">
            <label>일반 설문 생성 요청</label>
            <textarea v-model="createSurveyPrompt"></textarea>
          </div>
          <div class="form-row">
            <label>기존 응답 참고 설문 생성 요청</label>
            <textarea v-model="referenceSurveyPrompt"></textarea>
          </div>
        </div>
      </section>

      <section>
        <div class="card" v-if="activeView === 'surveyList'">
          <h2>설문 목록</h2>

          <div v-if="surveys.length === 0" class="empty">
            조회된 설문이 없습니다.
          </div>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Survey ID</th>
                  <th>제목</th>
                  <th>서비스</th>
                  <th>유형</th>
                  <th>생성일</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in surveys"
                  :key="item.surveyId || item.survey_id"
                  class="clickable"
                  @click="selectSurvey(item)"
                >
                  <td>{{ item.surveyId || item.survey_id }}</td>
                  <td>{{ item.title }}</td>
                  <td>{{ item.service }}</td>
                  <td>{{ item.surveyType || item.survey_type }}</td>
                  <td>{{ item.createdAt || item.created_at }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card" v-if="activeView === 'surveyDetail' && survey">
          <h2>설문 상세</h2>
          <div class="box">
            <h3>{{ survey.title }}</h3>
            <div>Survey ID: <span class="badge">{{ survey.surveyId }}</span></div>
            <div>Service: {{ survey.service }} / Type: {{ survey.surveyType }}</div>
          </div>

          <div
            v-for="question in survey.questions"
            :key="question.code"
            class="question"
          >
            <div class="question-header">
              <div class="question-meta">
                {{ question.code }} · {{ question.type }} · {{ question.category }}
              </div>
              <div>{{ question.text }}</div>
            </div>

            <input
              v-if="question.type === 'SC5'"
              type="number"
              min="1"
              max="5"
              v-model.number="answerMap[question.code]"
            />

            <textarea
              v-else
              v-model="answerMap[question.code]"
            ></textarea>
          </div>
        </div>

        <div class="card" v-if="activeView === 'reportList'">
          <h2>보고서 목록</h2>

          <div v-if="reports.length === 0" class="empty">
            조회된 보고서가 없습니다.
          </div>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Report ID</th>
                  <th>Survey ID</th>
                  <th>생성일</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in reports"
                  :key="item.reportId || item.report_id"
                  class="clickable"
                  @click="selectReport(item)"
                >
                  <td>{{ item.reportId || item.report_id }}</td>
                  <td>{{ item.surveyId || item.survey_id }}</td>
                  <td>{{ item.createdAt || item.created_at }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card" v-if="activeView === 'reportDetail' && report">
          <h2>보고서</h2>
          <div class="box">
            <h3>{{ report.title }}</h3>
            <div class="summary">
              <div>서비스: {{ report.service }}</div>
              <div>응답 수: {{ report.n }}</div>
              <div>전체 평균: {{ report.overall?.avg }}</div>
              <div>긍정률: {{ report.overall?.pos }}</div>
              <div>부정률: {{ report.overall?.neg }}</div>
              <div>만족도 지수: {{ report.overall?.idx }}</div>
              <div>최고 영역: {{ report.overall?.high }}</div>
              <div>최저 영역: {{ report.overall?.low }}</div>
            </div>
          </div>

          <div class="box">
            <div>{{ report.summary }}</div>
            <div>{{ report.point }}</div>
            <div>{{ report.action }}</div>
            <div>{{ report.conclusion }}</div>
          </div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>영역</th>
                  <th>평균</th>
                  <th>지수</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="area in report.areas" :key="area.cat">
                  <td>{{ area.cat }}</td>
                  <td>{{ area.avg }}</td>
                  <td>{{ area.idx }}</td>
                  <td>{{ area.status }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card" v-if="activeView === 'execution'">
          <h2>실행 결과</h2>
          <div class="box">
            <div>Execution ARN</div>
            <div class="badge">{{ executionArn || '없음' }}</div>
          </div>
          <div>
            생성/분석 실행 후 `실행 상태 조회`를 눌러 완료 여부를 확인하세요.
          </div>
        </div>

        <div class="card">
          <h2>Raw Result</h2>
          <pre>{{ prettyResult }}</pre>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, ref } from 'vue';

const apiUrl = ref(import.meta.env.VITE_SURVEY_API_URL || 'https://wbf487tf0e.execute-api.ap-northeast-2.amazonaws.com/survey');
const surveyId = ref('S001');
const referenceSurveyId = ref('S001');
const executionArn = ref('');
const reportId = ref('');

const createSurveyPrompt = ref('스타뱅킹용 VOC 설문지 만들어줘. 모바일 앱 최근 30일 이용 고객 대상이고, 5점 척도 6문항과 주관식 2문항으로 만들어줘.');
const referenceSurveyPrompt = ref('기존 응답 결과를 참고해서 스타뱅킹 후속 VOC 설문지를 만들어줘. 5점 척도 6문항과 주관식 2문항으로 만들어줘.');

const result = ref(null);
const surveys = ref([]);
const reports = ref([]);
const survey = ref(null);
const report = ref(null);
const answerMap = ref({});
const activeView = ref('none');
const statusMessage = ref('대기 중');
const statusType = ref('');

const activeViewLabel = computed(() => {
  const labels = {
    none: '대기',
    surveyList: '설문 목록',
    surveyDetail: '설문 상세',
    reportList: '보고서 목록',
    reportDetail: '보고서 상세',
    execution: '실행 상태'
  };

  return labels[activeView.value] || activeView.value;
});

const prettyResult = computed(() => {
  if (!result.value) {
    return '결과가 여기에 표시됩니다.';
  }

  return JSON.stringify(result.value, null, 2);
});

function setStatus(message, type = '') {
  statusMessage.value = message;
  statusType.value = type;
}

function setResult(data) {
  result.value = data;
}

function changeView(view) {
  activeView.value = view;
}

function clearDetailState() {
  survey.value = null;
  report.value = null;
  answerMap.value = {};
}

async function callSurveyApi(payload) {
  setStatus('API 호출 중...');

  const response = await fetch(apiUrl.value, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  const text = await response.text();

  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch (e) {
    data = {
      rawText: text
    };
  }

  if (!response.ok) {
    setResult({
      status: response.status,
      statusText: response.statusText,
      requestPayload: payload,
      responseBody: data
    });

    throw new Error(data.message || `${response.status} ${response.statusText}`);
  }

  setStatus('성공', 'success');
  setResult(data);
  return data;
}

async function safeCall(callback) {
  try {
    return await callback();
  } catch (error) {
    const errorResult = {
      error: true,
      message: error.message
    };

    setStatus(error.message, 'error');
    setResult(errorResult);
    return null;
  }
}

function normalizeSurvey(apiResult) {
  if (!apiResult?.result?.survey) {
    return null;
  }

  return apiResult.result.survey;
}

function normalizeReport(apiResult) {
  if (apiResult?.result?.report?.report) {
    return apiResult.result.report.report;
  }

  if (apiResult?.result?.report) {
    return apiResult.result.report;
  }

  return null;
}

function prepareAnswers(questions) {
  const nextMap = {};

  questions.forEach((question) => {
    if (question.type === 'SC5') {
      nextMap[question.code] = 4;
    } else if (question.category === '만족 요인') {
      nextMap[question.code] = '계좌 조회가 빠르고 사용하기 편합니다.';
    } else {
      nextMap[question.code] = '메뉴 탐색이 더 직관적이면 좋겠습니다.';
    }
  });

  answerMap.value = nextMap;
}

function selectSurvey(item) {
  const nextSurveyId = item.surveyId || item.survey_id;

  if (nextSurveyId) {
    surveyId.value = nextSurveyId;
    getSurvey();
  }
}

function selectReport(item) {
  const nextReportId = item.reportId || item.report_id;

  if (nextReportId) {
    reportId.value = nextReportId;
    getReport();
  }
}

async function listSurveys() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'listSurveys',
      limit: 20
    });

    clearDetailState();
    surveys.value = data?.result?.surveys || [];
    reports.value = [];
    changeView('surveyList');

    return data;
  });
}

async function getSurvey() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'getSurvey',
      surveyId: surveyId.value
    });

    const nextSurvey = normalizeSurvey(data);
    if (nextSurvey) {
      survey.value = nextSurvey;
      prepareAnswers(nextSurvey.questions || []);
      reports.value = [];
      changeView('surveyDetail');
    }

    return data;
  });
}

async function createSurvey() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'createSurvey',
      userRequest: createSurveyPrompt.value
    });

    if (data.executionArn) {
      executionArn.value = data.executionArn;
    }

    clearDetailState();
    changeView('execution');

    return data;
  });
}

async function createSurveyWithReference() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'createSurveyWithReference',
      referenceSurveyId: referenceSurveyId.value,
      userRequest: referenceSurveyPrompt.value
    });

    if (data.executionArn) {
      executionArn.value = data.executionArn;
    }

    clearDetailState();
    changeView('execution');

    return data;
  });
}

async function submitSurveyResponse() {
  await safeCall(async () => {
    if (!survey.value || !survey.value.questions) {
      throw new Error('먼저 설문 상세를 조회하세요.');
    }

    const answers = survey.value.questions.map((question) => {
      if (question.type === 'SC5') {
        return {
          questionCode: question.code,
          scoreValue: Number(answerMap.value[question.code])
        };
      }

      return {
        questionCode: question.code,
        textValue: String(answerMap.value[question.code] || '')
      };
    });

    return await callSurveyApi({
      action: 'submitSurveyResponse',
      surveyId: survey.value.surveyId,
      answers
    });
  });
}

async function createReport() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'createReport',
      surveyId: surveyId.value
    });

    if (data.executionArn) {
      executionArn.value = data.executionArn;
    }

    clearDetailState();
    changeView('execution');

    return data;
  });
}

async function getExecutionStatus() {
  await safeCall(async () => {
    if (!executionArn.value) {
      throw new Error('executionArn이 필요합니다.');
    }

    const data = await callSurveyApi({
      action: 'getExecutionStatus',
      executionArn: executionArn.value
    });

    const output = data.output;
    const savedSurveyId = output?.saveSurveyResult?.body?.surveyId;
    const savedReport = output?.saveReportResult?.body?.report;
    const savedReportId = output?.saveReportResult?.body?.reportId;

    if (savedSurveyId) {
      surveyId.value = savedSurveyId;
      changeView('execution');
    }

    if (savedReportId) {
      reportId.value = savedReportId;
    }

    if (savedReport) {
      report.value = savedReport;
      changeView('reportDetail');
    }

    return data;
  });
}

async function getLatestReport() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'getLatestReport',
      surveyId: surveyId.value
    });

    const nextReport = normalizeReport(data);
    if (nextReport) {
      report.value = nextReport;
      survey.value = null;
      changeView('reportDetail');
    }

    if (data?.result?.reportId) {
      reportId.value = data.result.reportId;
    }

    return data;
  });
}

async function listReports() {
  await safeCall(async () => {
    const data = await callSurveyApi({
      action: 'listReports',
      surveyId: surveyId.value
    });

    reports.value = data?.result?.reports || [];
    survey.value = null;
    report.value = null;
    changeView('reportList');

    return data;
  });
}

async function getReport() {
  await safeCall(async () => {
    if (!reportId.value) {
      throw new Error('reportId가 필요합니다.');
    }

    const data = await callSurveyApi({
      action: 'getReport',
      reportId: reportId.value
    });

    const nextReport = normalizeReport(data);
    if (nextReport) {
      report.value = nextReport;
      survey.value = null;
      changeView('reportDetail');
    }

    return data;
  });
}
</script>
