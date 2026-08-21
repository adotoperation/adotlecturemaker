import os
from flask import Flask, render_template, request, jsonify, Response
from parser_engine import parse_english_passage, modify_analysis_with_prompt
from pdf_generator import create_lecture_handout_pdf

app = Flask(__name__)

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

@app.route('/')
def index():
    return render_template('index.html', default_api_key=DEFAULT_API_KEY)

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

if __name__ == '__main__':
    print("=" * 65)
    print(" [강의용 교안 만들기] 로컬 웹 서버를 구동합니다.")
    print(" 주소: http://localhost:5000")
    print("=" * 65)
    app.run(host='0.0.0.0', port=5000, debug=False)
