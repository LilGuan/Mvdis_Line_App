import os
import urllib3
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from supabase import create_client
import PIL.Image

load_dotenv()
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
ADMIN_UUID = os.getenv('Admin_uuid')

# 實例初始化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
