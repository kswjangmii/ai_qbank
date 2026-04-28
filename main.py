#uv add PyMuPDF google-generativeai pillow
#실행 uv run main.py
#Gemini 1.5 Flash: 하루 20회 요청

import fitz  # PyMuPDF
import google.generativeai as genai
import json
import os
import io
from PIL import Image
import time

# API 키 설정
GENAI_API_KEY = "AIzaSyBRbPzIIBpMCFLADaSvJPYVxQf0H_0M9DM"
genai.configure(api_key=GENAI_API_KEY)

# 빠른 속도와 가성비의 flash 모델 사용
model = genai.GenerativeModel('gemini-2.5-flash')

def extract_questions_and_save_images(pdf_path, output_img_dir="images"):
    # 이미지를 저장할 폴더가 없으면 생성
    os.makedirs(output_img_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    all_questions = []

    # AI에게 지시할 시스템 프롬프트 (좌표 추출 명령 추가)
    prompt = """
    이 이미지는 수학 시험지입니다. 이미지에 있는 모든 문항을 다음 JSON 형식의 배열로 추출해주세요.
    수식과 분수는 반드시 웹에서 렌더링 가능한 LaTeX 포맷($수식$)으로 작성해야 합니다.
    
    [중요] 만약 문제에 그림이나 도표가 포함되어 있다면, 전체 이미지 영역 대비 해당 그림의 위치를 나타내는 Bounding Box 좌표를 [ymin, xmin, ymax, xmax] 형태로 0부터 1000 사이의 정수로 정규화하여 'image_box'에 작성하세요. 그림이 없으면 null입니다.

    [
      {
        "exam_category": "수학 6-2 단원평가",
        "question_number": 숫자,
        "question_text": "문제 본문 (LaTeX 포함)",
        "options": ["보기1", "보기2", ...],
        "answer": "정답",
        "explanation": "해설 (있는 경우만)",
        "image_box": [ymin, xmin, ymax, xmax] 또는 null
      }
    ]
    """

    for page_num in range(len(doc)):
        print(f"--- {page_num + 1} 페이지 텍스트 및 이미지 추출 중 ---")
        page = doc.load_page(page_num)
        
        # 해상도를 높여서 페이지를 이미지로 변환 (잘라낼 때 화질 보존)
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # PIL Image 객체로 변환 (나중에 자르기 위해 보관)
        img_data = pix.tobytes("png")
        page_image = Image.open(io.BytesIO(img_data))

        try:
            # 1. API 호출 (JSON 포맷 강제)
            response = model.generate_content(
                [prompt, page_image],
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                )
            )
            
            # 2. 결과 파싱
            page_data = json.loads(response.text)
            
            # 3. 그림이 있는 경우 이미지 잘라서(Crop) 저장하기
            width, height = page_image.size
            margin = 15  # 자를 때 그림이 너무 꽉 차지 않도록 여백 주기 (픽셀)

            for q in page_data:
                # 좌표가 존재한다면 (그림이 있는 문제라면)
                if q.get("image_box"):
                    ymin, xmin, ymax, xmax = q["image_box"]
                    
                    # 0~1000 스케일을 실제 픽셀 좌표로 변환
                    left = max(0, (xmin / 1000.0) * width - margin)
                    top = max(0, (ymin / 1000.0) * height - margin)
                    right = min(width, (xmax / 1000.0) * width + margin)
                    bottom = min(height, (ymax / 1000.0) * height + margin)
                    
                    # 이미지 크롭 및 저장
                    cropped_img = page_image.crop((left, top, right, bottom))
                    img_filename = f"math_6_2_q{q['question_number']}.png"
                    img_filepath = os.path.join(output_img_dir, img_filename)
                    cropped_img.save(img_filepath)
                    
                    # DB 저장을 위해 파일 경로 업데이트 및 임시 좌표 데이터 삭제
                    q["image_path"] = f"/assets/{output_img_dir}/{img_filename}"
                else:
                    q["image_path"] = None
                
                # DB 스키마에 필요 없는 image_box 키는 삭제
                q.pop("image_box", None)
                all_questions.append(q)
                
        except Exception as e:
            print(f"페이지 {page_num + 1} 처리 중 오류 발생: {e}")
        
        # API 속도 제한 방지
        time.sleep(15) 

    return all_questions

if __name__ == "__main__":
    # PDF 파일 경로 (환경에 맞게 슬래시 방향 확인)
    pdf_file_path = "pdf/6-2_1단원(분수의 나눗셈)_단플(25).pdf"
    
    # 데이터 추출 및 이미지 저장 실행 (images 폴더에 자동 저장됨)
    extracted_data = extract_questions_and_save_images(pdf_file_path, output_img_dir="images")
    
    # JSON 파일 저장
    with open("extracted_questions.json", "w", encoding="utf-8") as f:
        json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        
    print(f"작업 완료! 추출된 문항 데이터는 JSON에, 문제 그림들은 'images' 폴더에 저장되었습니다.")