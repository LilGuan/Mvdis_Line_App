# ==========================================
# 🎨 UI 模板中心 (ui_templates.py)
# ==========================================

import re

from linebot.models import (
    FlexSendMessage, TextSendMessage, CarouselContainer, BubbleContainer
)
from config import DEFAULT_HERO_IMAGE, MV_DIS_URL, TAIWANTAXI_55688_LOGO_URL

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


# --- 2. 叫車比價卡片 ---
def create_ride_compare_flex(compare_result):
    bubbles = []
    pickup = _short_place(compare_result.get("pickup", {}))
    destination = _short_place(compare_result.get("destination", {}))
    provider_colors = {
        "Uber": "#111111",
        "LINE GO": "#0DD54D",
        "55688": "#F6C103",
        "Bolt": "#FFFFFFFF",
    }
    provider_logos = {
        "Uber": "https://i.ibb.co/fYWZMMKw/123d3d735b60.png",
        "LINE GO": "https://i.ibb.co/S7RSGL6P/767c5908696f.png",
        "55688": TAIWANTAXI_55688_LOGO_URL,
        "Bolt": "https://i.ibb.co/mrBSDryN/09fbcf4552d2.png",
    }
    provider_logo_sizes = {
        "Uber": "lg",
        "LINE GO": "lg",
        "55688": "lg",
        "Bolt": "lg",
    }
    provider_logo_ratios = {
        "Uber": "60:18",
        "LINE GO": "60:18",
        "55688": "60:18",
        "Bolt": "60:18",
    }

    for provider_result in compare_result.get("results", []):
        rows = [
            {
                "type": "box",
                "layout": "baseline",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": quote["name"], "size": "sm", "color": "#444444", "flex": 4, "wrap": True},
                    {"type": "text", "text": quote["fare"], "size": "sm", "color": "#111111", "weight": "bold", "align": "end", "flex": 2},
                ],
            }
            for quote in provider_result.get("quotes", [])[:8]
        ]

        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": provider_colors.get(provider_result["provider"], "#444444"),
                "paddingTop": "14px",
                "paddingBottom": "14px",
                "paddingStart": "0px",
                "paddingEnd": "0px",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "paddingStart": "10px",
                        "paddingEnd": "12px",
                        "contents": [
                            {
                                "type": "image",
                                "url": provider_logos.get(provider_result["provider"], ""),
                                "flex": 0,
                                "size": provider_logo_sizes.get(provider_result["provider"], "lg"),
                                "aspectMode": "fit",
                                "aspectRatio": provider_logo_ratios.get(provider_result["provider"], "60:18"),
                                "align": "start",
                                "gravity": "center",
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "flex": 1,
                                "contents": [],
                            },
                        ],
                    }
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {"type": "separator", "color": "#E5E7EB"},
                    {"type": "text", "text": f"{pickup} → {destination}", "size": "xs", "color": "#777777", "wrap": True},
                    {"type": "separator"},
                    {"type": "box", "layout": "vertical", "spacing": "sm", "contents": rows or [
                        {"type": "text", "text": "目前沒有符合條件的固定價", "size": "sm", "color": "#999999", "wrap": True}
                    ]},
                    {"type": "text", "text": "⚠️此為預估車資，僅供參考", "size": "xxs", "color": "#999999", "wrap": True},
                ],
            },
        }
        bubbles.append(bubble)

    if not bubbles:
        bubble = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "叫車比價", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": "目前沒有取得可顯示的固定價。", "size": "sm", "color": "#666666", "margin": "md", "wrap": True},
                ],
            },
        }
        bubbles.append(bubble)

    return FlexSendMessage(alt_text="叫車比價結果", contents={"type": "carousel", "contents": bubbles})

def _extract_taiwan_district(address):
    text = str(address or "")
    match = re.search(r"[\u4e00-\u9fff]{1,6}[縣市]([\u4e00-\u9fff]{1,8}[鄉鎮市區])", text)
    if match:
        return match.group(1)
    match = re.search(r"([\u4e00-\u9fff]{1,8}[鄉鎮市區])", text)
    return match.group(1) if match else "-"


def _format_55688_route_label(job):
    pickup_area = job.get("pickupArea") or _extract_taiwan_district(job.get("onAddrHumanRead"))
    dropoff_area = job.get("dropoffArea") or _extract_taiwan_district(job.get("offAddrHumanRead"))
    if pickup_area != "-" and dropoff_area != "-":
        return f"{pickup_area} → {dropoff_area}"
    return job.get("areaName") or "-"


def _create_55688_logo_header(title, subtitle, title_size="lg"):
    contents = [
        {
            "type": "box",
            "layout": "vertical",
            "flex": 1,
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": title_size, "color": "#111111", "wrap": True},
                {"type": "text", "text": str(subtitle), "size": "xs", "color": "#4A3A00", "margin": "xs", "wrap": True},
            ],
        }
    ]
    if TAIWANTAXI_55688_LOGO_URL:
        contents.append({
            "type": "image",
            "url": TAIWANTAXI_55688_LOGO_URL,
            "size": "md",
            "aspectRatio": "4:3",
            "aspectMode": "fit",
            "align": "end",
            "gravity": "top",
            "flex": 0,
        })
    return {
        "type": "box",
        "layout": "horizontal",
        "spacing": "md",
        "contents": contents,
    }


def create_55688_reservation_demo_flex(jobs, title="55688 預約單", subtitle="僅供內部測試，不是真實派單"):
    if not jobs:
        return TextSendMessage(text="55688 預約單\n目前沒有可顯示的資料。")

    bubbles = []
    for job in jobs[:10]:
        area_label = _format_55688_route_label(job) or job.get("areaName") or subtitle
        fare_label = job.get("estimatedFare") or "-"
        card_subtitle = f"{area_label}｜NT$ {fare_label}"
        rows = [
            ("單號", job.get("jobId", "-")),
            ("預約時間", job.get("bookingTime", "-")),
            ("預估車資", f"NT$ {job.get('estimatedFare', '-')}"),
            ("類型", job.get("jobRequireName", "-")),
            ("付款", job.get("payTypeLabel", "-")),
            ("特殊需求", job.get("specialReq") or "無"),
            ("可接單時間", job.get("canTakeJobTime", "-")),
        ]
        detail_contents = []
        for label, value in rows:
            detail_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "contents": [
                    {"type": "text", "text": label, "size": "xs", "color": "#7A7A7A", "flex": 3},
                    {"type": "text", "text": str(value), "size": "xs", "color": "#222222", "wrap": True, "flex": 7},
                ],
            })

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F6C103",
                "paddingAll": "16px",
                "contents": [
                    _create_55688_logo_header(title, card_subtitle),
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "xs",
                        "contents": [
                            {"type": "text", "text": "上車地點", "size": "xs", "color": "#888888"},
                            {"type": "text", "text": job.get("onAddrHumanRead", "-"), "size": "sm", "wrap": True, "weight": "bold"},
                        ],
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "xs",
                        "contents": [
                            {"type": "text", "text": "下車地點", "size": "xs", "color": "#888888"},
                            {"type": "text", "text": job.get("offAddrHumanRead", "-"), "size": "sm", "wrap": True, "weight": "bold"},
                        ],
                    },
                    {"type": "separator"},
                    {"type": "box", "layout": "vertical", "contents": detail_contents},
                ],
            },
        }
        bubbles.append(bubble)

    first_job = jobs[0]
    first_route = _format_55688_route_label(first_job)
    first_fare = first_job.get("estimatedFare", "-")
    return FlexSendMessage(
        alt_text=f"55688 預約單｜{first_route}｜NT$ {first_fare}",
        contents={"type": "carousel", "contents": bubbles},
    )

def create_55688_settings_flex(settings, area_options):
    active_text = "啟用中" if settings.get("active") else "已停用"
    active_color = "#0BBF4C" if settings.get("active") else "#999999"
    area_ids = settings.get("areas") or []
    area_text = "、".join(area_options.get(area_id, str(area_id)) for area_id in area_ids) or "未設定"
    date_mode = settings.get("date_mode", "all")
    date_value = settings.get("date_value") or ""
    if date_mode == "all":
        date_text = "全部日期"
    elif date_mode == "today":
        date_text = "今天"
    elif date_mode == "range" and "~" in date_value:
        start_date, end_date = date_value.split("~", 1)
        date_text = f"{start_date} ~ {end_date}"
    else:
        date_text = date_value or "指定日期"
    try:
        frequency_min = int(settings.get("frequency_min_sec") or 50)
        frequency_max = int(settings.get("frequency_max_sec") or 70)
    except (TypeError, ValueError):
        frequency_min, frequency_max = 50, 70
    frequency_text = f"{frequency_min} 秒" if frequency_min == frequency_max else f"{frequency_min}-{frequency_max} 秒"

    def button(label, data, color="#1E88E5", style="primary"):
        return {
            "type": "button",
            "style": style,
            "height": "sm",
            "color": color,
            "action": {
                "type": "postback",
                "label": label,
                "data": data,
                "displayText": label,
            },
        }

    area_buttons = []
    for area_id in (127, 128, 126,124):
        selected = area_id in area_ids
        area_buttons.append(button(
            f"{'✓ ' if selected else ''}{area_options.get(area_id, area_id)}",
            f"action=55688_area_toggle&area={area_id}",
            color="#0BBF4C" if selected else "#D9DEE8",
            style="primary" if selected else "secondary",
        ))

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F6C103",
            "paddingAll": "16px",
            "contents": [
                _create_55688_logo_header("55688 監控設定", "admin only"),
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "狀態", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": active_text, "size": "sm", "color": active_color, "weight": "bold", "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "門檻", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": f"NT$ {settings.get('min_fare')}", "size": "sm", "color": "#222222", "weight": "bold", "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "區域", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": area_text, "size": "sm", "color": "#222222", "wrap": True, "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "日期", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": date_text, "size": "sm", "color": "#222222", "wrap": True, "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "頻率", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": frequency_text, "size": "sm", "color": "#222222", "wrap": True, "flex": 5},
                ]},
                {"type": "separator"},
                {"type": "text", "text": "門檻快捷", "size": "xs", "color": "#777777"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    button("300", "action=55688_min_fare&value=300"),
                    button("400", "action=55688_min_fare&value=400"),
                    button("500", "action=55688_min_fare&value=500"),
                ]},
                {"type": "text", "text": "區域快捷", "size": "xs", "color": "#777777"},
                {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": area_buttons[:2]},
                    {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": area_buttons[2:]},
                ]},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                button("啟用監控" if not settings.get("active") else "停用監控", "action=55688_active_toggle"),
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    button("全部日期", "action=55688_date_mode&mode=all", color="#5E6C84"),
                    button("今天", "action=55688_date_mode&mode=today", color="#5E6C84"),
                ]},
                button("選擇區域", "action=55688_area_menu", color="#1E88E5"),
                button("立即查詢", "action=55688_manual_check", color="#0BBF4C"),
            ],
        },
    }
    return FlexSendMessage(alt_text="55688 監控設定", contents=bubble)


def create_55688_area_settings_flex(settings, area_options):
    selected_ids = set(settings.get("areas") or [])

    def area_button(area_id, area_name):
        selected = area_id in selected_ids
        return {
            "type": "button",
            "style": "primary" if selected else "secondary",
            "height": "sm",
            "color": "#0BBF4C" if selected else "#E4E8F0",
            "action": {
                "type": "postback",
                "label": f"{'✓ ' if selected else ''}{area_name}",
                "data": f"action=55688_area_toggle&area={area_id}",
                "displayText": f"{'取消' if selected else '加入'} {area_name}",
            },
        }

    area_items = list(area_options.items())
    bubbles = []
    for index in range(0, len(area_items), 8):
        chunk = area_items[index:index + 8]
        bubbles.append({
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F6C103",
                "paddingAll": "14px",
                "contents": [
                    _create_55688_logo_header("選擇監控區域", "新北市預約任務區域", title_size="md"),
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [area_button(area_id, area_name) for area_id, area_name in chunk],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#5E6C84",
                    "action": {
                        "type": "postback",
                        "label": "返回設定",
                        "data": "action=55688_settings",
                        "displayText": "55688設定",
                    },
                }],
            },
        })

    return FlexSendMessage(
        alt_text="55688 區域設定",
        contents={"type": "carousel", "contents": bubbles},
    )


def _format_taxigo_driver_route_label(job):
    pickup_area = _extract_taiwan_district(job.get("start_address"))
    dropoff_area = _extract_taiwan_district(job.get("end_address"))
    if pickup_area != "-" and dropoff_area != "-":
        return f"{pickup_area} → {dropoff_area}"
    return "LINE GO 預約任務"


def _format_taxigo_driver_fare(job):
    fares = (job.get("estimate") or {}).get("fare_range") or []
    if not fares:
        return "-"
    return str(fares[0])


def create_taxigo_driver_reservation_flex(jobs, title="LINE GO 預約單", subtitle="driver open reservations"):
    if not jobs:
        return TextSendMessage(text="LINE GO 預約單\n目前沒有可顯示的資料。")

    bubbles = []
    for job in jobs[:10]:
        fare_label = _format_taxigo_driver_fare(job)
        route_label = _format_taxigo_driver_route_label(job)
        rows = [
            ("單號", job.get("trip_id") or "-"),
            ("短碼", job.get("trip_hash") or "-"),
            ("預約時間", job.get("reserveTimeText") or "-"),
            ("預估車資", f"NT$ {fare_label}"),
            ("狀態", job.get("trip_status") or "-"),
            ("類型", job.get("trip_type") or "-"),
            ("付款", job.get("payment_method") or "-"),
            ("乘客", ((job.get("user") or {}).get("first_name") or "-")),
        ]
        detail_contents = []
        for label, value in rows:
            detail_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "contents": [
                    {"type": "text", "text": label, "size": "xs", "color": "#7A7A7A", "flex": 3},
                    {"type": "text", "text": str(value), "size": "xs", "color": "#222222", "wrap": True, "flex": 7},
                ],
            })

        body_contents = [
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {"type": "text", "text": "上車地點", "size": "xs", "color": "#888888"},
                    {"type": "text", "text": job.get("start_address") or "-", "size": "sm", "wrap": True, "weight": "bold"},
                ],
            },
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {"type": "text", "text": "下車地點", "size": "xs", "color": "#888888"},
                    {"type": "text", "text": job.get("end_address") or "-", "size": "sm", "wrap": True, "weight": "bold"},
                ],
            },
            {"type": "separator"},
            {"type": "box", "layout": "vertical", "contents": detail_contents},
        ]
        notes = str(job.get("notes") or "").strip()
        if notes:
            body_contents.extend([
                {"type": "separator"},
                {"type": "text", "text": notes, "size": "xs", "color": "#555555", "wrap": True},
            ])

        bubbles.append({
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#08BF5B",
                "paddingAll": "16px",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg", "color": "#FFFFFF", "wrap": True},
                    {"type": "text", "text": f"{route_label}｜NT$ {fare_label}", "size": "xs", "color": "#E9FFF1", "margin": "xs", "wrap": True},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": body_contents,
            },
        })

    first_job = jobs[0]
    return FlexSendMessage(
        alt_text=f"LINE GO 預約單｜{_format_taxigo_driver_route_label(first_job)}｜NT$ {_format_taxigo_driver_fare(first_job)}",
        contents={"type": "carousel", "contents": bubbles},
    )


def create_taxigo_driver_settings_flex(settings):
    active_text = "啟用中" if settings.get("active") else "已停用"
    active_color = "#0BBF4C" if settings.get("active") else "#999999"
    airport_only_text = "只抓機場單" if settings.get("airport_only") else "不限"
    airport_only_color = "#0BBF4C" if settings.get("airport_only") else "#666666"

    def button(label, data, color="#1E88E5", style="primary"):
        return {
            "type": "button",
            "style": style,
            "height": "sm",
            "color": color,
            "action": {
                "type": "postback",
                "label": label,
                "data": data,
                "displayText": label,
            },
        }

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#08BF5B",
            "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": "LINE GO 預約監控", "weight": "bold", "size": "lg", "color": "#FFFFFF"},
                {"type": "text", "text": "admin only", "size": "xs", "color": "#E9FFF1", "margin": "xs"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "狀態", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": active_text, "size": "sm", "color": active_color, "weight": "bold", "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "門檻", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": f"NT$ {settings.get('min_fare')}", "size": "sm", "color": "#222222", "weight": "bold", "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "機場單", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": airport_only_text, "size": "sm", "color": airport_only_color, "weight": "bold", "flex": 5},
                ]},
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "頻率", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": "50-70 秒", "size": "sm", "color": "#222222", "wrap": True, "flex": 5},
                ]},
                {"type": "separator"},
                {"type": "text", "text": "門檻快捷", "size": "xs", "color": "#777777"},
                {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                    button("500", "action=taxigo_driver_min_fare&value=500"),
                    button("600", "action=taxigo_driver_min_fare&value=600"),
                    button("800", "action=taxigo_driver_min_fare&value=800"),
                ]},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                button("啟用監控" if not settings.get("active") else "停用監控", "action=taxigo_driver_active_toggle"),
                button("取消只抓機場單" if settings.get("airport_only") else "只抓機場單", "action=taxigo_driver_airport_toggle", color="#00A86B"),
                button("立即查詢", "action=taxigo_driver_manual_check", color="#0BBF4C"),
            ],
        },
    }
    return FlexSendMessage(alt_text="LINE GO 預約監控設定", contents=bubble)


def _short_place(location):
    text = location.get("address") or location.get("title") or "位置"
    return text[:24] + "..." if len(text) > 24 else text


# --- 3. 航班查詢卡片 ---
def create_flight_region_flex(regions, role, include_taiwan_shortcut=False):
    role_text = "出發地" if role == "depart" else "目的地"
    bubbles = []
    if include_taiwan_shortcut:
        bubbles.append({
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0BBF4C",
                "contents": [
                    {"type": "text", "text": "台灣", "weight": "bold", "size": "lg", "color": "#ffffff"},
                    {"type": "text", "text": "常用起點", "size": "xxs", "color": "#E7FFF0"},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "快速選擇台北出發", "size": "sm", "wrap": True, "color": "#444444"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#0BBF4C",
                    "action": {
                        "type": "postback",
                        "label": "台北 TPE",
                        "data": f"action=flight_select_city&role={role}&code=TPE",
                        "displayText": "台北 TPE",
                    },
                }],
            },
        })

    for region in regions:
        bubbles.append({
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1F2937",
                "contents": [
                    {"type": "text", "text": region["name"], "weight": "bold", "size": "lg", "color": "#ffffff"},
                    {"type": "text", "text": f"選擇{role_text}", "size": "xxs", "color": "#d1d5db"},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"查看{region['name']}熱門國家/城市", "size": "sm", "wrap": True, "color": "#444444"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#2563EB",
                    "action": {
                        "type": "postback",
                        "label": "選擇",
                        "data": f"action=flight_select_region&role={role}&region={region['code']}",
                        "displayText": f"選擇{region['name']}",
                    },
                }],
            },
        })
    return FlexSendMessage(alt_text=f"選擇航班{role_text}洲別", contents={"type": "carousel", "contents": bubbles[:12]})


def create_flight_city_flex(cities, role, region_name):
    role_text = "出發地" if role == "depart" else "目的地"
    bubbles = []
    for city in cities[:12]:
        bubbles.append({
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F3F4F6",
                "contents": [
                    {"type": "text", "text": city["country"], "weight": "bold", "size": "sm", "color": "#111111"},
                    {"type": "text", "text": region_name, "size": "xxs", "color": "#777777"},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {"type": "text", "text": city["name"], "weight": "bold", "size": "lg", "color": "#111111"},
                    {"type": "text", "text": city["code"], "size": "sm", "color": "#2563EB"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [{
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#2563EB",
                    "action": {
                        "type": "postback",
                        "label": "選擇",
                        "data": f"action=flight_select_city&role={role}&code={city['code']}",
                        "displayText": f"{role_text}：{city['name']}",
                    },
                }],
            },
        })
    return FlexSendMessage(alt_text=f"選擇航班{role_text}", contents={"type": "carousel", "contents": bubbles})


def create_flight_result_flex(result, page=0, page_size=4, filter_type="active"):
    depart = result["depart"]
    arrive = result["arrive"]
    all_flights = result.get("flights", [])
    show_arrived = filter_type == "arrived"
    flights = [item for item in all_flights if _is_flight_arrived(item) == show_arrived]
    filter_label = "已抵達" if show_arrived else "尚未抵達"
    chunks = [flights[i:i + page_size] for i in range(0, len(flights), page_size)]
    bubbles = []
    total_pages = max(1, len(chunks))

    for chunk_index, page_flights in enumerate(chunks[:11]):
        rows = []
        for item in page_flights:
            flight = item.get("varItemInfo") or item
            status = flight.get("srak") or item.get("srak") or ""
            scheduled_depart = flight.get("dpDate") or flight.get("dTime") or ""
            actual_depart = flight.get("deDate") or flight.get("daDate") or flight.get("edTime") or scheduled_depart
            scheduled_arrive = flight.get("apDate") or flight.get("aTime") or ""
            actual_arrive = flight.get("aaDate") or flight.get("aeDate") or scheduled_arrive
            depart_text = _format_flight_time_line("起飛", actual_depart, scheduled_depart)
            arrive_text = _format_flight_time_line(
                "落地",
                actual_arrive,
                scheduled_arrive,
                is_actual_available=bool(flight.get("aaDate") or flight.get("aeDate")),
            )
            airline = flight.get("airlineName") or flight.get("airlineCode") or "未知航空"
            flight_no = flight.get("fltNo") or flight.get("fno") or "-"
            depart_code = flight.get("dpcode") or flight.get("dcode") or depart["code"]
            arrival_code = flight.get("apcode") or flight.get("acode") or arrive["code"]
            depart_airport = _format_airport_terminal(
                flight.get("dAirportShortName") or flight.get("dpname") or depart["name"] or depart_code,
                flight.get("dTerminal"),
            )
            arrival_airport = _format_airport_terminal(
                flight.get("aAirportShortName") or flight.get("apname") or arrive["name"] or arrival_code,
                flight.get("aTerminal"),
            )
            status_content = _clean_flight_status_text(flight.get("statusContent") or "")
            is_delayed = _is_flight_delayed(flight, status_content)
            status_color = "#E53935" if is_delayed else ("#0BBF4C" if status == "已抵達" else "#F59E0B")
            flight_contents = [
                {
                    "type": "box",
                    "layout": "baseline",
                    "spacing": "sm",
                    "contents": [
                        {"type": "text", "text": flight_no, "size": "sm", "weight": "bold", "flex": 2, "color": "#111111", "wrap": True},
                        {"type": "text", "text": airline, "size": "xs", "flex": 4, "color": "#444444", "wrap": True},
                    ],
                },
            ]
            if status:
                flight_contents.append({"type": "text", "text": status, "size": "xs", "color": status_color, "wrap": True})
            flight_contents.extend([
                {"type": "text", "text": f"{depart_text}（{depart_airport}）", "size": "xs", "color": "#666666", "wrap": True},
                {"type": "text", "text": f"{arrive_text}（{arrival_airport}）", "size": "xs", "color": "#666666", "wrap": True},
            ])
            if status_content:
                flight_contents.append({
                    "type": "text",
                    "text": status_content,
                    "size": "xxs",
                    "color": "#E53935" if is_delayed else "#888888",
                    "wrap": True,
                })
            rows.append({
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "paddingBottom": "8px",
                "contents": flight_contents,
            })
            rows.append({"type": "separator", "color": "#E5E7EB"})

        bubbles.append({
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#111827",
                "contents": [
                    {"type": "text", "text": "航班查詢", "weight": "bold", "size": "lg", "color": "#ffffff"},
                    {"type": "text", "text": f"{depart['name']} {depart['code']} → {arrive['name']} {arrive['code']}", "size": "xs", "color": "#E5E7EB", "margin": "xs", "wrap": True},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"日期：{result['date']}，{filter_label} {len(flights)}/{len(all_flights)} 筆，第 {chunk_index + 1}/{total_pages} 張", "size": "xs", "color": "#777777", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "vertical", "spacing": "sm", "contents": rows},
                    {"type": "text", "text": "資料來源：由第三方供應商所提供。如需最新資訊，請聯繫航空公司或機場。", "size": "xxs", "color": "#999999", "margin": "md", "wrap": True},
                ],
            },
        })

    if not bubbles:
        bubbles.append({
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#111827",
                "contents": [
                    {"type": "text", "text": "航班查詢", "weight": "bold", "size": "lg", "color": "#ffffff"},
                    {"type": "text", "text": f"{depart['name']} {depart['code']} → {arrive['name']} {arrive['code']}", "size": "xs", "color": "#E5E7EB", "margin": "xs", "wrap": True},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"目前沒有{filter_label}的航班。", "size": "sm", "color": "#777777", "wrap": True},
                    {"type": "text", "text": "資料來源：由第三方供應商所提供。如需最新資訊，請聯繫航空公司或機場。", "size": "xxs", "color": "#999999", "margin": "md", "wrap": True},
                ],
            },
        })

    next_filter = "active" if show_arrived else "arrived"
    toggle_label = "顯示尚未抵達航班" if show_arrived else "顯示已抵達航班"
    bubbles.append({
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F3F4F6",
            "contents": [
                {"type": "text", "text": "航班篩選", "weight": "bold", "size": "lg", "color": "#111111"},
                {"type": "text", "text": f"{filter_label} {len(flights)}/{len(all_flights)} 筆", "size": "xs", "color": "#666666", "wrap": True, "margin": "xs"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": f"{depart['name']} {depart['code']} → {arrive['name']} {arrive['code']}", "size": "sm", "color": "#555555", "wrap": True},
                {"type": "text", "text": f"日期：{result['date']}", "size": "sm", "color": "#777777", "wrap": True},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [{
                "type": "button",
                "style": "secondary",
                "height": "sm",
                "action": {
                    "type": "postback",
                    "label": toggle_label,
                    "data": f"action=flight_result_filter&filter={next_filter}",
                    "displayText": toggle_label,
                },
            }],
        },
    })

    return FlexSendMessage(alt_text="航班查詢結果", contents={"type": "carousel", "contents": bubbles[:12]})


def _is_flight_arrived(item):
    flight = item.get("varItemInfo") or item
    status = flight.get("srak") or item.get("srak") or ""
    return status == "已抵達"


def _format_airport_terminal(airport_name, terminal):
    airport_name = (airport_name or "").strip()
    terminal = (terminal or "").strip()
    if airport_name and terminal:
        return f"{airport_name} {terminal}"
    return airport_name or terminal or "-"


def _clean_flight_status_text(text):
    if not text:
        return ""
    text = str(text).replace("&nbsp;", " ")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[^>]+>", "", text)
    return " ".join(text.split())


def _is_flight_delayed(flight, status_content):
    status_text = f"{flight.get('srak') or ''} {flight.get('statusContent') or ''} {status_content}"
    delay_keywords = ("延誤", "延遲", "誤點", "晚到", "晚起飛", "delay", "delayed")
    if any(keyword in status_text.lower() for keyword in delay_keywords):
        return True
    scheduled_depart = _flight_hhmm(flight.get("dpDate") or flight.get("dTime") or "")
    actual_depart = _flight_hhmm(flight.get("deDate") or flight.get("daDate") or flight.get("edTime") or "")
    scheduled_arrive = _flight_hhmm(flight.get("apDate") or flight.get("aTime") or "")
    actual_arrive = _flight_hhmm(flight.get("aaDate") or flight.get("aeDate") or "")
    return (
        scheduled_depart != "-"
        and actual_depart != "-"
        and actual_depart > scheduled_depart
    ) or (
        scheduled_arrive != "-"
        and actual_arrive != "-"
        and actual_arrive > scheduled_arrive
    )


def _flight_hhmm(value):
    if not value:
        return "-"
    return value[11:16] if len(value) >= 16 else value


def _format_flight_time_line(label, actual_value, scheduled_value, is_actual_available=True):
    actual_text = _flight_hhmm(actual_value)
    scheduled_text = _flight_hhmm(scheduled_value)
    if not is_actual_available and scheduled_text != "-":
        return f"{label}：{scheduled_text}（表定）"
    if scheduled_text != "-" and actual_text != scheduled_text:
        return f"{label}：{actual_text}（表定 {scheduled_text}）"
    return f"{label}：{actual_text}"


# --- 3. VIP 管理卡片 ---
def create_vip_list_flex(vip_users, admin_line_id=""):
    bubbles = []
    sorted_users = sorted(
        vip_users,
        key=lambda row: (
            0 if row.get("line_id") == admin_line_id else 1,
            row.get("created_at") or "",
        ),
    )
    for row in sorted_users:
        line_id = row.get("line_id", "")
        display_name = row.get("display_name") or "未命名用戶"
        note = row.get("note") or ""
        is_active = bool(row.get("is_active"))
        is_admin = line_id == admin_line_id
        status_text = "管理員 / 固定啟用" if is_admin else ("啟用中" if is_active else "已停用")
        status_color = "#0BBF4C" if (is_active or is_admin) else "#999999"

        footer_contents = []
        if not is_admin:
            next_active = "0" if is_active else "1"
            toggle_label = "停用 VIP" if is_active else "啟用 VIP"
            toggle_color = "#F5A623" if is_active else "#0BBF4C"
            footer_contents.extend([
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": toggle_color,
                    "action": {
                        "type": "postback",
                        "label": toggle_label,
                        "data": f"action=vip_toggle&line_id={line_id}&active={next_active}",
                        "displayText": toggle_label,
                    },
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "color": "#FF3333",
                    "action": {
                        "type": "postback",
                        "label": "刪除 VIP",
                        "data": f"action=vip_delete&line_id={line_id}",
                        "displayText": "刪除 VIP",
                    },
                },
            ])
        else:
            footer_contents.append({
                "type": "text",
                "text": "管理員帳號不可停用或刪除",
                "size": "xs",
                "color": "#777777",
                "align": "center",
            })

        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#111111" if is_admin else "#0BBF4C",
                "paddingAll": "14px",
                "contents": [
                    {"type": "text", "text": display_name, "weight": "bold", "size": "lg", "color": "#ffffff", "wrap": True},
                    {"type": "text", "text": status_text, "size": "xs", "color": "#ffffff", "margin": "xs"},
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "LINE ID", "size": "xxs", "color": "#999999"},
                    {"type": "text", "text": line_id, "size": "xs", "color": "#333333", "wrap": True},
                    {"type": "separator", "margin": "md"},
                    {"type": "box", "layout": "baseline", "contents": [
                        {"type": "text", "text": "狀態", "size": "sm", "color": "#666666", "flex": 2},
                        {"type": "text", "text": status_text, "size": "sm", "color": status_color, "weight": "bold", "flex": 5},
                    ]},
                    {"type": "box", "layout": "baseline", "contents": [
                        {"type": "text", "text": "備註", "size": "sm", "color": "#666666", "flex": 2},
                        {"type": "text", "text": note or "-", "size": "sm", "color": "#333333", "wrap": True, "flex": 5},
                    ]},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": footer_contents,
            },
        }
        bubbles.append(bubble)

    if not bubbles:
        bubbles.append({
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "VIP 名單", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": "目前沒有 VIP 資料。", "size": "sm", "color": "#666666", "margin": "md"},
                ],
            },
        })

    return FlexSendMessage(alt_text="VIP 管理名單", contents={"type": "carousel", "contents": bubbles})


# --- 4. 會員申請審核卡片 ---
def create_vip_request_flex(display_name, line_id, member_type="vip"):
    display_name = display_name or "未命名用戶"
    is_vip = member_type == "vip"
    title = "VIP 申請" if is_vip else "一般會員申請"
    approve_label = "核准 VIP" if is_vip else "核准一般會員"
    reject_display = "拒絕 VIP" if is_vip else "拒絕一般會員"
    action_prefix = "vip" if is_vip else "member"
    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#111111",
            "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "lg", "color": "#ffffff"},
                {"type": "text", "text": "待管理員審核", "size": "xs", "color": "#dddddd", "margin": "xs"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {"type": "box", "layout": "baseline", "contents": [
                    {"type": "text", "text": "名稱", "size": "sm", "color": "#666666", "flex": 2},
                    {"type": "text", "text": display_name, "size": "sm", "color": "#111111", "weight": "bold", "wrap": True, "flex": 5},
                ]},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "LINE ID", "size": "xxs", "color": "#999999", "margin": "md"},
                {"type": "text", "text": line_id, "size": "xs", "color": "#333333", "wrap": True},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "color": "#0BBF4C",
                    "action": {
                        "type": "postback",
                        "label": approve_label,
                        "data": f"action={action_prefix}_approve&line_id={line_id}",
                        "displayText": approve_label,
                    },
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "color": "#FF3333",
                    "action": {
                        "type": "postback",
                        "label": "拒絕",
                        "data": f"action={action_prefix}_reject&line_id={line_id}",
                        "displayText": reject_display,
                    },
                },
            ],
        },
    }
    return FlexSendMessage(alt_text=f"{title}審核", contents=bubble)


# --- 5. 車輛列表卡片 (檢視 / 刪除 / 編輯模式) ---
def create_car_list_flex(cars, mode='view'):
    """
    mode='view': 純查看
    mode='delete': 顯示紅色刪除按鈕
    mode='edit': 顯示橘色編輯按鈕
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
                    {"type": "text", "text": f"{sub_label}: {car['sub_id']}", "size": "xs", "wrap": True},
                ] + (
                    [{"type": "text", "text": f"車牌: {car['plate_no'] or '未設定'}", "size": "xs", "wrap": True}] 
                    if car['mode'] == 'personal' else []
                )
            }
        }

        if mode in ('view', 'delete', 'edit'):
            is_delete = mode == 'delete'
            btn_color = "#FF3333" if is_delete else "#F5A623"
            btn_label = "刪除此車" if is_delete else "編輯此車"
            post_action = "delete_car" if is_delete else "edit_car"
            display_text = f"我要刪除 {car['name']}" if is_delete else f"我要編輯 {car['name']}"
            bubble["footer"] = {
                "type": "box", "layout": "vertical",
                "contents": [
                    {
                        "type": "button", "style": "secondary", "height": "sm", "color": btn_color,
                        "action": {
                            "type": "postback", "label": btn_label,
                            "data": f"action={post_action}&car_id={car['db_id']}&car_name={car['name']}",
                            "displayText": display_text
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
def create_fine_flex_message(record_data, id_number, image_urls, analysis_key=None):
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
                    {"type": "button", "style": "secondary", "height": "sm", "color": "#00b900", "action": {"type": "postback", "label": "🤖 AI 申訴評估", "data": f"action=ai_analyze&key={analysis_key or tkt_no}", "displayText": f"請幫我分析這張罰單{tkt_no}能否申訴"}}
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
