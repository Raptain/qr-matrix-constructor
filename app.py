import os
import json
import re
import uuid
import tempfile
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import io
import base64
from PIL import Image, ImageDraw

# QR Code
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import CircleModuleDrawer, RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask

# PDF417
from pdf417 import encode, render_image

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Папки для хранения
if not os.path.exists('static/history'):
    os.makedirs('static/history')
if not os.path.exists('static/uploads'):
    os.makedirs('static/uploads')

HISTORY_FILE = 'static/history/history.json'

def hex_to_rgb(hex_color):
    """Преобразует HEX цвет в RGB кортеж"""
    if isinstance(hex_color, tuple):
        return hex_color
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

# ============================================================
## ГЕНЕРАТОР QR
# ============================================================
def draw_eye_pattern(draw, center_x, center_y, module_size, pattern, color, back_color):
    half_size = (7 * module_size) // 2
    left = center_x - half_size
    top = center_y - half_size
    right = center_x + half_size
    bottom = center_y + half_size
    outer_rect = [left, top, right, bottom]
    
    inner_left = center_x - half_size + module_size
    inner_top = center_y - half_size + module_size
    inner_right = center_x + half_size - module_size
    inner_bottom = center_y + half_size - module_size
    inner_rect = [inner_left, inner_top, inner_right, inner_bottom]
    
    center_half = (3 * module_size) // 2
    
    if pattern == 'square':
        draw.rectangle(outer_rect, outline=color, width=module_size, fill=None)
        draw.rectangle(inner_rect, fill=back_color)
        center_rect = [center_x - center_half, center_y - center_half,
                       center_x + center_half, center_y + center_half]
        draw.rectangle(center_rect, fill=color)
    elif pattern == 'circle':
        draw.ellipse(outer_rect, outline=color, width=module_size, fill=None)
        draw.ellipse(inner_rect, fill=back_color)
        center_rect = [center_x - center_half, center_y - center_half,
                       center_x + center_half, center_y + center_half]
        draw.ellipse(center_rect, fill=color)
    elif pattern == 'rounded':
        radius = module_size * 2
        draw.rounded_rectangle(outer_rect, radius=radius, outline=color, 
                              width=module_size, fill=None)
        draw.rounded_rectangle(inner_rect, radius=radius//2, fill=back_color)
        center_rect = [center_x - center_half, center_y - center_half,
                       center_x + center_half, center_y + center_half]
        draw.ellipse(center_rect, fill=color)
    else:
        draw.rectangle(outer_rect, outline=color, width=module_size, fill=None)
        draw.rectangle(inner_rect, fill=back_color)
        center_rect = [center_x - center_half, center_y - center_half,
                       center_x + center_half, center_y + center_half]
        draw.rectangle(center_rect, fill=color)

def generate_qr(data, **kwargs):
    front_color = kwargs.get('front_color', '#000000')
    back_color = kwargs.get('back_color', '#ffffff')
    module_size = kwargs.get('box_size', 10)
    module_shape = kwargs.get('module_shape', 'square')
    eye_pattern = kwargs.get('eye_pattern', 'square')
    
    # Конвертируем цвета если нужно
    if isinstance(front_color, str):
        front_color = hex_to_rgb(front_color)
    if isinstance(back_color, str):
        back_color = hex_to_rgb(back_color)
    
    qr = qrcode.QRCode(
        version=kwargs.get('version', None),
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=module_size,
        border=0,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    matrix = qr.modules
    matrix_size = len(matrix)
    img_size_pixels = matrix_size * module_size
    
    if module_shape == 'circle':
        module_drawer = CircleModuleDrawer()
    elif module_shape == 'rounded':
        module_drawer = RoundedModuleDrawer()
    else:
        module_drawer = SquareModuleDrawer()
    
    color_mask = SolidFillColorMask(front_color=front_color, back_color=back_color)
    
    try:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=module_drawer,
            color_mask=color_mask
        ).convert('RGB')
    except:
        img = Image.new('RGB', (img_size_pixels, img_size_pixels), color=back_color)
        draw = ImageDraw.Draw(img)
        for y, row in enumerate(matrix):
            for x, module in enumerate(row):
                if module:
                    draw.rectangle(
                        [x * module_size, y * module_size, 
                         (x + 1) * module_size, (y + 1) * module_size],
                        fill=front_color
                    )
    
    img = img.convert('RGBA')
    draw = ImageDraw.Draw(img)
    
    half_eye_size = (7 * module_size) // 2
    eye_centers = [
        (half_eye_size, half_eye_size),
        (img_size_pixels - half_eye_size, half_eye_size),
        (half_eye_size, img_size_pixels - half_eye_size)
    ]
    
    for center_x, center_y in eye_centers:
        draw.rectangle(
            [center_x - half_eye_size, center_y - half_eye_size,
             center_x + half_eye_size, center_y + half_eye_size],
            fill=back_color
        )
    
    for center_x, center_y in eye_centers:
        draw_eye_pattern(draw, center_x, center_y, module_size, eye_pattern, front_color, back_color)
    
    logo_path = kwargs.get('logo_path')
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            img_w, img_h = img.size
            logo_size = min(kwargs.get('logo_size', 80), img_w // 3)
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            
            pos = kwargs.get('logo_position', 'center')
            if pos == 'center':
                x, y = (img_w - logo_size) // 2, (img_h - logo_size) // 2
            else:
                x, y = 10, 10
            
            img.paste(logo, (x, y), logo)
        except Exception as e:
            print(f"Ошибка логотипа: {e}")
    
    return img

# ============================================================
## ГЕНЕРАТОР DATA MATRIX (ИМИТАЦИЯ)
# ============================================================
def generate_datamatrix(data, **kwargs):
    front_color = kwargs.get('front_color', '#000000')
    back_color = kwargs.get('back_color', '#ffffff')
    module_size = kwargs.get('module_size', 10)
    
    if isinstance(front_color, str):
        front_color = hex_to_rgb(front_color)
    if isinstance(back_color, str):
        back_color = hex_to_rgb(back_color)
    
    data_len = len(data)
    if data_len <= 10:
        size = 10
    elif data_len <= 20:
        size = 12
    elif data_len <= 40:
        size = 14
    elif data_len <= 60:
        size = 16
    elif data_len <= 80:
        size = 18
    elif data_len <= 100:
        size = 20
    else:
        size = 22
    
    img_size = (size + 2) * module_size
    img = Image.new('RGB', (img_size, img_size), color=back_color)
    draw = ImageDraw.Draw(img)
    
    frame_width = module_size
    
    draw.rectangle([0, 0, frame_width, img_size], fill=front_color)
    draw.rectangle([0, img_size - frame_width, img_size, img_size], fill=front_color)
    
    for i in range(size + 2):
        if i % 2 == 0:
            draw.rectangle([i * module_size, 0, (i + 1) * module_size, frame_width], fill=front_color)
            draw.rectangle([img_size - frame_width, i * module_size, img_size, (i + 1) * module_size], fill=front_color)
    
    hash_bytes = hashlib.sha256(data.encode('utf-8')).digest()
    
    for y in range(size):
        for x in range(size):
            idx = (y * size + x) % len(hash_bytes)
            if hash_bytes[idx] > 128:
                draw.rectangle(
                    [frame_width + x * module_size, frame_width + y * module_size,
                     frame_width + (x + 1) * module_size, frame_width + (y + 1) * module_size],
                    fill=front_color
                )
    
    draw.rectangle([frame_width, frame_width, frame_width + module_size * 2, frame_width + module_size * 2], fill=front_color)
    draw.rectangle([img_size - frame_width - module_size * 2, img_size - frame_width - module_size * 2,
                    img_size - frame_width, img_size - frame_width], fill=front_color)
    
    return img

# ============================================================
## ГЕНЕРАТОР AZTEC (ИМИТАЦИЯ)
# ============================================================
def generate_aztec(data, **kwargs):
    front_color = kwargs.get('front_color', '#000000')
    back_color = kwargs.get('back_color', '#ffffff')
    module_size = kwargs.get('module_size', 8)
    
    if isinstance(front_color, str):
        front_color = hex_to_rgb(front_color)
    if isinstance(back_color, str):
        back_color = hex_to_rgb(back_color)
    
    data_len = len(data)
    if data_len <= 12:
        layers = 1
        core_size = 11
    elif data_len <= 30:
        layers = 2
        core_size = 11
    elif data_len <= 60:
        layers = 3
        core_size = 15
    elif data_len <= 100:
        layers = 4
        core_size = 15
    elif data_len <= 150:
        layers = 5
        core_size = 15
    else:
        layers = 6
        core_size = 15
    
    if core_size == 11:
        total_size = 11 + 4 * layers
    else:
        total_size = 15 + 4 * (layers - 1)
    
    margin = module_size * 2
    img_size = total_size * module_size + margin * 2
    
    img = Image.new('RGB', (img_size, img_size), color=back_color)
    draw = ImageDraw.Draw(img)
    
    offset_x = margin
    offset_y = margin
    
    def draw_module(x, y, color):
        px = offset_x + x * module_size
        py = offset_y + y * module_size
        draw.rectangle([px, py, px + module_size, py + module_size], fill=color)
    
    center = total_size // 2
    
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            draw_module(center + dx, center + dy, front_color)
    
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if abs(dx) == 2 or abs(dy) == 2:
                draw_module(center + dx, center + dy, front_color)
    
    eye_size = 4 if core_size == 11 else 6
    for dy in range(-eye_size, eye_size + 1):
        for dx in range(-eye_size, eye_size + 1):
            if abs(dx) == eye_size or abs(dy) == eye_size:
                draw_module(center + dx, center + dy, front_color)
    
    half_core = core_size // 2
    draw_module(center - half_core, center - half_core, front_color)
    draw_module(center - half_core + 1, center - half_core, front_color)
    draw_module(center - half_core, center - half_core + 1, front_color)
    draw_module(center + half_core - 1, center - half_core, front_color)
    draw_module(center + half_core, center - half_core, front_color)
    draw_module(center - half_core, center + half_core, front_color)
    
    hash_bytes = hashlib.sha256(data.encode('utf-8')).digest()
    bit_idx = 0
    
    for layer in range(1, layers + 1):
        ring_start = -(half_core + 2 * layer)
        ring_end = half_core + 2 * layer
        inner_bound = half_core + 2 * (layer - 1)
        
        for dy in range(ring_start, ring_end + 1):
            for dx in range(ring_start, ring_end + 1):
                if abs(dx) <= inner_bound and abs(dy) <= inner_bound:
                    continue
                if abs(dx) == ring_end or abs(dy) == ring_end or abs(dx) == ring_start or abs(dy) == ring_start:
                    idx = (bit_idx % len(hash_bytes))
                    if hash_bytes[idx] > 128:
                        draw_module(center + dx, center + dy, front_color)
                    bit_idx += 1
    
    return img

# ============================================================
## ГЕНЕРАТОР PDF417 (РАБОТАЕТ)
# ============================================================
def generate_pdf417(data, **kwargs):
    front_color = kwargs.get('front_color', '#000000')
    back_color = kwargs.get('back_color', '#ffffff')
    
    if isinstance(front_color, str):
        front_color = hex_to_rgb(front_color)
    if isinstance(back_color, str):
        back_color = hex_to_rgb(back_color)
    
    try:
        codes = encode(data, columns=5, security_level=2)
        img = render_image(codes)
        
        img = img.convert('RGB')
        pixels = img.load()
        
        width, height = img.size
        
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                if r < 128 and g < 128 and b < 128:
                    pixels[x, y] = front_color
                else:
                    pixels[x, y] = back_color
        
        # Масштабируем для лучшего отображения
        scale = 2
        new_width = width * scale
        new_height = height * scale
        img = img.resize((new_width, new_height), Image.Resampling.NEAREST)
        
        return img
    
    except Exception as e:
        print(f"PDF417 ошибка: {e}")
        img = Image.new('RGB', (500, 200), color=back_color)
        draw = ImageDraw.Draw(img)
        draw.text((20, 80), f"Ошибка: {str(e)[:80]}", fill=front_color, align="center")
        return img

# ============================================================
## МАРШРУТЫ
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/qr')
def qr_page():
    return render_template('qr.html')

@app.route('/datamatrix')
def datamatrix_page():
    return render_template('datamatrix.html')

@app.route('/aztec')
def aztec_page():
    return render_template('aztec.html')

@app.route('/pdf417')
def pdf417_page():
    return render_template('pdf417.html')

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.json
        code_type = data.get('type', 'qr')
        content = data.get('content', {})
        input_type = data.get('input_type', 'text')
        
        if input_type == 'text':
            text = content.get('text', '')
        elif input_type == 'url':
            text = content.get('url', '')
        elif input_type == 'wifi':
            ssid = content.get('ssid', '')
            pwd = content.get('password', '')
            enc = content.get('encryption', 'WPA')
            if enc == 'nopass':
                text = f"WIFI:S:{ssid};;"
            else:
                text = f"WIFI:T:{enc};S:{ssid};P:{pwd};;"
        elif input_type == 'sms':
            text = f"SMSTO:{content.get('phone', '')}:{content.get('message', '')}"
        elif input_type == 'email':
            text = f"mailto:{content.get('email', '')}?subject={content.get('subject', '')}&body={content.get('body', '')}"
        elif input_type == 'contact':
            text = f"BEGIN:VCARD\nVERSION:3.0\nFN:{content.get('name', '')}\nTEL:{content.get('phone', '')}\nEMAIL:{content.get('email', '')}\nEND:VCARD"
        else:
            text = ''
        
        if not text:
            return jsonify({'error': 'Введите данные'})
        
        logo_path = None
        logo_data = data.get('logo_data')
        if code_type == 'qr' and logo_data and logo_data.startswith('data:image'):
            img_data = re.sub('^data:image/.+;base64,', '', logo_data)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(base64.b64decode(img_data))
                logo_path = tmp.name
        
        if code_type == 'qr':
            params = {
                'front_color': data.get('foreground', '#000000'),
                'back_color': data.get('background', '#ffffff'),
                'module_shape': data.get('module_shape', 'square'),
                'eye_pattern': data.get('eye_pattern', 'square'),
                'box_size': 10,
                'logo_path': logo_path,
                'logo_size': data.get('logo_size', 80),
                'logo_position': data.get('logo_position', 'center'),
            }
            img = generate_qr(text, **params)
        
        elif code_type == 'datamatrix':
            params = {
                'front_color': data.get('foreground', '#000000'),
                'back_color': data.get('background', '#ffffff'),
                'module_size': data.get('module_size', 10),
            }
            img = generate_datamatrix(text, **params)
        
        elif code_type == 'aztec':
            params = {
                'front_color': data.get('foreground', '#000000'),
                'back_color': data.get('background', '#ffffff'),
                'module_size': data.get('module_size', 8),
            }
            img = generate_aztec(text, **params)
        
        elif code_type == 'pdf417':
            params = {
                'front_color': data.get('foreground', '#000000'),
                'back_color': data.get('background', '#ffffff'),
            }
            img = generate_pdf417(text, **params)
        
        else:
            return jsonify({'image': '', 'warning': f'Тип "{code_type}" не поддерживается'})
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        if logo_path and os.path.exists(logo_path):
            os.unlink(logo_path)
        
        history = load_history()
        history.append({
            'id': str(uuid.uuid4())[:8],
            'type': code_type,
            'input_type': input_type,
            'content': text[:50],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tags': data.get('tags', ''),
            'name': data.get('name', 'Без имени')
        })
        if len(history) > 50:
            history = history[-50:]
        save_history(history)
        
        return jsonify({'image': f'data:image/png;base64,{img_str}', 'success': True})
    
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/history')
def get_history():
    return jsonify(load_history())

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)