from flask import Flask, request, abort
import threading
from geopy.distance import geodesic
import time
import datetime
import re
import requests
from urllib.parse import parse_qs

from config import handler, line_bot_api, MV_DIS_URL, ADMIN_UUID
from database import (
    reload_parking_data, PARKING_CACHE, add_car, check_car_exists,
    get_user_cars, get_user_car_by_id, delete_specific_car,
    set_schedule, get_schedule, delete_schedule,
    update_last_run, get_all_schedules, get_line_user_name
)
from ui_templates import (
    create_parking_flex, create_car_list_flex, 
    create_car_selection_flex, create_fine_flex_message, create_plate_flex
)
from crawler_utils import (
    new_chrome, send_loading_animation, prepare_page_mode, get_captcha_and_solve,
    execute_query, get_taipei_photos, upload_to_imgbb, get_new_taipei_photos,
    get_all_pages_data, crawl_plate_numbers, get_ai_appeal_advice,
    set_crawler_mode
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, LocationMessage, LocationAction,
    PostbackEvent, QuickReply, QuickReplyButton, MessageAction
)

app = Flask(__name__)

# --- 全域變數：處理綁定流程的狀態機 ---
user_sessions = {}

# --- 共用元件：取消按鈕 ---
cancel_menu = QuickReply(items=[QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消"))])

# -----------------------------------------------------------
# 🛠️ 初始化：啟動時載入雲端停車場快取
# -----------------------------------------------------------
reload_parking_data()

# -----------------------------------------------------------
# ⏰ 背景任務：自動排程檢查器
# -----------------------------------------------------------
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
                    update_last_run(line_id)
                    cars = get_user_cars(line_id)
                    if cars:
                        # 啟動爬蟲執行緒 (不帶 reply_token，使用 push_message)
                        threading.Thread(target=process_crawling_task, args=(line_id, cars, None, True), daemon=True).start()
            
            time.sleep(60) # 每分鐘檢查一次
        except Exception as e:
            print(f"❌ 排程檢查錯誤: {e}")
            time.sleep(60)

threading.Thread(target=schedule_worker, daemon=True).start()

# -----------------------------------------------------------
# 🕷️ 核心業務：爬蟲執行任務 (罰單查詢)
# -----------------------------------------------------------
def process_crawling_task(user_id, car_list, reply_token=None, is_auto=False):
    """執行監理站爬蟲並回傳結果"""
    if not is_auto: send_loading_animation(user_id, duration=60)
    
    driver = new_chrome(headless=True)
    messages = []
    summary = []

    try:
        for car in car_list:
            driver.get(MV_DIS_URL)
            success = False
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
                            summary.append(f"🚨 {car['name']}：發現 {len(records)} 筆罰單！")
                            for rec in records:
                                imgs = []
                                if rec['單號'].startswith('A'):
                                    b64s = get_taipei_photos(rec['單號'], rec['車號'], car['id'])
                                    imgs = [upload_to_imgbb(b) for b in b64s]
                                elif rec['單號'].startswith('C'):
                                    b64s = get_new_taipei_photos(rec['單號'])
                                    imgs = [upload_to_imgbb(b) for b in b64s]
                                
                                messages.append(create_fine_flex_message(rec, car['id'], imgs))
                            success = True
                            break
                        driver.refresh()
                except Exception as e:
                    print(f"查詢重試失敗: {e}")
                    driver.refresh()
            if not success: summary.append(f"⚠️ {car['name']}：查詢失敗")

        final_msgs = [TextSendMessage(text="📅 查詢報告：\n" + "\n".join(summary or ["本次沒有可顯示的結果。"]))]
        if len(messages) > 3:
            final_msgs.extend(messages[:3])
            final_msgs.append(TextSendMessage(text="⚠️ 罰單較多，僅顯示前幾筆，請至監理站查詢完整內容。"))
        else:
            final_msgs.extend(messages)
        
        if is_auto:
            for m in final_msgs: line_bot_api.push_message(user_id, m)
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
    try: handler.handle(body, signature)
    except: abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    global user_sessions

    # 1. 中斷流程
    if msg == "取消":
        user_sessions.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 已取消目前流程。"))
        return

    # 2. 狀態機：車輛綁定流程
    if user_id in user_sessions:
        session = user_sessions[user_id]
        step = session["step"]
        
        if step == "wait_p_name" or step == "wait_c_name":
            session["data"]["name"] = msg
            session["step"] = "wait_p_id" if step == "wait_p_name" else "wait_c_tax"
            prompt = f"收到暱稱「{msg}」👌\n\n接著請輸入「身分證字號」(10碼)：" if step == "wait_p_name" else f"收到暱稱「{msg}」👌\n\n接著請輸入「公司統編」(8碼)："
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=prompt, quick_reply=cancel_menu))
        
        elif step == "wait_p_id" or step == "wait_c_tax":
            if step == "wait_p_id" and len(msg) != 10:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 身分證長度應為 10 碼，請重新輸入：", quick_reply=cancel_menu))
                return
            if step == "wait_c_tax" and (len(msg) != 8 or not msg.isdigit()):
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 統編應為 8 位數字，請重新輸入：", quick_reply=cancel_menu))
                return
            if check_car_exists(user_id, "1" if step == "wait_p_id" else "2", msg):
                user_sessions.pop(user_id)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 此資料已綁定過，請重新開始。"))
            else:
                session["data"]["id"] = msg.upper()
                session["step"] = "wait_p_birthday" if step == "wait_p_id" else "wait_c_plate"
                prompt = f"最後一步，請輸入「生日」🎂\n(格式：民國年7碼，例如 0800101)：" if step == "wait_p_id" else f"請輸入「車牌號碼」："
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=prompt, quick_reply=cancel_menu))

        elif step == "wait_p_birthday" or step == "wait_c_plate":
            data = session["data"]
            if step == "wait_p_birthday":
                if len(msg) != 7 or not msg.isdigit():
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 生日格式錯誤，請輸入 7 位數字，例如 0800101：", quick_reply=cancel_menu))
                    return
                add_car(user_id, data["name"], "1", data["id"], "", msg)
                success_text = f"✅ 綁定成功！\n\n🚗 暱稱：{data['name']}\n🪪 身分證：{data['id']}\n🎂 生日：{msg}"
            else:
                plate = msg.upper()
                if check_car_exists(user_id, "2", plate):
                    user_sessions.pop(user_id)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 車號「{plate}」已綁定過，請重新開始。"))
                    return
                add_car(user_id, data["name"], "2", data["id"], plate, "")
                success_text = f"✅ 綁定成功！\n\n🏢 暱稱：{data['name']}\n🔢 統編：{data['id']}\n🚙 車號：{plate}"
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
        user_sessions[user_id] = {"step": "wait_p_name", "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入車輛『暱稱』(例如:小白)：", quick_reply=cancel_menu))
    elif msg == "綁定公司車":
        user_sessions[user_id] = {"step": "wait_c_name", "data": {}}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入車輛『暱稱』(例如:公司貨車)：", quick_reply=cancel_menu))
    elif msg == "罰單查詢":
        cars = get_user_cars(user_id)
        if not cars: line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先綁定車輛。"))
        else: line_bot_api.reply_message(event.reply_token, [TextSendMessage(text="請選擇要查詢哪一台車輛？"), create_car_selection_flex(cars)])
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
    elif msg == "選號":
        threading.Thread(target=run_plate_crawler, args=(user_id, event.reply_token), daemon=True).start()
    elif msg == "計程車免費車位查詢":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請點下方按鈕傳送您的位置，我幫您查詢附近的計程車免費車位。", quick_reply=QuickReply(items=[
            QuickReplyButton(action=LocationAction(label="📍 傳送位置"))
        ])))
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
    if action == 'check_one_car':
        car = get_user_car_by_id(event.source.user_id, data.get('car_id', [''])[0])
        if car:
            threading.Thread(target=process_crawling_task, args=(event.source.user_id, [car], event.reply_token), daemon=True).start()
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 找不到該車輛資料，可能已被刪除或不屬於您。"))
    elif action == 'delete_car':
        if delete_specific_car(event.source.user_id, data.get('car_id', [''])[0]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ 已刪除 {data.get('car_name',[''])[0]}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 刪除失敗，找不到該車輛資料。"))
    elif action == 'ai_analyze':
        tkt_no = data.get('tkt_no', [''])[0]
        img_url = data.get('img_url', [''])[0]
        fact = data.get('fact', [''])[0]
        user_id = event.source.user_id
        send_loading_animation(user_id, duration=60)

        def run_ai_and_push():
            advice = get_ai_appeal_advice(tkt_no, fact, img_url)
            line_bot_api.push_message(user_id, TextSendMessage(text=f"【🤖 罰單 AI 評估報告】\n\n{advice}"))

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
