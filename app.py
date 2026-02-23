import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

# Inicializar Flask
app = Flask(__name__)
CORS(app)

# Configurar Gemini API
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyAquiVaTuAPIKey')  # Reemplaza con tu key
genai.configure(api_key=GEMINI_API_KEY)

# Configurar el modelo educativo
generation_config = {
    "temperature": 0.7,  # Creatividad balanceada
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1024,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

# Inicializar modelo educativo
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",  # Modelo rápido y gratuito
    generation_config=generation_config,
    safety_settings=safety_settings
)

# Lista de temas prohibidos (seguridad escolar)
PROHIBITED_TOPICS = [
    "suicidio", "autolesión", "como matarse", "violencia extrema",
    "contenido adulto", "sexo explícito", "drogas ilegales",
    "trampas en examen", "copiar en examen"
]

def is_safe_question(question):
    """Verifica si la pregunta es apropiada para el ámbito escolar"""
    question_lower = question.lower()
    for topic in PROHIBITED_TOPICS:
        if topic in question_lower:
            return False, "Lo siento, no puedo responder preguntas sobre ese tema. Si necesitas ayuda, por favor habla con un profesor."
    return True, ""

def create_educational_prompt(question):
    """Crea un prompt educativo que guíe al estudiante sin dar respuestas directas"""
    prompt = f"""Eres School AI, un asistente educativo diseñado para estudiantes de colegio.

INSTRUCCIONES IMPORTANTES:
1. Eres un GUÍA, no un solucionador. Ayudas al estudiante a descubrir la respuesta por sí mismo.
2. Nunca des la respuesta directa a problemas o ejercicios.
3. Usa preguntas para guiar el pensamiento del estudiante.
4. Sé alentador, positivo y paciente.
5. Explica conceptos de manera clara pero sin resolver tareas completas.
6. Si el estudiante pregunta algo inapropiado, redirige amablemente al tema educativo.

PREGUNTA DEL ESTUDIANTE: "{question}"

RESPUESTA EDUCATIVA (como guía, no como solucionador):"""
    return prompt

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_question = data.get('message', '').strip()
        
        if not user_question:
            return jsonify({'response': 'Por favor, escribe una pregunta.', 'warning': True})
        
        # Verificar seguridad
        is_safe, warning_message = is_safe_question(user_question)
        if not is_safe:
            return jsonify({'response': warning_message, 'warning': True})
        
        # Crear prompt educativo
        prompt = create_educational_prompt(user_question)
        
        # Llamar a Gemini API
        response = model.generate_content(prompt)
        
        # Obtener respuesta
        ai_response = response.text
        
        logging.info(f"Pregunta: {user_question[:50]}... | Respuesta generada")
        
        return jsonify({'response': ai_response, 'warning': False})
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({
            'response': "Lo siento, tuve un problema técnico. Por favor, intenta de nuevo.",
            'warning': True
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
