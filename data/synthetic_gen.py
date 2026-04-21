import json
import asyncio
import os
import sys
from typing import List, Dict
from openai import AsyncOpenAI
from dotenv import load_dotenv
from tqdm.asyncio import tqdm

# Fix for Windows console Unicode errors
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables
load_dotenv()

# Cấu hình Client theo yêu cầu của người dùng (Students updated this)
client = AsyncOpenAI(
    api_key=os.getenv("SHOPAI_APIKEY"), 
    base_url="https://api.shopaikey.com/v1",
    default_headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
)
MODEL_NAME = "qwen3.5-plus"

async def generate_qa_batch(context: str, num_pairs: int = 5) -> List[Dict]:
    """
    TODO: Sử dụng OpenAI/Anthropic API để tạo các cặp (Question, Expected Answer, Context)
    từ đoạn văn bản cho trước.
    Yêu cầu: Tạo ít nhất 1 câu hỏi 'lừa' (adversarial) hoặc cực khó.
    """
    prompt = f"""
    Dựa trên văn bản sau đây, hãy tạo ra {num_pairs} cặp Câu hỏi và Câu trả lời (QA) bằng tiếng Việt.
    Yêu cầu định dạng JSON list:
    [
      {{
        "question": "Câu hỏi cụ thể...",
        "expected_answer": "Câu trả lời đầy đủ dựa trên văn bản...",
        "metadata": {{"difficulty": "easy/medium/hard", "type": "fact-check/reasoning/adversarial"}}
      }}
    ]
    
    Lưu ý:
    - 1 câu hỏi phải là loại 'hard' (suy luận phức tạp).
    - 1 câu trả lời phải là loại 'adversarial' (thử thách Agent).
    - Các câu còn lại là 'easy' (tra cứu sự thật).
    
    Văn bản nguồn:
    {context}
    """
    
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are an expert AI Evaluation Engineer. Output ONLY a valid JSON list."},
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.choices[0].message.content
        # Extract JSON more robustly
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: try to fix common issues or just return empty
            return []
        if isinstance(data, dict) and "tasks" in data: # Some models wrap in a key
            data = data["tasks"]
        elif isinstance(data, dict):
            # Try to find any list in the dict
            for v in data.values():
                if isinstance(v, list):
                    data = v
                    break
        
        # Thêm context và ground_truth_id (giả định dùng tên context làm ID)
        for item in data:
            item["context"] = context
            item["ground_truth_context_ids"] = ["kb_section_" + str(hash(context) % 1000)]
            
        return data
    except Exception as e:
        print(f"Error generating QA: {e}")
        return []

async def main():
    kb_path = "data/knowledge_base.txt"
    if not os.path.exists(kb_path):
        print("Knowledge base not found!")
        return

    with open(kb_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Chia nhỏ văn bản theo các chương (##)
    sections = [s.strip() for s in content.split("##") if s.strip()]
    
    all_qa = []
    print(f"Bắt đầu sinh dữ liệu từ {len(sections)} phân đoạn tài liệu...")
    
    # Sử dụng gather để chạy song song
    results = await tqdm.gather(*[generate_qa_batch(s, num_pairs=8) for s in sections])
    for batch in results:
        all_qa.extend(batch)
        
    # Lưu kết quả
    output_path = "data/golden_set.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for item in all_qa:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
    print(f"\n Hoàn thành! Đã tạo {len(all_qa)} test cases chất lượng.")
    print(f" File lưu tại: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
