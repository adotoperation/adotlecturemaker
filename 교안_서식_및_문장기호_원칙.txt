========================================================================================
[에이닷 위브 (A. WEAVE) AI 삽화 및 교안 서식 표준 규정]
버전: 1.5 (영구 보존 표준 규정)
========================================================================================

■ [AI 삽화 생성 시스템 표준 (Gemini 3.7 Flash 적용)]
1. AI 프롬프트 엔진 역할 [System Role]:
   - You are an expert AI prompt engineer specialized in Studio Ghibli illustration styles for educational textbooks.
   - When given a Lesson Topic and a 3-Step Summary, analyze them to extract the core historical/scientific context, and generate a single descriptive English image prompt.
2. 엄격한 출력 제약조건 [Strict Constraints for Output]:
   가. Style: Studio Ghibli watercolor and colored pencil illustration, hand-drawn textures, soft pastel tones, cozy atmosphere.
   나. Absolutely NO text, NO speech bubbles, NO words, NO letters, NO labels inside the image.
   다. Express the core concept visually through character emotions, setting, and lighting (dappled light through trees, warm golden hour).
3. 프롬프트 생성 모델:
   - Google Gemini 3.7 Flash (gemini-3.7-flash) 우선 적용 (안정적 백업: gemini-2.5-flash).

----------------------------------------------------------------------------------------
■ [지문 핵심 정리 3단 내용 정리 및 핵심어휘 서식]
1. 3단 정리 레이아웃:
   - [좌측 타이틀 레이블]: '3단 정리' 레이블은 [왼쪽 정렬(text-left)].
   - [우측 3단 내용]: 3개 내용 항목은 모두 [가운데 정렬(text-center, items-center, justify-center)].
   - [화살표 없음]: 단계 간 하향 화살표(↓)를 일절 넣지 않음.
   - [엔터 간격]: 각 항목 사이에는 엔터를 한 번 친 것과 같은 상하 간격(space-y-3)을 적용.
   - [서식 예시]:
     3단 정리    1 보존과 보전은 유사하나 초기 계몽주의부터 밀접히 관련됨.

                 2 보전은 복원을, 보존은 원형 유지를 중시하며 구별됨.

                 3 보존주의자는 최소 개입으로 원본 상태 보호를 선호.

2. 핵심 어휘 표기:
   - 반드시 '① 영어단어 (한글 뜻)  ② 영어단어 (한글 뜻)  ③ 영어단어 (한글 뜻)' 형식으로 출력.

----------------------------------------------------------------------------------------
■ [문장기호 및 구문분석 표준 원칙]
1. 의미상의 주어 (동명사/to부정사):
   - 'toddlers falling over'의 toddlers, 'for + 목적격' 등은 단어 아래에 파란색 '의미상 S' 태그를 표기하고 밑줄 적용.
2. 등위접속사 세모(△): and, but, or, so, yet, however 등 단어 자체와 정중앙에 겹치도록(Overlay) 표시.
3. 전명구(전치사구): 화살표(⬑) 없이 소괄호 (...) 로 감싸기.
4. 1:1 직독직해 싱크로: 영어 본문 슬래시(/)와 한글 번역 슬래시(/) 구획 100% 1:1 일치.
========================================================================================
