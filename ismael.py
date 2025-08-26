import sys
import os
import json
import threading
import time
from datetime import datetime
import pytz
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QTextEdit, QLabel, QLineEdit, 
                            QTabWidget, QTableWidget, QTableWidgetItem, QComboBox,
                            QCheckBox, QGroupBox, QFormLayout, QScrollArea,
                            QMessageBox, QSplitter, QFrame, QSpinBox, QProgressBar,
                            QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem)
from PySide6.QtCore import QThread, Signal, QTimer, Qt, QSettings
from PySide6.QtGui import QFont, QPixmap, QIcon, QTextCursor

# Importar las funciones necesarias
import requests
from dotenv import load_dotenv
import imaplib
import email
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import smtplib
from email import message_from_string

# Configuraciones por defecto
DEFAULT_CONFIG = {
    "openai_api_key": "",
    "email_address": "ismael@orcatecnologia.cl",
    "email_password": "",
    "smtp_server": "smtp.gmail.com",
    "imap_server": "imap.gmail.com",
    "smtp_port": 587,
    "assistant_id": "asst_RO6jvTXoyyu6WmwL6w9imlvF",
    "technical_assistant_id": "asst_3iCMq8n0etmnIgzQQCsysuge",
    "check_interval": 60,
    "max_attempts": 10,
    "wait_time": 10,
    "temperature": 1.2,
    "top_p": 1.0,
    "test_recipient": "soporte@orcatecnologia.cl",
    "remitentes_permitidos": [
        "centralseguridadsay@salmonesaysen.cl",
        "vigilancia2@aquachile.com",
        "seguridad@caletabay.cl",
        "cespinoza.cast@gmail.com"
    ]
}

# Mantener compatibilidad con la variable global (se actualizará desde config)
REMITENTES_PERMITIDOS = [
    "centralseguridadsay@salmonesaysen.cl",
    "vigilancia2@aquachile.com",
    "seguridad@caletabay.cl",
    "cespinoza.cast@gmail.com"
]

# Centros por defecto
DEFAULT_CENTROS_EMPRESAS = {
    "Salmones Aysen": [
        "Teupa", "Lleuna", "Tutil", "Huenquillahue", "Raliguao", "Puyuhuapi", "Aldachildo", 
        "Lamahue", "Milagro", "Cuem", "Curbita", "Lin Lin", "Huito", "Chulchuy", "Choen", "Halcones Chico"
    ],
    "Caleta Bay": [
        "Caleta Martin", "Pucheguin", "Concheo 2", "Farellones", "Barquillo", "Punta Iglesias"
    ],
    "AquaChile": [
         "Nevenka", "Lalanca", "Jesus 1", "Valverde 2", "Canal Luchin", "Canalad 2", "Jesus 9", 
         "Jesus 5", "Cahueldao", "Pescadores", "Caleta Juarez", "Cuptana 4", "Gertrudis 2", 
         "Francisco Sur", "Davis", "Tangbac", "Canalad 1", "Mauchil", "Jud", "Quetros 2", 
         "Punta Ganso", "Pangal 3", "Paildad", "Martina", "Punta Porvenir", "Huapi"
    ],
    "Cermaq": [
        "Acopio"
    ]
}

class EmailWorkerThread(QThread):
    log_signal = Signal(str, str)  # message, level (INFO, ERROR, DEBUG, SUCCESS)
    email_processed_signal = Signal(dict)  # email data
    stats_updated_signal = Signal(int, int)  # total, responded
    inbox_count_signal = Signal(int, int)  # total emails, unread emails
    
    def __init__(self, config, centros_empresas):
        super().__init__()
        self.config = config
        self.centros_empresas = centros_empresas
        self.running = False
        self.total_correos = 0
        self.total_respondidos = 0
        self.check_inbox_requested = False
        
    def run(self):
        self.running = True
        self.log_signal.emit("🚀 Iniciando el asistente de correo electrónico...", "INFO")
        
        while self.running:
            try:
                self.check_emails()
                self.check_inbox_count()
                if self.running:
                    time.sleep(self.config.get('check_interval', 60))
            except Exception as e:
                self.log_signal.emit(f"❌ Error en el hilo principal: {str(e)}", "ERROR")
                time.sleep(10)
    
    def request_inbox_check(self):
        self.check_inbox_requested = True
        self.log_signal.emit("📬 Verificación manual de bandeja solicitada", "INFO")
        
    def check_inbox_count(self):
        try:
            mail = imaplib.IMAP4_SSL(self.config['imap_server'])
            mail.login(self.config['email_address'], self.config['email_password'])
            mail.select('inbox')
            
            # Contar todos los correos
            status, all_messages = mail.search(None, 'ALL')
            total_emails = len(all_messages[0].split()) if all_messages[0] else 0
            
            # Contar correos no leídos
            status, unread_messages = mail.search(None, '(UNSEEN)')
            unread_emails = len(unread_messages[0].split()) if unread_messages[0] else 0
            
            mail.close()
            mail.logout()
            
            self.inbox_count_signal.emit(total_emails, unread_emails)
            
            if self.check_inbox_requested:
                self.log_signal.emit(f"📊 Bandeja: {total_emails} correos totales, {unread_emails} no leídos", "INFO")
                self.check_inbox_requested = False
                
        except Exception as e:
            self.log_signal.emit(f"❌ Error verificando bandeja: {str(e)}", "ERROR")
    
    def stop(self):
        self.running = False
        self.log_signal.emit("⏹️ Deteniendo el asistente de correo...", "INFO")
    
    def check_emails(self):
        try:
            asunto, remitente, cuerpo, mensaje_original = self.leer_correo()
            if cuerpo and self.es_remitente_permitido(remitente):
                self.total_correos += 1
                self.log_signal.emit(f"📧 Procesando correo de: {remitente}", "INFO")
                self.log_signal.emit(f"📝 Asunto: {asunto}", "DEBUG")
                
                email_data = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'from': remitente,
                    'subject': asunto,
                    'body_preview': cuerpo[:100] + '...' if len(cuerpo) > 100 else cuerpo,
                    'status': 'Procesando...'
                }
                self.email_processed_signal.emit(email_data)
                
                if self.procesar_correo_principal(cuerpo, asunto, remitente, mensaje_original):
                    self.total_respondidos += 1
                    email_data['status'] = 'Respondido'
                else:
                    email_data['status'] = 'Error'
                
                self.email_processed_signal.emit(email_data)
                self.stats_updated_signal.emit(self.total_correos, self.total_respondidos)
                
            elif remitente:
                self.log_signal.emit(f"⚠️ Correo de {remitente} no está en la lista permitida", "DEBUG")
            else:
                self.log_signal.emit("💤 No hay correos nuevos", "DEBUG")
                
        except Exception as e:
            self.log_signal.emit(f"❌ Error verificando correos: {str(e)}", "ERROR")
    
    def leer_correo(self):
        try:
            mail = imaplib.IMAP4_SSL(self.config['imap_server'])
            mail.login(self.config['email_address'], self.config['email_password'])
            mail.select('inbox')
            
            status, mensajes = mail.search(None, '(UNSEEN)')
            correos_ids = mensajes[0].split()
            
            if correos_ids:
                for correo_id in correos_ids:
                    status, mensaje_data = mail.fetch(correo_id, '(RFC822)')
                    for respuesta_part in mensaje_data:
                        if isinstance(respuesta_part, tuple):
                            mensaje = email.message_from_bytes(respuesta_part[1])
                            asunto = mensaje['subject']
                            remitente = mensaje['from']
                            cuerpo = self.obtener_cuerpo(mensaje)
                            mail.close()
                            mail.logout()
                            return asunto, remitente, cuerpo, mensaje
            
            mail.close()
            mail.logout()
            return None, None, None, None
            
        except Exception as e:
            self.log_signal.emit(f"❌ Error leyendo correo: {str(e)}", "ERROR")
            return None, None, None, None
    
    def obtener_cuerpo(self, mensaje):
        if mensaje.is_multipart():
            for parte in mensaje.walk():
                if parte.get_content_type() == 'text/plain':
                    try:
                        return parte.get_payload(decode=True).decode('utf-8')
                    except UnicodeDecodeError:
                        return parte.get_payload(decode=True).decode('latin-1')
        else:
            try:
                return mensaje.get_payload(decode=True).decode('utf-8')
            except UnicodeDecodeError:
                return mensaje.get_payload(decode=True).decode('latin-1')
    
    def es_remitente_permitido(self, remitente):
        email_match = re.search(r'[\w\.-]+@[\w\.-]+', remitente)
        if email_match:
            remitente_email = email_match.group(0).lower()
            # Usar la lista actualizada desde la configuración
            remitentes_actuales = self.config.get('remitentes_permitidos', REMITENTES_PERMITIDOS)
            return remitente_email in [email.lower() for email in remitentes_actuales]
        return False
    
    def procesar_correo_principal(self, cuerpo, asunto, remitente, mensaje_original):
        try:
            self.log_signal.emit("🤖 Creando thread para asistente principal...", "DEBUG")
            thread_id_principal = self.crear_thread()
            
            if not thread_id_principal:
                return False
                
            self.log_signal.emit(f"✅ Thread principal creado: {thread_id_principal}", "DEBUG")
            
            mensaje_id = self.agregar_mensaje_al_thread(thread_id_principal, cuerpo)
            if not mensaje_id:
                return False
                
            respuesta_primaria = self.ejecutar_thread(thread_id_principal)
            if not respuesta_primaria:
                return False
                
            self.log_signal.emit("📤 Enviando respuesta principal...", "INFO")
            self.enviar_correo(respuesta_primaria, "", remitente, asunto, mensaje_original)
            
            centros_detectados, desconexion_detectada = self.detectar_desconexion(cuerpo, asunto)
            
            if desconexion_detectada and centros_detectados:
                self.log_signal.emit("🔧 Desconexión detectada, ejecutando asistente técnico...", "INFO")
                time.sleep(60)
                
                respuesta_tecnica = self.procesar_asistente_tecnico(centros_detectados)
                if respuesta_tecnica:
                    self.enviar_correo(respuesta_tecnica, "", remitente, asunto, mensaje_original)
                    self.log_signal.emit("✅ Respuesta técnica enviada", "SUCCESS")
            
            return True
            
        except Exception as e:
            self.log_signal.emit(f"❌ Error procesando correo: {str(e)}", "ERROR")
            return False
    
    def crear_thread(self):
        headers = {
            'Authorization': f'Bearer {self.config["openai_api_key"]}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        response = requests.post("https://api.openai.com/v1/threads", headers=headers, json={})
        if response.status_code == 200:
            return response.json().get("id")
        else:
            self.log_signal.emit(f"❌ Error creando thread: {response.text}", "ERROR")
            return None
    
    def agregar_mensaje_al_thread(self, thread_id, content):
        headers = {
            'Authorization': f'Bearer {self.config["openai_api_key"]}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        data = {"role": "user", "content": content}
        url = f"https://api.openai.com/v1/threads/{thread_id}/messages"
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['id']
        else:
            self.log_signal.emit(f"❌ Error agregando mensaje: {response.text}", "ERROR")
            return None
    
    def ejecutar_thread(self, thread_id):
        headers = {
            'Authorization': f'Bearer {self.config["openai_api_key"]}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        data = {
            "assistant_id": self.config["assistant_id"],
            "temperature": self.config.get("temperature", 1.2),
            "top_p": self.config.get("top_p", 1.0)
        }
        
        url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            self.log_signal.emit(f"❌ Error ejecutando thread: {response.text}", "ERROR")
            return None
        
        for attempt in range(self.config.get("max_attempts", 10)):
            time.sleep(self.config.get("wait_time", 10))
            status = self.obtener_estado_thread(thread_id)
            
            if status == "completed":
                return self.obtener_mensajes_thread(thread_id)
            elif status == "failed":
                self.log_signal.emit("❌ Thread falló", "ERROR")
                break
            
            self.log_signal.emit(f"⏳ Esperando thread... (intento {attempt + 1})", "DEBUG")
        
        return None
    
    def obtener_estado_thread(self, thread_id):
        headers = {
            'Authorization': f'Bearer {self.config["openai_api_key"]}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            runs = response.json().get("data", [])
            if runs:
                return runs[0].get("status")
        return None
    
    def obtener_mensajes_thread(self, thread_id):
        headers = {
            'Authorization': f'Bearer {self.config["openai_api_key"]}',
            'Content-Type': 'application/json',
            'OpenAI-Beta': 'assistants=v2'
        }
        
        url = f"https://api.openai.com/v1/threads/{thread_id}/messages"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            messages = response.json().get("data", [])
            for message in messages:
                if message.get("role") == "assistant":
                    return message["content"][0]["text"]["value"]
        return None
    
    def detectar_desconexion(self, cuerpo, asunto):
        terminos_desconexion = [
            "desconexión", "sin conexión", "sin enlace", "sin visual", "ping", "problema de enlace",
            "cámaras sin visual", "no hay visual en central", "desconectado", "desconectada",
            "no hay visual de camaras", "desconexion", "camaras en negro"
        ]
        
        texto_completo = (cuerpo + " " + asunto).lower()
        desconexion_detectada = any(termino in texto_completo for termino in terminos_desconexion)
        
        if desconexion_detectada:
            centros = self.capturar_centros(cuerpo, asunto)
            return centros, True
        
        return None, False
    
    def capturar_centros(self, cuerpo, asunto):
        texto_completo = (cuerpo + " " + asunto).lower()
        centros_encontrados = {}
        
        for empresa, centros in self.centros_empresas.items():
            for centro in centros:
                if centro.lower() in texto_completo:
                    if empresa not in centros_encontrados:
                        centros_encontrados[empresa] = set()
                    centros_encontrados[empresa].add(centro)
        
        return centros_encontrados if centros_encontrados else None
    
    def procesar_asistente_tecnico(self, centros_detectados):
        try:
            thread_id_tecnico = self.crear_thread()
            if not thread_id_tecnico:
                return None
            
            empresa = list(centros_detectados.keys())[0]
            resultado_api = self.consultar_api_por_empresa(empresa, centros_detectados)
            
            if resultado_api:
                mensaje_id = self.agregar_mensaje_al_thread(thread_id_tecnico, json.dumps(resultado_api))
                if mensaje_id:
                    return self.ejecutar_thread(thread_id_tecnico)
            
            return None
            
        except Exception as e:
            self.log_signal.emit(f"❌ Error en asistente técnico: {str(e)}", "ERROR")
            return None
    
    def consultar_api_por_empresa(self, empresa, centros_detectados):
        try:
            nombre_centro = list(centros_detectados[empresa])[0]
            nombre_centro_url = nombre_centro.replace(" ", "").lower()
            
            if empresa == "Cermaq":
                api_url = f"https://apiacopio.orcawan.uk/api/{nombre_centro_url}"
            elif empresa == "AquaChile":
                api_url = f"https://apihuapi.orcawan.uk/api/{nombre_centro_url}"
            else:
                return None
            
            self.log_signal.emit(f"🌐 Consultando API: {api_url}", "DEBUG")
            response = requests.get(api_url)
            
            if response.status_code == 200:
                return response.json()
            else:
                self.log_signal.emit(f"❌ Error API {response.status_code}: {nombre_centro}", "ERROR")
                return None
                
        except Exception as e:
            self.log_signal.emit(f"❌ Error consultando API: {str(e)}", "ERROR")
            return None
    
    def enviar_correo(self, respuesta, respuesta_tecnica, remitente, asunto, mensaje_original):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['email_address']
            msg['To'] = "soporte@orcatecnologia.cl"
            msg['Subject'] = f"Re: {asunto}"
            
            respuesta_limpia = respuesta.replace('**', '')
            html_body = f"<p>{respuesta_limpia.replace(chr(10), '<br>')}</p>"
            
            msg.attach(MIMEText(html_body, 'html'))
            
            servidor = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            servidor.starttls()
            servidor.login(self.config['email_address'], self.config['email_password'])
            servidor.sendmail(self.config['email_address'], ["soporte@orcatecnologia.cl"], msg.as_string())
            servidor.quit()
            
            self.log_signal.emit("✅ Correo enviado exitosamente", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_signal.emit(f"❌ Error enviando correo: {str(e)}", "ERROR")
            return False


class EmailAssistantGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('OrcaTech', 'EmailAssistant')
        
        # CARGAR CONFIGURACIÓN PRIMERO
        self.config = self.load_config()
        self.centros_empresas = self.load_centers()
        self.worker_thread = None
        
        # Estados de validación
        self.email_config_valid = False
        self.openai_config_valid = False
        self.assistant_main_valid = False
        self.assistant_tech_valid = False
        
        # ACTUALIZAR VARIABLE GLOBAL REMITENTES ANTES DE CREAR UI
        if 'remitentes_permitidos' in self.config:
            global REMITENTES_PERMITIDOS
            REMITENTES_PERMITIDOS = self.config['remitentes_permitidos'].copy()
            print(f"🔧 Remitentes actualizados en __init__: {REMITENTES_PERMITIDOS}")
        
        self.init_ui()
        self.validate_all_configs()
        
    def init_ui(self):
        self.setWindowTitle("Asistente de Correo Electrónico - OrcaTech")
        self.setGeometry(100, 100, 1400, 900)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        
        # Crear tabs
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Tabs
        self.create_monitor_tab()
        self.create_centers_tab()
        self.create_config_tab()
        self.create_test_tab()
        self.create_logs_tab()
        
        # Status bar
        self.statusBar().showMessage("Listo para iniciar")
    
    def add_log(self, message, level="INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        colors = {
            "INFO": "#ffffff",
            "DEBUG": "#cccccc", 
            "ERROR": "#ff6b6b",
            "SUCCESS": "#51cf66"
        }
        
        color = colors.get(level, "#ffffff")
        formatted_message = f'<span style="color: {color}">[{timestamp}] {message}</span>'
        
        # Solo añadir a los logs si los widgets existen
        if hasattr(self, 'log_display'):
            self.log_display.append(formatted_message)
        
        if hasattr(self, 'detailed_logs'):
            detailed_message = f"[{timestamp}] [{level}] {message}"
            self.detailed_logs.append(detailed_message)
        
        # También imprimir en consola
        print(f"[{timestamp}] [{level}] {message}")
        
        # Auto scroll si está habilitado y los widgets existen
        if (hasattr(self, 'auto_scroll_checkbox') and 
            hasattr(self, 'log_display') and 
            hasattr(self, 'detailed_logs') and
            self.auto_scroll_checkbox.isChecked()):
            self.log_display.moveCursor(QTextCursor.MoveOperation.End)
            self.detailed_logs.moveCursor(QTextCursor.MoveOperation.End)
    
    def load_config(self):
        """Cargar configuración desde archivo JSON"""
        config_file = "email_assistant_config.json"
        
        # Intentar cargar desde archivo JSON primero
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Validar que tenga todas las claves necesarias
                for key, default_value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = default_value
                        
                # Validación especial para temperature
                if 'temperature' in config:
                    try:
                        temp_val = float(config['temperature'])
                        if temp_val < 0 or temp_val > 2:
                            config['temperature'] = 1.2
                    except (ValueError, TypeError):
                        config['temperature'] = 1.2
                
                # Actualizar la variable global de remitentes permitidos
                if 'remitentes_permitidos' in config:
                    global REMITENTES_PERMITIDOS
                    REMITENTES_PERMITIDOS = config['remitentes_permitidos'].copy()
                    print(f"🔄 Variable global actualizada con {len(REMITENTES_PERMITIDOS)} remitentes")
                        
                print(f"✅ Configuración cargada desde: {config_file}")
                print(f"📧 Remitentes en config: {config.get('remitentes_permitidos', [])}")
                return config
                
            except (json.JSONDecodeError, Exception) as e:
                print(f"❌ Error cargando configuración JSON: {str(e)}")
                
        # Si no hay archivo JSON, intentar migrar desde QSettings
        config = {}
        for key, default_value in DEFAULT_CONFIG.items():
            stored_value = self.settings.value(key, default_value)
            if key == 'temperature':
                try:
                    if isinstance(stored_value, str):
                        clean_value = stored_value.split('.')[0] + '.' + str(stored_value).split('.')[1][:2]
                        config[key] = float(clean_value)
                    else:
                        config[key] = float(stored_value)
                    if config[key] < 0 or config[key] > 2:
                        config[key] = 1.2
                except (ValueError, IndexError, AttributeError):
                    config[key] = 1.2
            else:
                config[key] = stored_value
                
        # Guardar en JSON para futuras cargas
        self.save_config_to_json(config)
        return config
    
    def load_centers(self):
        """Cargar centros desde archivo JSON"""
        centers_file = "email_assistant_centers.json"
        
        # Intentar cargar desde archivo JSON
        if os.path.exists(centers_file):
            try:
                with open(centers_file, 'r', encoding='utf-8') as f:
                    centers = json.load(f)
                    print(f"✅ Centros cargados desde: {centers_file}")
                    return centers
            except (json.JSONDecodeError, Exception) as e:
                print(f"❌ Error cargando centros JSON: {str(e)}")
        
        # Si no existe, intentar migrar desde QSettings
        try:
            centers_json = self.settings.value('centros_empresas', '')
            if centers_json:
                centers = json.loads(centers_json)
                # Guardar en archivo para futuras cargas
                self.save_centers_to_json(centers)
                return centers
        except (json.JSONDecodeError, TypeError):
            pass
            
        # Usar valores por defecto
        centers = DEFAULT_CENTROS_EMPRESAS.copy()
        self.save_centers_to_json(centers)
        return centers
    
    def save_config_to_json(self, config):
        """Guardar configuración en archivo JSON"""
        try:
            config_file = "email_assistant_config.json"
            
            # Crear una copia para guardar
            config_to_save = config.copy()
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False)
                
            print(f"💾 Configuración guardada en: {config_file}")
            return True
            
        except Exception as e:
            print(f"❌ Error guardando configuración JSON: {str(e)}")
            return False
    
    def save_centers_to_json(self, centers):
        """Guardar centros en archivo JSON"""
        try:
            centers_file = "email_assistant_centers.json"
            
            with open(centers_file, 'w', encoding='utf-8') as f:
                json.dump(centers, f, indent=4, ensure_ascii=False)
                
            print(f"💾 Centros guardados en: {centers_file}")
            return True
            
        except Exception as e:
            print(f"❌ Error guardando centros JSON: {str(e)}")
            return False
    
    def save_centers(self):
        """Guardar centros (método de compatibilidad)"""
        return self.save_centers_to_json(self.centros_empresas)
        
    def init_ui(self):
        self.setWindowTitle("Asistente de Correo Electrónico - OrcaTech")
        self.setGeometry(100, 100, 1400, 900)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        
        # Crear tabs
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Tabs
        self.create_monitor_tab()
        self.create_centers_tab()
        self.create_config_tab()
        self.create_test_tab()
        self.create_logs_tab()
        
        # Status bar
        self.statusBar().showMessage("Listo para iniciar")
    
    def load_config(self):
        config = {}
        for key, default_value in DEFAULT_CONFIG.items():
            stored_value = self.settings.value(key, default_value)
            if key == 'temperature':
                try:
                    if isinstance(stored_value, str):
                        clean_value = stored_value.split('.')[0] + '.' + stored_value.split('.')[1][:2]
                        config[key] = float(clean_value)
                    else:
                        config[key] = float(stored_value)
                    if config[key] < 0 or config[key] > 2:
                        config[key] = 1.2
                except (ValueError, IndexError, AttributeError):
                    config[key] = 1.2
            else:
                config[key] = stored_value
        return config
    
    def load_centers(self):
        """Cargar centros desde configuración persistente"""
        try:
            centers_json = self.settings.value('centros_empresas', '')
            if centers_json:
                return json.loads(centers_json)
            else:
                return DEFAULT_CENTROS_EMPRESAS.copy()
        except (json.JSONDecodeError, TypeError):
            return DEFAULT_CENTROS_EMPRESAS.copy()
    
    def save_centers(self):
        """Guardar centros en configuración persistente"""
        try:
            centers_json = json.dumps(self.centros_empresas)
            self.settings.setValue('centros_empresas', centers_json)
            self.settings.sync()
            return True
        except Exception as e:
            self.add_log(f"❌ Error guardando centros: {str(e)}", "ERROR")
            return False
        
    def create_monitor_tab(self):
        monitor_widget = QWidget()
        layout = QVBoxLayout(monitor_widget)
        
        # Status indicators
        status_frame = QFrame()
        status_frame.setMaximumHeight(80)
        status_layout = QHBoxLayout(status_frame)
        
        self.email_status_label = QLabel("📧 Email: No validado")
        self.openai_status_label = QLabel("🤖 OpenAI: No validado")
        self.assistant_main_status_label = QLabel("👨‍💼 Asist. Principal: No validado")
        self.assistant_tech_status_label = QLabel("🔧 Asist. Técnico: No validado")
        
        status_layout.addWidget(self.email_status_label)
        status_layout.addWidget(self.openai_status_label)
        status_layout.addWidget(self.assistant_main_status_label)
        status_layout.addWidget(self.assistant_tech_status_label)
        status_layout.addStretch()
        
        layout.addWidget(status_frame)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("▶️ Iniciar Asistente")
        self.stop_button = QPushButton("⏹️ Detener Asistente")
        self.stop_button.setEnabled(False)
        
        self.start_button.clicked.connect(self.start_assistant)
        self.stop_button.clicked.connect(self.stop_assistant)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Stats
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("📊 Correos: 0 | Respondidos: 0")
        self.inbox_stats_label = QLabel("📬 Bandeja: - correos totales | - no leídos")
        self.stats_label.setStyleSheet("QLabel { font-size: 14px; font-weight: bold; color: #ffffff; }")
        self.inbox_stats_label.setStyleSheet("QLabel { font-size: 12px; color: #cccccc; }")
        
        stats_layout.addWidget(self.stats_label)
        stats_layout.addWidget(self.inbox_stats_label)
        stats_layout.addStretch()
        
        layout.addLayout(stats_layout)
        
        # Splitter para logs y tabla de correos
        splitter = QSplitter(Qt.Horizontal)
        
        # Debug logs (lado izquierdo)
        log_frame = QFrame()
        log_layout = QVBoxLayout(log_frame)
        log_label = QLabel("📝 Logs de Depuración:")
        log_label.setStyleSheet("QLabel { color: #ffffff; font-weight: bold; }")
        log_layout.addWidget(log_label)
        
        self.log_display = QTextEdit()
        self.log_display.setMaximumHeight(400)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 10px;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)
        log_layout.addWidget(self.log_display)
        
        # Tabla de correos (lado derecho)
        email_frame = QFrame()
        email_layout = QVBoxLayout(email_frame)
        email_label = QLabel("📧 Correos Procesados:")
        email_label.setStyleSheet("QLabel { color: #ffffff; font-weight: bold; }")
        email_layout.addWidget(email_label)
        
        self.email_table = QTableWidget()
        self.email_table.setColumnCount(5)
        self.email_table.setHorizontalHeaderLabels(["Hora", "Remitente", "Asunto", "Vista Previa", "Estado"])
        self.email_table.setColumnWidth(0, 130)
        self.email_table.setColumnWidth(1, 200)
        self.email_table.setColumnWidth(2, 200)
        self.email_table.setColumnWidth(3, 300)
        self.email_table.setColumnWidth(4, 100)
        self.email_table.setStyleSheet("""
            QTableWidget {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 6px;
            }
        """)
        email_layout.addWidget(self.email_table)
        
        splitter.addWidget(log_frame)
        splitter.addWidget(email_frame)
        splitter.setSizes([600, 800])
        
        layout.addWidget(splitter)
        
        self.tab_widget.addTab(monitor_widget, "🖥️ Monitor")
    
    def create_centers_tab(self):
        centers_widget = QWidget()
        layout = QHBoxLayout(centers_widget)
        
        # Panel izquierdo - Vista de árbol de centros
        left_panel = QGroupBox("🏢 Centros por Empresa")
        left_layout = QVBoxLayout(left_panel)
        
        self.centers_tree = QTreeWidget()
        self.centers_tree.setHeaderLabel("Empresas y Centros")
        self.centers_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #0078d4;
            }
        """)
        self.populate_centers_tree()
        left_layout.addWidget(self.centers_tree)
        
        # Panel derecho - Edición
        right_panel = QGroupBox("✏️ Editar Centros")
        right_layout = QVBoxLayout(right_panel)
        
        # Seleccionar empresa
        empresa_layout = QHBoxLayout()
        empresa_label = QLabel("Empresa:")
        empresa_label.setStyleSheet("QLabel { color: #ffffff; }")
        empresa_layout.addWidget(empresa_label)
        self.empresa_combo = QComboBox()
        self.empresa_combo.addItems(list(self.centros_empresas.keys()))
        self.empresa_combo.currentTextChanged.connect(self.load_centers_for_empresa)
        self.empresa_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
        """)
        empresa_layout.addWidget(self.empresa_combo)
        right_layout.addLayout(empresa_layout)
        
        # Lista de centros para la empresa seleccionada
        centers_label = QLabel("Centros:")
        centers_label.setStyleSheet("QLabel { color: #ffffff; }")
        right_layout.addWidget(centers_label)
        self.centers_list = QListWidget()
        self.centers_list.setStyleSheet("""
            QListWidget {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
        """)
        right_layout.addWidget(self.centers_list)
        
        # Agregar nuevo centro
        add_layout = QHBoxLayout()
        self.new_center_input = QLineEdit()
        self.new_center_input.setPlaceholderText("Nombre del nuevo centro")
        self.new_center_input.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        add_button = QPushButton("➕ Agregar")
        add_button.clicked.connect(self.add_center)
        
        add_layout.addWidget(self.new_center_input)
        add_layout.addWidget(add_button)
        right_layout.addLayout(add_layout)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        remove_button = QPushButton("🗑️ Eliminar Seleccionado")
        save_centers_button = QPushButton("💾 Guardar Cambios")
        
        remove_button.clicked.connect(self.remove_center)
        save_centers_button.clicked.connect(self.save_centers_ui)
        
        buttons_layout.addWidget(remove_button)
        buttons_layout.addWidget(save_centers_button)
        right_layout.addLayout(buttons_layout)
        
        # Agregar paneles al layout principal
        layout.addWidget(left_panel, 2)
        layout.addWidget(right_panel, 1)
        
        # Cargar centros para la primera empresa
        if self.empresa_combo.count() > 0:
            self.load_centers_for_empresa(self.empresa_combo.currentText())
        
        self.tab_widget.addTab(centers_widget, "🏢 Centros")
    
    def populate_centers_tree(self):
        """Llenar el árbol con empresas y centros"""
        self.centers_tree.clear()
        
        for empresa, centros in self.centros_empresas.items():
            empresa_item = QTreeWidgetItem([f"🏢 {empresa} ({len(centros)} centros)"])
            
            for centro in sorted(centros):
                centro_item = QTreeWidgetItem([f"🏭 {centro}"])
                empresa_item.addChild(centro_item)
            
            self.centers_tree.addTopLevelItem(empresa_item)
            empresa_item.setExpanded(True)
    
    def load_centers_for_empresa(self, empresa):
        """Cargar centros para la empresa seleccionada"""
        self.centers_list.clear()
        
        if empresa in self.centros_empresas:
            for centro in sorted(self.centros_empresas[empresa]):
                self.centers_list.addItem(centro)
    
    def add_center(self):
        """Agregar nuevo centro a la empresa seleccionada"""
        empresa = self.empresa_combo.currentText()
        nuevo_centro = self.new_center_input.text().strip()
        
        if not nuevo_centro:
            QMessageBox.warning(self, "Advertencia", "⚠️ Ingrese el nombre del centro")
            return
        
        if nuevo_centro in self.centros_empresas[empresa]:
            QMessageBox.warning(self, "Advertencia", f"⚠️ El centro '{nuevo_centro}' ya existe")
            return
        
        self.centros_empresas[empresa].append(nuevo_centro)
        self.load_centers_for_empresa(empresa)
        self.populate_centers_tree()
        self.new_center_input.clear()
        
        self.add_log(f"✅ Centro '{nuevo_centro}' agregado a {empresa}", "SUCCESS")
    
    def remove_center(self):
        """Eliminar centro seleccionado"""
        current_item = self.centers_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Advertencia", "⚠️ Seleccione un centro para eliminar")
            return
        
        empresa = self.empresa_combo.currentText()
        centro = current_item.text()
        
        reply = QMessageBox.question(self, "Confirmar", 
                                   f"¿Está seguro de eliminar el centro '{centro}'?")
        
        if reply == QMessageBox.StandardButton.Yes:
            self.centros_empresas[empresa].remove(centro)
            self.load_centers_for_empresa(empresa)
            self.populate_centers_tree()
            
            self.add_log(f"🗑️ Centro '{centro}' eliminado de {empresa}", "INFO")
    
    def save_centers_ui(self):
        """Guardar cambios en centros desde la UI"""
        if self.save_centers():
            QMessageBox.information(self, "Éxito", "✅ Cambios en centros guardados correctamente")
            self.add_log("💾 Configuración de centros guardada", "SUCCESS")
        else:
            QMessageBox.critical(self, "Error", "❌ Error guardando centros")
    
    def create_config_tab(self):
        config_widget = QScrollArea()
        config_content = QWidget()
        layout = QVBoxLayout(config_content)
        
        # OpenAI Configuration
        openai_group = QGroupBox("🤖 Configuración OpenAI")
        openai_layout = QFormLayout(openai_group)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setText(self.config.get('openai_api_key', ''))
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.textChanged.connect(self.validate_openai_config)
        
        self.assistant_id_input = QLineEdit()
        self.assistant_id_input.setText(self.config.get('assistant_id', ''))
        self.assistant_id_input.setPlaceholderText("asst_...")
        self.assistant_id_input.textChanged.connect(self.validate_assistant_main)
        
        self.technical_assistant_id_input = QLineEdit()
        self.technical_assistant_id_input.setText(self.config.get('technical_assistant_id', ''))
        self.technical_assistant_id_input.setPlaceholderText("asst_...")
        self.technical_assistant_id_input.textChanged.connect(self.validate_assistant_tech)
        
        self.temperature_input = QSpinBox()
        self.temperature_input.setRange(0, 200)
        temp_value = self.config.get('temperature', 1.2)
        try:
            temp_float = float(str(temp_value).split('.')[0] + '.' + str(temp_value).split('.')[1][:2])
            temp_int = int(temp_float * 100)
        except (ValueError, IndexError):
            temp_int = 120
        self.temperature_input.setValue(temp_int)
        self.temperature_input.setSuffix("/100")
        
        openai_layout.addRow("API Key:", self.api_key_input)
        openai_layout.addRow("ID Asistente Principal:", self.assistant_id_input)
        openai_layout.addRow("ID Asistente Técnico:", self.technical_assistant_id_input)
        openai_layout.addRow("Temperatura:", self.temperature_input)
        
        # Email Configuration
        email_group = QGroupBox("📧 Configuración de Correo")
        email_layout = QFormLayout(email_group)
        
        self.email_address_input = QLineEdit()
        self.email_address_input.setText(self.config.get('email_address', ''))
        self.email_address_input.textChanged.connect(self.validate_email_config)
        
        self.email_password_input = QLineEdit()
        self.email_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.email_password_input.setText(self.config.get('email_password', ''))
        self.email_password_input.textChanged.connect(self.validate_email_config)
        
        self.smtp_server_input = QLineEdit()
        self.smtp_server_input.setText(self.config.get('smtp_server', 'smtp.gmail.com'))
        
        self.imap_server_input = QLineEdit()
        self.imap_server_input.setText(self.config.get('imap_server', 'imap.gmail.com'))
        
        self.smtp_port_input = QSpinBox()
        self.smtp_port_input.setRange(1, 65535)
        self.smtp_port_input.setValue(self.config.get('smtp_port', 587))
        
        # Destinatario de pruebas
        self.test_recipient_input = QLineEdit()
        self.test_recipient_input.setText(self.config.get('test_recipient', 'soporte@orcatecnologia.cl'))
        self.test_recipient_input.setPlaceholderText("correo@ejemplo.com")
        
        email_layout.addRow("Dirección de correo:", self.email_address_input)
        email_layout.addRow("Contraseña:", self.email_password_input)
        email_layout.addRow("Servidor SMTP:", self.smtp_server_input)
        email_layout.addRow("Servidor IMAP:", self.imap_server_input)
        email_layout.addRow("Puerto SMTP:", self.smtp_port_input)
        email_layout.addRow("Destinatario pruebas:", self.test_recipient_input)
        
        # Timing Configuration
        timing_group = QGroupBox("⏱️ Configuración de Tiempos")
        timing_layout = QFormLayout(timing_group)
        
        self.check_interval_input = QSpinBox()
        self.check_interval_input.setRange(10, 3600)
        self.check_interval_input.setValue(self.config.get('check_interval', 60))
        self.check_interval_input.setSuffix(" segundos")
        
        self.max_attempts_input = QSpinBox()
        self.max_attempts_input.setRange(1, 50)
        self.max_attempts_input.setValue(self.config.get('max_attempts', 10))
        
        self.wait_time_input = QSpinBox()
        self.wait_time_input.setRange(1, 300)
        self.wait_time_input.setValue(self.config.get('wait_time', 10))
        self.wait_time_input.setSuffix(" segundos")
        
        timing_layout.addRow("Intervalo de verificación:", self.check_interval_input)
        timing_layout.addRow("Máximos intentos:", self.max_attempts_input)
        timing_layout.addRow("Tiempo de espera:", self.wait_time_input)
        
        # Allowed senders
        senders_group = QGroupBox("👥 Remitentes Permitidos")
        senders_layout = QVBoxLayout(senders_group)
        
        # Cargar remitentes desde configuración JSON (SIEMPRE desde config)
        remitentes_actuales = self.config.get('remitentes_permitidos', DEFAULT_CONFIG['remitentes_permitidos'])
        
        # Log para debug
        self.add_log(f"🔧 Cargando remitentes en interfaz: {len(remitentes_actuales)} emails", "DEBUG")
        self.add_log(f"📋 Remitentes cargados: {remitentes_actuales}", "DEBUG")
        
        self.senders_display = QTextEdit()
        self.senders_display.setPlainText("\n".join(remitentes_actuales))
        self.senders_display.setMaximumHeight(150)
        senders_layout.addWidget(self.senders_display)
        
        # Botón para actualizar remitentes
        update_senders_button = QPushButton("💾 Guardar Remitentes y Destinatario")
        update_senders_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        update_senders_button.clicked.connect(self.update_senders_list)
        senders_layout.addWidget(update_senders_button)
        
        # Save button
        save_button = QPushButton("💾 Guardar Configuración")
        save_button.clicked.connect(self.save_config)
        
        layout.addWidget(openai_group)
        layout.addWidget(email_group)
        layout.addWidget(timing_group)
        layout.addWidget(senders_group)
        layout.addWidget(save_button)
        layout.addStretch()
        
        config_widget.setWidget(config_content)
        self.tab_widget.addTab(config_widget, "⚙️ Configuración")
        
    def create_test_tab(self):
        test_widget = QWidget()
        layout = QVBoxLayout(test_widget)
        
        # Test email section
        test_email_group = QGroupBox("📧 Prueba de Procesamiento de Correo")
        test_email_layout = QVBoxLayout(test_email_group)
        
        # Input fields for test email
        sender_layout = QHBoxLayout()
        sender_label = QLabel("De:")
        sender_label.setStyleSheet("QLabel { color: #ffffff; }")
        sender_layout.addWidget(sender_label)
        self.test_sender_input = QLineEdit()
        self.test_sender_input.setPlaceholderText("test@example.com")
        sender_layout.addWidget(self.test_sender_input)
        
        subject_layout = QHBoxLayout()
        subject_label = QLabel("Asunto:")
        subject_label.setStyleSheet("QLabel { color: #ffffff; }")
        subject_layout.addWidget(subject_label)
        self.test_subject_input = QLineEdit()
        self.test_subject_input.setPlaceholderText("Problema en centro Canal Luchin")
        subject_layout.addWidget(self.test_subject_input)
        
        # Destinatario personalizable
        recipient_layout = QHBoxLayout()
        recipient_label = QLabel("Para:")
        recipient_label.setStyleSheet("QLabel { color: #ffffff; }")
        recipient_layout.addWidget(recipient_label)
        self.test_recipient_display = QLineEdit()
        self.test_recipient_display.setText(self.config.get('test_recipient', 'soporte@orcatecnologia.cl'))
        self.test_recipient_display.setReadOnly(True)
        self.test_recipient_display.setStyleSheet("QLineEdit { background-color: #3a3a3a; }")
        recipient_layout.addWidget(self.test_recipient_display)
        
        test_email_layout.addLayout(sender_layout)
        test_email_layout.addLayout(subject_layout)
        test_email_layout.addLayout(recipient_layout)
        
        body_label = QLabel("Cuerpo del correo:")
        body_label.setStyleSheet("QLabel { color: #ffffff; }")
        test_email_layout.addWidget(body_label)
        self.test_body_input = QTextEdit()
        self.test_body_input.setPlaceholderText(
            "Estimados,\n\n"
            "Informamos que el centro Canal Luchin presenta desconexión de cámaras.\n"
            "No hay visual en central desde las 10:30 hrs.\n\n"
            "Saludos cordiales"
        )
        self.test_body_input.setMaximumHeight(150)
        test_email_layout.addWidget(self.test_body_input)
        
        # Test buttons
        test_buttons_layout = QHBoxLayout()
        self.test_process_button = QPushButton("🔄 Procesar Correo de Prueba")
        self.test_send_button = QPushButton("📤 Enviar Correo de Prueba REAL")
        self.clear_test_button = QPushButton("🧹 Limpiar")
        
        self.test_send_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        
        self.test_process_button.clicked.connect(self.test_process_email)
        self.test_send_button.clicked.connect(self.test_send_email)
        self.clear_test_button.clicked.connect(self.clear_test_inputs)
        
        test_buttons_layout.addWidget(self.test_process_button)
        test_buttons_layout.addWidget(self.test_send_button)
        test_buttons_layout.addWidget(self.clear_test_button)
        test_buttons_layout.addStretch()
        
        test_email_layout.addLayout(test_buttons_layout)
        
        # Test results
        results_label = QLabel("Resultados de la prueba:")
        results_label.setStyleSheet("QLabel { color: #ffffff; }")
        test_email_layout.addWidget(results_label)
        self.test_results = QTextEdit()
        self.test_results.setMaximumHeight(200)
        test_email_layout.addWidget(self.test_results)
        
        # API Test section
        api_test_group = QGroupBox("🌐 Prueba de APIs")
        api_test_layout = QVBoxLayout(api_test_group)
        
        api_buttons_layout = QHBoxLayout()
        self.test_openai_button = QPushButton("🤖 Probar OpenAI")
        self.test_email_conn_button = QPushButton("📧 Probar Conexión Email")
        self.test_api_centers_button = QPushButton("🏢 Probar API Centros")
        
        self.test_openai_button.clicked.connect(self.test_openai_connection)
        self.test_email_conn_button.clicked.connect(self.test_email_connection)
        self.test_api_centers_button.clicked.connect(self.test_centers_api)
        
        api_buttons_layout.addWidget(self.test_openai_button)
        api_buttons_layout.addWidget(self.test_email_conn_button)
        api_buttons_layout.addWidget(self.test_api_centers_button)
        api_buttons_layout.addStretch()
        
        api_test_layout.addLayout(api_buttons_layout)
        
        # API test results
        api_results_label = QLabel("Resultados de pruebas de API:")
        api_results_label.setStyleSheet("QLabel { color: #ffffff; }")
        api_test_layout.addWidget(api_results_label)
        self.api_test_results = QTextEdit()
        self.api_test_results.setMaximumHeight(150)
        api_test_layout.addWidget(self.api_test_results)
        
        # Quick actions
        quick_actions_group = QGroupBox("⚡ Acciones Rápidas")
        quick_actions_layout = QHBoxLayout(quick_actions_group)
        
        self.check_inbox_button = QPushButton("📬 Verificar Bandeja de Entrada")
        self.simulate_disconnect_button = QPushButton("🔴 Simular Desconexión")
        self.view_logs_button = QPushButton("📋 Ver Últimos Logs")
        
        self.check_inbox_button.clicked.connect(self.check_inbox_manually)
        self.simulate_disconnect_button.clicked.connect(self.simulate_disconnection)
        self.view_logs_button.clicked.connect(self.view_recent_logs)
        
        quick_actions_layout.addWidget(self.check_inbox_button)
        quick_actions_layout.addWidget(self.simulate_disconnect_button)
        quick_actions_layout.addWidget(self.view_logs_button)
        quick_actions_layout.addStretch()
        
        layout.addWidget(test_email_group)
        layout.addWidget(api_test_group)
        layout.addWidget(quick_actions_group)
        layout.addStretch()
        
        self.tab_widget.addTab(test_widget, "🧪 Pruebas")
        
    def create_logs_tab(self):
        logs_widget = QWidget()
        layout = QVBoxLayout(logs_widget)
        
        # Log controls
        log_controls_layout = QHBoxLayout()
        self.clear_logs_button = QPushButton("🧹 Limpiar Logs")
        self.save_logs_button = QPushButton("💾 Guardar Logs")
        self.auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self.auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_checkbox.setStyleSheet("QCheckBox { color: #ffffff; }")
        
        self.clear_logs_button.clicked.connect(self.clear_logs)
        self.save_logs_button.clicked.connect(self.save_logs)
        
        log_controls_layout.addWidget(self.clear_logs_button)
        log_controls_layout.addWidget(self.save_logs_button)
        log_controls_layout.addWidget(self.auto_scroll_checkbox)
        log_controls_layout.addStretch()
        
        # Log level filter
        filter_label = QLabel("Filtro:")
        filter_label.setStyleSheet("QLabel { color: #ffffff; }")
        log_controls_layout.addWidget(filter_label)
        self.log_level_filter = QComboBox()
        self.log_level_filter.addItems(["Todos", "INFO", "DEBUG", "ERROR", "SUCCESS"])
        self.log_level_filter.currentTextChanged.connect(self.filter_logs)
        log_controls_layout.addWidget(self.log_level_filter)
        
        layout.addLayout(log_controls_layout)
        
        # Detailed logs
        self.detailed_logs = QTextEdit()
        self.detailed_logs.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                line-height: 1.4;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.detailed_logs)
        
        self.tab_widget.addTab(logs_widget, "📄 Logs Detallados")
    
    def validate_all_configs(self):
        """Validar todas las configuraciones al inicio"""
        self.validate_email_config()
        self.validate_openai_config()
        self.validate_assistant_main()
        self.validate_assistant_tech()
        
    def validate_email_config(self):
        """Validar configuración de email en tiempo real"""
        email = self.email_address_input.text() if hasattr(self, 'email_address_input') else self.config.get('email_address', '')
        password = self.email_password_input.text() if hasattr(self, 'email_password_input') else self.config.get('email_password', '')
        
        if email and password and '@' in email:
            self.email_config_valid = True
            self.email_status_label.setText("📧 Email: ✅ Configurado")
            self.email_status_label.setStyleSheet("QLabel { color: #27ae60; font-weight: bold; }")
        else:
            self.email_config_valid = False
            self.email_status_label.setText("📧 Email: ❌ No configurado")
            self.email_status_label.setStyleSheet("QLabel { color: #e74c3c; font-weight: bold; }")
    
    def validate_openai_config(self):
        """Validar configuración de OpenAI"""
        api_key = self.api_key_input.text() if hasattr(self, 'api_key_input') else self.config.get('openai_api_key', '')
        
        if api_key and api_key.startswith('sk-'):
            self.openai_config_valid = True
            self.openai_status_label.setText("🤖 OpenAI: ✅ Configurado")
            self.openai_status_label.setStyleSheet("QLabel { color: #27ae60; font-weight: bold; }")
        else:
            self.openai_config_valid = False
            self.openai_status_label.setText("🤖 OpenAI: ❌ No configurado")
            self.openai_status_label.setStyleSheet("QLabel { color: #e74c3c; font-weight: bold; }")
    
    def validate_assistant_main(self):
        """Validar ID del asistente principal"""
        assistant_id = self.assistant_id_input.text() if hasattr(self, 'assistant_id_input') else self.config.get('assistant_id', '')
        
        if assistant_id and assistant_id.startswith('asst_'):
            self.assistant_main_valid = True
            self.assistant_main_status_label.setText("👨‍💼 Asist. Principal: ✅ Configurado")
            self.assistant_main_status_label.setStyleSheet("QLabel { color: #27ae60; font-weight: bold; }")
        else:
            self.assistant_main_valid = False
            self.assistant_main_status_label.setText("👨‍💼 Asist. Principal: ❌ No configurado")
            self.assistant_main_status_label.setStyleSheet("QLabel { color: #e74c3c; font-weight: bold; }")
    
    def validate_assistant_tech(self):
        """Validar ID del asistente técnico"""
        tech_id = self.technical_assistant_id_input.text() if hasattr(self, 'technical_assistant_id_input') else self.config.get('technical_assistant_id', '')
        
        if tech_id and tech_id.startswith('asst_'):
            self.assistant_tech_valid = True
            self.assistant_tech_status_label.setText("🔧 Asist. Técnico: ✅ Configurado")
            self.assistant_tech_status_label.setStyleSheet("QLabel { color: #27ae60; font-weight: bold; }")
        else:
            self.assistant_tech_valid = False
            self.assistant_tech_status_label.setText("🔧 Asist. Técnico: ❌ No configurado")
            self.assistant_tech_status_label.setStyleSheet("QLabel { color: #e74c3c; font-weight: bold; }")
    
    def update_senders_list(self):
        """Actualizar lista de remitentes permitidos desde el campo de texto"""
        try:
            # Obtener texto del campo y dividir por líneas
            senders_text = self.senders_display.toPlainText()
            senders_list = [email.strip() for email in senders_text.split('\n') if email.strip()]
            
            # Validar que sean emails válidos
            valid_senders = []
            for sender in senders_list:
                if '@' in sender and '.' in sender:
                    valid_senders.append(sender.lower())
                else:
                    self.add_log(f"⚠️ Email inválido ignorado: {sender}", "DEBUG")
            
            if valid_senders:
                # Actualizar configuración en memoria
                self.config['remitentes_permitidos'] = valid_senders
                
                # TAMBIÉN ACTUALIZAR EL DESTINATARIO DE PRUEBAS SI CAMBIÓ
                if hasattr(self, 'test_recipient_input'):
                    nuevo_destinatario = self.test_recipient_input.text().strip()
                    if nuevo_destinatario:
                        self.config['test_recipient'] = nuevo_destinatario
                        self.add_log(f"✅ Destinatario de pruebas actualizado: {nuevo_destinatario}", "DEBUG")
                
                # Actualizar variable global
                global REMITENTES_PERMITIDOS
                REMITENTES_PERMITIDOS = valid_senders
                
                # GUARDAR AUTOMÁTICAMENTE EN JSON
                success = self.save_config_to_json(self.config)
                
                if success:
                    self.add_log(f"✅ Remitentes y configuración guardados: {len(valid_senders)} emails", "SUCCESS")
                    
                    # Actualizar worker thread si está ejecutándose
                    if self.worker_thread:
                        self.worker_thread.config = self.config
                        self.add_log("🔄 Configuración actualizada en worker thread", "DEBUG")
                    
                    QMessageBox.information(self, "Éxito", 
                        f"✅ Configuración actualizada y guardada\n\n"
                        f"📧 {len(valid_senders)} remitentes guardados\n"
                        f"🎯 Destinatario pruebas: {self.config['test_recipient']}\n"
                        f"📁 Guardado en: email_assistant_config.json")
                else:
                    self.add_log(f"✅ Configuración actualizada en memoria: {len(valid_senders)} emails", "SUCCESS")
                    QMessageBox.warning(self, "Advertencia", 
                        "✅ Configuración actualizada en memoria\n"
                        "⚠️ Error guardando en archivo\n\n"
                        "Usa 'Guardar Configuración' para persistir los cambios")
                
                # Actualizar el display para mostrar emails limpiados
                self.senders_display.setPlainText("\n".join(valid_senders))
                
                # Actualizar destinatario en pruebas si existe el widget
                if hasattr(self, 'test_recipient_display'):
                    self.test_recipient_display.setText(self.config['test_recipient'])
                
            else:
                QMessageBox.warning(self, "Advertencia", "⚠️ No se encontraron emails válidos")
                
        except Exception as e:
            self.add_log(f"❌ Error actualizando configuración: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Error", f"❌ Error actualizando configuración: {str(e)}")
    
    def save_config(self):
        try:
            # Actualizar configuración desde UI
            self.config['openai_api_key'] = self.api_key_input.text()
            self.config['assistant_id'] = self.assistant_id_input.text()
            self.config['technical_assistant_id'] = self.technical_assistant_id_input.text()
            
            temp_value = self.temperature_input.value() / 100.0
            self.config['temperature'] = round(temp_value, 2)
            
            self.config['email_address'] = self.email_address_input.text()
            self.config['email_password'] = self.email_password_input.text()
            self.config['smtp_server'] = self.smtp_server_input.text()
            self.config['imap_server'] = self.imap_server_input.text()
            self.config['smtp_port'] = self.smtp_port_input.value()
            self.config['check_interval'] = self.check_interval_input.value()
            self.config['max_attempts'] = self.max_attempts_input.value()
            self.config['wait_time'] = self.wait_time_input.value()
            self.config['test_recipient'] = self.test_recipient_input.text()
            
            # Actualizar remitentes permitidos desde el campo de texto
            senders_text = self.senders_display.toPlainText()
            senders_list = [email.strip() for email in senders_text.split('\n') if email.strip()]
            if senders_list:
                self.config['remitentes_permitidos'] = senders_list
                # Actualizar variable global también
                global REMITENTES_PERMITIDOS
                REMITENTES_PERMITIDOS = senders_list
            
            # Guardar en archivo JSON
            success_config = self.save_config_to_json(self.config)
            success_centers = self.save_centers_to_json(self.centros_empresas)
            
            # También guardar en QSettings como respaldo
            for key, value in self.config.items():
                self.settings.setValue(key, value)
            self.settings.sync()
            
            # Actualizar validaciones
            self.validate_all_configs()
            
            # Actualizar destinatario en pruebas
            if hasattr(self, 'test_recipient_display'):
                self.test_recipient_display.setText(self.config['test_recipient'])
            
            if success_config and success_centers:
                QMessageBox.information(self, "Éxito", 
                    "✅ Configuración guardada correctamente\n\n"
                    "📁 Archivos creados:\n"
                    "• email_assistant_config.json\n" 
                    "• email_assistant_centers.json\n\n"
                    f"📧 Remitentes permitidos: {len(self.config['remitentes_permitidos'])}")
                self.add_log("✅ Configuración y centros guardados en archivos JSON", "SUCCESS")
                self.add_log(f"📧 Remitentes permitidos guardados: {self.config['remitentes_permitidos']}", "DEBUG")
            else:
                QMessageBox.warning(self, "Advertencia", 
                    "⚠️ Configuración guardada parcialmente\n"
                    "Revise los logs para más detalles")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"❌ Error guardando configuración: {str(e)}")
            self.add_log(f"❌ Error guardando configuración: {str(e)}", "ERROR")
    
    def start_assistant(self):
        if not (self.email_config_valid and self.openai_config_valid):
            QMessageBox.warning(self, "Configuración Incompleta", 
                              "⚠️ Por favor configure correctamente Email y OpenAI antes de iniciar")
            return
        
        # Asegurar que el worker thread tenga la configuración más actualizada
        self.worker_thread = EmailWorkerThread(self.config.copy(), self.centros_empresas.copy())
        self.worker_thread.log_signal.connect(self.add_log)
        self.worker_thread.email_processed_signal.connect(self.add_email_to_table)
        self.worker_thread.stats_updated_signal.connect(self.update_stats)
        self.worker_thread.inbox_count_signal.connect(self.update_inbox_stats)
        
        self.worker_thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.statusBar().showMessage("🟢 Asistente ejecutándose...")
        self.add_log("🚀 Asistente de correo iniciado", "SUCCESS")
        
        # Log de configuración actual
        remitentes = self.config.get('remitentes_permitidos', REMITENTES_PERMITIDOS)
        self.add_log(f"📧 Remitentes permitidos cargados: {len(remitentes)}", "DEBUG")
        self.add_log(f"📧 Lista actual: {remitentes}", "DEBUG")
    
    def stop_assistant(self):
        if self.worker_thread:
            self.worker_thread.stop()
            self.worker_thread.wait()
            self.worker_thread = None
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("🔴 Asistente detenido")
        self.add_log("⏹️ Asistente de correo detenido", "INFO")
    
    def add_log(self, message, level="INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        colors = {
            "INFO": "#ffffff",
            "DEBUG": "#cccccc", 
            "ERROR": "#ff6b6b",
            "SUCCESS": "#51cf66"
        }
        
        color = colors.get(level, "#ffffff")
        formatted_message = f'<span style="color: {color}">[{timestamp}] {message}</span>'
        
        self.log_display.append(formatted_message)
        
        detailed_message = f"[{timestamp}] [{level}] {message}"
        self.detailed_logs.append(detailed_message)
        
        if hasattr(self, 'auto_scroll_checkbox') and self.auto_scroll_checkbox.isChecked():
            self.log_display.moveCursor(QTextCursor.MoveOperation.End)
            self.detailed_logs.moveCursor(QTextCursor.MoveOperation.End)
    
    def add_email_to_table(self, email_data):
        row_count = self.email_table.rowCount()
        self.email_table.insertRow(row_count)
        
        self.email_table.setItem(row_count, 0, QTableWidgetItem(email_data['timestamp']))
        self.email_table.setItem(row_count, 1, QTableWidgetItem(email_data['from']))
        self.email_table.setItem(row_count, 2, QTableWidgetItem(email_data['subject']))
        self.email_table.setItem(row_count, 3, QTableWidgetItem(email_data['body_preview']))
        self.email_table.setItem(row_count, 4, QTableWidgetItem(email_data['status']))
        
        self.email_table.scrollToBottom()
    
    def update_stats(self, total, responded):
        self.stats_label.setText(f"📊 Correos: {total} | Respondidos: {responded}")
    
    def update_inbox_stats(self, total, unread):
        self.inbox_stats_label.setText(f"📬 Bandeja: {total} correos totales | {unread} no leídos")
    
    def test_process_email(self):
        if not self.config.get('openai_api_key'):
            QMessageBox.warning(self, "Configuración", "⚠️ Configure la API Key de OpenAI primero")
            return
        
        sender = self.test_sender_input.text() or "test@example.com"
        subject = self.test_subject_input.text() or "Test"
        body = self.test_body_input.toPlainText() or "Test body"
        
        self.test_results.clear()
        self.test_results.append("🔄 Procesando correo de prueba...\n")
        
        try:
            centros = self.detect_centers_in_text(body + " " + subject)
            if centros:
                self.test_results.append(f"✅ Centros detectados: {centros}\n")
            else:
                self.test_results.append("ℹ️ No se detectaron centros\n")
            
            disconnect_terms = ["desconexión", "sin enlace", "sin visual", "ping"]
            text_lower = (body + " " + subject).lower()
            disconnection = any(term in text_lower for term in disconnect_terms)
            
            if disconnection:
                self.test_results.append("🔴 Desconexión detectada\n")
            else:
                self.test_results.append("🟢 No se detectó desconexión\n")
            
            # Usar la lista actualizada de remitentes permitidos
            remitentes_actuales = self.config.get('remitentes_permitidos', REMITENTES_PERMITIDOS)
            allowed = sender.lower() in [email.lower() for email in remitentes_actuales]
            if allowed:
                self.test_results.append("✅ Remitente permitido\n")
            else:
                self.test_results.append("⚠️ Remitente no está en lista permitida\n")
                self.test_results.append(f"📋 Remitentes permitidos actuales: {len(remitentes_actuales)}\n")
                
            self.test_results.append("✅ Procesamiento de prueba completado")
            
        except Exception as e:
            self.test_results.append(f"❌ Error en procesamiento: {str(e)}")
    
    def test_send_email(self):
        if not self.config.get('email_password'):
            QMessageBox.warning(self, "Configuración", "⚠️ Configure la contraseña del correo primero")
            return
        
        recipient = self.config.get('test_recipient', 'soporte@orcatecnologia.cl')
        
        reply = QMessageBox.question(self, "Confirmar Envío", 
                                   f"⚠️ ¿Está seguro de enviar un correo REAL de prueba?\n\n"
                                   f"Se enviará a: {recipient}")
        
        if reply != QMessageBox.StandardButton.Yes:
            self.test_results.append("❌ Envío de prueba cancelado por el usuario\n")
            return
            
        try:
            sender = self.test_sender_input.text() or "test@example.com"
            subject = self.test_subject_input.text() or "Prueba de Asistente"
            body = self.test_body_input.toPlainText() or "Este es un correo de prueba."
            
            msg = MIMEMultipart()
            msg['From'] = self.config['email_address']
            msg['To'] = recipient
            msg['Subject'] = f"PRUEBA - {subject}"
            
            email_body = f"""
            <h3>🧪 CORREO DE PRUEBA</h3>
            <p><strong>Enviado desde:</strong> Asistente de Correo Electrónico</p>
            <p><strong>Remitente simulado:</strong> {sender}</p>
            <p><strong>Asunto original:</strong> {subject}</p>
            <hr>
            <p><strong>Cuerpo del mensaje:</strong></p>
            <p>{body.replace(chr(10), '<br>')}</p>
            <hr>
            <p><em>Este es un correo de prueba generado automáticamente.</em></p>
            """
            
            msg.attach(MIMEText(email_body, 'html'))
            
            self.test_results.append("📤 Enviando correo de prueba...\n")
            
            servidor = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            servidor.starttls()
            servidor.login(self.config['email_address'], self.config['email_password'])
            servidor.sendmail(self.config['email_address'], [recipient], msg.as_string())
            servidor.quit()
            
            self.test_results.append("✅ ¡Correo de prueba enviado exitosamente!\n")
            self.test_results.append(f"📧 Enviado a: {recipient}\n")
            self.add_log(f"📤 Correo de prueba enviado a {recipient}", "SUCCESS")
            
        except Exception as e:
            self.test_results.append(f"❌ Error enviando correo de prueba: {str(e)}\n")
            self.add_log(f"❌ Error enviando correo de prueba: {str(e)}", "ERROR")
    
    def clear_test_inputs(self):
        self.test_sender_input.clear()
        self.test_subject_input.clear()
        self.test_body_input.clear()
        self.test_results.clear()
    
    def test_openai_connection(self):
        if not self.config.get('openai_api_key'):
            self.api_test_results.append("❌ API Key no configurada")
            return
        
        try:
            headers = {
                'Authorization': f'Bearer {self.config["openai_api_key"]}',
                'Content-Type': 'application/json',
                'OpenAI-Beta': 'assistants=v2'
            }
            
            response = requests.post("https://api.openai.com/v1/threads", 
                                   headers=headers, json={}, timeout=10)
            
            if response.status_code == 200:
                self.api_test_results.append("✅ OpenAI: Conexión exitosa")
                self.add_log("✅ Prueba OpenAI exitosa", "SUCCESS")
            else:
                self.api_test_results.append(f"❌ OpenAI: Error {response.status_code}")
                self.add_log(f"❌ Error OpenAI: {response.status_code}", "ERROR")
                
        except Exception as e:
            self.api_test_results.append(f"❌ OpenAI: {str(e)}")
            self.add_log(f"❌ Error prueba OpenAI: {str(e)}", "ERROR")
    
    def test_email_connection(self):
        try:
            mail = imaplib.IMAP4_SSL(self.config['imap_server'])
            mail.login(self.config['email_address'], self.config['email_password'])
            mail.select('inbox')
            
            status, messages = mail.search(None, 'ALL')
            total = len(messages[0].split()) if messages[0] else 0
            
            status, unread = mail.search(None, '(UNSEEN)')
            unread_count = len(unread[0].split()) if unread[0] else 0
            
            mail.close()
            mail.logout()
            
            self.api_test_results.append(f"✅ Email IMAP: Conexión exitosa ({total} correos, {unread_count} no leídos)")
            
            servidor = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            servidor.starttls()
            servidor.login(self.config['email_address'], self.config['email_password'])
            servidor.quit()
            
            self.api_test_results.append("✅ Email SMTP: Conexión exitosa")
            self.add_log("✅ Prueba conexión email exitosa", "SUCCESS")
            
        except Exception as e:
            self.api_test_results.append(f"❌ Email: {str(e)}")
            self.add_log(f"❌ Error prueba email: {str(e)}", "ERROR")
    
    def test_centers_api(self):
        try:
            response = requests.get("https://apiacopio.orcawan.uk/api/acopio", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.api_test_results.append(f"✅ API Cermaq: Disponible - Status: {data.get('centerStatus', 'N/A')}")
            else:
                self.api_test_results.append(f"⚠️ API Cermaq: Error {response.status_code}")
            
            response = requests.get("https://apihuapi.orcawan.uk/api/canalluchin", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.api_test_results.append(f"✅ API AquaChile: Disponible - Status: {data.get('centerStatus', 'N/A')}")
            else:
                self.api_test_results.append(f"⚠️ API AquaChile: Error {response.status_code}")
            
            self.add_log("✅ Prueba APIs centros completada", "SUCCESS")
                
        except Exception as e:
            self.api_test_results.append(f"❌ APIs Centros: {str(e)}")
            self.add_log(f"❌ Error prueba APIs: {str(e)}", "ERROR")
    
    def check_inbox_manually(self):
        if self.worker_thread:
            self.worker_thread.request_inbox_check()
        else:
            try:
                mail = imaplib.IMAP4_SSL(self.config['imap_server'])
                mail.login(self.config['email_address'], self.config['email_password'])
                mail.select('inbox')
                
                status, all_messages = mail.search(None, 'ALL')
                total_emails = len(all_messages[0].split()) if all_messages[0] else 0
                
                status, unread_messages = mail.search(None, '(UNSEEN)')
                unread_emails = len(unread_messages[0].split()) if unread_messages[0] else 0
                
                mail.close()
                mail.logout()
                
                self.update_inbox_stats(total_emails, unread_emails)
                self.add_log(f"📊 Verificación manual: {total_emails} correos totales, {unread_emails} no leídos", "INFO")
                
            except Exception as e:
                self.add_log(f"❌ Error en verificación manual: {str(e)}", "ERROR")
    
    def simulate_disconnection(self):
        test_email = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'from': 'test@aquachile.com',
            'subject': 'Desconexión Canal Luchin',
            'body_preview': 'Sin visual en cámaras del centro Canal Luchin...',
            'status': 'Simulado'
        }
        self.add_email_to_table(test_email)
        self.add_log("🔴 Simulación de desconexión agregada", "DEBUG")
    
    def view_recent_logs(self):
        self.tab_widget.setCurrentIndex(4)
        self.add_log("👀 Mostrando logs recientes", "INFO")
    
    def clear_logs(self):
        self.log_display.clear()
        self.detailed_logs.clear()
        self.add_log("🧹 Logs limpiados", "INFO")
    
    def save_logs(self):
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"email_assistant_logs_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.detailed_logs.toPlainText())
            
            QMessageBox.information(self, "Logs Guardados", 
                                  f"✅ Logs guardados en: {filename}")
            self.add_log(f"💾 Logs guardados en {filename}", "SUCCESS")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"❌ Error guardando logs: {str(e)}")
    
    def filter_logs(self, filter_level):
        if filter_level == "Todos":
            pass
        else:
            self.add_log(f"🔍 Filtro aplicado: {filter_level}", "DEBUG")
    
    def detect_centers_in_text(self, text):
        text_lower = text.lower()
        found_centers = {}
        
        for empresa, centros in self.centros_empresas.items():
            for centro in centros:
                if centro.lower() in text_lower:
                    if empresa not in found_centers:
                        found_centers[empresa] = []
                    found_centers[empresa].append(centro)
        
        return found_centers if found_centers else None
    
    def closeEvent(self, event):
        if self.worker_thread:
            self.stop_assistant()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Email Assistant")
    app.setApplicationVersion("1.0")
    
    # Dark theme
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QTabWidget::pane {
            border: 1px solid #555555;
            background-color: #ffffff;
        }
        QTabBar::tab {
            background-color: #3a3a3a;
            color: #ffffff;
            padding: 8px 16px;
            margin-right: 2px;
            border: 1px solid #555555;
        }
        QTabBar::tab:selected {
            background-color: #ffffff;
            color: #000000;
            border-bottom: 2px solid #0078d4;
        }
        QTabBar::tab:hover {
            background-color: #4a4a4a;
        }
        QPushButton {
            background-color: #0078d4;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #106ebe;
        }
        QPushButton:pressed {
            background-color: #005a9e;
        }
        QPushButton:disabled {
            background-color: #666666;
            color: #cccccc;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #555555;
            border-radius: 8px;
            margin-top: 1ex;
            padding-top: 10px;
            color: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
            color: #ffffff;
        }
        QLineEdit {
            background-color: #3a3a3a;
            color: #ffffff;
            padding: 6px;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QTextEdit {
            background-color: #3a3a3a;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QTreeWidget {
            background-color: #3a3a3a;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QListWidget {
            background-color: #3a3a3a;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QComboBox {
            background-color: #3a3a3a;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px;
        }
        QComboBox QAbstractItemView {
            background-color: #3a3a3a;
            color: #ffffff;
            selection-background-color: #0078d4;
        }
        QSpinBox {
            background-color: #3a3a3a;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px;
        }
        QCheckBox {
            color: #ffffff;
        }
        QLabel {
            color: #ffffff;
        }
        QScrollArea {
            background-color: #2b2b2b;
        }
        QStatusBar {
            background-color: #3a3a3a;
            color: #ffffff;
        }
    """)
    
    window = EmailAssistantGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
