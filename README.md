# Travel_planner

# 국내 여행지 추천 및 일정 생성 CLI 프로그램

Python CLI 환경에서 LLM(Google Gemini)과 장소 검색 API(Kakao Local)를 파이프라인으로 연동하여 여행 시기에 맞는 지역 추천 및 맛집 정보, 1일 추천 일정을 자동 생성하는 프로그램입니다.

## 1. 주요 기능
- **CLI 인터페이스**: `argparse` 기반 날짜(`YYYY-MM-DD`) 입력 및 유효성 검증
- **구조화된 LLM 응답 수집**: 1차 여행지 추천 결과를 JSON 포맷으로 강제 수집 및 자동 파싱(재시도 1회 지원)
- **지도 API 연동**: 추천 지역을 기반으로 카카오 로컬 REST API 맛집 5건 검색
- **오류 격리 및 대응**: 장소 검색 실패(401/403/네트워크 등) 시에도 프로세스를 중단하지 않고 Fallback 리포트 생성
- **결과 저장**: `results/` 디렉터리에 원본 JSON 및 최종 Markdown 리포트 자동 저장

## 2. 사전 준비 및 API 키 발급
1. **Google Gemini API Key**: [Google AI Studio](https://aistudio.google.com/)에서 API 키 발급
2. **Kakao REST API Key**: [Kakao Developers](https://developers.kakao.com/) 로그인 -> 내 애플리케이션 등록 -> **REST API 키** 복사

## 3. 환경 설정
저장소를 클론한 후 패키지를 설치합니다:

\`\`\`bash
pip install -r requirements.txt
\`\`\`

루트 디렉터리에 `.env` 파일을 생성하고 발급받은 키를 등록합니다:

\`\`\`env
GEMINI_API_KEY="AIzaSy..."
KAKAO_REST_API_KEY="your_kakao_rest_api_key"
\`\`\`

> **보안 주의사항**: `.env` 파일 및 API 키는 절대 GitHub 공개 저장소나 제출물 압축본에 직접 포함하지 마세요. `.gitignore`에 등록되어 있는지 반드시 확인해야 합니다.

## 4. 실행 방법
\`\`\`bash
python travel_planner.py --date "2026-05-15"
\`\`\`

### 실행 결과 예시
\`\`\`text
[1/3] 1차 추천 생성 중(LLM)...
 - recommended_city: "강릉"
[2/3] 맛집 검색 중(지도/장소 API)...
 - 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
 - 리포트 생성 완료

완료! 결과 파일을 확인하세요:
- 원본 데이터 JSON: results/2026-05-15_raw_data.json
- 최종 리포트 MD:   results/2026-05-15_travel_plan.md
\`\`\`

## 5. 핵심 개념 정리
- **REST API & HTTP Method**: 
  - `GET`: 데이터 조회를 목적으로 하며 URL 쿼리 파라미터로 조건을 전달합니다(장소 검색에 사용).
  - `POST`: 본문(Body)에 구조화된 요청 페이로드를 전달하여 상태를 생성하거나 추론을 요청할 때 사용합니다(LLM 요청에 사용).
- **LLM 출력 구조화**:
  - `response_mime_type="application/json"`을 지정하여 다음 단계(Kakao API 검색어)의 인자로 안정적으로 매핑합니다.
