Un bot de Telegram potente, persistente y asíncrono, construido con Python, Telethon y qbittorrent-api, para gestionar tu cliente qBittorrent de forma remota, cómoda y eficiente.

Esta versión introduce un sistema de persistencia de estado, lo que significa que el bot puede reiniciarse sin perder el rastro de las descargas activas y sin generar mensajes duplicados. Añade torrents, recibe notificaciones dinámicas, monitoriza el estado general de tu servidor y gestiona tus descargas, todo desde la comodidad de tu chat de Telegram.

🌟 Características Principales
🔄 Persistencia de Estado (¡No más mensajes duplicados!): El bot guarda el estado de sus mensajes en un archivo (bot_state.json). Si reinicias el script, reanudará la edición de los mensajes existentes en lugar de crear nuevos, manteniendo tu chat limpio.

🧠 Motor de Monitoreo Inteligente: El sistema de arranque ha sido rediseñado para ser más robusto. Al iniciar, verifica todos los torrents, limpia el estado de descargas ya eliminadas y se "revincula" a los mensajes de progreso que envió antes de reiniciarse.

📥 Añadir Descargas Fácilmente: Simplemente envía un archivo .torrent o pega un enlace magnet en el chat para iniciar una descarga.

🗂️ Gestión por Categorías: Antes de añadir una descarga, el bot te preguntará en qué categoría de qBittorrent deseas guardarla, obteniendo la lista directamente desde tu cliente.

📊 Notificaciones de Progreso Dinámicas: Por cada descarga activa, el bot crea un mensaje que se actualiza en tiempo real mostrando:

Barra de progreso visual.

Porcentaje, tamaño y velocidad de descarga.

Número de semillas y pares.

Botones para Pausar, Reanudar y Eliminar el torrent individualmente.

✅ Notificación de Finalización: Recibe un mensaje claro cuando una descarga se completa, con un botón para eliminar el torrent y sus archivos del disco directamente desde Telegram.

PANEL DE ESTADO (/status): Un panel completo que se actualiza automáticamente con información crucial:

Versión de qBittorrent y estado de la conexión.

Velocidades globales de subida y bajada.

Espacio libre en el disco.

Resumen de torrents por categoría.

Estadísticas de Trackers Privados: Monitoriza el ratio, datos subidos/bajados y estado por cada tracker privado que configures.

Controles para Pausar Todo y Reanudar Todo.

PANEL DE DESCARGAS (/descargas): Un resumen visual y ligero de todos los torrents que se están descargando activamente.

🦾 Robusto y Asíncrono: Construido sobre asyncio, puede gestionar múltiples descargas y actualizaciones de manera eficiente sin bloquearse.

🔁 Reconexión Automática: Si el bot pierde la conexión con qBittorrent, intentará reconectarse automáticamente.

🖼️ Vistazo a la Interfaz
La interfaz visual se mantiene intuitiva y potente, ahora respaldada por un motor más fiable.

Añadiendo un Torrent
El bot te pedirá que elijas una categoría para organizar tu descarga.

📁 ¡Archivo mi_pelicula.torrent recibido!

🔍 Por favor, selecciona la categoría para iniciar la descarga:
[ Películas ]
[ Series    ]
[ Música    ]
Notificación de Descarga en Tiempo Real
Cada descarga tiene su propio mensaje persistente con controles y estadísticas en vivo.

📥 Descargando: Mi_Pelicula_1080p.mkv
📊 Progreso: 42.15%
🟦🟦🟦🟦🟦🟦🟦⬜⬜⬜⬜⬜⬜⬜⬜⬜
📦 Tamaño: 4.37 GB
🚀 Velocidad: 8.73 MB/s
🌱 Semillas: 123 | 🤝 Pares: 45
📂 Guardado en: /data/downloads/Peliculas/

[ Pausar ] [ Eliminar ]
Notificación de Descarga Completada
Mensaje final con la opción de limpieza completa.

✅ Descarga completada:

🎬 Mi_Pelicula_1080p.mkv
📏 4.37 GB
📂 Guardado en: /data/downloads/Peliculas/

[ Eliminar de qBit (+Archivos) ]
⚙️ Configuración e Instalación
Requisitos Previos
Python 3.7+.

Un cliente qBittorrent en ejecución con la WebUI activada.

Una cuenta de Telegram.

Un bot de Telegram creado. Habla con @BotFather para crear uno y obtener tu BOT_TOKEN.

Pasos de Instalación
Clona el repositorio o descarga el script:
Guarda el archivo qbittelegramv4.py en una carpeta de tu elección.

Instala las dependencias de Python:

Bash

pip install telethon qbittorrent-api
Configura el script:
Abre el archivo qbittelegramv4.py y edita la sección de configuración con tus propios datos.

Python

# 🔹 Configuración del bot de Telegram
API_ID = 12345678          # Tu API ID de my.telegram.org
API_HASH = "tu_api_hash"   # Tu API Hash de my.telegram.org
BOT_TOKEN = "token_de_tu_bot" # El token que te dio @BotFather
CHAT_ID = 987654321        # Tu ID de usuario de Telegram. ¡Importante!

# 🔹 Configuración de qBittorrent
QB_HOST = "http://192.168.1.100:8080" # IP y puerto de tu qBittorrent WebUI

# 🔹 Trackers privados para monitorizar en /status
PRIVATE_TRACKER_DOMAINS = [
    "tracker.uno.org",
    "tracker.dos.net",
    # ...añade los dominios de tus trackers aquí
]
¿Cómo obtener API_ID, API_HASH y CHAT_ID?

API_ID y API_HASH: Obtenlos en my.telegram.org en la sección "API development tools".

CHAT_ID: Es tu ID de usuario numérico de Telegram. Puedes obtenerlo fácilmente enviando un mensaje a un bot como @userinfobot. Esto asegura que el bot solo te responda a ti.

🚀 Uso
Una vez configurado, simplemente ejecuta el script:

Bash

python qbittelegramv4.py
El bot se iniciará, buscará un archivo de estado bot_state.json, se conectará a qBittorrent, reanudará el seguimiento de las descargas existentes y estará listo para recibir tus comandos.

Comandos Disponibles
/start: Muestra un mensaje de bienvenida.

/status: Muestra el panel de estado general de qBittorrent, que se actualiza automáticamente.

/descargas: Muestra un panel con las descargas activas en curso, también con actualizaciones automáticas.

Interacciones
Enviar un archivo .torrent: El bot te preguntará la categoría y lo añadirá a la cola de qBittorrent.

Enviar un enlace magnet:: El bot te preguntará la categoría y lo añadirá a la cola.

🛠️ Cómo Funciona
El script utiliza asyncio para manejar todas las operaciones de forma no bloqueante.

Persistencia con bot_state.json:

Cada vez que el bot envía o elimina un mensaje de progreso, guarda un mapa del hash del torrent al ID del mensaje de Telegram en este archivo.

Al arrancar, la función monitorear_qbittorrent lee este archivo, obtiene los torrents activos de qBittorrent y busca los mensajes correspondientes en Telegram para reanudar su edición. Esto evita la creación de mensajes duplicados y asegura la continuidad.

Motor de Monitoreo Robusto:

A diferencia de versiones anteriores, el bucle principal ahora obtiene la lista completa de torrents de qBittorrent y los filtra en Python. Esto le permite detectar no solo nuevos torrents en descarga, sino también cuándo un torrent ha sido completado o eliminado, para así detener su tarea de monitoreo correspondiente y limpiar los recursos.

Telethon y qbittorrent-api:

Telethon sigue gestionando la comunicación con la API de Telegram.

qbittorrent-api se encarga de la comunicación con la API Web de qBittorrent.

📝 Posibles Mejoras (To-Do)
[ ] Mover la configuración a un archivo externo (config.ini o .env).

[ ] Añadir más controles a los torrents individuales (ej. forzar re-anuncio, cambiar prioridad).

[ ] Soporte para múltiples usuarios autorizados.

[ ] Dockerizar la aplicación para un despliegue más sencillo.

[ ] Mejorar el manejo de errores y notificar al usuario en caso de fallo persistente.

📄 Licencia
Este proyecto se distribuye bajo la Licencia MIT. Consulta el archivo LICENSE para más detalles.
