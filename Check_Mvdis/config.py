import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+")
warnings.filterwarnings("ignore", message=r"Call to deprecated class .*", module=r"linebot\..*")

import urllib3
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import LineBotSdkDeprecatedIn30
from supabase import create_client
import PIL.Image

warnings.filterwarnings("ignore", category=LineBotSdkDeprecatedIn30)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 修正 Pillow 相容性
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# 金鑰讀取
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '').strip()
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')
MV_DIS_URL = os.getenv('MV_DIS_URL')
DEFAULT_HERO_IMAGE = os.getenv('DEFAULT_HERO_IMAGE')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SE_GRID_URL = os.getenv('SE_GRID_URL')
ADMIN_UUID = os.getenv('Admin_uuid', 'Uc033d76e142adb971941e27cd685856f').strip()
NORMAL_DAILY_QUERY_LIMIT = int(os.getenv('NORMAL_DAILY_QUERY_LIMIT', '5'))
QUERY_USAGE_RESET_HOUR = int(os.getenv('QUERY_USAGE_RESET_HOUR', '8'))
NORMAL_MAX_CARS = int(os.getenv('NORMAL_MAX_CARS', '1'))

# Ride compare session tokens
UBER_COOKIE = os.getenv('UBER_COOKIE', '').strip()
UBER_COOKIE_SID = os.getenv('UBER_COOKIE_SID', '').strip()
UBER_COOKIE_CSID = os.getenv('UBER_COOKIE_CSID', '').strip()
UBER_PAYMENT_PROFILE_UUID = os.getenv('UBER_PAYMENT_PROFILE_UUID', '').strip()
TAXIGO_COOKIE = os.getenv('TAXIGO_COOKIE', '').strip()
TAXIGO_TOKEN = os.getenv('TAXIGO_TOKEN', '').strip()
TAXIGO_BILLING_TOKEN = os.getenv('TAXIGO_BILLING_TOKEN', '').strip()
TAXIGO_DRIVER_JWT = os.getenv('TAXIGO_DRIVER_JWT', '').strip()
TAXIGO_DRIVER_UUID = os.getenv('TAXIGO_DRIVER_UUID', '').strip()
TAXIGO_DRIVER_APP_VERSION = os.getenv('TAXIGO_DRIVER_APP_VERSION', '6.55.0').strip()
TAXIGO_DRIVER_BUILD_NUMBER = os.getenv('TAXIGO_DRIVER_BUILD_NUMBER', '2559').strip()
TAXIGO_DRIVER_USER_AGENT = os.getenv(
    'TAXIGO_DRIVER_USER_AGENT',
    'Driver iOS-27.0, iPhone16,2'
).strip()
TAIWANTAXI_PREPARE_URL = os.getenv('TAIWANTAXI_PREPARE_URL', '').strip()
TAIWANTAXI_ESTIMATE_URL = os.getenv('TAIWANTAXI_ESTIMATE_URL', '').strip()
TAIWANTAXI_GIS_REVERSE_URL = os.getenv('TAIWANTAXI_GIS_REVERSE_URL', '').strip()
TAIWANTAXI_GOOGLE_PLACE_DETAILS_URL = os.getenv('TAIWANTAXI_GOOGLE_PLACE_DETAILS_URL', '').strip()
TAIWANTAXI_USER_ID = os.getenv('TAIWANTAXI_USER_ID', '').strip()
TAIWANTAXI_ACCESS_TOKEN = os.getenv('TAIWANTAXI_ACCESS_TOKEN', '').strip()
TAIWANTAXI_SIGNATURE = os.getenv('TAIWANTAXI_SIGNATURE', '').strip()
TAIWANTAXI_GIS_SIGNATURE = os.getenv('TAIWANTAXI_GIS_SIGNATURE', '').strip()
TAIWANTAXI_GOOGLE_PLACE_SIGNATURE = os.getenv('TAIWANTAXI_GOOGLE_PLACE_SIGNATURE', '').strip()
TAIWANTAXI_TIME = os.getenv('TAIWANTAXI_TIME', '').strip()

TAIWANTAXI_DISPATCH_TOKEN = os.getenv('TAIWANTAXI_DISPATCH_TOKEN', '').strip()
TAIWANTAXI_55688_LOGO_URL = os.getenv(
    'TAIWANTAXI_55688_LOGO_URL',
    'https://i.ibb.co/206mVQSy/Chat-GPT-Image-2026-7-2-01-06-51.png'
).strip()

try:
    TAIWANTAXI_MEM_SN = int(os.getenv('TAIWANTAXI_MEM_SN', '59783'))
except ValueError:
    TAIWANTAXI_MEM_SN = 59783

try:
    TAIWANTAXI_SELECTED_AREAS = [
        int(value.strip())
        for value in os.getenv('TAIWANTAXI_SELECTED_AREAS', '127,128').split(',')
        if value.strip()
    ]
except ValueError:
    TAIWANTAXI_SELECTED_AREAS = [127, 128]

TAIWANTAXI_RESERVATION_MONITOR_ENABLED = os.getenv(
    'TAIWANTAXI_RESERVATION_MONITOR_ENABLED',
    'true'
).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
TAIWANTAXI_RESERVATION_QA_MODE = os.getenv(
    'TAIWANTAXI_RESERVATION_QA_MODE',
    'false'
).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

try:
    TAIWANTAXI_RESERVATION_INTERVAL_SEC = max(
        30,
        int(os.getenv('TAIWANTAXI_RESERVATION_INTERVAL_SEC', '60'))
    )
except ValueError:
    TAIWANTAXI_RESERVATION_INTERVAL_SEC = 60

try:
    TAIWANTAXI_RESERVATION_MIN_FARE = int(os.getenv('TAIWANTAXI_RESERVATION_MIN_FARE', '300'))
except ValueError:
    TAIWANTAXI_RESERVATION_MIN_FARE = 300

TAXIGO_DRIVER_RESERVATION_MONITOR_ENABLED = os.getenv(
    'TAXIGO_DRIVER_RESERVATION_MONITOR_ENABLED',
    'false'
).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
try:
    TAXIGO_DRIVER_RESERVATION_MIN_FARE = int(os.getenv('TAXIGO_DRIVER_RESERVATION_MIN_FARE', '500'))
except ValueError:
    TAXIGO_DRIVER_RESERVATION_MIN_FARE = 500

BOLT_AUTHORIZATION = os.getenv('BOLT_AUTHORIZATION', '').strip()
BOLT_COOKIE = os.getenv('BOLT_COOKIE', '').strip()
BOLT_PAYMENT_METHOD_ID = os.getenv('BOLT_PAYMENT_METHOD_ID', '').strip()
BOLT_PAYMENT_METHOD_TYPE = os.getenv('BOLT_PAYMENT_METHOD_TYPE', 'card').strip()
BOLT_DEVICE_ID = os.getenv('BOLT_DEVICE_ID', '').strip()
BOLT_DEVICE_TYPE = os.getenv('BOLT_DEVICE_TYPE', 'iphone').strip()
BOLT_DEVICE_NAME = os.getenv('BOLT_DEVICE_NAME', 'iPhone').strip()
BOLT_DEVICE_OS_VERSION = os.getenv('BOLT_DEVICE_OS_VERSION', 'iOS').strip()
BOLT_DISTINCT_ID = os.getenv('BOLT_DISTINCT_ID', '').strip()
BOLT_RH_SESSION_ID = os.getenv('BOLT_RH_SESSION_ID', '').strip()
BOLT_SESSION_ID = os.getenv('BOLT_SESSION_ID', '').strip()
BOLT_USER_ID = os.getenv('BOLT_USER_ID', '').strip()
BOLT_VERSION = os.getenv('BOLT_VERSION', 'CI.239.0').strip()
BOLT_BRAND = os.getenv('BOLT_BRAND', 'bolt').strip()
BOLT_COUNTRY = os.getenv('BOLT_COUNTRY', 'tw').strip()
BOLT_LANGUAGE = os.getenv('BOLT_LANGUAGE', 'zh-TW').strip()

# Trip.com flight search
TRIP_GUID = os.getenv('TRIP_GUID', '09034145411409046732').strip()
TRIP_GUID_SIG = os.getenv('TRIP_GUID_SIG', 't3WysHa7tG31Cm1HdUgCAtvOoVj7QyKQsuR6eBmvC_4').strip()
TRIP_CURRENCY = os.getenv('TRIP_CURRENCY', 'HKD').strip()
TRIP_LOCALE = os.getenv('TRIP_LOCALE', 'zh-TW').strip()

# 實例初始化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
