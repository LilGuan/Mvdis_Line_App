from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 請填入你的 LINE Channel 資訊
LINE_ACCESS_TOKEN = "nX1N//BjGiFlpVcWboFDHEv36yht1xsXHe95cjSLMkEk0jLGdy9GMEL12bm50Mi6CW8DHR02VJ7QDTPiLQ7pzYLsGH85Z1eV2zqUMtjzFjK3tVi+GZ2uBE95+bF+eXbOkYszMMDolrHjt6ptgXkZqwdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "06b0ec3c7c42162197cf6c7e17b1eddd"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 取得 ID
    user_id = event.source.user_id
    group_id = getattr(event.source, "group_id", None)
    
    print("="*30)
    if group_id:
        print(f"【成功抓到群組 ID】: {group_id}")
        reply_msg = f"此群組的 ID 是：\n{group_id}"
    else:
        print(f"這是個人 ID: {user_id}")
        reply_msg = f"這是個人 ID，請在群組測試。\n{user_id}"
    print("="*30)

    # 回傳給 LINE 讓你知道有沒有成功
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_msg)
    )

if __name__ == "__main__":
    app.run(port=5000)