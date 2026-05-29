import os
import re
import uuid
import tempfile
import requests
from http.cookiejar import MozillaCookieJar
# pyrefly: ignore [missing-import]
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import yt_dlp

app = Flask(__name__)

cookie_storage = {}

def save_uploaded_cookie(cookie_file):
    if not cookie_file or cookie_file.filename == '':
        return None
    token = str(uuid.uuid4())
    temp_path = os.path.join(tempfile.gettempdir(), f'yt_cookies_{token}.txt')
    cookie_file.save(temp_path)
    cookie_storage[token] = temp_path
    return token


def get_cookie_path(token):
    return cookie_storage.get(token)


def load_cookies_from_file(cookie_path):
    if not cookie_path or not os.path.exists(cookie_path):
        return None
    cookie_jar = MozillaCookieJar()
    try:
        cookie_jar.load(cookie_path, ignore_discard=True, ignore_expires=True)
    except Exception:
        return None
    return requests.utils.cookiejar_from_dict({cookie.name: cookie.value for cookie in cookie_jar})

# Memastikan judul file aman untuk disimpan
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/info', methods=['POST'])
def get_video_info():
    url = None
    cookie_token = None

    if request.is_json:
        data = request.get_json(silent=True) or {}
        url = data.get('url')
    else:
        url = request.form.get('url')
        cookie_file = request.files.get('cookie_file')
        cookie_token = save_uploaded_cookie(cookie_file) if cookie_file else None

    if not url:
        return jsonify({'error': 'URL tidak boleh kosong'}), 400
        
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    if cookie_token:
        cookie_path = get_cookie_path(cookie_token)
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'Video Tanpa Judul')
            thumbnail = info.get('thumbnail') or info.get('thumbnails', [{}])[-1].get('url')
            duration = info.get('duration')
            duration_str = ""
            if duration:
                mins, secs = divmod(duration, 60)
                hours, mins = divmod(mins, 60)
                if hours > 0:
                    duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
                else:
                    duration_str = f"{mins:02d}:{secs:02d}"
            else:
                duration_str = "Unknown"
                
            uploader = info.get('uploader', 'Unknown')
            
            formats_list = []
            seen_resolutions = set()
            
            for f in info.get('formats', []):
                ext = f.get('ext')
                vcodec = f.get('vcodec')
                acodec = f.get('acodec')
                format_url = f.get('url')
                
                if not format_url:
                    continue
                    
                height = f.get('height')
                format_id = f.get('format_id')
                filesize = f.get('filesize') or f.get('filesize_approx')
                
                has_video = vcodec != 'none' and vcodec is not None
                has_audio = acodec != 'none' and acodec is not None
                
                if has_video and has_audio:
                    resolution = f"{height}p" if height else f.get('resolution', 'Standard')
                    key = ('combined', resolution)
                    if key not in seen_resolutions:
                        formats_list.append({
                            'format_id': format_id,
                            'resolution': resolution,
                            'ext': ext,
                            'type': 'video_audio',
                            'filesize': filesize,
                            'note': f.get('format_note', 'Standard Video')
                        })
                        seen_resolutions.add(key)
                        
                elif has_audio and not has_video:
                    abr = f.get('abr')
                    bitrate = f"{int(abr)}kbps" if abr else "Standard"
                    key = ('audio', bitrate)
                    if key not in seen_resolutions:
                        formats_list.append({
                            'format_id': format_id,
                            'resolution': f"Audio ({bitrate})",
                            'ext': ext,
                            'type': 'audio',
                            'filesize': filesize,
                            'note': f"Audio Saja ({ext})"
                        })
                        seen_resolutions.add(key)
                        
                elif has_video and not has_audio:
                    resolution = f"{height}p" if height else f.get('resolution', 'High Quality')
                    key = ('video_only', resolution)
                    if key not in seen_resolutions:
                        formats_list.append({
                            'format_id': format_id,
                            'resolution': f"{resolution} (Tanpa Suara)",
                            'ext': ext,
                            'type': 'video_only',
                            'filesize': filesize,
                            'note': "Video Kualitas Tinggi"
                        })
                        seen_resolutions.add(key)
            
            formats_list.reverse()
            
            return jsonify({
                'title': title,
                'thumbnail': thumbnail,
                'duration': duration_str,
                'uploader': uploader,
                'formats': formats_list,
                'original_url': url,
                'cookie_token': cookie_token
            })
            
    except Exception as e:
        return jsonify({'error': f'Gagal memproses video: {str(e)}'}), 500

@app.route('/api/download')
def download_video():
    video_url = request.args.get('url')
    format_id = request.args.get('format_id')
    cookie_token = request.args.get('token')
    cookie_path = get_cookie_path(cookie_token) if cookie_token else None
    
    if not video_url or not format_id:
        return 'Parameter tidak lengkap', 400
        
    ydl_opts = {
        'format': format_id,
        'quiet': True,
        'no_warnings': True,
    }
    
    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            direct_url = info.get('url')
            title = info.get('title', 'download')
            ext = info.get('ext', 'mp4')
            
            if not direct_url:
                formats = info.get('formats', [])
                for f in formats:
                    if f.get('format_id') == format_id:
                        direct_url = f.get('url')
                        ext = f.get('ext', ext)
                        break
            
            if not direct_url:
                return 'Gagal mendapatkan URL unduhan langsung', 404
                
            safe_title = sanitize_filename(title)
            filename = f"{safe_title}.{ext}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            session = requests.Session()
            if cookie_path:
                cookies = load_cookies_from_file(cookie_path)
                if cookies is not None:
                    session.cookies = cookies

            req_stream = session.get(direct_url, headers=headers, stream=True, timeout=30)
            
            def generate():
                for chunk in req_stream.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            
            response_headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': req_stream.headers.get('Content-Type', 'application/octet-stream')
            }
            
            if 'Content-Length' in req_stream.headers:
                response_headers['Content-Length'] = req_stream.headers['Content-Length']
                
            return Response(stream_with_context(generate()), headers=response_headers)
            
    except Exception as e:
        return f'Gagal mengunduh: {str(e)}', 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
