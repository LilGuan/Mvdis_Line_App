import json
import mimetypes
from pathlib import Path
import requests

CHANNEL_ACCESS_TOKEN = "nX1N//BjGiFlpVcWboFDHEv36yht1xsXHe95cjSLMkEk0jLGdy9GMEL12bm50Mi6CW8DHR02VJ7QDTPiLQ7pzYLsGH85Z1eV2zqUMtjzFjK3tVi+GZ2uBE95+bF+eXbOkYszMMDolrHjt6ptgXkZqwdB04t89/1O/w1cDnyilFU="

API_BASE = "https://api.line.me/v2/bot"
DATA_API_BASE = "https://api-data.line.me/v2/bot"

headers_json = {
    "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}
headers_auth = {
    "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
}

ROOT = Path(__file__).resolve().parent

MENUS = [
        {
        "alias": "menu-activity",
        "name": "Ticket",
        "chatBarText": "功能選單",
        "image": ROOT / "richmenu_activity_template.jpg",
        "areas": [
            {"bounds": {"x": 0, "y": 0, "width": 833, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-activity", "data": "action=switch_activity"}},
            {"bounds": {"x": 833, "y": 0, "width": 834, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-query", "data": "action=switch_query"}},
            {"bounds": {"x": 1667, "y": 0, "width": 833, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-points", "data": "action=switch_points"}},
            {"bounds": {"x": 0, "y": 190, "width": 2500, "height": 500}, "action": {"type": "message", "text": "罰單查詢"}},
            {"bounds": {"x": 70, "y": 690, "width": 760, "height": 780}, "action": {"type": "message", "text": "綁定車輛"}},
            {"bounds": {"x": 870, "y": 690, "width": 760, "height": 780}, "action": {"type": "message", "text": "清除車輛"}},
            {"bounds": {"x": 1670, "y": 690, "width": 760, "height": 780}, "action": {"type": "message", "text": "查詢車輛"}}
        ]
    },
    {
        "alias": "menu-query",
        "name": "Query",
        "chatBarText": "功能選單",
        "image": ROOT / "richmenu_query_template.jpg",
        "areas": [
            {"bounds": {"x": 0, "y": 0, "width": 833, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-activity", "data": "action=switch_activity"}},
            {"bounds": {"x": 833, "y": 0, "width": 834, "height": 190}, "action": {"type": "postback", "data": "noop=query"}},
            {"bounds": {"x": 1667, "y": 0, "width": 833, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-points", "data": "action=switch_points"}},

            {"bounds": {"x": 0, "y": 190, "width": 2500, "height": 1496}, "action": {"type": "message", "text": "計程車免費車位查詢"}}
        ]
    },
    {
        "alias": "menu-points",
        "name": "Points",
        "chatBarText": "功能選單",
        "image": ROOT / "richmenu_other_template.jpg",
        "areas": [
            {"bounds": {"x": 0, "y": 0, "width": 833, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-activity", "data": "action=switch_activity"}},
            {"bounds": {"x": 833, "y": 0, "width": 834, "height": 190}, "action": {"type": "richmenuswitch", "richMenuAliasId": "menu-query", "data": "action=switch_query"}},
            {"bounds": {"x": 1667, "y": 0, "width": 833, "height": 190}, "action": {"type": "postback", "data": "noop=points"}},
            {"bounds": {"x": 70, "y": 690, "width": 760, "height": 780}, "action": {"type": "uri", "uri": "https://example.com/points-balance"}},
            {"bounds": {"x": 870, "y": 690, "width": 760, "height": 780}, "action": {"type": "uri", "uri": "https://example.com/redeem"}},
            {"bounds": {"x": 1670, "y": 690, "width": 760, "height": 780}, "action": {"type": "uri", "uri": "https://example.com/points-history"}}
        ]
    },
]
def get_alias_list():
    resp = requests.get(f"{API_BASE}/richmenu/alias/list", headers=headers_auth, timeout=30)
    resp.raise_for_status()
    return resp.json()

def alias_exists(alias_id):
    data = get_alias_list()
    for item in data.get("aliases", []):
        if item.get("richMenuAliasId") == alias_id:
            return True
    return False

def create_or_update_alias(alias_id, rich_menu_id):
    if alias_exists(alias_id):
        resp = requests.post(
            f"{API_BASE}/richmenu/alias/{alias_id}",
            headers=headers_json,
            json={"richMenuId": rich_menu_id},
            timeout=30,
        )
    else:
        resp = requests.post(
            f"{API_BASE}/richmenu/alias",
            headers=headers_json,
            json={
                "richMenuAliasId": alias_id,
                "richMenuId": rich_menu_id,
            },
            timeout=30,
        )

    print(resp.status_code, resp.text)
    resp.raise_for_status()
def create_rich_menu(menu):
    payload = {
        "size": {"width": 2500, "height": 1686},
        "selected": False,
        "name": menu["name"],
        "chatBarText": menu["chatBarText"],
        "areas": menu["areas"],
    }
    resp = requests.post(f"{API_BASE}/richmenu", headers=headers_json, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["richMenuId"]

def upload_image(rich_menu_id, image_path: Path):
    mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": mime,
    }
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{DATA_API_BASE}/richmenu/{rich_menu_id}/content",
            headers=headers,
            data=f,
            timeout=60,
        )
    print(resp.status_code, resp.text)
    resp.raise_for_status()

def create_alias(alias_id, rich_menu_id):
    payload = {
        "richMenuAliasId": alias_id,
        "richMenuId": rich_menu_id,
    }
    resp = requests.post(f"{API_BASE}/richmenu/alias", headers=headers_json, json=payload, timeout=30)
    resp.raise_for_status()

def set_default(rich_menu_id):
    resp = requests.post(f"{API_BASE}/user/all/richmenu/{rich_menu_id}", headers=headers_auth, timeout=30)
    resp.raise_for_status()

def main():
    created = []
    for menu in MENUS:
        rich_menu_id = create_rich_menu(menu)
        upload_image(rich_menu_id, menu["image"])
        create_or_update_alias(menu["alias"], rich_menu_id)
        created.append((menu["alias"], rich_menu_id))
        print(f"created: {menu['alias']} -> {rich_menu_id}")

    # 將第一張設成預設 rich menu
    set_default(created[0][1])
    print(f"default set: {created[0][0]}")

if __name__ == "__main__":
    main()
