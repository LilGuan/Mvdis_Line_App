import warnings

warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+")

from flask import Flask, request, abort
import threading
from geopy.distance import geodesic
import time
import datetime
import json
import os
import random
import re
import requests
import uuid
from pathlib import Path
from urllib.parse import parse_qs

import config as app_config
import crawler_utils as crawler_utils_module
from config import (
    handler, line_bot_api, MV_DIS_URL, ADMIN_UUID, DEFAULT_HERO_IMAGE,
    TAIWANTAXI_DISPATCH_TOKEN, TAIWANTAXI_RESERVATION_MONITOR_ENABLED,
    TAIWANTAXI_RESERVATION_MIN_FARE,
    TAIWANTAXI_SELECTED_AREAS, TAIWANTAXI_RESERVATION_QA_MODE,
    TAXIGO_DRIVER_JWT, TAXIGO_DRIVER_UUID, TAXIGO_DRIVER_APP_VERSION,
    TAXIGO_DRIVER_BUILD_NUMBER, TAXIGO_DRIVER_USER_AGENT,
    TAXIGO_DRIVER_RESERVATION_MONITOR_ENABLED, TAXIGO_DRIVER_RESERVATION_MIN_FARE,
)
from database import (
    reload_parking_data, PARKING_CACHE, add_car, check_car_exists,
    check_car_exists_except, get_user_cars, get_user_car_by_id, delete_specific_car, update_car,
    set_schedule, get_schedule, delete_schedule,
    update_last_run, get_all_schedules, get_line_user_name,
    is_admin_user, is_vip_user, upsert_vip_user, delete_vip_user,
    set_vip_active, list_vip_users,
    can_start_manual_query, record_manual_query, get_remaining_manual_queries,
    get_normal_max_cars,
    get_reservation_monitor_setting, upsert_reservation_monitor_setting
)
from ui_templates import (
    create_parking_flex, create_car_list_flex, 
    create_car_selection_flex, create_fine_flex_message, create_plate_flex,
    create_ride_compare_flex, create_vip_list_flex, create_vip_request_flex,
    create_flight_region_flex, create_flight_city_flex, create_flight_result_flex,
    create_55688_reservation_demo_flex, create_55688_settings_flex,
    create_55688_area_settings_flex, create_taxigo_driver_reservation_flex,
    create_taxigo_driver_settings_flex
)
from ride_compare import build_location, compare_ride_fares
from trip_flights import (
    FLIGHT_REGIONS, get_cities_by_region, get_city, get_region,
    normalize_flight_no, search_flights, search_flights_by_number, today_taipei_date
)
from crawler_utils import (
    new_chrome, send_loading_animation, prepare_page_mode, get_captcha_and_solve,
    execute_query, get_taipei_photos, upload_to_imgbb, get_new_taipei_photos,get_taoyuan_photos,
    get_all_pages_data, crawl_plate_numbers, get_ai_appeal_advice,
    set_crawler_mode, get_55688_reservation
)
from linebot.models import (
    FollowEvent, MessageEvent, TextMessage, TextSendMessage, LocationMessage, LocationAction,
    PostbackEvent, QuickReply, QuickReplyButton, MessageAction, ImageSendMessage
)
from linebot.exceptions import LineBotApiError
from dotenv import set_key

app = Flask(__name__)

# --- 全域變數：處理綁定流程的狀態機 ---
user_sessions = {}
edit_car_sessions = {}
ride_compare_sessions = {}
flight_search_sessions = {}
ai_analysis_cache = {}

# 排程查罰單最多同時開啟 5 個 Selenium session；超出的任務會等待席位。
SCHEDULE_CRAWLER_MAX_CONCURRENCY = 5
schedule_crawler_slots = threading.BoundedSemaphore(SCHEDULE_CRAWLER_MAX_CONCURRENCY)

# --- 共用元件：取消按鈕 ---
cancel_menu = QuickReply(items=[QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消"))])

member_apply_menu = QuickReply(items=[
    QuickReplyButton(action=MessageAction(label="申請一般會員", text="申請一般會員")),
    QuickReplyButton(action=MessageAction(label="VIP會員", text="VIP會員")),
])

def build_welcome_message():
    return TextSendMessage(
        text=(
            "歡迎加入交通違規罰單通知。\n\n"
            "請先選擇會員類型：\n"
            "一般會員：送出後由管理員審核。\n"
            "VIP會員：送出後由管理員審核，核准後開通 VIP 功能。"
        ),
        quick_reply=member_apply_menu
    )

def build_vip_help_text():
    return (
        "VIP 管理指令：\n"
        "VIP新增 <LINE_ID> [備註]\n"
        "VIP刪除 <LINE_ID>\n"
        "VIP列表\n"
        "VIP狀態\n\n"
        "只有管理員可以新增、修改、刪除 VIP。"
    )

def handle_vip_command(user_id, msg, reply_token):
    if msg in ("VIP", "VIP管理", "VIP幫助"):
        if is_admin_user(user_id):
            line_bot_api.reply_message(reply_token, TextSendMessage(text=build_vip_help_text()))
        else:
            status = "VIP" if is_vip_user(user_id) else "一般用戶"
            remaining = get_remaining_manual_queries(user_id)
            usage_text = "手動查詢無上限" if remaining is None else f"今日剩餘手動查詢 {remaining} 次"
            line_bot_api.reply_message(reply_token, TextSendMessage(text=f"目前身分：{status}\n{usage_text}"))
        return True

    if msg == "VIP狀態":
        status = "VIP" if is_vip_user(user_id) else "一般用戶"
        remaining = get_remaining_manual_queries(user_id)
        usage_text = "手動查詢無上限" if remaining is None else f"今日剩餘手動查詢 {remaining} 次"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"目前身分：{status}\n{usage_text}"))
        return True

    if not msg.startswith("VIP"):
        return False

    if not is_admin_user(user_id):
        line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ 只有管理員可以管理 VIP。"))
        return True

    parts = msg.split(maxsplit=2)
    command = parts[0]

    if command in ("VIP新增", "VIP修改"):
        if len(parts) < 2:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入：VIP新增 <LINE_ID> [備註]"))
            return True
        target_id = parts[1].strip()
        note = parts[2].strip() if len(parts) >= 3 else ""
        try:
            display_name = get_line_user_name(target_id)
            if display_name == "未知用戶" and note:
                display_name = note
            upsert_vip_user(target_id, display_name=display_name, note=note or "VIP", created_by=user_id)
            line_bot_api.reply_message(reply_token, TextSendMessage(text=f"✅ 已設定 VIP：{target_id}"))
        except Exception as e:
            print(f"❌ VIP 設定失敗: {e}")
            line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ VIP 設定失敗，請先確認 Supabase 已建立 vip_users 表。"))
        return True

    if command == "VIP刪除":
        if len(parts) < 2:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入：VIP刪除 <LINE_ID>"))
            return True
        target_id = parts[1].strip()
        if target_id == ADMIN_UUID:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="⚠️ 管理員帳號不可刪除。"))
            return True
        try:
            delete_vip_user(target_id)
            line_bot_api.reply_message(reply_token, TextSendMessage(text=f"🗑️ 已刪除 VIP：{target_id}"))
        except Exception as e:
            print(f"❌ VIP 移除失敗: {e}")
            line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ VIP 移除失敗，請先確認 Supabase 已建立 vip_users 表。"))
        return True

    if command == "VIP列表":
        rows = list_vip_users(include_inactive=True)
        if not rows:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="目前沒有 VIP 資料。"))
            return True
        line_bot_api.reply_message(reply_token, create_vip_list_flex(rows[:12], admin_line_id=ADMIN_UUID))
        return True

    line_bot_api.reply_message(reply_token, TextSendMessage(text=build_vip_help_text()))
    return True

def handle_vip_application(user_id, reply_token):
    return handle_member_application(user_id, reply_token, "vip")

def handle_member_application(user_id, reply_token, member_type):
    is_vip_request = member_type == "vip"
    title = "VIP" if is_vip_request else "一般會員"
    if is_vip_request and is_vip_user(user_id):
        line_bot_api.reply_message(reply_token, TextSendMessage(text="✅ 你目前已是 VIP。"))
        return True

    display_name = get_line_user_name(user_id)
    try:
        line_bot_api.push_message(ADMIN_UUID, create_vip_request_flex(display_name, user_id, member_type=member_type))
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"✅ 已送出{title}申請，請等待管理員審核。"))
    except Exception as e:
        print(f"❌ {title}申請送出失敗: {e}")
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"❌ {title}申請送出失敗，請稍後再試。"))
    return True

def start_flight_search(user_id, reply_token, search_date=None):
    search_date = search_date or today_taipei_date()
    flight_search_sessions[user_id] = {
        "step": "select_depart_region",
        "data": {"date": search_date},
        "updated_at": time.time(),
    }
    date_note = "今天" if search_date == today_taipei_date() else search_date
    line_bot_api.reply_message(
        reply_token,
        [
            TextSendMessage(text=f"航班日期：{date_note}\n請先選擇出發地"),
            create_flight_region_flex(FLIGHT_REGIONS, role="depart", include_taiwan_shortcut=True),
        ],
    )

def build_flight_city_selection(role, region_code):
    region = get_region(region_code)
    region_name = region["name"] if region else region_code
    cities = get_cities_by_region(region_code)
    return create_flight_city_flex(cities, role=role, region_name=region_name)

def handle_flight_city_selected(user_id, reply_token, role, city_code):
    session = flight_search_sessions.setdefault(user_id, {"step": "select_depart_region", "data": {}})
    city = get_city(city_code)
    if not city:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ 找不到這個航點，請重新選擇。"))
        return

    session["data"][role] = city
    session["updated_at"] = time.time()
    if role == "depart":
        session["step"] = "select_arrive_region"
        line_bot_api.reply_message(
            reply_token,
            [
                TextSendMessage(text=f"已選出發地：{city['country']} {city['name']}。接著請選擇目的地洲別。"),
                create_flight_region_flex(FLIGHT_REGIONS, role="arrive", include_taiwan_shortcut=False),
            ],
        )
        return

    depart = session["data"].get("depart")
    arrive = session["data"].get("arrive")
    if not depart or not arrive:
        flight_search_sessions.pop(user_id, None)
        line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ 航班查詢流程遺失，請重新輸入「查詢航班」。"))
        return

    search_date = session["data"].get("date") or today_taipei_date()
    try:
        send_loading_animation(user_id, duration=20)
        result = search_flights(depart["code"], arrive["code"], search_date)
        session["step"] = "show_results"
        session["result"] = result
        session["page"] = 0
        session["filter"] = "active"
        line_bot_api.reply_message(reply_token, create_flight_result_flex(result, page=0, filter_type="active"))
    except Exception as e:
        print(f"❌ 航班查詢失敗: {e}")
        flight_search_sessions.pop(user_id, None)
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"❌ 航班查詢失敗：{e}"))

def reply_flight_result_page(user_id, reply_token, page, filter_type=None):
    session = flight_search_sessions.get(user_id)
    result = session.get("result") if session else None
    if not result:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ 航班結果已失效，請重新輸入「查詢航班」。"))
        return
    if filter_type not in ("active", "arrived"):
        filter_type = session.get("filter") or "active"
    session["page"] = page
    session["filter"] = filter_type
    session["updated_at"] = time.time()
    send_loading_animation(user_id, duration=10)
    line_bot_api.reply_message(reply_token, create_flight_result_flex(result, page=page, filter_type=filter_type))

def parse_flight_search_date(value):
    text = (value or "").strip()
    match = re.match(r"^(\d{4})[-/]?(\d{2})[-/]?(\d{2})$", text)
    if not match:
        return None
    try:
        parsed = datetime.datetime.strptime("-".join(match.groups()), "%Y-%m-%d")
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return None

def extract_flight_search_date(parts):
    for index, part in enumerate(list(parts)):
        parsed_date = parse_flight_search_date(part)
        if parsed_date:
            parts.pop(index)
            return parsed_date, True
    return today_taipei_date(), False

def parse_flight_route_query(message):
    text = (message or "").strip()
    cleaned = re.sub(r"^(查詢航班|航班查詢|查航班|即時航班)\s*", "", text, flags=re.IGNORECASE).strip()
    if cleaned == text or not cleaned:
        return None
    parts = re.split(r"[\s,，]+", cleaned.upper())
    search_date, _ = extract_flight_search_date(parts)
    if parts:
        return None
    return search_date

def parse_flight_number_query(message):
    text = (message or "").strip()
    if not text:
        return None

    compact = text.replace(" ", "")
    if compact in ("查詢航班", "航班查詢", "查航班", "即時航班"):
        return None

    cleaned = re.sub(r"^(查詢航班|航班查詢|查航班|即時航班|航班)\s*", "", text, flags=re.IGNORECASE).strip()
    has_prefix = cleaned != text
    if not cleaned:
        return None

    parts = re.split(r"[\s,，]+", cleaned.upper())
    search_date, date_is_explicit = extract_flight_search_date(parts)
    if not parts:
        return None
    flight_no = normalize_flight_no(parts[0])
    if not _looks_like_flight_no(flight_no):
        return None
    if not has_prefix and not re.search(r"[A-Z]", flight_no):
        return None

    depart_code = parts[1] if len(parts) >= 3 else None
    arrive_code = parts[2] if len(parts) >= 3 else None
    if depart_code and not re.match(r"^[A-Z0-9]{3}$", depart_code):
        depart_code = None
    if arrive_code and not re.match(r"^[A-Z0-9]{3}$", arrive_code):
        arrive_code = None
    return flight_no, depart_code, arrive_code, search_date, date_is_explicit

def _looks_like_flight_no(value):
    if not value or len(value) < 3 or len(value) > 8:
        return False
    return bool(re.match(r"^[A-Z0-9]{2,3}\d{2,4}[A-Z]?$", value))

def _flight_result_default_filter(result):
    flights = result.get("flights", [])
    if not flights:
        return "active"
    for item in flights:
        flight = item.get("varItemInfo") or item
        if (flight.get("srak") or item.get("srak") or "") != "已抵達":
            return "active"
    return "arrived"

def handle_flight_number_search(user_id, reply_token, flight_no, depart_code=None, arrive_code=None, search_date=None, date_is_explicit=False):
    search_date = search_date or today_taipei_date()
    try:
        send_loading_animation(user_id, duration=60)
        result = search_flights_by_number(
            flight_no,
            search_date,
            depart_code=depart_code,
            arrive_code=arrive_code,
            allow_route_fallback=date_is_explicit,
        )
        flight_search_sessions[user_id] = {
            "step": "show_results",
            "data": {
                "flight_no": flight_no,
                "depart_code": depart_code,
                "arrive_code": arrive_code,
                "date": search_date,
            },
            "result": result,
            "page": 0,
            "filter": _flight_result_default_filter(result),
            "updated_at": time.time(),
        }
        if not result.get("flights"):
            hint = f"{flight_no} {depart_code} {arrive_code}" if depart_code and arrive_code else f"{flight_no} TPE PUS"
            date_text = "今日" if search_date == today_taipei_date() else search_date
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=f"目前查不到 {flight_no} {date_text}航班。\n可改用：查詢航班 {hint} {search_date}")
            )
            return
        filter_type = flight_search_sessions[user_id]["filter"]
        line_bot_api.reply_message(reply_token, create_flight_result_flex(result, page=0, filter_type=filter_type))
    except Exception as e:
        print(f"❌ 航班代號查詢失敗: {e}")
        flight_search_sessions.pop(user_id, None)
        line_bot_api.reply_message(reply_token, TextSendMessage(text=f"❌ 航班代號查詢失敗：{e}"))

def normalize_plate_text(value):
    return re.sub(r'[^A-Z0-9]', '', (value or '').upper())

def format_plate_text(value):
    clean = normalize_plate_text(value)
    if "-" in (value or ""):
        return value.upper().strip()
    if len(clean) > 4:
        return f"{clean[:-4]}-{clean[-4:]}"
    return clean

def filter_records_for_personal_plate(car, records):
    plate = normalize_plate_text(car.get("plate_no", ""))
    if not plate:
        return records, None
    matched = [rec for rec in records if normalize_plate_text(rec.get("車號", "")) == plate]
    return matched, plate

def build_edit_field_items(car):
    items = [
        ("name", "暱稱"),
        ("id", "身分證" if car["mode"] == "personal" else "統編"),
    ]
    if car["mode"] == "personal":
        items.append(("birthday", "生日"))
        items.append(("plate", "車牌"))
    else:
        items.append(("plate", "車牌"))
    return items

def build_edit_menu_message(session):
    car = session["car"]
    draft = session["draft"]
    field_items = build_edit_field_items(car)
    field_label_map = dict(field_items)
    detail_lines = [f"✏️ 編輯車輛：{car['name']}"]
    for key, label in field_items:
        detail_lines.append(f"{label}：{draft.get(key, '')}")
    detail_lines.append("")
    detail_lines.append("請選擇要編輯的欄位。")
    if session.get("touched_fields"):
        touched_labels = [field_label_map.get(key, key) for key in session["touched_fields"]]
        detail_lines.insert(1, f"已暫存修改：{', '.join(touched_labels)}")

    quick_reply_items = [
        QuickReplyButton(action=MessageAction(label=label, text=label))
        for _, label in field_items
    ]
    quick_reply_items.extend([
        QuickReplyButton(action=MessageAction(label="✅ 完成編輯", text="完成編輯")),
        QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消")),
    ])

    return TextSendMessage(
        text="\n".join(detail_lines),
        quick_reply=QuickReply(items=quick_reply_items),
    )

def build_edit_prompt_message(session, field_key):
    current_value = session["draft"].get(field_key, "")
    car = session["car"]
    if field_key == "name":
        prompt = "請輸入新的暱稱"
    elif field_key == "id":
        prompt = "請輸入新的身分證字號（10碼）" if car["mode"] == "personal" else "請輸入新的統編（8碼）"
    elif field_key == "birthday":
        prompt = "請輸入新的生日（民國年7碼，例如 0800101）"
    else:
        prompt = "請輸入新的車牌號碼"
    return TextSendMessage(
        text=(
            f"{prompt}\n"
            f"目前值：{current_value}\n"
            f"也可以輸入「略過」保留原本，或按「返回上一頁」。"
        ),
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="⬅️ 返回上一頁", text="返回上一頁")),
            QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消")),
        ]),
    )

def start_car_edit_session(user_id, car):
    edit_car_sessions[user_id] = {
        "car": car,
        "draft": {
            "name": car["name"],
            "id": car["id"],
            "birthday": car["sub_id"] if car["mode"] == "personal" else "",
            "plate": car["plate_no"] if car["mode"] == "personal" else (car["sub_id"] if car["mode"] == "legal" else ""),
        },
        "pending_field": None,
        "touched_fields": [],
    }

def validate_edit_field(car, field_key, value, user_id):
    if field_key == "name":
        clean = value.strip()
        if not clean:
            return None, "⚠️ 暱稱不能空白，請重新輸入。"
        return clean, None

    if field_key == "id":
        clean = value.upper().strip()
        if car["mode"] == "personal":
            if len(clean) != 10:
                return None, "⚠️ 身分證長度應為 10 碼，請重新輸入："
        else:
            if len(clean) != 8 or not clean.isdigit():
                return None, "⚠️ 統編應為 8 位數字，請重新輸入："
        return clean, None

    if field_key == "birthday":
        clean = value.strip()
        if len(clean) != 7 or not clean.isdigit():
            return None, "⚠️ 生日格式錯誤，請輸入 7 位數字，例如 0800101："
        return clean, None

    if field_key == "plate":
        clean = format_plate_text(value)
        if not clean:
            return None, "⚠️ 車牌號碼不能空白，請重新輸入。"
        if len(normalize_plate_text(clean)) < 4:
            return None, "⚠️ 車牌格式太短，請重新輸入。"
        if check_car_exists_except(user_id, "2", clean, car["db_id"]):
            return None, f"❌ 車號「{clean}」已綁定過，請輸入另一組車號。"
        return clean, None

    return value, None

def apply_edit_value(session, field_key, value):
    session["draft"][field_key] = value
    if field_key not in session["touched_fields"]:
        session["touched_fields"].append(field_key)

def finalize_car_edit(user_id, reply_token):
    session = edit_car_sessions.get(user_id)
    if not session:
        return

    car = session["car"]
    draft = session["draft"]
    mode = "1" if car["mode"] == "personal" else "2"
    birthday = draft["birthday"] if car["mode"] == "personal" else ""
    plate = draft["plate"]

    ok = update_car(user_id, car["db_id"], draft["name"], mode, draft["id"], plate, birthday)
    edit_car_sessions.pop(user_id, None)

    if ok:
        if car["mode"] == "personal":
            text = f"✅ 車輛資料已更新！\n\n🚗 暱稱：{draft['name']}\n🪪 身分證：{draft['id']}\n🎂 生日：{birthday}\n🚙 車牌：{plate}"
        else:
            text = f"✅ 車輛資料已更新！\n\n🏢 暱稱：{draft['name']}\n🔢 統編：{draft['id']}\n🚙 車號：{plate}"
        line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
    else:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ 更新失敗，請稍後再試一次。"))

def handle_car_edit_text(user_id, msg, reply_token):
    session = edit_car_sessions.get(user_id)
    if not session:
        return False

    car = session["car"]
    cleaned = msg.strip()

    if session["pending_field"]:
        field_key = session["pending_field"]
        field_label = dict(build_edit_field_items(car)).get(field_key, field_key)
        if cleaned == "返回上一頁":
            session["pending_field"] = None
            line_bot_api.reply_message(
                reply_token,
                [TextSendMessage(text="↩️ 已返回編輯選單。"), build_edit_menu_message(session)]
            )
            return True
        if cleaned == "略過":
            session["pending_field"] = None
            line_bot_api.reply_message(
                reply_token,
                [TextSendMessage(text=f"✅ 已保留原本的{field_label}。"), build_edit_menu_message(session)]
            )
            return True

        value, error_text = validate_edit_field(car, field_key, cleaned, user_id)
        if error_text:
            line_bot_api.reply_message(reply_token, TextSendMessage(text=error_text, quick_reply=cancel_menu))
            return True

        apply_edit_value(session, field_key, value)
        session["pending_field"] = None
        line_bot_api.reply_message(
            reply_token,
            [TextSendMessage(text=f"✅ 已暫存更新：{field_label} = {value}"), build_edit_menu_message(session)]
        )
        return True

    field_map = {label: key for key, label in build_edit_field_items(car)}
    if cleaned in field_map:
        session["pending_field"] = field_map[cleaned]
        line_bot_api.reply_message(reply_token, build_edit_prompt_message(session, session["pending_field"]))
        return True

    if cleaned == "完成編輯":
        finalize_car_edit(user_id, reply_token)
        return True

    if cleaned == "取消":
        edit_car_sessions.pop(user_id, None)
        line_bot_api.reply_message(reply_token, TextSendMessage(text="🚫 已取消編輯流程。"))
        return True

    if cleaned == "返回上一頁":
        line_bot_api.reply_message(
            reply_token,
            [TextSendMessage(text="↩️ 已返回編輯選單。"), build_edit_menu_message(session)]
        )
        return True

    line_bot_api.reply_message(reply_token, build_edit_menu_message(session))
    return True

# -----------------------------------------------------------
# 🛠️ 初始化：啟動時載入雲端停車場快取
# -----------------------------------------------------------
reload_parking_data()

# -----------------------------------------------------------
# ⏰ 背景任務：自動排程檢查器
# -----------------------------------------------------------
def run_scheduled_crawling_task(user_id, cars):
    """讓排程查詢受 5 個 Selenium session 的並發上限控制。"""
    print(
        f"⏳ 排程查詢等待 session：{user_id} "
        f"（上限 {SCHEDULE_CRAWLER_MAX_CONCURRENCY}）"
    )
    schedule_crawler_slots.acquire()
    print(f"▶️ 排程查詢取得 session：{user_id}")
    try:
        process_crawling_task(user_id, cars, None, True)
    except Exception as exc:
        print(f"❌ 排程查罰單失敗：{user_id}: {exc}")
    finally:
        schedule_crawler_slots.release()
        print(f"⏹️ 排程查詢釋放 session：{user_id}")


def schedule_worker():
    print("🚀 排程檢查器啟動...")
    while True:
        try:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
            time_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")
            
            schedules = get_all_schedules()
            for line_id, s_type, value, last_run in schedules:
                should_run = False
                if s_type == 'daily' and time_str == value and last_run != today_str:
                    should_run = True
                elif s_type == 'weekly' and str(now.weekday()) == value and time_str == "09:00" and last_run != today_str:
                    should_run = True
                elif s_type == 'interval':
                    if not last_run or (now.date() - datetime.datetime.strptime(last_run, "%Y-%m-%d").date()).days >= int(value):
                        if time_str == "09:00" and last_run != today_str:
                            should_run = True

                if should_run:
                    print(f"⏰ 執行自動查詢: {line_id}")
                    if is_line_quota_paused("scheduled_fines"):
                        print(f"⚠️ 排程查罰單因 LINE 額度上限暫停，略過: {line_id}")
                        continue
                    if not is_vip_user(line_id):
                        safe_push_message(
                            line_id,
                            TextSendMessage(text="⚠️ 自動排程為 VIP 功能。此排程已略過，若需使用請聯繫管理員。"),
                            feature_key="scheduled_fines",
                            feature_name="排程查罰單",
                        )
                        continue
                    cars = get_user_cars(line_id)
                    if cars:
                        update_last_run(line_id)
                        # 啟動排程查詢；超過 5 個並發時會在 wrapper 內等待空位。
                        threading.Thread(
                            target=run_scheduled_crawling_task,
                            args=(line_id, cars),
                            daemon=True,
                        ).start()
            
            time.sleep(60) # 每分鐘檢查一次
        except Exception as e:
            print(f"❌ 排程檢查錯誤: {e}")
            time.sleep(60)

threading.Thread(target=schedule_worker, daemon=True).start()

# -----------------------------------------------------------
# 🚕 背景任務：55688 預約單安全監控
# -----------------------------------------------------------
reservation_monitor_state = {"last_key": None}
RESERVATION_SENT_LOG_PATH = Path(__file__).resolve().parent / "reservation_sent_jobs.json"
RESERVATION_SETTINGS_PATH = Path(__file__).resolve().parent / "reservation_settings.json"
RESERVATION_TOKEN_ALERT_PATH = Path(__file__).resolve().parent / "reservation_token_alert.json"
TAXIGO_DRIVER_SENT_LOG_PATH = Path(__file__).resolve().parent / "taxigo_driver_reservation_sent_jobs.json"
TAXIGO_DRIVER_SETTINGS_PATH = Path(__file__).resolve().parent / "taxigo_driver_reservation_settings.json"
TAXIGO_DRIVER_TOKEN_ALERT_PATH = Path(__file__).resolve().parent / "taxigo_driver_token_alert.json"
LINE_QUOTA_ALERT_PATH = Path(__file__).resolve().parent / "line_quota_alert.json"
MIN_55688_AREA_COUNT = 4
RESERVATION_MONITOR_SLEEP_RANGE_SEC = (50, 70)
NEW_TAIPEI_RESERVATION_AREAS = {
    124: "新莊區",
    125: "林口區",
    126: "五股區",
    127: "蘆洲區",
    128: "三重區",
    129: "泰山區",
    130: "新店區",
    131: "石碇區",
    132: "深坑區",
    133: "坪林區",
    134: "烏來區",
    135: "板橋區",
    136: "三峽區",
    137: "鶯歌區",
    138: "樹林區",
    139: "中和區",
    140: "土城區",
    141: "瑞芳區",
    142: "平溪區",
    143: "雙溪區",
    144: "貢寮區",
    145: "金山區",
    146: "萬里區",
    147: "淡水區",
    148: "汐止區",
    149: "三芝區",
    150: "石門區",
    151: "八里區",
    152: "永和區",
}
DEFAULT_55688_RESERVATION_SETTINGS = {
    "active": TAIWANTAXI_RESERVATION_MONITOR_ENABLED,
    "min_fare": TAIWANTAXI_RESERVATION_MIN_FARE,
    "areas": TAIWANTAXI_SELECTED_AREAS,
    "date_mode": "all",
    "date_value": "",
    "frequency_min_sec": RESERVATION_MONITOR_SLEEP_RANGE_SEC[0],
    "frequency_max_sec": RESERVATION_MONITOR_SLEEP_RANGE_SEC[1],
}
DEFAULT_TAXIGO_DRIVER_RESERVATION_SETTINGS = {
    "active": TAXIGO_DRIVER_RESERVATION_MONITOR_ENABLED,
    "min_fare": TAXIGO_DRIVER_RESERVATION_MIN_FARE,
    "airport_only": False,
    "frequency_min_sec": RESERVATION_MONITOR_SLEEP_RANGE_SEC[0],
    "frequency_max_sec": RESERVATION_MONITOR_SLEEP_RANGE_SEC[1],
}

def get_next_month_first_yyyymmdd():
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    year = now.year + (1 if now.month == 12 else 0)
    month = 1 if now.month == 12 else now.month + 1
    return f"{year}{month:02d}01"

def _is_line_monthly_quota_error(exc):
    if isinstance(exc, LineBotApiError) and getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc or "").lower()
    return "429" in text or "monthly limit" in text or "quota" in text or "rate limit" in text

def _load_line_quota_alert():
    try:
        if LINE_QUOTA_ALERT_PATH.exists():
            with LINE_QUOTA_ALERT_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"⚠️ LINE 額度提醒紀錄讀取失敗: {exc}")
    return {}

def _save_line_quota_alert(data):
    try:
        with LINE_QUOTA_ALERT_PATH.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"⚠️ LINE 額度提醒紀錄寫入失敗: {exc}")

def build_line_quota_notice(feature_name):
    return (
        "[重要通知]\n"
        "因line bot reply token 已達到每月額度上限 "
        f"{feature_name}將暫停使用直到{get_next_month_first_yyyymmdd()}"
    )

def notify_line_quota_once(feature_key, feature_name):
    alert = _load_line_quota_alert()
    reset_date = get_next_month_first_yyyymmdd()
    alert_key = f"{feature_key}:{reset_date}"
    if alert.get(alert_key):
        return
    notice = build_line_quota_notice(feature_name)
    try:
        line_bot_api.push_message(ADMIN_UUID, TextSendMessage(text=notice))
        alert[alert_key] = True
        alert[f"{feature_key}_last_notice"] = notice
        alert[f"{feature_key}_last_notice_at"] = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).isoformat()
        _save_line_quota_alert(alert)
    except Exception as exc:
        print(f"❌ LINE 額度重要通知推播失敗: {exc}")
        alert[alert_key] = True
        alert[f"{feature_key}_last_notice"] = notice
        alert[f"{feature_key}_last_notice_push_failed"] = str(exc)
        _save_line_quota_alert(alert)

def is_line_quota_paused(feature_key):
    alert = _load_line_quota_alert()
    return bool(alert.get(f"{feature_key}:{get_next_month_first_yyyymmdd()}"))

def handle_line_quota_exceeded(feature_key, feature_name):
    notify_line_quota_once(feature_key, feature_name)
    if feature_key == "55688_reservation":
        try:
            persist_55688_settings({"active": False}, updated_by="line_quota_exceeded")
        except Exception as exc:
            print(f"⚠️ 55688 監控停用失敗: {exc}")
    elif feature_key == "taxigo_driver_reservation":
        try:
            persist_taxigo_driver_settings({"active": False}, updated_by="line_quota_exceeded")
        except Exception as exc:
            print(f"⚠️ LINE GO 預約監控停用失敗: {exc}")
    elif feature_key == "scheduled_fines":
        print("⚠️ 排程查罰單因 LINE 額度上限暫停；既有排程會在觸發時略過。")

def safe_push_message(to, messages, feature_key=None, feature_name=None):
    try:
        line_bot_api.push_message(to, messages)
        return True
    except Exception as exc:
        if feature_key and _is_line_monthly_quota_error(exc):
            print(f"⚠️ LINE 月額度已達上限，暫停 {feature_name}: {exc}")
            handle_line_quota_exceeded(feature_key, feature_name)
            return False
        raise

def _get_env_file_path():
    check_mvdis_env = Path(__file__).resolve().parent / ".env"
    project_env = Path(__file__).resolve().parent.parent / ".env"
    if check_mvdis_env.exists():
        return check_mvdis_env
    return project_env

def _mask_secret(value):
    text = str(value or "")
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"

def update_55688_dispatch_token(new_token):
    global TAIWANTAXI_DISPATCH_TOKEN
    token = str(new_token or "").strip()
    if not token:
        raise ValueError("token 不可為空")

    env_path = _get_env_file_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.touch()

    set_key(str(env_path), "TAIWANTAXI_DISPATCH_TOKEN", token, quote_mode="always")
    os.environ["TAIWANTAXI_DISPATCH_TOKEN"] = token
    TAIWANTAXI_DISPATCH_TOKEN = token
    app_config.TAIWANTAXI_DISPATCH_TOKEN = token
    crawler_utils_module.TAIWANTAXI_DISPATCH_TOKEN = token
    _clear_55688_token_alert()
    return env_path

def _is_55688_token_error(value):
    text = str(value or "").lower()
    token_error_keywords = (
        "dispatchtoken not found",
        "authentication failed",
        "unauthorized",
        "401",
        "缺少 taiwantaxi_dispatch_token",
        "dispatchtoken",
    )
    return any(keyword in text for keyword in token_error_keywords)

def _load_55688_token_alert():
    try:
        if RESERVATION_TOKEN_ALERT_PATH.exists():
            with RESERVATION_TOKEN_ALERT_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"⚠️ 55688 token 提醒紀錄讀取失敗: {exc}")
    return {}

def _save_55688_token_alert(data):
    try:
        with RESERVATION_TOKEN_ALERT_PATH.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"⚠️ 55688 token 提醒紀錄寫入失敗: {exc}")

def _clear_55688_token_alert():
    try:
        if RESERVATION_TOKEN_ALERT_PATH.exists():
            RESERVATION_TOKEN_ALERT_PATH.unlink()
    except Exception as exc:
        print(f"⚠️ 55688 token 提醒紀錄清除失敗: {exc}")

def notify_55688_token_error_once_daily(error_message):
    today = _today_taipei_str()
    alert = _load_55688_token_alert()
    if alert.get("last_alert_date") == today:
        return
    try:
        line_bot_api.push_message(
            ADMIN_UUID,
            TextSendMessage(text=(
                "⚠️ 55688 DispatchToken 可能已過期\n"
                "今日僅提醒一次。\n\n"
                f"錯誤：{error_message}\n\n"
                "請在 bot 輸入：\n"
                "55688 token :你的新token"
            ))
        )
        alert["last_alert_date"] = today
        alert["last_error"] = str(error_message)
        _save_55688_token_alert(alert)
    except Exception as exc:
        print(f"❌ 55688 token 過期提醒推播失敗: {exc}")

def _parse_int(value, default=0):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default

def _parse_yyyymmdd(value):
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    if not match:
        return None
    try:
        parsed = datetime.datetime.strptime("".join(match.groups()), "%Y%m%d")
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return None

def parse_55688_date_command(text):
    raw = str(text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    if compact in ("全部", "all", "ALL"):
        return {"date_mode": "all", "date_value": ""}
    if compact in ("今天", "today", "TODAY"):
        return {"date_mode": "today", "date_value": ""}
    if "~" in compact or "～" in compact:
        parts = re.split(r"[~～]", compact, maxsplit=1)
        if len(parts) != 2:
            return None
        start_date = _parse_yyyymmdd(parts[0])
        end_date = _parse_yyyymmdd(parts[1])
        if not start_date or not end_date:
            return None
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return {"date_mode": "range", "date_value": f"{start_date}~{end_date}"}
    single_date = _parse_yyyymmdd(compact)
    if single_date:
        return {"date_mode": "date", "date_value": single_date}
    return None

def parse_55688_frequency_command(text):
    compact = re.sub(r"\s+", "", str(text or ""))
    match = re.fullmatch(r"(\d+)(?:[~～](\d+))?", compact)
    if not match:
        return None
    min_sec = max(5, int(match.group(1)))
    max_sec = max(5, int(match.group(2) or match.group(1)))
    if min_sec > max_sec:
        min_sec, max_sec = max_sec, min_sec
    return {"frequency_min_sec": min_sec, "frequency_max_sec": max_sec}

def format_55688_date_text(settings):
    mode = settings.get("date_mode", "all")
    value = settings.get("date_value") or ""
    if mode == "all":
        return "全部"
    if mode == "today":
        return _today_taipei_str()
    if mode == "range" and "~" in value:
        start_date, end_date = value.split("~", 1)
        return f"{start_date} ~ {end_date}"
    return value or "指定日期"

def format_55688_frequency_text(settings):
    min_sec = _parse_int(settings.get("frequency_min_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[0])
    max_sec = _parse_int(settings.get("frequency_max_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[1])
    if min_sec == max_sec:
        return f"{min_sec} 秒"
    return f"{min_sec}-{max_sec} 秒"

def get_55688_monitor_sleep_seconds(settings):
    min_sec = _parse_int(settings.get("frequency_min_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[0])
    max_sec = _parse_int(settings.get("frequency_max_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[1])
    min_sec = max(5, min_sec)
    max_sec = max(5, max_sec)
    if min_sec > max_sec:
        min_sec, max_sec = max_sec, min_sec
    if min_sec == max_sec:
        return min_sec
    return random.randint(min_sec, max_sec)

def normalize_55688_area_ids(area_values):
    try:
        area_ids = [
            int(area)
            for area in area_values
            if int(area) in NEW_TAIPEI_RESERVATION_AREAS
        ]
    except (TypeError, ValueError):
        area_ids = []

    if len(area_ids) < MIN_55688_AREA_COUNT:
        defaults = list(TAIWANTAXI_SELECTED_AREAS)
        if len(defaults) < MIN_55688_AREA_COUNT:
            defaults = [127, 128, 124, 152]
        for area_id in defaults:
            if area_id in NEW_TAIPEI_RESERVATION_AREAS and area_id not in area_ids:
                area_ids.append(area_id)
            if len(area_ids) >= MIN_55688_AREA_COUNT:
                break
    return sorted(set(area_ids))

def load_55688_settings():
    settings = DEFAULT_55688_RESERVATION_SETTINGS.copy()
    try:
        if RESERVATION_SETTINGS_PATH.exists():
            with RESERVATION_SETTINGS_PATH.open("r", encoding="utf-8") as fh:
                saved = json.load(fh)
                if isinstance(saved, dict):
                    settings.update(saved)
    except Exception as exc:
        print(f"⚠️ 55688 設定讀取失敗: {exc}")

    remote_settings = get_reservation_monitor_setting()
    if remote_settings:
        settings.update({
            "active": remote_settings.get("active"),
            "min_fare": remote_settings.get("min_fare"),
            "areas": remote_settings.get("areas"),
            "date_mode": remote_settings.get("date_mode"),
            "date_value": remote_settings.get("date_value"),
            "frequency_min_sec": remote_settings.get("frequency_min_sec"),
            "frequency_max_sec": remote_settings.get("frequency_max_sec"),
        })

    settings["active"] = bool(settings.get("active"))
    settings["min_fare"] = max(0, _parse_int(settings.get("min_fare"), TAIWANTAXI_RESERVATION_MIN_FARE))
    settings["areas"] = normalize_55688_area_ids(settings.get("areas", []))
    if settings.get("date_mode") not in ("all", "today", "date", "range"):
        settings["date_mode"] = "all"
    settings["date_value"] = str(settings.get("date_value") or "")
    min_sec = max(5, _parse_int(settings.get("frequency_min_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[0]))
    max_sec = max(5, _parse_int(settings.get("frequency_max_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[1]))
    if min_sec > max_sec:
        min_sec, max_sec = max_sec, min_sec
    settings["frequency_min_sec"] = min_sec
    settings["frequency_max_sec"] = max_sec
    return settings

def save_55688_settings(settings):
    normalized = load_55688_settings()
    normalized.update(settings)
    normalized["areas"] = normalize_55688_area_ids(normalized.get("areas", []))
    with RESERVATION_SETTINGS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, ensure_ascii=False, indent=2)
    return normalized

def persist_55688_settings(settings, updated_by=""):
    normalized = save_55688_settings(settings)
    upsert_reservation_monitor_setting(normalized, updated_by=updated_by)
    return normalized

def format_55688_area_label(settings=None):
    settings = settings or load_55688_settings()
    return "、".join(
        NEW_TAIPEI_RESERVATION_AREAS.get(area, str(area))
        for area in settings.get("areas", [])
    ) or "-"

def summarize_55688_reservation():
    checked_at = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    settings = load_55688_settings()
    summary = {
        "checked_at": checked_at,
        "ok": False,
        "is_success": False,
        "msg": "",
        "machine": "",
        "total_jobs": 0,
        "over_threshold_count": 0,
        "threshold": settings["min_fare"],
    }

    if not TAIWANTAXI_DISPATCH_TOKEN:
        summary["msg"] = "缺少 TAIWANTAXI_DISPATCH_TOKEN，監控未執行。"
        return summary

    try:
        data = get_55688_reservation_with_settings(settings)
    except Exception as exc:
        summary["msg"] = f"{type(exc).__name__}: {exc}"
        if _is_55688_token_error(summary["msg"]):
            notify_55688_token_error_once_daily(summary["msg"])
        return summary

    result = data.get("result") or {}
    job_data = result.get("jobData") or []
    filtered_by_date = [
        job for job in job_data
        if _matches_55688_date_filter(job, settings)
    ]
    summary.update({
        "ok": bool(data.get("isSuccess")),
        "is_success": bool(data.get("isSuccess")),
        "msg": data.get("msg") or "",
        "machine": data.get("machine") or "",
        "total_jobs": len(filtered_by_date),
        "over_threshold_count": sum(
            1
            for job in filtered_by_date
            if _parse_int(job.get("estimatedFare")) > settings["min_fare"]
        ),
    })
    return summary

def format_55688_reservation_summary(summary):
    settings = load_55688_settings()
    status = "成功" if summary.get("is_success") else "失敗"
    msg = summary.get("msg") or "-"
    machine = summary.get("machine") or "-"
    areas = format_55688_area_label(settings)
    active = "啟用" if settings.get("active") else "停用"
    date_text = format_55688_date_text(settings)
    frequency_text = format_55688_frequency_text(settings)
    return (
        "55688 預約單監控\n"
        f"狀態：{status} / 監控{active}\n"
        f"區域：{areas}\n"
        f"日期：{date_text}\n"
        f"頻率：{frequency_text}\n"
        f"總筆數：{summary.get('total_jobs', 0)}\n"
        f"預估車資 > {summary.get('threshold', TAIWANTAXI_RESERVATION_MIN_FARE)}："
        f"{summary.get('over_threshold_count', 0)} 筆\n"
        f"機器：{machine}\n"
        f"訊息：{msg}\n"
        f"時間：{summary.get('checked_at')}"
    )

def infer_55688_area_name(job):
    for key in ("areaId", "areaID", "iveArea", "iveSelectedArea", "selectedArea"):
        area_id = _parse_int(job.get(key))
        if area_id in NEW_TAIPEI_RESERVATION_AREAS:
            return NEW_TAIPEI_RESERVATION_AREAS[area_id]

    address = str(job.get("onAddrHumanRead") or "")
    for area_name in NEW_TAIPEI_RESERVATION_AREAS.values():
        if area_name in address:
            return area_name
    return "新北市"

def mask_55688_address(address):
    text = str(address or "").strip()
    if not text:
        return "-"
    first_part = re.split(r"[，,]", text, maxsplit=1)[0].strip()
    match = re.search(r"(?P<city>[^縣市]{1,6}[縣市])(?P<district>[^鄉鎮市區]{1,8}[鄉鎮市區])?(?P<road>[^,，0-9０-９]{1,12}(?:路|街|大道|巷|弄))?", first_part)
    if not match:
        return first_part[:6] + "..." if len(first_part) > 6 else first_part
    city = match.group("city") or ""
    district = match.group("district") or ""
    road = match.group("road") or ""
    return f"{city}{district}{road}附近" if road else f"{city}{district}附近"

def get_55688_reservation_safe_details(limit=5):
    settings = load_55688_settings()
    data = get_55688_reservation_with_settings(settings)
    jobs = ((data.get("result") or {}).get("jobData") or [])
    filtered = [
        job for job in jobs
        if _parse_int(job.get("estimatedFare")) > settings["min_fare"]
        and _matches_55688_date_filter(job, settings)
    ]
    items = []
    for job in filtered[:limit]:
        items.append({
            "booking_time": job.get("bookingTime") or "-",
            "fare_label": f"NT$ {job.get('estimatedFare') or '-'}",
            "job_type": job.get("jobRequireName") or "-",
            "special_req": "有" if job.get("specialReq") else "無",
            "pickup": mask_55688_address(job.get("onAddrHumanRead")),
            "dropoff": mask_55688_address(job.get("offAddrHumanRead")),
        })
    return data, items, len(filtered)

def format_55688_reservation_safe_details(data, items, total_filtered):
    machine = data.get("machine") or "-"
    if not data.get("isSuccess"):
        return (
            "55688 預約單明細測試\n"
            "狀態：失敗\n"
            f"機器：{machine}\n"
            f"訊息：{data.get('msg') or '-'}"
        )
    if not items:
        return (
            "55688 預約單明細測試\n"
            f"目前沒有符合設定條件的預約單。\n"
            f"機器：{machine}"
        )

    lines = [
        "55688 預約單明細測試",
        f"符合門檻：{total_filtered} 筆",
        f"僅顯示前 {len(items)} 筆遮罩資訊",
        f"機器：{machine}",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.extend([
            f"{index}. {item['booking_time']}",
            f"類型：{item['job_type']}｜備註：{item['special_req']}｜車資：{item['fare_label']}",
            f"上車：{item['pickup']}",
            f"下車：{item['dropoff']}",
            "",
        ])
    return "\n".join(lines).strip()

def build_55688_reservation_demo_jobs():
    return [
        {
            "jobId": "DEMO260812A001",
            "bookingTime": "2026/08/13 15:30",
            "onAddrHumanRead": "新北市三重區神農街481~501號，神農街481~501號",
            "offAddrHumanRead": "新北市新莊區五工路37號，機場捷運新北產業園區站",
            "estimatedFare": "455",
            "specialReq": "行李箱",
            "jobRequireName": "一般叫車",
            "payTypeLabel": "企業簽單",
            "canTakeJobTime": "2026/08/13 15:27",
        },
        {
            "jobId": "DEMO260812A002",
            "bookingTime": "2026/08/13 18:10",
            "onAddrHumanRead": "台北市松山區敦化北路168號",
            "offAddrHumanRead": "桃園市大園區航站南路9號，桃園國際機場第二航廈",
            "estimatedFare": "980",
            "specialReq": "大型行李、需協助搬運",
            "jobRequireName": "機場接送測試",
            "payTypeLabel": "信用卡",
            "canTakeJobTime": "2026/08/13 18:00",
        },
        {
            "jobId": "DEMO260812A003",
            "bookingTime": "2026/08/14 09:00",
            "onAddrHumanRead": "新北市蘆洲區光華路108號",
            "offAddrHumanRead": "台北市信義區松仁路95號",
            "estimatedFare": "360",
            "specialReq": None,
            "jobRequireName": "預約叫車",
            "payTypeLabel": "現金",
            "canTakeJobTime": "2026/08/14 08:50",
        },
    ]

def _format_ms_time(value):
    timestamp = _parse_int(value)
    if timestamp <= 0:
        return "-"
    return datetime.datetime.fromtimestamp(timestamp / 1000).strftime("%Y/%m/%d %H:%M")

def _load_reservation_sent_log():
    try:
        if RESERVATION_SENT_LOG_PATH.exists():
            with RESERVATION_SENT_LOG_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"⚠️ 55688 已推送紀錄讀取失敗: {exc}")
    return {}

def _save_reservation_sent_log(data):
    try:
        cutoff = (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        cleaned = {
            date_key: sorted(set(job_ids))
            for date_key, job_ids in data.items()
            if date_key >= cutoff and isinstance(job_ids, list)
        }
        with RESERVATION_SENT_LOG_PATH.open("w", encoding="utf-8") as fh:
            json.dump(cleaned, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"⚠️ 55688 已推送紀錄寫入失敗: {exc}")

def _today_taipei_str():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d")

def get_55688_reservation_with_settings(settings=None):
    settings = settings or load_55688_settings()
    dispatch_token = TAIWANTAXI_DISPATCH_TOKEN
    if not dispatch_token:
        raise RuntimeError("缺少 TAIWANTAXI_DISPATCH_TOKEN")

    url = "https://dispatchapi.taiwantaxi.com.tw/api/Reservation/GetReservationJobV2"
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "v8/3.2.62 (tw.com.taiwantaxi.driver; build:20260629143002; iOS 27.0.0) Alamofire/5.10.2",
        "Accept-Language": "zh-Hant-TW;q=1.0",
        "DispatchToken": dispatch_token,
    }
    payload = {
        "memSN": _parse_int(os.getenv("TAIWANTAXI_MEM_SN", "59783"), 59783),
        "iveSelectedArea": settings["areas"],
    }
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data.get("isSuccess") and _is_55688_token_error(data.get("msg")):
        raise RuntimeError(data.get("msg") or "DispatchToken 驗證失敗")
    return data

def _job_booking_date(job):
    booking_time = str(job.get("bookingTime") or "")
    match = re.match(r"(\d{4})/(\d{2})/(\d{2})", booking_time)
    if match:
        return "-".join(match.groups())
    timestamp = _parse_int(job.get("jobTimeMS"))
    if timestamp > 0:
        return datetime.datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
    return ""

def _matches_55688_date_filter(job, settings):
    mode = settings.get("date_mode", "all")
    if mode == "all":
        return True
    target_date = _today_taipei_str() if mode == "today" else settings.get("date_value", "")
    job_date = _job_booking_date(job)
    if mode == "range":
        if "~" not in target_date:
            return False
        start_date, end_date = target_date.split("~", 1)
        return bool(job_date) and start_date <= job_date <= end_date
    return bool(target_date) and job_date == target_date

def build_55688_reservation_live_qa_jobs(limit=10):
    settings = load_55688_settings()
    data = get_55688_reservation_with_settings(settings)
    if not data.get("isSuccess"):
        raise RuntimeError(data.get("msg") or "55688 API 回傳失敗")

    jobs = ((data.get("result") or {}).get("jobData") or [])
    filtered = [
        job for job in jobs
        if _parse_int(job.get("estimatedFare")) > settings["min_fare"]
        and _matches_55688_date_filter(job, settings)
    ]
    return [
        {
            "jobId": job.get("jobId") or "-",
            "bookingTime": job.get("bookingTime") or _format_ms_time(job.get("jobTimeMS")),
            "onAddrHumanRead": job.get("onAddrHumanRead") or "-",
            "offAddrHumanRead": job.get("offAddrHumanRead") or "-",
            "estimatedFare": job.get("estimatedFare") or "-",
            "specialReq": job.get("specialReq"),
            "jobRequireName": job.get("jobRequireName") or "-",
            "payTypeLabel": str(job.get("custPayType") or "-"),
            "canTakeJobTime": _format_ms_time(job.get("canTakeJobTimeMS")),
            "areaName": infer_55688_area_name(job),
        }
        for job in filtered[:limit]
    ]

def get_unsent_55688_reservation_jobs(limit=10):
    jobs = build_55688_reservation_live_qa_jobs(limit=50)
    today = _today_taipei_str()
    sent_log = _load_reservation_sent_log()
    sent_ids = set(sent_log.get(today, []))
    unsent_jobs = [
        job for job in jobs
        if job.get("jobId") and job.get("jobId") not in sent_ids
    ][:limit]
    return unsent_jobs, sent_log, today

def mark_55688_reservation_jobs_sent(jobs, sent_log, today):
    if not jobs:
        return
    sent_ids = set(sent_log.get(today, []))
    sent_ids.update(job["jobId"] for job in jobs if job.get("jobId"))
    sent_log[today] = sorted(sent_ids)
    _save_reservation_sent_log(sent_log)

def _reservation_summary_key(summary):
    return (
        summary.get("is_success"),
        summary.get("msg"),
        summary.get("machine"),
        summary.get("total_jobs"),
        summary.get("over_threshold_count"),
        summary.get("threshold"),
    )

def reservation_monitor_worker():
    print("🚕 55688 預約單監控啟動...")
    while True:
        settings = load_55688_settings()
        try:
            if settings.get("active"):
                jobs, sent_log, today = get_unsent_55688_reservation_jobs()
                if jobs:
                    pushed = safe_push_message(
                        ADMIN_UUID,
                        create_55688_reservation_demo_flex(
                            jobs,
                            title="55688 預約單",
                            subtitle="預約任務"
                        ),
                        feature_key="55688_reservation",
                        feature_name="55688預約單監控",
                    )
                    if pushed:
                        mark_55688_reservation_jobs_sent(jobs, sent_log, today)
        except Exception as exc:
            print(f"❌ 55688 預約單監控錯誤: {exc}")
            if _is_55688_token_error(exc):
                notify_55688_token_error_once_daily(exc)
            elif _is_line_monthly_quota_error(exc):
                handle_line_quota_exceeded("55688_reservation", "55688預約單監控")
        settings = load_55688_settings()
        if not settings.get("active"):
            time.sleep(60)
            continue
        sleep_seconds = get_55688_monitor_sleep_seconds(settings)
        print(f"⏱️ 55688 下一次監控：{sleep_seconds} 秒後")
        time.sleep(sleep_seconds)

threading.Thread(target=reservation_monitor_worker, daemon=True).start()

def reply_55688_manual_check(reply_token):
    jobs = build_55688_reservation_live_qa_jobs()
    if not jobs:
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=f"55688 預約單\n目前沒有區域 {format_55688_area_label()} 且符合設定條件的資料。")
        )
        return
    line_bot_api.reply_message(
        reply_token,
        create_55688_reservation_demo_flex(jobs, title="55688 預約單", subtitle="預約任務")
    )


def _normalize_taxigo_driver_jwt(value=None):
    token = str(value if value is not None else TAXIGO_DRIVER_JWT or "").strip()
    if token.lower().startswith("jwt "):
        token = token[4:].strip()
    return token


def update_taxigo_driver_jwt(new_token):
    global TAXIGO_DRIVER_JWT
    token = _normalize_taxigo_driver_jwt(new_token)
    if not token:
        raise ValueError("token 不可為空")

    env_path = _get_env_file_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.touch()

    set_key(str(env_path), "TAXIGO_DRIVER_JWT", token, quote_mode="always")
    os.environ["TAXIGO_DRIVER_JWT"] = token
    TAXIGO_DRIVER_JWT = token
    app_config.TAXIGO_DRIVER_JWT = token
    _clear_taxigo_driver_token_alert()
    return env_path


def _is_taxigo_driver_token_error(value):
    text = str(value or "").lower()
    return any(keyword in text for keyword in ("401", "unauthorized", "jwt", "token", "authentication"))


def _load_json_file(path, label):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"⚠️ {label} 讀取失敗: {exc}")
    return {}


def _save_json_file(path, data, label):
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"⚠️ {label} 寫入失敗: {exc}")


def _load_taxigo_driver_token_alert():
    return _load_json_file(TAXIGO_DRIVER_TOKEN_ALERT_PATH, "LINE GO driver token 提醒紀錄")


def _save_taxigo_driver_token_alert(data):
    _save_json_file(TAXIGO_DRIVER_TOKEN_ALERT_PATH, data, "LINE GO driver token 提醒紀錄")


def _clear_taxigo_driver_token_alert():
    try:
        if TAXIGO_DRIVER_TOKEN_ALERT_PATH.exists():
            TAXIGO_DRIVER_TOKEN_ALERT_PATH.unlink()
    except Exception as exc:
        print(f"⚠️ LINE GO driver token 提醒紀錄清除失敗: {exc}")


def notify_taxigo_driver_token_error_once_daily(error_message):
    today = _today_taipei_str()
    alert = _load_taxigo_driver_token_alert()
    if alert.get("last_alert_date") == today:
        return
    try:
        line_bot_api.push_message(
            ADMIN_UUID,
            TextSendMessage(text=(
                "⚠️ LINE GO driver JWT 可能已過期\n"
                "今日僅提醒一次。\n\n"
                f"錯誤：{error_message}\n\n"
                "請在 bot 輸入：\n"
                "LINEGO token :你的新JWT"
            ))
        )
        alert["last_alert_date"] = today
        alert["last_error"] = str(error_message)
        _save_taxigo_driver_token_alert(alert)
    except Exception as exc:
        print(f"❌ LINE GO driver token 過期提醒推播失敗: {exc}")


def load_taxigo_driver_settings():
    settings = DEFAULT_TAXIGO_DRIVER_RESERVATION_SETTINGS.copy()
    saved = _load_json_file(TAXIGO_DRIVER_SETTINGS_PATH, "LINE GO 預約監控設定")
    settings.update(saved)

    remote_settings = get_reservation_monitor_setting(setting_key="taxigo_driver")
    if remote_settings:
        settings.update({
            "active": remote_settings.get("active"),
            "min_fare": remote_settings.get("min_fare"),
            "frequency_min_sec": remote_settings.get("frequency_min_sec"),
            "frequency_max_sec": remote_settings.get("frequency_max_sec"),
        })

    settings["active"] = bool(settings.get("active"))
    settings["min_fare"] = max(0, _parse_int(settings.get("min_fare"), TAXIGO_DRIVER_RESERVATION_MIN_FARE))
    settings["airport_only"] = bool(settings.get("airport_only"))
    settings["frequency_min_sec"] = max(5, _parse_int(settings.get("frequency_min_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[0]))
    settings["frequency_max_sec"] = max(5, _parse_int(settings.get("frequency_max_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[1]))
    if settings["frequency_min_sec"] > settings["frequency_max_sec"]:
        settings["frequency_min_sec"], settings["frequency_max_sec"] = settings["frequency_max_sec"], settings["frequency_min_sec"]
    return settings


def save_taxigo_driver_settings(settings):
    normalized = load_taxigo_driver_settings()
    normalized.update(settings)
    normalized["min_fare"] = max(0, _parse_int(normalized.get("min_fare"), TAXIGO_DRIVER_RESERVATION_MIN_FARE))
    normalized["airport_only"] = bool(normalized.get("airport_only"))
    _save_json_file(TAXIGO_DRIVER_SETTINGS_PATH, normalized, "LINE GO 預約監控設定")
    return normalized


def persist_taxigo_driver_settings(settings, updated_by=""):
    normalized = save_taxigo_driver_settings(settings)
    remote_payload = {
        "active": normalized.get("active"),
        "min_fare": normalized.get("min_fare"),
        "areas": [],
        "date_mode": "all",
        "date_value": "",
        "frequency_min_sec": normalized.get("frequency_min_sec"),
        "frequency_max_sec": normalized.get("frequency_max_sec"),
    }
    upsert_reservation_monitor_setting(remote_payload, updated_by=updated_by, setting_key="taxigo_driver")
    return normalized


def get_taxigo_driver_monitor_sleep_seconds(settings):
    min_sec = max(5, _parse_int(settings.get("frequency_min_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[0]))
    max_sec = max(5, _parse_int(settings.get("frequency_max_sec"), RESERVATION_MONITOR_SLEEP_RANGE_SEC[1]))
    if min_sec > max_sec:
        min_sec, max_sec = max_sec, min_sec
    return min_sec if min_sec == max_sec else random.randint(min_sec, max_sec)


def _format_unix_time(value):
    timestamp = _parse_int(value)
    if timestamp <= 0:
        return "-"
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y/%m/%d %H:%M")


def get_taxigo_driver_open_reservations():
    token = _normalize_taxigo_driver_jwt()
    driver_uuid = str(TAXIGO_DRIVER_UUID or "").strip()
    if not token:
        raise RuntimeError("缺少 TAXIGO_DRIVER_JWT")
    if not driver_uuid:
        raise RuntimeError("缺少 TAXIGO_DRIVER_UUID")

    url = f"https://api.taxigo.com.tw/v3/drivers/open-reservations?uuid={driver_uuid}"
    user_agent = TAXIGO_DRIVER_USER_AGENT
    if "uuid:" not in user_agent:
        user_agent = f"{user_agent}, uuid: {driver_uuid}"
    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-TW,zh-Hant;q=0.9",
        "Authorization": f"JWT {token}",
        "User-Agent": user_agent,
        "X-Build-Number": TAXIGO_DRIVER_BUILD_NUMBER,
        "X-App-Version": TAXIGO_DRIVER_APP_VERSION,
        "X-Platform": "iOS",
        "X-Role": "driver",
    }
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code == 401:
        raise RuntimeError("401 Unauthorized，LINE GO driver JWT 可能已過期")
    response.raise_for_status()
    return response.json()


def is_taxigo_driver_airport_job(job):
    text = " ".join([
        str(job.get("start_address") or ""),
        str(job.get("end_address") or ""),
        str((job.get("stops") or [{}])[-1].get("address") if job.get("stops") else ""),
    ]).upper()
    airport_keywords = (
        "機場", "航廈", "AIRPORT",
        "TPE", "TSA", "KHH", "RMQ", "CYI", "TNN",
        "HUN", "TTT", "MZG", "KNH", "LZN", "MFK",
    )
    return any(keyword in text for keyword in airport_keywords)


def build_taxigo_driver_reservation_jobs(limit=10):
    settings = load_taxigo_driver_settings()
    data = get_taxigo_driver_open_reservations()
    jobs = data.get("data") or []
    filtered = []
    for job in jobs:
        fare = ((job.get("estimate") or {}).get("fare_range") or [None])[0]
        if not isinstance(fare, (int, float)) or fare < settings["min_fare"]:
            continue
        if settings.get("airport_only") and not is_taxigo_driver_airport_job(job):
            continue
        job = dict(job)
        job["reserveTimeText"] = _format_unix_time(job.get("reserve_time"))
        filtered.append(job)
    filtered.sort(key=lambda item: _parse_int(item.get("reserve_time"), 0))
    return filtered[:limit]


def _load_taxigo_driver_sent_log():
    return _load_json_file(TAXIGO_DRIVER_SENT_LOG_PATH, "LINE GO 已推送紀錄")


def _save_taxigo_driver_sent_log(data):
    cutoff = (datetime.datetime.utcnow() + datetime.timedelta(hours=8) - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    cleaned = {
        date_key: sorted(set(job_ids))
        for date_key, job_ids in data.items()
        if date_key >= cutoff and isinstance(job_ids, list)
    }
    _save_json_file(TAXIGO_DRIVER_SENT_LOG_PATH, cleaned, "LINE GO 已推送紀錄")


def get_unsent_taxigo_driver_reservation_jobs(limit=10):
    jobs = build_taxigo_driver_reservation_jobs(limit=50)
    today = _today_taipei_str()
    sent_log = _load_taxigo_driver_sent_log()
    sent_ids = set(sent_log.get(today, []))
    unsent_jobs = [
        job for job in jobs
        if str(job.get("trip_id") or job.get("trip_hash") or "") not in sent_ids
    ][:limit]
    return unsent_jobs, sent_log, today


def format_taxigo_driver_seen_count(sent_log, today):
    return len(set(sent_log.get(today, [])))


def mark_taxigo_driver_reservation_jobs_sent(jobs, sent_log, today):
    if not jobs:
        return
    sent_ids = set(sent_log.get(today, []))
    for job in jobs:
        job_id = str(job.get("trip_id") or job.get("trip_hash") or "")
        if job_id:
            sent_ids.add(job_id)
    sent_log[today] = sorted(sent_ids)
    _save_taxigo_driver_sent_log(sent_log)


def taxigo_driver_reservation_monitor_worker():
    print("🚕 LINE GO 預約單監控啟動...")
    while True:
        settings = load_taxigo_driver_settings()
        try:
            if settings.get("active"):
                jobs, sent_log, today = get_unsent_taxigo_driver_reservation_jobs()
                if jobs:
                    pushed = safe_push_message(
                        ADMIN_UUID,
                        create_taxigo_driver_reservation_flex(jobs, title="LINE GO 預約單", subtitle="driver open reservations"),
                        feature_key="taxigo_driver_reservation",
                        feature_name="LINE GO預約單監控",
                    )
                    if pushed:
                        mark_taxigo_driver_reservation_jobs_sent(jobs, sent_log, today)
        except Exception as exc:
            print(f"❌ LINE GO 預約單監控錯誤: {exc}")
            if _is_taxigo_driver_token_error(exc):
                notify_taxigo_driver_token_error_once_daily(exc)
            elif _is_line_monthly_quota_error(exc):
                handle_line_quota_exceeded("taxigo_driver_reservation", "LINE GO預約單監控")
        settings = load_taxigo_driver_settings()
        if not settings.get("active"):
            time.sleep(60)
            continue
        sleep_seconds = get_taxigo_driver_monitor_sleep_seconds(settings)
        print(f"⏱️ LINE GO 下一次監控：{sleep_seconds} 秒後")
        time.sleep(sleep_seconds)


threading.Thread(target=taxigo_driver_reservation_monitor_worker, daemon=True).start()


def reply_taxigo_driver_manual_check(reply_token):
    jobs, sent_log, today = get_unsent_taxigo_driver_reservation_jobs()
    if not jobs:
        settings = load_taxigo_driver_settings()
        seen_count = format_taxigo_driver_seen_count(sent_log, today)
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=(
                "LINE GO 預約單\n"
                f"目前沒有新的預估車資 >= NT$ {settings['min_fare']} 的資料。\n"
                f"機場單：{'只抓機場單' if settings.get('airport_only') else '不限'}\n"
                f"今日已顯示：{seen_count} 筆"
            ))
        )
        return
    line_bot_api.reply_message(
        reply_token,
        create_taxigo_driver_reservation_flex(jobs, title="LINE GO 預約單", subtitle="driver open reservations")
    )
    mark_taxigo_driver_reservation_jobs_sent(jobs, sent_log, today)

# -----------------------------------------------------------
# 🕷️ 核心業務：爬蟲執行任務 (罰單查詢)
# -----------------------------------------------------------
def report_crawler_error(user_id, car, driver, error, is_auto=False):
    """將查詢錯誤與當下瀏覽器截圖通知出去。"""
    target_id = ADMIN_UUID if is_auto else user_id
    plate = car.get("plate_no") or car.get("sub_id") or "未設定"
    error_text = (
        f"❌ 罰單查詢失敗\n"
        f"車輛：{car.get('name', '未命名')}\n"
        f"車號：{plate}\n"
        f"錯誤：{type(error).__name__}: {error}"
    )
    messages = [TextSendMessage(text=error_text[:2000])]
    try:
        screenshot = driver.get_screenshot_as_base64()
        image_url = upload_to_imgbb(screenshot)
        if image_url:
            messages.append(ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url,
            ))
    except Exception as screenshot_error:
        print(f"⚠️ 無法取得查詢錯誤截圖：{screenshot_error}")

    if is_auto:
        for message in messages:
            safe_push_message(
                target_id,
                message,
                feature_key="scheduled_fines",
                feature_name="排程查罰單錯誤通知",
            )
    else:
        line_bot_api.push_message(target_id, messages)


def process_crawling_task(user_id, car_list, reply_token=None, is_auto=False):
    """執行監理站爬蟲並回傳結果"""
    if not is_auto: send_loading_animation(user_id, duration=60)
    
    # 排程與手動查詢都使用 headless，錯誤時另行擷取瀏覽器截圖通知。
    driver = new_chrome(headless=True)
    messages = []
    summary = []

    try:
        for car in car_list:
            if car["mode"] == "personal" and (car.get("id") in ("", "未設定") or len(car.get("id", "")) != 10):
                summary.append(f"⚠️ {car['name']}：尚未補身分證，請先到「編輯車輛」補齊後再查詢。")
                continue
            driver.get(MV_DIS_URL)
            success = False
            error_reported = False
            for _ in range(3): # 最多嘗試 3 次
                try:
                    prepare_page_mode(driver, car['mode'])
                    captcha = get_captcha_and_solve(driver, car['mode'])
                    execute_query(driver, car['mode'], car['id'], car['sub_id'], captcha)
                    time.sleep(2)

                    try:
                        alert = driver.switch_to.alert
                        alert.accept()
                        driver.refresh()
                        continue
                    except Exception:
                        pass
                    
                    if "驗證碼錯誤" in driver.page_source: continue
                    
                    if "查無" in driver.page_source and "資料" in driver.page_source:
                        summary.append(f"✅ {car['name']}：無違規")
                        success = True
                        break
                    else:
                        records = get_all_pages_data(driver)
                        if records:
                            display_records = records
                            plate_note = ""
                            if car["mode"] == "personal":
                                display_records, matched_plate = filter_records_for_personal_plate(car, records)
                                if matched_plate:
                                    # plate_note = f"（已依車牌 {car['plate_no']} 篩選）"
                                    if not display_records:
                                        summary.append(f"✅ {car['name']}：無違規")
                                        success = True
                                        break
                                else:
                                    plate_note = "（尚未設定車牌，顯示全部罰單）"

                            summary.append(f"🚨 {car['name']}：發現 {len(display_records)} 筆罰單{plate_note}")
                            for rec in display_records:
                                imgs = []
                                if rec['單號'].startswith('A'):
                                    b64s = get_taipei_photos(rec['單號'], rec['車號'], car['id'])
                                    imgs = [upload_to_imgbb(b) for b in b64s]
                                elif rec['單號'].startswith('C'):
                                    b64s = get_new_taipei_photos(rec['單號'])
                                    imgs = [upload_to_imgbb(b) for b in b64s]
                                elif rec['單號'].startswith('D'):
                                    raw_time = rec.get('違規時間', '') # 假設是 "2026/04/08 10:30" 或 "20260408"
                                    
                                    # 移除斜線並只取日期部分
                                    clean_date = raw_time.split(' ')[0].replace('/', '')
                                    
                                    # 判斷是否為西元年 (前四碼大於 1911)
                                    if int(clean_date[:4]) > 1911:
                                        year = int(clean_date[:4]) - 1911
                                        month_day = clean_date[4:]
                                        vil_date = f"{year:03d}{month_day}"
                                    else:
                                        # 如果本來就是民國年，直接取前 7 碼
                                        vil_date = clean_date[:7]

                                    print(f"✅ 桃園格式化日期：{vil_date}") # 這邊應該會印出 1150408
                                    b64s = get_taoyuan_photos(rec['單號'], vil_date, rec['車號'])
                                    imgs = [upload_to_imgbb(b) for b in b64s]
                                analysis_key = uuid.uuid4().hex[:12]
                                ai_analysis_cache[analysis_key] = {
                                    "user_id": user_id,
                                    "tkt_no": rec['單號'],
                                    "fact": rec['違規事實'].strip(),
                                    "img_url": imgs[0] if imgs else DEFAULT_HERO_IMAGE,
                                    "created_at": time.time(),
                                }
                                messages.append(create_fine_flex_message(rec, car['id'], imgs, analysis_key=analysis_key))
                            success = True
                            break
                        driver.refresh()
                except Exception as e:
                    print(f"查詢重試失敗: {e}")
                    if not error_reported:
                        report_crawler_error(user_id, car, driver, e, is_auto=is_auto)
                        error_reported = True
                    try:
                        driver.refresh()
                    except Exception as refresh_error:
                        print(f"⚠️ 錯誤後重新整理失敗：{refresh_error}")
                        break
            if not success: summary.append(f"⚠️ {car['name']}：查詢失敗")

        final_msgs = [TextSendMessage(text="📅 查詢報告：\n" + "\n".join(summary or ["本次沒有可顯示的結果。"]))]
        if len(messages) > 3:
            final_msgs.extend(messages[:3])
            final_msgs.append(TextSendMessage(text="⚠️ 罰單較多，僅顯示前幾筆，請至監理站查詢完整內容。"))
        else:
            final_msgs.extend(messages)
        
        if is_auto:
            for m in final_msgs:
                if not safe_push_message(
                    user_id,
                    m,
                    feature_key="scheduled_fines",
                    feature_name="排程查罰單",
                ):
                    break
        else:
            line_bot_api.reply_message(reply_token, final_msgs)
    finally:
        driver.quit()

# -----------------------------------------------------------
# 🤖 LINE Webhook 路由
# -----------------------------------------------------------
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except LineBotApiError as exc:
        if "Invalid reply token" in str(exc):
            print(f"⚠️ ignore invalid reply token: {exc}")
            print(body)
            return 'OK'
        print(f"❌ callback line api error: {exc}")
        print(body)
        abort(400)
    except Exception as exc:
        print(f"❌ callback error: {exc}")
        print(body)
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(event.reply_token, build_welcome_message())

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    compact_msg = msg.replace(" ", "")
    global user_sessions, edit_car_sessions, ride_compare_sessions, flight_search_sessions

    if compact_msg in ("申請一般會員", "一般會員", "加入一般會員"):
        handle_member_application(user_id, event.reply_token, "normal")
        return

    if compact_msg in ("VIP會員", "申請VIP會員", "加入VIP會員", "申請VIP", "我要申請VIP", "VIP申請"):
        handle_member_application(user_id, event.reply_token, "vip")
        return

    if handle_vip_command(user_id, msg, event.reply_token):
        return

    # 1. 中斷流程
    if msg == "取消":
        user_sessions.pop(user_id, None)
        edit_car_sessions.pop(user_id, None)
        ride_compare_sessions.pop(user_id, None)
        flight_search_sessions.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 已取消目前流程。"))
        return

    if user_id in edit_car_sessions:
        if handle_car_edit_text(user_id, msg, event.reply_token):
            return

    ride_session = ride_compare_sessions.get(user_id)
    if ride_session and ride_session.get("step") in ("wait_ride_pickup", "wait_ride_destination"):
        label = "上車地點" if ride_session["step"] == "wait_ride_pickup" else "目的地"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"請用 LINE 內建位置功能傳送{label}。",
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=LocationAction(label=f"📍 傳送{label}")),
                    QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消")),
                ]),
            ),
        )
        return

    # 2. 狀態機：車輛綁定流程
    if user_id in user_sessions:
        session = user_sessions[user_id]
        step = session["step"]
        
        if step == "wait_p_name" or step == "wait_c_name":
            session["data"]["name"] = msg
            session["step"] = "wait_p_id" if step == "wait_p_name" else "wait_c_tax"
            prompt = (
                f"收到暱稱「{msg}」👌\n\n接著請輸入「身分證字號」（10碼）："
                if step == "wait_p_name"
                else f"收到暱稱「{msg}」👌\n\n接著請輸入「公司統編」(8碼)："
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=prompt, quick_reply=cancel_menu))

        elif step == "wait_p_id" or step == "wait_c_tax":
            if step == "wait_p_id":
                clean_id = msg.upper().strip()
                if len(clean_id) != 10:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 身分證字號應為 10 碼，請重新輸入：", quick_reply=cancel_menu))
                    return
                session["data"]["id"] = clean_id
                session["step"] = "wait_p_birthday"
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text="接著請輸入「生日」🎂\n(格式：民國年7碼，例如 0800101)：",
                        quick_reply=cancel_menu
                    )
                )
                return

            if len(msg) != 8 or not msg.isdigit():
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 統編應為 8 位數字，請重新輸入：", quick_reply=cancel_menu))
                return
            session["data"]["id"] = msg.upper()
            session["step"] = "wait_c_plate"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="請輸入「車牌號碼」：",
                    quick_reply=cancel_menu
                )
            )

        elif step == "wait_p_birthday" or step == "wait_c_plate":
            data = session["data"]
            if step == "wait_p_birthday":
                if len(msg) != 7 or not msg.isdigit():
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 生日格式錯誤，請輸入 7 位數字，例如 0800101：", quick_reply=cancel_menu))
                    return
                session["data"]["birthday"] = msg
                session["step"] = "wait_p_plate"
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text="最後請輸入「車牌號碼」：",
                        quick_reply=cancel_menu
                    )
                )
                return

            plate = format_plate_text(msg)
            if len(normalize_plate_text(plate)) < 4:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 車牌格式太短，請重新輸入車牌號碼：", quick_reply=cancel_menu))
                return
            if check_car_exists(user_id, "2", plate):
                user_sessions.pop(user_id)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 車號「{plate}」已綁定過，請重新開始。"))
                return
            add_car(user_id, data["name"], "2", data["id"], plate, "")
            success_text = f"✅ 綁定成功！\n\n🏢 暱稱：{data['name']}\n🔢 統編：{data['id']}\n🚙 車號：{plate}"
            user_sessions.pop(user_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=success_text))

        elif step == "wait_p_plate":
            data = session["data"]
            plate = format_plate_text(msg)
            if len(normalize_plate_text(plate)) < 4:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 車牌格式太短，請重新輸入車牌號碼：", quick_reply=cancel_menu))
                return
            if check_car_exists(user_id, "2", plate):
                user_sessions.pop(user_id)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 車號「{plate}」已綁定過，請重新開始。"))
                return
            birthday = data["birthday"]
            add_car(user_id, data["name"], "1", data["id"], plate, birthday)
            success_text = f"✅ 綁定成功！\n\n🚗 暱稱：{data['name']}\n🪪 身分證：{data['id']}\n🎂 生日：{birthday}\n🚙 車牌：{plate}"
            user_sessions.pop(user_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=success_text))
        return

    # 3. 一般指令
    if msg == "綁定車輛":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請選擇類型：", quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="🚗 個人車", text="綁定個人車")),
            QuickReplyButton(action=MessageAction(label="🏢 公司車", text="綁定公司車"))
        ])))
    elif msg == "綁定個人車":
        max_cars = get_normal_max_cars()
        if not is_vip_user(user_id) and max_cars > 0 and len(get_user_cars(user_id)) >= max_cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ 一般用戶最多可綁定 {max_cars} 台車。VIP 可無限制綁定。"))
            return
        user_sessions[user_id] = {"step": "wait_p_name", "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入車輛『暱稱』(例如:小白)：", quick_reply=cancel_menu))
    elif msg == "綁定公司車":
        max_cars = get_normal_max_cars()
        if not is_vip_user(user_id) and max_cars > 0 and len(get_user_cars(user_id)) >= max_cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ 一般用戶最多可綁定 {max_cars} 台車。VIP 可無限制綁定。"))
            return
        user_sessions[user_id] = {"step": "wait_c_name", "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入車輛『暱稱』(例如:公司貨車)：", quick_reply=cancel_menu))
    elif msg in ("罰單查詢", "查罰單", "查詢罰單", "違規查詢"):
        can_query, quota_message = can_start_manual_query(user_id)
        if not can_query:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ {quota_message}"))
            return
        cars = get_user_cars(user_id)
        if not cars: line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先綁定車輛。"))
        else: line_bot_api.reply_message(event.reply_token, [TextSendMessage(text=f"請選擇要查詢哪一台車輛？\n{quota_message}"), create_car_selection_flex(cars)])
    elif msg == "查詢車輛" or msg == "查詢設定":
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📭 目前沒有綁定任何車輛。"))
        else:
            sched = get_schedule(user_id)
            sched_info = "無自動排程"
            if sched:
                s_type, s_val = sched
                if s_type == 'daily':
                    sched_info = f"每天 {s_val} 自動查詢"
                elif s_type == 'interval':
                    sched_info = f"每 {s_val} 天 09:00 自動查詢"
                elif s_type == 'weekly':
                    days_map = {'0': '一', '1': '二', '2': '三', '3': '四', '4': '五', '5': '六', '6': '日'}
                    sched_info = f"每週{days_map.get(str(s_val), s_val)} 09:00 自動查詢"
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text=f"📋 目前排程設定：{sched_info}"),
                create_car_list_flex(cars, mode='view')
            ])
    elif msg == "設定排程":
        if not is_vip_user(user_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 自動排程為 VIP 功能。一般用戶可使用手動查詢，每日 5 次。"))
            return
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先綁定車輛後，才能設定排程。"))
            return
        quick_reply = QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="每週一 09:00", text="每週一 09:00")),
            QuickReplyButton(action=MessageAction(label="每 3 天", text="每 3 天")),
            QuickReplyButton(action=MessageAction(label="❌ 取消排程", text="取消排程"))
        ])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請選擇自動查詢的頻率：", quick_reply=quick_reply))
    elif msg.startswith("每天 ") or (msg.startswith("每 ") and "天" in msg) or msg == "每週一 09:00":
        if not is_vip_user(user_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 自動排程為 VIP 功能。一般用戶可使用手動查詢，每日 5 次。"))
            return
        if not get_user_cars(user_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先綁定車輛。"))
            return
        try:
            user_name = get_line_user_name(user_id)
            if msg.startswith("每天"):
                time_val = msg.split()[1]
                datetime.datetime.strptime(time_val, "%H:%M")
                set_schedule(user_id, 'daily', time_val, user_name)
                reply = f"⏰ 已設定：每天 {time_val} 自動查詢。"
            elif msg == "每週一 09:00":
                set_schedule(user_id, 'weekly', '0', user_name)
                reply = "🗓️ 已設定：每週一 09:00 自動查詢。"
            else:
                days = re.findall(r'\d+', msg)[0]
                set_schedule(user_id, 'interval', days, user_name)
                reply = f"🗓️ 已設定：每 {days} 天 09:00 自動查詢一次。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        except Exception as e:
            print(f"設定排程錯誤: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 格式錯誤或系統異常，請重試。"))
    elif msg == "取消排程":
        delete_schedule(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔕 已取消所有自動排程。"))
    elif msg == "清除車輛":
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📭 目前沒有綁定車輛。"))
        else:
            line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="請選擇要刪除的車輛："), create_car_list_flex(cars, mode='delete')])
    elif msg in ("編輯車輛", "修改車輛"):
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📭 目前沒有綁定車輛。"))
        else:
            line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="請選擇要編輯的車輛："), create_car_list_flex(cars, mode='edit')])
    elif msg == "選號":
        threading.Thread(target=run_plate_crawler, args=(user_id, event.reply_token), daemon=True).start()
    elif msg in ("叫車比價", "比價", "查詢車資"):
        ride_compare_sessions[user_id] = {"step": "wait_ride_pickup", "data": {}, "updated_at": time.time()}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請先傳送上車地點。",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=LocationAction(label="📍 傳送上車地點")),
                QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消")),
            ])
        ))
    elif compact_msg in ("查詢航班", "航班查詢", "查航班", "即時航班"):
        start_flight_search(user_id, event.reply_token)
    elif flight_query := parse_flight_number_query(msg):
        flight_no, depart_code, arrive_code, search_date, date_is_explicit = flight_query
        handle_flight_number_search(
            user_id,
            event.reply_token,
            flight_no,
            depart_code=depart_code,
            arrive_code=arrive_code,
            search_date=search_date,
            date_is_explicit=date_is_explicit,
        )
    elif route_search_date := parse_flight_route_query(msg):
        start_flight_search(user_id, event.reply_token, search_date=route_search_date)
    elif msg == "計程車免費車位查詢":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請點下方按鈕傳送您的位置，我幫您查詢附近的計程車免費車位。", quick_reply=QuickReply(items=[
            QuickReplyButton(action=LocationAction(label="📍 傳送位置"))
        ])))
    elif re.match(r"^\[?\s*55688\s*token\s*[:：]", msg, re.IGNORECASE):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限更新 55688 token。"))
            return
        token_match = re.match(r"^\[?\s*55688\s*token\s*[:：]\s*(.*?)\s*\]?\s*$", msg, re.IGNORECASE)
        new_token = token_match.group(1).strip() if token_match else ""
        if not new_token:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入例如：55688 token :你的新token"))
            return
        try:
            env_path = update_55688_dispatch_token(new_token)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=(
                    "✅ 55688 DispatchToken 已更新\n"
                    f"token：{_mask_secret(new_token)}\n"
                    f"寫入：{env_path.name}\n\n"
                    "下一次監控會直接使用新 token。"
                ))
            )
        except Exception as exc:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ 55688 token 更新失敗：{type(exc).__name__}: {exc}")
            )
    elif msg in ("55688預約狀態", "55688派單狀態", "55688預約監控"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限查看 55688 預約監控。"))
            return
        summary = summarize_55688_reservation()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=format_55688_reservation_summary(summary)))
    elif msg.startswith("調整日期"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        settings_update = parse_55688_date_command(msg.replace("調整日期", "", 1))
        if not settings_update:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入例如：調整日期 20260814 或 調整日期 20260814~20260816，也可輸入 調整日期 全部 / 調整日期 今天")
            )
            return
        settings = persist_55688_settings(settings_update, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ 55688 日期已更新：{format_55688_date_text(settings)}"),
            create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS),
        ])
    elif msg.startswith("調整頻率"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        settings_update = parse_55688_frequency_command(msg.replace("調整頻率", "", 1))
        if not settings_update:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入例如：調整頻率 60 或 調整頻率 60~80")
            )
            return
        settings = persist_55688_settings(settings_update, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ 55688 頻率已更新：{format_55688_frequency_text(settings)}"),
            create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS),
        ])
    elif msg.startswith("調整門檻"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        numbers = re.findall(r"\d+", msg)
        if not numbers:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入例如：調整門檻450"))
            return
        settings = persist_55688_settings({"min_fare": int(numbers[0])}, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ 55688 門檻已更新：NT$ {settings['min_fare']}"),
            create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS),
        ])
    elif msg in ("55688設定", "55688監控設定"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        line_bot_api.reply_message(
            event.reply_token,
            create_55688_settings_flex(load_55688_settings(), NEW_TAIPEI_RESERVATION_AREAS)
        )
    elif msg.startswith("55688門檻"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        numbers = re.findall(r"\d+", msg)
        if not numbers:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入例如：55688門檻 350"))
            return
        settings = persist_55688_settings({"min_fare": int(numbers[0])}, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ 55688 門檻已更新為 NT$ {settings['min_fare']}"),
            create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS),
        ])
    elif msg.startswith("55688區域"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        area_ids = [int(value) for value in re.findall(r"\d+", msg)]
        area_ids = [area_id for area_id in area_ids if area_id in NEW_TAIPEI_RESERVATION_AREAS]
        if len(set(area_ids)) < MIN_55688_AREA_COUNT:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"請至少選 {MIN_55688_AREA_COUNT} 個區域，例如：55688區域 124,127,128,151")
            )
            return
        settings = persist_55688_settings({"areas": area_ids}, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ 55688 區域已更新：{format_55688_area_label(settings)}"),
            create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS),
        ])
    elif msg.startswith("55688日期"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return
        settings_update = parse_55688_date_command(msg.replace("55688日期", "", 1))
        if not settings_update:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入例如：55688日期 20260814 / 55688日期 20260814~20260816 / 55688日期 全部 / 55688日期 今天"))
            return
        settings = persist_55688_settings(settings_update, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ 55688 日期條件已更新：{format_55688_date_text(settings)}"),
            create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS),
        ])
    elif msg in ("55688預約明細", "55688派單明細", "55688明細測試"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限查看 55688 預約明細。"))
            return
        if TAIWANTAXI_RESERVATION_QA_MODE:
            try:
                reply_55688_manual_check(event.reply_token)
            except Exception as exc:
                if _is_55688_token_error(exc):
                    notify_55688_token_error_once_daily(exc)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"55688 預約單\n狀態：失敗\n訊息：{type(exc).__name__}: {exc}")
                )
            return
        try:
            data, items, total_filtered = get_55688_reservation_safe_details()
            text = format_55688_reservation_safe_details(data, items, total_filtered)
        except Exception as exc:
            if _is_55688_token_error(exc):
                notify_55688_token_error_once_daily(exc)
            text = f"55688 預約單明細測試\n狀態：失敗\n訊息：{type(exc).__name__}: {exc}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))
    elif msg in ("55688假單測試", "55688demo", "55688Demo"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限查看 55688 假單測試。"))
            return
        line_bot_api.reply_message(
            event.reply_token,
            create_55688_reservation_demo_flex(build_55688_reservation_demo_jobs())
        )
    elif re.match(r"^\[?\s*(?:LINEGO|LINE GO|Taxigo)\s*token\s*[:：]", msg, re.IGNORECASE):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限更新 LINE GO driver token。"))
            return
        token_match = re.match(r"^\[?\s*(?:LINEGO|LINE GO|Taxigo)\s*token\s*[:：]\s*(.*?)\s*\]?\s*$", msg, re.IGNORECASE)
        new_token = token_match.group(1).strip() if token_match else ""
        if not new_token:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入例如：LINEGO token :你的新JWT"))
            return
        try:
            env_path = update_taxigo_driver_jwt(new_token)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=(
                    "✅ LINE GO driver JWT 已更新\n"
                    f"token：{_mask_secret(_normalize_taxigo_driver_jwt(new_token))}\n"
                    f"寫入：{env_path.name}\n\n"
                    "下一次監控會直接使用新 token。"
                ))
            )
        except Exception as exc:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ LINE GO token 更新失敗：{type(exc).__name__}: {exc}")
            )
    elif msg in ("LINEGO預約設定", "LINE GO預約設定", "Taxigo預約設定", "LINEGO監控設定"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 LINE GO 預約監控。"))
            return
        line_bot_api.reply_message(
            event.reply_token,
            create_taxigo_driver_settings_flex(load_taxigo_driver_settings())
        )
    elif msg.startswith("LINEGO門檻") or msg.startswith("LINE GO門檻"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 LINE GO 預約監控。"))
            return
        numbers = re.findall(r"\d+", msg)
        if not numbers:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入例如：LINEGO門檻 500"))
            return
        settings = persist_taxigo_driver_settings({"min_fare": int(numbers[0])}, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ LINE GO 門檻已更新為 NT$ {settings['min_fare']}"),
            create_taxigo_driver_settings_flex(settings),
        ])
    elif msg in ("LINEGO機場", "LINE GO機場", "LINEGO只抓機場", "LINE GO只抓機場"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 LINE GO 預約監控。"))
            return
        current = load_taxigo_driver_settings()
        settings = persist_taxigo_driver_settings({"airport_only": not current.get("airport_only")}, updated_by=user_id)
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=f"✅ LINE GO 機場單條件已更新：{'只抓機場單' if settings.get('airport_only') else '不限'}"),
            create_taxigo_driver_settings_flex(settings),
        ])
    elif msg in ("LINEGO預約明細", "LINE GO預約明細", "LINEGO預約單", "LINEGO手動查詢"):
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限查看 LINE GO 預約明細。"))
            return
        try:
            reply_taxigo_driver_manual_check(event.reply_token)
        except Exception as exc:
            if _is_taxigo_driver_token_error(exc):
                notify_taxigo_driver_token_error_once_daily(exc)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"LINE GO 預約單\n狀態：失敗\n訊息：{type(exc).__name__}: {exc}")
            )
    elif msg == "remote":
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限切換爬蟲模式。"))
            return
        set_crawler_mode("remote")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚀 爬蟲模式已切換為：遠端 Grid 模式。"))
    elif msg == "local":
        if user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限切換爬蟲模式。"))
            return
        set_crawler_mode("local")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="💻 爬蟲模式已切換為：本地 Local 模式。"))
    elif msg == "備份資料庫":
        if user_id != ADMIN_UUID:
            return
        try:
            with open('users_cars.db', 'rb') as f:
                response = requests.post('https://file.io', files={'file': f}, timeout=30)
            if response.status_code == 200:
                download_link = response.json().get('link')
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📦 SQLite 備份成功！\n注意：此連結下載一次後即失效\n\n{download_link}"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 上傳失敗，狀態碼: {response.status_code}"))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 備份錯誤: {e}"))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    user_id = event.source.user_id
    session = ride_compare_sessions.get(user_id)
    if session and session.get("step") == "wait_ride_pickup":
        session["data"]["pickup"] = build_location(event.message)
        print(f"ride compare pickup event: {session['data']['pickup']}")
        session["step"] = "wait_ride_destination"
        session["updated_at"] = time.time()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="收到上車地點，請再傳送目的地。",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=LocationAction(label="📍 傳送目的地")),
                QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消")),
            ])
        ))
        return

    if session and session.get("step") == "wait_ride_destination":
        pickup = session["data"]["pickup"]
        destination = build_location(event.message)
        print(f"ride compare destination event: {destination}")
        ride_compare_sessions.pop(user_id, None)
        user_sessions.pop(user_id, None)
        send_loading_animation(user_id, duration=20)
        try:
            compare_result = compare_ride_fares(pickup, destination)
            messages = [create_ride_compare_flex(compare_result)]
            if compare_result.get("errors"):
                messages.append(TextSendMessage(text="部分平台未取得固定價：\n" + "\n".join(compare_result["errors"][:3])))
            line_bot_api.reply_message(event.reply_token, messages)
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 比價失敗：{e}"))
        return

    user_pos = (event.message.latitude, event.message.longitude)
    lots = PARKING_CACHE.copy()
    for lot in lots:
        lot['distance'] = round(geodesic(user_pos, (lot['lat'], lot['lng'])).km, 2)
    nearby = sorted(lots, key=lambda x: x['distance'])[:5]
    line_bot_api.reply_message(event.reply_token, create_parking_flex(nearby))

@handler.add(PostbackEvent)
def handle_postback(event):
    data = parse_qs(event.postback.data)
    action = data.get('action', [''])[0]
    if action.startswith("55688_"):
        if event.source.user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 55688 監控。"))
            return

        settings = load_55688_settings()
        try:
            if action == "55688_settings":
                line_bot_api.reply_message(
                    event.reply_token,
                    create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS)
                )
                return
            elif action == "55688_area_menu":
                line_bot_api.reply_message(
                    event.reply_token,
                    create_55688_area_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS)
                )
                return
            elif action == "55688_active_toggle":
                settings = persist_55688_settings({"active": not settings.get("active")}, updated_by=event.source.user_id)
            elif action == "55688_min_fare":
                value = _parse_int(data.get("value", ["0"])[0], settings["min_fare"])
                settings = persist_55688_settings({"min_fare": value}, updated_by=event.source.user_id)
            elif action == "55688_area_toggle":
                area_id = _parse_int(data.get("area", ["0"])[0])
                areas = set(settings.get("areas", []))
                if area_id in areas:
                    if len(areas) <= MIN_55688_AREA_COUNT:
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text=f"⚠️ 前端至少需要 {MIN_55688_AREA_COUNT} 個區域，不能再取消。")
                        )
                        return
                    areas.remove(area_id)
                elif area_id in NEW_TAIPEI_RESERVATION_AREAS:
                    areas.add(area_id)
                settings = persist_55688_settings({"areas": sorted(areas)}, updated_by=event.source.user_id)
            elif action == "55688_date_mode":
                mode = data.get("mode", ["all"])[0]
                if mode == "today":
                    settings = persist_55688_settings({"date_mode": "today", "date_value": ""}, updated_by=event.source.user_id)
                else:
                    settings = persist_55688_settings({"date_mode": "all", "date_value": ""}, updated_by=event.source.user_id)
            elif action == "55688_manual_check":
                reply_55688_manual_check(event.reply_token)
                return

            line_bot_api.reply_message(
                event.reply_token,
                [TextSendMessage(text="✅ 55688 設定已更新"), create_55688_settings_flex(settings, NEW_TAIPEI_RESERVATION_AREAS)]
            )
        except Exception as exc:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 55688 設定更新失敗：{type(exc).__name__}: {exc}"))
    elif action.startswith("taxigo_driver_"):
        if event.source.user_id != ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限管理 LINE GO 預約監控。"))
            return

        settings = load_taxigo_driver_settings()
        try:
            if action == "taxigo_driver_active_toggle":
                settings = persist_taxigo_driver_settings({"active": not settings.get("active")}, updated_by=event.source.user_id)
            elif action == "taxigo_driver_airport_toggle":
                settings = persist_taxigo_driver_settings({"airport_only": not settings.get("airport_only")}, updated_by=event.source.user_id)
            elif action == "taxigo_driver_min_fare":
                value = _parse_int(data.get("value", ["0"])[0], settings["min_fare"])
                settings = persist_taxigo_driver_settings({"min_fare": value}, updated_by=event.source.user_id)
            elif action == "taxigo_driver_manual_check":
                reply_taxigo_driver_manual_check(event.reply_token)
                return

            line_bot_api.reply_message(
                event.reply_token,
                [TextSendMessage(text="✅ LINE GO 設定已更新"), create_taxigo_driver_settings_flex(settings)]
            )
        except Exception as exc:
            if _is_taxigo_driver_token_error(exc):
                notify_taxigo_driver_token_error_once_daily(exc)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ LINE GO 設定更新失敗：{type(exc).__name__}: {exc}"))
    elif action == 'check_one_car':
        car = get_user_car_by_id(event.source.user_id, data.get('car_id', [''])[0])
        if car:
            can_query, quota_message = can_start_manual_query(event.source.user_id)
            if not can_query:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ {quota_message}"))
                return
            try:
                record_manual_query(event.source.user_id)
            except Exception:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 查詢額度紀錄失敗，請稍後再試或確認 Supabase 用量表已建立。"))
                return
            threading.Thread(target=process_crawling_task, args=(event.source.user_id, [car], event.reply_token), daemon=True).start()
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 找不到該車輛資料，可能已被刪除或不屬於您。"))
    elif action == 'edit_car':
        car = get_user_car_by_id(event.source.user_id, data.get('car_id', [''])[0])
        if car:
            start_car_edit_session(event.source.user_id, car)
            line_bot_api.reply_message(event.reply_token, build_edit_menu_message(edit_car_sessions[event.source.user_id]))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 找不到該車輛資料，可能已被刪除或不屬於您。"))
    elif action == 'delete_car':
        if delete_specific_car(event.source.user_id, data.get('car_id', [''])[0]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ 已刪除 {data.get('car_name',[''])[0]}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 刪除失敗，找不到該車輛資料。"))
    elif action in ("vip_approve", "vip_reject", "member_approve", "member_reject"):
        if not is_admin_user(event.source.user_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 只有管理員可以審核會員申請。"))
            return

        target_id = data.get("line_id", [""])[0]
        if not target_id:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 缺少申請人的 LINE ID。"))
            return

        display_name = get_line_user_name(target_id)
        is_vip_request = action.startswith("vip_")
        is_approve = action.endswith("_approve")
        member_label = "VIP" if is_vip_request else "一般會員"
        display_target = display_name if display_name != '未知用戶' else target_id
        try:
            if is_approve and is_vip_request:
                upsert_vip_user(target_id, display_name=display_name, note="申請核准", created_by=event.source.user_id)
                result_text = f"✅ 已核准 VIP：{display_target}"
                try:
                    line_bot_api.push_message(target_id, TextSendMessage(text="✅ 你的 VIP 申請已核准，現在已可使用 VIP 功能。"))
                except Exception as push_error:
                    print(f"⚠️ VIP 核准通知推送失敗: {push_error}")
            elif is_approve:
                result_text = f"✅ 已核准一般會員：{display_target}"
                try:
                    line_bot_api.push_message(
                        target_id,
                        TextSendMessage(
                            text="✅ 你的一般會員申請已核准，現在可以開始綁定車輛與查詢罰單。"
                        )
                    )
                except Exception as push_error:
                    print(f"⚠️ 一般會員核准通知推送失敗: {push_error}")
            else:
                result_text = f"已拒絕{member_label}申請：{display_target}"
                try:
                    line_bot_api.push_message(target_id, TextSendMessage(text=f"你的{member_label}申請未通過，如需協助請再聯絡管理員。"))
                except Exception as push_error:
                    print(f"⚠️ {member_label}拒絕通知推送失敗: {push_error}")

            rows = list_vip_users(include_inactive=True)
            messages = [TextSendMessage(text=result_text)]
            if rows and is_vip_request:
                messages.append(create_vip_list_flex(rows[:12], admin_line_id=ADMIN_UUID))
            line_bot_api.reply_message(event.reply_token, messages)
        except Exception as e:
            print(f"❌ {member_label}申請審核失敗: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ {member_label}申請審核失敗，請稍後再試。"))

    elif action in ("vip_toggle", "vip_delete"):
        if not is_admin_user(event.source.user_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 只有管理員可以管理 VIP。"))
            return

        target_id = data.get("line_id", [""])[0]
        if not target_id:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 缺少 VIP LINE ID。"))
            return
        if target_id == ADMIN_UUID:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 管理員帳號不可停用或刪除。"))
            return

        try:
            if action == "vip_toggle":
                next_active = data.get("active", ["1"])[0] == "1"
                set_vip_active(target_id, next_active)
                result_text = f"✅ 已{'啟用' if next_active else '停用'} VIP：{target_id}"
            else:
                delete_vip_user(target_id)
                result_text = f"🗑️ 已刪除 VIP：{target_id}"

            rows = list_vip_users(include_inactive=True)
            line_bot_api.reply_message(
                event.reply_token,
                [TextSendMessage(text=result_text), create_vip_list_flex(rows[:12], admin_line_id=ADMIN_UUID)]
            )
        except Exception as e:
            print(f"❌ VIP postback action failed: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ VIP 操作失敗，請稍後再試。"))
    elif action == "flight_select_region":
        role = data.get("role", [""])[0]
        region_code = data.get("region", [""])[0]
        if role not in ("depart", "arrive") or not get_region(region_code):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 航班選單資料錯誤，請重新輸入「查詢航班」。"))
            return
        flight_search_sessions.setdefault(event.source.user_id, {"step": "", "data": {}})
        line_bot_api.reply_message(event.reply_token, build_flight_city_selection(role, region_code))
    elif action == "flight_select_city":
        role = data.get("role", [""])[0]
        city_code = data.get("code", [""])[0]
        if role not in ("depart", "arrive"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 航班選單資料錯誤，請重新輸入「查詢航班」。"))
            return
        handle_flight_city_selected(event.source.user_id, event.reply_token, role, city_code)
    elif action == "flight_result_page":
        try:
            page = int(data.get("page", ["0"])[0])
        except ValueError:
            page = 0
        filter_type = data.get("filter", [""])[0]
        reply_flight_result_page(event.source.user_id, event.reply_token, page, filter_type=filter_type)
    elif action == "flight_result_filter":
        filter_type = data.get("filter", ["active"])[0]
        if filter_type not in ("active", "arrived"):
            filter_type = "active"
        reply_flight_result_page(event.source.user_id, event.reply_token, 0, filter_type=filter_type)
    elif action == 'ai_analyze':
        analysis_key = data.get('key', [''])[0]
        cached = ai_analysis_cache.get(analysis_key)
        user_id = event.source.user_id
        if not cached or cached.get("user_id") != user_id:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 找不到這筆罰單分析資料，請重新查詢後再試一次。"))
            return

        tkt_no = cached["tkt_no"]
        img_url = cached["img_url"]
        fact = cached["fact"]
        send_loading_animation(user_id, duration=60)

        def run_ai_and_push():
            advice = get_ai_appeal_advice(tkt_no, fact, img_url)
            line_bot_api.push_message(user_id, TextSendMessage(text=f"【🤖 罰單 AI 評估報告】\n\n{advice}"))
            ai_analysis_cache.pop(analysis_key, None)

        threading.Thread(target=run_ai_and_push, daemon=True).start()

def run_plate_crawler(user_id, reply_token):
    send_loading_animation(user_id, duration=60)
    plates = crawl_plate_numbers()
    if not plates:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="⚠️ 查詢失敗或目前無可選號碼。"))
        return

    total = len(plates)
    message_batches = [plates[i:i + 300] for i in range(0, len(plates), 300)]
    messages_to_send = [TextSendMessage(text=f"🔍 查詢完成，共 {total} 筆資料。")]
    for index, batch in enumerate(message_batches):
        if len(messages_to_send) >= 5:
            break
        messages_to_send.append(create_plate_flex(batch, index + 1, total))
    line_bot_api.reply_message(reply_token, messages_to_send)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
