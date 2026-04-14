import json
from supabase import create_client

# 1. 您的 Supabase 資訊 (已經填入)
url = "https://nvtbhrkbahxhalaugcdn.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im52dGJocmtiYWh4aGFsYXVnY2RuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4NjIxOTUsImV4cCI6MjA5MDQzODE5NX0.LwejsX16O87jw2hiPXdJiQ42ZFR8Xy9B6A8cyhj8GF4"
supabase = create_client(url, key)

# 2. 讀取您的 JSON 檔案
try:
    with open('parking_data.json', 'r', encoding='utf-8') as f:
        parking_data = json.load(f)

    # 3. 批次匯入
    print(f"正在匯入 {len(parking_data)} 筆資料到雲端...")
    response = supabase.table("parking_lots").insert(parking_data).execute()
    print("✅ 匯入成功！現在可以去 Supabase 後台查看資料了。")

except Exception as e:
    print(f"❌ 匯入失敗，原因：{e}")