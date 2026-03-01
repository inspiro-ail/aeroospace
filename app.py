from flask import Flask, render_template, request, jsonify, send_file
import requests
import json
import csv
import io
from datetime import datetime
from typing import Dict, List, Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = 'planet-classifier-secret-key-2026'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  


OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"


planets_storage: List[Dict] = [
    {
        'id': 1,
        'name': 'Kepler-452b',
        'mass': '5 Earth masses',
        'radius': '1.6 Earth radii',
        'temperature': '265 K (-8°C)',
        'atmosphere': 'Potentially habitable',
        'waterPresence': 'Possible',
        'classification': None
    }
]
next_id = 2


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def check_status():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.ok:
            return jsonify({
                'status': 'connected',
                'message': 'Ollama подключена'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Ollama не отвечает'
            }), 503
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка подключения: {str(e)}'
        }), 503


@app.route('/api/planets', methods=['GET'])
def get_planets():
    return jsonify(planets_storage)


@app.route('/api/planets', methods=['POST'])
def add_planet():
    global next_id
    
    data = request.json
    
    if not data.get('name'):
        return jsonify({'error': 'Название планеты обязательно'}), 400
    
    planet = {
        'id': next_id,
        'name': data.get('name'),
        'mass': data.get('mass', 'N/A'),
        'radius': data.get('radius', 'N/A'),
        'temperature': data.get('temperature', 'N/A'),
        'atmosphere': data.get('atmosphere', 'N/A'),
        'waterPresence': data.get('waterPresence', 'N/A'),
        'classification': None
    }
    
    next_id += 1
    planets_storage.append(planet)
    
    return jsonify(planet), 201


@app.route('/api/planets/<int:planet_id>', methods=['DELETE'])
def delete_planet(planet_id):
    global planets_storage
    planets_storage = [p for p in planets_storage if p['id'] != planet_id]
    return jsonify({'success': True})


@app.route('/api/planets/clear', methods=['POST'])
def clear_planets():
    global planets_storage, next_id
    planets_storage = []
    next_id = 1
    return jsonify({'success': True})


@app.route('/api/classify/<int:planet_id>', methods=['POST'])
def classify_planet(planet_id):
    """Классифицировать планету с помощью Ollama"""
    planet = next((p for p in planets_storage if p['id'] == planet_id), None)
    
    if not planet:
        return jsonify({'error': 'Планета не найдена'}), 404
    
    prompt = f"""Ты эксперт по планетарной науке. Проанализируй следующие характеристики планеты и определи, является ли она полезной для человечества (колонизация, добыча ресурсов, научные исследования).

Название: {planet['name']}
Масса: {planet['mass']}
Радиус: {planet['radius']}
Температура: {planet['temperature']}
Атмосфера: {planet['atmosphere']}
Наличие воды: {planet['waterPresence']}

Ответь в формате JSON:
{{
  "useful": true/false,
  "confidence": 0-100,
  "reasoning": "краткое объяснение на русском",
  "potentialUses": ["список возможных применений"],
  "risks": ["список рисков"]
}}

Отвечай ТОЛЬКО JSON, без дополнительного текста."""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=120
        )
        
        if not response.ok:
            return jsonify({
                'error': f'Ollama вернула ошибку: {response.status_code}'
            }), 503
        
        data = response.json()
        
        try:
            result = json.loads(data['response'])
        except:
            
            import re
            json_match = re.search(r'\{[\s\S]*\}', data['response'])
            if json_match:
                result = json.loads(json_match.group(0))
            else:
                return jsonify({
                    'error': 'Не удалось распарсить ответ от Ollama'
                }), 500
        
        
        planet['classification'] = result
        
        return jsonify(result)
        
    except requests.exceptions.Timeout:
        return jsonify({
            'error': 'Превышено время ожидания ответа от Ollama'
        }), 504
    except Exception as e:
        return jsonify({
            'error': f'Ошибка классификации: {str(e)}'
        }), 500


@app.route('/api/import/json', methods=['POST'])
def import_json():
    global next_id
    
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не предоставлен'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    try:
        content = file.read().decode('utf-8')
        data = json.loads(content)
        
        if isinstance(data, list):
            imported_planets = data
        else:
            imported_planets = [data]
        
        count = 0
        for planet_data in imported_planets:
            if 'name' in planet_data and planet_data['name']:
                planet = {
                    'id': next_id,
                    'name': planet_data.get('name'),
                    'mass': planet_data.get('mass', 'N/A'),
                    'radius': planet_data.get('radius', 'N/A'),
                    'temperature': planet_data.get('temperature', 'N/A'),
                    'atmosphere': planet_data.get('atmosphere', 'N/A'),
                    'waterPresence': planet_data.get('waterPresence', 
                                                    planet_data.get('water', 'N/A')),
                    'classification': None
                }
                next_id += 1
                planets_storage.append(planet)
                count += 1
        
        return jsonify({
            'success': True,
            'count': count,
            'message': f'Импортировано планет: {count}'
        })
        
    except json.JSONDecodeError:
        return jsonify({'error': 'Неверный формат JSON'}), 400
    except Exception as e:
        return jsonify({'error': f'Ошибка импорта: {str(e)}'}), 500


@app.route('/api/import/csv', methods=['POST'])
def import_csv():
    global next_id
    
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не предоставлен'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    try:
        content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        count = 0
        for row in csv_reader:
            if 'name' in row and row['name']:
                planet = {
                    'id': next_id,
                    'name': row.get('name'),
                    'mass': row.get('mass', 'N/A'),
                    'radius': row.get('radius', 'N/A'),
                    'temperature': row.get('temperature', 'N/A'),
                    'atmosphere': row.get('atmosphere', 'N/A'),
                    'waterPresence': row.get('waterPresence', 
                                            row.get('water', 'N/A')),
                    'classification': None
                }
                next_id += 1
                planets_storage.append(planet)
                count += 1
        
        return jsonify({
            'success': True,
            'count': count,
            'message': f'Импортировано планет: {count}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Ошибка импорта: {str(e)}'}), 500


@app.route('/api/export/json')
def export_json():
    output = io.BytesIO()
    output.write(json.dumps(planets_storage, ensure_ascii=False, indent=2).encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'planets_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )


@app.route('/api/export/csv')
def export_csv():
    output = io.StringIO()
    fieldnames = ['name', 'mass', 'radius', 'temperature', 
                 'atmosphere', 'waterPresence', 'useful', 
                 'confidence', 'reasoning']
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for planet in planets_storage:
        row = {
            'name': planet.get('name', ''),
            'mass': planet.get('mass', ''),
            'radius': planet.get('radius', ''),
            'temperature': planet.get('temperature', ''),
            'atmosphere': planet.get('atmosphere', ''),
            'waterPresence': planet.get('waterPresence', ''),
            'useful': '',
            'confidence': '',
            'reasoning': ''
        }
        
        if planet.get('classification'):
            cls = planet['classification']
            row['useful'] = cls.get('useful', '')
            row['confidence'] = cls.get('confidence', '')
            row['reasoning'] = cls.get('reasoning', '')
        
        writer.writerow(row)
    
    output.seek(0)
    output_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
    
    return send_file(
        output_bytes,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'planets_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )


@app.route('/api/templates/json')
def download_json_template():
    template = [
        {
            "name": "Example Planet 1",
            "mass": "3 Earth masses",
            "radius": "1.5 Earth radii",
            "temperature": "280 K (+7°C)",
            "atmosphere": "Nitrogen-oxygen mix",
            "waterPresence": "Liquid water present"
        },
        {
            "name": "Example Planet 2",
            "mass": "1.2 Jupiter masses",
            "radius": "1.1 Jupiter radii",
            "temperature": "1500 K (+1227°C)",
            "atmosphere": "Hydrogen-helium",
            "waterPresence": "No liquid water"
        }
    ]
    
    output = io.BytesIO()
    output.write(json.dumps(template, ensure_ascii=False, indent=2).encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name='planets_template.json'
    )


@app.route('/api/templates/csv')
def download_csv_template():
    template = """name,mass,radius,temperature,atmosphere,waterPresence
Example Planet 1,3 Earth masses,1.5 Earth radii,280 K (+7°C),Nitrogen-oxygen mix,Liquid water present
Example Planet 2,1.2 Jupiter masses,1.1 Jupiter radii,1500 K (+1227°C),Hydrogen-helium,No liquid water"""
    
    output = io.BytesIO(template.encode('utf-8'))
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name='planets_template.csv'
    )


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Ресурс не найден'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


if __name__ == '__main__':
    print("🌌 Запуск Планетарного Классификатора...")
    print("📡 Сервер доступен по адресу: http://localhost:5000")
    print("🤖 Убедитесь что Ollama запущена на http://localhost:11434")
    app.run(debug=False, host='0.0.0.0', port=5000)
