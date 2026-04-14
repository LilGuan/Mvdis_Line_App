import time
import json
import requests
import ddddocr
import openai
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from config import (
    LINE_CHANNEL_ACCESS_TOKEN, IMGBB_API_KEY, 
    MV_DIS_URL, DEFAULT_HERO_IMAGE, OPENAI_API_KEY, SE_GRID_URL
)

CRAWLER_MODE = "local"
client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def new_chrome(headless=True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    if CRAWLER_MODE == "remote" and SE_GRID_URL:
        print(f"DEBUG: [模式: Remote] 正在連線至 {SE_GRID_URL}")
        return webdriver.Remote(command_executor=SE_GRID_URL, options=options)

    print("DEBUG: [模式: Local] 正在啟動本地瀏覽器")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(options=options, service=service)

def set_crawler_mode(mode: str):
    global CRAWLER_MODE
    if mode in {"local", "remote"}:
        CRAWLER_MODE = mode

def get_crawler_mode() -> str:
    return CRAWLER_MODE

# --- 2. LINE 專用工具 ---
def send_loading_animation(user_id, duration=20):
    """發送 LINE 聊天室 Loading 動畫 (最長 60 秒)"""
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    try:
        requests.post(url, headers=headers, json={"chatId": user_id, "loadingSeconds": duration})
    except Exception as e:
        print(f"Loading 動畫發送失敗: {e}")

# --- 3. 圖片處理與上傳 (ImgBB) ---
def upload_to_imgbb(base64_str):
    """將 Base64 圖片上傳至 ImgBB 並取得公開 URL"""
    if not base64_str:
        return None
    
    url = "https://api.imgbb.com/1/upload"
    # 去除 base64 標頭 (data:image/png;base64,)
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]
    
    payload = {
        "key": IMGBB_API_KEY,
        "image": base64_str,
        "expiration": 604800  # 圖片保留 7 天
    }
    try:
        response = requests.post(url, data=payload, timeout=15)
        if response.status_code == 200:
            return response.json()['data']['url']
    except Exception as e:
        print(f"ImgBB 上傳失敗: {e}")
    return None

# --- 4. 罰單照片抓取邏輯 (台北市 & 新北市) ---

def get_taipei_photos(tkt_no, plt_no, id_num):
    """取得台北市 (A開頭) 罰單照片"""
    url = "https://smsweb.tcpd.gov.tw/NewSmsWeb/photo/get"
    payload = json.dumps({
        "Tkt_no": tkt_no, 
        "Plt_no": plt_no, 
        "Id_num": id_num, 
        "Captcha": "", 
        "Workdt": ""
    })
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    base64_list = []
    try:
        # 台北市 API 通常需要 verify=False 繞過憑證檢查
        response = requests.post(url, headers=headers, data=payload, timeout=15, verify=False)
        if response.status_code == 200:
            data = response.json()
            if data.get("image1"): base64_list.append(data["image1"])
            if data.get("image2"): base64_list.append(data["image2"])
    except Exception as e:
        print(f"台北市照片 API 錯誤: {e}")
    return base64_list

def get_new_taipei_photos(tkt_no):
    """取得新北市 (C開頭) 罰單照片"""
    url = "https://trspweb.ntpd.gov.tw/File/GetPhoto"
    payload = json.dumps({"ticket": tkt_no})
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://trspweb.ntpd.gov.tw/'
    }
    base64_list = []
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15, verify=False)
        if response.status_code == 200:
            data = response.json()
            # 新北市結構為 {"photos": [{"fileContents": "..."}, ...]}
            if "photos" in data and isinstance(data["photos"], list):
                for item in data["photos"]:
                    if item.get("fileContents"):
                        base64_list.append(item["fileContents"])
    except Exception as e:
        print(f"新北市照片 API 錯誤: {e}")
    return base64_list

def get_captcha_and_solve(driver: webdriver.Chrome, mode: str) -> str:
    wait = WebDriverWait(driver, 20)
    target_id = "pickimg2" if mode == "legal" else "pickimg"
    try:
        img_el = wait.until(EC.visibility_of_element_located((By.ID, target_id)))
    except Exception:
        xpath = '//img[contains(@src, "validate") or contains(@src, "Captcha") or contains(@id, "pickimg")]'
        imgs = driver.find_elements(By.XPATH, xpath)
        img_el = next((img for img in imgs if img.is_displayed()), None)
        if not img_el:
            raise RuntimeError("無法找到驗證碼圖片")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img_el)
    time.sleep(0.5)
    img_bytes = img_el.screenshot_as_png

    try:
        ocr = ddddocr.DdddOcr(show_ad=False)
        return ocr.classification(img_bytes)
    except TypeError:
        ocr = ddddocr.DdddOcr()
        return ocr.classification(img_bytes)

def prepare_page_mode(driver: webdriver.Chrome, mode: str):
    wait = WebDriverWait(driver, 15)
    if mode == "legal":
        try:
            safe_click(driver, (By.XPATH, '//a[contains(@class, "tab") and contains(text(), "法人")]'))
        except Exception:
            safe_click(driver, (By.CLASS_NAME, "tab2"))
        wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@aria-label, "統一編號") or @id="id2"]')))
    else:
        try:
            safe_click(driver, (By.XPATH, '//a[contains(@class, "tab") and contains(text(), "個人")]'))
        except Exception:
            safe_click(driver, (By.CLASS_NAME, "tab1"))
        wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@aria-label, "身分證") or @id="id1"]')))

def execute_query(driver: webdriver.Chrome, mode: str, id_val: str, sub_val: str, captcha: str):
    wait = WebDriverWait(driver, 15)
    if mode == "legal":
        el_id = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="id2" or contains(@aria-label,"統一編號")]')))
        safe_type(driver, el_id, id_val)
        if sub_val:
            el_plate = driver.find_element(By.XPATH, '//div[contains(@style,"block")]//input[contains(@aria-label,"車號") or contains(@name,"plate")]')
            safe_type(driver, el_plate, sub_val)
        btn_locator = (By.ID, "search2")
    else:
        el_id = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="id1" or contains(@aria-label,"身分證")]')))
        safe_type(driver, el_id, id_val)
        if sub_val:
            el_bd = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="birthday" or contains(@aria-label,"生日")]')))
            safe_type(driver, el_bd, sub_val)
        btn_locator = (By.ID, "search1")

    captcha_input = next((el for el in driver.find_elements(By.NAME, "validateStr") if el.is_displayed()), None)
    if not captcha_input:
        captcha_input = wait.until(EC.visibility_of_element_located((By.NAME, "validateStr")))
    safe_type(driver, captcha_input, captcha)

    try:
        safe_click(driver, btn_locator)
    except Exception:
        driver.execute_script(f"document.getElementById('{btn_locator[1]}').click();")

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
    if not value:
        return
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    driver.execute_script("arguments[0].removeAttribute('readonly');", element)
    element.clear()
    element.send_keys(value)

def parse_mvdis_data(driver: webdriver.Chrome):
    results = []
    try:
        checkboxes = driver.find_elements(By.XPATH, "//input[contains(@onclick, 'changePay')]")
        for chk in checkboxes:
            onclick_val = chk.get_attribute("onclick")
            matches = re.findall(r"'([^']*)'", onclick_val)
            if len(matches) >= 12:
                results.append({
                    "單號": matches[4],
                    "違規時間": matches[1],
                    "違規事實": matches[2],
                    "車號": matches[5],
                    "金額": matches[8],
                    "違規地點": matches[11],
                    "應到案日": matches[3]
                })
    except Exception as e:
        print(f"頁面解析錯誤: {e}")
    return results

def get_all_pages_data(driver: webdriver.Chrome):
    wait = WebDriverWait(driver, 10)
    all_data = []
    while True:
        current_data = parse_mvdis_data(driver)
        if current_data:
            all_data.extend(current_data)

        next_btns = driver.find_elements(By.ID, "next")
        if not next_btns or not next_btns[0].is_displayed() or "disabled" in next_btns[0].get_attribute("class"):
            break

        try:
            next_btn = next_btns[0]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            try:
                next_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(1)
            try:
                wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
            except Exception:
                pass
            time.sleep(0.5)
        except Exception:
            break

    return all_data

def crawl_plate_numbers():
    print("🚀 啟動選號爬蟲...")
    driver = new_chrome(headless=True)
    plates = []
    url = "https://www.mvdis.gov.tw/m3-emv-plate/webpickno/queryPickNo#"

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        try:
            accept_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '(//a[text()="接受"])[2]')))
            driver.execute_script("arguments[0].click();", accept_btn)
            time.sleep(1)
        except Exception as e:
            print(f"接受按鈕略過: {e}")

        try:
            dept_el = wait.until(EC.element_to_be_clickable((By.ID, "selDeptCode")))
            Select(dept_el).select_by_visible_text("臺北市")
        except Exception:
            time.sleep(2)
            dept_el = driver.find_element(By.ID, "selDeptCode")
            Select(dept_el).select_by_visible_text("臺北市")
        time.sleep(1)

        station_el = wait.until(EC.element_to_be_clickable((By.ID, "selStationCode")))
        try:
            Select(station_el).select_by_visible_text("臺北市區監理所")
        except Exception:
            Select(station_el).select_by_index(1)
        time.sleep(1)

        win_el = wait.until(EC.element_to_be_clickable((By.ID, "selWindowNo")))
        Select(win_el).select_by_visible_text("臺北市八德路4段21號地下室")
        time.sleep(1)

        Select(driver.find_element(By.XPATH, "//tr[th[contains(text(),'車種別')]]//select")).select_by_visible_text("汽車")
        time.sleep(0.5)
        Select(driver.find_element(By.XPATH, "//tr[th[contains(text(),'能源別')]]//select")).select_by_visible_text("非電能")
        time.sleep(0.5)
        Select(driver.find_element(By.XPATH, "//tr[th[contains(text(),'車牌別')]]//select")).select_by_visible_text("營業小客車")

        captcha_img = wait.until(EC.visibility_of_element_located((By.ID, "pickimg")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", captcha_img)
        is_loaded = driver.execute_script(
            "return arguments[0].complete && typeof arguments[0].naturalWidth != 'undefined' && arguments[0].naturalWidth > 0;",
            captcha_img
        )
        time.sleep(1 if not is_loaded else 0.5)

        img_bytes = captcha_img.screenshot_as_png
        try:
            ocr = ddddocr.DdddOcr(show_ad=False)
            captcha_code = ocr.classification(img_bytes)
        except TypeError:
            ocr = ddddocr.DdddOcr()
            captcha_code = ocr.classification(img_bytes)

        input_field = driver.find_element(By.NAME, "validateStr")
        input_field.clear()
        input_field.send_keys(captcha_code)

        submit_btns = driver.find_elements(By.XPATH, "//a[text()='確定']")
        clicked = False
        for btn in submit_btns:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                break
        if not clicked:
            driver.execute_script("query();")

        time.sleep(2)
        if "驗證碼錯誤" in driver.page_source:
            print("❌ 選號查詢驗證碼錯誤")
            return []

        while True:
            try:
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "number")))
            except Exception:
                break

            numbers = driver.find_elements(By.XPATH, '//a[@class="number"]')
            for n in numbers:
                txt = n.text.strip()
                if txt:
                    plates.append(txt)

            next_btns = driver.find_elements(By.ID, "next")
            if not next_btns or not next_btns[0].is_displayed() or "disabled" in next_btns[0].get_attribute("class"):
                break

            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btns[0])
                driver.execute_script("arguments[0].click();", next_btns[0])
                time.sleep(0.5)
                try:
                    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
                except Exception:
                    pass
                time.sleep(1)
            except Exception as e:
                print(f"選號翻頁錯誤: {e}")
                break
    except Exception as e:
        print(f"❌ 選號查詢錯誤: {e}")
    finally:
        driver.quit()

    return plates

def get_ai_appeal_advice(tkt_no, fact, image_url):
    if not client:
        return "抱歉，目前尚未設定 AI 分析服務。"

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
最後，如果建議申訴，請提供一段簡短的申訴理由書範本。
""".strip()

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI 分析失敗: {e}")
        return "抱歉大哥，AI 目前忙碌中，請稍後再試。"
