# ==========================================
# 📦 匯入模組 (Imports)
# ==========================================

# --- 標準函式庫 (Standard Libraries) ---
import base64
import datetime
import json
import os
import re
import threading
import time
import traceback
from urllib.parse import parse_qs
import openai
# --- 第三方套件 (Third-party Libraries) ---
import ddddocr
import PIL.Image
import requests
import urllib3
from dotenv import load_dotenv
from flask import Flask, request, abort
from geopy.distance import geodesic
from supabase import create_client

# --- 自動化與爬蟲相關 (Selenium) ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# --- LINE Bot SDK ---
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    LocationMessage, LocationAction, PostbackEvent, PostbackAction,
    QuickReply, QuickReplyButton, MessageAction
)

# ==========================================
# 🛠️ 環境初始化 (Initialization)
# ==========================================
CRAWLER_MODE = None # 全域變數，稍後根據指令設定為 "local" 或 "remote"
# 載入 .env 檔案
load_dotenv()

# 修正 Pillow 版本問題 (相容性修補)
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# 忽略 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# ⚙️ 系統設定區 (Configurations)
# ==========================================

# --- LINE Channel ---
LINE_CHANNEL_ACCESS_TOKEN  = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_SECRET        = os.getenv('LINE_CHANNEL_SECRET')

# --- Supabase 雲端資料庫 ---
SUPABASE_URL       = os.getenv('SUPABASE_URL')
SUPABASE_KEY       = os.getenv('SUPABASE_KEY')

# --- 外部服務 API ---
IMGBB_API_KEY      = os.getenv('IMGBB_API_KEY')
MV_DIS_URL         = os.getenv('MV_DIS_URL')

# --- 圖片設定 ---
DEFAULT_HERO_IMAGE = os.getenv('DEFAULT_HERO_IMAGE')

# --- AI 相關 ---
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
# ==========================================
# 🔌 實例初始化 (Instances)
# ==========================================

app          = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler      = WebhookHandler(LINE_SECRET)
supabase     = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 🚀 程式邏輯開始
# ==========================================

# --- 1. 在程式最上方 ---
PARKING_CACHE = []

def reload_parking_data():
    global PARKING_CACHE
    try:
        print("正在從雲端同步停車場資料...")
        response = supabase.table("parking_lots").select("*").execute()
        PARKING_CACHE = response.data
        print(f"✅ 同步完成！已成功載入 {len(PARKING_CACHE)} 筆資料。")
    except Exception as e:
        print("❌ 快取載入失敗，詳細錯誤如下：")
        print(e)  # 印出原始錯誤
        traceback.print_exc() # 印出詳細錯誤行數

# 程式啟動時先跑一次，把 658 筆資料抓進記憶體
reload_parking_data()

# ==========================================
# 🗄️ 資料庫管理 (新增 Schedules 表)
# ==========================================
def init_db():
    """現在僅作為連線測試"""
    try:
        supabase.table("cars").select("id").limit(1).execute()
        print("☁️ Supabase 雲端資料庫連線成功，準備服務 1000 位運將！")
    except Exception as e:
        print(f"❌ 連線失敗: {e}")

# --- 車輛相關 ---
def add_car(line_id, name, mode, pid, plate, birthday="", display_name=""):
    """新增車輛綁定"""
    # 取得 LINE 暱稱
    display_name = get_line_user_name(line_id)
    
    data = {
        "line_id": line_id,
        "name": name,
        "mode": mode,
        "pid": pid,
        "plate": plate,
        "birthday": birthday,
        "display_name": display_name
    }
    
    # 執行插入
    supabase.table("cars").insert(data).execute()
    print(f"✅ 已幫 {display_name} 綁定車牌 {plate}")

def check_is_bound(user_id, car_type, search_value):
    clean_val = search_value.upper().strip()
    
    # 這裡直接下 query 給雲端
    query = supabase.table("cars").select("id", count="exact").eq("line_id", user_id)
    
    if car_type == "1":
        res = query.eq("pid", clean_val).execute()
    else:
        res = query.eq("plate", clean_val).execute()
    
    # 加這行印出偵錯資訊，看看到底抓到幾筆
    print(f"DEBUG: 檢查 {clean_val}, 資料庫回傳數量: {res.count}")
    
    return res.count > 0
def get_line_user_name(user_id):
    """跟 LINE 伺服器查詢使用者的顯示名稱"""
    try:
        profile = line_bot_api.get_profile(user_id)
        return profile.display_name
    except:
        return "未知用戶"
def get_user_cars(line_id):
    """取得該使用者的所有車輛清單"""
    res = supabase.table("cars").select("*").eq("line_id", line_id).execute()
    
    rows = res.data
    cars = []
    for row in rows:
        # 維持原本的 Dictionary 結構，讓你的 Flex Message 函式不用改
        cars.append({
            "db_id": row['id'],        # Supabase 的唯一 ID
            "name": row['name'],
            "mode": "legal" if row['mode'] == "2" else "personal",
            "id": row['pid'],      
            "plate_no": row['plate'], 
            "sub_id": row['plate'] if row['mode'] == "2" else row['birthday'],
            "display_id": row['pid']   # 顯示用的證號
        })
    return cars

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

def delete_specific_car(line_id, car_db_id):
    """刪除指定 ID 的車輛 (需核對 line_id 避免刪錯別人的)"""
    res = supabase.table("cars").delete().eq("id", car_db_id).eq("line_id", line_id).execute()
    
    # 如果有資料被刪除，res.data 會有內容
    return len(res.data) > 0

def delete_user_cars(line_id):
    """刪除該使用者所有綁定"""
    supabase.table("cars").delete().eq("line_id", line_id).execute()
    print(f"🗑️ 已清除使用者 {line_id} 的所有綁定資料")
def create_car_list_flex(cars, mode='view'):
    """
    產生車輛列表卡片
    mode='view': 純查看 (查詢車輛)
    mode='delete': 顯示刪除按鈕 (清除綁定)
    """
    bubbles = []
    
    for car in cars:
        # 判斷車輛類型顯示文字
        type_text = "🏢 公司車" if car['mode'] == 'legal' else "🚗 個人車"
        id_text = f"統編: {car['id']}" if car['mode'] == 'legal' else f"身分證: {car['id']}"
        sub_text = f"車號: {car['sub_id']}" if car['mode'] == 'legal' else f"生日: {car['sub_id']}"

        # 卡片內容
        bubble = {
            "type": "bubble",
            "size": "micro", # 用小卡片比較好左右滑
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": car['name'], "weight": "bold", "size": "md", "color": "#1DB446"},
                    {"type": "text", "text": type_text, "size": "xxs", "color": "#aaaaaa"}
                ],
                "backgroundColor": "#f0f0f0"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": id_text, "size": "xs", "wrap": True},
                    {"type": "text", "text": sub_text, "size": "xs", "wrap": True}
                ],
                "spacing": "sm"
            }
        }

        # 如果是刪除模式，加上刪除按鈕
        if mode == 'delete':
            bubble["footer"] = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "color": "#FF3333",
                        "action": {
                            "type": "postback",
                            "label": "刪除此車",
                            # 這裡將 action 和車輛 ID 藏在 data 裡傳回後台
                            "data": f"action=delete_car&car_id={car['db_id']}&car_name={car['name']}",
                            "displayText": f"我要刪除 {car['name']}"
                        }
                    }
                ]
            }
        
        bubbles.append(bubble)

    return FlexSendMessage(
        alt_text="車輛列表",
        contents={
            "type": "carousel",
            "contents": bubbles
        }
    )
def create_car_selection_flex(cars):
    """產生讓使用者選擇要查詢哪台車的 Flex Message"""
    bubbles = []
    
    for car in cars:
        type_text = "🏢 公司車" if car['mode'] == 'legal' else "🚗 個人車"
        # 顯示車號或身分證
        sub_text = car['plate_no'] if car['plate_no'] else car['id']

        bubble = {
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": car['name'], "weight": "bold", "color": "#1DB446", "size": "sm"},
                    {"type": "text", "text": type_text, "size": "xxs", "color": "#aaaaaa"}
                ],
                "backgroundColor": "#f0f0f0",
                "paddingAll": "8px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": sub_text, "size": "xs", "align": "center", "weight": "bold"}
                ],
                "paddingAll": "10px"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "color": "#007bff",
                        "action": {
                            "type": "postback",
                            "label": "查詢此車",
                            # 將 action 設為 check_one_car，並帶上 car_id
                            "data": f"action=check_one_car&car_id={car['db_id']}",
                            "displayText": f"🔍 正在查詢 {car['name']}..."
                        }
                    }
                ],
                "paddingAll": "5px"
            }
        }
        bubbles.append(bubble)

    return FlexSendMessage(
        alt_text="請選擇要查詢的車輛",
        contents={
            "type": "carousel",
            "contents": bubbles
        }
    )
def send_loading_animation(user_id, duration=20):
    """
    顯示 LINE 聊天室的 Loading 動畫
    user_id: 使用者 ID
    duration: 動畫持續秒數 (預設 20秒，最長 60秒)
    """
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    data = {
        "chatId": user_id,
        "loadingSeconds": duration
    }
    try:
        # 使用 requests 直接呼叫，因為 line-bot-sdk v2 舊版可能還沒包裝這個功能
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        print(f"Loading 動畫發送失敗: {e}")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def get_ai_appeal_advice(tkt_no, fact, image_url):
    """
    使用 GPT-4o 進行罰單分析
    """
    prompt = f"""
    你是一位專業的台灣交通法律顧問。請分析以下違規案件並給予申訴建議：
    
    【違規事實】：{fact}
    【罰單單號】：{tkt_no}
    
    請根據我提供的罰單照片，觀察是否有以下有利於申訴的情況：
    1. 標線（紅/黃線）是否磨損不清晰？
    2. 是否有樹木、車輛或雜物遮擋禁止停車標誌？
    3. 採證照片是否模糊，難以辨識車牌或駕駛？
    4. 違規時間是否屬於深夜/離峰，且無阻礙交通之情事？
    
    請用台灣運將聽得懂、親切的語氣回答。
    最後，如果建議申訴，請提供一段簡短的『申訴理由書範本』。
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ],
                }
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI 分析失敗: {e}")
        return "抱歉大哥，AI 目前忙碌中，請稍後再試。"

# ==========================================
# 🎫 選號查詢爬蟲
# ==========================================
def crawl_plate_numbers():
    print("🚀 啟動選號爬蟲測試...")
    
    # 測試時建議設為 False，看得到畫面比較好 debug
    driver = new_chrome() 
    plates = []
    url = "https://www.mvdis.gov.tw/m3-emv-plate/webpickno/queryPickNo#"

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        # ===========================================
        # 0. 處理「接受」按鈕 (新增部分)
        # ===｀========================================
        try: 
            print("0. 正在點擊「接受」按鈕...")
            # 等待按鈕出現並可點擊
            accept_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '(//a[text()="接受"])[2]')))
            
            # 使用 JS 強制點擊 (避免被其他元素擋住)
            driver.execute_script("arguments[0].click();", accept_btn)
            time.sleep(1) # 等待視窗關閉或動畫結束
        except Exception as e:
            print(f"   -> 沒找到「接受」按鈕或點擊失敗 (可能已略過): {e}")

        # -------------------------------------------
        # 1. 填寫連動選單 (AJAX 載入需要等待)
        # -------------------------------------------
        print("1. 正在選擇：管轄監理單位 (臺北市區監理所)...")
        # 確保選單可點擊前，再次確認遮罩是否消失
        try:
            dept_el = wait.until(EC.element_to_be_clickable((By.ID, "selDeptCode")))
            Select(dept_el).select_by_visible_text("臺北市")
        except:
            # 有時候 blockUI 還沒消失，多等一下再試
            time.sleep(2)
            dept_el = driver.find_element(By.ID, "selDeptCode")
            Select(dept_el).select_by_visible_text("臺北市")
            
        time.sleep(1) # 等待地點選單載入

        print("2. 正在選擇：領牌地點 (臺北市區監理所)...")
        station_el = wait.until(EC.element_to_be_clickable((By.ID, "selStationCode")))
        try:
            Select(station_el).select_by_visible_text("臺北市區監理所")
        except:
            Select(station_el).select_by_index(1)
        time.sleep(1)

        print("3. 正在選擇：窗口 (臺北市八德路)...")
        win_el = wait.until(EC.element_to_be_clickable((By.ID, "selWindowNo")))
        Select(win_el).select_by_visible_text("臺北市八德路4段21號地下室")
        time.sleep(1) 

        print("4. 設定車輛參數 (汽車/非電能/自用小客車)...")
        
        # 車種別: 汽車
        car_type_el = driver.find_element(By.XPATH, "//tr[th[contains(text(),'車種別')]]//select")
        Select(car_type_el).select_by_visible_text("汽車")
        time.sleep(0.5)

        # 能源別: 非電能
        energy_el = driver.find_element(By.XPATH, "//tr[th[contains(text(),'能源別')]]//select")
        Select(energy_el).select_by_visible_text("非電能")
        time.sleep(0.5)

        # 車牌別: 自用小客車
        plate_type_el = driver.find_element(By.XPATH, "//tr[th[contains(text(),'車牌別')]]//select")
        Select(plate_type_el).select_by_visible_text("營業小客車")
        
        # -------------------------------------------
        # 2. 破解驗證碼
        # -------------------------------------------
        print("5. 處理驗證碼...")
        
        # (1) 等待圖片元素出現
        captcha_img = wait.until(EC.visibility_of_element_located((By.ID, "pickimg")))
        
        # (2) 滾動到畫面中間，確保截圖完整
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", captcha_img)
        
        # (3) [新增] 檢查圖片是否真的載入完成 (避免截到全黑或破圖)
        # 使用 JavaScript 檢查 naturalWidth 是否大於 0
        is_loaded = driver.execute_script(
            "return arguments[0].complete && typeof arguments[0].naturalWidth != 'undefined' && arguments[0].naturalWidth > 0;",
            captcha_img
        )
        
        if not is_loaded:
            print("   -> 圖片尚未載入完全，等待 1 秒...")
            time.sleep(1)
        else:
            time.sleep(0.5) # 稍微緩衝一下視覺渲染

        # (4) 截圖並辨識
        img_bytes = captcha_img.screenshot_as_png
        
        try:
            ocr = ddddocr.DdddOcr(show_ad=False)
            captcha_code = ocr.classification(img_bytes)
        except TypeError:
            # 針對部分 ddddocr 版本不支援 show_ad 的相容寫法
            ocr = ddddocr.DdddOcr()
            captcha_code = ocr.classification(img_bytes)
            
        print(f"   -> 辨識結果: {captcha_code}")

        input_field = driver.find_element(By.NAME, "validateStr")
        input_field.clear()
        input_field.send_keys(captcha_code)
        
        # -------------------------------------------
        # 3. 送出查詢
        # -------------------------------------------
        print("6. 送出查詢...")
        submit_btns = driver.find_elements(By.XPATH, "//a[text()='確定']")
        clicked = False
        for btn in submit_btns:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn) # 改用 JS 點擊比較保險
                clicked = True
                break
        
        if not clicked:
            print("   -> 找不到按鈕，嘗試 JS 執行 query()...")
            driver.execute_script("query();")

        time.sleep(2) 

        if "驗證碼錯誤" in driver.page_source:
            print("❌ 驗證碼錯誤")
            driver.quit()
            return []
        
        # -------------------------------------------
        # 4. 抓取資料與翻頁
        # -------------------------------------------
        print("7. 開始抓取車牌資料...")
        page_count = 1
        
        while True:
            try:
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "number")))
            except:
                print("   -> 查無資料或載入逾時。")
                break

            numbers = driver.find_elements(By.XPATH, '//a[@class="number"]')
            
            current_page_plates = []
            for n in numbers:
                txt = n.text.strip()
                if txt:
                    plates.append(txt)
                    current_page_plates.append(txt)
            
            print(f"   -> 第 {page_count} 頁: 抓到 {len(current_page_plates)} 筆")

            next_btns = driver.find_elements(By.ID, "next")
            
            if not next_btns or not next_btns[0].is_displayed() or "disabled" in next_btns[0].get_attribute("class"):
                print("   -> 已達最後一頁，停止抓取。")
                break
            
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btns[0])
                driver.execute_script("arguments[0].click();", next_btns[0])
                page_count += 1
                
                time.sleep(0.5)
                try:
                    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
                except: pass
                time.sleep(1) 
            except Exception as e:
                print(f"   -> 翻頁發生錯誤: {e}")
                break

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
    finally:
        print("🛑 關閉瀏覽器")
        driver.quit()
    
    return plates

# --- 排程相關 (Supabase 版) ---

def set_schedule(line_id, s_type, value, user_name):
    # 取得昨天的日期
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 使用 upsert：如果 line_id 存在就更新，不存在就新增
    data = {
        "line_id": line_id,
        "type": s_type,
        "value": value,
        "last_run": yesterday,
        "display_name": user_name
    }
    # on_conflict 代表當 line_id 重複時執行的動作
    supabase.table("schedules").upsert(data, on_conflict="line_id").execute()
    print(f"✅ 已更新 {user_name} 的排程")

def get_schedule(line_id):
    # 查詢特定使用者的排程
    res = supabase.table("schedules").select("type, value").eq("line_id", line_id).execute()
    if res.data:
        # 回傳格式跟原本 SQLite 一致: (type, value)
        row = res.data[0]
        return (row['type'], row['value'])
    return None

def delete_schedule(line_id):
    # 刪除排程
    supabase.table("schedules").delete().eq("line_id", line_id).execute()
    print(f"🗑️ 已刪除 {line_id} 的排程")

def update_last_run(line_id):
    # 更新最後執行日期為今天
    today = datetime.date.today().strftime("%Y-%m-%d")
    supabase.table("schedules").update({"last_run": today}).eq("line_id", line_id).execute()
    print(f"📅 已更新 {line_id} 的最後執行日為 {today}")

def get_all_schedules():
    # 取得所有人的排程 (給背景檢查執行緒用的)
    res = supabase.table("schedules").select("line_id, type, value, last_run").execute()
    # 轉換成原本 SQLite fetchall() 的格式 [(id, type, val, run), ...]
    rows = []
    for row in res.data:
        rows.append((row['line_id'], row['type'], row['value'], row['last_run']))
    return rows

# ==========================================
# 🕷️ 爬蟲工具 (維持不變)
# ==========================================
SE_GRID_URL = os.getenv('SE_GRID_URL')

def new_chrome(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    
    # 共用優化參數
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    if CRAWLER_MODE == "remote":
        # --- 遠端模式：連線到 Docker Selenium Grid ---
        url = SE_GRID_URL # 確保 config 裡有這行
        print(f"DEBUG: [模式: Remote] 正在連線至 {url}")
        return webdriver.Remote(command_executor=url, options=options)
    else:
        # --- 本地模式：直接啟動伺服器上的 Chrome ---
        print("DEBUG: [模式: Local] 正在啟動本地瀏覽器")
        # 本地模式需要 Service
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

def safe_click(driver, locator, timeout=10):
    wait = WebDriverWait(driver, timeout)
    try:
        el = wait.until(EC.element_to_be_clickable(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        el.click()
    except Exception:
        el = driver.find_element(*locator)
        driver.execute_script("arguments[0].click();", el)

def safe_type(driver, element, value: str):
    if not value: return
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    driver.execute_script("arguments[0].removeAttribute('readonly');", element)
    element.clear()
    element.send_keys(value)

def prepare_page_mode(driver: webdriver.Chrome, mode: str):
    wait = WebDriverWait(driver, 15)
    if mode == "legal":
        try: safe_click(driver, (By.XPATH, '//a[contains(@class, "tab") and contains(text(), "法人")]'))
        except: safe_click(driver, (By.CLASS_NAME, "tab2"))
        wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@aria-label, "統一編號") or @id="id2"]')))
    else:
        try: safe_click(driver, (By.XPATH, '//a[contains(@class, "tab") and contains(text(), "個人")]'))
        except: safe_click(driver, (By.CLASS_NAME, "tab1"))
        wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@aria-label, "身分證") or @id="id1"]')))

def get_captcha_and_solve(driver: webdriver.Chrome, mode: str) -> str:
    wait = WebDriverWait(driver, 20)
    target_id = "pickimg2" if mode == "legal" else "pickimg"
    try:
        img_el = wait.until(EC.visibility_of_element_located((By.ID, target_id)))
    except:
        xpath = '//img[contains(@src, "validate") or contains(@src, "Captcha") or contains(@id, "pickimg")]'
        imgs = driver.find_elements(By.XPATH, xpath)
        img_el = next((img for img in imgs if img.is_displayed()), None)
        if not img_el: raise RuntimeError("無法找到驗證碼圖片")
    
    time.sleep(0.5)
    img_bytes = img_el.screenshot_as_png
    try:
        ocr = ddddocr.DdddOcr(show_ad=False)
        res = ocr.classification(img_bytes)
        return res
    except:
        ocr = ddddocr.DdddOcr()
        return ocr.classification(img_bytes)

def execute_query(driver: webdriver.Chrome, mode: str, id_val: str, sub_val: str, captcha: str):
    wait = WebDriverWait(driver, 15)
    if mode == "legal":
        el_id = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="id2" or contains(@aria-label,"統一編號")]')))
        safe_type(driver, el_id, id_val)
        if sub_val:
            el_plate = driver.find_element(By.XPATH, '//div[contains(@style,"block")]//input[contains(@aria-label,"車號") or contains(@name,"plate")]')
            safe_type(driver, el_plate, sub_val)
    else:
        el_id = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="id1" or contains(@aria-label,"身分證")]')))
        safe_type(driver, el_id, id_val)
        if sub_val:
            el_bd = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="birthday" or contains(@aria-label,"生日")]')))
            safe_type(driver, el_bd, sub_val)

    captcha_input = None
    candidates = driver.find_elements(By.NAME, "validateStr")
    for c in candidates:
        if c.is_displayed():
            captcha_input = c
            break
    if not captcha_input:
         captcha_input = wait.until(EC.visibility_of_element_located((By.NAME, "validateStr")))
    safe_type(driver, captcha_input, captcha)
    
    btn_id = "search2" if mode == "legal" else "search1"
    try:
        safe_click(driver, (By.ID, btn_id))
    except:
        driver.execute_script(f"document.getElementById('{btn_id}').click();")
def create_plate_flex(plates_chunk, batch_index, total_count):
    """
    將部分車牌製作成一個 Flex Message Carousel
    """
    bubbles = []
    
    # 設定每張卡片 (Bubble) 放 30 個號碼 (3直行 x 10橫列)
    # 這樣一張卡片不會太長，也不會超過 Carousel 數量限制
    items_per_bubble = 30
    bubble_chunks = [plates_chunk[i:i + items_per_bubble] for i in range(0, len(plates_chunk), items_per_bubble)]
    
    for i, b_chunk in enumerate(bubble_chunks):
        # 排版：每行 3 個
        rows = []
        row_buffer = []
        
        for plate in b_chunk:
            row_buffer.append(plate)
            if len(row_buffer) == 3:
                rows.append(row_buffer)
                row_buffer = []
        if row_buffer: # 處理剩下的
            rows.append(row_buffer)
            
        # 建立內容組件
        contents = []
        for row in rows:
            box = {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": p, "size": "md", "align": "center", "color": "#111111", "weight": "bold"} for p in row
                ],
                "margin": "md"
            }
            contents.append(box)

        # 建立 Bubble
        bubble = {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "選號查詢結果",
                        "weight": "bold",
                        "color": "#ffffff",
                        "size": "sm"
                    },
                    {
                        "type": "text",
                        "text": f"第 {batch_index}-{i+1} 頁 | 範圍：{b_chunk[0]}~{b_chunk[-1]}",
                        "color": "#ffffff",
                        "size": "xs",
                        "margin": "xs",
                        "wrap": True
                    }
                ],
                "backgroundColor": "#00b900",
                "paddingAll": "12px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": contents,
                "paddingAll": "10px"
            }
        }
        bubbles.append(bubble)

    return FlexSendMessage(
        alt_text="監理站選號結果",
        contents={
            "type": "carousel",
            "contents": bubbles
        }
    )
def parse_current_page(driver: webdriver.Chrome):
    results = []
    try:
        checkboxes = driver.find_elements(By.XPATH, "//input[contains(@onclick, 'changePay')]")
        for chk in checkboxes:
            onclick_val = chk.get_attribute("onclick")
            if not onclick_val: continue
            matches = re.findall(r"'([^']*)'", onclick_val)
            if len(matches) >= 12:
                item = {
                    "單號": matches[4],
                    "違規時間": matches[1],
                    "違規事實": matches[2],
                    "車號": matches[5],
                    "金額": matches[8],
                    "違規地點": matches[11],
                    "應到案日": matches[3]
                }
                results.append(item)
    except Exception as e:
        print(f"解析頁面錯誤: {e}")
    return results

def get_all_pages_data(driver: webdriver.Chrome):
    wait = WebDriverWait(driver, 10)
    all_data = []
    while True:
        current_data = parse_current_page(driver)
        if current_data:
            all_data.extend(current_data)
        
        next_btns = driver.find_elements(By.ID, "next")
        if not next_btns or not next_btns[0].is_displayed():
            break
        try:
            next_btn = next_btns[0]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            try: next_btn.click()
            except: driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(1)
            try: wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
            except: pass
            time.sleep(0.5)
        except:
            break
    return all_data

# ==========================================
# 🖼️ 照片 API 與 Flex Message
# ==========================================
def get_taipei_photos(tkt_no, plt_no, id_num):
    url = "https://smsweb.tcpd.gov.tw/NewSmsWeb/photo/get"
    payload = json.dumps({"Tkt_no": tkt_no, "Plt_no": plt_no, "Id_num": id_num, "Captcha": "", "Workdt": ""})
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    base64_list = []
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15, verify=False)
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("image1"): base64_list.append(data["image1"])
                if data.get("image2"): base64_list.append(data["image2"])
            except: pass
    except Exception as e:
        print(f"照片 API 錯誤: {e}")
    return base64_list
def get_new_taipei_photos(tkt_no):
    """打 API 取得新北市 (C開頭單號) 照片的 Base64"""
    url = "https://trspweb.ntpd.gov.tw/File/GetPhoto"
    
    # 新北市 API 只需要 ticket 參數
    payload = json.dumps({
      "ticket": tkt_no
    })
    
    headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Referer': 'https://trspweb.ntpd.gov.tw/' # 建議加上 Referer
    }

    base64_list = []

    try:
        # 保持 verify=False 以略過 SSL 憑證檢查
        response = requests.post(url, headers=headers, data=payload, timeout=15, verify=False)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                # 新北市的回傳結構是 {"photos": [{"fileContents": "..."}, ...]}
                if "photos" in data and isinstance(data["photos"], list):
                    for photo_item in data["photos"]:
                        b64_str = photo_item.get("fileContents")
                        if b64_str:
                            base64_list.append(b64_str)
                    
                print(f"成功取得 {len(base64_list)} 張新北市照片 Base64")
                
            except Exception as e:
                print(f"API 回傳解析失敗: {e}")
        else:
            print(f"API 請求失敗: {response.status_code}")

    except Exception as e:
        print(f"連線錯誤: {e}")
    
    return base64_list
def upload_to_imgbb(base64_str):
    if not base64_str: return None
    url = "https://api.imgbb.com/1/upload"
    if "," in base64_str: base64_str = base64_str.split(",")[1]
    payload = {"key": IMGBB_API_KEY, "image": base64_str, "expiration": 604800}
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            return response.json()['data']['url']
    except: pass
    return None

def create_fine_flex_message(record_data, id_number):
    tkt_no = record_data['單號']
    image_urls = []
    
    # --- 1. 取得照片邏輯 (維持不變) ---
    if tkt_no.startswith('A'):
        base64_list = get_taipei_photos(tkt_no, record_data['車號'], id_number)
        for b64 in base64_list:
            url = upload_to_imgbb(b64)
            if url: image_urls.append(url)
            time.sleep(0.5)
    elif tkt_no.startswith('C'):
        base64_list = get_new_taipei_photos(tkt_no)
        for b64 in base64_list:
            url = upload_to_imgbb(b64)
            if url: image_urls.append(url)
            time.sleep(0.5)

    if not image_urls: image_urls = [DEFAULT_HERO_IMAGE]

    # --- 2. 建立 Flex Message ---
    bubbles = []
    for idx, img_url in enumerate(image_urls):
        page_txt = f" ({idx+1}/{len(image_urls)})" if len(image_urls) > 1 else ""
        violation_fact = record_data['違規事實'].strip()
        bubble = {
            "type": "bubble", "size": "giga",
            "styles": {"header": {"backgroundColor": "#850000"}, "body": {"backgroundColor": "#2b2b2b"}, "footer": {"backgroundColor": "#2b2b2b"}},
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "交通違規警報", "weight": "bold", "color": "#ffffff", "size": "md", "align": "center"}]
            },
            "hero": {
                "type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover",
                "action": {"type": "uri", "uri": img_url}
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"{record_data['車號']}{page_txt}", "weight": "bold", "size": "xl", "color": "#ffffff", "align": "center"},
                    {"type": "text", "text": tkt_no, "size": "xs", "color": "#aaaaaa", "align": "center", "margin": "xs"},
                    {"type": "separator", "margin": "lg", "color": "#555555"},
                    
                    # --- 詳細資料區塊 ---
                    {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                        # 1. 金額
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "金額", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": f"NT$ {record_data['金額']}", "color": "#FF3333", "size": "xl", "weight": "bold", "flex": 4}]},
                        # 2. 時間
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data['違規時間'], "color": "#ffffff", "size": "sm", "flex": 4}]},
                        # 3. 應到案日
                        {"type": "box", "layout": "baseline", "contents": [
                            {"type": "text", "text": "應到案日", "color": "#aaaaaa", "size": "sm", "flex": 1}, 
                            {"type": "text", "text": record_data.get('應到案日', '無'), "color": "#ffcc00", "size": "sm", "flex": 4} 
                        ]},
                        # 4. 地點
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "地點", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data.get('違規地點', '無'), "color": "#ffffff", "size": "sm", "flex": 4, "wrap": True}]},
                        
                        # 5. 事由
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "事由", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data['違規事實'], "color": "#ffffff", "size": "sm", "flex": 4, "wrap": True}]}
                    ]}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",  # 按鈕之間的間距
                "contents": [
                    # 按鈕 1：原本的前往監理站
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "color": "#E60000",
                        "action": {
                            "type": "uri",
                            "label": "前往監理站繳費",
                            "uri": MV_DIS_URL
                        }
                    },
                    # 按鈕 2：新增的 AI 評估按鈕
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "color": "#00b900",
                        "action": {
                            "type": "postback",
                            "label": "🤖 AI 申訴評估",
                            # 這裡多帶一個 &fact 參數
                            "data": f"action=ai_analyze&tkt_no={tkt_no}&img_url={img_url}&fact={violation_fact}",
                            "displayText": f"請幫我分析這張罰單{tkt_no}能否申訴"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)
    
    content = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return FlexSendMessage(alt_text=f"違規通知：{record_data['車號']}", contents=content)

# ==========================================
# 🚀 爬蟲主流程
# ==========================================
def process_crawling_for_user(user_id, car_list, reply_token, is_auto_schedule=False):
    """
    執行爬蟲
    reply_token: 用來回覆訊息的 token (手動查詢時必填)
    is_auto_schedule: True 代表是排程觸發 (排程時沒有 reply_token，仍需使用 push)
    """
    print(f"啟動爬蟲，目標: {user_id}, 模式: {'自動排程' if is_auto_schedule else '手動查詢'}")
    if not is_auto_schedule:
        send_loading_animation(user_id, duration=60)
    try:
        driver = new_chrome()
        if CRAWLER_MODE == "remote":
            print(f"DEBUG: 成功連線至 Selenium Grid 伺服器 ({SE_GRID_URL})!")
        else:
            print("DEBUG: 成功啟動本地瀏覽器!")

    
        # 收集所有要發送的訊息物件
        messages_to_send = []
        results_text = [] # 用來存純文字結果

        try:
            # 爬蟲邏輯 (與原本相同，但不再中途 push 訊息)
            for car in car_list:
                try:
                    driver.get(MV_DIS_URL)
                    max_retries = 3
                    success = False

                    for attempt in range(max_retries):
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
                            except: pass

                            if "驗證碼錯誤" in driver.page_source:
                                driver.refresh()
                                continue

                            # 狀況 1: 無違規
                            if "查無" in driver.page_source and "資料" in driver.page_source:
                                results_text.append(f"✅ {car['name']}：無違規")
                                success = True
                                break

                            # 狀況 2: 有違規
                            records = get_all_pages_data(driver)
                            if records:
                                results_text.append(f"🚨 {car['name']}：發現 {len(records)} 筆罰單！")
                                # 建立罰單卡片並加入待發送清單
                                for record in records:
                                    try:
                                        flex_msg = create_fine_flex_message(record, car['id'])
                                        messages_to_send.append(flex_msg)
                                    except: pass
                                success = True
                                break
                            
                            driver.refresh()

                        except Exception as e:
                            print(f"嘗試錯誤: {e}")
                            driver.refresh()

                    if not success:
                        results_text.append(f"⚠️ {car['name']}：查詢失敗")

                except Exception as e:
                    print(f"單一車輛錯誤: {e}")

            # === 建立總結訊息 ===
            summary_text = "📅 查詢報告：\n" + "\n".join(results_text)

            # 將總結文字放在最前面
            messages_to_send.insert(0, TextSendMessage(text=summary_text))

            # 限制一次最多發送 5 則訊息 (Line API 限制)
            # 如果罰單太多，我們只傳前 4 張 + 總結
            if len(messages_to_send) > 5:
                messages_to_send = messages_to_send[:5]
                messages_to_send.append(TextSendMessage(text="⚠️ 罰單較多，僅顯示前幾筆，請至監理站查詢完整內容。"))

            # === 發送訊息 ===
            if is_auto_schedule:
                # 排程模式：還是得用 push，因為沒有 reply_token
                # 但排程通常一天才一次，應該還好
                for msg in messages_to_send:
                    line_bot_api.push_message(user_id, msg)
            else:
                # 手動模式：使用 reply_message (免費！)
                # 注意：這裡假設爬蟲能在 30-60 秒內跑完，否則 Token 會過期
                if reply_token:
                    line_bot_api.reply_message(reply_token, messages_to_send)
                else:
                    print("錯誤：手動模式但沒有 reply_token")

        except Exception as e:
            print(f"瀏覽器或發送錯誤: {e}")
            # 如果出錯，嘗試回傳錯誤訊息 (如果 Token 還沒過期)
            if not is_auto_schedule and reply_token:
                try:
                    line_bot_api.reply_message(reply_token, TextSendMessage(text="❌ 查詢發生錯誤或逾時，請稍後再試。"))
                except: pass
    except Exception as e:
        print(f"DEBUG: 爬蟲連線失敗，原因: {e}")
    finally:
        driver.quit()

# ==========================================
# ⏰ 排程檢查器 (Background Thread)
# ==========================================
def schedule_checker():
    """每分鐘檢查一次資料庫，看看誰該跑爬蟲"""
    print("🚀 排程檢查器已啟動...")
    
    while True:
        try:
            # 1. 設定台灣時間
            taiwan_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
            current_time_str = taiwan_time.strftime("%H:%M") 
            today_str = taiwan_time.strftime("%Y-%m-%d")
            
            # 取得今天是星期幾 (0=週一, 1=週二 ... 6=週日)
            current_weekday = taiwan_time.weekday()

            schedules = get_all_schedules() 
            
            for row in schedules:
                user_id, s_type, value, last_run = row
                should_run = False
                
                # --- A. 每天模式 ---
                if s_type == 'daily':
                    if current_time_str == value and last_run != today_str:
                        should_run = True
                
                # --- B. [新增] 每週模式 ---
                elif s_type == 'weekly':
                    # 條件：
                    # 1. 今天星期幾 == 設定的星期幾 (value='0' 代表週一)
                    # 2. 時間是 09:00 (這裡固定寫死，或你也可以存進資料庫)
                    # 3. 今天還沒跑過
                    if str(current_weekday) == value and current_time_str == "09:00" and last_run != today_str:
                        should_run = True

                # --- C. 間隔模式 (每 N 天) ---
                elif s_type == 'interval':
                    try:
                        if not last_run:
                            last_run_date = (taiwan_time - datetime.timedelta(days=int(value)+1)).date()
                        else:
                            last_run_date = datetime.datetime.strptime(last_run, "%Y-%m-%d").date()
                            
                        current_date = taiwan_time.date()
                        days_diff = (current_date - last_run_date).days
                        
                        if days_diff >= int(value) and current_time_str == "09:00" and last_run != today_str:
                            should_run = True
                    except Exception as e:
                        print(f"日期計算錯誤: {e}")

                # --- 觸發執行 ---
                if should_run:
                    print(f"👉 觸發排程！對象: {user_id}, 類型: {s_type}")
                    update_last_run(user_id)
                    cars = get_user_cars(user_id)
                    if cars:
                        # 記得這理參數要傳 4 個: user_id, cars, reply_token(None), is_auto(True)
                        threading.Thread(target=process_crawling_for_user, args=(user_id, cars, None, True)).start()
            
            time.sleep(60)
            
        except Exception as e:
            print(f"❌ 排程檢查發生錯誤: {e}")
            time.sleep(60)

# 啟動排程檢查執行緒
threading.Thread(target=schedule_checker, daemon=True).start()

DB_NAME = 'users_cars.db' # 你的資料庫檔名

def check_car_exists(line_id, mode, value_to_check):
    """
    檢查車輛是否重複綁定 (Supabase 雲端版)
    """
    # 1. 整理輸入值，避免因為大小寫或空格導致判斷錯誤
    clean_val = value_to_check.upper().strip()
    
    try:
        # 2. 建立查詢：先鎖定這位使用者的 line_id
        query = supabase.table("cars").select("id", count="exact").eq("line_id", line_id)
        
        if mode == "1":
            # 個人車：檢查 pid (身分證) 是否重複
            res = query.eq("pid", clean_val).execute()
        else:
            # 公司車：檢查 plate (車牌) 是否重複
            res = query.eq("plate", clean_val).execute()
        
        # 3. 判斷數量是否大於 0
        # res.count 會回傳符合條件的資料總數
        is_exist = res.count > 0
        
        if is_exist:
            print(f"🚩 偵測到重複綁定: {clean_val} (用戶: {line_id})")
            
        return is_exist

    except Exception as e:
        print(f"❌ 雲端資料庫檢查錯誤: {e}")
        # 如果資料庫連不上，保險起見回傳 False 讓使用者可以繼續嘗試，或者報錯
        return False
# ==========================================
# 🤖 LINE Webhook & 指令處理
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 全局變數 ---
user_sessions = {}

# --- 共用元件：取消按鈕 ---
# 在每一步驟都顯示這個按鈕
cancel_menu = QuickReply(
    items=[
        QuickReplyButton(action=MessageAction(label="❌ 取消綁定", text="取消"))
    ]
)

def run_plate_crawler(user_id, reply_token):
    """
    執行選號爬蟲並分批推播 Flex 結果 (改用 Reply)
    """
    send_loading_animation(user_id, duration=60)
    plates = crawl_plate_numbers()
    
    if not plates:
        # 失敗時用 Reply
        line_bot_api.reply_message(reply_token, TextSendMessage(text="⚠️ 查詢失敗或目前無可選號碼 (驗證碼錯誤或無資料)。"))
        return

    try:
        total = len(plates)
        msg_batch_size = 300
        message_batches = [plates[i:i + msg_batch_size] for i in range(0, len(plates), msg_batch_size)]
        
        # 準備要發送的訊息列表
        messages_to_send = []
        
        # 第一則：文字統計
        messages_to_send.append(TextSendMessage(text=f"🔍 查詢完成，共 {total} 筆資料..."))
        
        # 後續：Flex Carousel
        # 注意：Reply 一次最多 5 則訊息
        for index, batch in enumerate(message_batches):
            if len(messages_to_send) >= 5:
                break # 超過限制，停止加入
            flex_message = create_plate_flex(batch, index + 1, total)
            messages_to_send.append(flex_message)

        # 一次性發送
        line_bot_api.reply_message(reply_token, messages_to_send)
            
    except Exception as e:
        print(f"發送 Flex 失敗: {e}")
        try:
            line_bot_api.reply_message(reply_token, TextSendMessage(text="⚠️ 發生錯誤，無法顯示結果。"))
        except: pass
def fetch_parking_data():
    response = supabase.table("parking_lots").select("*").execute()
    return response.data
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    
    # 引用全局變數
    global user_sessions

    # ==========================================
    # 優先權 1: 「取消」指令 (隨時中斷)
    # ==========================================
    if msg == "取消":
        if user_id in user_sessions:
            del user_sessions[user_id]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 已取消綁定流程，回到主選單。"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="目前沒有進行中的流程喔。"))
        return

    # ==========================================
    # 優先權 2: 綁定流程狀態機 (State Machine)
    # 只要 User ID 在 Session 裡，代表他正在回答問題
    # ==========================================
    if user_id in user_sessions:
        session = user_sessions[user_id]
        step = session["step"]
        data = session["data"]

        # ----------------------------------
        # A. 個人車流程
        # ----------------------------------
        if step == "wait_p_name":
            data["name"] = msg
            session["step"] = "wait_p_id"
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"收到暱稱「{msg}」👌\n\n接著請輸入「身分證字號」(10碼)：", quick_reply=cancel_menu)
            )
            return

        elif step == "wait_p_id":
            # 格式檢查
            if len(msg) != 10:
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text="⚠️ 身分證長度應為10碼，請重新輸入：", quick_reply=cancel_menu)
                )
                return
            
            p_id = msg.upper()

            # ★★★ 檢查個人車重複 (對 pid) ★★★
            if check_car_exists(user_id, "1", p_id):
                del user_sessions[user_id] # 清除狀態
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text=f"🚫 綁定失敗！\n\n身分證「{p_id}」您已經綁定過了，不需要重複綁定喔。")
                )
                return

            # 檢查通過，存入暫存，進入下一步
            data["id"] = p_id
            session["step"] = "wait_p_birthday"
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text="最後一步，請輸入「生日」🎂\n(格式：民國年7碼，例如 0800101)", quick_reply=cancel_menu)
            )
            return

        elif step == "wait_p_birthday":
            if len(msg) != 7 or not msg.isdigit():
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text="⚠️ 生日格式錯誤，請輸入7位數字 (例如 0800101)：", quick_reply=cancel_menu)
                )
                return
            
            # 寫入資料庫
            try:
                # add_car 參數順序請依照您原本的設定
                # 假設: user_id, 暱稱, 類型, pid(身分證), 統編(空), 生日/車號
                add_car(user_id, data["name"], "1", data["id"], "", msg)
                
                del user_sessions[user_id]
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text=f"✅ 綁定成功！\n\n🚗 暱稱：{data['name']}\n🪪 身分證：{data['id']}\n🎂 生日：{msg}")
                )
            except Exception as e:
                del user_sessions[user_id]
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 綁定失敗，系統錯誤: {str(e)}"))
            return

        # ----------------------------------
        # B. 公司車流程
        # ----------------------------------
        elif step == "wait_c_name":
            data["name"] = msg
            session["step"] = "wait_c_tax"
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"收到暱稱「{msg}」👌\n\n接著請輸入「公司統編」(8碼)：", quick_reply=cancel_menu)
            )
            return

        elif step == "wait_c_tax":
            if len(msg) != 8 or not msg.isdigit():
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text="⚠️ 統編應為8位數字，請重新輸入：", quick_reply=cancel_menu)
                )
                return
            data["tax"] = msg
            session["step"] = "wait_c_plate"
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text="最後一步，請輸入「車牌號碼」🚙\n(例如 ABC-1234)：", quick_reply=cancel_menu)
            )
            return

        elif step == "wait_c_plate":
            plate = msg.upper()
            
            # ★★★ 檢查公司車重複 (對 plate) ★★★
            if check_car_exists(user_id, "2", plate):
                del user_sessions[user_id] # 清除狀態
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text=f"🚫 綁定失敗！\n\n車號「{plate}」您已經綁定過了，不需要重複綁定喔。")
                )
                return

            try:
                # add_car 參數: user_id, 暱稱, 類型, pid(統編), plate(車牌), param3(空)
                # 注意：這裡將統編存入 pid 欄位，車牌存入 plate 欄位，請確認 add_car 實作是否對應
                add_car(user_id, data["name"], "2", data["tax"], plate, "")
                
                del user_sessions[user_id]
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text=f"✅ 綁定成功！\n\n🏢 暱稱：{data['name']}\n🔢 統編：{data['tax']}\n🚙 車號：{plate}")
                )
            except Exception as e:
                del user_sessions[user_id]
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 綁定失敗：{str(e)}"))
            return

    # ==========================================
    # 優先權 3: 一般指令區 (只有不在輸入狀態時才執行)
    # ==========================================
    
    # --- 1. 觸發綁定流程 ---
    if msg == "綁定車輛":
        # 確保舊狀態已清除
        if user_id in user_sessions: del user_sessions[user_id]
        
        reply_msg = TextSendMessage(
            text="請問您要綁定哪種類型的車輛？",
            quick_reply=QuickReply(
                items=[
                    QuickReplyButton(action=MessageAction(label="🚗 個人車", text="綁定個人車")),
                    QuickReplyButton(action=MessageAction(label="🏢 公司車", text="綁定公司車")),
                    QuickReplyButton(action=MessageAction(label="❌ 取消", text="取消"))
                ]
            )
        )
        line_bot_api.reply_message(event.reply_token, reply_msg)

    # --- 2. 選擇類型，進入狀態機 ---
    elif msg == "綁定個人車":
        # 建立 Session
        user_sessions[user_id] = {"step": "wait_p_name", "data": {"type": "1"}}
        # 第一步：問暱稱 (附帶取消按鈕)
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="請輸入這台車的「暱稱」\n(例如：小白、我的車)：", quick_reply=cancel_menu)
        )

    elif msg == "綁定公司車":
        # 建立 Session
        user_sessions[user_id] = {"step": "wait_c_name", "data": {"type": "2"}}
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="請輸入這台車的「暱稱」\n(例如：公司貨車)：", quick_reply=cancel_menu)
        )

    # --- 3. 罰單查詢 (修改後) ---
    elif msg == "罰單查詢":
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先綁定車輛。"))
            return
        
        # 產生選擇卡片
        flex_msg = create_car_selection_flex(cars)
        
        line_bot_api.reply_message(
            event.reply_token, 
            [
                TextSendMessage(text="請選擇要查詢哪一台車輛？"),
                flex_msg
            ]
        )

    elif msg == "查詢車輛" or msg == "查詢設定":
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📭 目前沒有綁定任何車輛。"))
        else:
            # 顯示車輛卡片 (檢視模式)
            flex_msg = create_car_list_flex(cars, mode='view')
            
            # --- [修改] 顯示排程資訊邏輯 ---
            sched = get_schedule(user_id)
            sched_info = "無自動排程"
            
            if sched:
                s_type, s_val = sched
                if s_type == 'daily':
                    sched_info = f"每天 {s_val} 自動查詢"
                elif s_type == 'interval':
                    sched_info = f"每 {s_val} 天 自動查詢"
                elif s_type == 'weekly':
                    # 轉換數字為中文 (0=週一)
                    days_map = {'0': '一', '1': '二', '2': '三', '3': '四', '4': '五', '5': '六', '6': '日'}
                    day_str = days_map.get(str(s_val), str(s_val))
                    sched_info = f"每週{day_str} 09:00 自動查詢"
            # ---------------------------
                
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text=f"📋 目前排程設定：{sched_info}"),
                flex_msg
            ])
    
    # --- 4. 設定排程 ---
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
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="請選擇自動查詢的頻率：",
            quick_reply=quick_reply
        ))

    elif msg.startswith("每天 ") or (msg.startswith("每 ") and "天" in msg) or msg == "每週一 09:00":
        # 檢查是否有車輛
        if not get_user_cars(user_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請先綁定車輛。"))
            return

        try:
            user_name = get_line_user_name(user_id) 

            # A. 每天模式
            if msg.startswith("每天"):
                time_val = msg.split()[1]
                datetime.datetime.strptime(time_val, "%H:%M") # 檢查時間格式
                set_schedule(user_id, 'daily', time_val, user_name)
                reply = f"⏰ 已設定：每天 {time_val} 自動查詢。"
            
            # B. [新增] 每週模式
            elif msg == "每週一 09:00":
                # value 存 '0' 代表星期一 (Python 的 weekday: 0=週一, 6=週日)
                set_schedule(user_id, 'weekly', '0', user_name)
                reply = "🗓️ 已設定：每週一 早上 09:00 自動查詢。"

            # C. 間隔模式 (每 N 天)
            else:
                days = re.findall(r'\d+', msg)[0]
                set_schedule(user_id, 'interval', days, user_name)
                reply = f"🗓️ 已設定：每 {days} 天自動查詢一次 (固定早上 09:00 執行)。"
            
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        except Exception as e:
            print(f"設定排程錯誤: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 格式錯誤或系統異常，請重試。"))

    elif msg == "取消排程":
        delete_schedule(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔕 已取消所有自動排程。"))

    # --- 5. 清除與查詢 ---
    elif msg == "清除車輛":
        cars = get_user_cars(user_id)
        if not cars:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📭 目前沒有綁定車輛。"))
        else:
            flex_msg = create_car_list_flex(cars, mode='delete')
            line_bot_api.reply_message(event.reply_token, [
                TextSendMessage(text="請選擇要刪除的車輛："),
                flex_msg
            ])

    elif msg == "查詢設定":
        cars = get_user_cars(user_id)
        sched = get_schedule(user_id)
        
        car_info = "\n".join([f"- {c['name']}" for c in cars]) if cars else "無"
        sched_info = "無"
        if sched:
            s_type, s_val = sched
            sched_info = f"每天 {s_val}" if s_type == 'daily' else f"每 {s_val} 天"
            
        reply = f"📋 設定狀態：\n\n🚗 綁定車輛：\n{car_info}\n\n⏰ 自動排程：\n{sched_info}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    
    # --- [新增] 選號查詢 ---
    elif msg == "選號":
        # 這裡也是，不能先回「查詢中」，因為 Reply 只能用一次
        # 所以使用者按下去後，會沒有反應約 10-20 秒，然後直接跳結果
        send_loading_animation(user_id, duration=60)
        threading.Thread(target=run_plate_crawler, args=(user_id, event.reply_token)).start()
    
    elif msg == "計程車免費車位查詢":
        reply_msg = TextSendMessage(
            text="請點下方按鈕傳送您的位置，我幫您查詢附近的計程車免費車位。",
            quick_reply=QuickReply(
                items=[
                    QuickReplyButton(
                        action=LocationAction(label="📍 傳送位置")
                    ),
                    QuickReplyButton(
                        action=MessageAction(label="❌ 取消", text="取消")
                    )
                ]
            )
        )
        line_bot_api.reply_message(event.reply_token, reply_msg)
        return

    elif msg == "remote":
        if user_id != os.getenv('Admin_uuid'):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限切換爬蟲模式。"))
            return
        CRAWLER_MODE = "remote"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚀 爬蟲模式已切換為：【遠端 Grid 模式】"))
        return

    elif msg == "local":
        if user_id != os.getenv('Admin_uuid'):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 您沒有權限切換爬蟲模式。"))
            return
        CRAWLER_MODE = "local"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="💻 爬蟲模式已切換為：【本地 Local 模式】"))
        return

    elif msg == "備份資料庫":
        if user_id != os.getenv('Admin_uuid'):
            return

        try:
            # 改連到 file.io
            with open('users_cars.db', 'rb') as f:
                files = {'file': f}
                # file.io 預設檔案下載一次後就會自動刪除，很安全
                response = requests.post('https://file.io', files=files)

            if response.status_code == 200:
                data = response.json()
                download_link = data.get('link')
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text=f"📦 SQLite 備份成功！\n注意：此連結下載一次後即失效\n\n{download_link}")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text=f"❌ 上傳失敗，狀態碼: {response.status_code}")
                )

        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 備份錯誤: {e}"))
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data # 取得例如 "action=delete_car&car_id=5..."
    
    # 解析參數
    params = parse_qs(data) # 會變成 {'action': ['delete_car'], 'car_id': ['5']}
    action = params.get('action', [''])[0]
    
    if action == 'delete_car':
        car_id = params.get('car_id', [''])[0]
        car_name = params.get('car_name', ['該車輛'])[0]
        
        if delete_specific_car(user_id, car_id):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🗑️ 已刪除車輛：{car_name}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 刪除失敗，找不到該車輛資料。"))
    # === [新增] 單一車輛查詢邏輯 ===
    elif action == 'check_one_car':
        car_id = params.get('car_id', [''])[0]
        
        # 從資料庫撈出那台車的詳細資料
        target_car = get_car_by_id(car_id)
        
        if target_car:
            # 啟動執行緒跑爬蟲
            # 注意：process_crawling_for_user 接受的是 list，所以要包成 [target_car]
            threading.Thread(
                target=process_crawling_for_user, 
                args=(user_id, [target_car], event.reply_token, False)
            ).start()
        else:
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text="❌ 找不到該車輛資料，可能已被刪除。")
            )
    elif action == 'ai_analyze':
        # 1. 先把資料拿出來
        tkt_no = params.get('tkt_no', [''])[0]
        img_url = params.get('img_url', [''])[0]
        fact = params.get('fact', [''])[0]
        user_id = event.source.user_id
        send_loading_animation(user_id, duration=60)
        # 2. 建立一個專門跑 AI 的副程式
        def run_ai_and_push(u_id, t_no, f_txt, i_url):
            advice = get_ai_appeal_advice(t_no, f_txt, i_url)
            line_bot_api.push_message(
                u_id,
                TextSendMessage(text=f"【🤖 罰單 AI 評估報告】\n\n{advice}")
            )

        # 3. 開啟新執行緒去跑 AI，主程式立刻往下走結束 callback
        threading.Thread(
            target=run_ai_and_push, 
            args=(user_id, tkt_no, fact, img_url)
        ).start()

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    # 防呆：如果是 LINE 控制台的測試訊息 (Verify)，直接跳過
    if event.reply_token in ["00000000000000000000000000000000", "ffffffffffffffffffffffffffffffff"]:
        return

    user_lat = event.message.latitude
    user_lng = event.message.longitude
    user_pos = (user_lat, user_lng)

    # 1. 取得資料（建議使用之前教你的 PARKING_CACHE 快取以防超時，這裡先維持你的邏輯）
    try:
        response = supabase.table("parking_lots").select("*").execute()
        current_lots = response.data 
    except Exception as e:
        print(f"資料庫讀取失敗: {e}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="抱歉，資料庫連線超時，請稍後再試。"))
        return
    
    # 2. 計算距離
    for lot in current_lots:
        lot_pos = (lot['lat'], lot['lng'])
        lot['distance'] = round(geodesic(user_pos, lot_pos).km, 2)

    # 3. 取最近的 5 筆
    nearby_lots = sorted(current_lots, key=lambda x: x['distance'])[:5]

    # 4. 建立 Flex Message 氣泡清單
    bubbles = []
    for lot in nearby_lots:
        # 基本資訊區塊
        contents = [
            {"type": "text", "text": lot['name'], "weight": "bold", "size": "sm", "wrap": True},
            {"type": "text", "text": f"距離: {lot['distance']} km", "size": "xs", "color": "#ff5551"},
            {"type": "text", "text": f"📍 {lot['address']}", "size": "xxs", "color": "#aaaaaa", "wrap": True},
            {"type": "separator", "margin": "md"}
        ]

        # --- 【補回：優惠時數顯示邏輯】 ---
        has_free_30m = lot.get('free_30m', False)
        has_free_1h = lot.get('free_1h', False)
        has_free_2h = lot.get('free_2h', False)
        has_free_4h = lot.get('free_4h', False)
        has_noon_2h = lot.get('noon_2h', False)

        # 邏輯判斷顯示內容
        # 1. 如果只有 30 分鐘
        if has_free_30m and not any([has_free_1h, has_free_2h, has_free_4h, has_noon_2h]):
            contents.append({"type": "text", "text": "✅ 未滿30分鐘免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        # 2. 顯示各種小時數 (如果有就顯示)
        if has_free_1h:
            contents.append({"type": "text", "text": "✅ 1小時免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_free_2h:
            contents.append({"type": "text", "text": "✅ 2小時免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_free_4h:
            contents.append({"type": "text", "text": "✅ 4小時免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_noon_2h:
            contents.append({"type": "text", "text": "✅ 中午免費2小時", "size": "xs", "margin": "md", "color": "#00b900"})

        # 3. 如果通通都沒有
        if not any([has_free_30m, has_free_1h, has_free_2h, has_free_4h, has_noon_2h]):
            contents.append({"type": "text", "text": "❌ 無免費停車優惠", "size": "xs", "margin": "md", "color": "#ff0000"})
        # -------------------------------

        bubble = {
            "type": "bubble",
            "size": "micro",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": contents
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "導航",
                            "uri": f"https://www.google.com/maps/search/?api=1&query={lot['lat']},{lot['lng']}"
                        },
                        "style": "primary",
                        "color": "#00b900"
                    }
                ]
            }
        }
        bubbles.append(bubble)

    # 5. 發送訊息
    flex_message = FlexSendMessage(
        alt_text="最近的計程車免費停車場",
        contents={"type": "carousel", "contents": bubbles}
    )
    line_bot_api.reply_message(event.reply_token, flex_message)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)