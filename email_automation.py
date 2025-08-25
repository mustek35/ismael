import os
from email import message_from_string
import requests
from dotenv import load_dotenv
import imaplib
import email
import re
import subprocess
import psycopg2
from psycopg2 import sql
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import smtplib
import time
from datetime import datetime
import pytz  # Para manejo de zonas horarias
from centros import CENTROS_EMPRESAS
from asistente_tecnico_api import limpiar_contenido_api
from asistente_tecnico_api import asistente_tecnico_por_empresa
from asistente_tecnico_api import consultar_api_por_empresa  # Aquí se importa la función
import json





# Cargar la clave de API de OpenAI desde un archivo .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# Configuración del correo
EMAIL = "ismael@orcatecnologia.cl"
PASSWORD = "fytb lgbz gkht clsb"
SMTP_SERVER = "smtp.gmail.com"
IMAP_SERVER = "imap.gmail.com"
SMTP_PORT = 587

# ID del thread del asistente 'Ismael'
thread_id = "thread_nHRORhtOPhMFdAcXv75tZzR5"

# Lista de remitentes permitidos
REMITENTES_PERMITIDOS = [
    "centralseguridadsay@salmonesaysen.cl",
    "vigilancia2@aquachile.com",
    "seguridad@caletabay.cl",
    "cespinoza.cast@gmail.com"
]

# Variables para conteo de correos
total_correos = 0
total_respondidos = 0

# Función para conectarse a la base de datos
def get_db_connection():
    return psycopg2.connect(
        host='179.57.170.61',
        port='24301',
        database='chatgpt',
        user='orca',
        password='estadoscam.'
    )

# Función para registrar una falla en la tabla 'historial_fallas'
def registrar_falla(remitente, correo, asunto, cuerpo, falla_identificada, es_fisico, referencia_db):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = '''
        INSERT INTO historial_fallas (remitente, correo, asunto, cuerpo, falla_identificada, es_fisico, referencia_db)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        '''

        cursor.execute(query, (remitente, correo, asunto, cuerpo, falla_identificada, es_fisico, referencia_db))
        conn.commit()

        print(f"Falla registrada exitosamente para {remitente} ({correo})")

    except Exception as e:
        print(f"Error al registrar la falla: {e}")
    
    finally:
        cursor.close()
        conn.close()

# Función para obtener el saludo dependiendo de la hora en Chile
def obtener_saludo():
    chile_tz = pytz.timezone('America/Santiago')
    hora_actual = datetime.now(chile_tz).hour

    if 5 <= hora_actual < 12:
        return "Hola buenos días"
    elif 12 <= hora_actual < 18:
        return "Hola buenas tardes"
    else:
        return "Hola buenas noches"

def contar_total_correos():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, PASSWORD)
    mail.select('inbox')
    status, mensajes = mail.search(None, 'ALL')
    total = len(mensajes[0].split())
    return total

def obtener_cuerpo(mensaje):
    if mensaje.is_multipart():
        for parte in mensaje.walk():
            if parte.get_content_type() == 'text/plain':
                try:
                    return parte.get_payload(decode=True).decode('utf-8')
                except UnicodeDecodeError:
                    # Intentar con otra codificación en caso de que utf-8 falle
                    return parte.get_payload(decode=True).decode('latin-1')
    else:
        try:
            return mensaje.get_payload(decode=True).decode('utf-8')
        except UnicodeDecodeError:
            return mensaje.get_payload(decode=True).decode('latin-1')



def leer_correo():
    """Función para leer correos no leídos (nuevos)"""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, PASSWORD)
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
                    cuerpo = obtener_cuerpo(mensaje)
                    print(f"DEBUG: Nuevo correo recibido: {asunto} de {remitente}")
                    print(f"DEBUG: Cuerpo del correo:\n{cuerpo}\n")
                    return asunto, remitente, cuerpo, mensaje
    return None, None, None, None

def obtener_nombre(remitente):
    """Extraer el nombre del remitente a partir del formato 'Nombre <correo@example.com>'."""
    match = re.match(r"([\w\s]+)\s*<.*>", remitente)
    if match:
        nombre_completo = match.group(1).strip()
        return nombre_completo
    else:
        return "Usuario"
    
# Función para crear un nuevo thread en la API de OpenAI
def crear_thread():
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'
    }

    url = "https://api.openai.com/v1/threads"
    data = {}

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        thread_data = response.json()
        return thread_data.get("id")  # Devolver el nuevo thread_id
    else:
        print(f"Error al crear un nuevo thread: {response.status_code} - {response.text}")
        return None

# Dentro de la función procesar_con_chatgpt (o donde detectes las respuestas)
def procesar_con_chatgpt(cuerpo_correo, asunto_correo):
    """Procesa el correo recibido y la respuesta del asistente para detectar si es una falla de desconexión o ping."""
    
    # Lista ampliada de términos que podrían indicar una desconexión o problema de conexión
    terminos_desconexion = [
        "desconexión", "sin conexión", "sin enlace", "sin visual", "ping", "problema de enlace",
        "cámaras sin visual", "no hay visual en central", "desconectado", "desconectada",
        "no hay visual de camaras", "desconexion", "camaras en negro", "camara termal", 
        "camara ptz", "ni visual", "no hay conexión", "sin conexión en", "falta de conexión", 
        "sin conexion", "pérdida de conexión", "no responde", "sin respuesta", 
        "falla de comunicación", "conexión interrumpida", "caída de enlace", "enlace caído", 
        "problema de red", "fallo en la red", "pérdida de enlace", "falla en la red", 
        "no tengo enlace", "no hay señal", "no se puede conectar", "problema de conectividad", 
        "no se visualizan", "sin respuesta del servidor", "conexión perdida", "corte de conexión", 
        "falla de conectividad", "no se ve", "no llegan los datos", "no hay comunicación", 
        "desconectado de la red", "sin datos", "pérdida de datos", "enlace perdido", 
        "red caída", "falla de conexión", "no hay respuesta de la red", "problemas con la red", 
        "interrupción de la conexión", "pérdida de comunicación", "no hay enlace"
    ]
    
    nuevo_thread_id = crear_thread()
    
    if nuevo_thread_id:
        mensaje_id = agregar_mensaje_al_thread(nuevo_thread_id, cuerpo_correo)
        if mensaje_id:
            resultado = ejecutar_thread(nuevo_thread_id)
            if resultado:
                # Eliminar cualquier referencia a documentos o manuales de la respuesta del asistente
                resultado = limpiar_referencia_documentos(resultado)
                
                # Capturar el nombre del centro desde el cuerpo del correo
                centros = capturar_centros(cuerpo_correo, asunto_correo)
                if centros:
                    print(f"DEBUG: Centros de cultivo detectados: {centros}")
                else:
                    print("DEBUG: No se detectó un nombre de centro de cultivo.")
                
                # Detectar si se menciona una desconexión o falta de visual en el cuerpo del correo
                desconexion_detectada_en_correo = any(termino in cuerpo_correo.lower() for termino in terminos_desconexion)
                
                # Detectar si se menciona una desconexión o falta de visual en la respuesta del asistente
                desconexion_detectada_en_respuesta = any(termino in resultado.lower() for termino in terminos_desconexion)
                
                # Determinar si se detectó una desconexión en el correo o en la respuesta del asistente
                desconexion_detectada = desconexion_detectada_en_correo or desconexion_detectada_en_respuesta
                
                if desconexion_detectada:
                    print("DEBUG: Se detectó una falla de conexión (desconexión o problema de enlace).")
                else:
                    print("DEBUG: No se detectó una falla de conexión ni en el correo ni en la respuesta del asistente.")
                
                # Devolver los centros detectados y el estado de la desconexión
                return centros, desconexion_detectada
            else:
                print("Error al ejecutar el thread.")
                return None, False
        else:
            print("Error al agregar el mensaje al thread.")
            return None, False
    else:
        print("Error al crear el thread.")
        return None, False


    
def capturar_centros(cuerpo, asunto):
    """Extrae los nombres de centros de cultivo específicos del cuerpo y asunto del correo, organizados por empresa."""
    # Convertir el cuerpo y asunto del correo a minúsculas para hacer una búsqueda insensible a mayúsculas
    cuerpo_lower = cuerpo.lower()
    asunto_lower = asunto.lower()

    # Diccionario para almacenar los centros encontrados por empresa
    centros_encontrados = {}

    # Verificar centros por empresa
    for empresa, centros in CENTROS_EMPRESAS.items():
        for centro in centros:
            # Convertir el nombre del centro a minúsculas para la comparación
            centro_lower = centro.lower()

            # Si el centro aparece en el cuerpo o en el asunto del correo
            if centro_lower in cuerpo_lower or centro_lower in asunto_lower:
                # Añadir el centro bajo la empresa correspondiente
                if empresa not in centros_encontrados:
                    centros_encontrados[empresa] = []
                centros_encontrados[empresa].append(centro)

    # Si se detectaron centros, devolver el diccionario de centros encontrados por empresa
    if centros_encontrados:
        return centros_encontrados
    return None




def limpiar_referencia_documentos(texto):
    """Elimina cualquier referencia a manuales o archivos del texto."""
    # Esto elimina cualquier patrón de referencia a manuales o archivos del tipo 【X:X†Nombre del archivo】
    return re.sub(r'【\d+:\d+†[^\]]+\】', '', texto)

def obtener_mensajes_thread(thread_id):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'
    }

    url = f"https://api.openai.com/v1/threads/{thread_id}/messages"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        mensajes_data = response.json()
        print(f"DEBUG: Mensajes del thread: {mensajes_data}")
        
        # Filtrar los mensajes que vienen del asistente
        for message in mensajes_data.get("data", []):
            if message.get("role") == "assistant":  # Filtrar solo los mensajes del asistente
                return message["content"][0]["text"]["value"]  # Extraer el texto de la respuesta
        
        print("DEBUG: No se encontró una respuesta del asistente en los mensajes del thread.")
        return None
    else:
        print(f"Error al obtener los mensajes del thread: {response.status_code} - {response.text}")
        return None
    
def obtener_estado_thread(thread_id):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'
    }

    url = f"https://api.openai.com/v1/threads/{thread_id}/runs"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        thread_data = response.json()
        print(f"DEBUG: Respuesta de la API al obtener el estado del thread: {thread_data}")
        
        # Verificar si hay datos en la lista 'data'
        runs = thread_data.get("data", [])
        if runs:
            for run in runs:
                if run['status'] == 'completed':  
                    return run['status']
            return runs[0].get("status")
        else:
            print("DEBUG: No se encontraron runs en la respuesta.")
            return None
    else:
        print(f"Error al obtener el estado del thread: {response.status_code} - {response.text}")
        return None    
    

# Función para agregar un mensaje al thread con el encabezado 'OpenAI-Beta'
def agregar_mensaje_al_thread(thread_id, content):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'  # Encabezado requerido
    }

    url = f"https://api.openai.com/v1/threads/{thread_id}/messages"
    data = {
        "role": "user",
        "content": content
    }

    print(f"DEBUG: Enviando el siguiente contenido al thread: {content}")

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        message_data = response.json()
        return message_data['id']
    else:
        print(f"Error al agregar mensaje: {response.status_code} - {response.text}")
        return None


# Función para obtener la respuesta del thread
def obtener_respuesta_thread(run_id):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'
    }

    url = f"https://api.openai.com/v1/threads/{thread_id}/runs/{run_id}"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        run_data = response.json()
        print(f"DEBUG: Estado del thread: {run_data.get('status')}")
        if run_data.get("status") == "completed":
            messages = run_data.get("messages", [])
            for message in messages:
                if message.get("role") == "assistant":
                    return message.get("content")
            print("DEBUG: No se encontró una respuesta del asistente en el thread completado.")
        else:
            print(f"DEBUG: El thread aún no está completado: {run_data.get('status')}")
            return None

    else:
        print(f"Error al obtener respuesta del thread: {response.status_code} - {response.text}")
        return None

# Función para ejecutar el thread con tu asistente
def ejecutar_thread(thread_id, assistant_id="asst_RO6jvTXoyyu6WmwL6w9imlvF"):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'
    }

    url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
    data = {
        "assistant_id": assistant_id,
        "temperature": 1.2,  # Ajustar para respuestas más centradas
        "top_p": 1,  # Ajustar para reducir la probabilidad de respuestas menos relevantes
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        run_data = response.json()
        run_id = run_data.get("id")

        # Intentar obtener el estado varias veces
        max_attempts = 10
        wait_time = 10

        for attempt in range(max_attempts):
            print(f"DEBUG: Intentando obtener el estado del thread (intento {attempt + 1}/{max_attempts})...")
            time.sleep(wait_time)

            thread_status = obtener_estado_thread(thread_id)
            if thread_status == "completed":
                print("DEBUG: Thread completado.")
                return obtener_mensajes_thread(thread_id)
            elif thread_status == "failed":
                print("DEBUG: El thread falló.")
                break
            elif thread_status == "queued":
                print(f"DEBUG: El thread sigue en cola, esperando {wait_time} segundos más...")
            else:
                print(f"DEBUG: Estado inesperado del thread: {thread_status}")

        print("DEBUG: No se pudo completar el thread después de varios intentos.")
        return None
    else:
        print(f"Error al ejecutar thread: {response.status_code} - {response.text}")
        return None

def obtener_cc_existente(mensaje_original):
    """Extraer el campo 'Cc' del correo original si existe."""
    if 'Cc' in mensaje_original:
        cc_list = mensaje_original['Cc'].split(',')
        return [correo.strip() for correo in cc_list]
    return []

def enviar_correo_en_hilo(respuesta_primaria, respuesta_tecnica, remitente, asunto, mensaje_original, remitente_fijo="soporte@orcatecnologia.cl", cc=None):
    msg = MIMEMultipart()
    msg['From'] = EMAIL
    msg['To'] = remitente_fijo  # Siempre enviamos a cespinoza@orcatecnologia.cl

    # Si mensaje_original es una cadena, convertirla a un objeto de correo
    if isinstance(mensaje_original, str):
        mensaje_original = message_from_string(mensaje_original)

    # Verificamos si 'Message-ID' existe en el correo original para incluirlo en las referencias
    in_reply_to = mensaje_original.get('Message-ID', None)
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = in_reply_to
    
    msg['Subject'] = f"Re: {asunto}"

    # Eliminar los asteriscos dobles de la respuesta antes de enviarla
    respuesta_primaria = respuesta_primaria.replace('**', '')
    respuesta_tecnica = respuesta_tecnica.replace('**', '')

    # Crear el cuerpo del correo en HTML, asegurando que mantenga el formato
    html_body = f"""
    <p>{respuesta_primaria.replace('\n', '<br>')}</p>
    <p>{respuesta_tecnica.replace('\n', '<br>')}</p>
    <img src="cid:firma" alt="Firma" />
    """
    
    msg.attach(MIMEText(html_body, 'html'))

    # Adjuntar la imagen de firma
    with open("/home/spnz/email_automation/firma.gif", 'rb') as f:
        img = MIMEImage(f.read())
        img.add_header('Content-ID', '<firma>')
        msg.attach(img)

    # Añadir destinatarios: remitente fijo cespinoza@orcatecnologia.cl
    destinatarios = [remitente_fijo]  # Solo enviamos a cespinoza@orcatecnologia.cl
    if cc:
        destinatarios += cc

    # Enviar el correo
    servidor = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    servidor.starttls()
    servidor.login(EMAIL, PASSWORD)
    servidor.sendmail(EMAIL, destinatarios, msg.as_string())
    servidor.quit()



def es_remitente_permitido(remitente):
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', remitente)
    if email_match:
        remitente_email = email_match.group(0).lower()
        return remitente_email in REMITENTES_PERMITIDOS
    return False




def main():
    global total_correos, total_respondidos
    print("DEBUG: Iniciando la función principal...")  # Depuración inicial

    while True:
        total_en_bandeja = contar_total_correos()
        print(f"DEBUG: Total de correos en la bandeja de entrada: {total_en_bandeja}")

        asunto, remitente, cuerpo, mensaje_original = leer_correo()
        if cuerpo and es_remitente_permitido(remitente):
            total_correos += 1
            print(f"DEBUG: El correo de {remitente} está en la lista permitida.")

            # Crear el thread del asistente principal (Ismael)
            thread_id_principal = crear_thread()
            if thread_id_principal:
                print(f"DEBUG: Thread del asistente principal creado: {thread_id_principal}")
                
                # Enviar el mensaje del correo original al thread del asistente principal
                mensaje_id_principal = agregar_mensaje_al_thread(thread_id_principal, cuerpo)
                if mensaje_id_principal:
                    print(f"DEBUG: Mensaje enviado al thread principal. ID del mensaje: {mensaje_id_principal}")

                    # Ejecutar el thread para obtener la respuesta del asistente principal
                    respuesta_primaria = ejecutar_thread(thread_id_principal)
                    if respuesta_primaria:
                        print(f"DEBUG: Respuesta del asistente principal obtenida: {respuesta_primaria}")

                        # Enviar el primer correo con la respuesta del asistente principal
                        enviar_correo_en_hilo(respuesta_primaria, "", remitente, asunto, mensaje_original)
                        print(f"DEBUG: Primer correo enviado con éxito a {remitente}.")
                        
                        # Detectar si hay una falla de conexión en el mensaje original
                        centros_detectados, desconexion_detectada = procesar_con_chatgpt(cuerpo, asunto)

                        if desconexion_detectada:
                            print("DEBUG: Se detectó una desconexión. Ejecutando el asistente técnico...")
                            
                            # Si se detectó una desconexión, proceder con el asistente técnico
                            thread_id_tecnico = crear_thread()
                            if thread_id_tecnico:
                                print(f"DEBUG: Thread del asistente técnico creado: {thread_id_tecnico}")
                                
                                # Obtener la empresa del primer centro detectado
                                empresa = list(centros_detectados.keys())[0]

                                # Consultar la API del centro
                                resultado_api = consultar_api_por_empresa(empresa, centros_detectados)
                                if resultado_api:
                                    print(f"DEBUG: Resultado de la API para el centro: {resultado_api}")
                                    
                                    # Convertir el diccionario a cadena JSON
                                    resultado_api_str = json.dumps(resultado_api)

                                    # Limpiar el resultado de la API antes de enviarlo al asistente técnico
                                    resultado_limpio = limpiar_contenido_api(resultado_api_str)

                                    # Enviar el resultado de la API al thread del asistente técnico
                                    mensaje_id_tecnico = agregar_mensaje_al_thread(thread_id_tecnico, resultado_limpio)
                                    if mensaje_id_tecnico:
                                        print(f"DEBUG: Mensaje enviado al thread técnico. ID del mensaje: {mensaje_id_tecnico}")

                                        # Ejecutar el thread para obtener la respuesta técnica
                                        respuesta_tecnica = ejecutar_thread(thread_id_tecnico)
                                        if respuesta_tecnica:
                                            print(f"DEBUG: Respuesta del asistente técnico obtenida: {respuesta_tecnica}")

                                            # Pausar por 60 segundos antes de enviar el segundo correo
                                            print("DEBUG: Esperando 60 segundos antes de enviar el segundo correo...")
                                            time.sleep(60)

                                            # Enviar el segundo correo con los resultados del ping
                                            enviar_correo_en_hilo(respuesta_tecnica, "", remitente, asunto, mensaje_original)
                                            total_respondidos += 1
                                            print(f"DEBUG: Segundo correo enviado con éxito a {remitente}. Falla registrada.")
                                        else:
                                            print("ERROR: No se pudo obtener la respuesta técnica del asistente.")
                                    else:
                                        print("ERROR: No se pudo agregar el mensaje técnico al thread.")
                                else:
                                    print("ERROR: No se pudo obtener el resultado de la API del centro.")
                            else:
                                print("ERROR: No se pudo crear el thread del asistente técnico.")
                        else:
                            print("DEBUG: No se detectó una desconexión o problema de enlace en el correo original.")
                    else:
                        print("ERROR: No se pudo obtener la respuesta del asistente principal.")
                else:
                    print("ERROR: No se pudo agregar el mensaje al thread del asistente principal.")
            else:
                print("ERROR: No se pudo crear el thread para el asistente principal.")
        else:
            if remitente:
                total_correos += 1
                print(f"DEBUG: Correo de {remitente} no está en la lista permitida, no se envió respuesta.")
            else:
                print("DEBUG: No hay correos nuevos.")

        print(f"Resumen: Total correos procesados: {total_correos}, Total respondidos: {total_respondidos}")
        time.sleep(60)

if __name__ == "__main__":
    print("DEBUG: Iniciando el script...")  # Depuración al inicio del script
    main()
