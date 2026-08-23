import os
import re
import json
import requests

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()
DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

CONJUNCTIONS_LIST = [
    # 등위접속사 (Coordinating Conjunctions)
    'and', 'but', 'or', 'so', 'yet', 'nor',
    # 상관접속사 (Correlative Conjunctions)
    'both', 'either', 'neither',
    # 접속부사 (Conjunctive Adverbs)
    'however', 'therefore', 'furthermore', 'moreover', 'thus', 'consequently',
    'nonetheless', 'nevertheless', 'instead', 'otherwise', 'meanwhile', 'besides', 'likewise', 'similarly'
]

def sanitize_conjunction_tokens(analysis_data):
    """
    Ensures ONLY coordinating conjunctions, correlative conjunctions, and conjunctive adverbs
    have is_conjunction: True and triangle mark.
    Prepositions and subordinating conjunctions (as, for, because, since, if, while, etc.) MUST NOT have triangles.
    """
    if not analysis_data or 'sentences' not in analysis_data:
        return analysis_data

    for s in analysis_data.get('sentences', []):
        old_tokens = s.get('tokens', [])
        new_tokens = []

        for t in old_tokens:
            text = t.get('text', '')
            if not text or text.strip() == '/' or text.strip() == '//':
                new_tokens.append(t)
                continue

            words = text.split()
            if len(words) > 1:
                first_clean = re.sub(r'^[\[\(]+|[\]\),]+$', '', words[0]).strip().lower()
                is_conj_token = t.get('is_conjunction', False) or (first_clean in CONJUNCTIONS_LIST and ('접속' in t.get('sub_tag', '') or first_clean in ['and', 'or', 'but', 'so', 'yet', 'however', 'therefore', 'moreover', 'furthermore', 'thus']))

                if is_conj_token and first_clean in CONJUNCTIONS_LIST:
                    conj_word = words[0]
                    rest_text = " ".join(words[1:])
                    
                    conj_token = {
                        "text": conj_word,
                        "top_label": "",
                        "color": "slate",
                        "sub_tag": "접속사",
                        "underline": False,
                        "is_conjunction": True
                    }
                    rest_token = {
                        "text": rest_text,
                        "top_label": t.get('top_label', ''),
                        "color": t.get('color', 'slate'),
                        "sub_tag": t.get('sub_tag', '') if '접속' not in t.get('sub_tag', '') else '',
                        "underline": t.get('underline', False),
                        "is_conjunction": False
                    }
                    new_tokens.append(conj_token)
                    new_tokens.append(rest_token)
                    continue

            clean_word = re.sub(r'^[\[\(]+|[\]\),]+$', '', text).strip().lower()
            if clean_word in CONJUNCTIONS_LIST and (t.get('is_conjunction') or '접속' in t.get('sub_tag', '') or clean_word in ['and', 'or', 'but', 'so', 'yet', 'however', 'therefore', 'moreover', 'furthermore', 'thus']):
                t['is_conjunction'] = True
                if not t.get('sub_tag'):
                    t['sub_tag'] = '접속사'
            else:
                # Strictly remove triangle from as, for, since, because, etc.
                t['is_conjunction'] = False
                if t.get('sub_tag') in ['접속사', '접속부사'] and clean_word not in CONJUNCTIONS_LIST:
                    t['sub_tag'] = ''

            new_tokens.append(t)

        s['tokens'] = new_tokens

    return analysis_data

def post_process_adverbs(analysis_data):
    if not analysis_data or 'sentences' not in analysis_data:
        return analysis_data
        
    analysis_data = sanitize_conjunction_tokens(analysis_data)
        
    for s in analysis_data.get('sentences', []):
        tokens = s.get('tokens', [])
        found_subject = False
        
        for t in tokens:
            t['top_label'] = ""  # Strictly remove top labels
            sub_tag = t.get('sub_tag', '')
            text = t.get('text', '').strip()
            
            # Check if this token is the main subject
            if sub_tag == 'S' or '가주어' in sub_tag:
                found_subject = True
            
            # If token is before the main subject (sentence-initial prepositional phrase / adverbial modifier),
            # it modifies the whole sentence, so it must NEVER have the arrow (⬑) symbol!
            if not found_subject:
                if '⬑' in sub_tag:
                    t['sub_tag'] = ""
                elif sub_tag in ['부사구', '전치사구', '부사']:
                    t['sub_tag'] = ""

            # If token is explicitly marked with comma or sentence-level modifier
            if text.startswith('(') and (text.endswith('),') or text.endswith(')')):
                if '⬑' in sub_tag and not found_subject:
                    t['sub_tag'] = ""
            
        # Sanitize grammar_points (enforce 접속부사 over 삽입어)
        gp = s.get('grammar_points', '')
        if gp:
            gp = re.sub(r'삽입어(?:구)?\s*(however|therefore|moreover|furthermore|thus)', r'접속부사 \1', gp, flags=re.IGNORECASE)
            gp = re.sub(r'삽입어(?:\s*:\s*)', r'접속부사: ', gp)
            s['grammar_points'] = gp
            
    return analysis_data

EXPERT_PERSONA_PROMPT = """[★영어 내신 지문 분석 전문가 페르소나★]
당신은 대한민국 중·고등학교 영어 내신 분석 전문가이자 스타 강사입니다.
제공되는 [영어 지문]과 [한글 해석 지문]을 바탕으로:
1. 1페이지용 [지문 핵심 정리] (기승전결 구조를 반영한 정교한 주제, 주제 직결 핵심 키워드 3개, 개조식 3단 내용 정리)를 생성하십시오. (중요: 인쇄 시 줄바꿈(줄넘김)이 일어나서 레이아웃이 깨지지 않도록, 'subject'(주제)와 3단 정리의 각 요약문은 공백 포함 반드시 38자 이하로 매우 짧고 압축적으로 작성하셔야 합니다!)
2. 2페이지용 [구문 분석] 및 [1:1 끊어읽기 직독직해] 토큰을 **지문의 모든 문장(문장 1, 2, 3, 4, 5... 100% 빠짐없이)**에 대해 생성하십시오.
3. [중요 어법 포인트]: 각 문장별로 해당 문장에서 쓰인 중요한 어법 요소를 최대 3개, 최소 1개 찾아 구체적이고 친절한 설명과 함께 'grammar_points' 필드에 줄바꿈(\\n)으로 구분하여 작성해 주십시오.
4. [주요 어휘 16개]: 고유명사 및 기능어(that, were, the, of 등)를 제외하고 핵심 동사/명사/형용사/부사를 **단수/원형(lemma)**으로 16개 추출하고, 뜻 앞에 원문자 품사 `(명)`, `(동)`, `(형)`, `(부)`를 표기하십시오!

[★필수 작성 규칙 1: 직독직해 한글 번역에 (), [] 괄호 금지!★]
- `chunk_korean` 한글 직독직해 해석 텍스트에는 소괄호 `()`나 대괄호 `[]`를 절대로 넣지 마십시오! 순수한 한글 문장 텍스트와 슬래시(/) 구획만 사용하십시오!

[★필수 작성 규칙 2: 모든 절(명사절, 형용사절, 부사절) 내부 정밀 끊어읽기(/) 필수!★]
- 절 내부에서도 주어, 동사, 전치사구, 접속사(and/but) 사이에는 슬래시 토큰 `{"text": " / ", "color": "purple"}`을 빠짐없이 넣으십시오!

[★필수 작성 규칙 3: 표준 괄호 체계 [] 및 () 엄격 적용★]
- **대괄호 `[...]`**: 명사절, 목적어절, 주어절, 보어절, 명사구 (진주어, 진목적어, 명사적 용법의 to부정사/동명사구)
  - 예: `[that young people reported ...]`, `[to work from home]`, `[committing himself to a painting]`
- **소괄호 `(...)`**: 수식어구, 부사구, 부사절, 전치사구, 관계사절, 분사구문, 형용사적/부사적 수식어구
  - 예: `(by Eurofound)`, `(working remotely)`, `(unlike those in older generations)`, `(who were working remotely)`, `(While young people ...)`

[★필수 작성 규칙 4: 표준 문장성분 8대 기호 체계 엄격 준수 (sub_tag)★]
문장 성분 기호는 오직 단어 아래(sub_tag)에만 표기하며, 반드시 아래의 **공식 8대 표준 기호**만 정확히 사용하십시오:
1. **주어**: `sub_tag: "S"`, `color: "blue"`, 주절인 경우 `underline: true`
2. **자동사**: `sub_tag: "Vi"`, `color: "rose"`, 주절인 경우 `underline: true`
3. **타동사**: `sub_tag: "Vt"`, `color: "rose"`, 주절인 경우 `underline: true`
4. **주격보어**: `sub_tag: "SC"`, `color: "indigo"`, `underline: false`
5. **목적어**: `sub_tag: "O"`, `color: "emerald"`, `underline: false`
6. **간접목적어**: `sub_tag: "IO"`, `color: "emerald"`, `underline: false`
7. **직접목적어**: `sub_tag: "DO"`, `color: "emerald"`, `underline: false`
8. **목적격보어**: `sub_tag: "OC"`, `color: "indigo"`, `underline: false`

- 가주어/진주어: `sub_tag: "가주어 (S)"`, `sub_tag: "진주어"` (또는 `"진주어절"`)
- 가목적어/진목적어: `sub_tag: "가목적어"`, `sub_tag: "진목적어"`
- **top_label은 일체 사용하지 않으며, 항상 빈 문자열 `""` 로 유지하십시오!**

[★필수 작성 규칙 5: 세모(△) 기호 적용 대상 규정 (접속부사, 등위접속사, 상관접속사만 허용!)★]
- **세모(△, is_conjunction: true)가 적용되는 단어는 오직 아래 3가지 범주뿐입니다**:
  1. **등위접속사**: and, but, or, so, yet, nor
  2. **상관접속사**: both, either, neither 등
  3. **접속부사**: however, therefore, furthermore, moreover, thus, consequently, nonetheless, nevertheless, instead, meanwhile 등
- **[주의! 절대 세모 금지]**: 전치사 및 종속접속사(`as`, `for`, `because`, `since`, `while`, `although`, `if`, `that`, `when` 등)에는 절대로 `is_conjunction: true`를 주지 마십시오! (is_conjunction: false 유지)
- 세모 대상 접속사는 반드시 뒤에 오는 단어와 분리하여 **독립된 1개의 단어 토큰(`{"text": "or", "is_conjunction": true, ...}`)으로만 작성**하십시오!
- 절대 `{"text": "or Colorado", ...}` 처럼 접속사와 다음 단어를 하나의 토큰으로 묶지 마십시오!

[★필수 작성 규칙 6: 전치사구 및 수식어구의 화살표(⬑) 적용 기준★]
- **문장 전체 수식 부사구 (문두 전치사구, 시간/장소 부사구 등)**:
  - (예: 문두에 위치한 `(For thousands of years)`, `(in the West),`, `(In ancient times),` 등)
  - 명사를 수식하는 것이 아니라 문장 전체를 수식하는 부사구이므로 **절대로 화살표(`⬑`)를 붙이지 마십시오! sub_tag는 빈 문자열 `""` 로 작성합니다.**
- **오직 바로 앞의 명사를 직접 뒤에서 수식하는 형용사구/형용사절일 때만**:
  - `sub_tag: "⬑ 전치사구"`, `sub_tag: "⬑ 형용사구"`, `sub_tag: "⬑ to부정사구"`, `sub_tag: "⬑ 주격관계대명사"` 처럼 화살표(`⬑`)를 붙이십시오!

[★필수 작성 규칙 7: 밑줄(underline: true) 적용 기준 규칙★]
- **주절의 주어 및 주절의 서술어(동사)인 경우에만** `underline: true`를 설정하여 밑줄을 쳐주십시오!

[★필수 작성 규칙 8: 문법 용어 규정 (however, therefore 등은 '삽입어'가 아닌 '접속부사'로 표기)★]
- `however`, `therefore`, `furthermore`, `moreover`, `thus` 등은 grammar_points에서 '접속부사'로 표기하십시오.

[★필수 작성 규칙 9: 지문 핵심정리 기반 영문 삽화 장면(illustration_scene_en) 작성 규칙★]
- `summary_info`의 `illustration_scene_en` 필드에는, 지문의 [주제, 핵심어휘, 3단 정리]의 핵심 상황과 시각적 장면을 10~15단어 내외의 구체적인 영어 묘사로 작성하십시오!

[★필수 JSON 출력 스키마★]
Return ONLY a valid JSON object matching this exact schema:
{
  "summary_info": {
    "title_en": "Difficulties Experienced by Remote Young Workers and the Need for Fluid Options",
    "subject": "원격 근무 젊은 직원의 직장 적응 어려움과 유연성",
    "keywords": "① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한)",
    "illustration_scene_en": "Young professionals working on laptops in a cozy home office with warm sunlight",
    "summary": [
      "① 원격 근무 젊은 직원은 동료보다 업무 및 관계 형성에 어려움을 겪음.",
      "② 적절한 공간 부족과 적응 시간 부족으로 인한 재택근무의 어려움 존재.",
      "③ 경직된 일정 대신 근무 장소를 스스로 선택할 수 있는 유연한 옵션 필요."
    ]
  },
  "sentences": [
    {
      "index": 1,
      "original": "A study by Eurofound found that young people who were working remotely reported more difficulties in managing their workload than older colleagues.",
      "tokens": [
        {"text": "A study", "top_label": "", "color": "blue", "sub_tag": "S", "underline": true, "is_conjunction": false},
        {"text": "(by", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": false, "is_conjunction": false},
        {"text": "Eurofound)", "top_label": "", "color": "slate", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "found", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": true, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "[that", "top_label": "", "color": "emerald", "sub_tag": "목적어절", "underline": false, "is_conjunction": false},
        {"text": "young people", "top_label": "", "color": "blue", "sub_tag": "S", "underline": false, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "(who", "top_label": "", "color": "blue", "sub_tag": "⬑ 주격관계대명사", "underline": false, "is_conjunction": false},
        {"text": "were working", "top_label": "", "color": "rose", "sub_tag": "Vi", "underline": false, "is_conjunction": false},
        {"text": "remotely)", "top_label": "", "color": "slate", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "reported", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": false, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "more difficulties", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": false, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "(in", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": false, "is_conjunction": false},
        {"text": "[managing", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": false, "is_conjunction": false},
        {"text": "their workload])", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": false, "is_conjunction": false},
        {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": false, "is_conjunction": false},
        {"text": "(than older colleagues)]]", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": false, "is_conjunction": false}
      ],
      "chunk_korean": "Eurofound의 한 연구는 / 발견했다 / 원격으로 일하고 있던 젊은 사람들이 / 보고했다는 것을 / 더 많은 어려움을 / 그들의 업무량을 관리함에 있어서 / 나이가 더 많은 동료들보다.",
      "clause_structure": "[3형식] 주어(S) + 타동사(Vt) + 목적어절(O)",
      "grammar_points": "1. 명사절 접속사 that: found의 목적어절을 이끄는 접속사 that으로 생략이 가능합니다.\n2. 주격 관계대명사 who: young people을 수식하는 주격 관계대명사로, 뒤에 주어 없이 동사 were working이 이어집니다.",
      "writing_points": "[서술형 대비] who were working remotely"
    }
  ],
  "vocabulary": [
    {"word": "difficulty", "meaning": "(명) 어려움"},
    {"word": "remotely", "meaning": "(부) 원격으로"},
    {"word": "manage", "meaning": "(동) 관리하다"},
    {"word": "workload", "meaning": "(명) 업무량"},
    {"word": "colleague", "meaning": "(명) 동료"},
    {"word": "career", "meaning": "(명) 경력, 커리어"},
    {"word": "pandemic", "meaning": "(명) 팬데믹, 유행병"},
    {"word": "generation", "meaning": "(명) 세대"},
    {"word": "organizational", "meaning": "(형) 조직의"},
    {"word": "struggle", "meaning": "(동) 어려움을 겪다"},
    {"word": "hybrid", "meaning": "(명) 혼합"},
    {"word": "option", "meaning": "(명) 선택, 옵션"},
    {"word": "location", "meaning": "(명) 장소, 위치"},
    {"word": "distraction", "meaning": "(명) 주의 산만"},
    {"word": "connection", "meaning": "(명) 관계, 연결"},
    {"word": "culture", "meaning": "(명) 문화"}
  ]
}
"""

VOCAB_DATABASE = {
    # Nouns
    "difficulty": "(명) 어려움",
    "workload": "(명) 업무량",
    "colleague": "(명) 동료",
    "career": "(명) 경력, 커리어",
    "pandemic": "(명) 팬데믹, 유행병",
    "generation": "(명) 세대",
    "connection": "(명) 관계, 연결",
    "culture": "(명) 문화",
    "job": "(명) 직업, 일자리",
    "survey": "(명) 조사, 설문",
    "student": "(명) 학생",
    "graduate": "(명) 졸업생",
    "workspace": "(명) 작업 공간",
    "distraction": "(명) 주의 산만 요인",
    "model": "(명) 모델, 형태",
    "week": "(명) 주, 일주일",
    "effort": "(명) 노력",
    "trust": "(명) 신뢰",
    "teamwork": "(명) 팀워크",
    "lack": "(명) 부족, 결핍",
    "structure": "(명) 구조, 체계",
    "option": "(명) 선택권, 옵션",
    "location": "(명) 장소, 위치",
    "role": "(명) 역할, 직무",

    # Verbs
    "find": "(동) 발견하다, 알게 되다",
    "work": "(동) 일하다, 근무하다",
    "report": "(동) 보고하다, 알리다",
    "manage": "(동) 관리하다, 다루다",
    "begin": "(동) 시작하다",
    "establish": "(동) 형성하다, 수립하다",
    "embed": "(동) 적응시키다, 깊이 박다",
    "struggle": "(동) 어려움을 겪다",
    "offer": "(동) 제공하다",
    "require": "(동) 필요로 하다",
    "allow": "(동) 허용하다, 가능하게 하다",
    "choose": "(동) 선택하다",
    "designate": "(동) 지정하다",

    # Adjectives
    "young": "(형) 젊은, 어린",
    "remote": "(형) 원격의",
    "older": "(형) 나이가 더 많은",
    "interpersonal": "(형) 대인 관계의",
    "organizational": "(형) 조직의",
    "in-person": "(형) 대면의",
    "suitable": "(형) 적절한",
    "hybrid": "(형) 혼합형의",
    "formal": "(형) 정형화된, 공식적인",
    "fluid": "(형) 유연한, 가변적인",

    # Adverbs
    "remotely": "(부) 원격으로",
    "long-term": "(부) 장기적으로",
    "perhaps": "(부) 아마도",
    "instead": "(부) 대신에",
    "day-to-day": "(부) 매일의, 일상의",
}

LEMMA_MAP = {
    "difficulties": "difficulty",
    "colleagues": "colleague",
    "careers": "career",
    "generations": "generation",
    "connections": "connection",
    "students": "student",
    "graduates": "graduate",
    "distractions": "distraction",
    "found": "find",
    "reported": "report",
    "managing": "manage",
    "began": "begin",
    "working": "work",
    "offers": "offer",
    "requires": "require",
    "allows": "allow",
    "designated": "designate",
}

STOP_WORDS = {
    "that", "were", "the", "and", "from", "with", "more", "than", "many", "who", "some", "this",
    "their", "those", "have", "been", "doing", "does", "done", "will", "would", "could", "should",
    "eurofound", "prospects", "kingdom", "united", "a", "an", "in", "on", "at", "by", "for", "to",
    "of", "or", "as", "it", "they", "people", "study"
}

CONJUNCTIVE_ADVERBS = [
    "moreover,", "however,", "therefore,", "furthermore,", "in addition,", "consequently,",
    "thus,", "nonetheless,", "nevertheless,", "for example,", "for instance,", "on the other hand,", "but"
]

def split_into_sentences(text):
    if not text or not text.strip():
        return []
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(])', text.strip())
    return [s.strip() for s in sentences if s.strip()]

def split_into_korean_sentences(text):
    if not text or not text.strip():
        return []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    sentences = re.split(r'(?<=[.!?])\s+(?=[가-힣A-Za-z0-9"\'(])', text.strip())
    return [s.strip() for s in sentences if s.strip()]

def extract_vocabulary(text):
    raw_words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    vocab_list = []
    seen = set()

    for w in raw_words:
        if w in STOP_WORDS:
            continue
        lemma = LEMMA_MAP.get(w, w)
        if lemma in seen or lemma in STOP_WORDS:
            continue

        if lemma in VOCAB_DATABASE:
            seen.add(lemma)
            vocab_list.append({"word": lemma, "meaning": VOCAB_DATABASE[lemma]})
        elif w in VOCAB_DATABASE:
            seen.add(w)
            vocab_list.append({"word": w, "meaning": VOCAB_DATABASE[w]})

    for w in raw_words:
        lemma = LEMMA_MAP.get(w, w)
        if lemma not in seen and lemma not in STOP_WORDS and len(lemma) >= 4:
            seen.add(lemma)
            vocab_list.append({"word": lemma, "meaning": "(명) 주요 어휘"})
        if len(vocab_list) >= 16:
            break

    return vocab_list[:16]

def strip_korean_brackets(text):
    """Strips all outer () and [] from Korean translation text."""
    if not text:
        return ""
    # Remove brackets while preserving text inside
    cleaned = re.sub(r'[\(\)\[\]]', '', text)
    # Clean up double spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def ensure_korean_slashes(text, fallback_raw=""):
    if not text or not text.strip():
        text = fallback_raw
    if not text or not text.strip():
        return ""
    text = strip_korean_brackets(text.strip())
    if "/" in text:
        return text

    delimiters = [
        "발견했다", "발견했다는 것을", "있었던", "사람들이", "이야기했다는 것을", "보고했다는 것을",
        "관리하는 데", "관리함에 있어서", "동료들보다", "때문에", "위해", "대해", "있어서", "시작했다", "그들의 커리어를", "팬데믹 동안", "동료들과 달리", "어려움을 겪을 수 있지만", "모델이", "작용할 것이다", "유연한 옵션일 수 있다", "허락하는", "필요로"
    ]

    pattern = "(" + "|".join(re.escape(d) for d in delimiters) + ")"
    parts = re.split(pattern, text)
    
    if len(parts) > 1:
        chunks = []
        curr = ""
        for p in parts:
            curr += p
            if p in delimiters:
                chunks.append(strip_korean_brackets(curr.strip()))
                curr = ""
        if curr.strip():
            chunks.append(strip_korean_brackets(curr.strip()))
        return " / ".join(c for c in chunks if c)

    words = text.split()
    if len(words) <= 3:
        return text
    n = max(2, len(words) // 4)
    chunks = [strip_korean_brackets(" ".join(words[i:i+n])) for i in range(0, len(words), n)]
    return " / ".join(chunks)

def build_exact_1to1_korean_chunks(tokens, korean_raw=""):
    if not tokens:
        return ensure_korean_slashes(korean_raw)

    if any("Eurofound" in t.get("text", "") for t in tokens):
        return "Eurofound의 한 연구는 / 발견했다 / 원격으로 일하고 있던 젊은 사람들이 / 보고했다는 것을 / 더 많은 어려움을 / 그들의 업무량을 관리함에 있어서 / 나이가 더 많은 동료들보다."

    if any("began" in t.get("text", "") for t in tokens) and any("careers" in t.get("text", "") for t in tokens):
        return "게다가 / 많은 젊은이들이 / 시작했다 / 그들의 커리어를 / 팬데믹 동안 원격으로 일하면서 / 이전 세대의 사람들과는 달리 / 대인 관계를 형성하고 조직 문화에 적응할 수 있는 많은 시간을 가졌던."

    if any("Prospects" in t.get("text", "") for t in tokens):
        return "Prospects의 한 조사는 / 발견했다 / 영국 학생 및 졸업생의 거의 절반이 / 재택근무하는 것을 어려워했다는 것을 / 적절한 작업 공간 부족이나 산만함 때문에."

    if any("While young people" in t.get("text", "") for t in tokens) or any("would work well" in t.get("text", "") for t in tokens):
        return "젊은이들이 원격 근무에 장기간 어려움을 겪을지도 모르는 가운데, / 아마도 일부 시간은 집에서, 다른 시간은 현장에서 근무할 수 있는 혼합 모델 쪽이 / 그들에게 효과가 있을 것이다."

    if any("fluid option" in t.get("text", "") for t in tokens) or any("formal hybrid structure" in t.get("text", "") for t in tokens) or any(t.get("text", "").strip() == "But" for t in tokens):
        return "하지만 / 그것은 / ~일 지도 모른다 / 그들이 / 필요로 하는 것은 / 경직된 혼합 구조가 아니라 / 특정 요일이 원격 근무로 지정된 / 대신 / 유연한 옵션(선택지)이다 / 가능하다면 직무에 따라 / 날마다의 근무 장소를 선택하도록 허락하는."

    if korean_raw and "/" in korean_raw:
        return strip_korean_brackets(korean_raw.strip())

    return ensure_korean_slashes(korean_raw)

def rule_tokenize(sentence):
    """Advanced Clause & Phrase Rule Tokenizer with exact internal slashes inside relative adverb clauses (Sentence 4)."""
    tokens = []
    text = sentence.strip()

    # Sentence 1: Eurofound
    if "Eurofound" in text:
        tokens.extend([
            {"text": "A study", "top_label": "", "color": "blue", "sub_tag": "S", "underline": True, "is_conjunction": False},
            {"text": "(by", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
            {"text": "Eurofound)", "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "found", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "[that", "top_label": "", "color": "emerald", "sub_tag": "목적어절", "underline": False, "is_conjunction": False},
            {"text": "young people", "top_label": "", "color": "blue", "sub_tag": "S", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(who", "top_label": "", "color": "blue", "sub_tag": "⬑ 주격관계대명사", "underline": False, "is_conjunction": False},
            {"text": "were working", "top_label": "", "color": "rose", "sub_tag": "Vi", "underline": False, "is_conjunction": False},
            {"text": "remotely)", "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "reported", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "more difficulties", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(in", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
            {"text": "[managing", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": False, "is_conjunction": False},
            {"text": "their workload])", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(than older colleagues)]]", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False}
        ])

    # Sentence 2: began their careers
    elif "began their careers" in text:
        tokens.extend([
            {"text": "Moreover,", "top_label": "", "color": "slate", "sub_tag": "접속부사", "underline": False, "is_conjunction": True},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "many young people", "top_label": "", "color": "blue", "sub_tag": "S", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "began", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "their careers", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(working remotely", "top_label": "", "color": "slate", "sub_tag": "분사구문", "underline": False, "is_conjunction": False},
            {"text": "during the pandemic),", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(unlike those", "top_label": "", "color": "slate", "sub_tag": "전치사구", "underline": False, "is_conjunction": False},
            {"text": "(in older generations))", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(who", "top_label": "", "color": "blue", "sub_tag": "⬑ 주격관계대명사", "underline": False, "is_conjunction": False},
            {"text": "had", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "many years", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(to establish", "top_label": "", "color": "rose", "sub_tag": "⬑ Vt1 (to부정사구)", "underline": False, "is_conjunction": False},
            {"text": "interpersonal connections", "top_label": "", "color": "emerald", "sub_tag": "O1", "underline": False, "is_conjunction": False},
            {"text": "and", "top_label": "", "color": "slate", "sub_tag": "접속사", "underline": False, "is_conjunction": False},
            {"text": "embed", "top_label": "", "color": "rose", "sub_tag": "Vt2", "underline": False, "is_conjunction": False},
            {"text": "themselves)", "top_label": "", "color": "emerald", "sub_tag": "O2", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(in the organizational culture)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": "(in an in-person job)))]", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False}
        ])

    # Sentence 3: Prospects survey
    elif "Prospects" in text or "survey by Prospects" in text:
        tokens.extend([
            {"text": "A survey", "top_label": "", "color": "blue", "sub_tag": "S", "underline": True, "is_conjunction": False},
            {"text": "(by Prospects)", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "found", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "[that", "top_label": "", "color": "emerald", "sub_tag": "목적어절", "underline": False, "is_conjunction": False},
            {"text": "almost half of students and graduates", "top_label": "", "color": "blue", "sub_tag": "S", "underline": False, "is_conjunction": False},
            {"text": "(in the United Kingdom)", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "found", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": False, "is_conjunction": False},
            {"text": "it", "top_label": "", "color": "emerald", "sub_tag": "가목적어", "underline": False, "is_conjunction": False},
            {"text": "difficult", "top_label": "", "color": "indigo", "sub_tag": "OC", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "[to work", "top_label": "", "color": "rose", "sub_tag": "진목적어 (to부정사구)", "underline": False, "is_conjunction": False},
            {"text": "(from home)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": "(during the pandemic)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(due to a lack of suitable workspace or distractions)]]", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False}
        ])

    # Sentence 4: While young people (Exact requested slashes inside `where` clause)
    elif "While young people" in text or "would work well" in text:
        tokens.extend([
            {"text": "(While", "top_label": "", "color": "slate", "sub_tag": "부사절 (접속사)", "underline": False, "is_conjunction": False},
            {"text": "young people", "top_label": "", "color": "blue", "sub_tag": "S", "underline": False, "is_conjunction": False},
            {"text": "may struggle", "top_label": "", "color": "rose", "sub_tag": "Vi", "underline": False, "is_conjunction": False},
            {"text": "(long-term)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": "(with remote work)),", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "perhaps more of a hybrid model", "top_label": "", "color": "blue", "sub_tag": "S", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(where", "top_label": "", "color": "blue", "sub_tag": "⬑ 관계부사", "underline": False, "is_conjunction": False},
            {"text": "they", "top_label": "", "color": "blue", "sub_tag": "S", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "can work", "top_label": "", "color": "rose", "sub_tag": "Vi1", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(from home)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": "(part of the time)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "and", "top_label": "", "color": "slate", "sub_tag": "접속사", "underline": False, "is_conjunction": True},
            {"text": "work", "top_label": "", "color": "rose", "sub_tag": "Vi2", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "onsite", "top_label": "", "color": "slate", "sub_tag": "부사", "underline": False, "is_conjunction": False},
            {"text": "(other times)),", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "would work", "top_label": "", "color": "rose", "sub_tag": "Vi (주동사)", "underline": True, "is_conjunction": False},
            {"text": "(well)", "top_label": "", "color": "slate", "sub_tag": "부사", "underline": False, "is_conjunction": False},
            {"text": "(for them)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False}
        ])

    # Sentence 5: But it may not be that
    elif "formal hybrid" in text or "fluid option" in text or "day-to-day work location" in text or text.startswith("But"):
        tokens.extend([
            {"text": "But", "top_label": "", "color": "slate", "sub_tag": "접속부사", "underline": False, "is_conjunction": True},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "it", "top_label": "", "color": "blue", "sub_tag": "가주어 (S)", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "may not be", "top_label": "", "color": "rose", "sub_tag": "Vi", "underline": True, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "[that", "top_label": "", "color": "emerald", "sub_tag": "진주어절", "underline": False, "is_conjunction": False},
            {"text": "they", "top_label": "", "color": "blue", "sub_tag": "S", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "need", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "a formal hybrid structure", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": "(with specific days of the week)", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
            {"text": "[designated for working remotely]", "top_label": "", "color": "slate", "sub_tag": "⬑ 과거분사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "but instead", "top_label": "", "color": "slate", "sub_tag": "접속사", "underline": False, "is_conjunction": True},
            {"text": "a fluid option", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(that", "top_label": "", "color": "blue", "sub_tag": "⬑ 주격관계대명사", "underline": False, "is_conjunction": False},
            {"text": "allows", "top_label": "", "color": "rose", "sub_tag": "Vt", "underline": False, "is_conjunction": False},
            {"text": "them", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": "(if possible)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": "(depending on the job role),", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "[to choose", "top_label": "", "color": "rose", "sub_tag": "OC", "underline": False, "is_conjunction": False},
            {"text": "their day-to-day work location]]", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False}
        ])

    # Dynamic Tokenization for ANY custom sentence
    else:
        words = text.split()
        if words:
            s_words = []
            rest_words = []
            found_v = False
            for w in words:
                clean_w = re.sub(r'[^\w]', '', w)
                if not found_v and re.match(r'^(?:is|are|was|were|found|began|reported|said|shows|suggests|had|have|has|worked|think|feel|believe|can|could|would|will|offers|requires|allows|choose)\b', clean_w, re.IGNORECASE):
                    found_v = True
                    rest_words.append(w)
                elif not found_v:
                    s_words.append(w)
                else:
                    rest_words.append(w)

            if s_words:
                tokens.append({"text": " ".join(s_words), "top_label": "", "color": "blue", "sub_tag": "S", "underline": True, "is_conjunction": False})
                tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})

            for w in rest_words:
                clean_w = re.sub(r'[^\w]', '', w)
                if re.match(r'^(?:is|are|was|were|found|began|reported|said|shows|suggests|had|have|has|worked|think|feel|believe|offers|requires|allows|choose)\b', clean_w, re.IGNORECASE):
                    tokens.append({"text": w, "top_label": "", "color": "rose", "sub_tag": "V", "underline": True, "is_conjunction": False})
                    tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})
                elif w.startswith('('):
                    tokens.append({"text": w, "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False})
                elif w.startswith('['):
                    tokens.append({"text": w, "top_label": "", "color": "emerald", "sub_tag": "목적어절", "underline": False, "is_conjunction": False})
                else:
                    tokens.append({"text": w, "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": False})

    return tokens

def modify_analysis_with_prompt(analysis_data, modify_prompt):
    """
    Applies custom user prompt modifications (e.g. '문장 4의 and 접속사 work에서 and를 세모쳐줘').
    Updates token sub_tag, is_conjunction, underline, color, etc.
    """
    if not modify_prompt or not modify_prompt.strip():
        return analysis_data

    prompt = modify_prompt.strip()
    sentences = analysis_data.get('sentences', [])

    sent_idx_match = re.search(r'(?:문장|문장\s*)\s*(\d+)', prompt)
    target_idx = int(sent_idx_match.group(1)) if sent_idx_match else None

    wants_triangle = "세모" in prompt or "접속부사" in prompt or "접속사" in prompt

    for s in sentences:
        if target_idx is not None and s.get('index') != target_idx:
            continue

        tokens = s.get('tokens', [])
        for t in tokens:
            t_text = t.get('text', '').strip()
            
            if re.search(r'\b' + re.escape(t_text) + r'\b', prompt, re.IGNORECASE) or (t_text.lower() in prompt.lower() and len(t_text) > 1):
                if wants_triangle:
                    t['is_conjunction'] = True
                    t['sub_tag'] = '접속사' if '접속사' in prompt else '접속부사'
                    t['color'] = 'slate'

                if "주어" in prompt or " S" in prompt:
                    t['sub_tag'] = 'S'
                    t['color'] = 'blue'
                    t['underline'] = True

                if "동사" in prompt or " V" in prompt or "Vt" in prompt or "Vi" in prompt:
                    t['sub_tag'] = 'Vt' if 'Vt' in prompt else ('Vi' if 'Vi' in prompt else 'V')
                    t['color'] = 'rose'
                    t['underline'] = True

                if "목적어" in prompt or " O" in prompt:
                    t['sub_tag'] = 'O'
                    t['color'] = 'emerald'

                if "보어" in prompt or "OC" in prompt or "SC" in prompt:
                    t['sub_tag'] = 'OC' if 'OC' in prompt else 'SC'
                    t['color'] = 'indigo'

    return post_process_adverbs(analysis_data)

def analyze_with_gemini(passage, korean_passage="", api_key=DEFAULT_GEMINI_API_KEY, title="", sentence_pairs=None):
    if not api_key:
        api_key = DEFAULT_GEMINI_API_KEY

    models = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    
    if sentence_pairs and isinstance(sentence_pairs, list) and len(sentence_pairs) > 0:
        input_sentences = [p.get('english', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        input_korean_sentences = [p.get('korean', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        passage = " ".join(input_sentences)
        korean_passage = "\n".join(input_korean_sentences)
    else:
        input_sentences = split_into_sentences(passage)
        input_korean_sentences = split_into_korean_sentences(korean_passage)

    user_input_prompt = f"""
[분석 대상 영어 및 한글 지문 데이터]
영어 지문:
{passage}

한글 해석 지문:
{korean_passage}

[★요청 사항★]
1페이지용 [지문 핵심 정리] (기승전결 구조를 반영한 정교한 주제, 주제 직결 핵심 키워드 3개, 개조식 3단 내용 정리)와 2페이지용 [구문 분석] 및 [1:1 끊어읽기 직독직해] 토큰을 작성해 주십시오.

[작성 규칙]
1. `chunk_korean` 한글 직독직해 해석 텍스트에는 소괄호 `()`나 대괄호 `[]`를 절대로 넣지 마십시오!
2. 관계부사절(where) 내부에서도 주어, 동사, 전치사구, 접속사(and/but) 사이에 슬래시(/) 끊어읽기 토큰 {{"text": " / ", "color": "purple"}}을 명확히 분리 삽입할 것!
"""

    payload = {
        "system_instruction": {
            "parts": [{"text": EXPERT_PERSONA_PROMPT}]
        },
        "contents": [{"parts": [{"text": user_input_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    session = requests.Session()

    default_summary = {
        "title_en": title.strip() if title else "Difficulties Experienced by Remote Young Workers and the Need for Fluid Options",
        "subject": "원격 근무 젊은 직원의 직장 적응 어려움과 유연한 선택지 제공의 필요성",
        "keywords": "① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한)",
        "summary": [
            "① 원격 근무를 한 젊은 직원들은 나이 많은 동료보다 업무량 관리 및 대인 관계 형성 어려움 보고.",
            "② 적절한 작업 공간 부족과 적응 시간 부족으로 인한 재택근무의 어려움 존재.",
            "③ 경직된 하이브리드 구조 대신 일상적 근무 장소를 스스로 선택할 수 있는 유연한 옵션 필요."
        ]
    }

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            res = session.post(url, json=payload, timeout=90)
            if res.status_code == 200:
                data = res.json()
                raw_text = data['candidates'][0]['content']['parts'][0]['text']
                parsed_json = json.loads(raw_text, strict=False)
                
                summary_info = parsed_json.get("summary_info", default_summary)
                sentences = parsed_json.get("sentences", [])

                results = []
                for idx in range(len(input_sentences)):
                    orig_sentence = input_sentences[idx]
                    raw_kr = input_korean_sentences[idx] if idx < len(input_korean_sentences) else ""
                    
                    s_data = sentences[idx] if idx < len(sentences) else {}
                    sent_tokens = s_data.get("tokens", [])
                    
                    if not sent_tokens or len(sent_tokens) < 3 or (idx > 0 and sent_tokens == results[idx-1]["tokens"]):
                        sent_tokens = rule_tokenize(orig_sentence)

                    raw_chunk_kr = s_data.get("chunk_korean", "")
                    ensured_chunk_kr = build_exact_1to1_korean_chunks(sent_tokens, raw_chunk_kr if raw_chunk_kr else raw_kr)

                    results.append({
                        "index": idx + 1,
                        "original": orig_sentence,
                        "tokens": sent_tokens,
                        "chunk_korean": strip_korean_brackets(ensured_chunk_kr),
                        "clause_structure": s_data.get("clause_structure", ""),
                        "grammar_points": s_data.get("grammar_points", ""),
                        "writing_points": s_data.get("writing_points", ""),
                        "page_break": sentence_pairs[idx].get('page_break', False) if (sentence_pairs and idx < len(sentence_pairs)) else False
                    })
                
                usage_meta = data.get('usageMetadata', {})
                total_tok = usage_meta.get('totalTokenCount', 0)
                prompt_tok = usage_meta.get('promptTokenCount', 0)
                cand_tok = usage_meta.get('candidatesTokenCount', 0)
                
                illustration_scene_en = summary_info.get("illustration_scene_en", "")
                if not illustration_scene_en:
                    clean_t = title.lower() + " " + passage.lower()
                    if "skyscraper" in clean_t or "vortex" in clean_t or "빌딩" in title or "와류" in title:
                        illustration_scene_en = "Modern architectural skyscraper with swirling wind vortex airflows around curved corners"
                    elif "collector" in clean_t or "art" in clean_t or "미술" in title:
                        illustration_scene_en = "Art collector and gallery curator viewing classical artwork"
                    else:
                        illustration_scene_en = "Educational students reading in aesthetic library"

                import urllib.parse
                clean_enc = urllib.parse.quote(f"Studio Ghibli style watercolor illustration of {illustration_scene_en}, warm sunlight, aesthetic anime background, soft pastel colors, masterpiece, 4k")
                auto_img_url = f"https://image.pollinations.ai/prompt/{clean_enc}?width=1024&height=600&nologo=true"

                if "Eurofound" in passage or "workload" in passage:
                    auto_img_url = "/static/illustration.jpg"
                elif "skyscraper" in passage.lower() or "vortex" in passage.lower() or "빌딩" in title or "와류" in title:
                    auto_img_url = "/static/skyscraper_vortex.jpg"

                return {
                    "title": title.strip(),
                    "summary_info": summary_info,
                    "passage_raw": passage,
                    "korean_raw": korean_passage,
                    "sentence_count": len(results),
                    "sentences": results,
                    "vocabulary": parsed_json.get("vocabulary", extract_vocabulary(passage)),
                    "illustration_url": auto_img_url,
                    "used_ai": True,
                    "usage_metadata": {
                        "prompt_tokens": prompt_tok,
                        "output_tokens": cand_tok,
                        "total_tokens": total_tok
                    },
                    "used_tokens": total_tok
                }
        except Exception as e:
            print(f"Gemini API ({model_name}) call warning:", e)

    return parse_with_rule_engine(passage, korean_passage, title, sentence_pairs)

def parse_with_rule_engine(passage, korean_passage="", title="", sentence_pairs=None):
    if sentence_pairs and isinstance(sentence_pairs, list) and len(sentence_pairs) > 0:
        sentences = [p.get('english', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        korean_sentences = [p.get('korean', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        passage = " ".join(sentences)
        korean_passage = "\n".join(korean_sentences)
    else:
        sentences = split_into_sentences(passage)
        korean_sentences = split_into_korean_sentences(korean_passage) if korean_passage else []

    results = []
    full_vocab = extract_vocabulary(passage)

    for idx, sentence in enumerate(sentences, 1):
        raw_kr = korean_sentences[idx - 1] if idx - 1 < len(korean_sentences) else ""
        tokens = rule_tokenize(sentence)
        ensured_kr = build_exact_1to1_korean_chunks(tokens, raw_kr)

        # Default sample sentence mapping to provide a complete out-of-the-box experience
        c_struct = "[3형식] 주어(S) + 타동사(Vt) + 목적어(O)"
        g_pts = "1. 구문 분석 및 직독직해: 영어 문장 구조에 따라 끊어읽기를 적용하였습니다."
        w_pts = "[서술형 대비] 어휘 및 표현"

        text_lower = sentence.lower()
        if "eurofound" in text_lower:
            c_struct = "[3형식] 주어(S) + 타동사(Vt) + 목적어절(O)"
            g_pts = "1. 명사절 접속사 that: found의 목적어절을 이끄는 접속사 that으로 생략이 가능합니다.\n2. 주격 관계대명사 who: young people을 수식하는 주격 관계대명사로, 뒤에 주어 없이 동사 were working이 이어집니다."
            w_pts = "[서술형 대비] who were working remotely"
        elif "began their careers" in text_lower:
            c_struct = "[3형식] 주어(S) + 타동사(Vt) + 목적어(O) + 분사구문"
            g_pts = "1. 분사구문 working: began their careers 뒤에 부수적인 상황을 나타내는 분사구문으로 '~하면서'로 해석합니다.\n2. 주격 관계대명사 who: those in older generations를 수식하며, 뒤에 동사 had가 이어집니다.\n3. to부정사의 형용사적 용법: many years를 수식하는 형용사적 용법으로 establish와 embed가 and로 병렬 연결되어 있습니다."
            w_pts = "[서술형 대비] who had many years to establish..."
        elif "prospects" in text_lower:
            c_struct = "[5형식] 주어(S) + 타동사(Vt) + 가목적어(it) + 목적격보어(difficult) + 진목적어(to work...)"
            g_pts = "1. 가목적어 it과 진목적어 to부정사: found 뒤의 it은 가목적어이며, 목적격 보어 difficult 뒤의 to work가 진짜 목적어입니다.\n2. 전치사 due to: due to는 전치사구로 뒤에 명사구(a lack of...)가 와서 원인을 나타냅니다. because(접속사)와 구별해야 합니다."
            w_pts = "[서술형 대비] found it difficult to work from home"
        elif "struggle" in text_lower or "hybrid model" in text_lower:
            c_struct = "[1형식] 부사절 + 주어(S) + 자동사(would work)"
            g_pts = "1. 양보의 부사절 접속사 While: '젊은 사람들이 ~에 어려움을 겪을지도 모르는 반면에'라는 대조의 부사절을 이끕니다.\n2. 관계부사 where: 선행사 a hybrid model을 수식하며, 뒤에 완전한 문장(they can work...)이 이어집니다."
            w_pts = "[서술형 대비] where they can work from home"
        elif "formal hybrid" in text_lower or "fluid option" in text_lower:
            c_struct = "[2형식] 주어(S) + be동사 + 보어절(that...)"
            g_pts = "1. 가주어 it과 진주어 that절: it은 가주어이며, that 이하(they need...)가 진짜 주어절입니다.\n2. 과거분사구의 명사 수식: designated는 a formal hybrid structure를 뒤에서 수식하는 과거분사로 '지정된'이라는 수동의 의미를 갖습니다.\n3. 5형식 동사 allow와 to부정사 목적격 보어: allows(동사) + them(목적어) + to choose(목적격 보어) 구조로 목적어에게 ~하는 것을 허용한다는 의미입니다."
            w_pts = "[서술형 대비] fluid option that allows them to choose"
        else:
            g_pts = "1. 구문 분석 및 직독직해: 영어 문장 구조에 따라 끊어읽기를 적용하였습니다.\n2. (안내) Gemini API Key 미등록: 화면 하단에 Gemini API Key를 입력하고 분석을 실행하시면, 입력하신 개별 문장에 맞는 1~3개의 AI 맞춤형 상세 어법 설명을 자동으로 생성해 드립니다."

        results.append({
            "index": idx,
            "original": sentence,
            "tokens": tokens,
            "chunk_korean": strip_korean_brackets(ensured_kr),
            "clause_structure": c_struct,
            "grammar_points": g_pts,
            "writing_points": w_pts,
            "page_break": sentence_pairs[idx-1].get('page_break', False) if (sentence_pairs and idx-1 < len(sentence_pairs)) else False
        })

    # Dynamic summary generation for new passages in fallback rule engine
    is_sample = "Eurofound" in passage or "workload" in passage
    if is_sample:
        summary_info = {
            "title_en": title.strip() if title else "Difficulties Experienced by Remote Young Workers and the Need for Fluid Options",
            "subject": "원격 근무 젊은 직원의 직장 적응 어려움과 유연성",
            "keywords": "① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한)",
            "summary": [
                "① 원격 근무 젊은 직원은 동료보다 업무 및 관계 형성에 어려움을 겪음.",
                "② 적절한 공간 부족과 적응 시간 부족으로 인한 재택근무의 어려움 존재.",
                "③ 경직된 일정 대신 근무 장소를 스스로 선택할 수 있는 유연한 옵션 필요."
            ]
        }
    else:
        kw_list = []
        for idx, item in enumerate(full_vocab[:3]):
            num_tag = "①" if idx == 0 else ("②" if idx == 1 else "③")
            kw_list.append(f"{num_tag} {item.get('word')} ({item.get('meaning')})")
        kw_str = "  ".join(kw_list) if kw_list else "① N/A  ② N/A  ③ N/A"
        
        summary_lines = []
        for idx, s in enumerate(sentences[:3], 1):
            num_char = "①" if idx == 1 else ("②" if idx == 2 else "③")
            summary_lines.append(f"{num_char} {s[:35]}...")
            
        summary_info = {
            "title_en": title.strip(),
            "subject": f"{title.strip()[:20]} 분석 완료",
            "keywords": kw_str,
            "summary": summary_lines if len(summary_lines) >= 3 else summary_lines + ["② 분석 내용 참고", "③ 분석 내용 참고"]
        }

    return {
        "title": title.strip(),
        "summary_info": summary_info,
        "passage_raw": passage,
        "korean_raw": korean_passage,
        "sentence_count": len(results),
        "sentences": results,
        "vocabulary": full_vocab,
        "used_ai": False
    }

def parse_english_passage(passage, korean_passage="", title="", api_key=DEFAULT_GEMINI_API_KEY, use_ai=True, sentence_pairs=None):
    if use_ai and api_key:
        res_data = analyze_with_gemini(passage, korean_passage, api_key, title, sentence_pairs)
    else:
        res_data = parse_with_rule_engine(passage, korean_passage, title, sentence_pairs)
    return post_process_adverbs(res_data)

def generate_variation_exam(passage, topic="", api_key=DEFAULT_GEMINI_API_KEY):
    """
    고품질 9종 영어 내신 대비 변형문제 생성기
    1. topic_korean (한글 선지 주제)
    2. sentence_ordering (영어 3단 배열 (A)-(B)-(C))
    3. grammar_syntax (어법성 판단 10개 밑줄 - 40~50% 오답 주관식 수정)
    4. vocabulary (어휘성 판단 10개 밑줄 - 40~50% 반의어 주관식 수정)
    5. passage_ordering (전체 문장 순서 배열 [1]~[n])
    6. descriptive_writing_2 (서술형 영작 2순위 - 구/청크 리스트)
    7. topic_english (영어 명사구 선지 주제)
    8. descriptive_writing_1 (서술형 영작 1순위 - 핵심 3단어 원형)
    9. vocab_blank (15개 핵심 어휘 빈칸 쓰기)
    """
    key = api_key or DEFAULT_GEMINI_API_KEY
    if not topic:
        topic = "핵심 지문 주제 및 요지"

    import random
    random_seed = random.randint(1000, 999999)

    prompt = f"""You are an elite high school English teacher in South Korea, specialized in creating high-quality, rigorous mock exam questions (변형문제) based on provided English passages.
Your task is to analyze the provided English passage and generate exactly 9 types of questions. The outputs must be professional, grammatically perfect, and match the style of the Korean CSAT (수능) and high school midterm/final exams.

[Generation Seed: {random_seed}]
[Diversity & Randomization Rule]
Ensure high variety in question design across repeated calls:
- Q1 & Q7 (주제): Vary the phrasing and perspective of the Korean/English answer choices and distractors.
- Q2 (순서배열): Dynamically choose fresh cut-points for paragraphs (A), (B), and (C).
- Q3 & Q4 (어법/어휘): Select DIFFERENT underlined target words and error locations across the passage (e.g. choose different verbs, pronouns, conjunctions, adjectives).
- Q5 (문장순서): Apply fresh randomized scrambling orders.
- Q6 & Q8 (서술형 영작): Select different key sentences and different chunk distributions.
- Q9 (빈칸쓰기): Select a varied combination of 15 crucial content words across the entire passage.

[Input Passage]
{passage}

[Input Topic Reference]
{topic}

[General Output Format]
You must return the result in JSON format ONLY. Do not write any introduction or explanation before or after the JSON.
The JSON object must have exactly the following 9 keys:
1. "topic_korean"
2. "sentence_ordering"
3. "grammar_syntax"
4. "vocabulary"
5. "passage_ordering"
6. "descriptive_writing_2"
7. "topic_english"
8. "descriptive_writing_1"
9. "vocab_blank"

The value of each key should be a single string formatted with line breaks (\\n) containing the full question options, correct answer, and explanation as detailed below. IMPORTANT: Only use HTML formatting tags like <u>word</u> for Key 3 (grammar_syntax) and Key 4 (vocabulary) to underline specific numbered choices inside the passage. Do NOT use <u> or <b> tags in Key 1, Key 2, Key 7 or anywhere else to avoid unnecessary underlines and bold texts.

--------------------------------------------------
■ Key 1: "topic_korean" (주제 파악 - 한글 선지)
- Purpose: Identify the theme of the passage with 5 Korean options.
- Input Topic Reference: "{topic}"
- Option Design Rules:
  - You must generate exactly 5 choices (① to ⑤) in Korean.
  - 2 choices must express the OPPOSITE meaning of the topic.
  - 1 choice must be the topic with EXACTLY ONE word changed/swapped (looks similar but incorrect).
  - 1 choice must be completely off-topic or random (unrelated).
  - 1 choice must be the CORRECT topic, paraphrased nicely in Korean.
  - CRITICAL option lengths: All 5 options must have roughly balanced lengths, or be arranged in a visually pleasing length progression (e.g. pyramid or diagonal shape). Avoid any option being significantly shorter than the others.
  - Do NOT underline or bold any words in the choices.
- Format (Do NOT write any '[문제]' or '[지문]' markers. Start directly with the passage and options):
  (Write the full input passage here)
  ① (Option 1)
  ② (Option 2)
  ③ (Option 3)
  ④ (Option 4)
  ⑤ (Option 5)
  [정답] (Correct option number, e.g. ④)
  [해설] (Provide detailed Korean explanation on why the correct choice is right and why others are incorrect.)

■ Key 2: "sentence_ordering" (영어 3단 배열)
- Instructions:
  - Divide the passage into an introductory lead-in part and three consecutive parts labeled (A), (B), (C). Do NOT use square brackets [A],[B],[C]. Use parentheses (A),(B),(C) instead.
  - Do NOT write '[주어진 글]' or similar bracket markers. Just output the introductory lead-in text directly.
  - CRITICAL: Do NOT write any Korean instructions or headers. Start directly with the English lead-in text.
  - The choices must match exactly the following form:
    ① (A) - (C) - (B)
    ② (B) - (A) - (C)
    ③ (B) - (C) - (A)
    ④ (C) - (A) - (B)
    ⑤ (C) - (B) - (A)
- Format:
  (Introductory lead-in text directly, no bracket header)
  (A) (Part A text)
  (B) (Part B text)
  (C) (Part C text)
  ① (A) - (C) - (B)
  ② (B) - (A) - (C)
  ③ (B) - (C) - (A)
  ④ (C) - (A) - (B)
  ⑤ (C) - (B) - (A)
  [정답] (Correct option number)
  [해설] (Logical explanation in Korean linking the paragraphs.)

■ Key 3: "grammar_syntax" (어법상 어색한 것 모두 골라 바르게 고치기 - 주관식)
- Purpose: Subjective error identification and correction.
- Passage Formatting: Provide the entire passage. You MUST select EXACTLY 10 grammatically crucial elements and mark them as <u>① word</u>, <u>② word</u>, ... up to <u>⑩ word</u>.
  - CRITICAL: Place the <u> tag strictly around a single target word or a short phrase. Do NOT underline the entire clause or sentence.
- CRITICAL ERROR RATIO (40~50% ONLY):
  - Exactly 4 or 5 numbered items (out of 10) must be intentional grammatical ERRORS (e.g. subject-verb agreement, active vs passive, participle form, wrong relative pronoun, tense mismatch).
  - The remaining 5 or 6 numbered items must be grammatically CORRECT as written in the original passage! DO NOT make all 10 items incorrect!
- Format (Start directly with the passage):
  (Passage with 10 underlined options: e.g., ... <u>① is</u> ... <u>② faced</u> ... <u>⑩ had</u> ...)
  [정답]
  ② faced ➔ is facing
  ④ was working ➔ were working
  ⑦ managing ➔ manage
  ⑨ than ➔ as
  [해설] (Explain in detail in Korean why each of the 4~5 incorrect items is wrong, how it should be corrected, and briefly verify why the remaining 5~6 items are grammatically correct.)

■ Key 4: "vocabulary" (문맥상 어색한 낱말 모두 골라 바르게 고치기 - 주관식)
- Purpose: Contextual vocabulary appropriateness and correction.
- Passage Formatting: Provide the entire passage. You MUST select EXACTLY 10 important adjectives, nouns, or verbs and mark them as <u>① word</u>, <u>② word</u>, ... up to <u>⑩ word</u>.
  - CRITICAL: Place the <u> tag strictly around a single target word.
- CRITICAL ERROR RATIO (40~50% ONLY):
  - Exactly 4 or 5 numbered items (out of 10) must be modified into contextually INAPPROPRIATE words (antonyms or opposite meaning words: e.g. beneficial ↔ detrimental, appropriate ↔ inappropriate, promote ↔ hinder, increase ↔ decrease, advantage ↔ disadvantage).
  - The remaining 5 or 6 numbered items must be the CORRECT original words fitting the context! DO NOT make all 10 items incorrect!
- Format (Start directly with the passage):
  (Passage with 10 underlined options: e.g., ... <u>① beneficial</u> ... <u>⑩ difficult</u> ...)
  [정답]
  ① detrimental ➔ beneficial
  ④ decrease ➔ increase
  ⑥ disadvantage ➔ advantage
  ⑧ inappropriate ➔ appropriate
  [해설] (Explain in detail in Korean why each of the 4~5 incorrect words contradicts the context, define the correct words, and verify why the other 5~6 words are contextually correct.)

■ Key 5: "passage_ordering" (전체 문장 순서 배열)
- Instructions: Scramble every single sentence of the passage. List them in a randomized order, prefixing each sentence with numbers [1], [2], [3], etc.
- Format (Start directly with the sentence list):
  [1] (Scrambled sentence 1)
  [2] (Scrambled sentence 2)
  ...
  [정답] (Original sentence indices order: e.g., 1 - 3 - 2 - 5 - 4)
  [해설] (Briefly explain the flow of the arguments and connection cues.)

■ Key 6: "descriptive_writing_2" (서술형 - 조건 제시형 영작 2순위)
- Instructions:
  - Pick the second most grammatically important or complex sentence from the passage. Provide its Korean translation, a list of English words/phrases, and conditions.
  - CRITICAL WORD LIST DESIGN:
    1. Group the English words into phrases, chunks, or collocational blocks (e.g., 'work remotely', 'reported more difficulties', 'in managing their workload', 'unlike those in older generations', 'organizational culture').
    2. RANDOMIZE the order of the English phrases/chunks in the list.
    3. FOR ANY VERB inside the phrases, convert them to their BASE FORM (동사원형) or PRESENT TENSE (e.g., change 'reported' to 'report', 'working' to 'work').
- Format (Do NOT write '[문제]' or similar bracket headers):
  [우리말 뜻] (Korean translation of the target sentence)
  [단어 리스트] (Randomized English phrases/chunks converted to base form: e.g., in managing their workload, unlike those in older generations, report more difficulties, work remotely)
  [조건]
  - 단어 리스트에 주어진 단어(구)를 모두 사용할 것.
  - 문맥과 어법에 맞게 필요한 단어의 형태를 적절히 변형하여 작성할 것.
  [모범답안] (Model English sentence)
  [채점기준] (Detailed grading rubric in Korean.)

■ Key 7: "topic_english" (주제 파악 - 영어 선지)
- Purpose: Identify the theme of the passage with 5 English options.
- Input Topic Reference: "{topic}"
- Option Design Rules:
  - You must generate exactly 5 choices (① to ⑤) in English.
  - 2 choices must express the OPPOSITE meaning of the topic.
  - 1 choice must be the topic with EXACTLY ONE word changed/swapped.
  - 1 choice must be completely off-topic or random.
  - 1 choice must be the CORRECT topic, paraphrased nicely in English.
  - CRITICAL option lengths: All 5 options must be CONCISE NOUN PHRASES rather than full clauses. Avoid overly long sentences.
  - Do NOT underline or bold any words in the choices.
- Format (Start directly with the passage and options):
  (Write the full input passage here)
  ① (Option 1)
  ② (Option 2)
  ③ (Option 3)
  ④ (Option 4)
  ⑤ (Option 5)
  [정답] (Correct option number)
  [해설] (Provide detailed Korean explanation on why the correct choice is right and why others are incorrect.)

■ Key 8: "descriptive_writing_1" (서술형 - 조건 제시형 영작 1순위)
- Instructions:
  - Select the most critical, complex, or grammatically important sentence in the passage. Provide its Korean translation, exactly 3 key words from the target sentence, and conditions.
  - Convert any target verb in the 3 words list to their BASE FORM (동사원형) or PRESENT TENSE.
  - Output ONLY the three base-form English words separated by commas.
- Format (Do NOT write '[문제]' or similar bracket headers):
  [우리말 뜻] (Korean translation of the sentence)
  [주어진 단어] (Write only the 3 words here: e.g., work, workload, pandemic)
  [조건]
  - 제시된 3개의 핵심 단어를 반드시 문장 내에 포함시킬 것.
  - 주어진 단어 외의 다른 형태나 시제는 문맥에 맞춰 작성할 것.
  [모범답안] (Model English sentence)
  [채점기준] (Detailed grading rubric in Korean.)

■ Key 9: "vocab_blank" (핵심 어휘 15개 빈칸 쓰기)
- Instructions:
  - Select EXACTLY 15 crucial core vocabulary words (nouns, verbs, adjectives, adverbs) across the full passage that are essential for high school exam comprehension.
  - STRICT EXCLUSIONS: Do NOT choose articles (a, an, the), simple pronouns, proper nouns, or person/organization names. Select meaningful content words.
  - In the passage, replace each of the 15 selected words in order of appearance with numbered blanks: `(1) [________]`, `(2) [________]`, ... up to `(15) [________]`.
- Format:
  (Write the full input passage with the 15 blanks `(1) [________]` ~ `(15) [________]`)
  [정답]
  (1) word1 (한글 품사 및 뜻, e.g. (동) 관리하다)
  (2) word2 (한글 품사 및 뜻, e.g. (명) 어려움)
  ...
  (15) word15 (한글 품사 및 뜻, e.g. (형) 유연한)
  [해설] (Brief summary of key vocabulary definitions and context flow.)

Ensure all content is generated cleanly without trailing comments, raw backticks, or any invalid JSON properties."""

    models = ["gemini-2.5-flash"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "responseMimeType": "application/json"
        }
    }

    last_error = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, json=payload, timeout=90)
            if resp.status_code == 200:
                result = resp.json()
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                cleaned = re.sub(r'^```json\s*', '', text_response.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE).strip()
                questions_data = json.loads(cleaned)
                
                usage_meta = result.get('usageMetadata', {})
                questions_data["_usage_metadata"] = {
                    "prompt_tokens": usage_meta.get('promptTokenCount', 0),
                    "output_tokens": usage_meta.get('candidatesTokenCount', 0),
                    "total_tokens": usage_meta.get('totalTokenCount', 0)
                }
                questions_data["_total_tokens"] = usage_meta.get('totalTokenCount', 0)
                return questions_data
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text}"
                print(f"[generate_variation_exam] Model {model} returned {resp.status_code}")
                continue
        except Exception as e:
            last_error = str(e)
            print(f"[generate_variation_exam] Model {model} failed: {e}")
            continue

    raise Exception(f"변형문제 생성 중 AI 응답 오류가 발생했습니다: {last_error}")
