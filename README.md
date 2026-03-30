# GGBus (경기도 버스 도착정보) Home Assistant 통합구성요소 🚍

[![HACS Integration](https://img.shields.io/badge/HACS-Integration-blue.svg)](https://hacs.xyz)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

경기도 버스도착정보 API와 정류소 조회 API(모두 data.go.kr 공공 API)를 사용해
**정류장 단위로 버스 도착정보를 90초 간격으로 갱신**하는 HACS 커스텀 통합입니다.

---

## ✨ 기능

* HACS로 설치 가능한 커스텀 통합
* 초기 등록 시:

  * 공공데이터포털 API 서비스키 입력
  * 정류장 번호(5자리) 입력
  * 해당 정류장의 버스 노선 목록 조회 후 선택
* 등록 후:

  * 정류장 장치(device) 아래에 버스 노선별 하위 기기(device) 생성
  * 각 버스 기기마다 엔티티 생성:

    * 도착 예정 시간
    * 남은 정류장 수
    * 저상버스 여부
  * 버스 하위 기기에서 "기기 제거"를 통해 개별 노선 삭제 가능
* API 호출 제한(일 1,000회)을 고려해 **정류장당 기본 1회 / 90초 폴링**

  * 설정에서 초 단위로 갱신 주기 변경 가능
* 정류장 기기에 `API 상태` 센서 제공

  * 최근 성공 / 오류 시각 확인 가능
* 저상버스 및 도착정보는 data.go.kr 원본 응답 기준으로 표시됨
  *(다른 앱과 표시 기준이 다를 수 있음)*

---

## 📦 설치

### 1. HACS Custom Repository 등록

1. HACS → Integrations
2. 우측 상단 메뉴 (⋮) → **Custom repositories**
3. 아래 정보 입력

* Repository URL: `https://github.com/<your-username>/<repo-name>`
* Category: `Integration`

4. 저장 후 `GGBus Home Assistant Integration` 설치

---

### 2. Home Assistant 재시작

설치 후 Home Assistant를 재시작하세요.

---

## ⚙️ 사용 방법

1. 설정 → **기기 및 서비스**
2. **통합 추가**
3. `Gyeonggi Bus Stop Arrivals` 선택
4. 다음 정보 입력:

* 공공데이터포털 API 서비스키
* 정류장 번호 (5자리)

5. 노선 목록에서 표시할 버스 선택

---

## 🔧 노선 관리

* 이미 등록된 정류장은 **서비스 추가로 다시 등록할 수 없습니다**
* 버스 노선 추가/삭제는:

👉 **통합 → 해당 정류장 → 옵션(톱니바퀴)** 에서 변경하세요

---

## ⏱️ 업데이트 주기

* 기본: **90초**
* 설정에서 자유롭게 변경 가능

---

## 🌐 사용 API

* [경기도 버스도착정보 조회](https://www.data.go.kr/data/15080346/openapi.do)
* [경기도 정류소 조회](https://www.data.go.kr/data/15080666/openapi.do)

---

## ⚠️ 주의사항

* API 응답 지연 또는 오류로 인해 실제 도착 정보와 차이가 발생할 수 있습니다
* 다른 앱(카카오버스, 네이버지도 등)과 표시 기준이 다를 수 있습니다
* 공공 API 특성상 서비스 안정성이 보장되지 않습니다

---

## ❗ Disclaimer

This integration is **not affiliated with or endorsed by Gyeonggi-do or data.go.kr**.

All data is provided by public APIs, and accuracy or availability is not guaranteed.
Use at your own risk.

---

## 📜 License

This project is licensed under the MIT License.
