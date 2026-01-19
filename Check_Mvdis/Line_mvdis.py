import os,schedule
import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import tempfile
import re
import json
import base64
import csv
from linebot.models import FlexSendMessage
# ==========================================
# 1. 加入這段修復 PIL.Image.ANTIALIAS 的程式碼
# ==========================================
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
# ==========================================
# 2. 接著再 import ddddocr
# ==========================================
import ddddocr 

from typing import Dict, Any, List, Optional
from selenium import webdriver
from typing import Dict, Any, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from linebot import LineBotApi
from linebot.models import TextSendMessage

# ==========================================
# 0. 使用者設定區 (請修改這裡)
# ==========================================
LINE_ACCESS_TOKEN = "nX1N//BjGiFlpVcWboFDHEv36yht1xsXHe95cjSLMkEk0jLGdy9GMEL12bm50Mi6CW8DHR02VJ7QDTPiLQ7pzYLsGH85Z1eV2zqUMtjzFjK3tVi+GZ2uBE95+bF+eXbOkYszMMDolrHjt6ptgXkZqwdB04t89/1O/w1cDnyilFU="  # 請填入 LINE Developers 的 Token
TARGET_USER_ID='C48871f7af817c55346d8b71abf400733' #罰單通知單
# TARGET_USER_ID = "Uc033d76e142adb971941e27cd685856f" #個人      # 要發送的目標 (User ID 或 Group ID)
DEFAULT_HERO_IMAGE='https://i.ibb.co/DmpPQ2q/69ec183b-3e6e-4b50-bbd9-55d2ba5ac572.jpg'  # 預設卡片圖片 (沒有罰單照片時使用)
IMGBB_API_KEY = 'db7c5f15e2e4e1d49ba2c216afd94bd5'


# 監控車輛清單
# mode: "personal" (個人) 或 "legal" (法人)
# id: 身分證字號 或 統一編號
# sub_id: 生日(例如 0800101) 或 車號(法人可選，沒有填空字串)
CARS_TO_CHECK = [
    # {
    #     "name": "TEC-3168",
    #     "mode": "legal",
    #     "id": "15500025",      # 統編
    #     "sub_id": "TEC-3168"   # 車號 (法人選填)
    # },
    # {
    #     "name": "ENS-8888",
    #     "mode": "personal",
    #     "id": "F131515023",    # 身分證
    #     "sub_id": "0920129"    # 生日 (民國年7碼)
    # },
    {
        "name": "TEC-0059",
        "mode": "legal",
        "id": "15500025",    # 統編
        "sub_id": "TEC-0059"            # 車號 (法人選填)
    }
]

MV_DIS_URL = "https://www.mvdis.gov.tw/m3-emv-vil/vil/penaltyQueryPay"

# ==========================================
# 1. LINE 通知函式
# ==========================================
def send_line_notify(message: str):
    try:
        line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
        line_bot_api.push_message(TARGET_USER_ID, TextSendMessage(text=message))
        print(f"LINE 訊息已發送至 {TARGET_USER_ID}")
    except Exception as e:
        print(f"LINE 發送失敗: {e}")

# ==========================================
# 2. 瀏覽器與工具函式
# ==========================================
def new_chrome(headless: bool = True) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
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

# ==========================================
# 3. 核心邏輯 (含 OCR)
# ==========================================
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
    """ 截圖並使用 OCR 自動辨識 (修正版) """
    wait = WebDriverWait(driver, 20)
    target_id = "pickimg2" if mode == "legal" else "pickimg"
    
    try:
        img_el = wait.until(EC.visibility_of_element_located((By.ID, target_id)))
    except:
        xpath = '//img[contains(@src, "validate") or contains(@src, "Captcha") or contains(@id, "pickimg")]'
        imgs = driver.find_elements(By.XPATH, xpath)
        img_el = next((img for img in imgs if img.is_displayed()), None)
        if not img_el: raise RuntimeError("無法找到驗證碼圖片")

    # 確保圖片載入
    time.sleep(1)
    
    # 截取驗證碼圖片
    img_bytes = img_el.screenshot_as_png
    
    # ==========================================
    # 修改這裡：拿掉 show_ad=False
    # ==========================================
    ocr = ddddocr.DdddOcr() 
    
    res = ocr.classification(img_bytes)
    print(f"OCR 辨識結果: {res}")
    return res

def execute_query(driver: webdriver.Chrome, mode: str, id_val: str, sub_val: str, captcha: str):
    wait = WebDriverWait(driver, 15)
    
    # 填寫資料
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

    # 填寫驗證碼
    captcha_input = None
    candidates = driver.find_elements(By.NAME, "validateStr")
    for c in candidates:
        if c.is_displayed():
            captcha_input = c
            break
    if not captcha_input:
         captcha_input = wait.until(EC.visibility_of_element_located((By.NAME, "validateStr")))
    safe_type(driver, captcha_input, captcha)
    
    # 點擊查詢
    btn_id = "search2" if mode == "legal" else "search1"
    try:
        safe_click(driver, (By.ID, btn_id))
    except:
        driver.execute_script(f"document.getElementById('{btn_id}').click();")

def parse_all_pages(driver: webdriver.Chrome) -> List[str]:
    """ 翻頁抓取所有資料 """
    wait = WebDriverWait(driver, 5)
    all_data = []
    
    while True:
        # 解析當前頁面
        try:
            checkboxes = driver.find_elements(By.XPATH, "//input[contains(@onclick, 'changePay')]")
            for chk in checkboxes:
                onclick_val = chk.get_attribute("onclick")
                matches = re.findall(r"'([^']*)'", onclick_val)
                if len(matches) >= 12:
                    # 格式: [日期] 車號 - 金額 (事由)
                    msg = f"📅 {matches[1]}\n🚗 {matches[5]}\n💰 {matches[8]}元\n📝 {matches[2]}\n📍 {matches[11]}"
                    all_data.append(msg)
        except: pass

        # 找下一頁
        next_btns = driver.find_elements(By.ID, "next")
        if not next_btns or not next_btns[0].is_displayed():
            break
        
        try:
            driver.execute_script("arguments[0].click();", next_btns[0])
            time.sleep(1)
            wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
        except:
            break
            
    return all_data

# ==========================================
# 1. (新) 上傳 Base64 到 ImageBB 換網址
# ==========================================
def upload_to_imgbb(base64_str):
    """將 Base64 上傳到 ImageBB 並取得 HTTPS 網址"""
    if not base64_str:
        return None
        
    url = "https://api.imgbb.com/1/upload"
    
    # 移除可能的 header
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]

    payload = {
        "key": IMGBB_API_KEY,
        "image": base64_str,
        "expiration": 600  # (選填) 圖片 600秒後自動刪除，保護隱私
    }

    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            return response.json()['data']['url']
        else:
            print(f"ImageBB 上傳失敗: {response.text}")
    except Exception as e:
        print(f"圖片上傳發生錯誤: {e}")
    return None

# ==========================================
# 2. (修改) 查詢台北市罰單照片 (處理 image1, image2)
# ==========================================
def get_taipei_photos(tkt_no, plt_no, id_num):
    """打 API 取得 image1 和 image2 的 Base64"""
    url = "https://smsweb.tcpd.gov.tw/NewSmsWeb/photo/get"
    
    payload = json.dumps({
      "Tkt_no": tkt_no,
      "Plt_no": plt_no,
      "Id_num": id_num,
      "Captcha": "",
      "Workdt": ""
    })
    
    headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    base64_list = []

    try:
        # 重點修改：加入 verify=False 以略過 SSL 憑證檢查
        response = requests.post(url, headers=headers, data=payload, timeout=15, verify=False)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                # 檢查 image1
                if data.get("image1"):
                    base64_list.append(data["image1"])
                
                # 檢查 image2
                if data.get("image2"):
                    base64_list.append(data["image2"])
                    
                print(f"成功取得 {len(base64_list)} 張照片 Base64")
                
            except Exception as e:
                print(f"API 回傳解析失敗: {e}")
        else:
            print(f"API 請求失敗: {response.status_code}")

    except Exception as e:
        print(f"連線錯誤: {e}")
    
    return base64_list

# ==========================================
# 3. 製作 Flex Message (維持原樣，逻辑微調)
# ==========================================
def create_fine_flex_message(record_data, id_number):
    """
    製作罰單卡片 (支援 ImageBB 圖片輪播)
    """
    tkt_no = record_data['單號']
    image_urls = []

    # 1. 嘗試抓照片 (如果是 A 開頭)
    if tkt_no.startswith('A'):
        print(f"正在查詢單號 {tkt_no} 的照片...")
        base64_list = get_taipei_photos(tkt_no, record_data['車號'], id_number)
        
        # 2. 上傳到 ImageBB
        for i, b64 in enumerate(base64_list):
            print(f"正在上傳第 {i+1} 張圖片到 ImageBB...")
            img_url = upload_to_imgbb(b64)
            if img_url:
                image_urls.append(img_url)
                time.sleep(0.5) # 避免太快被擋
    
    # 3. 沒照片就用預設圖
    if not image_urls:
        image_urls = [DEFAULT_HERO_IMAGE]

    # 4. 製作卡片 Bubble
    bubbles = []
    
    for idx, img_url in enumerate(image_urls):
        # 顯示頁碼 (例如: 1/2)
        page_text = f" ({idx+1}/{len(image_urls)})" if len(image_urls) > 1 else ""
        
        bubble = {
            "type": "bubble",
            "size": "giga",
            "styles": {
                "header": {"backgroundColor": "#850000"},
                "body": {"backgroundColor": "#2b2b2b"},
                "footer": {"backgroundColor": "#2b2b2b"}
            },
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": "交通違規警報", "weight": "bold", "color": "#ffffff", "size": "md", "flex": 1, "align": "center"}
                        ]
                    }
                ]
            },
            "hero": {
                "type": "image",
                "url": img_url,
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover",
                "action": {"type": "uri", "uri": img_url}
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{record_data['車號']}{page_text}",
                        "weight": "bold", "size": "xl", "color": "#ffffff", "align": "center"
                    },
                    {"type": "text", "text": tkt_no, "size": "xs", "color": "#aaaaaa", "align": "center", "margin": "xs"},
                    {"type": "separator", "margin": "lg", "color": "#555555"},
                    {
                        "type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm",
                        "contents": [
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "金額", "color": "#aaaaaa", "size": "sm", "flex": 1},
                                {"type": "text", "text": f"NT$ {record_data['金額']}", "wrap": True, "color": "#FF3333", "size": "xl", "weight": "bold", "flex": 4}
                            ]},
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1},
                                {"type": "text", "text": record_data['違規時間'], "wrap": True, "color": "#ffffff", "size": "sm", "flex": 4}
                            ]},
                            {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
                                {"type": "text", "text": "事由", "color": "#aaaaaa", "size": "sm", "flex": 1},
                                {"type": "text", "text": record_data['違規事實'], "wrap": True, "color": "#ffffff", "size": "sm", "flex": 4}
                            ]}
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "height": "sm", "action": {"type": "uri", "label": "前往監理站", "uri": MV_DIS_URL}, "color": "#E60000"}
                ]
            }
        }
        bubbles.append(bubble)

    # 包裝成 Carousel (輪播)
    if len(bubbles) == 1:
        content_json = bubbles[0]
    else:
        content_json = {
            "type": "carousel",
            "contents": bubbles
        }

    return FlexSendMessage(alt_text=f"{record_data['車號']}：{record_data['違規事實']} ${record_data['金額']} 時間: {record_data['違規時間']}", contents=content_json)
def parse_current_page(driver: webdriver.Chrome) -> List[Dict[str, str]]:
    """
    [修正版] 抓取當前頁面資料，回傳「字典列表」而非字串
    """
    results = []
    try:
        checkboxes = driver.find_elements(By.XPATH, "//input[contains(@onclick, 'changePay')]")
        for chk in checkboxes:
            onclick_val = chk.get_attribute("onclick")
            if not onclick_val: continue
            
            # Regex 抓取參數
            matches = re.findall(r"'([^']*)'", onclick_val)
            
            if len(matches) >= 12:
                # 這裡必須是 Dictionary (字典)，Flex Message 才能讀取
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
        print(f"解析頁面發生錯誤: {e}")
    return results

def get_all_pages_data(driver: webdriver.Chrome) -> List[Dict[str, str]]:
    """
    [修正版] 自動翻頁抓取所有資料 (回傳字典列表)
    """
    wait = WebDriverWait(driver, 10)
    all_data = []
    page_count = 1

    while True:
        # 1. 抓取當前頁面
        current_data = parse_current_page(driver)
        if current_data:
            all_data.extend(current_data)
            # print(f"  -> 第 {page_count} 頁抓到 {len(current_data)} 筆資料")
        
        # 2. 找下一頁按鈕 (id="next")
        next_btns = driver.find_elements(By.ID, "next")
        
        # 如果沒按鈕 或 按鈕隱藏 -> 結束
        if not next_btns or not next_btns[0].is_displayed():
            break
            
        try:
            next_btn = next_btns[0]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            
            # 點擊下一頁
            try:
                next_btn.click()
            except:
                driver.execute_script("arguments[0].click();", next_btn)
            
            page_count += 1
            
            # 等待遮罩消失
            time.sleep(1) 
            try:
                wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
            except:
                pass
            time.sleep(0.5)

        except Exception as e:
            print(f"翻頁結束或錯誤: {e}")
            break
            
    return all_data
# ==========================================
# 4. 主流程 (自動重試與發送)
# ==========================================
def check_car_job(car_config):
    print(f"\n[{car_config['name']}] 啟動查詢程序...")
    driver = new_chrome(headless=True) # 除錯時可改 False
    
    try:
        driver.get(MV_DIS_URL)
        
        # 設定最大重試次數 (例如 3 次)
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                print(f"--- 第 {attempt + 1} 次嘗試 ---")
                
                # 1. 準備頁面與驗證碼
                prepare_page_mode(driver, car_config['mode'])
                captcha = get_captcha_and_solve(driver, car_config['mode'])
                
                # 2. 填寫並送出
                execute_query(driver, car_config['mode'], car_config['id'], car_config['sub_id'], captcha)
                
                # 3. 等待結果載入 (稍作緩衝)
                time.sleep(2)
                
                # --- [錯誤檢查 A] 檢查 Alert 視窗 ---
                try:
                    alert = driver.switch_to.alert
                    alert_text = alert.text
                    alert.accept()
                    if "錯誤" in alert_text or "驗證碼" in alert_text:
                        print(f"查詢失敗 (Alert): {alert_text} -> 準備重試")
                        driver.refresh()
                        continue
                except:
                    pass

                # 重新抓取頁面原始碼
                page_src = driver.page_source

                # --- [錯誤檢查 B] 檢查頁面紅字 ---
                if "驗證碼錯誤" in page_src:
                    print("查詢失敗 (Page): 驗證碼識別錯誤 -> 準備重試")
                    driver.refresh()
                    continue

                # --- [成功狀況 A] 查無違規資料 ---
                if "查無" in page_src and "資料" in page_src:
                    print(f"[{car_config['name']}] 結果：無違規資料 (恭喜！)")
                    return # 任務完成，直接結束函式

                # --- [成功狀況 B] 有資料，嘗試解析 ---
                # 嘗試抓取資料 (這會包含自動翻頁邏輯)
                records = get_all_pages_data(driver)
                
                if records:
                    # 成功抓到資料！
                    print(f"[{car_config['name']}] 發現 {len(records)} 筆罰單，準備發送 LINE...")
                    
                    line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
                    for record in records:
                        try:
                            # 傳入 ID 以便查詢照片
                            flex_msg = create_fine_flex_message(record, car_config['id'])
                            line_bot_api.push_message(TARGET_USER_ID, flex_msg)
                            time.sleep(0.5)
                        except Exception as e:
                            print(f"發送卡片失敗: {e}")
                            
                    return # 任務完成，直接結束函式
                
                # --- [狀態不明] ---
                # 程式跑到這裡代表：
                # 1. 沒有驗證碼錯誤
                # 2. 網頁沒說「查無資料」
                # 3. 但是 get_all_pages_data 卻回傳空陣列 [] (沒抓到東西)
                # 這就是你遇到的狀況，我們強制它重試
                print(f"[{car_config['name']}] 狀態不明：網頁載入可能不完全或解析失敗。")
                print(">> 觸發重試機制...")
                driver.refresh()
                # 這裡不寫 break，迴圈會自動進入下一次 attempt
                
            except Exception as e:
                print(f"嘗試過程中發生異常: {e}")
                driver.refresh()
                time.sleep(1)
        
        # 如果跑完迴圈都沒有 return，代表 3 次都失敗了
        print(f"[{car_config['name']}] 已達最大重試次數 ({max_retries}次)，放棄本次查詢。")

    except Exception as e:
        print(f"系統嚴重錯誤: {e}")
    finally:
        driver.quit()

# 定義要執行的主任務
def job():
    print(f"啟動排程任務: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    # 這裡放你的車輛清單
    for car in CARS_TO_CHECK:
        check_car_job(car)
        time.sleep(5) # 車與車之間休息一下

# if __name__ == "__main__":
#     print("機器人已啟動，等待每天 15:50 執行...")
    
#     # 設定每天 08:00 執行
#     schedule.every().day.at("15:50").do(job)
    
#     # 或是你要測試用，可以先設每分鐘跑一次看看 (測試完記得註解掉)
#     # schedule.every(1).minutes.do(job)

#     while True:
#         schedule.run_pending()
#         time.sleep(60) # 每分鐘檢查一次時間



if __name__ == "__main__":
    print("=== 開始執行自動查詢 ===")
    for car in CARS_TO_CHECK:
        check_car_job(car)
        time.sleep(3) # 避免請求過快
    print("=== 執行結束 ===")