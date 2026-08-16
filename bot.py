import os
import sys
import asyncio
import logging
import torch
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("BOT_TOKEN", "8853292452:AAFIZig_YS3ZyAS7YtQIfjWwOov_o7zN9OE")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

INPUT_DIR = "/tmp/audio_input"
OUTPUT_DIR = "/tmp/audio_output"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
    device_info = torch.cuda.get_device_name(0) if gpu_available else "CPU (Railway)"
    await message.answer(
        f"🖥 **Ҳолати манбаъ:**\n"
        f"• Дастгоҳ: `{device_info}`\n"
        f"• Статус: **24/7 Онлайн**"
    )

@dp.message(F.text == "🎵 Ҷудо кардани овоз")
async def ask_audio(message: types.Message, state: FSMContext):
    await state.set_state(ProcessingState.waiting_for_audio)
    await message.answer("🎶 Суруд ё файли аудиоиро фиристед:")

async def run_demucs(input_path: str, output_dir: str):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", "htdemucs",
        "-d", device,
        "--two-stems", "vocals",
        "-o", output_dir,
        input_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.wait()

@dp.message(ProcessingState.waiting_for_audio, F.audio | F.voice | F.document)
async def handle_audio(message: types.Message, state: FSMContext):
    await state.clear()
    
    if message.audio:
        file_id, file_name = message.audio.file_id, message.audio.file_name or "song.mp3"
    elif message.voice:
        file_id, file_name = message.voice.file_id, "voice.ogg"
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("audio/"):
        file_id, file_name = message.document.file_id, message.document.file_name
    else:
        await message.answer("❌ Лутфан танҳо файли аудиоӣ фиристед!")
        return

    status_msg = await message.answer("📥 **Файл қабул шуд.** Боргирӣ ба сервер...")

    clean_name = f"{message.from_user.id}_{file_name}"
    input_file_path = os.path.join(INPUT_DIR, clean_name)
    
    file_info = await bot.get_file(file_id)
    await bot.download_file(file_info.file_path, destination=input_file_path)

    await status_msg.edit_text("⚙️ **Коркард дар сервер оғоз шуд...** сабр кунед.")

    try:
        await run_demucs(input_file_path, OUTPUT_DIR)

        await status_msg.edit_text("📤 **Коркард хатм шуд!** Равонкунии файлҳо...")

        track_folder_name = os.path.splitext(clean_name)[0]
        result_dir = os.path.join(OUTPUT_DIR, "htdemucs", track_folder_name)

        no_vocals_path = os.path.join(result_dir, "no_vocals.wav")
        vocals_path = os.path.join(result_dir, "vocals.wav")

        if os.path.exists(no_vocals_path):
            music_file = FSInputFile(no_vocals_path, filename=f"Minus_{file_name}.wav")
            await message.answer_audio(music_file, caption="🎼 **Мусиқӣ (Минусовка)**")

        if os.path.exists(vocals_path):
            vocal_file = FSInputFile(vocals_path, filename=f"Vocal_{file_name}.wav")
            await message.answer_audio(vocal_file, caption="🎤 **Танҳо овоз (Acapella)**")

        await status_msg.delete()
        await message.answer("✅ **Омода шуд!** Суруди навбатиро фиристонед.", reply_markup=main_kb)

    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer(f"❌ Хатогӣ рух дод: `{e}`", reply_markup=main_kb)

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Боти Telegram фаъол шуд!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
