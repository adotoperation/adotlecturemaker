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
GAS_URL = os.environ.get("GOOGLE_SHEET_API_URL", "") or "https://script.google.com/macros/s/AKfycbxFsfnKktu9HEzBBsMdJxlMPAGyKOrxuLYQA3uEHS8BwrIL2aVWPIV2GE-mAmAaIMfPAQ/exec"

app = Flask(__name__)

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'has_api_key': bool(DEFAULT_API_KEY),
        'api_key': DEFAULT_API_KEY
    })

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    return render_template('index.html', default_api_key=DEFAULT_API_KEY)

@app.route('/favicon.ico')
def favicon():
    svg_icon = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='#4f46e5'><path d='M12 3L1 9l11 6 9-4.91V17h2V9L12 3z'/><path d='M5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82z'/></svg>"""
    return Response(svg_icon, mimetype='image/svg+xml')

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

    clean_u = username.lower().replace('지점', '').strip()
    if clean_u in ['admin', '관리자', '본사']:
        return jsonify({'success': True, 'username': 'admin'})

    clean_branch = re.sub(r'지점$', '', username).strip() or username
    return jsonify({'success': True, 'username': clean_branch})

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
        title_clean = re.sub(r'\s*-\s*(?:9종\s*)?변형문제.*$', '', title).strip()
        title_clean = re.sub(r'\s*-\s*단어(?:TEST|테스트).*$', '', title_clean).strip()
        title_clean = re.sub(r'\s*강의용교안.*$', '', title_clean).strip()
        title_1 = f"{title_clean} - 변형문제 1차"
        title_2 = f"{title_clean} - 변형문제 2차"
        folder_name = data.get('folder_name') or extract_default_folder_name(title_clean, material_type)

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
                "folder_name": folder_name,
                "material_type": material_type,
                "doc_type": doc_type_val,
                "label": material_type,
                "branch": branch,
                "sentence_pairs": sentence_pairs,
                "analysis_data": {
                    "title": t_name,
                    "folder_name": folder_name,
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
            f_name = save_db_handout(t_name, p_load, label=material_type, material_type=material_type, doc_type=doc_type_val, branch=branch, folder_name=folder_name)
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
        title = '영어 지문 분석'

    if sentence_pairs and isinstance(sentence_pairs, list) and len(sentence_pairs) > 0:
        en_list = [p.get('english', '').strip() for p in sentence_pairs if p.get('english', '').strip()]
        kr_list = [p.get('korean', '').strip() for p in sentence_pairs if p.get('korean', '').strip()]
        if en_list:
            passage = " ".join(en_list)
            korean_passage = "\n".join(kr_list)
    else:
        sentence_pairs = []

    if not passage:
        return jsonify({'error': '영어 지문을 입력해 주세요.'}), 400

    try:
        result = parse_english_passage(
            passage=passage,
            korean_passage=korean_passage,
            title=title,
            api_key=api_key,
            use_ai=use_ai,
            sentence_pairs=sentence_pairs
        )
        
        # Return analysis immediately without blocking on heavy image generation
        # (Frontend loads illustration asynchronously via /api/generate_illustration)
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
        elif 'svg' in header:
            ext = 'svg'
        
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

def create_themed_svg_illustration(topic_text, title=""):
    """Generates an aesthetic SVG illustration matching the exact topic when external AI APIs are unreachable."""
    clean_t = (topic_text or title or "영어 지문 독해").strip()
    import hashlib
    h = hashlib.md5(clean_t.encode('utf-8')).hexdigest()[:10]
    filename = f"illu_svg_{h}.svg"
    filepath = os.path.join(UPLOADS_DIR, filename)

    is_plant = any(k in clean_t.lower() for k in ["식물", "방어", "곤충", "공진화", "plant", "insect", "defense", "잎", "화합물"])
    is_building = any(k in clean_t.lower() for k in ["빌딩", "skyscraper", "와류", "vortex", "건축"])
    is_remote = any(k in clean_t.lower() for k in ["원격", "remote", "근무", "직원", "청년"])
    is_culture = any(k in clean_t.lower() for k in ["스펙터클", "spectacle", "문화", "culture", "공연", "연극"])

    if is_plant:
        bg_gradient = 'linear-gradient(135deg, #134e4a 0%, #065f46 50%, #047857 100%)'
        accent_color = '#34d399'
        badge_text = 'BOTANICAL DEFENSE & COEVOLUTION'
        icon_path = '<path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" fill="#6ee7b7"/>'
    elif is_building:
        bg_gradient = 'linear-gradient(135deg, #1e293b 0%, #334155 50%, #0f172a 100%)'
        accent_color = '#38bdf8'
        badge_text = 'ARCHITECTURE & AERODYNAMICS'
        icon_path = '<rect x="4" y="2" width="16" height="20" rx="2" fill="#38bdf8" fill-opacity="0.6"/>'
    elif is_remote:
        bg_gradient = 'linear-gradient(135deg, #312e81 0%, #4338ca 50%, #1e1b4b 100%)'
        accent_color = '#a5b4fc'
        badge_text = 'MODERN WORKPLACE & COLLABORATION'
        icon_path = '<circle cx="12" cy="8" r="5" fill="#a5b4fc"/><path d="M3 21v-2a7 7 0 0 1 14 0v2" stroke="#a5b4fc" stroke-width="2"/>'
    else:
        bg_gradient = 'linear-gradient(135deg, #4c0519 0%, #881337 50%, #be123c 100%)'
        accent_color = '#fda4af'
        badge_text = 'ACADEMIC READING PASSAGE'
        icon_path = '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20v-14H6.5A2.5 2.5 0 0 0 4 5.5v14Z" fill="#fda4af"/>'

    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 480" width="800" height="480">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e1b4b"/>
      <stop offset="50%" stop-color="#312e81"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
  </defs>
  <rect width="800" height="480" fill="url(#bg)" rx="16"/>
  <circle cx="150" cy="100" r="180" fill="{accent_color}" fill-opacity="0.12" filter="blur(40px)"/>
  <circle cx="680" cy="380" r="220" fill="{accent_color}" fill-opacity="0.15" filter="blur(50px)"/>
  
  <rect x="50" y="50" width="700" height="380" rx="14" fill="none" stroke="{accent_color}" stroke-opacity="0.3" stroke-width="1.5"/>
  
  <g transform="translate(400, 160)" text-anchor="middle">
    <rect x="-140" y="-30" width="280" height="32" rx="16" fill="{accent_color}" fill-opacity="0.2"/>
    <text x="0" y="-9" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="12" font-weight="900" fill="{accent_color}" letter-spacing="2">{badge_text}</text>
  </g>

  <g transform="translate(400, 245)" text-anchor="middle">
    <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="24" font-weight="900" fill="#ffffff">{clean_t[:32]}</text>
    <text x="0" y="45" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" font-size="14" font-weight="500" fill="#cbd5e1">에이닷 영어학원 맞춤형 내신 분석 교안</text>
  </g>
</svg>'''

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        return f"/static/uploads/{filename}"
    except Exception as e:
        print("[create_themed_svg_illustration] Error saving svg:", e)
        return '/static/illustration.jpg'

def generate_illustration_sync(title, topic, keywords, summary, passage, branch="본사", material_type="모의고사", api_key="", scene_en=""):
    api_key = api_key or DEFAULT_API_KEY
    combined_context = f"Title: {title}\nSubject/Topic: {topic}\nKeywords: {keywords}\nSummary: {summary}\nPassage: {passage[:300]}"
    
    english_scene = scene_en.strip() if (scene_en and "ghibli" in scene_en.lower()) else ""
    if not english_scene and api_key:
        try:
            prompt_trans = f"""[System Role]
You are an expert AI prompt engineer specialized in translating English educational reading passages into single, highly descriptive English image generation prompts for Studio Ghibli-style textbook illustrations.

[Core Objectives]
1. Read and analyze the input English text passage to extract its core historical, scientific, or psychological context and communicative message.
2. Translate abstract ideas or non-verbal concepts from the text into concrete, visual metaphors (e.g., body language, subtle lighting, atmospheric details, symbolic elements).
3. Output ONLY a final, single English image generation prompt optimized for AI image models. Do not include conversational filler, headings, or markdown blocks.

[Strict Constraints for Image Generation Prompt]
1. Style Requirements: Studio Ghibli watercolor and colored pencil illustration, hand-drawn textures, soft pastel tones, cozy and warm atmosphere, cinematic lighting, detailed background.
2. Intellectual Property (IP) Restrictions: Absolutely NO copyrighted characters, creatures, or specific items (e.g., Totoro, No-Face, recognizable branded objects, or proprietary fictional characters). Use original, generic background characters and safe symbolic elements only.
3. Text & Layout Restrictions: Absolutely NO text, NO letters, NO words, NO typography, NO speech bubbles, and NO watermarks in the generated image.
4. Scene Composition: Focus on original characters, actions, or visual analogies that directly reflect the core theme of the input passage without violating any copyright.

[Input Data]
Lesson Topic: {topic}
Title: {title}
Keywords: {keywords}
3-Step Summary:
{summary}
Reading Passage:
{passage[:500]}

[Task]
Output ONLY the final English image generation prompt string without any introductory or conversational text."""


            for model_cand in ["gemini-3.7-flash", "gemini-2.5-flash"]:
                try:
                    url_text = f"https://generativelanguage.googleapis.com/v1beta/models/{model_cand}:generateContent?key={api_key}"
                    resp = requests.post(url_text, json={"contents": [{"parts": [{"text": prompt_trans}]}]}, timeout=10)
                    if resp.status_code == 200:
                        english_scene = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                        english_scene = re.sub(r'[\r\n"]+', ' ', english_scene).strip()
                        if english_scene:
                            break
                except Exception as cand_e:
                    print(f"[generate_illustration_sync] Model {model_cand} try error:", cand_e)
        except Exception as e:
            print("[generate_illustration_sync] Scene description warning:", e)

    if not english_scene:
        clean_t = re.sub(r'[\d년월고호번\-]+', '', f"{topic} {summary} {title}").strip()
        if any(w in clean_t.lower() for w in ["보존", "보전", "복원", "원형", "계몽주의", "유물", "역사", "유산", "conservation", "preservation", "restoration", "enlightenment", "heritage", "monument", "historic"]):
            english_scene = "An archivist and historical conservator gently restoring ancient manuscripts and classical stone artifacts inside a sunlit 18th-century library workshop with tall arched windows, soft pastel tones, cozy scholarly atmosphere"
        elif any(w in clean_t.lower() for w in ["몸집", "낙상", "부상", "뼈", "골절", "충격", "성인", "사고", "체격", "아기", "fall", "injury", "size", "bone", "scale", "fracture", "weight", "gravity", "biological", "physics", "toddler", "bear", "squirrel"]):
            english_scene = "In a deep lush ancient forest along a winding dirt path filled with moss and wildflowers, a comical scene unfolds where a large brown bear wearing a scarf clumsily slips backward landing with a thud and a surprised grimace, while a tiny nimble red squirrel happily completes a light tumble-roll landing safely unharmed in soft dappled sunlight"
        elif any(w in clean_t.lower() for w in ["식물", "방어", "곤충", "공진화", "화합물", "가시", "plant", "insect", "defense", "predator", "toxin"]):
            english_scene = "In a vibrant magical sunlit botanical greenhouse filled with ancient ferns and moss, exotic lush plants deploy natural defensive mechanisms with waxy dew-covered leaves and protective thorns, as colorful curious beetles gently flutter around under warm golden sunbeams"
        elif any(w in clean_t.lower() for w in ["빌딩", "skyscraper", "와류", "vortex", "건축"]):
            english_scene = "In a breezy coastal metropolis with fantastical retro-futuristic architecture, a soaring aerodynamic skyscraper gracefully deflects swirling wind currents with gentle curved corners, visible pastel wind vortex streams flowing like ribbons under fluffy white clouds"
        elif any(w in clean_t.lower() for w in ["스펙터클", "spectacle", "문화", "culture", "공연", "연극", "관객"]):
            english_scene = "Inside a grand atmospheric vintage theatre with ornate wooden balconies and warm lantern glow, a magical theatrical stage performance captivates a fascinated audience with glowing fairy lights and expressive performers blending tradition and innovation"
        elif any(w in clean_t.lower() for w in ["원격", "remote", "재택", "하이브리드", "근무", "직원", "청년"]):
            english_scene = "Inside a cozy sunlit wooden attic studio filled with potted green plants and bookshelves, a young creative professional in a warm sweater works comfortably on a vintage laptop next to a steaming teacup, looking thoughtfully out an arched window"
        elif any(w in clean_t.lower() for w in ["미술", "art", "수집", "collector", "gallery", "화가"]):
            english_scene = "An art collector and gallery curator thoughtfully viewing classical impressionist landscape paintings inside a warm sunlit museum gallery hall with polished oak floors"
        else:
            english_scene = f"A whimsical fairytale scene representing {clean_t[:25]} with soft dappled sunlight and lush nature"

    # Assemble ultimate 2D Studio Ghibli prompt with heavy 2D cel tokens at the front and negative constraints at the back
    clean_scene = re.sub(r'[\r\n"]+', ' ', english_scene).strip()
    ghibli_prompt = (
        f"2D traditional animation cel, anime background art, Studio Ghibli aesthetic, "
        f"Hayao Miyazaki style painting, hand-drawn watercolor and colored pencil on textured paper, "
        f"delicate ink line art, soft cel shading. {clean_scene}. "
        f"Warm golden hour dappled sunlight filtering through, cozy nostalgic atmosphere, soft pastel palette. "
        f"Strictly NO photorealism, NO photo, NO 3D render, NO CGI, NO live-action, NO glossy gradient, "
        f"NO text, NO speech bubbles, NO words, NO letters, NO labels, NO watermark, masterpiece 2D artwork."
    )
    print(f"\n[GHIBLI IMAGE PROMPT LOG] Final Prompt to Image Model:\n{ghibli_prompt}\n")

    saved_path = None
    if api_key:
        # Native Gemini 3.7 Flash & Multimodal Image Generation Models (Google AI API)
        image_models = ["gemini-3.7-flash-image", "gemini-3.7-flash", "gemini-3.1-flash-image", "gemini-2.5-flash-image", "gemini-3-pro-image"]
        for img_model in image_models:
            try:
                print(f"[GHIBLI IMAGE ENGINE] Requesting image generation with model: {img_model}")
                img_url = f"https://generativelanguage.googleapis.com/v1beta/models/{img_model}:generateContent?key={api_key}"
                img_payload = {
                    "contents": [{"parts": [{"text": ghibli_prompt}]}],
                    "generationConfig": {
                        "responseModalities": ["IMAGE"]
                    }
                }
                res = requests.post(img_url, json=img_payload, timeout=25)
                if res.status_code == 200:
                    cand = res.json().get('candidates', [{}])[0]
                    parts = cand.get('content', {}).get('parts', [])
                    for p in parts:
                        if 'inlineData' in p:
                            b64_img = p['inlineData'].get('data')
                            mime = p['inlineData'].get('mimeType', 'image/png')
                            if b64_img:
                                raw_data_url = f"data:{mime};base64,{b64_img}"
                                saved_path = persist_base64_image(raw_data_url, title)
                                if saved_path:
                                    break
                    if saved_path:
                        break
            except Exception as e:
                print(f"[generate_illustration_sync] {img_model} warning:", e)

    if not saved_path:
        try:
            import urllib.parse
            import hashlib
            import base64
            clean_seed = abs(int(hashlib.md5(f"{english_scene}_{title}".encode()).hexdigest()[:8], 16)) % 999999
            enc_prompt = urllib.parse.quote(ghibli_prompt)
            poll_url = f"https://image.pollinations.ai/prompt/{enc_prompt}?width=800&height=480&nologo=true&seed={clean_seed}"
            
            p_res = requests.get(poll_url, timeout=10)
            if p_res.status_code == 200 and len(p_res.content) > 1000:
                b64_str = base64.b64encode(p_res.content).decode('utf-8')
                raw_data_url = f"data:image/jpeg;base64,{b64_str}"
                saved_path = persist_base64_image(raw_data_url, title)
        except Exception as poll_e:
            print("[generate_illustration_sync] Pollinations AI warning:", poll_e)

    if not saved_path:
        # Fallback to authentic hand-drawn Ghibli watercolor illustration
        saved_path = '/static/illustration.jpg'

    if saved_path:
        try:
            append_usage_log(branch, material_type, 'AI삽화생성', f"{title} (삽화생성)", 2500)
        except Exception:
            pass
        return saved_path, ghibli_prompt

    return '/static/illustration.jpg', ghibli_prompt

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
    
    saved_path, ghibli_prompt = generate_illustration_sync(
        title=title,
        topic=topic,
        keywords=keywords,
        summary=summary,
        passage=passage,
        branch=branch,
        material_type=material_type,
        api_key=api_key
    )
    return jsonify({'success': True, 'illustration_url': saved_path, 'prompt': ghibli_prompt})

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

def extract_default_folder_name(title, material_type="모의고사"):
    title = (title or '').strip()
    if not title:
        return f"{material_type} 기본 폴더"
    # Clean sub-material suffixes (변형문제, 단어TEST, 강의용교안)
    clean_t = re.sub(r'\s*-\s*(?:9종\s*)?변형문제.*$', '', title).strip()
    clean_t = re.sub(r'\s*-\s*단어(?:TEST|테스트).*$', '', clean_t).strip()
    clean_t = re.sub(r'\s*강의용교안.*$', '', clean_t).strip()
    
    # Match patterns like: "26년 고3 3월 모의고사 32번" -> "26년 고3 3월 모의고사"
    m = re.match(r'^(.*?)\s+(?:[0-9]{1,3}번|본문\s*\d+|Q\d+|\d+문항)$', clean_t, re.IGNORECASE)
    if m and len(m.group(1).strip()) > 3:
        return m.group(1).strip()
    m2 = re.search(r'(\d+년\s*(?:[고중]\d\s*)?\d+월\s*모의고사)', clean_t)
    if m2:
        return m2.group(1).strip()
    m3 = re.search(r'([가-힣A-Za-z0-9]+\s*[IV1-4]?\s*[가-힣()]+\s*\d+과)', clean_t)
    if m3:
        return m3.group(1).strip()
    return f"{material_type} - {clean_t[:15]}" if len(clean_t) > 15 else (clean_t or f"{material_type} 기본 폴더")

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
            res = requests.post(GAS_URL, json={"action": "list", "label": "all"}, timeout=10)
            if res.status_code == 200:
                raw_saves = res.json().get("saves", [])
        except Exception as e:
            print("GAS list error, fallback to local SAVES_DIR:", e)
            raw_saves = []
            
    if not raw_saves:
        if IS_VERCEL_KV:
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
                                    title_val = data.get('title', k.replace("handout:", ""))
                                    mat_val = data.get('material_type', data.get('label', '모의고사'))
                                    raw_saves.append({
                                        'filename': k.replace("handout:", ""),
                                        'title': title_val,
                                        'folder_name': data.get('folder_name') or extract_default_folder_name(title_val, mat_val),
                                        'mtime': data.get('mtime', 0.0),
                                        'material_type': mat_val,
                                        'doc_type': data.get('doc_type', '강의용교안'),
                                        'label': mat_val,
                                        'branch': data.get('branch', '본사')
                                    })
                                except Exception:
                                    pass
            except Exception as e:
                print("Vercel KV KEYS error:", e)
        else:
            for filename in os.listdir(SAVES_DIR):
                if filename.endswith('.json') and not filename.startswith('usage_audit'):
                    path = os.path.join(SAVES_DIR, filename)
                    mtime = os.path.getmtime(path)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            saved_data = json.load(f)
                        title = saved_data.get('title', filename[:-5])
                        material_type = saved_data.get('material_type', saved_data.get('label', '모의고사'))
                        doc_type = saved_data.get('doc_type', '강의용교안')
                        branch = saved_data.get('branch', '본사')
                        folder_name = saved_data.get('folder_name') or extract_default_folder_name(title, material_type)
                    except Exception:
                        title = filename[:-5]
                        material_type = '모의고사'
                        doc_type = '강의용교안'
                        branch = '본사'
                        folder_name = extract_default_folder_name(title, material_type)
                    raw_saves.append({
                        'filename': filename,
                        'title': title,
                        'folder_name': folder_name,
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
        folder_n = (s.get('folder_name') or extract_default_folder_name(t, mat_type)).strip()

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
        s['folder_name'] = folder_n
        clean_saves.append(s)

    clean_saves.sort(key=lambda x: x.get('mtime', 0.0) or 0.0, reverse=True)
    return clean_saves

def save_db_handout(title, data, label="모의고사", material_type="모의고사", doc_type="강의용교안", branch="기타", folder_name=None):
    filename = safe_korean_filename(title)
    if not filename.endswith('.json'):
        filename += '.json'
    
    mat_type = material_type or label or '모의고사'
    folder = folder_name or data.get('folder_name') or extract_default_folder_name(title, mat_type)
    data['folder_name'] = folder
    data['mtime'] = time.time()
    data['material_type'] = mat_type
    data['doc_type'] = doc_type or '강의용교안'
    data['label'] = mat_type
    data['branch'] = branch
    
    # Ensure illustration_url is preserved and persisted as file if base64
    illu_url = data.get('illustration_url') or (data.get('analysis_data') and data['analysis_data'].get('illustration_url')) or (data.get('analysis_data') and isinstance(data['analysis_data'].get('summary_info'), dict) and data['analysis_data']['summary_info'].get('illustration_url'))
    if illu_url:
        if str(illu_url).startswith('data:image/'):
            illu_url = persist_base64_image(illu_url, title)
        data['illustration_url'] = illu_url
        if 'analysis_data' in data and isinstance(data['analysis_data'], dict):
            data['analysis_data']['illustration_url'] = illu_url
            if 'summary_info' in data['analysis_data'] and isinstance(data['analysis_data']['summary_info'], dict):
                data['analysis_data']['summary_info']['illustration_url'] = illu_url

    # Always persist local cache copy so illustration is instantly retrievable
    try:
        path = os.path.join(SAVES_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[save_db_handout] Local cache write error:", e)

    if GAS_URL:
        payload = {
            "action": "save",
            "material_type": mat_type,
            "doc_type": data['doc_type'],
            "label": mat_type,
            "folder_name": folder,
            "title": title,
            "branch": branch,
            "sentence_pairs": data.get("sentence_pairs", []),
            "analysis_data": data.get("analysis_data", {}),
            "illustration_url": illu_url or ''
        }
        try:
            res = requests.post(GAS_URL, json=payload, timeout=10)
            if res.status_code == 200 and res.json().get("success"):
                return filename
            else:
                print(f"[save_db_handout] Google Sheet Save response: {res.text}")
        except Exception as e:
            print(f"[save_db_handout] Google Sheet API error: {str(e)}")
            
    if IS_VERCEL_KV:
        headers = {"Authorization": f"Bearer {KV_TOKEN}"}
        key = f"handout:{filename}"
        payload = json.dumps(data, ensure_ascii=False)
        res = requests.post(KV_URL, headers=headers, json=["SET", key, payload], timeout=5)
        if res.status_code != 200:
            raise Exception(f"Vercel KV SET failed: {res.text}")
        return filename
    else:
        return filename

from urllib.parse import unquote

def load_db_handout(filename, label="모의고사", material_type=None, doc_type=None):
    filename = unquote(filename)
    title = filename.replace(".json", "").strip()
    safe_fn = safe_korean_filename(title) + '.json'
    doc_res = None
        
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
                    doc_res = res_data
            
            if not doc_res:
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
                                doc_res = f_res.json()
                                break

            if not doc_res:
                raise Exception("저장된 파일을 찾을 수 없습니다.")
        except Exception as e:
            print(f"[load_db_handout] Google Sheet load error, checking local cache: {str(e)}")
            
    if not doc_res:
        if IS_VERCEL_KV:
            headers = {"Authorization": f"Bearer {KV_TOKEN}"}
            key = f"handout:{filename}"
            res = requests.post(KV_URL, headers=headers, json=["GET", key], timeout=5)
            if res.status_code == 200:
                raw_data = res.json().get("result")
                if raw_data:
                    doc_res = json.loads(raw_data)
        else:
            path = os.path.join(SAVES_DIR, filename)
            if not (path and os.path.exists(path)):
                if not filename.endswith('.json'):
                    path = os.path.join(SAVES_DIR, safe_fn)
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    doc_res = json.load(f)
            else:
                for fname in os.listdir(SAVES_DIR):
                    if fname.endswith('.json') and not fname.startswith('usage_audit'):
                        try:
                            fpath = os.path.join(SAVES_DIR, fname)
                            with open(fpath, 'r', encoding='utf-8') as jf:
                                cdoc = json.load(jf)
                            if cdoc.get('title') == title or cdoc.get('title') == filename or fname == filename or fname == safe_fn:
                                doc_res = cdoc
                                break
                        except Exception:
                            pass

    if doc_res and isinstance(doc_res, dict):
        analysis_data = doc_res.get('analysis_data') or {}
        if isinstance(analysis_data, str):
            try:
                analysis_data = json.loads(analysis_data)
                doc_res['analysis_data'] = analysis_data
            except Exception:
                pass
        
        illu = (
            doc_res.get('illustration_url') or 
            (isinstance(analysis_data, dict) and analysis_data.get('illustration_url')) or 
            (isinstance(analysis_data, dict) and isinstance(analysis_data.get('summary_info'), dict) and analysis_data['summary_info'].get('illustration_url'))
        )
        
        # Fallback to local cache file if GAS cell didn't store illustration
        if not illu:
            local_path = os.path.join(SAVES_DIR, safe_fn)
            if os.path.exists(local_path):
                try:
                    with open(local_path, 'r', encoding='utf-8') as lf:
                        local_doc = json.load(lf)
                        illu = local_doc.get('illustration_url') or (local_doc.get('analysis_data') and local_doc['analysis_data'].get('illustration_url'))
                except Exception:
                    pass

        if illu:
            doc_res['illustration_url'] = illu
            if isinstance(analysis_data, dict):
                analysis_data['illustration_url'] = illu
                if isinstance(analysis_data.get('summary_info'), dict):
                    analysis_data['summary_info']['illustration_url'] = illu
                doc_res['analysis_data'] = analysis_data
    return doc_res

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
    
    import datetime
    kst_tz = datetime.timezone(datetime.timedelta(hours=9))
    now_kst = datetime.datetime.now(kst_tz)
    now_ts = time.time()
    
    log_entry = {
        'id': f"log_{int(now_ts * 1000)}",
        'timestamp': now_kst.strftime('%Y-%m-%dT%H:%M:%S'),
        'mtime': now_ts,
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
    folder_name = data.get('folder_name', '').strip()
    if not title:
        return jsonify({'error': '교안 제목이 필요합니다.'}), 400
    try:
        # Persist illustration image to local static file if it's base64 to avoid Google Sheets cell limits
        analysis_d = data.get('analysis_data') or {}
        if 'illustration_url' in analysis_d and analysis_d['illustration_url']:
            analysis_d['illustration_url'] = persist_base64_image(analysis_d['illustration_url'], title)
            data['analysis_data'] = analysis_d

        filename = save_db_handout(title, data, label=material_type, material_type=material_type, doc_type=doc_type, branch=branch, folder_name=folder_name)
        try:
            raw_tokens = analysis_d.get('used_tokens') or (analysis_d.get('usage_metadata') or {}).get('total_tokens', 0)
            if raw_tokens and int(raw_tokens) > 0:
                tokens = int(raw_tokens)
            else:
                tokens = estimate_tokens_for_item(doc_type, analysis_d, data.get('sentence_pairs'))
            append_usage_log(branch, material_type, doc_type, title, tokens)
        except Exception as e:
            print("[save_handout] log error:", e)
        return jsonify({'success': True, 'filename': filename, 'folder_name': data.get('folder_name'), 'illustration_url': analysis_d.get('illustration_url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folders', methods=['GET'])
def get_folders():
    try:
        saves = get_db_saves()
        material_filter = request.args.get('material_type', '').strip()
        branch_filter = request.args.get('branch', '').strip()
        mode = request.args.get('mode', 'all').strip()

        if branch_filter and branch_filter != 'admin':
            if mode == 'my':
                saves = [s for s in saves if s.get('branch') == branch_filter]
            elif mode == 'others':
                saves = [s for s in saves if s.get('branch') != branch_filter]

        folders_dict = {}
        for s in saves:
            mat = s.get('material_type') or '모의고사'
            if material_filter and material_filter != 'all' and mat != material_filter:
                continue
            folder_name = s.get('folder_name') or extract_default_folder_name(s.get('title', ''), mat)
            key = f"{mat}:::{folder_name}"
            if key not in folders_dict:
                folders_dict[key] = {
                    'key': key,
                    'folder_name': folder_name,
                    'material_type': mat,
                    'count': 0,
                    'mtime': 0.0,
                    'items': []
                }
            folders_dict[key]['count'] += 1
            folders_dict[key]['items'].append(s)
            if s.get('mtime', 0.0) > folders_dict[key]['mtime']:
                folders_dict[key]['mtime'] = s.get('mtime', 0.0)

        folder_list = list(folders_dict.values())
        folder_list.sort(key=lambda x: x.get('mtime', 0.0), reverse=True)
        return jsonify({'success': True, 'folders': folder_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folder/rename', methods=['POST'])
def rename_folder():
    data = request.json or {}
    old_folder = data.get('old_folder', '').strip()
    new_folder = data.get('new_folder', '').strip()
    material_type = data.get('material_type', '').strip()
    if not old_folder or not new_folder:
        return jsonify({'error': '이전 폴더명과 새 폴더명이 필요합니다.'}), 400

    try:
        count = 0
        if not GAS_URL:
            for filename in os.listdir(SAVES_DIR):
                if filename.endswith('.json') and not filename.startswith('usage_audit'):
                    path = os.path.join(SAVES_DIR, filename)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            saved = json.load(f)
                        cur_folder = saved.get('folder_name') or extract_default_folder_name(saved.get('title', ''), saved.get('material_type', '모의고사'))
                        cur_mat = saved.get('material_type', '모의고사')
                        if cur_folder == old_folder and (not material_type or cur_mat == material_type):
                            saved['folder_name'] = new_folder
                            with open(path, 'w', encoding='utf-8') as f:
                                json.dump(saved, f, ensure_ascii=False, indent=2)
                            count += 1
                    except Exception:
                        pass
        return jsonify({'success': True, 'updated_count': count, 'new_folder': new_folder})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/folder/delete', methods=['POST'])
def delete_folder():
    data = request.json or {}
    folder_name = data.get('folder_name', '').strip()
    material_type = data.get('material_type', '').strip()
    if not folder_name:
        return jsonify({'error': '폴더명이 필요합니다.'}), 400

    try:
        saves = get_db_saves()
        deleted = 0
        for s in saves:
            cur_folder = s.get('folder_name')
            cur_mat = s.get('material_type')
            if cur_folder == folder_name and (not material_type or cur_mat == material_type):
                delete_db_handout(s.get('filename'), label=cur_mat, material_type=cur_mat, doc_type=s.get('doc_type'))
                deleted += 1
        return jsonify({'success': True, 'deleted_count': deleted})
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

@app.route('/api/handout/update_meta', methods=['POST'])
def update_handout_meta():
    data = request.json or {}
    old_title = data.get('old_title', '').strip()
    old_filename = data.get('filename', '').strip()
    new_title = data.get('new_title', '').strip()
    new_folder = data.get('new_folder', '').strip()
    material_type = data.get('material_type', '모의고사').strip()
    doc_type = data.get('doc_type', '강의용교안').strip()
    branch = data.get('branch', '본사').strip()
    
    if not new_title:
        return jsonify({'error': '새로운 자료 제목을 입력해 주세요.'}), 400
        
    try:
        fn_to_load = old_filename or old_title
        doc = load_db_handout(fn_to_load, label=material_type, material_type=material_type, doc_type=doc_type)
        
        # If title changed, delete old record
        if old_title and old_title != new_title:
            try:
                delete_db_handout(fn_to_load, label=material_type, material_type=material_type, doc_type=doc_type)
            except Exception as del_e:
                print(f"[update_handout_meta] Old item delete note: {del_e}")
                
        doc['title'] = new_title
        doc['folder_name'] = new_folder or extract_default_folder_name(new_title, material_type)
        if doc.get('analysis_data') and isinstance(doc['analysis_data'], dict):
            doc['analysis_data']['title'] = new_title
            doc['analysis_data']['folder_name'] = doc['folder_name']
            
        saved_fn = save_db_handout(
            title=new_title,
            data=doc,
            label=material_type,
            material_type=material_type,
            doc_type=doc_type,
            branch=doc.get('branch', branch),
            folder_name=doc['folder_name']
        )
        return jsonify({'success': True, 'filename': saved_fn, 'title': new_title, 'folder_name': doc['folder_name']})
    except Exception as e:
        print(f"[update_handout_meta] Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 65)
    print(" [강의용 교안 만들기] 로컬 웹 서버를 구동합니다.")
    print(" 주소: http://localhost:5000")
    print("=" * 65)
    app.run(host='0.0.0.0', port=5000, debug=False)
