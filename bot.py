import os
import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web

# 🔑 Токени бот
TOKEN = "8853292452:AAFIZig_YS3ZyAS7YtQIfjWwOov_o7zN9OE"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

INPUT_DIR = "audio_queue"
OUTPUT_DIR = "audio_out"
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Очередь ва ҳолати Colab
colab_session = None
queue_files = []

# 📢 РЕКЛАМАИ GRAMADS
async def fetch_and_show_ad(user_id: int):
    url = f"https://api.gramads.net/v1/getAd?token={TOKEN}&user_id={user_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=3) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ad"):
                        ad_text = data["ad"].get("text", "")
                        ad_image = data["ad"].get("image_url", None)
                        if ad_image:
                            await bot.send_photo(user_id, photo=ad_image, caption=f"📢 **Реклама:**\n\n{ad_text}")
                        elif ad_text:
                            await bot.send_message(user_id, text=f"📢 **Реклама:**\n\n{ad_text}")
    except Exception as e:
        logging.error(f"GramAds Error: {e}")

class ProcessingState(StatesGroup):
    waiting_for_audio = State()

main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🎵 Ҷудо кардани овоз")],[KeyboardButton(text="⚡️ Ҳолати Сервер")]],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Салом {message.from_user.first_name}!\n\n🚀 **Боти Vocal Remover фаъол аст!**", reply_markup=main_kb)

@dp.message(F.text == "⚡️ Ҳолати Сервер")
async def check_server(message: types.Message):
    status = "🟢 Онлайн (GPU Colab)" if colab_session else "🟠 Офлайн (Дар навбат мемонад)"
    await message.answer(f"🖥 **Ҳолати манбаъ:**\n• Модели GPU: {status}\n• Файлҳо дар навбат: `{len(queue_files)}`")

@dp.message(F.text == "🎵 Ҷудо кардани овоз")
async def ask_audio(message: types.Message, state: FSMContext):
    await state.set_state(ProcessingState.waiting_for_audio)
    await message.answer("🎶 Суруд ё файли аудиоиро фиристед:")

@dp.message(ProcessingState.waiting_for_audio, F.audio | F.voice | F.document)
async def handle_audio(message: types.Message, state: FSMContext):
    await state.clear()
    await fetch_and_show_ad(message.from_user.id)

    file_obj = message.audio or message.voice or message.document
    orig_name = getattr(file_obj, 'file_name', 'song.mp3') or 'song.mp3'
    
    file_info = await bot.get_file(file_obj.file_id)
    file_path = os.path.join(INPUT_DIR, f"{message.from_user.id}_{orig_name}")
    await bot.download_file(file_info.file_path, destination=file_path)

    if colab_session:
        await message.answer("⚙️ **Сервер фаъол аст!** Коркарди аудио оғоз шуд...")
        # Ба Colab пайваст мекунем
        asyncio.create_task(send_to_colab(file_path, message.from_user.id, orig_name))
    else:
        queue_files.append({"path": file_path, "user_id": message.from_user.id, "name": orig_name})
        await message.answer("⏳ **Сервери GPU ҳоло хоб аст.**\n\nАудиои шумо ба навбат гирифта шуд. Ҳамин ки сервер пайваст шуд, автоматикӣ минусовка сохта ба шумо фиристода мешавад!")

async def send_to_colab(file_path, user_id, orig_name):
    global colab_session
    if not colab_session:
        return
    try:
        data = aiohttp.FormData()
        data.add_field('file', open(file_path, 'rb'))
        data.add_field('user_id', str(user_id))
        data.add_field('orig_name', orig_name)
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{colab_session}/process", data=data) as resp:
                pass
    except Exception as e:
        logging.error(f"Colab send error: {e}")

# API барои пайваст кардани Colab ба Railway
async def register_colab(request):
    global colab_session
    data = await request.json()
    colab_session = data.get("url")
    print(f"✅ Google Colab пайваст шуд: {colab_session}")
    
    # Аввалин коркарди файлҳои дар навбат монда
    asyncio.create_task(process_queue())
    return web.json_response({"status": "ok"})

async def receive_result(request):
    data = await request.post()
    user_id = int(data['user_id'])
    orig_name = data['orig_name']
    
    no_vocals = data['no_vocals']
    vocals = data['vocals']

    no_vocals_path = os.path.join(OUTPUT_DIR, f"minus_{orig_name}.wav")
    vocals_path = os.path.join(OUTPUT_DIR, f"vocal_{orig_name}.wav")

    with open(no_vocals_path, 'wb') as f:
        f.write(no_vocals.file.read())
    with open(vocals_path, 'wb') as f:
        f.write(vocals.file.read())

    await bot.send_audio(user_id, FSInputFile(no_vocals_path), caption="🎼 **Мусиқӣ (Минусовка)**")
    await bot.send_audio(user_id, FSInputFile(vocals_path), caption="🎤 **Танҳо овоз (Acapella)**")
    return web.json_response({"status": "sent"})

async def process_queue():
    while queue_files and colab_session:
        item = queue_files.pop(0)
        await send_to_colab(item["path"], item["user_id"], item["name"])
        await asyncio.sleep(1)

app = web.Application()
app.router.add_post('/register_colab', register_colab)
app.router.add_post('/receive_result', receive_result)

async def main():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())