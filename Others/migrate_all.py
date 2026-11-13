import sqlite3
from supabase import create_client

# 設定資訊 (務必加上 .strip() 防止之前的編碼錯誤)
SUPABASE_URL = "https://nvtbhrkbahxhalaugcdn.supabase.co".strip()
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im52dGJocmtiYWh4aGFsYXVnY2RuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4NjIxOTUsImV4cCI6MjA5MDQzODE5NX0.LwejsX16O87jw2hiPXdJiQ42ZFR8Xy9B6A8cyhj8GF4".strip()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def migrate_table(table_name):
    try:
        conn = sqlite3.connect('users_cars.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 讀取 SQLite 資料
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        if not rows:
            print(f"表 {table_name} 是空的，跳過。")
            return

        # 轉成 List of Dictionaries
        data = []
        for row in rows:
            d = dict(row)
            # 如果 SQLite 有 id 欄位，在匯入 Supabase 時建議移除 id 
            # 讓 Supabase 的 SERIAL 自動生成，避免衝突
            if 'id' in d:
                del d['id']
            data.append(d)

        print(f"正在搬移 {table_name} 共 {len(data)} 筆資料...")
        
        # 批次寫入 Supabase
        supabase.table(table_name).insert(data).execute()
        print(f"✅ {table_name} 搬移成功！")

    except Exception as e:
        print(f"❌ {table_name} 搬移失敗: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # 分別搬移兩張表
    migrate_table("cars")
    migrate_table("schedules")