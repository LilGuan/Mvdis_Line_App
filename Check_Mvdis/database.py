import datetime
import re
from config import (
    supabase, line_bot_api, ADMIN_UUID,
    NORMAL_DAILY_QUERY_LIMIT, QUERY_USAGE_RESET_HOUR, NORMAL_MAX_CARS
)

PARKING_CACHE = []

VIP_TABLE = "vip_users"
USAGE_TABLE = "user_query_usage"
RESERVATION_MONITOR_SETTINGS_TABLE = "reservation_monitor_settings"
_reservation_settings_supabase_available = True

def reload_parking_data():
    try:
        response = supabase.table("parking_lots").select("*").execute()
        PARKING_CACHE.clear()
        PARKING_CACHE.extend(response.data or [])
        print(f"✅ 同步完成！載入 {len(PARKING_CACHE)} 筆停車場資料。")
    except Exception as e:
        print(f"❌ 快取載入失敗: {e}")

# --- 會員 / 使用量管理 ---
def taipei_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=8)

def current_usage_date(now=None):
    now = now or taipei_now()
    if now.hour < QUERY_USAGE_RESET_HOUR:
        now = now - datetime.timedelta(days=1)
    return now.date().isoformat()

def is_admin_user(line_id):
    return line_id == ADMIN_UUID

def is_vip_user(line_id):
    if is_admin_user(line_id):
        return True
    try:
        res = (
            supabase.table(VIP_TABLE)
            .select("line_id,is_active")
            .eq("line_id", line_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        print(f"⚠️ VIP 查詢失敗，請確認 Supabase 已建立 {VIP_TABLE}: {e}")
        return False

def upsert_vip_user(line_id, display_name="", note="", created_by=""):
    data = {
        "line_id": line_id,
        "display_name": display_name or "",
        "note": note or "",
        "is_active": True,
        "created_by": created_by or "",
        "updated_at": taipei_now().isoformat(),
    }
    supabase.table(VIP_TABLE).upsert(data, on_conflict="line_id").execute()

def disable_vip_user(line_id):
    data = {"is_active": False, "updated_at": taipei_now().isoformat()}
    supabase.table(VIP_TABLE).update(data).eq("line_id", line_id).execute()

def set_vip_active(line_id, is_active):
    data = {"is_active": bool(is_active), "updated_at": taipei_now().isoformat()}
    supabase.table(VIP_TABLE).update(data).eq("line_id", line_id).execute()

def delete_vip_user(line_id):
    supabase.table(VIP_TABLE).delete().eq("line_id", line_id).execute()

def list_vip_users(include_inactive=False):
    try:
        query = supabase.table(VIP_TABLE).select("line_id,display_name,note,is_active,created_at,updated_at")
        if not include_inactive:
            query = query.eq("is_active", True)
        res = query.order("created_at", desc=False).execute()
        return res.data or []
    except Exception as e:
        print(f"⚠️ VIP 列表讀取失敗: {e}")
        return []

def get_manual_query_usage(line_id):
    usage_date = current_usage_date()
    try:
        res = (
            supabase.table(USAGE_TABLE)
            .select("manual_query_count")
            .eq("line_id", line_id)
            .eq("usage_date", usage_date)
            .limit(1)
            .execute()
        )
        if not res.data:
            return 0, usage_date
        return int(res.data[0].get("manual_query_count") or 0), usage_date
    except Exception as e:
        print(f"⚠️ 查詢使用量失敗，請確認 Supabase 已建立 {USAGE_TABLE}: {e}")
        return 0, usage_date

def get_remaining_manual_queries(line_id):
    if is_vip_user(line_id):
        return None
    used, _ = get_manual_query_usage(line_id)
    return max(NORMAL_DAILY_QUERY_LIMIT - used, 0)

def can_start_manual_query(line_id):
    if is_vip_user(line_id):
        return True, "VIP 無限制"
    used, usage_date = get_manual_query_usage(line_id)
    if used >= NORMAL_DAILY_QUERY_LIMIT:
        return False, f"今天手動查詢次數已用完（{used}/{NORMAL_DAILY_QUERY_LIMIT}）。每日早上 {QUERY_USAGE_RESET_HOUR}:00 會重新計算。"
    remaining = NORMAL_DAILY_QUERY_LIMIT - used
    return True, f"今日查詢剩餘 {remaining} 次。"

def record_manual_query(line_id):
    if is_vip_user(line_id):
        return None
    used, usage_date = get_manual_query_usage(line_id)
    data = {
        "line_id": line_id,
        "usage_date": usage_date,
        "manual_query_count": used + 1,
        "updated_at": taipei_now().isoformat(),
    }
    try:
        supabase.table(USAGE_TABLE).upsert(data, on_conflict="line_id,usage_date").execute()
        return used + 1
    except Exception as e:
        print(f"⚠️ 使用量寫入失敗，請確認 Supabase 已建立 {USAGE_TABLE}: {e}")
        raise

def get_normal_max_cars():
    return NORMAL_MAX_CARS

def get_reservation_monitor_setting(setting_key="default"):
    global _reservation_settings_supabase_available
    if not _reservation_settings_supabase_available:
        return None
    try:
        res = (
            supabase.table(RESERVATION_MONITOR_SETTINGS_TABLE)
            .select("setting_key,active,min_fare,areas,date_mode,date_value,frequency_min_sec,frequency_max_sec,updated_at,updated_by")
            .eq("setting_key", setting_key)
            .limit(1)
            .execute()
        )
        return (res.data or [None])[0]
    except Exception as e:
        _reservation_settings_supabase_available = False
        print(f"⚠️ 55688 Supabase 設定讀取失敗，改用本機設定: {e}")
        return None

def upsert_reservation_monitor_setting(settings, updated_by="", setting_key="default"):
    global _reservation_settings_supabase_available
    if not _reservation_settings_supabase_available:
        return False
    try:
        data = {
            "setting_key": setting_key,
            "active": bool(settings.get("active")),
            "min_fare": int(settings.get("min_fare") or 0),
            "areas": settings.get("areas") or [],
            "date_mode": settings.get("date_mode") or "all",
            "date_value": settings.get("date_value") or "",
            "frequency_min_sec": int(settings.get("frequency_min_sec") or 50),
            "frequency_max_sec": int(settings.get("frequency_max_sec") or 70),
            "updated_by": updated_by or "",
            "updated_at": taipei_now().isoformat(),
        }
        supabase.table(RESERVATION_MONITOR_SETTINGS_TABLE).upsert(
            data,
            on_conflict="setting_key"
        ).execute()
        return True
    except Exception as e:
        _reservation_settings_supabase_available = False
        print(f"⚠️ 55688 Supabase 設定寫入失敗，已保留本機設定: {e}")
        return False

# --- 車輛管理 ---
def normalize_plate_value(value):
    return re.sub(r'[^A-Z0-9]', '', (value or '').upper())

def format_plate_value(value):
    clean = normalize_plate_value(value)
    if "-" in (value or ""):
        return value.upper().strip()
    if len(clean) > 4:
        return f"{clean[:-4]}-{clean[-4:]}"
    return clean

def add_car(line_id, name, mode, pid, plate, birthday=""):
    data = {
        "line_id": line_id, "name": name, "mode": mode,
        "pid": pid.upper().strip(), "plate": format_plate_value(plate),
        "birthday": birthday, "display_name": get_line_user_name(line_id)
    }
    supabase.table("cars").insert(data).execute()

def check_car_exists(line_id, mode, value_to_check):
    clean_val = value_to_check.upper().strip()
    if mode == "2":
        res = supabase.table("cars").select("id, plate").eq("line_id", line_id).execute()
        clean_plate = normalize_plate_value(value_to_check)
        return any(normalize_plate_value(row.get("plate")) == clean_plate for row in (res.data or []))
    query = supabase.table("cars").select("id", count="exact").eq("line_id", line_id)
    res = query.eq("pid", clean_val).execute() if mode == "1" else query.eq("plate", clean_val).execute()
    return res.count > 0

def check_car_exists_except(line_id, mode, value_to_check, car_db_id):
    """檢查同一使用者是否還有其他車輛使用相同的證號/車牌"""
    clean_val = value_to_check.upper().strip()
    if mode == "2":
        res = supabase.table("cars").select("id, plate").eq("line_id", line_id).neq("id", car_db_id).execute()
        clean_plate = normalize_plate_value(value_to_check)
        return any(normalize_plate_value(row.get("plate")) == clean_plate for row in (res.data or []))
    query = supabase.table("cars").select("id", count="exact").eq("line_id", line_id).neq("id", car_db_id)
    res = query.eq("pid", clean_val).execute() if mode == "1" else query.eq("plate", clean_val).execute()
    return res.count > 0

def get_user_cars(line_id):
    res = supabase.table("cars").select("*").eq("line_id", line_id).execute()
    return [{
        "db_id": row['id'], "name": row['name'], "mode": "legal" if row['mode'] == "2" else "personal",
        "id": row['pid'] or "未設定", "plate_no": format_plate_value(row['plate']), 
        "sub_id": format_plate_value(row['plate']) if row['mode'] == "2" else row['birthday'],
        "display_id": row['pid']
    } for row in res.data]

def delete_specific_car(line_id, car_db_id):
    res = supabase.table("cars").delete().eq("id", car_db_id).eq("line_id", line_id).execute()
    return len(res.data) > 0

def update_car(line_id, car_db_id, name, mode, pid, plate, birthday=""):
    data = {
        "line_id": line_id,
        "name": name,
        "mode": mode,
        "pid": pid.upper().strip(),
        "plate": format_plate_value(plate),
        "birthday": birthday,
        "display_name": get_line_user_name(line_id),
    }
    try:
        supabase.table("cars").update(data).eq("id", car_db_id).eq("line_id", line_id).execute()
        return True
    except Exception as e:
        print(f"❌ 更新車輛失敗: {e}")
        return False

def get_car_by_id(car_db_id):
    """取得特定 ID 的單一車輛資料"""
    res = supabase.table("cars").select("*").eq("id", car_db_id).execute()
    
    if res.data:
        row = res.data[0]
        return {
            "db_id": row['id'],
            "name": row['name'],
            "mode": "legal" if row['mode'] == "2" else "personal",
            "id": row['pid'] or "未設定",      
            "plate_no": format_plate_value(row['plate']), 
            "sub_id": format_plate_value(row['plate']) if row['mode'] == "2" else row['birthday'],
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
        "id": row['pid'] or "未設定",
        "plate_no": format_plate_value(row['plate']),
        "sub_id": format_plate_value(row['plate']) if row['mode'] == "2" else row['birthday'],
        "display_id": row['pid']
    }

# --- 排程管理 ---
def set_schedule(line_id, s_type, value, user_name):
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    data = {
        "line_id": (line_id or "").strip(),
        "type": (s_type or "").strip(),
        "value": str(value or "").strip(),
        "last_run": yesterday,
        "display_name": user_name,
    }
    supabase.table("schedules").upsert(data, on_conflict="line_id").execute()

def get_schedule(line_id):
    res = supabase.table("schedules").select("type, value").eq("line_id", (line_id or "").strip()).execute()
    return (res.data[0]['type'].strip(), str(res.data[0]['value']).strip()) if res.data else None

def update_last_run(line_id):
    today = datetime.date.today().strftime("%Y-%m-%d")
    supabase.table("schedules").update({"last_run": today}).eq("line_id", (line_id or "").strip()).execute()

def delete_schedule(line_id):
    # 刪除排程
    line_id = (line_id or "").strip()
    supabase.table("schedules").delete().eq("line_id", line_id).execute()
    print(f"🗑️ 已刪除 {line_id} 的排程")

def get_all_schedules():
    res = supabase.table("schedules").select("line_id, type, value, last_run").execute()
    return [
        (
            (r.get('line_id') or '').strip(),
            (r.get('type') or '').strip(),
            str(r.get('value') or '').strip(),
            str(r.get('last_run') or '').strip(),
        )
        for r in (res.data or [])
    ]

def get_line_user_name(user_id):
    try: return line_bot_api.get_profile(user_id).display_name
    except: return "未知用戶"
