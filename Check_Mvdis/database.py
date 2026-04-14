import datetime
from config import supabase, line_bot_api

PARKING_CACHE = []

def reload_parking_data():
    try:
        response = supabase.table("parking_lots").select("*").execute()
        PARKING_CACHE.clear()
        PARKING_CACHE.extend(response.data or [])
        print(f"✅ 同步完成！載入 {len(PARKING_CACHE)} 筆停車場資料。")
    except Exception as e:
        print(f"❌ 快取載入失敗: {e}")

# --- 車輛管理 ---
def add_car(line_id, name, mode, pid, plate, birthday=""):
    data = {
        "line_id": line_id, "name": name, "mode": mode,
        "pid": pid.upper().strip(), "plate": plate.upper().strip(),
        "birthday": birthday, "display_name": get_line_user_name(line_id)
    }
    supabase.table("cars").insert(data).execute()

def check_car_exists(line_id, mode, value_to_check):
    clean_val = value_to_check.upper().strip()
    query = supabase.table("cars").select("id", count="exact").eq("line_id", line_id)
    res = query.eq("pid", clean_val).execute() if mode == "1" else query.eq("plate", clean_val).execute()
    return res.count > 0

def get_user_cars(line_id):
    res = supabase.table("cars").select("*").eq("line_id", line_id).execute()
    return [{
        "db_id": row['id'], "name": row['name'], "mode": "legal" if row['mode'] == "2" else "personal",
        "id": row['pid'], "plate_no": row['plate'], 
        "sub_id": row['plate'] if row['mode'] == "2" else row['birthday'],
        "display_id": row['pid']
    } for row in res.data]

def delete_specific_car(line_id, car_db_id):
    res = supabase.table("cars").delete().eq("id", car_db_id).eq("line_id", line_id).execute()
    return len(res.data) > 0

def get_car_by_id(car_db_id):
    """取得特定 ID 的單一車輛資料"""
    res = supabase.table("cars").select("*").eq("id", car_db_id).execute()
    
    if res.data:
        row = res.data[0]
        return {
            "db_id": row['id'],
            "name": row['name'],
            "mode": "legal" if row['mode'] == "2" else "personal",
            "id": row['pid'],      
            "plate_no": row['plate'], 
            "sub_id": row['plate'] if row['mode'] == "2" else row['birthday'],
            "display_id": row['pid']
        }
    return None

def get_user_car_by_id(line_id, car_db_id):
    """只取得屬於該使用者的特定車輛資料"""
    res = supabase.table("cars").select("*").eq("id", car_db_id).eq("line_id", line_id).execute()
    if not res.data:
        return None

    row = res.data[0]
    return {
        "db_id": row['id'],
        "name": row['name'],
        "mode": "legal" if row['mode'] == "2" else "personal",
        "id": row['pid'],
        "plate_no": row['plate'],
        "sub_id": row['plate'] if row['mode'] == "2" else row['birthday'],
        "display_id": row['pid']
    }

# --- 排程管理 ---
def set_schedule(line_id, s_type, value, user_name):
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    data = {"line_id": line_id, "type": s_type, "value": value, "last_run": yesterday, "display_name": user_name}
    supabase.table("schedules").upsert(data, on_conflict="line_id").execute()

def get_schedule(line_id):
    res = supabase.table("schedules").select("type, value").eq("line_id", line_id).execute()
    return (res.data[0]['type'], res.data[0]['value']) if res.data else None

def update_last_run(line_id):
    today = datetime.date.today().strftime("%Y-%m-%d")
    supabase.table("schedules").update({"last_run": today}).eq("line_id", line_id).execute()

def delete_schedule(line_id):
    # 刪除排程
    supabase.table("schedules").delete().eq("line_id", line_id).execute()
    print(f"🗑️ 已刪除 {line_id} 的排程")

def get_all_schedules():
    res = supabase.table("schedules").select("line_id, type, value, last_run").execute()
    return [(r['line_id'], r['type'], r['value'], r['last_run']) for r in res.data]

def get_line_user_name(user_id):
    try: return line_bot_api.get_profile(user_id).display_name
    except: return "未知用戶"
