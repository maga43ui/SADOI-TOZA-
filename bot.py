import os
import re
import sys
import asyncio
import logging
import aiohttp
import torch
import nest_asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton

nest_asyncio.apply()

# 🔑 Токени бот
TOKEN = "8853292452:AAFIZig_YS3ZyAS7YtQIfjWwOov_o7zN9OE"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

INPUT_DIR = "audio_input"
OUTPUT_DIR = "audio_output"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 📢 ФУНКСИЯИ ДАЪВАТИ РЕКЛАМАИ GRAMADS
async def fetch_and_show_ad(user_id: int):
    """Гирифтан ва нишон додани 1 реклама аз GramAds"""
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

# 📢 ФУНКСИЯИ НИШОН ДОДАНИ 2 РЕКЛАМА
async def show_multiple_ads(user_id: int, ad_count: int = 2):
    """Нишон додани 2 реклама пайиҳам"""
    for i in range(ad_count):
        await fetch_and_show_ad(user_id)
        if i < ad_count - 1:
            await asyncio.sleep(2)

class ProcessingState(StatesGroup):
    waiting_for_audio = State()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎵 Ҷудо кардани овоз")],
        [KeyboardButton(text="⚡️ Ҳолати Сервер")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Салом {message.from_user.first_name}!\n\n"
        f"🚀 **Боти Vocal Remover фаъол аст!**\n"
        f"Сурудро фиристед, овозро аз мусиқӣ ҷудо мекунам.",
        reply_markup=main_kb
    )

@dp.message(F.text == "⚡️ Ҳолати Сервер")
async def check_gpu(message: types.Message):
    gpu_available = torch.cuda.is_available()
    device_info = torch.cuda.get_device_name(0) if gpu_available else "CPU"
    await message.answer(f"🖥 **Сервер:** `{device_info}`\n• Статус: **Онлайн**")

@dp.message(F.text == "🎵 Ҷудо кардани овоз")
async def ask_audio(message: types.Message, state: FSMContext):
    await state.set_state(ProcessingState.waiting_for_audio)
    await message.answer("🎶 Суруд ё файли аудиоиро фиристед:")

async def run_demucs(input_path: str, output_dir: str):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # Модели сабуктар истифода мешавад, то дар Railway хотира (RAM) пур нашавад
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", "htdemucs",
        "-d", device,
        "--two-stems", "vocals",
        "-o", output_dir,
        input_path
    ]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return process.returncode, stderr.decode()

@dp.message(ProcessingState.waiting_for_audio, F.audio | F.voice | F.document)
async def handle_audio(message: types.Message, state: FSMContext):
    await state.clear()

    if message.audio:
        file_id = message.audio.file_id
        orig_name = message.audio.file_name or "song.mp3"
    elif message.voice:
        file_id = message.voice.file_id
        orig_name = "voice.ogg"
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("audio/"):
        file_id = message.document.file_id
        orig_name = message.document.file_name or "audio.mp3"
    else:
        await message.answer("❌ Лутфан танҳо файли аудиоӣ фиристед!")
        return

    # 1. Фиристодани 2 реклама пайиҳам
    await message.answer("📢 **Спонсорҳои бот:**")
    await show_multiple_ads(message.from_user.id, ad_count=2)

    status_msg = await message.answer("📥 **Файл қабул шуд.** Боргирӣ ва коркард оғоз шуд...")

    clean_filename = re.sub(r'[^a-zA-Z0-9_\.]', '_', orig_name)
    unique_file_name = f"{message.from_user.id}_{clean_filename}"
    input_file_path = os.path.join(INPUT_DIR, unique_file_name)
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, destination=input_file_path)

    await status_msg.edit_text("⚙️ **Коркард оғоз шуд...** (Сабр кунед)")

    try:
        return_code, stderr = await run_demucs(input_file_path, OUTPUT_DIR)

        if return_code != 0:
            await status_msg.edit_text(f"❌ **Хатогӣ дар коркард:**\n`{stderr[:200]}`")
            return

        track_folder_name = os.path.splitext(unique_file_name)[0]
        result_dir = os.path.join(OUTPUT_DIR, "htdemucs", track_folder_name)

        no_vocals_path = os.path.join(result_dir, "no_vocals.wav")
        vocals_path = os.path.join(result_dir, "vocals.wav")

        await status_msg.edit_text("📤 **Омода шуд!** Равонкунии файлҳо...")

        if os.path.exists(no_vocals_path):
            await message.answer_audio(FSInputFile(no_vocals_path, filename=f"Minus_{orig_name}.wav"), caption="🎼 **Мусиқӣ (Минусовка)**")

        if os.path.exists(vocals_path):
            await message.answer_audio(FSInputFile(vocals_path, filename=f"Vocal_{orig_name}.wav"), caption="🎤 **Танҳо овоз (Acapella)**")

        await status_msg.delete()
        await message.answer("✅ **Иҷро шуд!**", reply_markup=main_kb)

    except Exception as e:
        await message.answer(f"❌ Хатогии сервер: `{e}`", reply_markup=main_kb)

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Боти Telegram фаъол шуд!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
