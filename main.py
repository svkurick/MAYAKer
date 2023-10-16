import time
import os
import requests
from datetime import datetime
import json

import configparser
import telebot
import logging
from telebot import types
from bs4 import BeautifulSoup


def get_app_dir():
    return os.path.dirname(os.path.abspath(__file__))


class UnauthorizedException(Exception):
    pass


def get_tg_id():
    list_id = []
    try:
        tg_id_text = config.get('tg_id', 'list_id')
        tg_ids = tg_id_text.split(',')
        for tg_id in tg_ids:
            list_id.append(int(tg_id))
    except Exception as text_error:
        logging.error(f'Проблема с id в конфиге, {text_error}')
    return list_id


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

main_tg_id = config.get('tg_id', 'main_id')
tg_id_list = get_tg_id()

CHECK_DELAY_TIME = 120
ERROR_DELAY_TIME = 10

bot = telebot.TeleBot(token)

URL_INITIAL = 'https://ekis.moscow/lk/actions/change'
URL_CONFIRM = 'https://center.educom.ru/oauth/sfa'
URL_ME = 'https://ekis.moscow/lk/data/user/me'
URL_NEWS = 'https://ekis.moscow/lk/data/newsfeeds/list'
URL_UPDATE = 'https://ekis.moscow/lk/data/newsfeeds/update'
URL_ATTACHMENT = 'https://ekis.moscow/lk/data/newsfeeds/download/'
URL_READ_NEWS = 'https://ekis.moscow/lk/data/newsfeeds/'
URL_EKIS_FORM = 'https://ekis.moscow/lk/data/services/redirect/ekis'

session = requests.Session()
session.headers = {
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://ekis.moscow',
    'Referer': 'https://ekis.moscow/lk/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/117.0.0.0 Safari/537.36'),
    'sec-ch-ua': ('"Google Chrome";v="117", '
                  '"Not;A=Brand";v="8", '
                  '"Chromium";v="117"'),
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}


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
        session.cookies.clear()
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


def prepare_authorize():
    try:
        logging.info('Пробуем авторизоваться')
        markup_inline = types.InlineKeyboardMarkup()
        message_text = ('Кажется мы не авторизованы.\n'
                        'Нажми "Готов!", когда будешь готов прислать код')
        item_download_card = types.InlineKeyboardButton(
            text='Готов!',
            callback_data='start_auth'
        )
        markup_inline.add(item_download_card)
        bot.send_message(main_tg_id, message_text, reply_markup=markup_inline)
        logging.info('Отправили сообщение о готовности к авторизации')
    except Exception as text_error:
        logging.error(
            f'Проблемы с отправкой сообщения о готовности к '
            f'авторизации {text_error}'
        )


def save_cookies_from_session(session):
    try:
        cookies_dict = requests.utils.dict_from_cookiejar(session.cookies)
        with open('cookies.json', 'w') as file:
            json.dump(cookies_dict, file)
        logging.info('Куки сохранены')
    except Exception as text_error:
        logging.error(f'Проблемы с сохранением куки {text_error}')


def load_cookies():
    try:
        with open('cookies.json', 'r') as file:
            cookies_dict = json.load(file)
            session.cookies.clear()
            session.cookies = requests.utils.cookiejar_from_dict(cookies_dict)
        logging.info('Куки загружены')
    except Exception as text_error:
        logging.error(f'Не существует файла с куками,'
                      f'создаем файл, {text_error}')
        with open('cookies.json', 'wb') as f:
            f.close()
    return session


def is_cookies_valid(session):
    params = {
        'page': 1,
    }
    r = session.post(URL_NEWS, params=params)
    if r.status_code != 200:
        logging.warning('Куки не валидны')
        return False
    return True


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
            prepare_authorize()
            return
        bot.send_message(message.chat.id, 'Все отлично! Ждем писем')
        save_cookies_from_session(session)
        bot.stop_polling()
        return session
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
            r = session.post(URL_NEWS, params=params)
            if r.status_code == 401:
                raise UnauthorizedException
            response = r.json()
            data = response['data']
            if len(data) == 0:
                if len(new_news) > 0:
                    logging.info(f'Появились новости. {len(new_news)} шт.')
                else:
                    logging.info('Новостей нет')
                return new_news
            for news in data:
                if news['status'] == VIEWED or news['status'] == READ:
                    new_news.append(news)
            current_page += 1
    except UnauthorizedException:
        logging.warning('Проблема с авторизацией')
        prepare_authorize()
        bot.polling()
        return []
    except Exception as text_error:
        logging.error(f'Проблема с получением новостей {text_error}')


def download_attachment(news_id, attachments):
    try:
        link = URL_ATTACHMENT + news_id
        for attachment in attachments:
            attachment_url = link + '/' + str(attachment['guid'])
            response = session.get(attachment_url, allow_redirects=True)
            open(os.path.join(str(app_dir),
                              'download',
                              attachment['file_full_name']
                              ), 'wb').write(response.content)
        logging.info(
            f'Успешно сохранено вложение {attachment["file_full_name"]}'
        )
    except Exception as text_error:
        logging.error(
            f'Проблемы с сохранением вложенных документов {text_error}'
        )


def get_downloaded_files_paths():
    downloaded_files_path = []
    downloaded_file_names = os.listdir(os.path.join(str(app_dir), 'download'))
    for file_name in downloaded_file_names:
        downloaded_files_path.append(os.path.join(str(app_dir), 'download',
                                                  file_name))
    return downloaded_files_path


def send_media_group(tg_id, message):
    media_group = []
    attachments = get_downloaded_files_paths()
    for attachment in attachments:
        media_group.append(types.InputMediaDocument(open(attachment, 'rb')))
    bot.send_message(tg_id, message, parse_mode='HTML')
    bot.send_media_group(
        tg_id,
        media=media_group
    )
    for media in media_group:
        media.media.close()


def send_news_to_tg(news):
    try:
        datetime_news = datetime.strptime(
            news['publish_at'],
            '%Y-%m-%dT%H:%M:%S%z'
        )
        formatted_datetime = datetime_news.strftime("%d-%m-%Y %H:%M")
        message = (f'❗<b>Новое в МАЯКе!</b>'
                   f' <i> {str(formatted_datetime)}</i>\n\n')
        message += news['text']
        if len(news['form_link']) > 0:
            message += (f'\n\n <a href="{news["form_link"]}">'
                        f'<i>ссылка на форму</i></a>')

        send_media_group(main_tg_id, message)
        for tg_id in tg_id_list:
            send_media_group(tg_id, message)

        for file in get_downloaded_files_paths():
            os.remove(file)
        logging.info('Сообщения с новостями отправлены')
    except Exception as text_error:
        logging.error(f'Проблема с отправкой новостей в тг {text_error}')


def mark_read(news):
    try:
        read_url = URL_READ_NEWS + str(news['id'])
        r = session.post(read_url, allow_redirects=True)
        response = r.json()
        data = response['data']
        if len(data['form_link']) > 0:
            news['form_link'] = 'https://st.educom.ru' + data['form_link']
            json_data = {
                'endpoint': 'form',
                'path': data['form_link'],
            }
            session.post(URL_EKIS_FORM, json=json_data)
            req_data = {
                'id': news['id']
            }
            session.post(
                URL_UPDATE,
                json=req_data,
                allow_redirects=True
            )

        if len(data['attachments']) > 0:
            download_attachment(str(news['id']), data['attachments'])
        logging.info(f'Новость прочитана {news["text"]} ')
        return news
    except Exception as text_error:
        logging.error(f'Проблемы с прочитыванием новостей {text_error}')


def send_messages(tg_ids, message):
    for tg_id in tg_ids:
        bot.send_message(tg_id, message)


def bot_polling():
    logging.info('Запуск бота')
    send_messages(tg_id_list, 'Бот МАЯКер запущен')
    session.get(URL_INITIAL)
    load_cookies()
    if not is_cookies_valid(session):
        prepare_authorize()
        bot.polling(none_stop=True, timeout=123)
        load_cookies()
    while True:
        try:
            newsfeed = get_news()
            for news in newsfeed:
                mark_read(news)
                send_news_to_tg(news)
            time.sleep(CHECK_DELAY_TIME)
        except Exception as text_error:
            logging.error(f'Ошибка - {text_error}')
            try:
                send_messages(
                    tg_id_list,
                    f'У нас проблемы, сплю {ERROR_DELAY_TIME} сек.\n {text_error}'
                )
            except Exception as text:
                logging.error(f'Не смог отправить сообщение {text}')
            time.sleep(ERROR_DELAY_TIME)


if __name__ == "__main__":
    bot_polling()
