# MetroBus KR (경기/서울 버스 도착정보) Home Assistant 통합구성요소 🚍

[![HACS Integration](https://img.shields.io/badge/HACS-Integration-blue.svg)](https://hacs.xyz)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

MetroBus KR은 data.go.kr 공공 API를 사용해 **경기도/서울특별시 버스 정류장 도착정보를 정류장 단위로 폴링**하는 HACS 커스텀 통합입니다.

---

## ✨ 기능

* 지역 선택 기반 등록: **경기도 / 서울특별시**
* 등록 순서:
  1. 지역 선택
  2. 해당 지역 API 서비스키 입력
  3. 정류장 고유번호 입력
  4. 노선 선택
* 정류장 장치(device) 하위에 노선별 장치/센서 자동 생성
* 정류장당 1회 API 조회 후 노선별 센서 상태 갱신
* 기본 90초 폴링 (옵션에서 변경 가능)
* API 상태 센서 제공 (최근 성공/오류 추적)

---

## 📦 설치

### 1. HACS Custom Repository 등록

1. HACS → Integrations
2. 우측 상단 메뉴 (⋮) → **Custom repositories**
3. 아래 정보 입력

* Repository URL: `https://github.com/<your-username>/<repo-name>`
* Category: `Integration`

4. 저장 후 `MetroBus KR Home Assistant Integration` 설치

### 2. Home Assistant 재시작

설치 후 Home Assistant를 재시작하세요.

---

## ⚙️ 사용 방법

1. 설정 → **기기 및 서비스**
2. **통합 추가**
3. `MetroBus KR Arrivals (Gyeonggi/Seoul)` 선택
4. 지역 선택 후 API 키와 정류장 고유번호 입력
5. 노선 목록에서 표시할 버스 선택

---

## 🔧 노선 관리

* 이미 등록된 정류장은 동일 지역 내에서 중복 등록할 수 없습니다.
* 노선 추가/삭제는:

👉 **통합 → 해당 정류장 → 옵션(톱니바퀴)** 에서 변경하세요.

---

## 🌐 사용 API

* [경기도 버스도착정보 조회](https://www.data.go.kr/data/15080346/openapi.do)
* [경기도 정류소 조회](https://www.data.go.kr/data/15080666/openapi.do)
* [서울특별시 버스도착정보조회](https://www.data.go.kr/data/15000314/openapi.do)

---

## ⚠️ 주의사항

* API 응답 지연/오류로 실제 도착정보와 차이가 발생할 수 있습니다.
* 공공 API 특성상 서비스 안정성과 응답 형식이 수시로 바뀔 수 있습니다.

---

## ❗ Disclaimer

This integration is **not affiliated with or endorsed by Gyeonggi-do, Seoul Metropolitan Government, or data.go.kr**.

All data is provided by public APIs, and accuracy or availability is not guaranteed.
Use at your own risk.

---

## 📜 License

This project is licensed under the MIT License.
