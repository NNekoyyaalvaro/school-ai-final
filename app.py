import os
import google.generativeai as genai
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Chat, Message
import logging
import io

# Configuración
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school-ai.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar extensiones
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Configurar Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyAquiVaTuAPIKey')
genai.configure(api_key=GEMINI_API_KEY)

# Configurar modelo Gemini
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1024,
}

model = genai.GenerativeModel(
    model_name="models/gemini-2.5-flash",
    generation_config=generation_config
)

# Temas prohibidos
PROHIBITED_TOPICS = [
    "suicidio", "autolesión", "como matarse", "violencia extrema",
    "contenido adulto", "sexo explícito", "drogas ilegales",
    "trampas en examen", "copiar en examen"
]

# ============================================
# FUNCIONES AUXILIARES
# ============================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def is_safe_question(question):
    """Verifica si la pregunta es apropiada"""
    question_lower = question.lower()
    for topic in PROHIBITED_TOPICS:
        if topic in question_lower:
            return False, "Lo siento, no puedo responder preguntas sobre ese tema."
    return True, ""

def generate_chat_title(first_message):
    """Genera un título automático para el chat basado en el primer mensaje"""
    try:
        prompt = f"Genera un título muy corto (máximo 5 palabras) para un chat educativo que comienza con esta pregunta: '{first_message}'. Responde SOLO con el título, sin comillas ni puntuación extra."
        response = model.generate_content(prompt)
        title = response.text.strip()
        # Limitar longitud
        if len(title) > 50:
            title = title[:50] + "..."
        return title
    except:
        # Si falla, usar título genérico
        return "Nuevo chat"

def create_educational_prompt(question):
    """Crea prompt educativo"""
    prompt = f"""Eres School AI, un asistente educativo para estudiantes.

INSTRUCCIONES:
1. Eres un GUÍA, no un solucionador. Ayudas al estudiante a descubrir la respuesta.
2. Nunca des la respuesta directa a problemas o ejercicios.
3. Usa preguntas para guiar el pensamiento.
4. Sé alentador, positivo y paciente.
5. Explica conceptos de manera clara.
6. Tus respuestas deben ser en español.

PREGUNTA: "{question}"

RESPUESTA EDUCATIVA:"""
    return prompt

# ============================================
# RUTAS DE AUTENTICACIÓN
# ============================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validar que no exista
        if User.query.filter_by(username=username).first():
            flash('El nombre de usuario ya existe', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('El email ya está registrado', 'error')
            return redirect(url_for('register'))
        
        # Crear usuario
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
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
        # Obtener primer mensaje como preview
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
    """Obtener mensajes de un chat específico"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp).all()
    
    result = [{
        'role': msg.role,
        'content': msg.content,
        'timestamp': msg.timestamp.isoformat()
    } for msg in messages]
    
    return jsonify(result)

@app.route('/api/chat/new', methods=['POST'])
@login_required
def new_chat():
    """Crear nuevo chat"""
    data = request.json
    first_message = data.get('message', '')
    
    # Crear chat con título temporal
    chat = Chat(
        user_id=current_user.id,
        title='Nuevo chat...'
    )
    db.session.add(chat)
    db.session.commit()
    
    # Si hay mensaje, procesarlo
    if first_message:
        # Guardar mensaje del usuario
        user_message = Message(
            chat_id=chat.id,
            role='user',
            content=first_message
        )
        db.session.add(user_message)
        db.session.commit()
        
        # Verificar seguridad
        is_safe, warning = is_safe_question(first_message)
        if not is_safe:
            # Mensaje de advertencia
            ai_message = Message(
                chat_id=chat.id,
                role='assistant',
                content=warning
            )
            db.session.add(ai_message)
            db.session.commit()
            
            # Título genérico
            chat.title = "Chat educativo"
        else:
            # Generar respuesta con Gemini
            try:
                prompt = create_educational_prompt(first_message)
                response = model.generate_content(prompt)
                ai_response = response.text
                
                # Guardar respuesta
                ai_message = Message(
                    chat_id=chat.id,
                    role='assistant',
                    content=ai_response
                )
                db.session.add(ai_message)
                db.session.commit()
                
                # Generar título automático basado en el primer mensaje
                title = generate_chat_title(first_message)
                chat.title = title
                
            except Exception as e:
                logging.error(f"Error Gemini: {e}")
                ai_message = Message(
                    chat_id=chat.id,
                    role='assistant',
                    content="Lo siento, tuve un problema técnico. Por favor, intenta de nuevo."
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
    """Enviar mensaje en un chat existente"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    data = request.json
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'error': 'Mensaje vacío'}), 400
    
    # Guardar mensaje del usuario
    user_msg = Message(
        chat_id=chat.id,
        role='user',
        content=user_message
    )
    db.session.add(user_msg)
    db.session.commit()
    
    # Verificar seguridad
    is_safe, warning = is_safe_question(user_message)
    if not is_safe:
        ai_msg = Message(
            chat_id=chat.id,
            role='assistant',
            content=warning
        )
        db.session.add(ai_msg)
        db.session.commit()
        
        chat.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'role': 'assistant',
            'content': warning
        })
    
    # Generar respuesta con Gemini
    try:
        prompt = create_educational_prompt(user_message)
        
        # Incluir contexto de mensajes anteriores
        recent_messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp.desc()).limit(10).all()
        if len(recent_messages) > 1:
            context = "\n".join([f"{'Usuario' if m.role=='user' else 'Asistente'}: {m.content}" for m in reversed(recent_messages[:-1])])
            full_prompt = f"Historial reciente:\n{context}\n\nNueva pregunta: {user_message}\n\nRespuesta como asistente educativo:"
        else:
            full_prompt = prompt
        
        response = model.generate_content(full_prompt)
        ai_response = response.text
        
    except Exception as e:
        logging.error(f"Error Gemini: {e}")
        ai_response = "Lo siento, tuve un problema técnico. Por favor, intenta de nuevo."
    
    # Guardar respuesta
    ai_msg = Message(
        chat_id=chat.id,
        role='assistant',
        content=ai_response
    )
    db.session.add(ai_msg)
    
    # Actualizar timestamp del chat
    chat.updated_at = datetime.utcnow()
    
    # Si el chat no tiene título, generarlo ahora
    if chat.title == 'Nuevo chat...' or chat.title == 'Chat educativo':
        # Buscar el primer mensaje del usuario
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
    """Actualizar título de un chat"""
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
    """Eliminar un chat"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    
    # Los mensajes se eliminan automáticamente por cascade
    db.session.delete(chat)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/chat/<int:chat_id>/download', methods=['GET'])
@login_required
def download_chat(chat_id):
    """Descargar chat como archivo de texto"""
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp).all()
    
    # Crear contenido del archivo
    content = f"SCHOOL AI - CHAT: {chat.title}\n"
    content += f"Fecha: {chat.created_at.strftime('%d/%m/%Y %H:%M')}\n"
    content += "=" * 50 + "\n\n"
    
    for msg in messages:
        role = "TÚ" if msg.role == 'user' else "SCHOOL AI"
        time = msg.timestamp.strftime('%H:%M')
        content += f"[{time}] {role}:\n{msg.content}\n\n"
        content += "-" * 30 + "\n\n"
    
    # Crear archivo en memoria
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
# INICIALIZACIÓN (CON CREACIÓN DE BASE DE DATOS)
# ============================================
# Esta parte se ejecuta siempre, tanto en desarrollo como en producción
with app.app_context():
    try:
        # Crear todas las tablas si no existen
        db.create_all()
        print("✅ Base de datos verificada/creada correctamente.")
    except Exception as e:
        print(f"❌ Error al crear/verificar la base de datos: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
