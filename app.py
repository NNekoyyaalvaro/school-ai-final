from flask import Flask, render_template, request, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        pregunta = data.get('message', '').lower()
        
        # Respuestas educativas simples
        respuestas = {
            'fotosíntesis': '🌱 La fotosíntesis es el proceso donde las plantas convierten luz solar en energía. ¿Sabes qué gas del aire absorben las plantas?',
            'ecuación': '📐 Para resolver una ecuación, primero debes despejar la incógnita. ¿Puedes mostrarme la ecuación específica?',
            'célula': '🔬 Las células son la unidad básica de la vida. ¿Te interesa la célula animal o vegetal?',
            'agua': '💧 El agua es H2O. El ciclo del agua incluye evaporación, condensación y precipitación.',
            'gravedad': '🌍 La gravedad es la fuerza que nos atrae hacia la Tierra. Fue descubierta por Newton.',
            'poema': '📝 Para analizar un poema, observa: estrofas, versos, rima y el tema principal.'
        }
        
        respuesta = "Buena pregunta. Para ayudarte mejor, ¿puedes darme más detalles?"
        for palabra, resp in respuestas.items():
            if palabra in pregunta:
                respuesta = resp
                break
        
        return jsonify({'response': respuesta, 'warning': False})
        
    except Exception as e:
        return jsonify({'response': f'Error: {str(e)}', 'warning': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
