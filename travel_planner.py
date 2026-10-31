import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")

errors_log = []


def validate_environment():
    missing_keys = []
    if not GEMINI_API_KEY:
        missing_keys.append("GEMINI_API_KEY")
    if not KAKAO_REST_API_KEY:
        missing_keys.append("KAKAO_REST_API_KEY")

    if missing_keys:
        print("[오류] 필수 환경변수(API 키)가 설정되지 않았습니다.")
        print(f"누락된 키: {', '.join(missing_keys)}")
        print("\n[설정 방법 안내]")
        print("1. 프로젝트 루트에 .env 파일을 생성하세요.")
        print("2. 아래와 같이 API 키를 입력해 주세요:")
        print("   GEMINI_API_KEY=\"AIza...\"")
        print("   KAKAO_REST_API_KEY=\"your_kakao_rest_api_key\"")
        print("3. 터미널 환경변수로 직접 주입할 경우:")
        print("   export GEMINI_API_KEY=\"...\" (macOS/Linux)")
        print("   $env:GEMINI_API_KEY=\"...\" (PowerShell)")
        sys.exit(1)


def validate_date_string(date_str: str) -> bool:
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        return False
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def get_travel_date() -> str:
    parser = argparse.ArgumentParser(
        description="LLM과 지도 API를 결합한 국내 여행지 추천 CLI 프로그램"
    )
    parser.add_argument(
        "--date",
        type=str,
        required=False,
        default=None,
        help="여행 출발 일자 (형식: YYYY-MM-DD)"
    )
    args = parser.parse_args()

    # 1. CLI 옵션(--date)으로 입력된 경우 검증
    if args.date:
        if not validate_date_string(args.date):
            print("[입력 오류] CLI로 전달된 날짜 형식이 올바르지 않습니다. 'YYYY-MM-DD' 형식이어야 합니다.")
            sys.exit(1)
        return args.date

    # 2. 인자 없이 실행된 경우 인터랙티브 입력(input) 받기
    while True:
        try:
            user_input = input("여행 출발 일자를 입력하세요 (예: 2026-05-15, 종료: q): ").strip()
            if user_input.lower() in ("q", "quit", "exit"):
                print("프로그램을 종료합니다.")
                sys.exit(0)

            if validate_date_string(user_input):
                return user_input
            else:
                print(" -> 잘못된 형식입니다. 'YYYY-MM-DD' 형식의 유효한 날짜를 입력해 주세요.\n")
        except (KeyboardInterrupt, EOFError):
            print("\n프로그램을 종료합니다.")
            sys.exit(0)


def get_first_recommendation(date_str: str, client: genai.Client) -> dict:
    prompt = f"""
당신은 대한민국 여행 전문 컨설턴트입니다.
여행 예정 날짜인 '{date_str}'에 여행하기 가장 적합한 국내 도시 1곳을 추천하고 정보를 작성해주세요.

반드시 아래 JSON 스키마를 엄격히 준수하여 순수한 JSON 객체 하나만 출력하세요. 마크다운 태그(```json 등)는 제외하세요.

{{
  "recommended_city": "도시명 (예: 제주, 강릉, 전주 등)",
  "weather": "해당 시기 일반적 날씨 요약 (온도, 체감 등)",
  "events": ["행사 또는 축제 후보 1~3개"],
  "reason": "해당 시기에 이 지역을 추천하는 구체적인 근거 (2~4문장)"
}}
"""
    max_retries = 1
    current_prompt = prompt

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=current_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            raw_text = response.text.strip()
            data = json.loads(raw_text)

            required_keys = ["recommended_city", "weather", "events", "reason"]
            if not all(k in data for k in required_keys):
                raise ValueError("필수 JSON 필드가 누락되었습니다.")

            return data
        except Exception as e:
            if attempt < max_retries:
                current_prompt = (
                    prompt
                    + "\n주의: 이전 응답 파싱에 실패했습니다. 반드시 JSON 스키마를 만족하는 유효한 JSON 형식으로만 재작성하세요."
                )
            else:
                errors_log.append({
                    "step": "llm_initial_recommendation",
                    "type": "PARSE_ERROR",
                    "message": f"LLM JSON 생성/파싱 실패: {str(e)}",
                })
                return {
                    "recommended_city": "경주",
                    "weather": "온화한 날씨",
                    "events": ["유적지 야간 개장"],
                    "reason": "안정적인 여행지로 문화유산 탐방에 적합합니다.",
                }


def search_local_restaurants(city_name: str) -> list:
    url = "[https://dapi.kakao.com/v2/local/search/keyword.json](https://dapi.kakao.com/v2/local/search/keyword.json)"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {"query": f"{city_name} 맛집", "size": 5}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)

        if response.status_code in (401, 403):
            print(f" - 오류: 지도 API 인증 실패({response.status_code}). API 키 설정을 확인하세요.")
            errors_log.append({
                "step": "place_search",
                "type": "AUTH_ERROR",
                "message": f"HTTP {response.status_code}: Kakao Local API 인증 실패"
            })
            return []

        response.raise_for_status()
        data = response.json()
        documents = data.get("documents", [])

        if not documents:
            errors_log.append({
                "step": "place_search",
                "type": "EMPTY_RESULT",
                "message": f"0 results for query={city_name} 맛집"
            })
            return []

        restaurants = []
        for doc in documents:
            restaurants.append({
                "name": doc.get("place_name", ""),
                "address": doc.get("road_address_name") or doc.get("address_name", ""),
                "category": doc.get("category_name", ""),
                "url": doc.get("place_url", ""),
                "x": float(doc.get("x", 0.0)) if doc.get("x") else None,
                "y": float(doc.get("y", 0.0)) if doc.get("y") else None,
            })
        return restaurants

    except requests.exceptions.RequestException as e:
        errors_log.append({
            "step": "place_search",
            "type": "NETWORK_ERROR",
            "message": str(e)
        })
        return []


def generate_final_report(
    date_str: str, rec_data: dict, restaurants: list, client: genai.Client
) -> str:
    prompt = f"""
당신은 여행 리포트 작성 전문가입니다. 아래 데이터를 참고하여 사용자를 위한 최종 여행 추천 리포트를 마크다운(Markdown) 문서로 작성하세요.

[여행 기본 정보]
- 여행 일자: {date_str}
- 추천 지역: {rec_data.get('recommended_city')}
- 날씨 요약: {rec_data.get('weather')}
- 행사/축제: {json.dumps(rec_data.get('events', []), ensure_ascii=False)}
- 추천 사유: {rec_data.get('reason')}

[맛집 검색 결과]
{json.dumps(restaurants, ensure_ascii=False, indent=2) if restaurants else "검색 결과 없음"}

[작성 요구사항]
리포트에는 반드시 다음 구조와 제목이 포함되어야 합니다:
# {date_str} 국내 여행 추천 리포트
## 추천 지역
## 추천 이유
## 날씨 요약
## 행사/축제
## 맛집 추천
- 맛집 데이터가 있으면 상호명, 주소, 카테고리, 상세 링크를 정리하세요.
- 맛집 데이터가 비어있거나 검색 결과가 없으면 '데이터 없음 (장소 검색 결과 0건 또는 오류)'으로 명시하세요.
## 1일 일정 제안
- 오전, 오후, 저녁 시간대별 구체적인 동선과 활동 제안
## 오류 요약(errors)
- 발생한 오류가 없다면 '특이사항 없음'으로 기재하세요.
- 오류가 있다면 오류 내용을 bullet point로 요약해 주세요.
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        errors_log.append({
            "step": "report_generation",
            "type": "LLM_ERROR",
            "message": str(e)
        })
        return (
            f"# {date_str} 국내 여행 추천 리포트\n\n"
            f"## 추천 지역: {rec_data.get('recommended_city')}\n"
            f"- 리포트 자동 생성 중 오류가 발생했습니다: {str(e)}"
        )


def main():
    validate_environment()
    travel_date = get_travel_date()

    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"\n[1/3] 1차 추천 생성 중(LLM)...")
    rec_data = get_first_recommendation(travel_date, client)
    city = rec_data.get("recommended_city", "")
    print(f" - recommended_city: \"{city}\"")

    print(f"[2/3] 맛집 검색 중(지도/장소 API)...")
    restaurants = search_local_restaurants(city)
    if restaurants:
        print(f" - 맛집 {len(restaurants)}곳 검색 완료")
    else:
        print(f" - 검색 결과 0건 또는 오류 발생 (다음 단계로 진행)")

    print(f"[3/3] 최종 리포트 생성 중(LLM)...")
    final_report = generate_final_report(travel_date, rec_data, restaurants, client)
    print(f" - 리포트 생성 완료")

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)

    raw_data = {
        "travel_date": travel_date,
        "recommendation": rec_data,
        "restaurants": restaurants,
        "errors": errors_log,
    }

    raw_json_path = results_dir / f"{travel_date}_raw_data.json"
    report_md_path = results_dir / f"{travel_date}_travel_plan.md"

    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    print(f"\n완료! 결과 파일을 확인하세요:")
    print(f"- 원본 데이터 JSON: {raw_json_path}")
    print(f"- 최종 리포트 MD:   {report_md_path}")


if __name__ == "__main__":
    main()