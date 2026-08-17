import time
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Нигоҳдории вақти охирини ишораи Colab ва супоришҳо
colab_last_ping = 0
task_queue = []

app = Flask(__name__)

# Маркази қабули ишора ва супориш аз Colab
@app.route('/ping', methods=['POST'])
def ping():
    global colab_last_ping
    colab_last_ping = time.time()
    return jsonify({"status": "ok"})

@app.route('/get_task', methods=['GET'])
def get_task():
    global colab_last_ping
    colab_last_ping = time.time()
    if task_queue:
        task = task_queue.pop(0)
        return jsonify({"status": "has_task", "task": task})
    return jsonify({"status": "no_task"})

def run_flask():
    # Сервер дар формати мувофиқ бо Railway
    app.run(host='0.0.0.0', port=8080)

# Мантиқи Телеграм Бот
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Салом! Мусиқиро фиристед, то минуси онро созам.")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global colab_last_ping
    # Агар аз ишораи охирини Colab бештар аз 30 сония гузашта бошад
    if time.time() - colab_last_ping > 30:
        await update.message.reply_text("Ҳозир сервер пайваст нест. Лутфан баъдтар ҳаракат кунед.")
        return

    file_id = update.message.audio.file_id or update.message.voice.file_id
    task_queue.append({"chat_id": update.message.chat_id, "file_id": file_id})
    await update.message.reply_text("Мусиқӣ қабул шуд! Сервер онро ба қарибӣ коркард мекунад...")

if __name__ == '__main__':
    # Гузоштани Flask дар замина (background)
    Thread(target=run_flask).start()
    
    # Ишғоли Бот
    bot_app = ApplicationBuilder().token("ТОКЕНИ_БОТИ_ШУМО").build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    bot_app.run_polling()
