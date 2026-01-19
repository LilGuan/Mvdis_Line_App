import sqlite3

DB_NAME = "users_cars.db"

def add_column():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        # 幫 schedules 表新增 display_name 欄位
        c.execute("ALTER TABLE schedules ADD COLUMN display_name TEXT")
        print("✅ 成功新增 display_name 欄位到 schedules 表")
    except sqlite3.OperationalError:
        print("⚠️ schedules 表可能已經有 display_name 欄位了 (略過)")

    try:
        # 順便幫 cars 表也新增 (方便你辨識車主)
        c.execute("ALTER TABLE cars ADD COLUMN display_name TEXT")
        print("✅ 成功新增 display_name 欄位到 cars 表")
    except sqlite3.OperationalError:
        print("⚠️ cars 表可能已經有 display_name 欄位了 (略過)")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    add_column()