# trainbot_with_images.py
import os
import sqlite3
import logging
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from stability_sdk import client
import stability_sdk.interfaces.goose as stability

# Ganti dengan token bot dari @BotFather
TOKEN = "7260363453:AAHkl23HlxDZxpIeTPI-L0NsNbgbNnxogzM"
# Ganti dengan API key dari Stability AI
STABILITY_API_KEY = "YOUR_STABILITY_API_KEY"

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Inisialisasi Stability client
stability_api = client.StabilityInference(
    key=STABILITY_API_KEY,
    verbose=True,
)

# Inisialisasi database SQLite
def init_db():
    conn = sqlite3.connect('brain.db')
    c = conn.cursor()
    # Tambah kolom untuk prompt gambar
    c.execute('''CREATE TABLE IF NOT EXISTS qa (
                 question TEXT PRIMARY KEY,
                 answer TEXT,
                 image_prompt TEXT)''')
    conn.commit()
    conn.close()

# Simpan pertanyaan & jawaban (text atau gambar)
def learn(question: str, answer: str = None, image_prompt: str = None):
    conn = sqlite3.connect('brain.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO qa (question, answer, image_prompt) VALUES (?, ?, ?)",
              (question.lower(), answer or "", image_prompt or ""))
    conn.commit()
    conn.close()

# Cari jawaban berdasarkan pertanyaan
def get_qa(question: str):
    conn = sqlite3.connect('brain.db')
    c = conn.cursor()
    c.execute("SELECT answer, image_prompt FROM qa WHERE question = ?", (question.lower(),))
    row = c.fetchone()
    conn.close()
    return row if row else (None, None)

# Generate gambar dari prompt via Stability AI
async def generate_image(prompt: str, update: Update):
    try:
        answers = stability_api.generate(
            prompt=prompt,
            steps=30,  # Kualitas (20-50)
            cfg_scale=8.0,  # Creativity
            width=512,
            height=512,
            samples=1,
            sampler=stability.Sampler.k_dpm_2
        )

        for resp in answers:
            for artifact in resp.artifacts:
                if artifact.type == stability.ArtifactType.IMAGE:
                    # Kirim gambar sebagai photo
                    image = BytesIO(artifact.binary)
                    image.name = "generated_image.png"
                    await update.message.reply_photo(photo=image)
                    return
        await update.message.reply_text("Gagal generate gambar, coba prompt lain!")
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        await update.message.reply_text("Error: Cek API key atau koneksi!")

# Command /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Aku bot pintar yang bisa diajarin text & gambar 😄\n\n"
        "Cara ajarin text:\n"
        "<code>bot, kalau ditanya [pertanyaan] jawab [jawaban]</code>\n\n"
        "Cara ajarin gambar:\n"
        "<code>bot, kalau ditanya gambar [deskripsi] generate [prompt AI]</code>\n\n"
        "Contoh text: bot, kalau ditanya siapa presiden jawab Prabowo\n"
        "Contoh gambar: bot, kalau ditanya gambar kucing lucu generate a cute cat in cartoon style\n\n"
        "/hapus [pertanyaan] buat hapus data"
    )

# Command /hapus [pertanyaan]
async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Cara: /hapus <pertanyaan>")
        return
    
    question = " ".join(context.args).lower()
    conn = sqlite3.connect('brain.db')
    c = conn.cursor()
    c.execute("DELETE FROM qa WHERE question = ?", (question,))
    if c.rowcount > 0:
        await update.message.reply_text(f"Berhasil lupa: {question}")
    else:
        await update.message.reply_text("Aku nggak tahu itu kok")
    conn.commit()
    conn.close()

# Tangkap pesan biasa
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lower_text = text.lower()

    # Cek apakah user sedang mengajarkan bot
    if lower_text.startswith(("bot,", "bot ", "bot:")):
        try:
            # Cek format gambar dulu
            if "gambar" in lower_text and "generate" in lower_text:
                # Format: "bot, kalau ditanya gambar [deskripsi] generate [prompt]"
                bagian = text.split("kalau ditanya gambar", 1)
                if len(bagian) < 2:
                    await update.message.reply_text("Format salah. Contoh:\nbot, kalau ditanya gambar kucing lucu generate a cute cat in cartoon style")
                    return
                
                sisa = bagian[1].strip()
                if "generate" not in sisa:
                    await update.message.reply_text("Harus ada kata 'generate' untuk prompt AI")
                    return
                
                q_prompt = sisa.split("generate", 1)
                deskripsi = q_prompt[0].strip(" ?.!,")
                prompt_ai = q_prompt[1].strip()
                
                learn(deskripsi, image_prompt=prompt_ai)
                await update.message.reply_text(f"OK! Kalau ada yang tanya gambar \"{deskripsi}\"\nAku bakal generate pakai prompt: \"{prompt_ai}\"")
                return

            # Format text biasa
            bagian = text.split("kalau ditanya", 1)
            if len(bagian) < 2:
                await update.message.reply_text("Format salah. Contoh:\nbot, kalau ditanya apa ibukota Indonesia jawab Jakarta")
                return
            
            sisa = bagian[1].strip()
            if "jawab" not in sisa:
                await update.message.reply_text("Harus ada kata 'jawab'")
                return
            
            q_a = sisa.split("jawab", 1)
            question = q_a[0].strip(" ?.!,")
            answer = q_a[1].strip()
            
            learn(question, answer=answer)
            await update.message.reply_text(f"OK! Kalau ada yang tanya:\n\"{question}\"\nAku bakal jawab:\n\"{answer}\"")
        except Exception as e:
            await update.message.reply_text("Format salah banget nih 😅 Coba lagi ya")
        return

    # Kalau bukan mengajarkan, coba jawab dari database
    answer, image_prompt = get_qa(lower_text)
    
    if image_prompt and "gambar" in lower_text:  # Prioritas gambar kalau ada
        await update.message.reply_text("Sedang generate gambar...")
        await generate_image(image_prompt, update)
    elif answer:
        await update.message.reply_text(answer)
    # Kalau belum tahu, kasih saran
    elif not lower_text.startswith(('/', 'bot,')):
        await update.message.reply_text("Aku belum tahu nih 😅\nAjarkan aku ya:\n"
                                       f"- Text: <code>bot, kalau ditanya {text} jawab [jawabanmu]</code>\n"
                                       f"- Gambar: <code>bot, kalau ditanya gambar {text} generate [prompt AI]</code>")

def main():
    init_db()
    
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hapus", hapus))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.Regex(r'^[^/]'), handle_message))

    print("Bot pintar (text + gambar) sedang berjalan...")
    app.run_polling()

if __name__ == '__main__':
    main()
