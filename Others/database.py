import os
from supabase import create_client, Client

class TaxiDB:
    def __init__(self):
        # 這些資訊在 Supabase 後台的 Project Settings -> API 可以找到
        url = "你的_SUPABASE_URL"
        key = "你的_SUPABASE_ANON_KEY"
        self.supabase: Client = create_client(url, key)

    # --- 使用者相關 ---
    def check_user(self, user_id, display_name):
        """檢查使用者是否存在，不存在就建立"""
        res = self.supabase.table("users").select("*").eq("user_id", user_id).execute()
        if not res.data:
            self.supabase.table("users").insert({
                "user_id": user_id,
                "display_name": display_name
            }).execute()

    # --- 罰單相關 ---
    def log_search(self, user_id, plate_number):
        """紀錄查詢歷史"""
        self.supabase.table("search_logs").insert({
            "user_id": user_id,
            "plate_number": plate_number
        }).execute()

    # --- 停車場相關 ---
    def get_all_parking(self):
        """抓取所有停車場資料 (用來在 Python 計算距離)"""
        res = self.supabase.table("parking_lots").select("*").execute()
        return res.data

    def import_parking_from_json(self, json_data):
        """將 JSON 資料批次匯入資料庫 (只需跑一次)"""
        self.supabase.table("parking_lots").insert(json_data).execute()