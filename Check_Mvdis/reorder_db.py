import sqlite3

DB_NAME = "users_cars.db"

def reorder_all_tables():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    print("🚀 開始重組資料庫欄位順序...")

    # ==========================================
    # 1. 處理 Schedules 表格
    # ==========================================
    print("\n[1/2] 正在處理 'schedules' 表格...")
    try:
        # 1. 將舊表改名
        c.execute("ALTER TABLE schedules RENAME TO schedules_old")

        # 2. 建立新表 (display_name 排第一)
        c.execute('''CREATE TABLE schedules
                     (display_name TEXT,
                      line_id TEXT PRIMARY KEY,
                      type TEXT,
                      value TEXT,
                      last_run TEXT)''')

        # 3. 複製資料
        c.execute('''INSERT INTO schedules (display_name, line_id, type, value, last_run)
                     SELECT display_name, line_id, type, value, last_run
                     FROM schedules_old''')

        # 4. 刪除舊表
        c.execute("DROP TABLE schedules_old")
        print("✅ 'schedules' 重組完成！(display_name -> line_id...)")

    except Exception as e:
        print(f"⚠️ 'schedules' 處理跳過或失敗: {e}")
        # 如果失敗(例如表不存在)，嘗試復原名稱以免資料遺失
        try: c.execute("ALTER TABLE schedules_old RENAME TO schedules")
        except: pass

    # ==========================================
    # 2. 處理 Cars 表格
    # ==========================================
    print("\n[2/2] 正在處理 'cars' 表格...")
    try:
        # 1. 將舊表改名
        c.execute("ALTER TABLE cars RENAME TO cars_old")

        # 2. 建立新表 (display_name 排第二，在 id 之後)
        c.execute('''CREATE TABLE cars
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      display_name TEXT,
                      line_id TEXT NOT NULL,
                      name TEXT,
                      mode TEXT,
                      pid TEXT,
                      plate TEXT,
                      birthday TEXT)''')

        # 3. 複製資料
        # 注意：我們明確指定欄位對應，確保舊資料正確填入新位置
        c.execute('''INSERT INTO cars (id, display_name, line_id, name, mode, pid, plate, birthday)
                     SELECT id, display_name, line_id, name, mode, pid, plate, birthday
                     FROM cars_old''')

        # 4. 刪除舊表
        c.execute("DROP TABLE cars_old")
        print("✅ 'cars' 重組完成！(id -> display_name -> line_id...)")

    except Exception as e:
        print(f"⚠️ 'cars' 處理跳過或失敗: {e}")
        try: c.execute("ALTER TABLE cars_old RENAME TO cars")
        except: pass

    conn.commit()
    conn.close()
    print("\n🎉 資料庫重組作業結束。")

if __name__ == "__main__":
    reorder_all_tables()