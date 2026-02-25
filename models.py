from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Modelo de usuario con soporte para OAuth"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=True)  # Puede ser null para OAuth
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)  # Puede ser null para OAuth
    oauth_provider = db.Column(db.String(50), nullable=True)  # 'google' o None
    oauth_id = db.Column(db.String(200), nullable=True)  # ID de Google
    avatar_url = db.Column(db.String(500), nullable=True)  # Foto de perfil
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relación con chats
    chats = db.relationship('Chat', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def get_id(self):
        return str(self.id)

class Chat(db.Model):
    """Modelo de chat"""
    __tablename__ = 'chats'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, default='Nuevo chat')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con mensajes
    messages = db.relationship('Message', backref='chat', lazy=True, cascade='all, delete-orphan')

class Message(db.Model):
    """Modelo de mensaje con soporte para imágenes"""
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chats.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' o 'assistant'
    content = db.Column(db.Text, nullable=False)
    has_image = db.Column(db.Boolean, default=False)  # Si incluye imagen
    image_data = db.Column(db.Text, nullable=True)  # Base64 de la imagen (opcional)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
