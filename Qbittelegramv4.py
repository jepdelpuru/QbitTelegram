import asyncio
import html
import qbittorrentapi
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeFilename
import os
import collections
from telethon.errors.rpcerrorlist import MessageNotModifiedError
from urllib.parse import urlparse

# 🔹 Configuración del bot de Telegram
API_ID = XXXXXXXX
API_HASH = "XXXXXXXXXXX"
BOT_TOKEN = "XXXXXXXXXX"
CHAT_ID = XXXXXXXX

# 🔹 Configuración de qBittorrent
QB_HOST = "http://192.168.0.160:6363"

#PONER TRACKERS QUE SE QUIEREN MONITORIZAR
PRIVATE_TRACKER_DOMAINS = [
    "xxxxxxxx",
    "xxxxxx",
    "xxxxxxxx",
    "xxxxxxxx",
    "xxxxxxxx.cx",
    "xxxxx.com",
    "tracker.xxxxxx.org"
]


# 🔹 Variables globales para la conexión y control
qb = None
active_tasks = {}      # Tareas asíncronas de notificación dinámica, clave: torrent_hash
active_messages = {}   # Mensajes enviados por cada torrent, clave: torrent_hash
paused_torrents = set()  # Conjunto de hashes de torrents pausados
pending_torrents = {}  # key: id único, value: ruta del archivo torrent
pending_magnets = {}   # key: id único, value: enlace magnet
downloads_panel_message = None # Almacena el mensaje del panel para poder editarlo
downloads_panel_task = None    # Almacena la tarea de actualización del panel
status_panel_message = None    # Almacena el mensaje del panel de estado
status_panel_task = None       # Almacena la tarea de actualización del estado


# --- Función para conectar con qBittorrent ---
async def conectar_qbittorrent():
    global qb
    while True:
        try:
            qb = qbittorrentapi.Client(host=QB_HOST)
            qb.auth_log_in()
            print("✅ Conectado a qBittorrent en red local")
            return qb
        except qbittorrentapi.LoginFailed as e:
            print(f"⚠️ Error al conectar a qBittorrent: {e}, reintentando en 10 segundos...")
        except qbittorrentapi.APIConnectionError:
            print("⚠️ qBittorrent no está accesible, reintentando en 10 segundos...")
        await asyncio.sleep(10)

# --- Iniciar bot de Telegram con Telethon ---
bot = TelegramClient('qbittorrent_bot', API_ID, API_HASH)

def formato_velocidad(speed_bytes):
    if speed_bytes > 1e6:
        return f"{speed_bytes / 1e6:.2f} MB/s"
    if speed_bytes > 1e3:
        return f"{speed_bytes / 1e3:.1f} KB/s"
    return "0 KB/s"

# --- Función para formatear tamaños de archivo ---
def formato_tamano(size_bytes):
    if size_bytes > 1e9:
        return f"{size_bytes / 1e9:.2f} GB"
    elif size_bytes > 1e6:
        return f"{size_bytes / 1e6:.2f} MB"
    else:
        return f"{size_bytes / 1e3:.2f} KB"

# --- Función para dividir mensajes largos ---
async def enviar_mensaje(chat_id, mensaje):
    MAX_TAMANIO_MENSAJE = 4000
    partes = [mensaje[i:i+MAX_TAMANIO_MENSAJE] for i in range(0, len(mensaje), MAX_TAMANIO_MENSAJE)]
    for parte in partes:
        await bot.send_message(chat_id, parte, parse_mode="html")

# --- Función de notificación dinámica para cada torrent ---
async def notificar_descarga(torrent_hash):
    global qb
    total_segments = 17  # Barra de progreso

    while True:
        try:
            lista = qb.torrents_info(torrent_hashes=torrent_hash)
            if lista:
                torrent = lista[0]
                break
            else:
                return
        except qbittorrentapi.APIConnectionError as e:
            print(f"⚠️ qBittorrent no accesible al obtener info del torrent {torrent_hash}: {e}. Reintentando...")
            qb = await conectar_qbittorrent()
            await asyncio.sleep(5)
    
    if torrent_hash in paused_torrents:
        status_text = "⏸️ Pausado"
        toggle_text = "Reanudar"
    else:
        status_text = "📥 Descargando"
        toggle_text = "Pausar"

    filled = int(torrent.progress * total_segments)
    bar = "🟦" * filled + "⬜" * (total_segments - filled)
    mensaje_texto = (
        f"{status_text}: {html.escape(torrent.name)}\n"
        f"📊 Progreso: {torrent.progress*100:.2f}%\n"
        f"{bar}\n"
        f"📦 Tamaño: {formato_tamano(torrent.size)}\n"
        f"🚀 Velocidad: <b>{torrent.dlspeed / 1e6:.2f} MB/s</b>\n"
        f"🌱 Semillas: <b>{torrent.num_seeds}</b> | 🤝 Pares: <b>{torrent.num_leechs}</b>\n"
        f"📂 Guardado en: <code>{html.escape(torrent.save_path)}</code>\n"
    )

    buttons = [[
         Button.inline(toggle_text, b"toggle:" + torrent_hash.encode()),
         Button.inline("Eliminar", b"delete:" + torrent_hash.encode())
    ]]
    mensaje = await bot.send_message(CHAT_ID, mensaje_texto, parse_mode="html", buttons=buttons)
    active_messages[torrent_hash] = mensaje

    ultimo_progreso = torrent.progress

    try:
        while True:
            num_descargas = len(active_tasks)
            intervalo = 3 if num_descargas == 1 else 6

            await asyncio.sleep(intervalo)

            while True:
                try:
                    lista = qb.torrents_info(torrent_hashes=torrent_hash)
                    break
                except qbittorrentapi.APIConnectionError as e:
                    print(f"⚠️ qBittorrent desconectado al actualizar torrent {torrent_hash}: {e}. Esperando reconexión...")
                    qb = await conectar_qbittorrent()
                    await asyncio.sleep(5)
            if not lista:
                try:
                    await mensaje.delete()
                except Exception as e:
                    print(f"Error al borrar mensaje: {e}")
                active_messages.pop(torrent_hash, None)
                break
            torrent = lista[0]

            if torrent_hash in paused_torrents:
                status_text = "⏸️ Pausado"
                toggle_text = "Reanudar"
            else:
                status_text = "📥 Descargando"
                toggle_text = "Pausar"

            if torrent.progress < 0.99 and abs(torrent.progress - ultimo_progreso) < 0.01:
                continue
            ultimo_progreso = torrent.progress

            filled = int(torrent.progress * total_segments)
            bar = "🟦" * filled + "⬜" * (total_segments - filled)
            mensaje_texto = (
                f"{status_text}: {html.escape(torrent.name)}\n"
                f"📊 Progreso: {torrent.progress*100:.2f}%\n"
                f"{bar}\n"
                f"📦 Tamaño: {formato_tamano(torrent.size)}\n"
                f"🚀 Velocidad: <b>{torrent.dlspeed / 1e6:.2f} MB/s</b>\n"
                f"🌱 Semillas: <b>{torrent.num_seeds}</b> | 🤝 Pares: <b>{torrent.num_leechs}</b>\n"
                f"📂 Guardado en: <code>{html.escape(torrent.save_path)}</code>\n"
            )

            buttons = [[
                 Button.inline(toggle_text, b"toggle:" + torrent_hash.encode()),
                 Button.inline("Eliminar", b"delete:" + torrent_hash.encode())
            ]]
            try:
                await mensaje.edit(mensaje_texto, parse_mode="html", buttons=buttons)
            except Exception as e:
                print(f"Error al editar mensaje para torrent {torrent_hash}: {e}")
                break

            if (torrent.progress >= 1.0 or torrent.progress >= 0.99) and torrent_hash not in paused_torrents:
                try:
                    await mensaje.delete()
                except Exception as e:
                    print(f"Error al borrar mensaje: {e}")
                active_messages.pop(torrent_hash, None)
                mensaje_final_texto = (
                    f"✅ <b>Descarga completada:</b>\n\n"
                    f"🎬 <b>{html.escape(torrent.name)}</b>\n"
                    f"📏 <b>{formato_tamano(torrent.size)}</b>\n"
                    f"📂 <b>Guardado en:</b> <code>{html.escape(torrent.save_path)}</code>\n"
                )
                buttons_final = [[ Button.inline("Eliminar", b"delete:" + torrent_hash.encode()) ]]
                mensaje_final = await bot.send_message(CHAT_ID, mensaje_final_texto, parse_mode="html", buttons=buttons_final)
                active_messages[torrent_hash] = mensaje_final
                break
    except asyncio.CancelledError:
        try:
            await mensaje.delete()
        except Exception as e:
            print(f"Error al borrar mensaje tras cancelación: {e}")
        active_messages.pop(torrent_hash, None)
        raise

# --- Manejo de archivos torrent enviados ---
@bot.on(events.NewMessage)
async def handle_torrent_file(event):
    # Solo procesamos mensajes en chat privado con documentos
    if event.is_private and event.document:
        filename = None
        for attr in event.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name
                break
        if not filename:
            filename = event.document.file_name if hasattr(event.document, 'file_name') else ""
        if filename.lower().endswith(".torrent"):
            file_path = await event.download_media()
            torrent_id = str(event.id)
            pending_torrents[torrent_id] = file_path

            try:
                categorias_dict = qb.torrents_categories()
                print("Respuesta de categorías:", categorias_dict)
                categorias = list(categorias_dict.keys())
                if not categorias:
                    raise Exception("El diccionario de categorías está vacío.")
            except Exception as e:
                print(f"Error obteniendo categorías reales desde qBittorrent: {e}")
                categorias = ["Películas", "Series", "Documentales", "Música"]

            botones = [[Button.inline(categoria, f"category:{torrent_id}:{categoria}".encode())] for categoria in categorias]
            await bot.send_message(
                event.chat_id,
                f"📁 ¡Archivo <b>{html.escape(filename)}</b> recibido!\n\n"
                f"🔍 Por favor, selecciona la categoría para iniciar la descarga:",
                parse_mode="html",
                buttons=botones
            )

# --- Manejo de enlaces magnet enviados ---
@bot.on(events.NewMessage)
async def handle_magnet_link(event):
    # Procesamos solo mensajes privados de texto que contengan un enlace magnet
    if event.chat_id == CHAT_ID and event.raw_text and event.raw_text.strip().startswith("magnet:"):
        magnet_link = event.raw_text.strip()
        magnet_id = str(event.id)
        pending_magnets[magnet_id] = magnet_link
        try:
            categorias_dict = qb.torrents_categories()
            categorias = list(categorias_dict.keys())
            if not categorias:
                raise Exception("El diccionario de categorías está vacío.")
        except Exception as e:
            print(f"Error obteniendo categorías reales desde qBittorrent: {e}")
            categorias = ["Películas", "Series", "Documentales", "Música"]
        botones = [[Button.inline(categoria, f"category:{magnet_id}:{categoria}".encode())] for categoria in categorias]
        await bot.send_message(
            event.chat_id,
            f"📁 ¡Enlace magnet recibido!\n\n"
            f"🔍 Por favor, selecciona la categoría para iniciar la descarga:",
            parse_mode="html",
            buttons=botones
        )

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    global downloads_panel_task, status_panel_task
    if event.sender_id != CHAT_ID:
        return

    data = event.data

    # --- PANELES ---
    if data == b"close_panel":
        task_to_cancel = downloads_panel_task
        downloads_panel_task = None 
        if task_to_cancel and not task_to_cancel.done():
            task_to_cancel.cancel()
            await event.answer("Cerrando el panel de descargas...")
        else:
            await event.answer("El panel ya estaba cerrado.", alert=True)
            try:
                await event.delete()
            except Exception: pass
        return

    elif data == b"close_status":
        task_to_cancel = status_panel_task
        status_panel_task = None
        if task_to_cancel and not task_to_cancel.done():
            task_to_cancel.cancel()
            await event.answer("Cerrando el panel de estado...")
        else:
            await event.answer("El panel de estado ya estaba cerrado.", alert=True)
            try:
                await event.message.delete()
            except Exception: pass
        return

    # --- BOTONES DE ACCIÓN GLOBAL ---
    # EJEMPLO - USA LA CLAVE QUE ENCONTRASTE
    elif data == b'toggle_alt_speed':
        try:
            # Reemplaza 'use_alt_speed_limits' con la clave real que encontraste
            CLAVE_REAL = 'use_alt_speed_limits' 

            prefs = qb.app_preferences()
            current_state = prefs[CLAVE_REAL]

            qb.app_set_preferences(prefs={CLAVE_REAL: not current_state})

            new_status_text = "DESACTIVADOS" if current_state else "ACTIVADOS"
            await event.answer(f"✅ Límites de velocidad alternativos ahora {new_status_text}.")

        except Exception as e:
            await event.answer(f"❌ Error: {e}", alert=True)
        return

    elif data == b'pause_all':
        try:
            qb.torrents_pause(torrent_hashes='all')
            await event.answer("⏸️ Todos los torrents han sido pausados.")
        except Exception as e:
            await event.answer(f"❌ Error al pausar: {e}", alert=True)
        return
    
    elif data == b'resume_all':
        try:
            qb.torrents_resume(torrent_hashes='all')
            await event.answer("▶️ Todos los torrents han sido reanudados.")
        except Exception as e:
            await event.answer(f"❌ Error al reanudar: {e}", alert=True)
        return

    elif data == b'refresh_status':
        await event.answer("Panel actualizado en el siguiente ciclo.")
        return

    # --- BOTONES DE TORRENTS INDIVIDUALES ---
    elif data.startswith(b"toggle:"):
        torrent_hash = data.split(b":", 1)[1].decode()
        try:
            if torrent_hash in paused_torrents:
                qb.torrents_resume(torrent_hashes=[torrent_hash])
                paused_torrents.remove(torrent_hash)
                await event.answer("Torrent reanudado")
            else:
                qb.torrents_pause(torrent_hashes=[torrent_hash])
                paused_torrents.add(torrent_hash)
                await event.answer("Torrent pausado")
        except qbittorrentapi.APIConnectionError:
            await event.answer("qBittorrent no está accesible.", alert=True)
        return

    elif data.startswith(b"delete:"):
        torrent_hash = data.split(b":", 1)[1].decode()
        try:
            # --- Bloque para qBittorrent ---
            # Intentamos eliminar el torrent, pero no dejamos que un error aquí detenga el proceso.
            try:
                qb.torrents_delete(torrent_hashes=[torrent_hash], delete_files=True)
            except qbittorrentapi.NotFound404Error:
                # Esto es normal si el torrent ya fue borrado manualmente. Lo ignoramos.
                print(f"Info: Se intentó borrar el torrent {torrent_hash}, pero ya no existía en qBittorrent.")
            except Exception as e:
                # Otro error de qBittorrent, lo registramos pero continuamos para borrar el mensaje.
                print(f"Error borrando el torrent de qBittorrent: {e}")

            # --- Bloque para Telegram y estado del bot ---
            # Limpiamos el estado interno del bot (siempre)
            paused_torrents.discard(torrent_hash)
            active_tasks.pop(torrent_hash, None)
            active_messages.pop(torrent_hash, None)
            
            # Respondemos al usuario y borramos el mensaje (siempre)
            await event.answer("Acción completada. Mensaje eliminado.", alert=True)
            await event.delete()
            
        except Exception as e:
            # Este 'except' general es para errores de Telegram (ej. al borrar el mensaje)
            await event.answer(f"❌ Error al procesar la acción en Telegram: {e}", alert=True)
            print(f"Error en callback delete (lado de Telegram): {e}")
        return

    # --- BOTONES DE CATEGORÍA ---
    elif data.startswith(b"category:"):
        try:
            decoded = event.data.decode()
            _, torrent_id, categoria = decoded.split(":", 2)

            # Lógica para archivos .torrent
            if torrent_id in pending_torrents:
                file_path = pending_torrents.pop(torrent_id)
                try:
                    qb.torrents_add(torrent_files=file_path, category=categoria)
                    await event.answer(f"Torrent añadido en la categoría {categoria}.", alert=True)
                    os.remove(file_path)
                    await event.delete()
                except Exception as e:
                    await event.answer("Error al añadir el torrent a qBittorrent.", alert=True)
                    print(f"Error añadiendo torrent: {e}")

            # Lógica para enlaces magnet
            elif torrent_id in pending_magnets:
                magnet_link = pending_magnets.pop(torrent_id)
                try:
                    qb.torrents_add(urls=magnet_link, category=categoria)
                    await event.answer(f"Magnet añadido en la categoría {categoria}.", alert=True)
                    await event.delete()
                except Exception as e:
                    await event.answer("Error al añadir el magnet a qBittorrent.", alert=True)
                    print(f"Error añadiendo magnet: {e}")
            
            else:
                await event.answer("Archivo o magnet no encontrado o ya procesado.", alert=True)

        except Exception as e:
            await event.answer("Error procesando la selección de categoría.", alert=True)
            print(f"Error en callback category: {e}")
            
        return

# --- Comando para listar descargas activas ---
# NUEVO: Función para abreviar nombres largos
def abreviar_nombre(nombre, longitud=28):
    if len(nombre) > longitud:
        return nombre[:longitud-3] + "..."
    return nombre

async def update_status_panel(event):
    global status_panel_message
    
    start_time = asyncio.get_event_loop().time()
    timeout_seconds = 240

    try:
        while True:
            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                print("Panel de estado cerrado por timeout.")
                if status_panel_message:
                    try:
                        await status_panel_message.delete()
                    except Exception:
                        pass
                break 

            try:
                main_data = qb.sync_maindata()
                server_state = main_data.server_state
                qb_version = qb.app_version()
                all_torrents = qb.torrents_info()

                pause_status_str = ""
                if all_torrents:
                    # Añadimos 'stoppedUP' y 'stoppedDL' a la lista de estados que consideramos "pausados"
                    estados_inactivos = ['pausedUP', 'pausedDL', 'stoppedUP', 'stoppedDL']
                    
                    # Comprobamos si TODOS los torrents están en uno de esos estados
                    all_are_inactive = all(t.state in estados_inactivos for t in all_torrents)

                    if all_are_inactive:
                        pause_status_str = "\n\n‼️ <b><u>Estado Global:</u> ¡TODO PAUSADO O DETENIDO!</b> ‼️\n\n"

                # (El resto del código de la función para construir el mensaje es idéntico)
                category_counts = collections.defaultdict(int)
                for t in all_torrents:
                    category_counts[t.category] += 1
                category_items = []
                if category_counts:
                    for name, count in sorted(category_counts.items()):
                        display_name = "Sin Categoría" if name == "" else html.escape(name)
                        category_items.append(f"  <b>{display_name}:</b> <code>{count} torrents</code>")
                
                category_section_str = "\n📂 <b><u>Torrents por Categoría</u></b>\n" + "\n".join(category_items) if category_items else ""
                tracker_stats = collections.defaultdict(lambda: {'count': 0, 'uploaded': 0, 'downloaded': 0, 'status_codes': [], 'seeding_count': 0})

                for torrent in all_torrents:
                    found_private_domains = set()
                    for tracker in torrent.trackers:
                        try:
                            domain = urlparse(tracker['url']).hostname
                            if domain and domain in PRIVATE_TRACKER_DOMAINS:
                                found_private_domains.add(domain)
                                tracker_stats[domain]['status_codes'].append(tracker['status'])
                        except Exception:
                            continue
                    
                    # 2. Comprobamos si el torrent está sedeando
                    is_seeding = torrent.state in ['uploading', 'stalledUP']

                    for domain in found_private_domains:
                        stats = tracker_stats[domain]
                        stats['count'] += 1
                        stats['uploaded'] += torrent.uploaded
                        stats['downloaded'] += torrent.downloaded
                        # 3. Incrementamos el contador si está sedeando
                        if is_seeding:
                            stats['seeding_count'] += 1
                
                private_trackers_section_str = ""
                if tracker_stats:
                    items = []
                    for domain, stats in sorted(tracker_stats.items()):
                        statuses = stats['status_codes']
                        status_icon = '🟢'
                        if statuses:
                            all_working = all(s == 2 for s in statuses)
                            any_working = any(s == 2 for s in statuses)
                            if all_working: status_icon = '🟢'
                            elif any_working: status_icon = '🟡'
                            else: status_icon = '🔴'
                        
                        ratio = stats['uploaded'] / stats['downloaded'] if stats['downloaded'] > 0 else float('inf')
                        ratio_str = f"{ratio:.2f}" if ratio != float('inf') else "∞"
                        up_str = formato_tamano(stats['uploaded'])
                        down_str = formato_tamano(stats['downloaded'])
                        
                        # --- 4. NUEVO FORMATO DEL MENSAJE ---
                        # Añadimos el contador de seeding a la línea principal de forma compacta
                        seeding_str = f" (🌱{stats['seeding_count']})" if stats['seeding_count'] > 0 else ""
                        count_str = f"{stats['count']} torrents{seeding_str}"

                        line = (
                            f"{status_icon} <b>{domain}:</b> <code>{count_str}</code>\n"
                            f"   - 📤 <code>{up_str}</code> | 📥 <code>{down_str}</code>\n"
                            f"   - ⚖️ <b>Ratio:</b> <code>{ratio_str}</code>"
                        )
                        items.append(line)
                    
                    private_trackers_section_str = "\n\n🔑 <b><u>Trackers Privados Activos</u></b>\n" + "\n".join(items)

                session_download = formato_tamano(server_state.dl_info_data)
                session_upload = formato_tamano(server_state.up_info_data)
                ratio_val = server_state.global_ratio
                global_ratio = f"{ratio_val:.2f}" if isinstance(ratio_val, (int, float)) else str(ratio_val)
                status_map = {'connected': '✅ Conectado', 'firewalled': '⚠️ Cortafuegos', 'disconnected': '❌ Desconectado'}
                connection_status = status_map.get(server_state.connection_status, '❓ Desconocido')
                dht_nodes = server_state.dht_nodes
                alt_speed_status = "🟢 ACTIVADO" if server_state.use_alt_speed_limits else "🔴 DESACTIVADO"
                num_seeding = len([t for t in all_torrents if t.state in ['uploading', 'stalledUP']])
                num_paused = len([t for t in all_torrents if t.state in ['pausedUP', 'pausedDL']])
                num_stalled_dl = len([t for t in all_torrents if t.state == 'stalledDL'])
                main_free_space = formato_tamano(server_state.free_space_on_disk)
                dl_speed = formato_velocidad(sum(t.dlspeed for t in all_torrents))
                up_speed = formato_velocidad(sum(t.upspeed for t in all_torrents))
                
                mensaje = (
                    f"📊 <b><u>Estado de qBittorrent v{qb_version}</u></b> 📊"
                    f"{pause_status_str}"  # Mensaje de pausa se inserta aquí
                    f"\n\n📡 <b>Conexión:</b> <code>{connection_status} ({dht_nodes} nodos DHT)</code>\n"
                    f"🐢 <b>Límite Alt.:</b> <code>{alt_speed_status}</code>\n"
                    f"💾 <b>Espacio Libre (principal):</b> <code>{main_free_space}</code>\n"
                    f"{category_section_str}"
                    f"{private_trackers_section_str}"
                    f"\n\n🔄 <b><u>Sesión Actual</u></b>\n"
                    f"  <b>Ratio Global:</b> <code>{global_ratio}</code>\n"
                    f"  <b>Descargado:</b> <code>{session_download}</code>\n"
                    f"  <b>Subido:</b> <code>{session_upload}</code>\n\n"
                    f"🚀 <b><u>Velocidad Global</u></b>\n"
                    f"  <b>Descarga:</b> <code>{dl_speed}</code>\n"
                    f"  <b>Subida:</b> <code>{up_speed}</code>\n\n"
                    f"📝 <b><u>Resumen de Torrents</u></b>\n"
                    f"  📥 <b>Descargando:</b> <code>{len([t for t in all_torrents if 'DL' in t.state.upper() and 'PAUSED' not in t.state.upper()])}</code>\n"
                    f"  🌱 <b>Sedeando:</b> <code>{num_seeding}</code>\n"
                    f"  ⏸️ <b>Pausados:</b> <code>{num_paused}</code>\n"
                    f"  ⚠️ <b>Estancados (DL):</b> <code>{num_stalled_dl}</code>\n"
                )
                
            except Exception as e:
                mensaje = f"❌ <b>Error al actualizar estado:</b>\n<code>{e}</code>\n\nReintentando..."
                print(f"Error en el bucle de update_status_panel: {e}")

            buttons = [
                [
                    Button.inline("🔄 Actualizar", b"refresh_status")
                ],
                [
                    Button.inline("⏸️ Pausar Todo", b"pause_all"),
                    Button.inline("▶️ Reanudar Todo", b"resume_all")
                ],
                [Button.inline("Cerrar Panel ❌", b"close_status")]
            ]
            
            try:
                if status_panel_message:
                    await status_panel_message.edit(mensaje, parse_mode="html", buttons=buttons)
                else:
                    status_panel_message = await event.reply(mensaje, parse_mode="html", buttons=buttons)
            except MessageNotModifiedError:
                pass

            await asyncio.sleep(10)

    except asyncio.CancelledError:
        if status_panel_message:
            try:
                await status_panel_message.delete()
            except Exception:
                pass
        print("Panel de estado cerrado correctamente por el usuario.")
    finally:
        status_panel_message = None
        global status_panel_task
        status_panel_task = None


async def update_downloads_panel(event):
    global downloads_panel_message

    # --- AÑADIDO: Guardar el tiempo de inicio ---
    start_time = asyncio.get_event_loop().time()
    timeout_seconds = 120  # 2 minutos

    try:
        while True:
            # --- AÑADIDO: Comprobar si ha pasado el tiempo ---
            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                print("Panel de descargas cerrado por timeout.")
                if downloads_panel_message:
                    try:
                        await downloads_panel_message.delete()
                    except Exception:
                        pass
                break # Salir del bucle para terminar la tarea

            try:
                torrents = qb.torrents_info(filter="downloading")
            except qbittorrentapi.APIConnectionError:
                error_message = "⚠️ No se puede conectar con qBittorrent. Reintentando..."
                buttons = [[Button.inline("Cerrar Panel ❌", b"close_panel")]]
                if downloads_panel_message:
                    await downloads_panel_message.edit(error_message, buttons=buttons)
                else:
                    downloads_panel_message = await event.reply(error_message, buttons=buttons)
                
                await asyncio.sleep(10)
                continue

            buttons = [[Button.inline("Cerrar Panel ❌", b"close_panel")]]
            
            if not torrents:
                mensaje = "✅ No hay descargas activas en este momento."
            else:
                mensaje = "📂 <b>Descargas en curso:</b>\n\n"
                total_segments = 12
                for t in sorted(torrents, key=lambda x: x.name):
                    filled = int(t.progress * total_segments)
                    bar = "🟦" * filled + "⬜" * (total_segments - filled)
                    nombre_corto = html.escape(abreviar_nombre(t.name))
                    porcentaje = f"{t.progress * 100:.1f}%"
                    velocidad = formato_velocidad(t.dlspeed)
                    mensaje += f"🎬 <code>{nombre_corto}</code>\n{bar}\n<b>{porcentaje}</b>  🚀 <b>{velocidad}</b>\n"

            try:
                if downloads_panel_message:
                    await downloads_panel_message.edit(mensaje, parse_mode="html", buttons=buttons)
                else:
                    downloads_panel_message = await event.reply(mensaje, parse_mode="html", buttons=buttons)
            except MessageNotModifiedError:
                pass
            except Exception as e:
                print(f"Error irrecuperable en el panel de descargas: {e}")
                break

            # La pausa también debe estar DENTRO del `while True`
            await asyncio.sleep(10)

    except asyncio.CancelledError:
        if downloads_panel_message:
            try:
                await downloads_panel_message.delete()
            except Exception:
                pass
        print("Panel de descargas cerrado correctamente por el usuario.")
    finally:
        downloads_panel_message = None
        global downloads_panel_task
        downloads_panel_task = None


@bot.on(events.NewMessage(pattern="/descargas"))
async def listar_descargas(event):
    await event.delete()
    global downloads_panel_task
    if event.chat_id != CHAT_ID:
        return

    # Evita abrir múltiples paneles
    if downloads_panel_task and not downloads_panel_task.done():
        await event.reply("⚠️ Un panel de descargas ya está activo.", parse_mode="html")
        return

    # Lanza la tarea que se encargará de actualizar el mensaje
    downloads_panel_task = asyncio.create_task(update_downloads_panel(event))

@bot.on(events.NewMessage(pattern="/status"))
async def show_status(event):
    await event.delete()
    global status_panel_task
    if event.chat_id != CHAT_ID:
        return

    # Evita abrir múltiples paneles de estado
    if status_panel_task and not status_panel_task.done():
        await event.reply("⚠️ Un panel de estado ya está activo.", parse_mode="html")
        return

    # Lanza la tarea que se encargará de actualizar el panel de estado
    status_panel_task = asyncio.create_task(update_status_panel(event))

# --- Monitorización de qBittorrent: lanza tareas para torrents nuevos ---
async def monitorear_qbittorrent():
    global qb, active_tasks
    torrents_iniciales = {t.hash: t for t in qb.torrents_info(filter="downloading")}
    for t_hash in torrents_iniciales:
        active_tasks[t_hash] = asyncio.create_task(notificar_descarga(t_hash))
    print(f"🔄 {len(torrents_iniciales)} torrents ya estaban descargando al iniciar. Se notificarán dinámicamente.")
    descargas_previas = set(torrents_iniciales.keys())
    while True:
        try:
            torrents_actuales = {t.hash: t for t in qb.torrents_info(filter="downloading")}
            descargas_previas = {h for h in descargas_previas if h in torrents_actuales}
            torrents_nuevos = set(torrents_actuales.keys()) - descargas_previas
            for t_hash in torrents_nuevos:
                active_tasks[t_hash] = asyncio.create_task(notificar_descarga(t_hash))
                descargas_previas.add(t_hash)
            for t_hash, task in list(active_tasks.items()):
                if task.done():
                    active_tasks.pop(t_hash, None)
        except qbittorrentapi.APIConnectionError:
            print("⚠️ Perdida la conexión con qBittorrent. Intentando reconectar...")
            qb = await conectar_qbittorrent()
        await asyncio.sleep(5)

# --- Función principal ---
async def main():
    global qb
    await bot.start(bot_token=BOT_TOKEN)
    qb = await conectar_qbittorrent()
    await asyncio.gather(bot.run_until_disconnected(), monitorear_qbittorrent())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())





