import os
import re
import json
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, Response
from parser_engine import parse_english_passage, modify_analysis_with_prompt, generate_variation_exam
from pdf_generator import create_lecture_handout_pdf

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()
DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', default_api_key=DEFAULT_API_KEY)

@app.route('/vocab-test')
def vocab_test():
    return render_template('vocab_test.html')

@app.route('/exam-view')
def exam_view():
    return render_template('exam_view.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', '')).strip()

    if not username:
        return jsonify({'success': False, 'error': '아이디를 입력해 주세요.'}), 400
    if not password:
        return jsonify({'success': False, 'error': '비밀번호를 입력해 주세요.'}), 400

    if not GAS_URL:
        return jsonify({'success': True, 'username': username})

    try:
        payload = {
            "action": "login",
            "username": username,
            "password": password
        }
        res = requests.post(GAS_URL, json=payload, timeout=12)
        if res.status_code == 200:
            res_data = res.json()
            if res_data.get('success'):
                return jsonify({'success': True, 'username': res_data.get('username', username)})
            else:
                error_msg = res_data.get('error', '아이디 또는 비밀번호가 일치하지 않습니다.')
                return jsonify({'success': False, 'error': error_msg}), 401
        else:
            return jsonify({'success': False, 'error': f'구글 시트 인증 오류 (HTTP {res.status_code})'}), 500
    except Exception as e:
        print(f"[api_login] Error: {e}")
        return jsonify({'success': False, 'error': f'로그인 처리 중 오류 발생: {str(e)}'}), 500

@app.route('/api/generate_exam', methods=['POST'])
@app.route('/api/generate_variation', methods=['POST'])
def generate_exam():
    data = request.json or {}
    title = data.get('title', '').strip()
    passage = data.get('passage', '').strip()
    topic = data.get('topic', '').strip()
    sentence_pairs = data.get('sentence_pairs', [])
    branch = data.get('branch', '기타').strip() or '기타'
    material_type = data.get('material_type') or data.get('label') or '모의고사'
    api_key = data.get('api_key', '').strip() or DEFAULT_API_KEY

    if not title:
        return jsonify({'error': '지문 제목이 필요합니다.'}), 400

    if not passage and sentence_pairs:
        passage = " ".join([p.get('english', '').strip() for p in sentence_pairs if p.get('english')])

    if not passage:
        return jsonify({'error': '변형문제를 생성할 영어 지문 내용이 없습니다.'}), 400

    if not topic:
        topic = title

    try:
        title_clean = re.sub(r'\s*-\s*9종\s*변형문제.*$', '', title).strip()
        title_1 = f"{title_clean} - 9종 변형문제 1차"
        title_2 = f"{title_clean} - 9종 변형문제 2차"

        all_keys = [
            "topic_korean", "sentence_ordering", "grammar_syntax", "vocabulary",
            "passage_ordering", "descriptive_writing_2", "topic_english",
            "descriptive_writing_1", "vocab_blank"
        ]

        def _gen_exam(idx, t_name):
            q_data = generate_variation_exam(passage, topic=f"{topic} (세트 {idx}차)", api_key=api_key)
            import random
            shuffled_order = list(all_keys)
            random.shuffle(shuffled_order)

            doc_type_val = f"변형문제 {idx}차"
            p_load = {
                "title": t_name,
                "material_type": material_type,
                "doc_type": doc_type_val,
                "label": material_type,
                "branch": branch,
                "sentence_pairs": sentence_pairs,
                "analysis_data": {
                    "title": t_name,
                    "material_type": material_type,
                    "doc_type": doc_type_val,
                    "passage": passage,
                    "topic": topic,
                    "branch": branch,
                    "questions": q_data,
                    "question_order": shuffled_order,
                    "is_variation_exam": True,
                    "set_number": idx,
                    "created_at": time.strftime('%Y-%m-%dT%H:%M:%S')
                }
            }
            f_name = save_db_handout(t_name, p_load, label=material_type, material_type=material_type, doc_type=doc_type_val, branch=branch)
            try:
                actual_tokens = q_data.get('_total_tokens', 0) or estimate_tokens_for_item(doc_type_val)
                append_usage_log(branch, material_type, doc_type_val, t_name, actual_tokens)
            except Exception:
                pass
            return {"title": t_name, "filename": f_name, "material_type": material_type, "doc_type": doc_type_val, "questions": q_data, "question_order": shuffled_order, "branch": branch}

        with ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(_gen_exam, 1, title_1)
            future2 = executor.submit(_gen_exam, 2, title_2)
            res1 = future1.result()
            res2 = future2.result()

        return jsonify({
            'success': True,
            'results': [res1, res2],
            'filename': res1['filename'],
            'questions': res1['questions'],
            'question_order': res1['question_order'],
            'branch': branch,
            'label': '변형문제'
        })
    except Exception as e:
        print(f"[generate_exam] Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/save_exam_layout', methods=['POST'])
def save_exam_layout():
    data = request.json or {}
    filename = data.get('filename', '').strip()
    label = data.get('label', '변형문제').strip()
    branch = data.get('branch', '기타').strip() or '기타'
    page_breaks = data.get('page_breaks', [])
    question_order = data.get('question_order')
    
    if not filename:
        return jsonify({'error': '파일명이 필요합니다.'}), 400
        
    try:
        doc = load_db_handout(filename, label=label)
        if not doc.get('analysis_data'):
            doc['analysis_data'] = {}
        doc['analysis_data']['page_breaks'] = page_breaks
        if question_order and isinstance(question_order, list):
            doc['analysis_data']['question_order'] = question_order
        if branch:
            doc['branch'] = branch
            doc['analysis_data']['branch'] = branch
        saved_fn = save_db_handout(doc.get('title', filename.replace('.json', '')), doc, label=label, branch=branch)
        return jsonify({'success': True, 'filename': saved_fn})
    except Exception as e:
        print(f"[save_exam_layout] Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json or {}
    title = data.get('title', '').strip()
    passage = data.get('passage', '').strip()
    korean_passage = data.get('korean_passage', '').strip()
    sentence_pairs = data.get('sentence_pairs', [])
    api_key = data.get('api_key', '').strip() or DEFAULT_API_KEY
    use_ai = data.get('use_ai', True)

    if not title:
        return jsonify({'error': '지문 제목을 필수 입력해 주세요.'}), 400

    if sentence_pairs and isinstance(sentence_pairs, list) and len(sentence_pairs) > 0:
        en_list = [p.get('english', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        kr_list = [p.get('korean', '').strip() for p in sentence_pairs if p.get('korean', '').strip()]
        passage = " ".join(en_list)
        korean_passage = "\n".join(kr_list)
    else:
        sentence_pairs = []

    if not passage:
        return jsonify({'error': '영어 지문을 입력해 주세요.'}), 400

    if not korean_passage:
        return jsonify({'error': '끊어읽기 직독직해 매칭을 위해 한글 해석을 입력해 주세요.'}), 400

    try:
        result = parse_english_passage(
            passage=passage,
            korean_passage=korean_passage,
            title=title,
            api_key=api_key,
            use_ai=use_ai,
            sentence_pairs=sentence_pairs
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
try:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
except Exception:
    pass

def persist_base64_image(image_data_url, title=""):
    """
    Saves a base64 image data URL to a local static file to prevent overflowing 
    Google Sheets cell character limits (50,000 chars) and ensure 100% reliable persistence.
    """
    if not image_data_url or not isinstance(image_data_url, str):
        return image_data_url
    if not image_data_url.startswith('data:image/'):
        return image_data_url
    
    try:
        header, b64_str = image_data_url.split(',', 1)
        ext = 'png'
        if 'jpeg' in header or 'jpg' in header:
            ext = 'jpg'
        elif 'webp' in header:
            ext = 'webp'
        
        import hashlib
        h = hashlib.md5(b64_str.encode('utf-8')).hexdigest()[:12]
        filename = f"illu_{int(time.time())}_{h}.{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(b64_str))
        
        return f"/static/uploads/{filename}"
    except Exception as e:
        print("[persist_base64_image] Error saving image file:", e)
        return image_data_url

@app.route('/api/modify', methods=['POST'])
def modify():
    data = request.json or {}
    analysis_data = data.get('analysis_data', {})
    modify_prompt = data.get('modify_prompt', '').strip()
    branch = data.get('branch', '본사')
    title = (analysis_data.get('title') or '영어 교안').strip()
    material_type = data.get('material_type', '모의고사')

    if not analysis_data or 'sentences' not in analysis_data:
        return jsonify({'error': '먼저 교안 생성을 실행해 주세요.'}), 400

    if not modify_prompt:
        return jsonify({'error': '수정 프롬프트를 입력해 주세요.'}), 400

    try:
        updated_data = modify_analysis_with_prompt(analysis_data, modify_prompt)
        
        # Real-time token tracking for modifications
        try:
            modify_tokens = 1500  # Benchmark token usage for AI prompt modifications
            append_usage_log(branch, material_type, '교안구문수정', f"{title} (구문수정)", modify_tokens)
        except Exception as log_e:
            print("[modify] Token log warning:", log_e)

        return jsonify(updated_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate_illustration', methods=['POST'])
def generate_illustration_endpoint():
    data = request.json or {}
    title = data.get('title', '').strip()
    topic = data.get('topic', '').strip()
    keywords = data.get('keywords', '').strip()
    summary = data.get('summary', '').strip()
    passage = data.get('passage', '').strip()
    branch = data.get('branch', '본사')
    material_type = data.get('material_type', '모의고사')
    api_key = data.get('api_key', '').strip() or DEFAULT_API_KEY
    
    combined_context = f"Title: {title}\nSubject/Topic: {topic}\nKeywords: {keywords}\nSummary: {summary}\nPassage: {passage[:300]}"
    
    # 1. First, create a concise English visual scene description using Gemini
    english_scene = ""
    if api_key:
        try:
            prompt_trans = f"""You are an art director creating educational illustrations for high school reading materials.
Based on the following reading passage summary:
{combined_context}

Task:
Create a single concise (10~15 words) English visual scene description that vividly captures the main subject, setting, and core concepts described in the summary.

Examples:
- Skyscraper vortex: "A towering aerodynamic skyscraper with swirling wind vortex airflows around its curved corners under sunlight"
- Art collector: "An art collector thoughtfully evaluating classical masterpiece paintings in a sunlit art gallery"

Rules:
- Output ONLY the English visual scene description.
- Do not write any explanations or conversational text."""
            url_text = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            resp = requests.post(url_text, json={"contents": [{"parts": [{"text": prompt_trans}]}]}, timeout=12)
            if resp.status_code == 200:
                english_scene = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                english_scene = re.sub(r'[\r\n"]+', ' ', english_scene).strip()
        except Exception as e:
            print("[generate_illustration] Scene description warning:", e)

    if not english_scene:
        clean_t = re.sub(r'[\d년월고호번\-]+', '', f"{topic} {summary} {title}").strip()
        if "빌딩" in clean_t or "skyscraper" in clean_t.lower() or "와류" in clean_t or "vortex" in clean_t.lower():
            english_scene = "Modern architectural aerodynamic skyscraper with swirling wind vortex shedding airflows around curved building corners"
        elif "미술" in clean_t or "art" in clean_t.lower() or "수집" in clean_t:
            english_scene = "Art collector and gallery curator viewing classical paintings in warm gallery"
        elif "원격" in clean_t or "remote" in clean_t.lower():
            english_scene = "Young professional working on a laptop in a cozy room"
        else:
            english_scene = f"Aesthetic scenery depicting {clean_t}"

    ghibli_prompt = f"Studio Ghibli style watercolor illustration of {english_scene}, aesthetic anime scenery, soft warm lighting, detailed background, peaceful anime art, masterpiece, 4k"

    # 2. Generate Image directly via official Google Gemini Image API (gemini-2.5-flash-image)
    if api_key:
        for img_model in ["gemini-2.5-flash-image", "gemini-3.1-flash-image"]:
            try:
                img_url = f"https://generativelanguage.googleapis.com/v1beta/models/{img_model}:generateContent?key={api_key}"
                img_payload = {
                    "contents": [{
                        "parts": [{"text": f"Generate an artistic, high-quality image: {ghibli_prompt}"}]
                    }]
                }
                res = requests.post(img_url, json=img_payload, timeout=35)
                if res.status_code == 200:
                    res_json = res.json()
                    parts = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [])
                    for part in parts:
                        inline_data = part.get('inlineData')
                        if inline_data and inline_data.get('data'):
                            mime = inline_data.get('mimeType', 'image/png')
                            b64 = inline_data.get('data')
                            raw_data_url = f"data:{mime};base64,{b64}"
                            saved_path = persist_base64_image(raw_data_url, title)
                            
                            # Real-time token tracking for AI Illustration generation
                            try:
                                append_usage_log(branch, material_type, 'AI삽화생성', f"{title} (삽화생성)", 2500)
                            except Exception:
                                pass

                            return jsonify({
                                'success': True,
                                'illustration_url': saved_path,
                                'prompt': ghibli_prompt
                            })
            except Exception as gemini_img_err:
                print(f"[generate_illustration] {img_model} error:", gemini_img_err)

    # 3. Fallback to local high-res themes if offline
    fallback_url = '/static/skyscraper_vortex.jpg' if ("빌딩" in title or "와류" in title or "skyscraper" in passage.lower()) else '/static/illustration.jpg'
    return jsonify({'success': True, 'illustration_url': fallback_url, 'prompt': ghibli_prompt})

@app.route('/api/fetch_image_url', methods=['POST'])
def fetch_image_url_endpoint():
    data = request.json or {}
    raw_url = data.get('url', '').strip()
    if not raw_url:
        return jsonify({'error': '이미지 URL을 입력해 주세요.'}), 400

    if raw_url.startswith('blob:'):
        return jsonify({'error': 'blob 주소는 브라우저 내부 임시 주소입니다. 이미지를 마우스 우클릭 후 [이미지 복사]를 하신 뒤 화면에서 Ctrl+V 로 붙여넣으시거나, [이미지 주소 복사]를 이용해 주세요.'}), 400

    import urllib.parse
    import base64

    target_url = raw_url
    # 1. Parse Google Image Search result URL: google.com/imgres?...&imgurl=...
    if "imgurl=" in raw_url:
        try:
            parsed = urllib.parse.urlparse(raw_url)
            params = urllib.parse.parse_qs(parsed.query)
            if 'imgurl' in params and params['imgurl']:
                target_url = params['imgurl'][0]
        except Exception:
            pass

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Referer': target_url
    }

    try:
        res = requests.get(target_url, headers=headers, timeout=20)
        if res.status_code == 200 and len(res.content) > 200:
            content_type = res.headers.get('Content-Type', 'image/jpeg')
            if 'text/html' in content_type.lower():
                # Extract og:image meta tag from HTML page
                og_match = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', res.text, re.IGNORECASE)
                if not og_match:
                    og_match = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', res.text, re.IGNORECASE)
                
                if og_match:
                    og_url = og_match.group(1)
                    res_og = requests.get(og_url, headers=headers, timeout=20)
                    if res_og.status_code == 200 and len(res_og.content) > 200:
                        ct = res_og.headers.get('Content-Type', 'image/jpeg')
                        b64 = base64.b64encode(res_og.content).decode('utf-8')
                        return jsonify({'success': True, 'illustration_url': f'data:{ct};base64,{b64}'})
                return jsonify({'error': '해당 주소는 이미지 파일 주소가 아닌 웹페이지입니다. 이미지에서 마우스 우클릭 후 [이미지 주소 복사]를 하거나 [이미지 복사] 후 Ctrl+V로 붙여넣어 주세요.'}), 400

            b64 = base64.b64encode(res.content).decode('utf-8')
            return jsonify({'success': True, 'illustration_url': f'data:{content_type};base64,{b64}'})
        else:
            return jsonify({'error': f'이미지를 불러올 수 없습니다 (상태: {res.status_code})'}), 400
    except Exception as e:
        return jsonify({'error': f'이미지 다운로드 실패: {str(e)}'}), 500

@app.route('/api/upload_illustration', methods=['POST'])
def upload_illustration_endpoint():
    data = request.json or {}
    image_data = data.get('image_data', '')
    if not image_data:
        return jsonify({'error': '이미지 데이터가 필요합니다.'}), 400
    return jsonify({'success': True, 'illustration_url': image_data})

if os.environ.get('VERCEL') or not os.access(os.path.dirname(os.path.abspath(__file__)), os.W_OK):
    SAVES_DIR = '/tmp/saves'
else:
    SAVES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')

try:
    os.makedirs(SAVES_DIR, exist_ok=True)
except Exception as e:
    print("Warning creating SAVES_DIR:", e)

GAS_URL = os.environ.get("GOOGLE_SHEET_API_URL", "") or "https://script.google.com/macros/s/AKfycbxFsfnKktu9HEzBBsMdJxlMPAGyKOrxuLYQA3uEHS8BwrIL2aVWPIV2GE-mAmAaIMfPAQ/exec"
KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")
IS_VERCEL_KV = bool(KV_URL and KV_TOKEN)

def safe_korean_filename(name):
    import re
    cleaned = re.sub(r'[^\w\s\-\.\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]', '', name)
    return cleaned.strip()

def get_db_saves():
    raw_saves = []
    if GAS_URL:
        try:
            res = requests.post(GAS_URL, json={"action": "list", "label": "all"}, timeout=15)
            print("GAS Raw Response length:", len(res.text))
            if res.status_code == 200:
                raw_saves = res.json().get("saves", [])
            else:
                print("GAS List failed:", res.text)
        except Exception as e:
            print("GAS List error:", e)
    elif IS_VERCEL_KV:
        headers = {"Authorization": f"Bearer {KV_TOKEN}"}
        try:
            res = requests.post(KV_URL, headers=headers, json=["KEYS", "handout:*"], timeout=5)
            if res.status_code == 200:
                keys = res.json().get("result", [])
                for k in keys:
                    res_val = requests.post(KV_URL, headers=headers, json=["GET", k], timeout=5)
                    if res_val.status_code == 200:
                        raw_data = res_val.json().get("result")
                        if raw_data:
                            try:
                                data = json.loads(raw_data)
                                raw_saves.append({
                                    'filename': k.replace("handout:", ""),
                                    'title': data.get('title', k.replace("handout:", "")),
                                    'mtime': data.get('mtime', 0.0),
                                    'material_type': data.get('material_type', data.get('label', '모의고사')),
                                    'doc_type': data.get('doc_type', '강의용교안'),
                                    'label': data.get('material_type', data.get('label', '모의고사')),
                                    'branch': data.get('branch', '본사')
                                })
                            except Exception:
                                pass
        except Exception as e:
            print("Vercel KV KEYS error:", e)
    else:
        for filename in os.listdir(SAVES_DIR):
            if filename.endswith('.json'):
                path = os.path.join(SAVES_DIR, filename)
                mtime = os.path.getmtime(path)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        saved_data = json.load(f)
                    title = saved_data.get('title', filename[:-5])
                    material_type = saved_data.get('material_type', saved_data.get('label', '모의고사'))
                    doc_type = saved_data.get('doc_type', '강의용교안')
                    branch = saved_data.get('branch', '본사')
                except Exception:
                    title = filename[:-5]
                    material_type = '모의고사'
                    doc_type = '강의용교안'
                    branch = '본사'
                raw_saves.append({
                    'filename': filename,
                    'title': title,
                    'mtime': mtime,
                    'material_type': material_type,
                    'doc_type': doc_type,
                    'label': material_type,
                    'branch': branch
                })

    # Sanitize and filter saves
    clean_saves = []
    ignored_titles = {'시행연도', '시행월', '제목', 'Title', 'title', '비고', '문장데이터', '분석데이터', '등록일시'}
    for s in raw_saves:
        t = (s.get('title') or '').strip()
        mat_type = (s.get('material_type') or s.get('label') or '모의고사').strip()
        doc_type = (s.get('doc_type') or '강의용교안').strip()
        br = (s.get('branch') or '').strip()

        # Skip empty titles or sheet header artifacts
        if not t or t in ignored_titles or mat_type in ignored_titles:
            continue
        if len(t) < 2 and not t.isalnum():
            continue

        if not br or br.lower() == 'admin' or br in ['에이닷 본원', '본원', '본사', 'admin', '본사제작']:
            s['branch'] = '본사'
        else:
            s['branch'] = br

        s['title'] = t
        s['material_type'] = mat_type
        s['doc_type'] = doc_type
        s['label'] = mat_type
        clean_saves.append(s)

    clean_saves.sort(key=lambda x: x.get('mtime', 0.0) or 0.0, reverse=True)
    return clean_saves

def save_db_handout(title, data, label="모의고사", material_type="모의고사", doc_type="강의용교안", branch="기타"):
    filename = safe_korean_filename(title)
    if not filename.endswith('.json'):
        filename += '.json'
    
    data['mtime'] = time.time()
    data['material_type'] = material_type or label or '모의고사'
    data['doc_type'] = doc_type or '강의용교안'
    data['label'] = data['material_type']
    data['branch'] = branch
    
    if GAS_URL:
        payload = {
            "action": "save",
            "material_type": data['material_type'],
            "doc_type": data['doc_type'],
            "label": data['material_type'],
            "title": title,
            "branch": branch,
            "sentence_pairs": data.get("sentence_pairs", []),
            "analysis_data": data.get("analysis_data", {})
        }
        try:
            res = requests.post(GAS_URL, json=payload, timeout=10)
            if res.status_code == 200 and res.json().get("success"):
                return filename
            else:
                raise Exception(f"Google Sheet Save failed: {res.text}")
        except Exception as e:
            raise Exception(f"Google Sheet API error: {str(e)}")
            
    elif IS_VERCEL_KV:
        headers = {"Authorization": f"Bearer {KV_TOKEN}"}
        key = f"handout:{filename}"
        payload = json.dumps(data, ensure_ascii=False)
        res = requests.post(KV_URL, headers=headers, json=["SET", key, payload], timeout=5)
        if res.status_code != 200:
            raise Exception(f"Vercel KV SET failed: {res.text}")
        return filename
    else:
        path = os.path.join(SAVES_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filename

from urllib.parse import unquote

def load_db_handout(filename, label="모의고사", material_type=None, doc_type=None):
    filename = unquote(filename)
    title = filename.replace(".json", "").strip()
    safe_fn = safe_korean_filename(title) + '.json'
        
    if GAS_URL:
        payload = {
            "action": "load",
            "title": title,
            "material_type": material_type or label or '모의고사',
            "doc_type": doc_type or '',
            "label": material_type or label or '모의고사'
        }
        try:
            res = requests.post(GAS_URL, json=payload, timeout=10)
            if res.status_code == 200:
                res_data = res.json()
                if "error" not in res_data:
                    return res_data
            
            # Fallback: Query list to find matching item regardless of label
            list_res = requests.post(GAS_URL, json={"action": "list", "label": "all"}, timeout=10)
            if list_res.status_code == 200:
                all_saves = list_res.json().get("saves", [])
                for item in all_saves:
                    item_title = item.get("title", "")
                    if item_title == title or item.get("filename") == safe_fn or item_title.replace(" ", "") == title.replace(" ", ""):
                        fallback_payload = {
                            "action": "load",
                            "title": item_title,
                            "material_type": item.get("material_type", item.get("label", "")),
                            "doc_type": item.get("doc_type", "")
                        }
                        f_res = requests.post(GAS_URL, json=fallback_payload, timeout=10)
                        if f_res.status_code == 200 and "error" not in f_res.json():
                            return f_res.json()

            raise Exception("저장된 파일을 찾을 수 없습니다.")
        except Exception as e:
            raise Exception(f"Google Sheet Load error: {str(e)}")
            
    elif IS_VERCEL_KV:
        headers = {"Authorization": f"Bearer {KV_TOKEN}"}
        key = f"handout:{filename}"
        # Command: GET key
        res = requests.post(KV_URL, headers=headers, json=["GET", key], timeout=5)
        if res.status_code == 200:
            raw_data = res.json().get("result")
            if not raw_data:
                raise Exception("저장된 파일을 찾을 수 없습니다.")
            return json.loads(raw_data)
        else:
            raise Exception("Vercel KV GET failed")
    else:
        path = os.path.join(SAVES_DIR, filename)
        if not os.path.exists(path):
            raise Exception("저장된 파일을 찾을 수 없습니다.")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

def delete_db_handout(filename, label="모의고사", material_type=None, doc_type=None):
    filename = unquote(filename)
    title = filename.replace(".json", "").strip()
    safe_fn = safe_korean_filename(title) + '.json'
    mat_type = material_type or label or '모의고사'
        
    if GAS_URL:
        payload = {
            "action": "delete",
            "material_type": mat_type,
            "doc_type": doc_type or '',
            "label": mat_type,
            "title": title
        }
        try:
            res = requests.post(GAS_URL, json=payload, timeout=10)
            if res.status_code == 200 and res.json().get("success"):
                return True
            
            # Fallback delete search
            list_res = requests.post(GAS_URL, json={"action": "list", "label": "all"}, timeout=10)
            if list_res.status_code == 200:
                all_saves = list_res.json().get("saves", [])
                for item in all_saves:
                    item_title = item.get("title", "")
                    if item_title == title or item.get("filename") == safe_fn:
                        f_del = requests.post(GAS_URL, json={
                            "action": "delete", 
                            "material_type": item.get("material_type", item.get("label", "")), 
                            "doc_type": item.get("doc_type", ""),
                            "title": item_title
                        }, timeout=10)
                        if f_del.status_code == 200 and f_del.json().get("success"):
                            return True

            raise Exception("Google Sheet Delete failed")
        except Exception as e:
            raise Exception(f"Google Sheet Delete error: {str(e)}")
            
    elif IS_VERCEL_KV:
        headers = {"Authorization": f"Bearer {KV_TOKEN}"}
        key = f"handout:{filename}"
        # Command: DEL key
        res = requests.post(KV_URL, headers=headers, json=["DEL", key], timeout=5)
        if res.status_code != 200:
            raise Exception("Vercel KV DEL failed")
        return True
    else:
        path = os.path.join(SAVES_DIR, filename)
        if not os.path.exists(path):
            raise Exception("저장된 파일을 찾을 수 없습니다.")
        os.remove(path)
        return True

@app.route('/api/saves', methods=['GET'])
def get_saves():
    branch = request.args.get('branch', '').strip()
    mode = request.args.get('mode', 'all').strip()
    try:
        saves = get_db_saves()
        if branch and branch != 'admin':
            if mode == 'my':
                saves = [s for s in saves if s.get('branch') == branch]
            elif mode == 'others':
                saves = [s for s in saves if s.get('branch') != branch]
        return jsonify({'saves': saves})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Token pricing constants (Gemini API standard with USD/KRW 1,380)
# Prompt: $0.075 / 1M tokens, Output: $0.300 / 1M tokens -> Blended: ~0.00035 KRW / token
TOKEN_PRICE_PER_TOKEN_KRW = 0.00035

def estimate_tokens_for_item(doc_type, analysis_data=None, sentence_pairs=None):
    dt = (doc_type or '강의용교안').strip()
    if '변형문제' in dt:
        return 11000  # 9종 변형문제 세트당 약 11,000 토큰
    elif '단어' in dt:
        return 2000   # 15개 어휘 추출 및 단어 테스트 약 2,000 토큰
    else:
        # 강의용 교안: 문장 수 및 구문분석 데이터 크기 반영
        sentence_count = len(sentence_pairs) if sentence_pairs else 7
        return max(4000, min(8000, 3000 + sentence_count * 300))

def get_billing_period_bounds(year, month):
    """
    Returns (start_timestamp, end_timestamp) for the billing cycle in KST.
    Cycle: Previous month 26th 00:00:00 KST to Target month 25th 23:59:59 KST.
    """
    import datetime
    # Target month 25th 23:59:59
    end_dt = datetime.datetime(year, month, 25, 23, 59, 59)
    
    # Previous month 26th 00:00:00
    if month == 1:
        start_dt = datetime.datetime(year - 1, 12, 26, 0, 0, 0)
    else:
        start_dt = datetime.datetime(year, month - 1, 26, 0, 0, 0)
        
    start_ts = start_dt.timestamp()
    end_ts = end_dt.timestamp()
    return start_ts, end_ts, start_dt.strftime('%Y.%m.%d 00:00'), end_dt.strftime('%Y.%m.%d 24:00')

USAGE_LOGS_FILE = os.path.join(SAVES_DIR, 'usage_audit_logs.json')

def append_usage_log(branch, material_type, doc_type, title, tokens=None):
    if tokens is None:
        tokens = estimate_tokens_for_item(doc_type)
    cost = round(tokens * TOKEN_PRICE_PER_TOKEN_KRW, 2)
    log_entry = {
        'id': f"log_{int(time.time()*1000)}",
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'mtime': time.time(),
        'branch': branch or '본사',
        'material_type': material_type or '모의고사',
        'doc_type': doc_type or '강의용교안',
        'title': title,
        'tokens': tokens,
        'cost_krw': cost
    }
    
    # Save to local audit logs
    try:
        logs = []
        if os.path.exists(USAGE_LOGS_FILE):
            with open(USAGE_LOGS_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        logs.append(log_entry)
        with open(USAGE_LOGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[append_usage_log] Error writing local log:", e)

    # Save to GAS RDB_로그 sheet if GAS is available
    if GAS_URL:
        try:
            requests.post(GAS_URL, json={
                "action": "log",
                "branch": log_entry['branch'],
                "material_type": log_entry['material_type'],
                "doc_type": log_entry['doc_type'],
                "title": log_entry['title'],
                "tokens": log_entry['tokens'],
                "cost_krw": log_entry['cost_krw'],
                "timestamp": log_entry['timestamp']
            }, timeout=5)
        except Exception:
            pass

    return log_entry

def get_all_usage_logs():
    """
    Returns all usage logs (from GAS log sheet, local file, and existing saves).
    Logs are permanent and never deleted even if document is deleted.
    """
    logs_map = {}
    
    # 1. From local persistent audit log file
    if os.path.exists(USAGE_LOGS_FILE):
        try:
            with open(USAGE_LOGS_FILE, 'r', encoding='utf-8') as f:
                saved_logs = json.load(f)
                for idx, l in enumerate(saved_logs):
                    unique_id = l.get('id') or f"log_{l.get('branch')}_{l.get('title')}_{l.get('timestamp')}_{idx}"
                    l['id'] = unique_id
                    logs_map[unique_id] = l
        except Exception:
            pass

    # 2. From current saves (ensures existing items without prior audit log are accounted for)
    current_saves = get_db_saves()
    for s in current_saves:
        t = s.get('title', '')
        br = s.get('branch', '본사')
        mat = s.get('material_type', '모의고사')
        doc = s.get('doc_type', '강의용교안')
        mt = s.get('mtime', 0.0)
        tokens = estimate_tokens_for_item(doc)
        cost = round(tokens * TOKEN_PRICE_PER_TOKEN_KRW, 2)
        
        iso_time = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(mt)) if mt > 100000 else time.strftime('%Y-%m-%dT%H:%M:%S')
        save_key = f"save_{br}_{t}_{doc}"
        already_logged = any(l.get('title') == t and l.get('doc_type') == doc and l.get('branch') == br for l in logs_map.values())
        if not already_logged and save_key not in logs_map:
            logs_map[save_key] = {
                'id': save_key,
                'timestamp': iso_time,
                'mtime': mt if mt > 100000 else time.time(),
                'branch': br,
                'material_type': mat,
                'doc_type': doc,
                'title': t,
                'tokens': tokens,
                'cost_krw': cost
            }

    all_logs = list(logs_map.values())
    all_logs.sort(key=lambda x: x.get('mtime', 0.0), reverse=True)
    return all_logs

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        now = time.localtime()
        current_year = int(request.args.get('year', now.tm_year))
        current_month = int(request.args.get('month', now.tm_mon))
        user_branch = request.args.get('branch', '').strip()
        
        # 1. Calculate Billing Period: (M-1)월 26일 00:00:00 ~ M월 25일 23:59:59
        start_ts, end_ts, period_start_str, period_end_str = get_billing_period_bounds(current_year, current_month)
        
        # 2. Retrieve All Permanent Logs
        all_logs = get_all_usage_logs()
        
        # 3. Filter Logs within the Selected Billing Cycle
        period_logs = []
        for l in all_logs:
            mt = l.get('mtime', 0.0)
            if start_ts <= mt <= end_ts:
                period_logs.append(l)

        # 4. Aggregations for the Selected Period
        total_count = len(period_logs)
        total_tokens = sum(l.get('tokens', 0) for l in period_logs)
        total_cost_krw = round(total_tokens * TOKEN_PRICE_PER_TOKEN_KRW, 1)

        exam_count = sum(1 for l in period_logs if '변형문제' in l.get('doc_type', ''))
        vocab_count = sum(1 for l in period_logs if '단어' in l.get('doc_type', ''))
        lecture_count = sum(1 for l in period_logs if '강의용' in l.get('doc_type', ''))
        
        # Branch Aggregations
        branch_stats = {}
        for l in period_logs:
            br = (l.get('branch') or '본사').strip()
            if not br or br.lower() == 'admin' or br in ['본사', '에이닷 본원', '본사제작']:
                br = '본사'
            l['branch'] = br
            if br not in branch_stats:
                branch_stats[br] = {
                    'branch': br,
                    'count': 0,
                    'tokens': 0,
                    'cost_krw': 0.0,
                    'last_active': 0.0
                }
            branch_stats[br]['count'] += 1
            branch_stats[br]['tokens'] += l.get('tokens', 0)
            branch_stats[br]['cost_krw'] = round(branch_stats[br]['tokens'] * TOKEN_PRICE_PER_TOKEN_KRW, 1)
            if l.get('mtime', 0.0) > branch_stats[br]['last_active']:
                branch_stats[br]['last_active'] = l.get('mtime', 0.0)

        # Full nationwide ranking with explicit rank numbers
        full_ranking = sorted(branch_stats.values(), key=lambda x: x['tokens'], reverse=True)
        for idx, item in enumerate(full_ranking, 1):
            item['rank'] = idx

        # Access Control: admin sees all branches; individual branch sees ONLY their own branch
        if user_branch and user_branch != 'admin':
            effective_branch = '본사' if user_branch.lower() == 'admin' else user_branch
            my_logs = [l for l in period_logs if l.get('branch') == effective_branch]
            my_count = len(my_logs)
            my_tokens = sum(l.get('tokens', 0) for l in my_logs)
            my_cost_krw = round(my_tokens * TOKEN_PRICE_PER_TOKEN_KRW, 1)
            visible_ranking = [item for item in full_ranking if item['branch'] == effective_branch]
        else:
            my_logs = period_logs
            my_count = total_count
            my_tokens = total_tokens
            my_cost_krw = total_cost_krw
            visible_ranking = full_ranking

        return jsonify({
            "success": True,
            "is_admin": (user_branch == 'admin'),
            "year": current_year,
            "month": current_month,
            "period": {
                "start": period_start_str,
                "end": period_end_str,
                "label": f"{current_year}년 {current_month}월 정산 주기 ({period_start_str} ~ {period_end_str})"
            },
            "pricing_standard": {
                "token_unit_price_krw": TOKEN_PRICE_PER_TOKEN_KRW,
                "per_1k_tokens_krw": 0.35,
                "exchange_rate": 1380,
                "pricing_desc": "Gemini Flash 모델 기준 (1,000 토큰 당 약 0.35원)"
            },
            "summary": {
                "total_count": total_count,
                "total_tokens": total_tokens,
                "total_cost_krw": total_cost_krw,
                "total_branches": len(branch_stats),
                "exam_count": exam_count,
                "vocab_count": vocab_count,
                "lecture_count": lecture_count,
                "my_count": my_count,
                "my_tokens": my_tokens,
                "my_cost_krw": my_cost_krw
            },
            "branch_ranking": visible_ranking,
            "my_logs": my_logs[:100]  # Max 100 recent entries in period
        })
    except Exception as e:
        print("[get_stats] Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_handout():
    data = request.json or {}
    title = data.get('title', '').strip()
    material_type = data.get('material_type') or data.get('label') or '모의고사'
    doc_type = data.get('doc_type') or '강의용교안'
    branch = data.get('branch', '기타').strip() or '기타'
    if not title:
        return jsonify({'error': '교안 제목이 필요합니다.'}), 400
    try:
        # Persist illustration image to local static file if it's base64 to avoid Google Sheets cell limits
        analysis_d = data.get('analysis_data') or {}
        if 'illustration_url' in analysis_d and analysis_d['illustration_url']:
            analysis_d['illustration_url'] = persist_base64_image(analysis_d['illustration_url'], title)
            data['analysis_data'] = analysis_d

        filename = save_db_handout(title, data, label=material_type, material_type=material_type, doc_type=doc_type, branch=branch)
        try:
            raw_tokens = analysis_d.get('used_tokens') or (analysis_d.get('usage_metadata') or {}).get('total_tokens', 0)
            if raw_tokens and int(raw_tokens) > 0:
                tokens = int(raw_tokens)
            else:
                tokens = estimate_tokens_for_item(doc_type, analysis_d, data.get('sentence_pairs'))
            append_usage_log(branch, material_type, doc_type, title, tokens)
        except Exception as e:
            print("[save_handout] log error:", e)
        return jsonify({'success': True, 'filename': filename, 'illustration_url': analysis_d.get('illustration_url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save/<filename>', methods=['GET'])
def load_handout(filename):
    material_type = request.args.get('material_type') or request.args.get('label') or '모의고사'
    doc_type = request.args.get('doc_type', '')
    try:
        saved_data = load_db_handout(filename, label=material_type, material_type=material_type, doc_type=doc_type)
        return jsonify(saved_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save/<filename>', methods=['DELETE'])
def delete_handout(filename):
    material_type = request.args.get('material_type') or request.args.get('label') or '모의고사'
    doc_type = request.args.get('doc_type', '')
    try:
        delete_db_handout(filename, label=material_type, material_type=material_type, doc_type=doc_type)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 65)
    print(" [강의용 교안 만들기] 로컬 웹 서버를 구동합니다.")
    print(" 주소: http://localhost:5000")
    print("=" * 65)
    app.run(host='0.0.0.0', port=5000, debug=False)
