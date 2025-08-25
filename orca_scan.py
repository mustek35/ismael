import os
import subprocess
import requests
import zipfile
import io
import platform
import xml.etree.ElementTree as ET
import threading
import time
from flask import Flask, jsonify, request, send_file
from requests.auth import HTTPBasicAuth
from PIL import ImageGrab  # Para capturar la pantalla
import pyautogui  # Para interactuar con la pantalla y capturar

# URL base sin la IP fija
BASE_URL = 'http://{ip}:8601'

# Función para capturar la pantalla
def capture_screenshot():
    screenshot = pyautogui.screenshot()  # Captura la pantalla
    screenshot.save("screenshot.png")  # Guarda la captura de pantalla como un archivo
    return "screenshot.png"

# Función para obtener el estado de las cámaras
def get_camera_status(ip):
    url = BASE_URL.format(ip=ip) + '/Interface/Cameras/GetStatus?AuthUser=admin&ResponseFormat=XML'
    response = requests.get(url, auth=HTTPBasicAuth('', ''))  # Basic Auth sin usuario y contraseña
    if response.status_code == 200:
        return parse_camera_xml(response.content)
    else:
        return None

# Función para convertir XML a JSON
def parse_camera_xml(xml_data):
    root = ET.fromstring(xml_data)
    cameras = []
    for camera in root.find('.//Cameras'):
        camera_data = {
            'name': camera.find('Name').text,
            'active': camera.find('Active').text == 'TRUE',
            'working': camera.find('Working').text == 'TRUE',
            'recording_time': convert_hours_to_readable(float(camera.find('RecordingHours').text))
        }
        cameras.append(camera_data)
    
    summary = f"{len(cameras)} de {root.find('.//Count').text} cámaras están activas"
    
    return {
        "devicesStatus": {
            "summary": summary,
            "cameras": cameras,
            "acopioStatus": "NVR acopio: online"
        }
    }

# Convertir horas en formato amigable (meses y días)
def convert_hours_to_readable(hours):
    days = hours / 24
    months = int(days // 30)
    days = int(days % 30)
    return f"{months} mes(es) y {days} día(s)"

# Función para obtener los eventos recientes de comunicación
def get_recent_event_data(ip):
    url = BASE_URL.format(ip=ip) + '/Interface/Events/Search?EventType=COMMUNICATION_RESTORED'
    response = requests.get(url, auth=HTTPBasicAuth('', ''))  # Basic Auth sin usuario y contraseña
    if response.status_code == 200:
        return parse_event_xml(response.content)
    else:
        return None

# Función para convertir los eventos XML a JSON
def parse_event_xml(xml_data):
    root = ET.fromstring(xml_data)
    events = []
    for record in root.findall('.//DeviceCommunicationRecord'):
        event_data = {
            'RecordNumber': record.find('RecordNumber').text,
            'DateTime': record.find('DateTime').text,
            'DeviceName': record.find('DeviceName').text,
            'DeviceCommunicationEvent': record.find('DeviceCommunicationEvent').text,
            'DeviceCommunicationFailureTime': record.find('DeviceCommunicationFailureTime').text,
        }
        events.append(event_data)
    
    if events:
        return {"events": events}
    else:
        return {"events": "No hay errores recientes"}

# Función para instalar ngrok en Windows
def install_ngrok():
    """Instala ngrok si no está presente en Windows"""
    if not os.path.exists("ngrok.exe"):
        print("ngrok no está instalado. Instalando ngrok...")
        ngrok_url = "https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-windows-amd64.zip"
        response = requests.get(ngrok_url)
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        zip_file.extractall()
        print("ngrok instalado correctamente.")

# Función para ejecutar ngrok y exponer la API
def run_ngrok():
    """Ejecuta ngrok para exponer el puerto 5700"""
    ngrok_process = subprocess.Popen(['ngrok.exe', 'http', '5700'], stdout=subprocess.PIPE)
    print("Ejecutando ngrok para exponer el puerto 5700...")
    time.sleep(5)  # Espera para que el túnel se inicialice

    # Obtener la URL pública
    try:
        url = requests.get('http://127.0.0.1:4040/api/tunnels').json()['tunnels'][0]['public_url']
        print(f"API expuesta públicamente en: {url}")
    except Exception as e:
        print("Error obteniendo la URL de ngrok:", str(e))

# Interfaz interactiva para cambiar la IP y el nombre del centro
def get_ip_and_center_from_user():
    """Permite que el usuario ingrese la IP y el nombre del centro"""
    ip = input("Ingrese la IP del servidor (deje vacío para usar la IP por defecto '10.11.10.3'): ")
    center = input("Ingrese el nombre del centro: ")
    if not ip:
        ip = "10.11.10.3"
    if not center:
        center = "acopio"  # Nombre por defecto si no se ingresa nada
    return ip, center

# Configuración de la API Flask con rutas dinámicas
def create_flask_app(center):
    app = Flask(__name__)

    @app.route(f'/api/{center}/status', methods=['GET'])
    def get_status():
        ip = request.args.get('ip', '10.11.10.3')  # IP por defecto
        status = get_camera_status(ip)
        if status:
            return jsonify(status)
        else:
            return jsonify({"error": "No se pudo recuperar el estado de las cámaras"}), 500

    @app.route(f'/api/{center}/events', methods=['GET'])
    def get_recent_events():
        ip = request.args.get('ip', '10.11.10.3')
        events = get_recent_event_data(ip)
        if events:
            return jsonify(events)
        else:
            return jsonify({"error": "No se encontraron eventos recientes"}), 500

    @app.route(f'/api/{center}/screenshot', methods=['GET'])
    def get_screenshot():
        # Capturar la pantalla y devolver el archivo
        screenshot_path = capture_screenshot()
        return send_file(screenshot_path, mimetype='image/png')

    return app

def main():
    try:
        print("Iniciando la instalación de ngrok...")
        install_ngrok()  # Instala ngrok si no está instalado en Windows
        print("ngrok instalado.")

        # Obtener la IP y el nombre del centro del usuario
        ip, center = get_ip_and_center_from_user()
        print(f"IP: {ip}, Centro: {center}")

        # Crear la API Flask con el nombre del centro dinámico
        app = create_flask_app(center)
        print("API Flask creada correctamente.")

        # Ejecutar la API Flask en un hilo separado
        flask_thread = threading.Thread(target=app.run, kwargs={'port': 5700})
        flask_thread.start()
        print("Servidor Flask iniciado.")

        # Ejecutar ngrok para exponer la API
        run_ngrok()
        print("ngrok ejecutado correctamente.")
    except Exception as e:
        print(f"Ocurrió un error: {e}")
        input("Presiona Enter para cerrar...")
