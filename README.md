# NamuRulesCollector

나무위키 게임 문서에서 **룰 / 게임 규칙 / 규칙** 등 사용자가 지정한 제목의 섹션만 추출하여 Obsidian용 Markdown 파일로 저장하는 Windows GUI 프로그램입니다.

## V1 기능

- 여러 나무위키 URL 입력 (한 줄에 하나)
- 규칙 섹션 제목 키워드 직접 설정
- 게임별 `.md` 저장 또는 하나의 `.md`로 통합 저장
- Windows 폴더 선택 창
- Obsidian Vault 내부 폴더를 저장 위치로 직접 선택 가능
- YAML Properties 자동 생성
- 원문 URL 및 수집 날짜 기록
- 콘솔 창 없이 GUI만 실행
- GitHub Actions에서 Windows 단독 EXE 자동 빌드

## GitHub에서 EXE 만들기

1. GitHub에서 새 Repository를 만듭니다.
2. 이 프로젝트의 **내용물 전체**를 Repository 최상위에 업로드합니다.
3. `Actions` 탭을 엽니다.
4. `Build Windows EXE` 워크플로를 실행합니다.
   - `main` 브랜치에 업로드하면 자동 실행됩니다.
   - 또는 `Run workflow` 버튼으로 수동 실행할 수 있습니다.
5. 빌드가 완료되면 실행 결과 화면 아래 `Artifacts`의 `NamuRulesCollector-windows`를 다운로드합니다.
6. 압축을 풀고 `NamuRulesCollector.exe`를 실행합니다.

사용자 PC에는 Python 설치가 필요하지 않습니다.

## 참고

V1은 별도 브라우저 엔진을 포함하지 않는 최소 버전입니다. 나무위키의 HTML 구조나 자동 접근 정책이 바뀌면 일부 문서에서 수집이 실패할 수 있습니다.

수집한 문서의 이용 및 재배포 시에는 원문 사이트의 이용 조건과 저작권을 확인하세요.
