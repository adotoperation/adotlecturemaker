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

            # Strip any accidental △ or ▲ from text, top_label, sub_tag
            text = re.sub(r'^[△▲\s]+|[△▲]+$', '', text).strip()
            t['text'] = text
            if t.get('top_label') in ['△', '▲']:
                t['top_label'] = '△'
            if t.get('sub_tag') in ['△', '▲']:
                t['sub_tag'] = ''

            words = text.split()
            if len(words) > 1:
                first_clean = re.sub(r'^[\[\(]+|[\]\),]+$', '', words[0]).strip().lower()
                is_conj_token = t.get('is_conjunction', False) or (first_clean in CONJUNCTIONS_LIST and ('접속' in t.get('sub_tag', '') or first_clean in ['and', 'or', 'but', 'so', 'yet', 'however', 'therefore', 'moreover', 'furthermore', 'thus', 'either', 'neither']))

                if is_conj_token and first_clean in CONJUNCTIONS_LIST:
                    conj_word = words[0]
                    rest_text = " ".join(words[1:])
                    
                    conj_token = {
                        "text": conj_word,
                        "top_label": "△",
                        "color": "slate",
                        "sub_tag": "",
                        "underline": False,
                        "is_conjunction": True
                    }
                    rest_token = {
                        "text": rest_text,
                        "top_label": t.get('top_label', '') if t.get('top_label') != '△' else '',
                        "color": t.get('color', 'slate'),
                        "sub_tag": t.get('sub_tag', '') if '접속' not in t.get('sub_tag', '') else '',
                        "underline": t.get('underline', False),
                        "is_conjunction": False
                    }
                    new_tokens.append(conj_token)
                    new_tokens.append(rest_token)
                    continue

            clean_word = re.sub(r'^[\[\(]+|[\]\),]+$', '', text).strip().lower()
            if clean_word in CONJUNCTIONS_LIST and (t.get('is_conjunction') or '접속' in t.get('sub_tag', '') or clean_word in ['and', 'or', 'but', 'so', 'yet', 'however', 'therefore', 'moreover', 'furthermore', 'thus', 'either', 'neither', 'both']):
                t['is_conjunction'] = True
                t['top_label'] = '△'
                t['sub_tag'] = ''
            else:
                # Strictly remove triangle from as, for, since, because, etc.
                t['is_conjunction'] = False
                if t.get('top_label') == '△':
                    t['top_label'] = ''
                if t.get('sub_tag') in ['접속사', '접속부사']:
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
            t['top_label'] = ""
            sub_tag = t.get('sub_tag', '')
            text = t.get('text', '').strip()
            
            # Check if this token is the main subject
            if sub_tag.startswith('S') or '가주어' in sub_tag:
                found_subject = True
            
            # Prepositional phrases (전명구): Wrap in () and NEVER give arrow ⬑
            prep_starters = ['of', 'in', 'on', 'at', 'with', 'by', 'from', 'for', 'about', 'like', 'through', 'without', 'between', 'under', 'over', 'into', 'onto', 'upon', 'since', 'ever', 'during', 'before', 'after', 'throughout', 'across', 'among', 'along', 'despite', 'unlike']
            clean_word = re.sub(r'^[\[\(]+|[\]\),]+$', '', text).strip().lower()
            first_w = clean_word.split()[0] if clean_word else ""
            is_prep_phrase = (first_w in prep_starters) or ('전치사' in sub_tag) or text.startswith('(')

            if is_prep_phrase:
                t['sub_tag'] = ""
                # Ensure wrapped in ()
                if not text.startswith('(') and not text.startswith('['):
                    if text.endswith(','):
                        t['text'] = f"({text[:-1]}),"
                    elif text.endswith('.'):
                        t['text'] = f"({text[:-1]})."
                    else:
                        t['text'] = f"({text})"
            elif '관계' in sub_tag or (clean_word in ['that', 'which', 'who', 'whom', 'whose', 'where', 'when'] and sub_tag != 'O'):
                # Only true relative clauses get arrow ⬑
                t['sub_tag'] = "⬑"
            elif any(k in sub_tag for k in ['부사구', '부사절', '부사', '분사구문', '분사구']):
                t['sub_tag'] = ""
            elif sub_tag == '목적어절':
                t['sub_tag'] = "O"
            elif '진목적어' in sub_tag:
                t['sub_tag'] = "진목적어"
            elif '의미상' in sub_tag or sub_tag == '의미상 S' or sub_tag == '의미상 주어':
                t['sub_tag'] = "의미상 S"
                t['color'] = 'blue'
                t['underline'] = True
            elif '⬑' in sub_tag:
                t['sub_tag'] = ""

            # Strict syntax correction: Adverbs (-ly, time adverbs) must NEVER be O or S or Vt!
            common_adverbs = ['often', 'always', 'never', 'already', 'still', 'even', 'also', 'just', 'only', 'ever', 'well', 'far', 'so', 'too', 'very', 'almost', 'much', 'more', 'together', 'apart', 'ahead', 'away', 'back', 'down', 'up', 'out', 'in', 'off', 'over']
            is_pure_adverb = (clean_word.endswith('ly') and clean_word not in ['family', 'likely', 'lonely', 'lovely', 'friendly', 'early', 'ugly', 'silly', 'holy', 'daily', 'weekly', 'monthly', 'yearly']) or clean_word in common_adverbs
            if is_pure_adverb and not is_prep_phrase:
                if t.get('sub_tag') in ['O', 'S', 'Vt', 'Vi', 'V', 'C', 'OC', 'SC', 'DO', 'IO']:
                    t['sub_tag'] = ""
                    t['color'] = 'slate'
                    t['underline'] = False

            # Linking verbs (have been, is, are, was, were, become, remain, seem)
            if clean_word in ['have been', 'has been', 'had been', 'been', 'is', 'are', 'was', 'were', 'become', 'became', 'remained', 'remain', 'seemed', 'seem', 'appeared', 'appear']:
                t['sub_tag'] = 'Vi'
                t['color'] = 'rose'
                t['underline'] = True

            # Predicate Adjectives/Complements (SC) following linking verbs
            if t.get('sub_tag') in ['O', 'Vt', 'Vi'] and clean_word in ['related', 'different', 'important', 'crucial', 'essential', 'common', 'rare', 'necessary', 'likely', 'possible', 'difficult', 'clear', 'critical', 'effective', 'useful', 'similar']:
                t['sub_tag'] = 'SC'
                t['color'] = 'indigo'
                t['underline'] = False

        # Auto-detect semantic subject of gerund (e.g. toddlers falling over)
        for i, t in enumerate(tokens):
            clean_word = re.sub(r'^[\[\(]+|[\]\),]+$', '', t.get('text', '')).strip().lower()
            sub_tag = t.get('sub_tag', '')
            if '의미상' in sub_tag or sub_tag == '의미상 S' or sub_tag == '의미상 주어':
                t['sub_tag'] = '의미상 S'
                t['color'] = 'blue'
                t['underline'] = True
            elif i + 1 < len(tokens):
                next_t = tokens[i + 1]
                next_word = re.sub(r'^[\[\(]+|[\]\),]+$', '', next_t.get('text', '')).strip().lower()
                if (clean_word in ['toddlers', 'toddler', 'infants', 'infant', 'children', 'child', 'adults', 'adult'] or clean_word.startswith('for ')) and (next_word.endswith('ing') or next_word.startswith('to ') or next_word in ['falling', 'tripping', 'slipping']):
                    if not sub_tag or sub_tag == 'S' or '의미상' in sub_tag or sub_tag == '':
                        t['sub_tag'] = '의미상 S'
                        t['color'] = 'blue'
                        t['underline'] = True

        # Auto-detect parallel subjects (e.g. preservation and conservation)
        for i, t in enumerate(tokens):
            if t.get('is_conjunction'):
                prev_idx = i - 1
                while prev_idx >= 0 and tokens[prev_idx].get('text') == ' / ':
                    prev_idx -= 1
                next_idx = i + 1
                while next_idx < len(tokens) and tokens[next_idx].get('text') == ' / ':
                    next_idx += 1
                
                if prev_idx >= 0 and next_idx < len(tokens):
                    prev_t = tokens[prev_idx]
                    next_t = tokens[next_idx]
                    if prev_t.get('sub_tag') == 'S' and not next_t.get('sub_tag') and not next_t.get('text', '').startswith('('):
                        next_clean = re.sub(r'^[\[\(]+|[\]\),]+$', '', next_t.get('text', '')).strip().lower()
                        if not any(k in next_clean for k in ['have', 'has', 'is', 'are', 'was', 'were', 'see', 'load']):
                            next_t['sub_tag'] = 'S'
                            next_t['color'] = 'blue'
                            next_t['underline'] = True

        # Sanitize grammar_points (enforce 접속부사 over 삽입어 and strip markdown stars/backticks)
        gp = s.get('grammar_points', '')
        if isinstance(gp, list):
            gp = "\n".join(str(item) for item in gp)
        if gp and isinstance(gp, str):
            gp = re.sub(r'삽입어(?:구)?\s*(however|therefore|moreover|furthermore|thus)', r'접속부사 \1', gp, flags=re.IGNORECASE)
            gp = re.sub(r'삽입어(?:\s*:\s*)', r'접속부사: ', gp)
            gp = re.sub(r'[\*`]+', '', gp)
            s['grammar_points'] = gp
        elif not gp:
            s['grammar_points'] = ""

        # Sanitize clause_structure
        cs = s.get('clause_structure', '')
        if isinstance(cs, list):
            cs = "\n".join(str(item) for item in cs)
        s['clause_structure'] = str(cs) if cs else ""

        # Sanitize chunk_korean
        ck = s.get('chunk_korean', '')
        if isinstance(ck, list):
            ck = " / ".join(str(item) for item in ck)
        s['chunk_korean'] = strip_korean_brackets(str(ck)) if ck else ""

    # Sanitize summary_info keywords to ALWAYS be '① english_word (한글뜻)  ② english_word (한글뜻)  ③ english_word (한글뜻)'
    s_info = analysis_data.get('summary_info')
    if isinstance(s_info, dict):
        raw_kw = str(s_info.get('keywords', '')).strip()
        vocab = analysis_data.get('vocabulary', [])
        has_english = bool(re.search(r'[a-zA-Z]{3,}', raw_kw))
        if (not has_english or not raw_kw) and vocab:
            kw_parts = []
            for idx, item in enumerate(vocab[:3]):
                num = '①' if idx == 0 else ('②' if idx == 1 else '③')
                w = item.get('word', '')
                m = re.sub(r'^\([가-힣\w\s]+\)\s*', '', item.get('meaning', '')).strip()
                kw_parts.append(f"{num} {w} ({m})")
            s_info['keywords'] = "  ".join(kw_parts)

    return post_process_coordinating_conjunction_numbering(analysis_data)

def post_process_coordinating_conjunction_numbering(analysis_data):
    """
    When sentence elements are directly connected in parallel by coordinating conjunctions (and, or, nor),
    and share the same syntactic role, numbers them as S1, S2 / V1, V2 / Vt1, Vt2 / Vi1, Vi2 / O1, O2 / SC1, SC2 / OC1, OC2.
    NEVER numbers main clause and subordinate clause elements together!
    """
    if not analysis_data or 'sentences' not in analysis_data:
        return analysis_data

    for s in analysis_data.get('sentences', []):
        tokens = s.get('tokens', [])

        # Find indexes of coordinating conjunctions (and, or, nor)
        conj_indices = [
            i for i, t in enumerate(tokens)
            if t.get('is_conjunction') or t.get('text', '').strip().lower() in ['and', 'or', 'nor']
        ]

        for c_idx in conj_indices:
            # Look at candidate before conjunction (left side) and after conjunction (right side)
            left_tokens = [t for t in tokens[:c_idx] if t.get('text', '').strip() not in ['/', '//']]
            right_tokens = [t for t in tokens[c_idx+1:] if t.get('text', '').strip() not in ['/', '//']]

            if left_tokens and right_tokens:
                # Check for parallel verbals or verbs or objects connected across the conjunction
                for cat in ['Vt', 'Vi', 'V', 'O', 'SC', 'OC', 'S']:
                    left_match = next((t for t in reversed(left_tokens[-4:]) if t.get('sub_tag') == cat or t.get('top_label') == cat), None)
                    right_match = next((t for t in right_tokens[:4] if t.get('sub_tag') == cat or t.get('top_label') == cat), None)

                    if left_match and right_match and left_match is not right_match:
                        # Do not number main subject vs subordinate subject
                        if cat == 'S' and (left_match.get('underline') != right_match.get('underline')):
                            continue
                        
                        if left_match.get('sub_tag') == cat: left_match['sub_tag'] = f"{cat}1"
                        if left_match.get('top_label') == cat: left_match['top_label'] = f"{cat}1"
                        if right_match.get('sub_tag') == cat: right_match['sub_tag'] = f"{cat}2"
                        if right_match.get('top_label') == cat: right_match['top_label'] = f"{cat}2"

        # Verbal syntax tagging enhancement
        # E.g. [to maintain (sub_tag: O, top_label: Vt) / an object (top_label: O1) / or (△) / system (top_label: O2)]
        for i, t in enumerate(tokens):
            txt = t.get('text', '').strip()
            sub = t.get('sub_tag', '')
            top = t.get('top_label', '')
            
            clean_txt = re.sub(r'^[\[\(]+|[\]\),]+$', '', txt).strip().lower()
            is_verbal_head = (
                (clean_txt.startswith('to ') or clean_txt.endswith('ing') or clean_txt.endswith('ed') or
                 'to부정사' in sub or '분사' in sub or '동명사' in sub) and
                not t.get('underline') and not sub.startswith('V') and not sub.startswith('S') and not t.get('is_conjunction')
            )

            if is_verbal_head:
                if not top:
                    # Determine if transitive or intransitive
                    next_tok = tokens[i+1] if i+1 < len(tokens) else None
                    if next_tok and next_tok.get('text', '').strip() not in ['/', '//'] and not next_tok.get('sub_tag', '').startswith('V'):
                        t['top_label'] = 'Vt'
                    else:
                        t['top_label'] = 'Vi'

                # If this verbal is inside a bracketed noun phrase or has sub_tag 'O', ensure its object tokens have top_label: 'O'
                if sub == 'O' or txt.startswith('['):
                    j = i + 1
                    while j < len(tokens) and j < i + 6:
                        tok = tokens[j]
                        t_txt = tok.get('text', '').strip()
                        if t_txt in ['/', '//'] or tok.get('is_conjunction'):
                            j += 1
                            continue
                        if tok.get('underline') or tok.get('sub_tag', '').startswith('V') or t_txt.startswith('('):
                            break
                        if not tok.get('top_label') and not tok.get('sub_tag'):
                            tok['top_label'] = 'O'
                            if not tok.get('color') or tok.get('color') == 'slate':
                                tok['color'] = 'emerald'
                        j += 1

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
- **소괄호 `(...)`**: 수식어구, 부사구, 부사절, 전치사구, 관계사절, 분사구문, 형용사적/부사적 수식어구

[★필수 작성 규칙 4: 표준 문장성분 기호 체계 (sub_tag & top_label) 및 등위접속사 넘버링 준수★]
1. **주어**: `sub_tag: "S"`, `color: "blue"`, 주절인 경우 `underline: true`
2. **자동사/타동사**: `sub_tag: "Vi"` / `"Vt"`, `color: "rose"`, 주절인 경우 `underline: true`
3. **보어/목적어**: `sub_tag: "SC"`/`"OC"` (`color: "purple"`), `sub_tag: "O"`/`"IO"`/`"DO"` (`color: "emerald"`). (목적어절은 '목적어절' 대신 오직 `"O"`로 표기합니다!)
4. **[등위접속사 병렬구조 넘버링 규칙]**: 등위접속사(and, but, or, so 등)로 주어, 동사, 목적어, 보어가 2개 이상 연결될 경우, 반드시 `S1, S2`, `V1, V2` (`Vt1, Vt2`, `Vi1, Vi2`), `O1, O2`, `SC1, SC2`, `OC1, OC2` 와 같이 숫자를 붙여 작성하십시오!
5. **[준동사구 (명사구/형용사구/부사구) 괄호, 화살표, 상단 문장형식(top_label) 정밀 규칙]**:
   - **명사구 준동사구 (주어, 목적어, 보어)**: 대괄호 `[ ... ]` 로 묶고, 대괄호 시작 `[` 밑(`sub_tag`)에 `O`(또는 `S`, `C`, `진목적어`) 표기. 준동사 단어 위에는 `top_label: "Vt"` (또는 `"Vi"`), 목적어/보어 위에는 `top_label: "O"` (병렬 시 `top_label: "O1"`, `"O2"`) 표기. (예: `[to maintain` (하단: `O`, 상단: `Vt`) `/ an object` (상단: `O1`) `/ or` (세모) `/ system insofar]` (상단: `O2`))
   - **형용사구 준동사구 (명사 후치수식)**: 소괄호 `( ... )` 로 묶고, 소괄호 `(` 밑에 수식 화살표 `⬑` 표기. 준동사 단어 위에는 `top_label: "Vt"`/`"Vi"`, 목적어 위에는 `top_label: "O"` 표기. (예: `spaces (designated` (하단: `⬑`, 상단: `Vt`) `/ for working remotely)`)
   - **부사구 준동사구 (목적, 원인, 결과, 분사구문 등)**: 소괄호 `( ... )` 로 묶고, 화살표 없이 깔끔한 소괄호 유지. 준동사 단어 위에는 `top_label: "Vt"`/`"Vi"`, 목적어 위에는 `top_label: "O"` 표기. (예: `(to protect` (상단: `Vt`) `/ their crops` (상단: `O`))`)

[★필수 작성 규칙 5: 세모(△) 기호 적용 대상 규정 (접속부사, 등위접속사, 상관접속사만 허용!)★]
- **세모(△, is_conjunction: true)가 적용되는 단어는 오직 아래 3가지 범주뿐입니다**:
  1. **등위접속사**: and, but, or, so, yet, nor
  2. **상관접속사**: both, either, neither 등
  3. **접속부사**: however, therefore, furthermore, moreover, thus, consequently, nonetheless, nevertheless, instead, meanwhile 등
- **[주의! 절대 세모 금지]**: 전치사 및 종속접속사(`as`, `for`, `because`, `since`, `while`, `although`, `if`, `that`, `when` 등)에는 절대로 `is_conjunction: true`를 주지 마십시오! (is_conjunction: false 유지)
- 세모 대상 접속사는 반드시 뒤에 오는 단어와 분리하여 **독립된 1개의 단어 토큰(`{"text": "or", "is_conjunction": true, ...}`)으로만 작성**하십시오!

[★필수 작성 규칙 6: 수식어구 화살표(⬑) 및 문법 명칭 제거 규칙★]
- **문장 전체 수식 부사구 (문두 전치사구, 시간/장소 부사구 등)**:
  - 명사를 수식하는 것이 아니므로 화살표를 붙이지 않고 `sub_tag: ""` 로 작성합니다.
- **오직 바로 앞의 명사를 직접 뒤에서 수식하는 형용사구/형용사절일 때만**:
  - '전치사구', '주격관계대명사', '부사구' 등의 한글 문법 텍스트를 절대로 붙이지 말고, **오직 화살표 기호 `sub_tag: "⬑"` 만 단독으로 표기**하십시오!

[★필수 작성 규칙 7: 밑줄(underline: true) 적용 기준 규칙★]
- **주절의 주어 및 주절의 서술어(동사)인 경우에만** `underline: true`를 설정하여 밑줄을 쳐주십시오!

[★필수 작성 규칙 8: 문법 용어 규정 (however, therefore 등은 '삽입어'가 아닌 '접속부사'로 표기)★]
- `however`, `therefore`, `furthermore`, `moreover`, `thus` 등은 grammar_points에서 '접속부사'로 표기하십시오.

[★필수 작성 규칙 9: 지문 핵심정리 기반 2D 지브리풍 영문 삽화 장면(illustration_scene_en) 작성 규칙★]
- `summary_info`의 `illustration_scene_en` 필드에는, 지문의 핵심 맥락과 비유를 2D 정통 지브리 애니메이션 셀화 스타일로 작성하십시오!
- [프론트 스타일 토큰]: `2D traditional animation cel, anime background art, Studio Ghibli aesthetic, Hayao Miyazaki style painting, hand-drawn watercolor and colored pencil on textured paper, delicate ink line art, soft cel shading`
- [네거티브 차단선]: `Strictly NO photorealism, NO photo, NO 3D render, NO CGI, NO live-action, NO glossy gradient, NO text, NO speech bubbles, NO words`
- 따뜻한 골든 아워의 햇살과 지문 주제를 직관적으로 전달하는 정교한 2D 손그림 장면 묘사를 작성하십시오!

[★필수 작성 규칙 10: 직독직해(chunk_korean) 영어 토큰(/)과 100% 1:1 완벽 싱크로 규칙★]
- 영어 토큰에서 슬래시(/)로 끊은 단위 및 순서와 한글 직독직해(chunk_korean)의 슬래시(/) 구획은 완전히 1:1로 일치해야 합니다!
- [예시]:
  - 영어 본문 끊어읽기: `Structural defenses / like thick coats / of wax / on leaves / may prevent`
  - 직독직해(chunk_korean): `구조적 방어기제는 / 두꺼운 층 같은 / 왁스의 / 잎에 / 막을지도 모른다`
- 영어의 끊어읽기 구획마다 정확히 대응되는 한국어 번역 덩어리를 슬래시(/)로 구분하여 순서대로 1:1 매핑하십시오!

[★필수 작성 규칙 11: grammar_points 마크다운 별표(**) 및 백틱(`) 일체 사용 금지★]
- `grammar_points`에는 볼드체 마크다운 `**` 나 코드 백틱(`)을 절대로 쓰지 마십시오!
- (예: `**현재완료**` (X) ➔ `1. 현재완료 (Present Perfect): have evolved는 과거부터 현재까지...` (O))

[★필수 작성 규칙 12: 동명사 및 to부정사의 의미상의 주어 (의미상 S) 표기 규칙★]
- 동명사의 의미상의 주어 (예: `toddlers falling over`에서 `toddlers`, `his doing so`에서 `his`) 또는 to부정사의 의미상의 주어 (예: `for children to learn`에서 `for children`)는 반드시 `sub_tag: "의미상 S"`, `color: "blue"`, `underline: true` 로 분석하여 단어 아래에 '의미상 S' 태그가 표시되도록 하십시오!

[★필수 작성 규칙 13: 부사(-ly) 목적어(O) 오표기 방지 및 연결동사/보어(SC) 규정★]
- `closely`, `greatly`, `severely`, `deeply`, `widely`, `frequently`, `often`, `always` 등 부사는 목적어(O)가 될 수 없으므로 절대로 `sub_tag: "O"`로 표기하지 말고 `sub_tag: ""`, `color: "slate"` 로 작성하십시오!
- `have been`, `is`, `are`, `was`, `were`, `become`, `remain` 등 be동사 및 연결동사는 타동사(Vt)가 아니므로 `Vi`로 표기하고, 뒤따르는 형용사 보어(예: `related`, `different`, `important`)는 목적어(O)가 아닌 주격보어 `sub_tag: "SC"`, `color: "indigo"` 로 작성하십시오!
- 문두의 부사구/시간 전치사구(예: `(Ever since the early Enlightenment,)`)는 소괄호 `(...)`로 감싸고 `sub_tag: ""`, `color: "slate"` 로 작성하십시오!

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
        {"text": "Eurofound)", "top_label": "", "color": "slate", "sub_tag": "", "underline": false, "is_conjunction": false}
      ]
    }
  ]
}
"""

VOCAB_DATABASE = {
    # Biology / Science / Nature / Plants / Defenses
    "plant": "(명) 식물", "plants": "(명) 식물",
    "evolve": "(동) 진화하다, 발전하다", "evolved": "(동) 진화한, 진화된", "evolution": "(명) 진화",
    "defense": "(명) 방어, 방어 기제", "defenses": "(명) 방어 기제", "defend": "(동) 방어하다",
    "diverse": "(형) 다양한", "diversity": "(명) 다양성",
    "genera": "(명) 속(genus의 복수형)", "genus": "(명) (생물 분류상의) 속",
    "tissue": "(명) (생체) 조직", "tissues": "(명) 생체 조직",
    "harsh": "(형) 가혹한, 독한, 거친",
    "compound": "(명) 화합물, 복합체", "compounds": "(명) 화합물",
    "repel": "(동) 물리치다, 쫓아버리다", "repels": "(동) 격퇴하다",
    "insect": "(명) 곤충, 벌레", "insects": "(명) 곤충류",
    "intoxicate": "(동) 중독시키다, 취하게 하다", "intoxicates": "(동) 중독시키다", "toxic": "(형) 유독성의",
    "toxin": "(명) 독소, 유해 물질", "toxins": "(명) 독소",
    "structural": "(형) 구조적인, 구조상의", "structure": "(명) 구조, 체계",
    "coating": "(명) 껍질, 피막, 코팅", "coatings": "(명) 보호 피막",
    "thorn": "(명) 가시", "thorns": "(명) 가시",
    "predator": "(명) 포식자, 천적", "predators": "(명) 포식자들",
    "prey": "(명) 먹이, 사냥감",
    "adaptation": "(명) 적응, 순응", "adapt": "(동) 적응하다",
    "organism": "(명) 유기체, 생물", "organisms": "(명) 생물체",
    "species": "(명) (생물) 종", "specimen": "(명) 표본",
    "chemical": "(명) 화학 물질 (형) 화학의", "chemicals": "(명) 화학 물질",
    "barrier": "(명) 장벽, 방어벽", "barriers": "(명) 방어벽",
    "survival": "(명) 생존", "survive": "(동) 살아남다",
    "mechanism": "(명) 기제, 메커니즘", "mechanisms": "(명) 작용 기제",
    "reproduce": "(동) 번식하다, 재생하다", "reproduction": "(명) 번식",
    "trait": "(명) 특성, 형질", "traits": "(명) 유전 형질",
    "absorb": "(동) 흡수하다", "nutrient": "(명) 영양소", "nutrients": "(명) 영양분",

    # Arts / Culture / Humanities / Social
    "spectacle": "(명) 장관, 화려한 구경거리", "spectacular": "(형) 장관의, 눈부신",
    "instinctive": "(형) 본능적인", "instinct": "(명) 본능",
    "response": "(명) 반응, 응답", "respond": "(동) 반응하다",
    "primarily": "(부) 주로, 근본적으로", "primary": "(형) 주요한, 근본적인",
    "prevailing": "(형) 지배적인, 유행하는", "prevail": "(동) 널리 퍼지다",
    "perception": "(명) 인식, 지각", "perceive": "(동) 인식하다, 지각하다",
    "observer": "(명) 관찰자, 보는 사람", "observers": "(명) 관찰자들",
    "creation": "(명) 창작, 생성", "create": "(동) 창조하다",
    "universal": "(형) 보편적인", "inevitable": "(형) 불가피한, 필연적인",
    "expression": "(명) 표현, 표출", "express": "(동) 표현하다",
    "strategy": "(명) 전략, 방책", "strategies": "(명) 전략들",
    "address": "(동) 다루다, 해결하다 (명) 주소",
    "liken": "(동) 비유하다, 견주다", "likened": "(동) 비유된",
    "literature": "(명) 문학, 문헌", "literary": "(형) 문학의",
    "tradition": "(명) 전통, 관례", "traditions": "(명) 전통 관습",
    "genre": "(명) 장르, 예술 양식", "genres": "(명) 장르들",
    "originality": "(명) 독창성, 신선함", "original": "(형) 독창적인, 원래의",
    "impress": "(동) 감명을 주다, 인상을 남기다", "impression": "(명) 인상, 감명",
    "audience": "(명) 관객, 청중", "audiences": "(명) 관객들",
    "extension": "(명) 확장, 연장", "extend": "(동) 확장하다",
    "blend": "(동) 혼합하다, 조화시키다", "blending": "(동) 조화시키는 것",
    "established": "(형) 확립된, 기성의", "establish": "(동) 확립하다, 설립하다",
    "innovative": "(형) 혁신적인", "innovation": "(명) 혁신",
    "deploy": "(동) 전개하다, 활용하다", "deploying": "(동) 활용하는 것",
    "repertoire": "(명) 레퍼토리, 기량의 범위",
    "convention": "(명) 관습, 관례", "conventions": "(명) 전통적 규범",
    "imitation": "(명) 모방, 흉내", "imitate": "(동) 모방하다",

    # High-Frequency Academic Words
    "difficulty": "(명) 어려움", "difficulties": "(명) 어려움",
    "workload": "(명) 업무량", "colleague": "(명) 동료", "colleagues": "(명) 동료들",
    "career": "(명) 경력, 커리어", "careers": "(명) 직업 경력",
    "pandemic": "(명) 팬데믹, 유행병", "generation": "(명) 세대", "generations": "(명) 세대들",
    "connection": "(명) 관계, 연결", "connections": "(명) 대인 관계",
    "culture": "(명) 문화", "cultural": "(형) 문화적인",
    "job": "(명) 직업, 일자리", "survey": "(명) 조사, 설문",
    "student": "(명) 학생", "graduate": "(명) 졸업생",
    "workspace": "(명) 작업 공간", "distraction": "(명) 주의 산만 요인",
    "model": "(명) 모델, 형태", "week": "(명) 주, 일주일",
    "effort": "(명) 노력", "trust": "(명) 신뢰", "teamwork": "(명) 팀워크",
    "lack": "(명) 부족, 결핍", "option": "(명) 선택권, 옵션",
    "location": "(명) 장소, 위치", "role": "(명) 역할, 직무",
    "element": "(명) 구성 요소", "elements": "(명) 구성 요소들",
    "trigger": "(동) 유발하다, 촉발하다", "frame": "(명) 틀, 구조",
    "mode": "(명) 방식, 양식", "modes": "(명) 방식들",
    "individual": "(형) 개인의 (명) 개인", "community": "(명) 공동체",
    "perspective": "(명) 관점, 시각", "aspect": "(명) 측면, 양상",
    "concept": "(명) 개념", "factor": "(명) 요인, 요소",
    "impact": "(명) 영향, 충격 (동) 영향을 주다", "influence": "(동) 영향을 미치다",
    "resource": "(명) 자원, 재원", "resources": "(명) 자원들",
    "environment": "(명) 환경", "environmental": "(형) 환경의",

    # Additional Common Content Words
    "load": "(동) 싣다, 채우다", "loads": "(동) 채우다", "loaded": "(동) 채워진",
    "stress": "(동) 강조하다 (명) 스트레스", "stresses": "(동) 강조하다",
    "writer": "(명) 작가", "writers": "(명) 작가들",
    "rule": "(명) 규칙, 규범", "rules": "(명) 규칙들",
    "bound": "(형) 얽매인, 구속된 (동) 튀어오르다",
    "sufficient": "(형) 충분한", "sufficiently": "(부) 충분히",
    "show": "(동) 보여주다, 나타내다", "shows": "(동) 보여주다",
    "grain": "(명) 결, 성질, 곡물",
    "festival": "(명) 축제, 페스티벌", "festivals": "(명) 축제들",
    "activity": "(명) 활동, 행사", "activities": "(명) 활동들",
    "anyone": "(명) 누구나, 어떤 사람", "someone": "(명) 어떤 사람",
    "imitation": "(명) 모방, 흉내", "imitate": "(동) 모방하다",

    # Common Verbs
    "find": "(동) 발견하다, 알게 되다", "work": "(동) 일하다, 작용하다",
    "report": "(동) 보고하다, 알리다", "manage": "(동) 관리하다, 다루다",
    "begin": "(동) 시작하다", "embed": "(동) 적응시키다, 깊이 박다",
    "struggle": "(동) 어려움을 겪다", "offer": "(동) 제공하다",
    "require": "(동) 필요로 하다", "allow": "(동) 허용하다, 가능하게 하다",
    "choose": "(동) 선택하다", "designate": "(동) 지정하다",
    "provide": "(동) 제공하다", "indicate": "(동) 나타내다, 가리키다",
    "suggest": "(동) 제안하다, 암시하다", "demonstrate": "(동) 입증하다, 보여주다",
    "enhance": "(동) 향상시키다, 강화하다", "reduce": "(동) 줄이다, 감소시키다",
    "maintain": "(동) 유지하다", "generate": "(동) 생성하다, 만들어내다",
    "determine": "(동) 결정하다", "affect": "(동) 영향을 미치다", "draw": "(동) 끌어내다, 그리다",

    # Common Adjectives
    "young": "(형) 젊은, 어린", "remote": "(형) 원격의", "older": "(형) 나이가 더 많은",
    "interpersonal": "(형) 대인 관계의", "organizational": "(형) 조직의", "in-person": "(형) 대면의",
    "suitable": "(형) 적절한", "hybrid": "(형) 혼합형의", "formal": "(형) 정형화된, 공식적인",
    "fluid": "(형) 유연한, 가변적인", "essential": "(형) 필수적인", "crucial": "(형) 중대한, 결정적인",
    "significant": "(형) 중요한, 상당한", "effective": "(형) 효과적인", "complex": "(형) 복잡한",
    "various": "(형) 다양한", "potential": "(형) 잠재적인 (명) 잠재력", "critical": "(형) 비판적인, 중대한",
    "different": "(형) 다른, 다양한", "specific": "(형) 특정한, 구체적인", "particular": "(형) 특정한, 특별한",

    # Common Adverbs
    "remotely": "(부) 원격으로", "long-term": "(부) 장기적으로", "perhaps": "(부) 아마도",
    "instead": "(부) 대신에", "day-to-day": "(부) 매일의, 일상의", "effectively": "(부) 효과적으로",
    "significantly": "(부) 상당히, 크게", "gradually": "(부) 점진적으로", "eventually": "(부) 결국에는",
    "normally": "(부) 보통, 정상적으로", "commonly": "(부) 흔히, 일반적으로", "primarily": "(부) 주로, 본래"
}

LEMMA_MAP = {
    "plants": "plant", "evolved": "evolve", "defenses": "defense", "genera": "genus",
    "tissues": "tissue", "compounds": "compound", "insects": "insect", "repels": "repel",
    "intoxicates": "intoxicate", "coatings": "coating", "thorns": "thorn", "predators": "predator",
    "organisms": "organism", "toxins": "toxin", "chemicals": "chemical", "barriers": "barrier",
    "mechanisms": "mechanism", "traits": "trait", "nutrients": "nutrient",
    "observers": "observer", "strategies": "strategy", "likened": "liken", "traditions": "tradition",
    "genres": "genre", "audiences": "audience", "blending": "blend", "deploying": "deploy",
    "conventions": "convention", "elements": "element", "modes": "mode", "resources": "resource",
    "difficulties": "difficulty", "colleagues": "colleague", "careers": "career", "generations": "generation",
    "connections": "connection", "students": "student", "graduates": "graduate", "distractions": "distraction",
    "found": "find", "reported": "report", "managing": "manage", "began": "begin", "working": "work",
    "offers": "offer", "requires": "require", "allows": "allow", "designated": "designate",
    "writers": "writer", "rules": "rule", "festivals": "festival", "activities": "activity", "stresses": "stress"
}

STOP_WORDS = {
    "that", "were", "the", "and", "from", "with", "more", "than", "many", "who", "some", "this",
    "their", "those", "have", "been", "doing", "does", "done", "will", "would", "could", "should",
    "eurofound", "prospects", "kingdom", "united", "a", "an", "in", "on", "at", "by", "for", "to",
    "of", "or", "as", "it", "they", "people", "study", "is", "are", "was", "be", "has", "had",
    "there", "may", "must", "also", "into", "onto", "upon", "about", "above", "across", "after",
    "before", "behind", "during", "through", "within", "without", "although", "though", "even",
    "neither", "either", "them", "which", "what", "where", "when", "why", "how", "such", "other",
    "saying", "said", "can", "our", "your", "his", "her", "its"
}

CONJUNCTIVE_ADVERBS = [
    "moreover,", "however,", "therefore,", "furthermore,", "in addition,", "consequently,",
    "thus,", "nonetheless,", "nevertheless,", "for example,", "for instance,", "on the other hand,", "but"
]

def get_word_definition(word):
    clean = re.sub(r'[^a-zA-Z]', '', word).lower()
    if not clean:
        return "(명) 주요 어휘"
    if clean in VOCAB_DATABASE:
        return VOCAB_DATABASE[clean]
    
    lemma = LEMMA_MAP.get(clean, clean)
    if lemma in VOCAB_DATABASE:
        return VOCAB_DATABASE[lemma]

    for suffix, replacement, pos in [
        ('ies', 'y', '(명)'), ('es', '', '(명)'), ('s', '', '(명)'),
        ('ing', '', '(동)'), ('ed', '', '(동)'), ('tion', '', '(명)'),
        ('ment', '', '(명)'), ('ness', '', '(명)'), ('ity', '', '(명)'),
        ('able', '', '(형)'), ('ible', '', '(형)'), ('ous', '', '(형)'),
        ('ful', '', '(형)'), ('less', '', '(형)'), ('ive', '', '(형)'),
        ('al', '', '(형)'), ('ly', '', '(부)')
    ]:
        if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
            base = clean[:-len(suffix)] + replacement
            if base in VOCAB_DATABASE:
                meaning = VOCAB_DATABASE[base]
                core = re.sub(r'^\([가-힣]+\)\s*', '', meaning)
                return f"{pos} {core}"
            elif clean[:-len(suffix)] in VOCAB_DATABASE:
                meaning = VOCAB_DATABASE[clean[:-len(suffix)]]
                core = re.sub(r'^\([가-힣]+\)\s*', '', meaning)
                return f"{pos} {core}"

    # Default morphological POS inference
    if clean.endswith('ly'): return "(부) " + clean
    if clean.endswith(('tion', 'ment', 'ness', 'ity', 'ance', 'ence', 'er', 'or', 'ist', 'ism')): return "(명) " + clean
    if clean.endswith(('able', 'ible', 'ive', 'ous', 'ful', 'less', 'ic', 'al', 'ent', 'ant')): return "(형) " + clean
    if clean.endswith(('ize', 'ate', 'en', 'fy')): return "(동) " + clean
    return "(명) " + clean

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
    raw_words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    vocab_list = []
    seen = set()

    for w in raw_words:
        if w in STOP_WORDS:
            continue
        lemma = LEMMA_MAP.get(w, w)
        if lemma in seen or lemma in STOP_WORDS:
            continue

        meaning = get_word_definition(lemma if lemma in VOCAB_DATABASE else w)
        seen.add(lemma)
        seen.add(w)
        vocab_list.append({"word": lemma, "meaning": meaning})
        if len(vocab_list) >= 16:
            break

    # If fewer than 16 words, grab remaining content words
    if len(vocab_list) < 16:
        for w in raw_words:
            if w not in seen and w not in STOP_WORDS and len(w) >= 3:
                seen.add(w)
                meaning = get_word_definition(w)
                vocab_list.append({"word": w, "meaning": meaning})
                if len(vocab_list) >= 16:
                    break

    return vocab_list[:16]

def strip_korean_brackets(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\(\)\[\]]', '', text)
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
        "진화시켜 왔다", "방어 기제를", "수만큼이나 다양한", "물리치거나", "중독시키는", "가혹한 화합물로",
        "조직을 채운다", "두꺼운 외피나", "가시와 같은", "구조적 방어는", "흔하다",
        "발견했다", "발견했다는 것을", "있었던", "사람들이", "이야기했다는 것을", "보고했다는 것을",
        "관리하는 데", "관리함에 있어서", "동료들보다", "때문에", "위해", "대해", "있어서", "시작했다",
        "그들의 커리어를", "팬데믹 동안", "동료들과 달리", "어려움을 겪을 수 있지만", "모델이", "작용할 것이다",
        "유연한 옵션일 수 있다", "허락하는", "필요로", "작동한다", "인식 방식에 따라", "문화적 틀 안에서", "강조한다",
        "특정 요구를 해결하기 위해", "비유되어 왔다", "독창성을 보여주어야 한다", "결합함으로써", "활용할 수 있지만",
        "충분하지 않다", "눈부셔야 한다"
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

    if korean_raw and "/" in korean_raw:
        return strip_korean_brackets(korean_raw.strip())

    return ensure_korean_slashes(korean_raw)

def analyze_clause_structure_dynamically(sentence, tokens):
    text = sentence.strip()
    text_lower = text.lower()
    
    if re.search(r'\b(?:allow|allows|allowed|make|makes|made|find|finds|found|keep|keeps|kept|leave|leaves|left|cause|causes|caused|enable|enables|enabled|call|calls|called)\b\s+\w+\s+(?:to\s+\w+|difficult|easy|possible|safe|happy|clean)', text, re.IGNORECASE):
        c_type = "[5형식] 주어(S) + 타동사(Vt) + 목적어(O) + 목적격보어(OC)"
        breakdown = "• 주절: 주어(S) + 5형식 타동사(Vt) + 목적어(O) + 목적격보어(OC)\n• 구문 해설: 목적어의 상태나 동작을 보충 설명하는 목적격 보어 구조"
    elif re.search(r'\b(?:give|gives|gave|send|sends|sent|offer|offers|offered|show|shows|showed|tell|tells|told|bring|brings|brought)\b\s+\w+\s+\w+', text, re.IGNORECASE):
        c_type = "[4형식] 주어(S) + 수여동사(Vt) + 간접목적어(IO) + 직접목적어(DO)"
        breakdown = "• 주절: 주어(S) + 수여동사(Vt) + 간접목적어(~에게) + 직접목적어(~을/를)"
    elif re.search(r'\b(?:is|are|was|were|been|seem|seems|seemed|appear|appears|appeared|become|becomes|became|look|looks|looked|feel|feels|felt|taste|tastes|sound|sounds|remain|remains)\b', text, re.IGNORECASE) and (not re.search(r'\b(?:is|are|was|were)\s+\w+ing\b', text, re.IGNORECASE) or "been" in text.lower()):
        c_type = "[2형식] 주어(S) + 불완전자동사(Vi) + 주격보어(SC)"
        breakdown = "• 주절: 주어(S) + 연결동사(Vi) + 주격보어(SC)\n• 구문 해설: 주어의 상태나 성질을 보충 설명하는 주격보어 구조"
    elif re.search(r'\b(?:evolve|evolved|load|loads|loaded|repel|repels|repelled|intoxicate|intoxicates|create|creates|created|deploy|deploys|deployed|produce|produces|produced|blend|blends|blended|liken|likened|impress|impresses|impressed|address|addresses|addressed|have|has|had|find|found|report|reported)\b', text, re.IGNORECASE):
        c_type = "[3형식] 주어(S) + 타동사(Vt) + 목적어(O)"
        breakdown = "• 주절: 주어(S) + 타동사(Vt) + 목적어(O)\n• 수식어구: 전치사구 및 수식절 결합 구조"
    else:
        c_type = "[1형식 & 수식구조] 주어(S) + 완전자동사(Vi) + 수식어구(Modifier)"
        breakdown = "• 주절: 주어(S) + 자동사(Vi) + 부사적 수식어구(M)"

    sub_clauses = []
    if " that " in text_lower or " which " in text_lower or " who " in text_lower:
        sub_clauses.append("• 수식절(관계사절): 선행사를 수식하는 형용사절")
    if " where " in text_lower or " when " in text_lower or " while " in text_lower or " although " in text_lower or " because " in text_lower:
        sub_clauses.append("• 부사절: 시간/조건/양보를 나타내는 종속접속사절")
    if "either" in text_lower and "or" in text_lower:
        sub_clauses.append("• 상관접속사 병렬구조: either A or B (A 또는 B 중 하나)")
    if " as " in text_lower and re.search(r'as\s+\w+\s+as', text_lower):
        sub_clauses.append("• 동등비교 구문: as + 원급 + as (~만큼이나 ...한)")

    if sub_clauses:
        breakdown = breakdown + "\n" + "\n".join(sub_clauses)

    return f"{c_type}\n{breakdown}"

def generate_grammar_points_dynamically(sentence, tokens):
    text = sentence.strip()
    text_lower = text.lower()
    points = []

    if re.search(r'\b(?:have|has)\s+(?:evolved|developed|been|shown|established|grown|changed|increased)\b', text, re.IGNORECASE):
        points.append("1. 현재완료 시제 (have/has + p.p.): 과거에 시작된 동작이나 상태가 현재까지 지속되거나 영향을 미치고 있음을 나타냅니다.")
    elif re.search(r'\b(?:had)\s+\w+ed\b', text, re.IGNORECASE):
        points.append("1. 과거완료 시제 (had + p.p.): 과거의 특정 기준 시점보다 더 이전에 일어난 대과거의 동작을 나타냅니다.")
    elif re.search(r'\b(?:is|are|was|were)\s+\w+ed\b', text, re.IGNORECASE) and not any(w in text_lower for w in ["intoxicated", "evolved"]):
        points.append("1. 수동태 구조 (be + p.p.): 주어가 동작을 행하는 주체가 아니라 동작의 대상이 됨을 표현합니다.")

    if "either" in text_lower and "or" in text_lower:
        points.append("2. 상관접속사 (either A or B): 'A 또는 B 중 하나'라는 뜻으로, 동사원형이나 명사구가 문법적으로 동일한 형태로 병렬 연결됩니다.")
    elif "neither" in text_lower and "nor" in text_lower:
        points.append("2. 상관접속사 (neither A nor B): 'A도 B도 아닌'이라는 양자부정의 병렬 구조를 이끕니다.")
    elif "not only" in text_lower and "but" in text_lower:
        points.append("2. 상관접속사 (not only A but also B): 'A뿐만 아니라 B도'라는 뜻으로 B에 초점이 맞추어집니다.")
    elif " and " in text_lower or " or " in text_lower:
        points.append("2. 등위접속사 병렬구조: 문맥상 대등한 역할을 하는 어구들이 접속사를 중심으로 균형을 이룹니다.")

    if re.search(r'\bas\s+(\w+)\s+as\b', text, re.IGNORECASE):
        m = re.search(r'\bas\s+(\w+)\s+as\b', text, re.IGNORECASE)
        adj_adv = m.group(1)
        points.append(f"3. 원급 동등비교 (as {adj_adv} as): '~만큼이나 {adj_adv}한'이라는 의미로 비교 대상 간의 동등한 정도를 나타냅니다.")
    elif "more" in text_lower and "than" in text_lower:
        points.append("3. 비교급 구문 (more ... than): 기준 대상보다 더 뛰어남이나 차이를 나타내는 우등비교 구조입니다.")

    if re.search(r'\bthat\s+(?:either|repel|repels|intoxicate|allows|works|are|is)\b', text, re.IGNORECASE):
        points.append("4. 주격 관계대명사 that: 선행사 명사구를 뒤에서 수식하며, 관계사절 내에서 주어 역할을 수행합니다.")
    elif "who " in text_lower or "which " in text_lower:
        points.append("4. 관계사절 수식: 선행사를 직접 수식하는 형용사절로 뒤에 불완전한 문장이 이어집니다.")
    elif "where " in text_lower or "when " in text_lower:
        points.append("4. 관계부사절: 선행사의 장소/시간적 배경을 수식하며, 뒤에 주어·동사를 갖춘 완전한 문장이 이어집니다.")

    if "blending" in text_lower or "working with" in text_lower or "deploying" in text_lower or re.search(r',\s*\w+ing\b', text):
        points.append("5. 분사구문 (-ing): 부수적인 동작이나 상황(~하면서)을 간결하게 나타내는 분사구문입니다.")
    elif "likened to" in text_lower or "designated for" in text_lower or "developed from" in text_lower:
        points.append("5. 과거분사구 후치수식 (p.p.): 앞의 명사를 뒤에서 수동의 의미로 수식하는 구조입니다.")

    if len(points) < 2:
        points.append("1. 구문 분석 및 직독직해: 핵심 주어와 동사 및 목적어/수식어 단위로 정확한 끊어읽기 구획이 적용되었습니다.")
        points.append("2. 서술형 어법 대비: 문장 내 수일치와 전치사구 및 수식 구조의 위치 관계에 유의해야 합니다.")

    return "\n".join(points[:3])

def dynamic_rule_tokenize(sentence):
    tokens = []
    text = sentence.strip()
    words = text.split()
    if not words: return tokens
    i = 0
    found_main_verb = False
    found_main_subject = False
    while i < len(words):
        w = words[i]
        clean_w = re.sub(r'^[^\w]+|[^\w]+$', '', w).lower()
        if clean_w in ['and', 'but', 'or', 'so', 'yet', 'nor', 'however', 'therefore', 'moreover', 'furthermore', 'thus', 'instead']:
            tokens.append({"text": w, "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": True})
            tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})
            i += 1
            continue
        if clean_w in ['either', 'neither', 'both']:
            tokens.append({"text": w, "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": True})
            i += 1
            continue
        if clean_w in ['toddlers', 'toddler', 'infants', 'children'] and i + 1 < len(words) and (words[i+1].lower().startswith('fall') or words[i+1].lower().endswith('ing')):
            tokens.append({"text": w, "top_label": "", "color": "blue", "sub_tag": "의미상 S", "underline": True, "is_conjunction": False})
            tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})
            i += 1
            continue
        if clean_w in ['that', 'which', 'who', 'where', 'when', 'whose', 'whom']:
            tokens.append({"text": f"({w}", "top_label": "", "color": "blue", "sub_tag": "⬑", "underline": False, "is_conjunction": False})
            i += 1
            continue
        if clean_w in ['with', 'like', 'as', 'of', 'by', 'in', 'on', 'at', 'from', 'for', 'about', 'without', 'through', 'since', 'ever', 'during', 'before', 'after', 'throughout', 'across', 'among', 'along', 'despite', 'unlike']:
            prep_words = [w]
            j = i + 1
            while j < len(words) and not re.match(r'^(?:that|which|who|and|but|or|is|are|was|were|may|can|will|must|could|should|might|shall|see|sees|saw|load|loads|repel|repels|prevent|prevents|face|faces|make|makes|cause|causes|have|has|had|\.)$', words[j].lower()) and not words[j-1].endswith(','):
                prep_words.append(words[j])
                j += 1
            if j < len(words) and words[j].endswith(',') and not re.match(r'^(?:that|which|who|and|but|or|is|are|was|were|may|can|will|must|could|should|might|shall|see|sees|saw|load|loads|repel|repels|prevent|prevents|face|faces|make|makes|cause|causes|have|has|had|\.)$', words[j].lower()):
                prep_words.append(words[j]); j += 1
            p_text = " ".join(prep_words)
            if not p_text.startswith('('): p_text = f"({p_text}"
            if not p_text.endswith(')') and not p_text.endswith('),'): p_text = f"{p_text})"
            arrow_tag = "⬑" if found_main_subject else ""
            tokens.append({"text": p_text, "top_label": "", "color": "slate", "sub_tag": arrow_tag, "underline": False, "is_conjunction": False})
            tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})
            i = j
            continue
        VERB_REGEX = r'^(?:see|sees|saw|seen|have|has|had|is|are|was|were|load|loads|loaded|works|worked|stress|stressed|liken|likened|produce|produced|draw|drew|must|can|may|might|could|should|shall|will|would|find|finds|found|began|begin|begins|experience|experiences|experienced|increase|increases|increased|prevent|prevents|prevented|make|makes|made|cause|causes|caused|face|faces|faced|decide|decides|decided|create|creates|created|spray|sprays|sprayed|want|wants|wanted|need|needs|needed|maintain|maintains|maintained|protect|protects|protected|deploy|deploys|deployed|allow|allows|allowed|struggle|struggles|struggled|offer|offers|offered|require|requires|required)$'
        if not found_main_verb and (re.match(VERB_REGEX, clean_w) or clean_w.endswith('ed')):
            v_phrase = [w]
            j = i + 1
            while j < len(words) and words[j].lower() in ['evolved', 'been', 'likened', 'produced', 'developed', 'also', 'be', 'working', 'prevent', 'prevents', 'feed', 'feeding', 'experience', 'increase', 'make', 'cause', 'face', 'load']:
                v_phrase.append(words[j])
                j += 1
            verb_text = " ".join(v_phrase)
            is_transitive = clean_w not in ['evolve', 'evolved', 'work', 'worked', 'been', 'be', 'struggle', 'struggled']
            v_tag = "Vt" if is_transitive else "Vi"
            tokens.append({"text": verb_text, "top_label": "", "color": "rose", "sub_tag": v_tag, "underline": True, "is_conjunction": False})
            tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})
            found_main_verb = True
            i = j
            continue
        if not found_main_subject and not found_main_verb and clean_w not in ['in', 'by', 'on', 'at', 'with', 'for', 'to', 'from', 'as', 'while', 'although', 'thus', 'since', 'ever', 'during', 'before', 'after']:
            subj_words = [w]
            j = i + 1
            while j < len(words) and not re.match(VERB_REGEX, re.sub(r'[^a-zA-Z]', '', words[j]).lower()) and not words[j].lower().endswith('ed'):
                if words[j].startswith('(') or words[j].lower() in ['like', 'with', 'of', 'in', 'by', 'that', 'who', 'which', 'and', 'or', 'but']: break
                subj_words.append(words[j])
                j += 1
            subj_text = " ".join(subj_words)
            tokens.append({"text": subj_text, "top_label": "", "color": "blue", "sub_tag": "S", "underline": True, "is_conjunction": False})
            tokens.append({"text": " / ", "top_label": "", "color": "purple", "sub_tag": "", "underline": False, "is_conjunction": False})
            found_main_subject = True
            i = j
            continue
        if found_main_verb and clean_w not in ['the', 'a', 'an']:
            is_adverb = (clean_w.endswith('ly') and clean_w not in ['family', 'likely', 'lonely', 'lovely', 'friendly', 'early', 'ugly', 'silly', 'holy', 'daily', 'weekly', 'monthly', 'yearly']) or clean_w in ['often', 'always', 'never', 'already', 'still', 'even', 'also', 'just', 'only', 'ever', 'well', 'far', 'so', 'too', 'very', 'almost', 'much', 'more', 'together', 'apart', 'ahead', 'away', 'back', 'down', 'up', 'out', 'in', 'off', 'over']
            if is_adverb:
                tokens.append({"text": w, "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": False})
            elif clean_w in ['related', 'different', 'important', 'crucial', 'essential', 'common', 'rare', 'necessary', 'likely', 'possible', 'difficult', 'clear', 'critical', 'effective', 'useful', 'similar']:
                tokens.append({"text": w, "top_label": "", "color": "indigo", "sub_tag": "SC", "underline": False, "is_conjunction": False})
            else:
                tokens.append({"text": w, "top_label": "", "color": "emerald", "sub_tag": "O", "underline": False, "is_conjunction": False})
            i += 1
            continue
        tokens.append({"text": w, "top_label": "", "color": "slate", "sub_tag": "", "underline": False, "is_conjunction": False})
        i += 1
    return tokens

def rule_tokenize(sentence):
    return dynamic_rule_tokenize(sentence)

def modify_analysis_with_prompt(analysis_data, modify_prompt):
    """
    Applies custom user prompt modifications (e.g. '문장 4의 and 접속사 work에서 and를 세모쳐줘').
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

def generate_summary_info_dynamically(sentences, full_vocab, title=""):
    clean_title = (title or '').strip()
    words_all = " ".join(sentences).lower()
    if "plant" in words_all or "defense" in words_all or "compound" in words_all or "tissue" in words_all:
        subj = "식물의 다양한 방어 기제와 생존 전략"
        s1, s2, s3 = "① 식물은 속의 수만큼 다양한 방어 기제 진화.", "② 곤충을 물리치거나 중독시키는 화학물질 활용.", "③ 두꺼운 외피 및 가시 등의 구조적 방어 구축."
    elif "spectacle" in words_all or "culture" in words_all or "audience" in words_all:
        subj = "문화적 틀 안에서의 스펙터클 창작과 독창성"
        s1, s2, s3 = "① 스펙터클은 문화적 인식의 틀 안에서 작동함.", "② 기존 전통과 혁신의 조화를 통한 창작 필요.", "③ 단순한 모방을 넘어 눈부신 완성도 요구됨."
    elif "eurofound" in words_all or "remote" in words_all or "hybrid" in words_all:
        subj = "원격 근무 젊은 직원의 직장 적응과 유연성"
        s1, s2, s3 = "① 원격 근무 젊은 직원의 업무 적응 어려움.", "② 적절한 공간 및 시간 부족으로 인한 애로.", "③ 일상적 장소를 선택할 수 있는 유연성 필요."
    elif any(w in words_all for w in ["conservation", "preservation", "restoration", "enlightenment", "monument", "historic", "preserve", "conserve", "보존", "보전", "복원"]):
        subj = "보존과 보전의 개념적 차이와 역사적 발전"
        s1 = "보존과 보전은 유사하나 초기 계몽주의부터 밀접히 관련됨."
        s2 = "보전은 복원을, 보존은 원형 유지를 중시하며 구별됨."
        s3 = "보존주의자는 최소 개입으로 원본 상태 보호를 선호."
    elif any(w in words_all for w in ["fall", "injury", "size", "bone", "fracture", "weight", "gravity", "scale", "body", "toddler"]):
        subj = "몸집 크기에 따른 낙상 충격과 부상 위험"
        s1 = "몸집이 클수록 사소한 사고에도 더 큰 손상을 입는다."
        s2 = "아기는 뼈가 상대적으로 두꺼워 넘어져도 심각한 부상이 드물다."
        s3 = "성인은 큰 몸집으로 인해 낙상 시 충격이 커 뼈 손상 위험이 높다."
    else:
        topic_term = full_vocab[0]["word"] if full_vocab else (clean_title[:10] or "영어 지문")
        subj = f"{topic_term}의 핵심 원리와 주요 특징"
        s1, s2, s3 = f"① {topic_term}의 기본 개념과 주요 배경 설명.", f"② 세부적인 작용 방식과 관련 요인 분석.", f"③ 종합적인 결론 및 실질적 시사점 제시."
    kw_parts = [f"{('①' if idx == 0 else ('②' if idx == 1 else '③'))} {item.get('word', '')} ({re.sub(r'^\([가-힣]+\)\s*', '', item.get('meaning', ''))})" for idx, item in enumerate(full_vocab[:3])]
    return {"title_en": clean_title or "English Passage Comprehensive Analysis", "subject": subj[:38], "keywords": "  ".join(kw_parts) if kw_parts else "① 핵심 어휘 분석  ② 세부 개념  ③ 주요 원리", "summary": [s1[:38], s2[:38], s3[:38]]}

def parse_with_rule_engine(passage, korean_passage="", title="", sentence_pairs=None):
    if sentence_pairs and isinstance(sentence_pairs, list) and len(sentence_pairs) > 0:
        sentences = [p.get('english', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        korean_sentences = [p.get('korean', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
    else:
        sentences = split_into_sentences(passage)
        korean_sentences = split_into_korean_sentences(korean_passage) if korean_passage else []

    results = []
    full_vocab = extract_vocabulary(passage)

    for idx, sentence in enumerate(sentences, 1):
        raw_kr = korean_sentences[idx - 1] if idx - 1 < len(korean_sentences) else ""
        tokens = rule_tokenize(sentence)
        ensured_kr = build_exact_1to1_korean_chunks(tokens, raw_kr)

        c_struct = analyze_clause_structure_dynamically(sentence, tokens)
        g_pts = generate_grammar_points_dynamically(sentence, tokens)
        w_pts = f"[서술형 대비 핵심 구문] {sentence[:45]}..."

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

    summary_info = generate_summary_info_dynamically(sentences, full_vocab, title)

    return {
        "title": title.strip() if title else "영어 지문 분석 교안",
        "summary_info": summary_info,
        "passage_raw": passage,
        "korean_raw": korean_passage,
        "sentence_count": len(results),
        "sentences": results,
        "vocabulary": full_vocab,
        "used_ai": False
    }

def analyze_with_gemini(passage, korean_passage="", api_key=DEFAULT_GEMINI_API_KEY, title="", sentence_pairs=None):
    if not api_key:
        api_key = DEFAULT_GEMINI_API_KEY

    models = ["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    
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
2. 모든 절(명사절, 형용사절, 부사절) 내부에서도 주어, 동사, 전치사구, 접속사(and/but) 사이에 슬래시(/) 끊어읽기 토큰 {{"text": " / ", "color": "purple"}}을 명확히 분리 삽입할 것!
"""

    payload = {
        "system_instruction": {
            "parts": [{"text": EXPERT_PERSONA_PROMPT}]
        },
        "contents": [{"parts": [{"text": user_input_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    session = requests.Session()

    full_vocab = extract_vocabulary(passage)
    default_summary = generate_summary_info_dynamically(input_sentences, full_vocab, title)

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

                    c_struct = s_data.get("clause_structure", "") or analyze_clause_structure_dynamically(orig_sentence, sent_tokens)
                    g_pts = s_data.get("grammar_points", "") or generate_grammar_points_dynamically(orig_sentence, sent_tokens)
                    w_pts = s_data.get("writing_points", "") or f"[서술형 대비 핵심 구문] {orig_sentence[:45]}..."

                    results.append({
                        "index": idx + 1,
                        "original": orig_sentence,
                        "tokens": sent_tokens,
                        "chunk_korean": strip_korean_brackets(ensured_chunk_kr),
                        "clause_structure": c_struct,
                        "grammar_points": g_pts,
                        "writing_points": w_pts,
                        "page_break": sentence_pairs[idx].get('page_break', False) if (sentence_pairs and idx < len(sentence_pairs)) else False
                    })
                
                usage_meta = data.get('usageMetadata', {})
                total_tok = usage_meta.get('totalTokenCount', 0)
                prompt_tok = usage_meta.get('promptTokenCount', 0)
                cand_tok = usage_meta.get('candidatesTokenCount', 0)

                raw_vocab = parsed_json.get("vocabulary") or full_vocab
                final_vocab = []
                if isinstance(raw_vocab, list):
                    for item in raw_vocab:
                        if isinstance(item, dict):
                            w = item.get("word") or item.get("english") or item.get("term") or item.get("lemma") or item.get("name") or ""
                            m = item.get("meaning") or item.get("korean") or item.get("definition") or item.get("mean") or ""
                            if not w and item:
                                for k, val in item.items():
                                    if k not in ['word', 'meaning', 'english', 'korean', 'definition', 'pos']:
                                        w = k
                                        m = val
                                        break
                            if w:
                                final_vocab.append({"word": str(w).strip(), "meaning": str(m).strip() if m else get_word_definition(str(w))})
                        elif isinstance(item, str) and item.strip():
                            w = item.strip()
                            final_vocab.append({"word": w, "meaning": get_word_definition(w)})
                elif isinstance(raw_vocab, dict):
                    for k, val in raw_vocab.items():
                        final_vocab.append({"word": str(k).strip(), "meaning": str(val).strip()})

                if not final_vocab or len(final_vocab) < 3:
                    final_vocab = full_vocab

                return {
                    "title": title.strip() if title else "영어 지문 분석 교안",
                    "summary_info": summary_info,
                    "passage_raw": passage,
                    "korean_raw": korean_passage,
                    "sentence_count": len(results),
                    "sentences": results,
                    "vocabulary": final_vocab,
                    "used_ai": True,
                    "used_tokens": total_tok,
                    "usage_metadata": {
                        "total_tokens": total_tok,
                        "prompt_tokens": prompt_tok,
                        "candidates_tokens": cand_tok
                    }
                }
        except Exception as e:
            print(f"Gemini generation error with model {model_name}:", e)
            continue

    # Fallback to rule engine if Gemini fails or quota exceeded
    return parse_with_rule_engine(passage, korean_passage, title, sentence_pairs)

def parse_english_passage(passage, korean_passage="", title="", api_key=DEFAULT_GEMINI_API_KEY, use_ai=True, sentence_pairs=None):
    if use_ai and api_key:
        res_data = analyze_with_gemini(passage, korean_passage, api_key, title, sentence_pairs)
    else:
        res_data = parse_with_rule_engine(passage, korean_passage, title, sentence_pairs)
    return post_process_adverbs(res_data)

def generate_variation_exam(passage, topic="", api_key=DEFAULT_GEMINI_API_KEY):
    key = api_key or DEFAULT_GEMINI_API_KEY
    if not topic:
        topic = "Core Passage Topic"

    import random
    random_seed = random.randint(1000, 999999)

    prompt_tmpl = """You are an elite high school English teacher in South Korea, specialized in creating high-quality, rigorous mock exam questions based on provided English passages.
Your task is to analyze the provided English passage and generate exactly 9 types of questions. The outputs must be professional, grammatically perfect, and match the style of the Korean CSAT and high school midterm/final exams.

[Generation Seed: __RANDOM_SEED__]
[Diversity & Randomization Rule]
Ensure high variety in question design across repeated calls:
- Q1 & Q7 (Topic): Vary the phrasing and perspective of the Korean/English answer choices and distractors.
- Q2 (Sequence): Dynamically choose fresh cut-points for paragraphs (A), (B), and (C).
- Q3 & Q4 (Grammar/Vocab): Select DIFFERENT underlined target words and error locations across the passage.
- Q5 (Sentence Order): Apply fresh randomized scrambling orders.
- Q6 & Q8 (Descriptive Writing): Select different key sentences and different chunk distributions.
- Q9 (Fill in the blanks): Select a varied combination of 15 crucial content words across the entire passage.

[Input Passage]
__PASSAGE__

[Input Topic Reference]
__TOPIC__

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
- Input Topic Reference: "__TOPIC__"
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
- Input Topic Reference: "__TOPIC__"
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

    prompt = prompt_tmpl.replace("__RANDOM_SEED__", str(random_seed)).replace("__PASSAGE__", passage).replace("__TOPIC__", topic)

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
