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
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By


def get_app_dir():
    """Получение директории нахождения программы."""
    return os.path.dirname(os.path.abspath(__file__))


def get_tg_id():
    """Получение списка id сотрудников, которым нужно отправлять новости."""
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
MIN_ERROR_DELAY_TIME = 10
MAX_ERROR_DELAY_TIME = 3600

bot = telebot.TeleBot(token)

URL_ME = 'https://ekis.moscow/lk/api/v1/user/me'
URL_INITIAL = 'https://ekis.moscow/lk/actions/change'
# URL_INITIAL = 'https://center.educom.ru/oauth/auth?sr=OQ=='
URL_CONFIRM = 'https://center.educom.ru/oauth/sfa'
URL_NEWS = 'https://ekis.moscow/lk/api/v1/newsfeeds/list'
URL_UPDATE = 'https://ekis.moscow/lk/api/v1/newsfeeds/update'
URL_ATTACHMENT = 'https://ekis.moscow/lk/api/v1/newsfeeds/download/'
URL_READ_NEWS = 'https://ekis.moscow/lk/api/v1/newsfeeds/'
URL_EKIS_FORM = 'https://ekis.moscow/lk/api/v1/services/redirect/ekis'

session = requests.Session()
session.headers = {
    'authority': 'ekis.moscow',
    'accept': '*/*',
    'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'referer': 'https://ekis.moscow/lk/',
    'sec-ch-ua': '"Chromium";v="118", "Google Chrome";v="118",'
                 '"Not=A?Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/118.0.0.0 Safari/537.36',
}


# Настройка браузера

CSRF_NAME_VALUE = ''
CSRF_VALUE_VALUE = ''
AUTH_COOKIES = ''


class UnauthorizedException(Exception):
    """Возникает при сбое авторизации."""
    pass


class NewsException(Exception):
    """Возникает при проблемах с получением новостей."""
    pass


def success_confirmation_answer(html):
    """Возвращает True при правильно введенном СМС-коде авторизации."""
    soup = BeautifulSoup(html, 'html.parser')
    header = soup.find('h4', class_='alert-heading')
    if header is None:
        logging.info('Успешная авторизация, СМС код подошел')
        return True
    logging.warning('Некорректный код подтверждения из СМС')
    return False
    # if header.get_text() == 'Ошибка!':
    #     logging.warning('Некорректный код подтверждения из СМС')
    #     return False
    # logging.info('Успешная авторизация, СМС код подошел')
    # return True


@bot.callback_query_handler(func=lambda call: True)
def start_auth(call):
    """Первая часть авторизации.

    Ввод логина и пароля, запрос СМС пароля."""
    try:
        global CSRF_NAME_VALUE
        global CSRF_VALUE_VALUE
        global AUTH_COOKIES

        opts = Options()
        opts.add_argument("--headless")
        opts.set_preference('devtools.jsonview.enabled', False)

        browser = Firefox(options=opts)

        browser.get('https://center.educom.ru/oauth/auth?sr=OQ==')
        time.sleep(2)

        el = browser.find_element(By.ID, 'username')
        el.send_keys(username)
        el = browser.find_element(By.ID, 'password')
        el.send_keys(password)
        time.sleep(2)

        el = browser.find_element(By.ID, 'btn_login_submit')
        el.click()

        result = browser.page_source
        soup = BeautifulSoup(result, 'html.parser')

        csrf_name_input = soup.find('input', {'name': 'csrf_name'})
        CSRF_NAME_VALUE = csrf_name_input['value']

        csrf_value_input = soup.find('input', {'name': 'csrf_value'})
        CSRF_VALUE_VALUE = csrf_value_input['value']
        AUTH_COOKIES = browser.get_cookies()
        browser.quit()
        bot.send_message(
            call.message.chat.id,
            'Напиши код подтверждения из СМС'
        )
        logging.info('Ввели логин и пароль, ждем код из СМС')
    except Exception as text_error:
        logging.error(f'Проблемы с авторизацией {text_error}')


def prepare_authorize():
    """Подготовка к авторизации.

    В этой функции происходит отправка сообщения пользователю, на которое нужно
    ответить, когда он будет готов ввести пароль из СМС.
    """
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
    """Сохранение куков после успешной авторизации."""
    try:
        cookies_dict = requests.utils.dict_from_cookiejar(session.cookies)
        with open('cookies.json', 'w') as file:
            json.dump(cookies_dict, file)
        logging.info('Куки сохранены')
    except Exception as text_error:
        logging.error(f'Проблемы с сохранением куки {text_error}')


def load_cookies():
    """Загрузка куков из файла для работы."""
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
    """Проверка куков на актуальность."""
    params = {
        'page': '1',
    }
    r = session.get(URL_NEWS, params=params)
    if r.status_code != 200:
        logging.warning('Куки не валидны')
        return False
    return True


@bot.message_handler(content_types=["text"])
def enter_pass(message):
    """Вторая часть авторизации. Ввод пароля из СМС."""
    try:
        session = requests.Session()
        for cookie in AUTH_COOKIES:
            session.cookies.set(cookie['name'], cookie['value'],
                                domain=cookie['domain'])
        data = {
            'sr': 'OQ==',
            'csrf_name': CSRF_NAME_VALUE,
            'csrf_value': CSRF_VALUE_VALUE,
            'confirm_code': message.text,
            'sfa_time_reload': '',
        }
        r = session.post(URL_CONFIRM, data=data)

        html = r.text
        if not success_confirmation_answer(html):
            bot.send_message(message.chat.id, 'Код не подошел.. ')
            prepare_authorize()
            return


        # #ДЛЯ И.О.
        # URL_IO = 'https://center.educom.ru/oauth/sel'
        # data = {
        #      'sr': 'OQ==',
        #      'role': '450031',
        #  }
        # session.post(URL_IO, data=data)
        # #КОНЕЦ ДЛЯ И.О.

        bot.send_message(message.chat.id, 'Все отлично! Ждем писем')
        save_cookies_from_session(session)
        bot.stop_polling()
        return session
    except Exception as text_error:
        logging.error(f'Проблемы с вводом СМС пароля {text_error}')


def auth():
    """Весь путь авторизации"""
    prepare_authorize()
    bot.polling(none_stop=True, timeout=123)
    load_cookies()


def get_news():
    """Получение непрочитанных и непросмотренных новостей."""
    try:
        VIEWED = 1
        READ = 2
        current_page = 1
        new_news = []
        while True:
            params = {
                'page': str(current_page),
            }
            r = session.get(URL_NEWS, params=params)
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
        raise UnauthorizedException
    except Exception as text_error:
        raise NewsException


def download_attachment(news_id, attachments):
    """Загрузка вложенных к новостям документов."""
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
    """Получение пути к папке с сохраненными вложениями из новостей."""
    downloaded_files_path = []
    downloaded_file_names = os.listdir(os.path.join(str(app_dir), 'download'))
    for file_name in downloaded_file_names:
        downloaded_files_path.append(os.path.join(str(app_dir), 'download',
                                                  file_name))
    return downloaded_files_path


def send_media_group(tg_id, message):
    """Группировка документов для отправки одним сообщением."""
    media_group = []
    attachments = get_downloaded_files_paths()
    for attachment in attachments:
        media_group.append(types.InputMediaDocument(open(attachment, 'rb')))
    bot.send_message(tg_id, message, parse_mode='HTML')
    bot.send_media_group(
        tg_id,
        media=media_group,
        timeout=10
    )
    for media in media_group:
        media.media.close()


def send_news_to_tg(news):
    """Отправка новости в телеграм."""
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
        logging.info('Сообщения с новостью отправлены')
    except Exception as text_error:
        logging.error(f'Проблема с отправкой новостей в тг {text_error}')


def mark_read(news):
    """Новость в МАЯКе отмечается как прочитанная."""
    try:
        read_url = URL_READ_NEWS + str(news['id'])
        r = session.get(read_url, allow_redirects=True)
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
    """Отправка сообщения группе получателей."""
    for tg_id in tg_ids:
        bot.send_message(tg_id, message)


def bot_polling():
    """Основная функция."""
    logging.info('Запуск бота')
    news_excep_count = 0
    send_messages(tg_id_list, 'Бот МАЯКер запущен')
    session.get(URL_INITIAL)
    load_cookies()
    error_delay_time = MIN_ERROR_DELAY_TIME
    if not is_cookies_valid(session):
        auth()
    while True:
        try:
            newsfeed = get_news()
            for news in newsfeed:
                mark_read(news)
                send_news_to_tg(news)
            time.sleep(CHECK_DELAY_TIME)
            error_delay_time = MIN_ERROR_DELAY_TIME

        except NewsException:
            if news_excep_count > 3:
                news_excep_count = 0
                logging.warning('Проблема с авторизацией')
                auth()
            else:
                logging.warning('Проблема с получением новостей')
                news_excep_count += 1
                time.sleep(error_delay_time)

        except UnauthorizedException:
            logging.warning('Проблема с авторизацией')
            auth()
        except Exception as text_error:
            logging.error(f'Ошибка - {text_error}')
            try:
                send_messages(
                    tg_id_list,
                    f'У нас проблемы, сплю {error_delay_time} '
                    f'сек.\n {text_error}'
                )
            except Exception as text:
                logging.error(f'Не смог отправить сообщение {text}')
            time.sleep(error_delay_time)
            error_delay_time *= error_delay_time
            if error_delay_time > MAX_ERROR_DELAY_TIME:
                error_delay_time = MAX_ERROR_DELAY_TIME


if __name__ == "__main__":
    while True:
        try:
            bot_polling()
        except Exception as text_error:
            logging.error(f'Бот упал, ждем {MIN_ERROR_DELAY_TIME} сек.'
                          f'{text_error}')
            time.sleep(MIN_ERROR_DELAY_TIME)
