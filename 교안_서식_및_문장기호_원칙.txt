====================================================================================================
[에이닷 위브 (A. WEAVE) AI 교안 제작 및 문장 구조분석 종합 표준 규정집]
버전: 3.0 (대화 이력 전수 분석 및 영구 불변 표준 규정)
====================================================================================================

■ [제1장: 시스템 개요 및 입력 시스템]
1. 명칭: 내신자료 AI 자동생성 '에이닷 위브 (A. WEAVE)'
2. 지문 및 해석 입력:
   - [메인 기능]: 전체 영어 지문과 한글 해석 지문을 한 번에 붙여넣어 일괄 자동 분석.
   - [서브 기능]: 문장별 1:1 입력창은 접기/펼치기(Toggle) 아코디언 UI로 제공.
   - [초기화 보장]: 새로운 지문 입력 시 이전 캐시나 기본 예시 지문이 남지 않고 100% 새로운 데이터로 생성.

----------------------------------------------------------------------------------------------------
■ [제2장: 제1페이지 지문 핵심 정리 (기승전결 3단 정리, 어휘, AI 삽화)]

1. 지문 주제 (Subject):
   - 인쇄 시 줄바꿈(줄넘김)으로 인한 레이아웃 깨짐을 방지하기 위해 공백 포함 반드시 38자 이하로 압축 작성.

2. 핵심 어휘 3개 (Keywords):
   - 반드시 '① 영어단어 (한글 뜻)  ② 영어단어 (한글 뜻)  ③ 영어단어 (한글 뜻)' 형식으로 출력.
   - (예: ① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한))

3. 지문 핵심 3단 정리 (3-Step Summary):
   - [좌측 레이블]: '3단 정리' 텍스트는 [왼쪽 정렬(text-left)].
   - [우측 3단 내용]: 3개 요약문 항목은 모두 [가운데 정렬(text-center, items-center, justify-center)].
   - [하향 화살표(↓) 금지]: 단계 간 하향 화살표를 일절 넣지 않음.
   - [상하 간격]: 각 항목 사이에는 엔터를 한 번 친 것과 같은 상하 간격(space-y-3)을 적용.
   - [넘버링 일체형]: 넘버링 배지 바로 옆에 글이 위치하도록 배치.
   - [서식 예시]:
     3단 정리    1 보존과 보전은 유사하나 초기 계몽주의부터 밀접히 관련됨.

                 2 보전은 복원을, 보존은 원형 유지를 중시하며 구별됨.

                 3 보존주의자는 최소 개입으로 원본 상태 보호를 선호.

4. AI 삽화 생성 시스템 표준 (Gemini 3.7 Flash + Google AI Image API):
   - [System Role]:
     You are an expert AI prompt engineer specialized in Studio Ghibli illustration styles for educational textbooks.
     When given a Lesson Topic and a 3-Step Summary, analyze them to extract the core historical/scientific context, and generate a single descriptive English image prompt.
   - [Strict Constraints for Output]:
     1) Style: Studio Ghibli watercolor and colored pencil illustration, hand-drawn textures, soft pastel tones, cozy atmosphere.
     2) Absolutely NO text, NO speech bubbles, NO words, NO letters, NO labels inside the image.
     3) Express the core concept visually through character emotions, setting, and lighting (dappled light through trees, warm golden hour).
     4) 지브리 고유 캐릭터(토토로, 가오나시 등) 삽입 금지.
   - [프롬프트 엔진]: Google Gemini 3.7 Flash (gemini-3.7-flash) 우선 적용.
   - [이미지 생성 엔진]: Google AI 정품 Gemini 이미지 생성 모델 (gemini-2.5-flash-image / gemini-3.1-flash-image).
   - [단일 마스터 엔진]: 비지브리 묘사로 덮어쓰기 현상 원천 차단.

----------------------------------------------------------------------------------------------------
■ [제3장: 제2페이지 문장 구조분석 및 직독직해 (13대 문법 및 문장기호 절대 규칙)]

[규칙 1. 표준 문장 성분 기호 및 색상 (단어 하단 sub_tag 표기)]
  - 주어 (S): 파란색 (blue), 주절인 경우 밑줄(underline) 적용
  - 자동사 (Vi): 빨간색 (rose), 주절인 경우 밑줄(underline) 적용
  - 타동사 (Vt): 빨간색 (rose), 주절인 경우 밑줄(underline) 적용
  - 목적어 (O, IO, DO): 초록색 (emerald)
  - 주격보어 (SC): 인디고/보라색 (indigo)
  - 목적격보어 (OC): 자주색/보라색 (purple) - 목적어(O)의 초록색과 확연히 구분되는 전용 보라색
  - 가목적어 / 진목적어: 목적어 계열이므로 초록색(emerald)으로 표기 ('가목적어', '진목적어')
  - 의미상의 주어: 동명사/to부정사의 의미상의 주어(예: toddlers falling over의 toddlers, for + 목적격)는 파란색 밑줄 및 단어 하단 '의미상 S' 태그 표기

[규칙 2. 2형식 연결동사(Vi) 및 주격보어(SC) 정석 규정]
  - have been, has been, had been, is, are, was, were, become, remain, seem, appear 등 be동사 및 연결동사는 타동사(Vt)가 아닌 자동사(Vi)로 표기.
  - 뒤따르는 형용사/분사(related, important, different, crucial 등)는 목적어(O)가 아닌 주격보어(SC)로 표기.

[규칙 3. 부사(-ly)의 목적어(O) 오표기 절대 금지]
  - closely, greatly, severely, deeply, widely, frequently, often, always 등 부사는 목적어가 될 수 없으므로 sub_tag: "" (공백), color: "slate" 로 표기.

[규칙 4. 등위접속사 병렬구조 넘버링 (S1, S2 / V1, V2 / O1, O2)]
  - 등위접속사(and, but, or 등)로 주어, 동사, 목적어, 보어가 2개 이상 병렬 연결될 때만 S1, S2 / Vt1, Vt2 / O1, O2 / SC1, SC2 로 넘버링.
  - (예: preservation (S1) + and (△) + conservation (S2))

[규칙 5. 등위접속사/상관접속사/접속부사 세모(△) 오버레이]
  - 세모 기호 적용 대상:
    1) 등위접속사: and, but, or, so, yet, nor
    2) 상관접속사: both, either, neither 등
    3) 접속부사: however, therefore, furthermore, moreover, thus, consequently, instead 등
  - 단어 자체와 정중앙에 겹치도록(SVG Overlay) 깔끔하게 세모를 씌움.
  - [세모 절대 금지]: as, for, because, since, while, although, if, that, when 등 종속접속사/전치사에는 세모 금지.

[규칙 6. 표준 괄호 체계 [ ] 및 ( )]
  - 대괄호 [ ... ]: 명사절, 목적어절, 주어절, 보어절, 명사구 (진주어, 진목적어, to부정사/동명사 명사적 용법)
  - 소괄호 ( ... ): 전치사구(전명구), 부사구, 부사절, 관계사절, 분사구문, 형용사적/부사적 수식어구

[규칙 7. 전치사구(전명구) 및 수식 화살표(⬑) 규칙]
  - 문두/문미의 전치사구 및 부사구(예: (Ever since the early Enlightenment,), (without any serious damage.))는 화살표(⬑) 없이 소괄호 (...)로만 감쌈.
  - 화살표(⬑ - 아래에서 왼쪽 위로 향하는 꺾쇠 화살표)는 오직 바로 앞의 명사를 뒤에서 직접 수식하는 관계사절/형용사구의 소괄호 '(' 바로 밑에만 표기.
  - '전치사구', '주격관계대명사', '부사구' 등의 한글 텍스트 라벨은 일절 제거.

[규칙 8. 준동사구 (명사구/형용사구/부사구) 괄호, 화살표, 상단 문장형식(top_label) 정밀 규정]
  1) **명사구로 쓰이는 준동사구 (주어, 목적어, 보어)**:
     - 괄호: 대괄호 [ ... ] 로 묶고 내부를 의미 단위로 끊어읽기(/) 처리.
     - 하단 기호: 대괄호 시작 [ 밑(sub_tag)에 주절에서의 역할인 'S', 'O', 'C' (또는 '진주어', '진목적어')를 표기.
     - 상단 기호: 준동사 서술어 위에 'top_label: "Vt"'(또는 "Vi"), 목적어/보어 성분 위에 'top_label: "O"' (병렬 연결 시 'O1', 'O2')를 표기.
     - (예: [to maintain (하단: O, 상단: Vt) / an object (상단: O1) / or (△) / system insofar] (상단: O2))
  2) **형용사구로 쓰이는 준동사구 (명사 후치수식)**:
     - 괄호: 소괄호 ( ... ) 로 묶음.
     - 수식 화살표: 바로 앞의 명사를 뒤에서 수식하므로 소괄호 '(' 바로 밑에 왼쪽 위를 가리키는 화살표(⬑)를 표기.
     - 상단 기호: 준동사 서술어 위에 'top_label: "Vt"'(또는 "Vi"), 목적어 성분 위에 'top_label: "O"' 표기.
     - (예: spaces (designated (화살표: ⬑, 상단: Vt) / for working remotely))
  3) **부사구로 쓰이는 준동사구 (목적 ~하기 위해, 원인, 결과, 조건, 분사구문 등)**:
     - 괄호: 소괄호 ( ... ) 로 묶음.
     - 화살표 없음: 명사를 수식하는 것이 아니므로 화살표 없이 소괄호 (...)만 유지.
     - 상단 기호: 준동사 서술어 위에 'top_label: "Vt"'(또는 "Vi"), 목적어 성분 위에 'top_label: "O"' 표기.
     - (예: (to protect (상단: Vt) / their crops (상단: O)))

[규칙 9. 1:1 직독직해 싱크로]
  - 영어 본문 슬래시(/) 구획과 한글 직독직해(chunk_korean) 슬래시(/) 구획은 순서와 개수가 100% 1:1로 일치.
  - (예: Structural defenses / like thick coats / of wax / on leaves / may prevent)
  - (예: 구조적 방어기제는 / 두꺼운 층 같은 / 왁스의 / 잎에 / 막을지도 모른다)
  - 한글 직독직해 텍스트 내에는 (), [] 괄호 사용 일절 금지.

[규칙 10. 중요 어법 포인트 (grammar_points)]
  - 각 문장별 1~3개의 고품질 내신 문법 포인트 작성.
  - 마크다운 별표(**)나 코드 백틱(`) 없이 깔끔한 텍스트로 표기 (예: 1. 현재완료 (Present Perfect): have evolved는...).
  - however, therefore 등은 '삽입어'가 아닌 '접속부사'로 공식 표기.

[규칙 11. 문장 형식 (clause_structure)]
  - 문장별 형식 (1~5형식) 및 주절/종속절 구문 분석 해설 표기.

----------------------------------------------------------------------------------------------------
■ [제4장: 어휘 추출 및 단어장 (Vocabulary)]
1. 고유명사 및 기능어(that, were, the, of 등)를 제외하고 핵심 어휘 16개를 단수/원형(lemma)으로 추출.
2. 품사 원문자 표기: (명), (동), (형), (부).
3. undefined 또는 빈칸 없이 단어와 뜻이 정확하게 1:1 매칭되어 출력.

----------------------------------------------------------------------------------------------------
■ [제5장: 저장소 (Repository) 및 폴더 관리]
1. 4대 카테고리: 교과서, 모의고사, 부교재, 기타 (변형문제, 단어테스트 포함).
2. 폴더 생성, 폴더 선택, 폴더별 검색 및 파일 불러오기 지원.
3. 구글 스프레드시트(RDB_교안) 자동 백업 및 로컬 JSON 데이터베이스 연동.

----------------------------------------------------------------------------------------------------
■ [제6장: 타이포그래피 및 인쇄/PDF 레이아웃]
1. 영어 단어 폰트: Outfit, 11pt, 표준 워드 스타일의 균일하고 미려한 자간(1.05~1.15배).
2. 슬래시(/) 구획: 보라색 볼드 기호로 단어 사이에 자연스럽게 배치.
3. 인쇄 시 불필요한 공백 페이지(빈 페이지) 방지.
====================================================================================================
