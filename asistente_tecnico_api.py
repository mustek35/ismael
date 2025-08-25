import requests
import os
import re
import time
from dotenv import load_dotenv


# Cargar la clave de API desde un archivo .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# ID del asistente técnico (Ismael 2)
assistant_id = "asst_3iCMq8n0etmnIgzQQCsysuge"

# Diccionario para almacenar los threads por remitente
threads_remitentes = {}

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

# Función para agregar un mensaje al thread con el encabezado 'OpenAI-Beta'
def agregar_mensaje_al_thread(thread_id, content):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'OpenAI-Beta': 'assistants=v2'
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

# Función para ejecutar el thread con tu asistente
def ejecutar_thread(thread_id):
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
        wait_time = 5

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

# Función para obtener el estado del thread
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

# Función para obtener los mensajes del thread
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
        for message in mensajes_data.get("data", []):
            if message.get("role") == "assistant":
                return message["content"][0]["text"]["value"]
        return None
    else:
        print(f"Error al obtener los mensajes del thread: {response.status_code} - {response.text}")
        return None

# Cambiar la función de consulta para manejar tanto empresas y centros
def consultar_api_por_empresa(empresa, centros_detectados):
    try:
        # Obtener el primer centro detectado
        nombre_centro = list(centros_detectados[empresa])[0]

        # Eliminar los espacios en blanco del nombre del centro (como canalad 2 -> canalad2)
        nombre_centro_url = nombre_centro.replace(" ", "").lower()  # Convertir a minúsculas si es necesario

        # Construir la URL de la API según la empresa
        if empresa == "Cermaq":
            api_url = f"https://apiacopio.orcawan.uk/api/{nombre_centro_url}"
        elif empresa == "AquaChile":
            api_url = f"https://apihuapi.orcawan.uk/api/{nombre_centro_url}"
        else:
            print(f"ERROR: Empresa {empresa} no soportada.")
            return f"ERROR: Empresa {empresa} no soportada."

        # DEBUG: Imprimir la URL que se está usando para verificar que sea correcta
        print(f"DEBUG: Haciendo solicitud a la URL: {api_url}")

        # Realizar la solicitud a la API
        response = requests.get(api_url)

        # Comprobar si la respuesta es exitosa (código 200)
        if response.status_code == 200:
            api_response = response.json()
            print(f"DEBUG: Respuesta de la API para el centro {nombre_centro}: {api_response}")
            
            # Verificar si la API devolvió un resultado válido
            if api_response.get("centerStatus") == "En línea":
                return api_response
            else:
                return f"ERROR: El centro {nombre_centro} no está en línea."

        # Manejo específico de errores 404
        elif response.status_code == 404:
            print(f"ERROR: La API devolvió un código de error 404 para el centro {nombre_centro}.")
            return f"ERROR: La API devolvió un código de error 404 para el centro {nombre_centro}."

        # Manejar otros códigos de error
        else:
            print(f"ERROR: La API devolvió un código de error {response.status_code}.")
            return f"ERROR: La API devolvió un código de error {response.status_code} para el centro {nombre_centro}."

    except Exception as e:
        print(f"ERROR: Ocurrió un error en consultar_api_por_empresa: {e}")
        return f"ERROR: Ocurrió un error en consultar la API del centro {nombre_centro}: {str(e)}"


# Limpiar el contenido del resultado de la API para evitar caracteres no permitidos
def limpiar_contenido_api(contenido):
    """
    Esta función limpia el contenido de caracteres no permitidos o no imprimibles,
    y ajusta los espacios en blanco.
    """
    # Eliminar caracteres no imprimibles
    contenido_limpio = re.sub(r'[^\x00-\x7F]+', ' ', contenido)
    
    # Reemplazar múltiples espacios por uno solo
    contenido_limpio = re.sub(r'\s+', ' ', contenido_limpio).strip()
    
    return contenido_limpio

# Función para obtener o crear un thread asociado al remitente
def obtener_o_crear_thread(remitente):
    """
    Si ya existe un thread para el remitente, devolverlo.
    Si no, crear uno nuevo.
    """
    if remitente in threads_remitentes:
        print(f"DEBUG: Reutilizando thread existente para {remitente}")
        return threads_remitentes[remitente]
    else:
        print(f"DEBUG: Creando un nuevo thread para {remitente}")
        nuevo_thread_id = crear_thread()
        threads_remitentes[remitente] = nuevo_thread_id
        return nuevo_thread_id

# Función principal de tu asistente técnico
def asistente_tecnico_por_empresa(centros_detectados, empresa, remitente):
    thread_id = obtener_o_crear_thread(remitente)
    
    # Consultar la API del centro
    resultado_api = consultar_api_por_empresa(empresa, centros_detectados)
    
    if resultado_api:
        # Limpiar el contenido antes de enviarlo al asistente
        resultado_limpio = limpiar_contenido_api(resultado_api)
        
        # Agregar el mensaje al thread
        mensaje_id = agregar_mensaje_al_thread(thread_id, resultado_limpio)
        
        if mensaje_id:
            # Ejecutar el thread para obtener la respuesta del asistente
            respuesta_asistente = ejecutar_thread(thread_id)
            
            if respuesta_asistente:
                print(f"Respuesta del asistente técnico para {empresa} - {nombre_centro}: {respuesta_asistente}")
            else:
                print(f"No se obtuvo una respuesta válida del asistente técnico para el centro {nombre_centro}.")
        else:
            print(f"No se pudo agregar el mensaje al thread para el centro {nombre_centro}.")
    else:
        # Si no hay respuesta de la API o hay un error, informar al asistente
        error_msg = f"ERROR: No se pudo obtener el resultado de la API del centro {nombre_centro} debido a un problema de conectividad."
        agregar_mensaje_al_thread(thread_id, error_msg)
        respuesta_asistente = ejecutar_thread(thread_id)
        
        if respuesta_asistente:
            print(f"Respuesta del asistente técnico para error: {respuesta_asistente}")
        else:
            print(f"No se obtuvo una respuesta válida del asistente técnico para el error.")

# Ejecución principal del asistente técnico
if __name__ == "__main__":
    centros_detectados = {
        "AquaChile": ["Canal Luchin"]
    }

    empresa = "AquaChile"
    remitente = "cespinoza.cast@gmail.com"
    
    asistente_tecnico_por_empresa(centros_detectados, empresa, remitente)
