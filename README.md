# StickyNotes_DaeriDoong

DaeriDoong이 배포하는 Windows용 스티커 노트 앱입니다. Python tkinter 기반으로 제작되었습니다.

## 최신 배포 파일

- 실행 파일: dist/StickyNotes_DaeriDoong.exe
- 바로가기 생성 스크립트: create_shortcut.bat

## 주요 기능

- 다중 노트 창 관리 및 자동 저장
- 제목/본문/크기/위치/색상/접힘 상태 복원
- 단일 인스턴스 실행(이미 실행 중이면 기존 창 활성화)
- 시스템 트레이 메뉴(열기/새 노트/종료/크래시 로그 열기)
- 앱 내부 자동실행(on/off) 설정
- 자동실행 시 전체 숨김 상태였을 때 시작 동작 옵션 제공
- 전역 설정 창(자동실행/시작 동작/항상 위/백업)
- 노트별 설정 창(색상/글꼴 크기/투명도)
- 노트 목록에서 제목+본문 빠른 검색/필터
- 한글 IME 입력 안정화(입력 중 불필요한 모드 흔들림 완화)
- 표 삽입/셀 추가/삭제/병합/분할 지원
- 이미지 삽입(앱 미디어 폴더로 복사 후 참조)
- 간단한 그림판 스케치 후 이미지 삽입
- 삽입된 표/이미지를 텍스트가 아닌 실제 임베드 형태로 렌더링
- 우하단 리사이즈 그립 제공
- 상단 메뉴바(저장/새 노트/백업/가져오기/닫기/종료)
- 삽입된 표는 노트 내부에서 재편집 가능하며 수정 내용 저장
- 병합된 셀 레이아웃도 삽입/편집 후 유지

## 실행 방법

1. Python 3이 없다면 먼저 설치합니다.
2. create_shortcut.bat 실행 또는 dist/StickyNotes_DaeriDoong.exe 직접 실행합니다.

## 점검 및 테스트

- 정적 진단: 현재 진단 오류 없음
- 기본 테스트 명령:
	py -3 -m unittest discover -s tests -p "test_*.py" -v

## 코드 구조

- 핵심 앱: sticky_notes.py
- 저장 처리: persistence.py
- 자동실행: autostart.py
- 트레이 아이콘: tray.py
- 단일 인스턴스 제어: instance_control.py
- 창 관련 모듈: windows/global_settings.py, windows/note_settings.py

## 데이터 저장 위치

- 노트 데이터: %APPDATA%/Sticky Notes/notes_data.json
- 크래시 로그: %APPDATA%/Sticky Notes/last_crash.log

## 개선 목록

- 진행/백로그는 IMPROVEMENT_CHECKLIST.md 참고
