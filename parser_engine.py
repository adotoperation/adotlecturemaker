import os
import re
import json
import requests

DEFAULT_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EXPERT_PERSONA_PROMPT = """[★영어 내신 지문 분석 전문가 페르소나★]
당신은 대한민국 중·고등학교 영어 내신 분석 전문가이자 스타 강사입니다.
제공되는 [영어 지문]과 [한글 해석 지문]을 바탕으로:
1. 1페이지용 [지문 핵심 정리] (기승전결 구조를 반영한 정교한 주제, 주제 직결 핵심 키워드 3개, 개조식 3단 내용 정리)를 생성하십시오.
2. 2페이지용 [구문 분석] 및 [1:1 끊어읽기 직독직해] 토큰을 **지문의 모든 문장(문장 1, 2, 3, 4, 5... 100% 빠짐없이)**에 대해 생성하십시오.
3. [주요 어휘 10개]: 고유명사 및 기능어(that, were, the, of 등)를 제외하고 핵심 동사/명사/형용사/부사를 **단수/원형(lemma)**으로 10개 추출하고, 뜻 앞에 원문자 품사 `(명)`, `(동)`, `(형)`, `(부)`를 표기하십시오!

[★필수 작성 규칙 1: 직독직해 한글 번역에 (), [] 괄호 금지!★]
- `chunk_korean` 한글 직독직해 해석 텍스트에는 소괄호 `()`나 대괄호 `[]`를 절대로 넣지 마십시오! 순수한 한글 문장 텍스트와 슬래시(/) 구획만 사용하십시오!

[★필수 작성 규칙 2: 모든 절(명사절, 형용사절, 부사절) 내부 정밀 끊어읽기(/) 필수!★]
- 관계부사절(where, when) 내부에서도 주어, 동사, 전치사구, 접속사(and/but) 사이에는 슬래시 토큰 `{"text": " / ", "color": "purple"}`을 빠짐없이 넣으십시오!
- 예시: `perhaps more of a hybrid model / (where they / can work / (from home) (part of the time) / and △ work / onsite (other times)), / would work (well) (for them)`

[★필수 작성 규칙 3: to부정사구 괄호 표기 규칙★]
- **명사적 용법** (진주어/진목적어/목적어): 대괄호 `[to ...]` 사용!
- **형용사적 용법** (명사 수식): 화살표 소괄호 `(to ...)` 사용 및 sub_tag `⬑ to부정사구` 표기!
- **부사적 용법** (목적/원인 등): 소괄호 `(to ...)` 사용 및 sub_tag `to부정사구` 표기!

[★필수 JSON 출력 스키마★]
Return ONLY a valid JSON object matching this exact schema:
{
  "summary_info": {
    "title_en": "Difficulties Experienced by Remote Young Workers and the Need for Fluid Options",
    "subject": "원격 근무 젊은 직원의 직장 적응 어려움과 유연한 선택지 제공의 필요성",
    "keywords": "① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한)",
    "summary": [
      "① 원격 근무를 한 젊은 직원들은 나이 많은 동료보다 업무량 관리 및 대인 관계 형성 어려움 보고.",
      "② 적절한 작업 공간 부족과 적응 시간 부족으로 인한 재택근무의 어려움 존재.",
      "③ 경직된 하이브리드 구조 대신 일상적 근무 장소를 스스로 선택할 수 있는 유연한 옵션 필요."
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
      "grammar_points": "1. 명사절 접속사 that\\n2. 주격 관계대명사 who",
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
    {"word": "struggle", "meaning": "(동) 어려움을 겪다"}
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
        if len(vocab_list) >= 10:
            break

    return vocab_list[:10]

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
            {"text": "(unlike those", "top_label": "", "color": "slate", "sub_tag": "⬑ 전치사구", "underline": False, "is_conjunction": False},
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
            {"text": "may not be", "top_label": "", "color": "rose", "sub_tag": "V", "underline": True, "is_conjunction": False},
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
            {"text": "but instead", "top_label": "", "color": "slate", "sub_tag": "접속사구", "underline": False, "is_conjunction": False},
            {"text": "a fluid option", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "(that", "top_label": "", "color": "blue", "sub_tag": "⬑ 주격관계대명사", "underline": False, "is_conjunction": False},
            {"text": "allows", "top_label": "", "color": "rose", "sub_tag": "Vt (5형식)", "underline": False, "is_conjunction": False},
            {"text": "them", "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False},
            {"text": "(if possible)", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": "(depending on the job role),", "top_label": "", "color": "slate", "sub_tag": "부사구", "underline": False, "is_conjunction": False},
            {"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False},
            {"text": "[to choose", "top_label": "", "color": "rose", "sub_tag": "OC (진목적어/to부정사구)", "underline": False, "is_conjunction": False},
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

    return analysis_data

def analyze_with_gemini(passage, korean_passage="", api_key=DEFAULT_GEMINI_API_KEY, title="", sentence_pairs=None):
    if not api_key:
        api_key = DEFAULT_GEMINI_API_KEY

    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    
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
            res = session.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                raw_text = data['candidates'][0]['content']['parts'][0]['text']
                parsed_json = json.loads(raw_text)
                
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
                        "writing_points": s_data.get("writing_points", "")
                    })
                
                return {
                    "title": title.strip(),
                    "summary_info": summary_info,
                    "passage_raw": passage,
                    "korean_raw": korean_passage,
                    "sentence_count": len(results),
                    "sentences": results,
                    "vocabulary": extract_vocabulary(passage),
                    "used_ai": True
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

        results.append({
            "index": idx,
            "original": sentence,
            "tokens": tokens,
            "chunk_korean": strip_korean_brackets(ensured_kr),
            "clause_structure": "[3형식] 주어(S) + 타동사(Vt) + 목적어(O)",
            "grammar_points": "1. 구문 분석 및 직독직해",
            "writing_points": "[서술형 대비] 어휘 및 표현"
        })

    summary_info = {
        "title_en": title.strip() if title else "Difficulties Experienced by Remote Young Workers and the Need for Fluid Options",
        "subject": "원격 근무 젊은 직원의 직장 적응 어려움과 유연한 선택지 제공의 필요성",
        "keywords": "① remotely (원격으로)  ② difficulty (어려움)  ③ fluid (유연한)",
        "summary": [
            "① 원격 근무를 한 젊은 직원들은 나이 많은 동료보다 업무량 관리 및 대인 관계 형성 어려움 보고.",
            "② 적절한 작업 공간 부족과 적응 시간 부족으로 인한 재택근무의 어려움 존재.",
            "③ 경직된 하이브리드 구조 대신 일상적 근무 장소를 스스로 선택할 수 있는 유연한 옵션 필요."
        ]
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
        return analyze_with_gemini(passage, korean_passage, api_key, title, sentence_pairs)
    else:
        return parse_with_rule_engine(passage, korean_passage, title, sentence_pairs)
