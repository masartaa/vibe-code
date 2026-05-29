import os
import re
import time
import requests
from functools import wraps
from urllib.parse import urlparse
# pyrefly: ignore [missing-import]
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, make_response
import yt_dlp

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'replace-with-secure-key')

# Konfigurasi keamanan dasar
BASIC_AUTH_USER = os.environ.get('ADMIN_USER', 'admin')
BASIC_AUTH_PASS = os.environ.get('ADMIN_PASS', 'secret')
RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', 30))
RATE_LIMIT_WINDOW = 60
ALLOWED_HOSTS = [host.strip().lower() for host in os.environ.get(
    'ALLOWED_HOSTS',
    'youtube.com,youtu.be,tiktok.com,instagram.com,facebook.com,fb.watch,twitter.com,x.com,vimeo.com'
).split(',') if host.strip()]

rate_limit_store = {}

# Memastikan judul file aman untuk disimpan
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)


def get_client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


def is_host_allowed(url):
    if not ALLOWED_HOSTS:
        return True
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        hostname = hostname.lower()
        return any(hostname == allowed or hostname.endswith('.' + allowed) for allowed in ALLOWED_HOSTS)
    except Exception:
        return False


def rate_limit_exceeded():
    client_ip = get_client_ip()
    now = int(time.time())
    window_start, count = rate_limit_store.get(client_ip, (now, 0))

    if now - window_start >= RATE_LIMIT_WINDOW:
        rate_limit_store[client_ip] = (now, 1)
        return False

    if count + 1 > RATE_LIMIT_PER_MINUTE:
        return True

    rate_limit_store[client_ip] = (window_start, count + 1)
    return False


def check_auth(username, password):
    return username == BASIC_AUTH_USER and password == BASIC_AUTH_PASS


def authenticate():
    response = make_response('Authentication required', 401)
    response.headers['WWW-Authenticate'] = 'Basic realm="StreamVault"'
    return response


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' fonts.googleapis.com; font-src fonts.gstatic.com; img-src 'self' data: https:;"
    return response


@app.after_request
def set_security_headers(response):
    return add_security_headers(response)


@app.before_request
def enforce_basic_auth_and_rate_limit():
    if request.endpoint in ('favicon',):
        return None

    if request.path.startswith('/static/'):
        return None

    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()

    if rate_limit_exceeded():
        return jsonify({'error': 'Terlalu banyak permintaan. Silakan coba lagi nanti.'}), 429

    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/info', methods=['POST'])
def get_video_info():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL tidak boleh kosong'}), 400

    if not is_valid_url(url):
        return jsonify({'error': 'URL tidak valid. Gunakan URL mulai dengan http:// atau https://'}), 400

    if not is_host_allowed(url):
        return jsonify({'error': 'Domain tidak diizinkan. Harap gunakan URL dari situs video yang terpercaya.'}), 400
        
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Ekstraksi metadata utama
            title = info.get('title', 'Video Tanpa Judul')
            thumbnail = info.get('thumbnail') or info.get('thumbnails', [{}])[-1].get('url')
            duration = info.get('duration') # dalam detik
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
            
            # Parse format unduhan yang tersedia
            formats_list = []
            seen_resolutions = set()
            
            # Kita urutkan format dari kualitas terbaik ke terendah
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
                
                # Format yang memiliki Video & Audio
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
            
            # Balik urutan agar resolusi tertinggi berada di atas
            formats_list.reverse()
            
            return jsonify({
                'title': title,
                'thumbnail': thumbnail,
                'duration': duration_str,
                'uploader': uploader,
                'formats': formats_list,
                'original_url': url
            })
            
    except Exception as e:
        return jsonify({'error': f'Gagal memproses video: {str(e)}'}), 500

@app.route('/api/download')
def download_video():
    video_url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    if not video_url or not format_id:
        return 'Parameter tidak lengkap', 400

    if not is_valid_url(video_url):
        return 'URL tidak valid', 400

    if not is_host_allowed(video_url):
        return 'Domain tidak diizinkan', 400
        
    ydl_opts = {
        'format': format_id,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            direct_url = info.get('url')
            title = info.get('title', 'download')
            ext = info.get('ext', 'mp4')
            
            if not direct_url:
                # Coba format alternatif jika direct URL kosong
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
            
            # Headers untuk streaming chunk-by-chunk dari remote server ke client
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            req_stream = requests.get(direct_url, headers=headers, stream=True, timeout=30)
            
            # Buat generator untuk melakukan streaming byte-by-byte
            def generate():
                for chunk in req_stream.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            
            # Response dengan header attachment agar browser mendownload file
            response_headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': req_stream.headers.get('Content-Type', 'application/octet-stream')
            }
            
            # Tambahkan Content-Length jika tersedia
            if 'Content-Length' in req_stream.headers:
                response_headers['Content-Length'] = req_stream.headers['Content-Length']
                
            return Response(stream_with_context(generate()), headers=response_headers)
            
    except Exception as e:
        return f'Gagal mengunduh: {str(e)}', 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
