import time
import base64
import ddddocr
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 🚑 修正 Pillow 版本問題 (必須放在 import ddddocr 之前)
# ==========================================
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
# ==========================================

import ddddocr  # ddddocr 必須在修正代碼之後匯入
from selenium import webdriver
# ==========================================
# 🔧 瀏覽器設定
# ==========================================
def new_chrome(headless=False):
    """
    啟動 Chrome 瀏覽器
    headless: True (背景執行), False (顯示視窗, 測試用)
    """
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    
    # 模擬真實使用者，避免被擋
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800") # 設定視窗大小，避免元素重疊
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

# ==========================================
# 🕷️ 選號爬蟲核心邏輯
# ==========================================
def crawl_plate_numbers():
    print("🚀 啟動選號爬蟲測試...")
    
    # 測試時建議設為 False，看得到畫面比較好 debug
    driver = new_chrome(headless=False) 
    plates = []
    url = "https://www.mvdis.gov.tw/m3-emv-plate/webpickno/queryPickNo#"

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        # ===========================================
        # 0. 處理「接受」按鈕 (新增部分)
        # ===========================================
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

# ==========================================
# 🏁 測試執行入口
# ==========================================
if __name__ == "__main__":
    result = crawl_plate_numbers()
    
    print("\n" + "="*30)
    print(f"🎉 測試完成！共抓到 {len(result)} 筆車牌")
    print("="*30)
    
    # 印出所有車牌 (每10個換行)
    for i in range(0, len(result), 10):
        print(", ".join(result[i:i+10]))