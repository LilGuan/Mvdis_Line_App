# ==========================================
# 🎨 UI 模板中心 (ui_templates.py)
# ==========================================

from linebot.models import (
    FlexSendMessage, TextSendMessage, CarouselContainer, BubbleContainer
)
from urllib.parse import quote_plus
from config import DEFAULT_HERO_IMAGE, MV_DIS_URL

# --- 1. 停車場搜尋結果卡片 ---
def create_parking_flex(nearby_lots):
    """
    產生附近停車場的橫向捲動卡片 (Carousel)
    nearby_lots: 包含距離資訊的停車場列表
    """
    bubbles = []
    for lot in nearby_lots:
        # 基本欄位
        contents = [
            {"type": "text", "text": lot['name'], "weight": "bold", "size": "sm", "wrap": True},
            {"type": "text", "text": f"距離: {lot['distance']} km", "size": "xs", "color": "#ff5551"},
            {"type": "text", "text": f"📍 {lot['address']}", "size": "xxs", "color": "#aaaaaa", "wrap": True},
            {"type": "separator", "margin": "md"}
        ]

        # 取得優惠標籤狀態
        has_free_30m = lot.get('free_30m', False)
        has_free_1h = lot.get('free_1h', False)
        has_free_2h = lot.get('free_2h', False)
        has_free_4h = lot.get('free_4h', False)
        has_noon_2h = lot.get('noon_2h', False)

        # 邏輯判斷：顯示哪些優惠
        if has_free_30m and not any([has_free_1h, has_free_2h, has_free_4h, has_noon_2h]):
            contents.append({"type": "text", "text": "✅ 未滿30分鐘免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_free_1h:
            contents.append({"type": "text", "text": "✅ 1小時免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_free_2h:
            contents.append({"type": "text", "text": "✅ 2小時免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_free_4h:
            contents.append({"type": "text", "text": "✅ 4小時免費", "size": "xs", "margin": "md", "color": "#00b900"})
        
        if has_noon_2h:
            contents.append({"type": "text", "text": "✅ 中午免費2小時", "size": "xs", "margin": "md", "color": "#00b900"})

        if not any([has_free_30m, has_free_1h, has_free_2h, has_free_4h, has_noon_2h]):
            contents.append({"type": "text", "text": "❌ 無免費停車優惠", "size": "xs", "margin": "md", "color": "#ff0000"})

        bubble = {
            "type": "bubble",
            "size": "micro",
            "body": {"type": "box", "layout": "vertical", "contents": contents},
            "footer": {
                "type": "box", "layout": "vertical", 
                "contents": [
                    {
                        "type": "button", "style": "primary", "color": "#00b900", "height": "sm",
                        "action": {
                            "type": "uri", "label": "導航", 
                            "uri": f"https://www.google.com/maps/search/?api=1&query={lot['lat']},{lot['lng']}"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return FlexSendMessage(alt_text="最近的停車場", contents={"type": "carousel", "contents": bubbles})


# --- 2. 車輛列表卡片 (檢視與刪除模式) ---
def create_car_list_flex(cars, mode='view'):
    """
    mode='view': 純查看
    mode='delete': 顯示紅色刪除按鈕
    """
    bubbles = []
    for car in cars:
        type_text = "🏢 公司車" if car['mode'] == 'legal' else "🚗 個人車"
        id_label = "統編" if car['mode'] == 'legal' else "身分證"
        sub_label = "車號" if car['mode'] == 'legal' else "生日"

        bubble = {
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": car['name'], "weight": "bold", "size": "md", "color": "#1DB446"},
                    {"type": "text", "text": type_text, "size": "xxs", "color": "#aaaaaa"}
                ],
                "backgroundColor": "#f0f0f0"
            },
            "body": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"{id_label}: {car['id']}", "size": "xs", "wrap": True},
                    {"type": "text", "text": f"{sub_label}: {car['sub_id']}", "size": "xs", "wrap": True}
                ]
            }
        }

        if mode == 'delete':
            bubble["footer"] = {
                "type": "box", "layout": "vertical",
                "contents": [
                    {
                        "type": "button", "style": "secondary", "height": "sm", "color": "#FF3333",
                        "action": {
                            "type": "postback", "label": "刪除此車",
                            "data": f"action=delete_car&car_id={car['db_id']}&car_name={car['name']}",
                            "displayText": f"我要刪除 {car['name']}"
                        }
                    }
                ]
            }
        bubbles.append(bubble)

    return FlexSendMessage(alt_text="您的車輛清單", contents={"type": "carousel", "contents": bubbles})


# --- 3. 罰單查詢選擇卡片 ---
def create_car_selection_flex(cars):
    """產生藍色查詢按鈕的卡片，供使用者選擇查詢哪台車"""
    bubbles = []
    for car in cars:
        type_text = "🏢 公司車" if car['mode'] == 'legal' else "🚗 個人車"
        display_no = car['plate_no'] if car['plate_no'] else car['id']

        bubble = {
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box", "layout": "vertical", "paddingAll": "8px",
                "contents": [
                    {"type": "text", "text": car['name'], "weight": "bold", "color": "#1DB446", "size": "sm"},
                    {"type": "text", "text": type_text, "size": "xxs", "color": "#aaaaaa"}
                ],
                "backgroundColor": "#f0f0f0"
            },
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "10px",
                "contents": [{"type": "text", "text": display_no, "size": "xs", "align": "center", "weight": "bold"}]
            },
            "footer": {
                "type": "box", "layout": "vertical", "paddingAll": "5px",
                "contents": [
                    {
                        "type": "button", "style": "primary", "height": "sm", "color": "#007bff",
                        "action": {
                            "type": "postback", "label": "查詢此車",
                            "data": f"action=check_one_car&car_id={car['db_id']}",
                            "displayText": f"🔍 正在查詢 {car['name']}..."
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return FlexSendMessage(alt_text="請選擇要查詢的車輛", contents={"type": "carousel", "contents": bubbles})


# --- 4. 交通違規警報卡片 (最核心的罰單通知) ---
def create_fine_flex_message(record_data, id_number, image_urls):
    """
    record_data: 單筆罰單物件
    image_urls: 該罰單的照片網址清單
    """
    tkt_no = record_data['單號']
    bubbles = []
    
    # 若無照片，使用預設圖
    display_images = image_urls if image_urls else [DEFAULT_HERO_IMAGE]

    for idx, img_url in enumerate(display_images):
        page_txt = f" ({idx+1}/{len(display_images)})" if len(display_images) > 1 else ""
        encoded_fact = quote_plus(record_data['違規事實'].strip())
        encoded_img_url = quote_plus(img_url)
        
        bubble = {
            "type": "bubble", "size": "giga",
            "styles": {"header": {"backgroundColor": "#850000"}, "body": {"backgroundColor": "#2b2b2b"}, "footer": {"backgroundColor": "#2b2b2b"}},
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "🚨 交通違規警報", "weight": "bold", "color": "#ffffff", "size": "md", "align": "center"}]
            },
            "hero": {
                "type": "image", "url": img_url, "size": "full", "aspectRatio": "20:13", "aspectMode": "cover",
                "action": {"type": "uri", "uri": img_url}
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"{record_data['車號']}{page_txt}", "weight": "bold", "size": "xl", "color": "#ffffff", "align": "center"},
                    {"type": "text", "text": f"單號: {tkt_no}", "size": "xs", "color": "#aaaaaa", "align": "center", "margin": "xs"},
                    {"type": "separator", "margin": "lg", "color": "#555555"},
                    {"type": "box", "layout": "vertical", "margin": "lg", "spacing": "sm", "contents": [
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "金額", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": f"NT$ {record_data['金額']}", "color": "#FF3333", "size": "xl", "weight": "bold", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "時間", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data['違規時間'], "color": "#ffffff", "size": "sm", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "應到案日", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data.get('應到案日', '無'), "color": "#ffcc00", "size": "sm", "flex": 4}]},
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "地點", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data.get('違規地點', '未知'), "color": "#ffffff", "size": "sm", "flex": 4, "wrap": True}]},
                        {"type": "box", "layout": "baseline", "contents": [{"type": "text", "text": "事由", "color": "#aaaaaa", "size": "sm", "flex": 1}, {"type": "text", "text": record_data['違規事實'], "color": "#ffffff", "size": "sm", "flex": 4, "wrap": True}]}
                    ]}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "height": "sm", "color": "#E60000", "action": {"type": "uri", "label": "前往監理站繳費", "uri": MV_DIS_URL}},
                    {"type": "button", "style": "secondary", "height": "sm", "color": "#00b900", "action": {"type": "postback", "label": "🤖 AI 申訴評估", "data": f"action=ai_analyze&tkt_no={tkt_no}&img_url={encoded_img_url}&fact={encoded_fact}", "displayText": f"請幫我分析這張罰單{tkt_no}能否申訴"}}
                ]
            }
        }
        bubbles.append(bubble)
    
    container = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return FlexSendMessage(alt_text=f"🚨 罰單通知：{record_data['車號']}", contents=container)


# --- 5. 監理站選號結果卡片 ---
def create_plate_flex(plates_chunk, batch_index, total_count):
    """每張卡片顯示 30 個號碼 (3直行 x 10橫列)"""
    bubbles = []
    items_per_bubble = 30
    sub_chunks = [plates_chunk[i:i + items_per_bubble] for i in range(0, len(plates_chunk), items_per_bubble)]
    
    for i, b_chunk in enumerate(sub_chunks):
        rows_contents = []
        for j in range(0, len(b_chunk), 3):
            row_items = b_chunk[j:j+3]
            rows_contents.append({
                "type": "box", "layout": "horizontal", "margin": "md",
                "contents": [{"type": "text", "text": p, "size": "md", "align": "center", "weight": "bold"} for p in row_items]
            })

        bubble = {
            "type": "bubble", "size": "giga",
            "header": {
                "type": "box", "layout": "vertical", "backgroundColor": "#00b900", "paddingAll": "12px",
                "contents": [
                    {"type": "text", "text": "🟢 監理站選號結果", "weight": "bold", "color": "#ffffff", "size": "sm"},
                    {"type": "text", "text": f"批次 {batch_index}-{i+1} | 範圍: {b_chunk[0]}~{b_chunk[-1]}", "color": "#ffffff", "size": "xs"}
                ]
            },
            "body": {"type": "box", "layout": "vertical", "contents": rows_contents, "paddingAll": "10px"}
        }
        bubbles.append(bubble)

    return FlexSendMessage(alt_text="選號查詢結果", contents={"type": "carousel", "contents": bubbles})
