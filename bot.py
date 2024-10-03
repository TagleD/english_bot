from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
import psycopg2
import random

# Словарь для хранения слов. Ключом будет tuple (user_id, block_id)
words_to_repeat = {}

# Подключение к базе данных
conn = psycopg2.connect(
    dbname='english_bot',
    user='english_bot_user',
    password='english_bot_password',
    host='localhost'
)

def start(update: Update, context: CallbackContext) -> None:
    # Отправляем приветственное сообщение и список команд
    commands = """
    Привет! Вот список команд, которые я могу выполнить:
    /add_block - Добавляет новый блок для слов.
    /add_words <block_id> - Начинает процесс добавления новых слов в указанный блок.
    /block_list <block_id> - Показывает список всех слов в указанном блоке.
    /repeat <block_id> - Начинает сессию повторения слов для указанного блока.
    """
    update.message.reply_text(commands)

# Функция для обработки команды /add_block
def add_block(update: Update, context: CallbackContext) -> None:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO \"block\" DEFAULT VALUES RETURNING id;")
    new_block_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    update.message.reply_text(f"Новый блок создан под номером {new_block_id}")

# Функция для начала добавления слов
def start_adding_words(update: Update, context: CallbackContext) -> None:
    try:
        block_id = context.args[0]  # Получаем ID блока из аргументов команды
    except IndexError:
        update.message.reply_text("Пожалуйста, укажите ID блока после команды. Например: /add_words 1")
        return
    context.user_data['adding_words'] = True
    context.user_data['block_id'] = block_id
    update.message.reply_text("Введите слова, которые вы хотите добавить в блок (отправьте 'exit' для завершения):")


def add_word(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('adding_words'):
        text = update.message.text
        if text.lower() == 'exit':
            del context.user_data['adding_words']
            update.message.reply_text("Добавление слов завершено.")
        else:
            block_id = context.user_data['block_id']
            try:
                name_en, name_ru = map(str.strip, text.split('-', 1))  # Разделяем строку на две части по тире и удаляем пробелы
                cursor = conn.cursor()
                # Заполняем все три поля: name, name_en, name_ru
                cursor.execute(
                    "INSERT INTO word (name, name_en, name_ru, block_id) VALUES (%s, %s, %s, %s)",
                    (text, name_en, name_ru, block_id)
                )
                conn.commit()
                cursor.close()
                update.message.reply_text(f"Слово '{text}' добавлено.")
            except ValueError:
                # Если не удается разделить строку, сообщаем об ошибке
                update.message.reply_text("Неправильный формат. Пожалуйста, отправьте слово в формате 'name_en - name_ru'.")

# Функция для обработки команды /block_list
def block_list(update: Update, context: CallbackContext) -> None:
    try:
        block_id = context.args[0]  # Получаем ID блока из аргументов команды
    except IndexError:
        update.message.reply_text("Пожалуйста, укажите ID блока после команды. Например: /block_list 1")
        return

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM word WHERE block_id = %s ORDER BY id", (block_id,))
    words = cursor.fetchall()
    cursor.close()

    if words:
        # Создаем список с нумерацией
        words_list = [f"{i+1}. <b>{word[0]}</b>" for i, word in enumerate(words)]
        message_text = "Список слов в блоке:\n" + "\n".join(words_list)
    else:
        message_text = "В этом блоке нет слов."

    update.message.reply_html(message_text)


def repeat(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    try:
        block_id = context.args[0]
    except IndexError:
        update.message.reply_text("Пожалуйста, укажите ID блока после команды. Например: /repeat 1")
        return

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM word WHERE block_id = %s", (block_id,))
    words = cursor.fetchall()
    cursor.close()

    if not words:
        update.message.reply_text("В этом блоке нет слов.")
        return

    words_list = [word[0] for word in words]
    random.shuffle(words_list)
    words_to_repeat[(user_id, block_id)] = words_list

    send_word(update, context, user_id, block_id)

def repeat_independent(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    try:
        block_id = context.args[0]
    except IndexError:
        update.message.reply_text("Пожалуйста, укажите ID блока после команды. Например: /repeat_independent 1")
        return

    cursor = conn.cursor()
    cursor.execute("SELECT name_ru, name_en FROM word WHERE block_id = %s", (block_id,))
    words = cursor.fetchall()
    cursor.close()

    if not words:
        update.message.reply_text("В этом блоке нет слов.")
        return

    words_to_repeat[(user_id, block_id)] = words
    random.shuffle(words_to_repeat[(user_id, block_id)])

    send_word_independent(update, context, user_id, block_id)

def send_word_independent(update: Update, context: CallbackContext, user_id, block_id):
    words_list = words_to_repeat.get((user_id, block_id), [])
    if not words_list:
        context.bot.send_message(chat_id=user_id, text="Все слова повторены!")
        return

    # Получаем русское слово
    word_ru, word_en = words_list[0]
    message = f"{word_ru}"
    keyboard = [
        [InlineKeyboardButton("Посмотреть перевод", callback_data=f"translate_{block_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=user_id, text=message, reply_markup=reply_markup)


def send_word(update: Update, context: CallbackContext, user_id, block_id):
    words_list = words_to_repeat.get((user_id, block_id), [])
    if not words_list:
        context.bot.send_message(chat_id=user_id, text="Все слова повторены!")
        return

    random.shuffle(words_list)
    word = words_list[0]  # Берем первое слово из списка
    keyboard = [
        [InlineKeyboardButton("умничка", callback_data=f"correct_{block_id}"),
         InlineKeyboardButton("повторить", callback_data=f"repeat_{block_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=user_id, text=word, reply_markup=reply_markup)

def button_repeat(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    data = query.data
    action, block_id = data.split('_')

    if action == "correct":
        if (user_id, block_id) in words_to_repeat and words_to_repeat[(user_id, block_id)]:
            words_to_repeat[(user_id, block_id)].pop(0)
        send_word(update, context, user_id, block_id)
    elif action == "repeat":
        send_word(update, context, user_id, block_id)

def button_repeat_independent(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = query.from_user.id
    action, block_id = data.split('_')
    # block_id = int(block_id)

    if (user_id, block_id) not in words_to_repeat or not words_to_repeat[(user_id, block_id)]:
        query.edit_message_text(text="Все слова повторены!")
        return

    if action == "translate":
        word_ru, word_en = words_to_repeat[(user_id, block_id)][0]
        message = f"{word_en} - {word_ru}"
        keyboard = [
            [InlineKeyboardButton("Умничка", callback_data=f"correctIndependent_{block_id}"),
             InlineKeyboardButton("Повторить", callback_data=f"repeatIndependent_{block_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text=message, reply_markup=reply_markup)

    elif action == "correctIndependent":
        words_to_repeat[(user_id, block_id)].pop(0)
        if words_to_repeat[(user_id, block_id)]:
            random.shuffle(words_to_repeat[(user_id, block_id)])
            send_word_independent(update, context, user_id, block_id)
        else:
            query.edit_message_text(text="Все слова повторены!")

    elif action == "repeatIndependent":
        # Перемешивание списка перед повторением слова, чтобы оно могло появиться позже
        random.shuffle(words_to_repeat[(user_id, block_id)])
        send_word_independent(update, context, user_id, block_id)

    print(len(words_to_repeat[(user_id, block_id)]))



def main():
    updater = Updater("6809515984:AAHSKOI0y8AFeXYpE1xeF5eVA-TEdofulko")

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add_block", add_block))
    dp.add_handler(CommandHandler("add_words", start_adding_words, pass_args=True))
    dp.add_handler(CommandHandler("block_list", block_list, pass_args=True))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, add_word))
    dp.add_handler(CommandHandler("repeat", repeat, pass_args=True))
    dp.add_handler(CommandHandler("repeat_independent", repeat_independent, pass_args=True))
    dp.add_handler(CallbackQueryHandler(button_repeat, pattern='^(repeat|correct)_'))
    dp.add_handler(CallbackQueryHandler(button_repeat_independent, pattern='^(translate|correctIndependent|repeatIndependent)_'))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()


# 6809515984:AAHSKOI0y8AFeXYpE1xeF5eVA-TEdofulko