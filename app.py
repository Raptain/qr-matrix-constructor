import os
import json
import re
import uuid
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import CircleModuleDrawer, RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw
import io
import base64

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

def generate_qr(data, **kwargs):
    qr = qrcode.QRCode(
        version=kwargs.get('version', 1),
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=kwargs.get('box_size', 10),
        border=kwargs.get('border', 4),
    )
    qr.add_data(data)
    qr.make(fit=True)

    # Выбор стиля модулей
    eye_style = kwargs.get('eye_style', 'square')
    if eye_style == 'circle':
        module_drawer = CircleModuleDrawer()
    elif eye_style == 'rounded':
        module_drawer = RoundedModuleDrawer()
    else:
        module_drawer = SquareModuleDrawer()

    # Цвета (конвертируем HEX в RGB)
    front_color = hex_to_rgb(kwargs.get('front_color', '#000000'))
    back_color = hex_to_rgb(kwargs.get('back_color', '#ffffff'))
    
    color_mask = SolidFillColorMask(front_color=front_color, back_color=back_color)

    # Генерация QR
    try:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=module_drawer,
            color_mask=color_mask
        ).convert('RGB')
    except:
        # Fallback на обычный QR
        img = qr.make_image(fill_color=front_color, back_color=back_color).convert('RGB')

    # Добавление логотипа
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
            elif pos == 'top-left':
                x, y = 10, 10
            elif pos == 'top-right':
                x, y = img_w - logo_size - 10, 10
            elif pos == 'bottom-left':
                x, y = 10, img_h - logo_size - 10
            elif pos == 'bottom-right':
                x, y = img_w - logo_size - 10, img_h - logo_size - 10
            else:
                x, y = (img_w - logo_size) // 2, (img_h - logo_size) // 2
            
            img.paste(logo, (x, y), logo)
        except Exception as e:
            print(f"Логотип: {e}")

    # Форма (круг/сердце)
    shape = kwargs.get('shape', 'square')
    if shape == 'circle':
        img = img.convert("RGBA")
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, img.size[0], img.size[1]), fill=255)
        transparent = Image.new('RGBA', img.size, (0, 0, 0, 0))
        transparent.paste(img, (0, 0), mask)
        img = transparent
    elif shape == 'heart':
        img = img.convert("RGBA")
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((img.size[0]//4, img.size[1]//4, 
                     img.size[0]*3//4, img.size[1]*3//4), fill=255)
        transparent = Image.new('RGBA', img.size, (0, 0, 0, 0))
        transparent.paste(img, (0, 0), mask)
        img = transparent

    return img

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
        
        if code_type != 'qr':
            return jsonify({'image': '', 'warning': f'Тип "{code_type}" пока не реализован'})
        
        input_type = data.get('input_type', 'text')
        
        # Формирование текста для QR
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
        
        # Логотип
        logo_path = None
        logo_data = data.get('logo_data')
        if logo_data and logo_data.startswith('data:image'):
            img_data = re.sub('^data:image/.+;base64,', '', logo_data)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(base64.b64decode(img_data))
                logo_path = tmp.name
        
        params = {
            'front_color': data.get('foreground', '#000000'),
            'back_color': data.get('background', '#ffffff'),
            'eye_style': data.get('eye_style', 'square'),
            'shape': data.get('shape', 'square'),
            'logo_path': logo_path,
            'logo_size': data.get('logo_size', 80),
            'logo_position': data.get('logo_position', 'center'),
        }
        
        img = generate_qr(text, **params)
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        if logo_path and os.path.exists(logo_path):
            os.unlink(logo_path)
        
        # История
        history = load_history()
        history.append({
            'id': str(uuid.uuid4())[:8],
            'type': 'qr',
            'input_type': input_type,
            'content': text[:50],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tags': data.get('tags', ''),
            'name': data.get('name', 'Без имени')
        })
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