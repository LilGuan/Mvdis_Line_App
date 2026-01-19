import os,re
import time
import tempfile
from typing import Dict, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

MV_DIS_URL = "https://www.mvdis.gov.tw/m3-emv-vil/vil/penaltyQueryPay"

def new_chrome(headless: bool = True) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    
    # 基本反爬蟲設置
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080") # 視窗大一點避免元素重疊
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=zh-TW")

    # 忽略憑證錯誤
    options.add_argument("--ignore-certificate-errors")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def safe_click(driver, locator, timeout=10):
    """ 安全點擊：等待可點擊 + 滾動到可見區域 + JS fallback """
    wait = WebDriverWait(driver, timeout)
    try:
        el = wait.until(EC.element_to_be_clickable(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        el.click()
    except Exception:
        # 如果被遮擋，嘗試 JS 強制點擊
        el = driver.find_element(*locator)
        driver.execute_script("arguments[0].click();", el)

def safe_type(driver, element, value: str, clear: bool = True):
    """ 安全輸入：處理 readonly, 滾動, 清空 """
    if not value:
        return
    
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    
    # 移除 readonly 屬性 (針對日期選擇器)
    driver.execute_script("arguments[0].removeAttribute('readonly');", element)
    
    if clear:
        element.clear()
        # 雙重保險清空
        driver.execute_script("arguments[0].value = '';", element)
    
    element.send_keys(value)

def prepare_page_mode(driver: webdriver.Chrome, mode: str):
    """
    切換到正確的 Tab 並回傳該區塊的 Container 元素
    """
    wait = WebDriverWait(driver, 5)
    
    if mode == "legal":
        # 點擊法人 Tab (假設 class 包含 tab2)
        xpath_tab = '//a[contains(@class, "tab") and contains(text(), "法人")]'
        try:
            safe_click(driver, (By.XPATH, xpath_tab))
        except:
            # 備用：有時候 class 是 tab2
            safe_click(driver, (By.CLASS_NAME, "tab2"))
            
        # 等待法人表格出現 (通常 id="block2" 或類似特徵)
        # 這裡用 "統一編號" 的輸入框可見性來判斷 Tab 是否切換成功
        wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@aria-label, "統一編號") or @id="id2"]')))
        
    else:
        # 點擊個人 Tab
        xpath_tab = '//a[contains(@class, "tab") and contains(text(), "個人")]'
        try:
            safe_click(driver, (By.XPATH, xpath_tab))
        except:
            safe_click(driver, (By.CLASS_NAME, "tab1"))
            
        # 等待個人表格出現
        wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@aria-label, "身分證") or @id="id1"]')))
def parse_current_page(driver: webdriver.Chrome) -> list:
    """
    抓取「當前頁面」的所有罰單資料 (回傳 List)
    """
    results = []
    # 策略: 從 checkbox 的 onclick="changePay(...)" 中提取資料
    try:
        checkboxes = driver.find_elements(By.XPATH, "//input[contains(@onclick, 'changePay')]")
        
        for chk in checkboxes:
            onclick_val = chk.get_attribute("onclick")
            if not onclick_val: continue
            
            # 正則表達式抓參數
            matches = re.findall(r"'([^']*)'", onclick_val)
            
            # 確保參數數量足夠 (根據你的截圖通常有 12+ 個參數)
            if len(matches) >= 12:
                # 建立一個乾淨的字典或是格式化字串
                data_str = (
                    f"單號: {matches[4]} | "
                    f"時間: {matches[1]} | "
                    f"車號: {matches[5]} | "
                    f"金額: {matches[8]} 元 | "
                    f"事實: {matches[2]}"
                )
                results.append(data_str)
    except Exception as e:
        print(f"解析頁面發生錯誤: {e}")
        
    return results

def get_all_pages_data(driver: webdriver.Chrome) -> list[str]:
    """
    [核心] 自動翻頁抓取所有資料 (針對 id="next" 優化)
    """
    wait = WebDriverWait(driver, 10)
    all_data = []
    page_count = 1

    while True:
        # 1. 抓取當前頁面資料
        current_data = parse_current_page(driver)
        if current_data:
            all_data.extend(current_data)
            print(f"  -> 第 {page_count} 頁抓到 {len(current_data)} 筆資料")
        else:
            print(f"  -> 第 {page_count} 頁無資料 (或解析失敗)")

        # 2. 嘗試尋找「下一頁」按鈕
        # 根據你的截圖，按鈕結構為 <a id="next" ...><img alt="下一頁"></a>
        # 使用 find_elements 比較安全，找不到時回傳空串列，不會直接報錯
        next_btns = driver.find_elements(By.ID, "next")
        
        # 如果找不到 id="next" 的元素，代表已經在最後一頁了
        if not next_btns:
            print("沒有下一頁了 (未發現下一頁按鈕)，抓取結束。")
            break
            
        next_btn = next_btns[0]
        
        # 額外檢查：有時候按鈕存在但被隱藏 (display: none)
        if not next_btn.is_displayed():
            print("已達最後一頁 (按鈕不可見)，抓取結束。")
            break

        # 3. 點擊並等待
        try:
            print(f"正在前往第 {page_count + 1} 頁...")
            
            # 滾動到按鈕處，確保不被遮擋
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            
            # 點擊
            try:
                next_btn.click()
            except Exception:
                # 備用點擊方案：JS Click
                driver.execute_script("arguments[0].click();", next_btn)
            
            page_count += 1
            
            # 4. 等待載入 (監理站會有 blockUI 遮罩)
            # 先睡一下等遮罩出現，避免程式跑太快以為遮罩已經沒了
            time.sleep(1) 
            try:
                # 等待遮罩消失
                wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "blockUI")))
            except:
                pass
            
            # 再睡一下確保表格內容 DOM 渲染完畢
            time.sleep(0.5)

        except Exception as e:
            print(f"翻頁過程中發生錯誤: {e}")
            break
            
    return all_data
def get_captcha_image(driver: webdriver.Chrome, mode: str) -> str:
    """
    抓取驗證碼圖片 (針對 MVDIS 優化 ID 選擇與載入檢查)
    """
    wait = WebDriverWait(driver, 20)

    # 1. 根據模式直接鎖定該 Tab 對應的圖片 ID
    # 個人查詢通常是 id="pickimg"
    # 法人查詢通常是 id="pickimg2"
    if mode == "legal":
        target_id = "pickimg2"
    else:
        target_id = "pickimg"

    print(f"正在尋找驗證碼圖片，目標 ID: {target_id}...")

    # 2. 等待元素出現
    try:
        img_el = wait.until(EC.visibility_of_element_located((By.ID, target_id)))
    except Exception:
        # Fallback: 如果 ID 變了，改用通用特徵找 (class 包含 validate 或 src 包含 validate)
        print("ID 定位失敗，嘗試通用特徵定位...")
        xpath = '//img[contains(@src, "validate") or contains(@src, "Captcha") or contains(@id, "pickimg")]'
        imgs = driver.find_elements(By.XPATH, xpath)
        img_el = None
        for img in imgs:
            if img.is_displayed():
                img_el = img
                break
        if not img_el:
            raise RuntimeError("無法找到驗證碼圖片元素")

    # 3. 確保圖片「內容」已載入 (避免截到破圖)
    # 使用 JS 檢查 naturalWidth
    is_loaded = driver.execute_script(
        "return arguments[0].complete && typeof arguments[0].naturalWidth != 'undefined' && arguments[0].naturalWidth > 0;",
        img_el
    )
    
    if not is_loaded:
        print("圖片尚未完全載入，等待 1 秒...")
        time.sleep(1)
        # 還是沒載入的話，嘗試點擊圖片重新整理一下
        try:
            img_el.click()
            time.sleep(1.5)
        except:
            pass

    # 4. 滾動到視野中 (避免被 header 擋住導致截圖報錯)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img_el)
    time.sleep(0.5) # 給一點滾動動畫時間

    # 5. 截圖
    out_path = os.path.join(tempfile.gettempdir(), f"mvdis_cap_{int(time.time())}.png")
    
    try:
        img_el.screenshot(out_path)
    except Exception as e:
        # 如果元素截圖失敗，改用 Base64 抓取 (備用方案)
        print(f"元素截圖失敗 ({e})，嘗試 Base64 方案...")
        src = img_el.get_attribute("src")
        if src and "base64" in src:
            import base64
            data = src.split("base64,")[-1]
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(data))
        else:
            raise e

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("截圖檔案為空或未建立")

    return out_path
def execute_query(driver: webdriver.Chrome, mode: str, inputs: Dict[str, str], captcha: str):
    """
    填寫表單並送出
    """
    wait = WebDriverWait(driver, 15)
    
    # 1. 尋找輸入框 (只找可見的)
    if mode == "legal":
        # 統一編號 (通常 id="id2")
        el_id = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="id2" or contains(@aria-label,"統一編號")]')))
        safe_type(driver, el_id, inputs.get("unified_no", ""))
        
        # 車號 (有的話)
        if inputs.get("plate_no"):
            # 在法人區塊內找車號
            el_plate = driver.find_element(By.XPATH, '//div[contains(@style,"block")]//input[contains(@aria-label,"車號") or contains(@name,"plate")]')
            safe_type(driver, el_plate, inputs.get("plate_no", ""))
            
    else:
        # 身分證 (通常 id="id1")
        el_id = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="id1" or contains(@aria-label,"身分證")]')))
        safe_type(driver, el_id, inputs.get("personal_id", ""))
        
        # 生日 (通常 id="birthday")
        if inputs.get("birthday"):
            el_bd = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[@id="birthday" or contains(@aria-label,"生日")]')))
            safe_type(driver, el_bd, inputs.get("birthday", ""))

    # 2. 填寫驗證碼 (關鍵修改：只找可見的 validateStr)
    # 使用 xpath 組合拳：name 是 validateStr 且不是 hidden 且 當前可見
    captcha_input = None
    candidates = driver.find_elements(By.NAME, "validateStr")
    for c in candidates:
        if c.is_displayed():
            captcha_input = c
            break
            
    if not captcha_input:
         captcha_input = wait.until(EC.visibility_of_element_located((By.NAME, "validateStr")))

    safe_type(driver, captcha_input, captcha)
    
    # 3. 點擊查詢按鈕 (修改為指定 ID)
    if mode == "legal":
        btn_locator = (By.ID, "search2")
        print("正在點擊法人查詢按鈕 (search2)...")
    else:
        btn_locator = (By.ID, "search1")
        print("正在點擊個人查詢按鈕 (search1)...")

    try:
        # 使用 safe_click 確保：等待可點擊 + 滾動到可視範圍 + 點擊
        safe_click(driver, btn_locator)
    except Exception as e:
        # 如果標準點擊失敗，嘗試最後的 JS 強制觸發 (針對有些情況按鈕被 mask 擋住)
        print(f"標準點擊失敗，嘗試 JS 強制點擊: {e}")
        btn = driver.find_element(*btn_locator)
        driver.execute_script("arguments[0].click();", btn)

def check_result(driver: webdriver.Chrome) -> Dict[str, Any]:
    """
    解析結果：同時支援「列表頁 hidden JS 資料」與「彈出視窗表格」
    """
    time.sleep(1.5)

    # 1. 檢查 Alert / 基本錯誤
    try:
        alert = driver.switch_to.alert
        alert.accept()
    except:
        pass

    page_source = driver.page_source
    if "驗證碼錯誤" in page_source:
        return {"ok": False, "message": "驗證碼錯誤"}
    if "查無" in page_source and "資料" in page_source:
        return {"ok": True, "message": "查無違規資料"}

    parsed_results = []

    # =========================================================
    # 策略 A: 針對列表頁 (你的截圖情況)
    # 從 checkbox 的 onclick="changePay(...)" 中提取資料
    # =========================================================
    try:
        # 尋找所有包含 changePay 的 checkbox
        checkboxes = driver.find_elements(By.XPATH, "//input[contains(@onclick, 'changePay')]")
        
        if checkboxes:
            print(f"找到 {len(checkboxes)} 筆列表資料，正在解析 JS 參數...")
            
            for i, chk in enumerate(checkboxes):
                onclick_val = chk.get_attribute("onclick")
                # onclick 格式範例: 
                # changePay('12', '2025/12/15 14:56:00', '違規事實', ..., '900', ...)
                
                # 使用 Regex 抓取所有單引號內的內容
                # pattern 意思：抓取 ' 裡面的內容 '
                matches = re.findall(r"'([^']*)'", onclick_val)
                
                # 根據截圖參數順序推測索引：
                # 0: ID (12)
                # 1: 違規時間 (2025/12/15...)
                # 2: 違規事實 (在交岔路口...)
                # 3: 應到案日
                # 4: 違規單號 (RA7570160)
                # 5: 車號 (892-9C)
                # 8: 罰鍰金額 (900)
                # 11: 違規地點 (暖暖區...)
                
                if len(matches) >= 12:
                    res_str = (
                        f"=== 罰單 #{i+1} ===\n"
                        f"單號: {matches[4]}\n"
                        f"時間: {matches[1]}\n"
                        f"車號: {matches[5]}\n"
                        f"地點: {matches[11]}\n"
                        f"事實: {matches[2]}\n"
                        f"金額: {matches[8]} 元\n"
                        f"應到案日: {matches[3]}\n"
                    )
                    parsed_results.append(res_str)
            
            return {"ok": True, "message": "\n".join(parsed_results)}
            
    except Exception as e:
        print(f"列表解析失敗: {e}")

    # =========================================================
    # 策略 B: 針對彈出視窗 (如果你有手動點開詳細資料)
    # 抓取 class="tb_list_std"
    # =========================================================
    try:
        tables = driver.find_elements(By.CSS_SELECTOR, "table.tb_list_std")
        if tables:
            for index, table in enumerate(tables):
                if not table.is_displayed(): continue # 只抓顯示的
                
                rows = table.find_elements(By.TAG_NAME, "tr")
                detail_str = f"=== 詳細視窗 #{index + 1} ===\n"
                has_content = False
                for row in rows:
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        headers = row.find_elements(By.TAG_NAME, "th")
                        if cols and headers:
                            th = headers[0].text.strip()
                            td = cols[0].text.strip()
                            detail_str += f"{th}: {td}\n"
                            has_content = True
                    except:
                        continue
                if has_content:
                    parsed_results.append(detail_str)
            
            if parsed_results:
                return {"ok": True, "message": "\n".join(parsed_results)}

    except Exception:
        pass

    # =========================================================
    # 策略 C: 什麼都沒抓到，回傳 Body 前段文字供除錯
    # =========================================================
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        # 簡單過濾掉太多空白
        clean_text = "\n".join([line.strip() for line in body_text.splitlines() if line.strip()])
        return {"ok": False, "message": f"未解析到表格結構，頁面文字預覽:\n{clean_text[:500]}..."}
    except:
        return {"ok": False, "message": "解析完全失敗"}

def run_cli():
    print("=== MVDis 監理站罰單查詢優化版 ===")
    
    # 簡單輸入介面
    mode_map = {"1": "personal", "2": "legal"}
    print("1. 個人查詢\n2. 法人查詢")
    sel = input("請選擇 (預設 1): ").strip()
    mode = mode_map.get(sel, "personal")

    inputs = {}
    if mode == "legal":
        inputs["unified_no"] = input("統一編號 (8碼): ").strip()
        inputs["plate_no"] = input("車號 (選填): ").strip()
    else:
        inputs["personal_id"] = input("身分證字號: ").strip()
        inputs["birthday"] = input("生日 (民國年7碼, e.g. 0800101): ").strip()

    # 啟動瀏覽器
    driver = new_chrome(headless=False) # 為了看驗證碼方便，先開視窗，想 headless 改 True
    
    try:
        print(f"正在前往 {MV_DIS_URL} ...")
        driver.get(MV_DIS_URL)
        
        # 1. 先切換模式並等待頁面就緒
        prepare_page_mode(driver, mode)
        
        # 2. 抓取驗證碼
        cap_path = get_captcha_image(driver, mode)
        print(f"\n驗證碼圖片已存至: {cap_path}")
        
        # Mac 用戶可以用這行自動打開圖片，Windows 可移除或改用 os.startfile(cap_path)
        if os.name == 'posix': 
            os.system(f"open {cap_path}")
        elif os.name == 'nt':
            os.startfile(cap_path)

        user_cap = input(">> 請輸入圖片中的驗證碼: ").strip()
        
        # 3. 填寫並送出
        print("正在查詢...")
        execute_query(driver, mode, inputs, user_cap)
        
        # 4. 解析結果
        if "驗證碼錯誤" in driver.page_source:
            print("驗證碼錯誤，請重試。")
        elif "查無" in driver.page_source and "資料" in driver.page_source:
            print("查無違規資料。")
        else:
            # 開始執行翻頁抓取
            total_results = get_all_pages_data(driver)
            
            print("\n" + "="*30)
            print(f"查詢完成！總共抓到 {len(total_results)} 筆資料：")
            for item in total_results:
                print(item)
            print("="*30)

    except Exception as e:
        print(f"發生錯誤: {e}")
        # debug 用：截圖錯誤畫面
        driver.save_screenshot("error_debug.png")
    finally:
        print("關閉瀏覽器...")
        driver.quit()

if __name__ == "__main__":
    run_cli()