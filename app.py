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

            p_load = {
                "title": t_name,
                "label": "변형문제",
                "branch": branch,
                "sentence_pairs": sentence_pairs,
                "analysis_data": {
                    "title": t_name,
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
            f_name = save_db_handout(t_name, p_load, label='변형문제', branch=branch)
            return {"title": t_name, "filename": f_name, "questions": q_data, "question_order": shuffled_order, "branch": branch}

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

@app.route('/api/modify', methods=['POST'])
def modify():
    data = request.json or {}
    analysis_data = data.get('analysis_data', {})
    modify_prompt = data.get('modify_prompt', '').strip()

    if not analysis_data or 'sentences' not in analysis_data:
        return jsonify({'error': '먼저 교안 생성을 실행해 주세요.'}), 400

    if not modify_prompt:
        return jsonify({'error': '수정 프롬프트를 입력해 주세요.'}), 400

    try:
        updated_data = modify_analysis_with_prompt(analysis_data, modify_prompt)
        return jsonify(updated_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-pdf', methods=['POST'])
def export_pdf():
    data = request.json or {}
    if not data or 'sentences' not in data:
        return jsonify({'error': '유효한 분석 데이터가 없습니다.'}), 400

    try:
        pdf_bytes = create_lecture_handout_pdf(data)
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': 'attachment; filename="lecture_handout.pdf"'
            }
        )
    except Exception as e:
        print("PDF export error:", e)
        return jsonify({'error': f'PDF 생성 실패: {str(e)}'}), 500

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
    # Keep Korean, alphanumeric, spaces, hyphens, underscores, dots
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
                                    'label': data.get('label', '모의고사'),
                                    'branch': data.get('branch', '본사제작')
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
                    label = saved_data.get('label', '모의고사')
                    branch = saved_data.get('branch', '본사제작')
                except Exception:
                    title = filename[:-5]
                    label = '모의고사'
                    branch = '본사제작'
                raw_saves.append({
                    'filename': filename,
                    'title': title,
                    'mtime': mtime,
                    'label': label,
                    'branch': branch
                })

    # Sanitize and filter saves
    clean_saves = []
    ignored_titles = {'시행연도', '시행월', '제목', 'Title', 'title', '비고', '문장데이터', '분석데이터', '등록일시'}
    for s in raw_saves:
        t = (s.get('title') or '').strip()
        lbl = (s.get('label') or '').strip()
        
        # Skip empty titles or sheet header artifacts
        if not t or t in ignored_titles or lbl in ignored_titles:
            continue
        if len(t) < 2 and not t.isalnum():
            continue

        br = (s.get('branch') or '').strip()
        if not br or br.lower() == 'admin' or br in ['에이닷 본원', '본원', '본사', 'admin']:
            s['branch'] = '본사제작'
        else:
            s['branch'] = br

        clean_saves.append(s)

    clean_saves.sort(key=lambda x: x.get('mtime', 0.0) or 0.0, reverse=True)
    return clean_saves

def save_db_handout(title, data, label="모의고사", branch="기타"):
    filename = safe_korean_filename(title)
    if not filename.endswith('.json'):
        filename += '.json'
    
    data['mtime'] = time.time()
    data['label'] = label
    data['branch'] = branch
    
    if GAS_URL:
        payload = {
            "action": "save",
            "label": label,
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
        # Command: SET key value
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

def load_db_handout(filename, label="모의고사"):
    filename = unquote(filename)
    title = filename.replace(".json", "").strip()
    safe_fn = safe_korean_filename(title) + '.json'
        
    if GAS_URL:
        # 1. Try with given label
        payload = {
            "action": "load",
            "label": label,
            "title": title
        }
        try:
            res = requests.post(GAS_URL, json=payload, timeout=10)
            if res.status_code == 200:
                res_data = res.json()
                if "error" not in res_data:
                    return res_data
            
            # 2. Fallback: Query list to find matching item regardless of label
            list_res = requests.post(GAS_URL, json={"action": "list", "label": "all"}, timeout=10)
            if list_res.status_code == 200:
                all_saves = list_res.json().get("saves", [])
                for item in all_saves:
                    item_title = item.get("title", "")
                    if item_title == title or item.get("filename") == safe_fn or item_title.replace(" ", "") == title.replace(" ", ""):
                        real_label = item.get("label", label)
                        fallback_payload = {
                            "action": "load",
                            "label": real_label,
                            "title": item_title
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

def delete_db_handout(filename, label="모의고사"):
    filename = unquote(filename)
    title = filename.replace(".json", "").strip()
    safe_fn = safe_korean_filename(title) + '.json'
        
    if GAS_URL:
        payload = {
            "action": "delete",
            "label": label,
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
                        real_label = item.get("label", label)
                        f_del = requests.post(GAS_URL, json={"action": "delete", "label": real_label, "title": item_title}, timeout=10)
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

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        saves = get_db_saves()
        total_count = len(saves)
        
        label_counts = {
            "교과서": 0,
            "모의고사": 0,
            "부교재": 0,
            "변형문제": 0,
            "단어테스트": 0,
            "기타": 0
        }
        
        branch_counts = {}
        branch_recent = {}
        
        for s in saves:
            lbl = s.get('label', '기타')
            if lbl in label_counts:
                label_counts[lbl] += 1
            else:
                label_counts["기타"] += 1
                
            br = s.get('branch', '에이닷 본원').strip() or '에이닷 본원'
            branch_counts[br] = branch_counts.get(br, 0) + 1
            
            mtime = s.get('mtime', 0)
            if br not in branch_recent or mtime > branch_recent[br]:
                branch_recent[br] = mtime
                
        branch_ranking = []
        for br, cnt in sorted(branch_counts.items(), key=lambda x: x[1], reverse=True):
            branch_ranking.append({
                "branch": br,
                "count": cnt,
                "last_active": branch_recent.get(br, 0)
            })
            
        return jsonify({
            "success": True,
            "total_count": total_count,
            "total_branches": len(branch_counts),
            "label_counts": label_counts,
            "branch_ranking": branch_ranking
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_handout():
    data = request.json or {}
    title = data.get('title', '').strip()
    label = data.get('label', '모의고사').strip()
    branch = data.get('branch', '기타').strip() or '기타'
    if not title:
        return jsonify({'error': '교안 제목이 필요합니다.'}), 400
    try:
        filename = save_db_handout(title, data, label=label, branch=branch)
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save/<filename>', methods=['GET'])
def load_handout(filename):
    label = request.args.get('label', '모의고사').strip()
    try:
        saved_data = load_db_handout(filename, label=label)
        return jsonify(saved_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save/<filename>', methods=['DELETE'])
def delete_handout(filename):
    label = request.args.get('label', '모의고사').strip()
    try:
        delete_db_handout(filename, label=label)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 65)
    print(" [강의용 교안 만들기] 로컬 웹 서버를 구동합니다.")
    print(" 주소: http://localhost:5000")
    print("=" * 65)
    app.run(host='0.0.0.0', port=5000, debug=False)
