import time
import os
import requests
from datetime import datetime

import configparser
import telebot
import logging
from telebot import types
from bs4 import BeautifulSoup


def get_app_dir():
    directory = os.path.dirname(os.path.abspath(__file__))
    return directory


app_dir = get_app_dir()
logging.basicConfig(
    filename=os.path.join(str(app_dir), "logs.log"),
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    encoding='utf-8'
)
config = configparser.RawConfigParser()
config.read(os.path.join(str(app_dir), 'config.properties'))

username = config.get('mayak', 'USERNAME')
password = config.get('mayak', 'PASSWORD')
token = config.get('details', 'token')
sv_id = config.get('tg_id', 'sv_id')
da_id = config.get('tg_id', 'da_id')
mm_id = config.get('tg_id', 'mm_id')

DEELAY_TIME = 120
ERROR_DEELAY_TIME = 10

bot = telebot.TeleBot(token)

URL_INITIAL = 'https://ekis.moscow/lk/actions/change'
URL_CONFIRM = 'https://center.educom.ru/oauth/sfa'
URL_ME = 'https://ekis.moscow/lk/data/user/me'
NEWS_URL = 'https://ekis.moscow/lk/data/newsfeeds/list'

session = requests.Session()
session.headers = {
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    # 'Content-Length': '0',
    'Content-Type': 'application/x-www-form-urlencoded',
    # 'Cookie': '_ym_uid=169415399627035008; _ym_d=1694153996; SessionId=JSlBD_y7TvjXADr4tE02Lw%3D%3DYXM1RUF5U1BEbTlyeGphS5xtmHjFxFap7FqxYtvq4wy0mp4msD_BvDKwAtvWQ9Qw; _ym_isad=1',
    'Origin': 'https://ekis.moscow',
    'Referer': 'https://ekis.moscow/lk/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}


class UnauthorizedException(Exception):
    logging.warning('Проблема с авторизацией')


def success_confirmation_answer(html):
    soup = BeautifulSoup(html, 'html.parser')
    header = soup.find('h4', class_='alert-heading')
    if header is None:
        logging.info('Успешная авторизация, СМС код подошел')
        return True
    logging.warning('Некорректный код подтверждения из СМС')
    return False


@bot.callback_query_handler(func=lambda call: True)
def start_auth(call):
    try:
        r = session.get(URL_INITIAL)
        next_url = r.history[1].next.url
        data = {
            'sr': 'OQ==',
            'username': username,
            'password': password,
        }

        session.post(next_url, data=data)
        bot.send_message(
            call.message.chat.id,
            'Напиши код подтверждения из СМС'
        )
        logging.info('Ввели логин и пароль, ждем код из СМС')
    except Exception as text_error:
        logging.error(f'Проблемы с авторизацией {text_error}')


def preparation_authorize():
    try:
        markup_inline = types.InlineKeyboardMarkup()
        message_text = ('Кажется мы не авторизованы.\n'
                        'Нажми "Готов!", когда будешь готов прислать код')
        item_download_card = types.InlineKeyboardButton(
            text='Готов!',
            callback_data='start_auth'
        )
        markup_inline.add(item_download_card)
        bot.send_message(sv_id, message_text, reply_markup=markup_inline)
        bot.send_message(mm_id, message_text, reply_markup=markup_inline)
        logging.info('Отправили сообщение о готовности к авторизации')
    except Exception as text_error:
        logging.error(
            f'Проблемы с отправкой сообщения о готовности к авторизации {text_error}'
        )


@bot.message_handler(content_types=["text"])
def auth(message):
    try:
        data = {
            'confirm_code': message.text,
            'sfa_time_reload': '',
        }
        r = session.post(URL_CONFIRM, data=data)
        html = r.text
        if not success_confirmation_answer(html):
            bot.send_message(message.chat.id, 'Код не подошел.. ')
            preparation_authorize()
            return
        bot.send_message(message.chat.id, 'Все отлично! Ждем писем')
        bot.stop_polling()
    except Exception as text_error:
        logging.error(f'Проблемы с вводом СМС пароля {text_error}')


def get_news():
    try:
        VIEWED = 1
        READ = 2

        current_page = 1

        new_news = []
        while True:
            params = {
                'page': current_page,
            }

            r = session.post(NEWS_URL, params=params)
            if r.status_code == 401:
                raise UnauthorizedException
            response = r.json()
            data = response['data']
            if len(data) == 0:
                if len(new_news) > 0:
                    logging.info(f'Появились новости. {len(new_news)} шт.')
                logging.info(f'Появились новости. {len(new_news)} шт.')
                return new_news
            for news in data:
                if news['status'] == VIEWED or news['status'] == READ:
                    new_news.append(news)

            current_page += 1
    except Exception as text_error:
        logging.error(f'Проблема с получением новостей {text_error}')


def download_attachment(news_id, attachments):
    try:
        link = 'https://ekis.moscow/lk/data/newsfeeds/download/' + news_id
        for attachment in attachments:
            attachment_url = link + '/' + str(attachment['guid'])
            response = session.get(attachment_url, allow_redirects=True)
            open(os.path.join(str(app_dir),
                              'download',
                              attachment['file_full_name']
                              ), 'wb').write(response.content)
        logging.info('Успешно сохранены все вложения')
    except Exception as text_error:
        logging.error(
            f'Проблемы с сохранением вложенных документов {text_error}'
        )


def send_news_to_tg(news):
    try:
        datetime_news = datetime.strptime(
            news['publish_at'],
            '%Y-%m-%dT%H:%M:%S%z'
        )
        formatted_datetime = datetime_news.strftime("%d-%m-%Y %H:%M")
        message = f'❗<b>Новое в МАЯКе!</b> <i> {str(formatted_datetime)}</i>\n\n'
        message += news['text']
        if len(news['form_link']) > 0:
            message += (f'\n\n <a href="{news["form_link"]}">'
                        f'<i>ссылка на форму</i></a>')

        attachments = os.listdir(os.path.join(str(app_dir), 'download'))
        media_group = []
        for attachment in attachments:
            file_dir = os.path.join(str(app_dir), 'download', attachment)
            media_group.append(types.InputMediaDocument(open(file_dir, 'rb')))

        bot.send_message(mm_id, message, parse_mode='HTML')
        bot.send_media_group(
            mm_id,
            media=media_group
        )
        bot.send_message(sv_id, message, parse_mode='HTML')
        bot.send_media_group(
            sv_id,
            media=media_group
        )
        bot.send_message(da_id, message, parse_mode='HTML')
        bot.send_media_group(
            da_id,
            media=media_group
        )

        for media in media_group:
            media.media.close()
            os.remove(media.media.name)
        logging.info('Сообщения с новостями отправлены')
    except Exception as text_error:
        logging.error(f'Проблема с отправкой новостей в тг {text_error}')


def mark_read(news):
    try:
        read_url = 'https://ekis.moscow/lk/data/newsfeeds/' + str(news['id'])
        EKIS_FORM_URL = 'https://ekis.moscow/lk/data/services/redirect/ekis'
        r = session.post(read_url)
        response = r.json()
        data = response['data']
        if len(data['form_link']) > 0:
            news['form_link'] = 'https://st.educom.ru' + data['form_link']
            json_data = {
                'endpoint': 'form',
                'path': data['form_link'],
            }
            session.post(EKIS_FORM_URL, json=json_data)
        if len(data['attachments']) > 0:
            download_attachment(str(news['id']), data['attachments'])
        logging.info('Новости прочитаны')
        return news
    except Exception as text_error:
        logging.error(f'Проблемы с прочитыванием новостей {text_error}')


def bot_polling():
    logging.info('Запуск бота')
    bot.send_message(da_id, 'Бот МАЯКер запущен')

    preparation_authorize()
    bot.polling(none_stop=True, timeout=123)
    while True:
        try:
            newsfeed = get_news()
            for news in newsfeed:
                mark_read(news)
                send_news_to_tg(news)
            time.sleep(DEELAY_TIME)
        except UnauthorizedException:
            logging.warning('Ошибка авторизации')
            preparation_authorize()
        except Exception as text_error:
            logging.error(f'Ошибка - {text_error}')
            bot.send_message(
                sv_id,
                f'У нас проблемы, сплю {ERROR_DEELAY_TIME} сек.\n {text_error}'
            )
            time.sleep(ERROR_DEELAY_TIME)


if __name__ == "__main__":
    bot_polling()
