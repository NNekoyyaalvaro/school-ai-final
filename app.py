import os
import base64
import io
import google.generativeai as genai
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from PIL import Image
from models import db, User, Chat, Message
import logging

# Configuración
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school-ai.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Sesión persistente
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Inicializar extensiones
db.init_app(app)

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, inicia sesión para acceder.'
login_manager.session_protection = 'strong'  # Protección contra secuestro de sesión
login_manager.remember_cookie_duration = timedelta(days=7)

# Configurar OAuth (Google)
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account'  # Forzar selección de cuenta
    }
)

# Configurar Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY no está configurada en las variables de entorno")
genai.configure(api_key=GEMINI_API_KEY)

# Configurar modelo Gemini multimodal (acepta imágenes)
generation_config = {
    "temperature": 0.8,  # Más creativo
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

model = genai.GenerativeModel(
    model_name="models/gemini-2.5-flash",  # Modelo que acepta imágenes
    generation_config=generation_config
)

# ============================================
# FUNCIONES AUXILIARES
# ============================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_chat_title(first_message):
    """Genera título automático para el chat"""
    try:
        prompt = f"Genera un título muy corto (máximo 5 palabras) para un chat educativo que comienza con: '{first_message}'. Responde SOLO con el título."
        response = model.generate_content(prompt)
        return response.text.strip()[:50]
    except:
        return "Nuevo chat"

def process_image(image_data):
    """Procesa imagen subida (base64) para Gemini"""
    try:
        # Decodificar base64
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        
        # Verificar que es una imagen válida
        img = Image.open(io.BytesIO(image_bytes))
        
        # Redimensionar si es muy grande (Gemini tiene límites)
        max_size = (1024, 1024)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convertir de vuelta a bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
    except Exception as e:
        logging.error(f"Error procesando imagen: {e}")
        return None

def create_multimodal_prompt(question, image_bytes=None):
    """Crea prompt que puede incluir imagen"""
    if image_bytes:
        # Si hay imagen, construir prompt multimodal
        prompt = [
            "Eres School AI, un asistente educativo.",
            "El usuario ha subido esta imagen y pregunta:",
            {"mime_type": "image/png", "data": image_bytes},
            question,
            "Por favor, responde considerando la imagen y la pregunta."
        ]
        return prompt
    else:
        # Prompt normal sin imagen
        return f"""Eres School AI, un asistente educativo.

PREGUNTA: "{question}"

RESPUESTA EDUCATIVA (completa, detallada y útil):"""

# ============================================
# RUTAS DE AUTENTICACIÓN (con Google OAuth)
# ============================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validar
        if User.query.filter_by(email=email).first():
            flash('El email ya está registrado', 'error')
            return redirect(url_for('register'))
        
        # Crear usuario
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password) if password else None,
            created_at=datetime.utcnow()
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Email o contraseña incorrectos', 'error')
    
    return render_template('login.html')

@app.route('/login/google')
def google_login():
    """Iniciar sesión con Google"""
    redirect_uri = url_for('google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize/google')
def google_authorize():
    """Callback de Google OAuth"""
    try:
        token = google.authorize_access_token()
        user_info = google.parse_id_token(token)
        
        email = user_info.get('email')
        name = user_info.get('name')
        google_id = user_info.get('sub')
        avatar = user_info.get('picture')
        
        # Buscar usuario existente
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Crear nuevo usuario con OAuth
            user = User(
                username=name,
                email=email,
                oauth_provider='google',
                oauth_id=google_id,
                avatar_url=avatar,
                created_at=datetime.utcnow()
            )
            db.session.add(user)
        
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=True)
        return redirect(url_for('index'))
        
    except Exception as e:
        logging.error(f"Error en Google OAuth: {e}")
        flash('Error al iniciar sesión con Google', 'error')
        return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

# ============================================
# RUTAS PRINCIPALES
# ============================================

@app.route('/')
@login_required
def index():
    """Página principal del chat"""
    return render_template('index.html')

@app.route('/api/chats', methods=['GET'])
@login_required
def get_chats():
    """Obtener todos los chats del usuario"""
    chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.updated_at.desc()).all()
    
    result = []
    for chat in chats:
        first_message = Message.query.filter_by(chat_id=chat.id, role='user').first()
        preview = first_message.content[:50] + '...' if first_message else 'Chat vacío'
        
        result.append({
            'id': chat.id,
            'title': chat.title,
            'preview': preview,
            'created_at': chat.created_at.isoformat(),
            'updated_at': chat.updated_at.isoformat()
        })
    
    return jsonify(result)

@app.route('/api/chat/<int:chat_id>', methods=['GET'])
@login_required
def get_chat(chat_id):
    """Obtener mensajes de un chat"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp).all()
    
    result = [{
        'role': msg.role,
        'content': msg.content,
        'has_image': msg.has_image,
        'timestamp': msg.timestamp.isoformat()
    } for msg in messages]
    
    return jsonify(result)

@app.route('/api/chat/new', methods=['POST'])
@login_required
def new_chat():
    """Crear nuevo chat"""
    data = request.json
    first_message = data.get('message', '')
    
    chat = Chat(
        user_id=current_user.id,
        title='Nuevo chat...'
    )
    db.session.add(chat)
    db.session.commit()
    
    if first_message:
        # Guardar mensaje del usuario
        user_message = Message(
            chat_id=chat.id,
            role='user',
            content=first_message,
            has_image=False
        )
        db.session.add(user_message)
        db.session.commit()
        
        try:
            # Generar respuesta con Gemini
            prompt = f"""Eres School AI, un asistente educativo.

PREGUNTA: "{first_message}"

Responde de manera completa, educativa y detallada. Puedes incluir explicaciones, ejemplos y guiar al estudiante."""
            
            response = model.generate_content(prompt)
            ai_response = response.text
            
            # Guardar respuesta
            ai_message = Message(
                chat_id=chat.id,
                role='assistant',
                content=ai_response,
                has_image=False
            )
            db.session.add(ai_message)
            
            # Generar título automático
            chat.title = generate_chat_title(first_message)
            
        except Exception as e:
            logging.error(f"Error Gemini: {e}")
            ai_message = Message(
                chat_id=chat.id,
                role='assistant',
                content="Lo siento, tuve un problema técnico. Por favor, intenta de nuevo.",
                has_image=False
            )
            db.session.add(ai_message)
            chat.title = "Chat educativo"
        
        chat.updated_at = datetime.utcnow()
        db.session.commit()
    
    return jsonify({
        'chat_id': chat.id,
        'title': chat.title
    })

@app.route('/api/chat/<int:chat_id>/message', methods=['POST'])
@login_required
def send_message(chat_id):
    """Enviar mensaje (con o sin imagen)"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    
    data = request.json
    user_message = data.get('message', '').strip()
    image_base64 = data.get('image', None)  # Imagen en base64
    
    if not user_message and not image_base64:
        return jsonify({'error': 'Mensaje vacío'}), 400
    
    # Guardar mensaje del usuario
    user_msg = Message(
        chat_id=chat.id,
        role='user',
        content=user_message or "[Imagen enviada]",
        has_image=bool(image_base64),
        image_data=image_base64 if image_base64 else None
    )
    db.session.add(user_msg)
    db.session.commit()
    
    # Procesar imagen si existe
    image_bytes = None
    if image_base64:
        image_bytes = process_image(image_base64)
    
    # Generar respuesta con Gemini
    try:
        if image_bytes:
            # Prompt multimodal con imagen
            prompt = f"""Eres School AI, un asistente educativo.

El usuario ha subido esta imagen. {user_message if user_message else 'Analiza esta imagen educativamente.'}

Por favor, analiza la imagen y responde de manera completa y educativa."""
            
            response = model.generate_content([
                prompt,
                {"mime_type": "image/png", "data": image_bytes}
            ])
        else:
            # Prompt normal sin imagen
            prompt = f"""Eres School AI, un asistente educativo.

PREGUNTA: "{user_message}"

Responde de manera completa, educativa y detallada."""
            
            response = model.generate_content(prompt)
        
        ai_response = response.text
        
    except Exception as e:
        logging.error(f"Error Gemini: {e}")
        ai_response = "Lo siento, tuve un problema técnico. Por favor, intenta de nuevo."
    
    # Guardar respuesta
    ai_msg = Message(
        chat_id=chat.id,
        role='assistant',
        content=ai_response,
        has_image=False
    )
    db.session.add(ai_msg)
    
    # Actualizar timestamp
    chat.updated_at = datetime.utcnow()
    
    # Si el chat no tiene título, generarlo
    if chat.title == 'Nuevo chat...' or chat.title == 'Chat educativo':
        first_user_msg = Message.query.filter_by(chat_id=chat.id, role='user').order_by(Message.timestamp).first()
        if first_user_msg:
            chat.title = generate_chat_title(first_user_msg.content)
    
    db.session.commit()
    
    return jsonify({
        'role': 'assistant',
        'content': ai_response
    })

@app.route('/api/chat/<int:chat_id>/title', methods=['PUT'])
@login_required
def update_chat_title(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    data = request.json
    new_title = data.get('title', '').strip()
    
    if new_title:
        chat.title = new_title
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'error': 'Título vacío'}), 400

@app.route('/api/chat/<int:chat_id>', methods=['DELETE'])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    db.session.delete(chat)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/chat/<int:chat_id>/download', methods=['GET'])
@login_required
def download_chat(chat_id):
    """Descargar chat como archivo de texto"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp).all()
    
    content = f"SCHOOL AI - CHAT: {chat.title}\n"
    content += f"Fecha: {chat.created_at.strftime('%d/%m/%Y %H:%M')}\n"
    content += "=" * 50 + "\n\n"
    
    for msg in messages:
        role = "TÚ" if msg.role == 'user' else "SCHOOL AI"
        time = msg.timestamp.strftime('%H:%M')
        content += f"[{time}] {role}:\n{msg.content}\n\n"
        if msg.has_image:
            content += "[📷 Imagen adjunta]\n\n"
        content += "-" * 30 + "\n\n"
    
    memory_file = io.BytesIO()
    memory_file.write(content.encode('utf-8'))
    memory_file.seek(0)
    
    filename = f"school-ai-{chat.title[:30]}.txt".replace(' ', '-').replace('/', '-')
    
    return send_file(
        memory_file,
        download_name=filename,
        as_attachment=True,
        mimetype='text/plain'
    )

# ============================================
# INICIALIZACIÓN
# ============================================
with app.app_context():
    db.create_all()
    print("✅ Base de datos verificada/creada")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
