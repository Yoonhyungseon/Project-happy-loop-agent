# Happyloop VOC Vue 테스트 화면

Vue 3 + Vite 기반 테스트 화면입니다.

## 실행

```bash
npm install
npm run dev
```

PowerShell 실행 정책 문제 발생 시:

```powershell
npm.cmd install
npm.cmd run dev
```

## 주요 수정 사항

- `vite.config.js` 포함
- 설문 목록/상세/보고서 목록/보고서 상세 화면 전환 상태 추가
- 버튼 클릭 시 이전 상세 화면이 남아 보이던 문제 수정
- API 500/503 응답 본문을 Raw Result에 표시하도록 개선


dist 생성
npm.cmd run build