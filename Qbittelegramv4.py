import asyncio
import html
import qbittorrentapi
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeFilename
import os

# 🔹 Configuración del bot de Telegram
API_ID = xxxxxxxx
API_HASH = "xxxxxx"
BOT_TOKEN = "xxxxxxxx"
CHAT_ID = xxxxxxxx

# 🔹 Configuración de qBittorrent
QB_HOST = "http://192.168.0.160:6363"

# 🔹 Variables globales para la conexión y control
qb = None
active_tasks = {}      # Tareas asíncronas de notificación dinámica, clave: torrent_hash
active_messages = {}   # Mensajes enviados por cada torrent, clave: torrent_hash
paused_torrents = set()  # Conjunto de hashes de torrents pausados
pending_torrents = {}  # key: id único, value: ruta del archivo torrent
pending_magnets = {}   # key: id único, value: enlace magnet

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

# --- Callback para manejo de botones ---
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    if event.sender_id != CHAT_ID:
        return
    data = event.data
    if data.startswith(b"toggle:"):
        torrent_hash = data.split(b":", 1)[1].decode()
        try:
            lista = qb.torrents_info(torrent_hashes=torrent_hash)
        except qbittorrentapi.APIConnectionError as e:
            await event.answer("qBittorrent no está accesible.", alert=True)
            return
        if lista:
            torrent = lista[0]
            if torrent_hash in paused_torrents:
                qb.torrents_resume(torrent_hashes=[torrent_hash])
                paused_torrents.remove(torrent_hash)
                await event.answer("Torrent reanudado")
            else:
                qb.torrents_pause(torrent_hashes=[torrent_hash])
                paused_torrents.add(torrent_hash)
                await event.answer("Torrent pausado")
        else:
            await event.answer("Torrent no encontrado", alert=True)
    elif data.startswith(b"delete:"):
        torrent_hash = data.split(b":", 1)[1].decode()
        qb.torrents_delete(torrent_hashes=[torrent_hash], delete_files=True)
        paused_torrents.discard(torrent_hash)
        if torrent_hash in active_tasks:
            task = active_tasks[torrent_hash]
            task.cancel()
            active_tasks.pop(torrent_hash, None)
        if torrent_hash in active_messages:
            try:
                await active_messages[torrent_hash].delete()
            except Exception as e:
                print(f"Error al borrar el mensaje de notificación: {e}")
            active_messages.pop(torrent_hash, None)
        await event.answer("Torrent eliminado", alert=True)
    elif data.startswith(b"category:"):
        try:
            decoded = event.data.decode()
            _, torrent_id, categoria = decoded.split(":", 2)
            if torrent_id in pending_torrents:
                file_path = pending_torrents.pop(torrent_id)
                try:
                    qb.torrents_add(torrent_files=file_path, category=categoria)
                    await event.answer(f"Torrent añadido en la categoría {categoria}.", alert=True)
                    try:
                        await bot.delete_messages(event.chat_id, event.message_id)
                    except Exception as e:
                        print(f"Error borrando el mensaje completo: {e}")
                    os.remove(file_path)
                except Exception as e:
                    await event.answer("Error al añadir el torrent a qBittorrent.", alert=True)
                    print(f"Error añadiendo torrent: {e}")
            elif torrent_id in pending_magnets:
                magnet_link = pending_magnets.pop(torrent_id)
                try:
                    qb.torrents_add(urls=magnet_link, category=categoria)
                    await event.answer(f"Magnet añadido en la categoría {categoria}.", alert=True)
                    try:
                        await bot.delete_messages(event.chat_id, event.message_id)
                    except Exception as e:
                        print(f"Error borrando el mensaje completo: {e}")
                except Exception as e:
                    await event.answer("Error al añadir el magnet a qBittorrent.", alert=True)
                    print(f"Error añadiendo magnet: {e}")
            else:
                await event.answer("Archivo torrent o enlace magnet no encontrado o ya procesado.", alert=True)
        except Exception as e:
            await event.answer("Error procesando la selección de categoría.", alert=True)
            print(f"Error en callback category: {e}")

# --- Comando para listar descargas activas ---
@bot.on(events.NewMessage(pattern="/descargas"))
async def listar_descargas(event):
    if event.chat_id != CHAT_ID:
        return
    try:
        torrents_descargando = [t for t in qb.torrents_info(filter="downloading")]
        if not torrents_descargando:
            await event.reply("⚠️ No hay descargas activas.", parse_mode="html")
            return
        mensaje = "📂 <b>Descargas en curso:</b>\n\n"
        for t in torrents_descargando:
            mensaje += (
                f"🎬 <b>{html.escape(t.name)}</b>\n"
                f"📊 <b>{t.progress * 100:.2f}%</b> | 📏 <b>{formato_tamano(t.size)}</b>\n"
                f"⚡️ <b>{t.dlspeed / 1e6:.2f} MB/s</b> ↓ | 🚀 <b>{t.upspeed / 1e6:.2f} MB/s</b> ↑\n"
                f"🌱 Semillas: <b>{t.num_seeds}</b> | 🚀 Pares: <b>{t.num_leechs}</b>\n"
                f"📂 <b>Guardado en:</b> <code>{html.escape(t.save_path)}</code>\n"
                f"------------------------------------------------\n\n"
            )
        await enviar_mensaje(event.chat_id, mensaje)
    except qbittorrentapi.APIConnectionError:
        await event.reply("⚠️ No se puede obtener la lista de descargas, qBittorrent no está accesible.", parse_mode="html")

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


