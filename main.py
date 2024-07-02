import time
import os
import requests
from datetime import datetime
import pickle

from urllib.parse import urlparse, parse_qs
import configparser
import telebot
import logging
from telebot import types
from bs4 import BeautifulSoup


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
URL_CONFIRM = 'https://center.educom.ru/oauth/sfa'
URL_GET_AUTH = 'https://center.educom.ru/oauth/auth'
URL_NEWS = 'https://ekis.moscow/lk/api/v1/newsfeeds/list'
URL_UPDATE = 'https://ekis.moscow/lk/api/v1/newsfeeds/update'
URL_ATTACHMENT = 'https://ekis.moscow/lk/api/v1/newsfeeds/download/'
URL_READ_NEWS = 'https://ekis.moscow/lk/api/v1/newsfeeds/'
URL_EKIS_FORM = 'https://ekis.moscow/lk/api/v1/services/redirect/ekis'
URL_LK = 'https://ekis.moscow/lk/'
URL_GET_NEW_SFA = 'https://center.educom.ru/oauth/sfa?sr=OQ=='


class UnauthorizedException(Exception):
    """Возникает при сбое авторизации."""
    pass


class NewsException(Exception):
    """Возникает при проблемах с получением новостей."""
    pass


@bot.callback_query_handler(func=lambda call: True)
def start_auth(call):
    """Первая часть авторизации.

    Ввод логина и пароля, запрос СМС пароля."""
    try:
        auth_session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }
        auth_session.headers.update(headers)
        r = auth_session.get(URL_INITIAL, allow_redirects=True)
        soup = BeautifulSoup(r.text, 'html.parser')

        csrf_name_input = soup.find('input', {'name': 'csrf_name'})
        csrf_name = csrf_name_input['value']

        csrf_value_input = soup.find('input', {'name': 'csrf_value'})
        csrf_value = csrf_value_input['value']

        data = {
            'sr': 'OQ==',
            'csrf_name': csrf_name,
            'csrf_value': csrf_value,
            'username': username,
            'password': password,
        }
        time.sleep(2)
        req = auth_session.post(URL_GET_AUTH, data=data, allow_redirects=False)

        save_cookies_from_session(auth_session)
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
    """Сохранение сессии после успешной авторизации."""
    try:
        with open('session.pkl', 'wb') as file:
            pickle.dump(session, file)
        logging.info('Сессия сохранена')
    except Exception as text_error:
        logging.error(f'Проблемы с сохранением сессии: {text_error}')


def load_cookies():
    """Загрузка сессии из файла для работы."""
    try:
        session = requests.Session()
        with open('session.pkl', 'rb') as file:
            session = pickle.load(file)
        logging.info('Сессия загружена')
        return session
    except Exception as text_error:
        logging.error(f'Не существует файла с сессией,'
                      f'создаем файл, {text_error}')
        with open('session.pkl', 'wb') as f:
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
        session = load_cookies()
        get_sfa = session.get(URL_GET_NEW_SFA)
        soup = BeautifulSoup(get_sfa.text, 'html.parser')

        csrf_name_input = soup.find('input', {'name': 'csrf_name'})
        csrf_name = csrf_name_input['value']

        csrf_value_input = soup.find('input', {'name': 'csrf_value'})
        csrf_value = csrf_value_input['value']
        csrf_data = {
            'sr': 'OQ==',
            'csrf_name': csrf_name,
            'csrf_value': csrf_value,
            'confirm_code': message.text,
            'sfa_time_reload': '',
        }

        r_sfa = session.post(
            URL_CONFIRM,
            data=csrf_data,
            allow_redirects=False
        )
        location = r_sfa.headers.get('Location')
        if location == '/oauth/sfa?sr=OQ==':
            logging.warning('Некорректный код подтверждения из СМС')
            bot.send_message(message.chat.id, 'Код не подошел.. ')
            prepare_authorize()
            return
        parsed_url = urlparse(location)
        query_params = parse_qs(parsed_url.query)

        code = query_params.get('code', [None])[0]

        state = query_params.get('state', [None])[0]
        location_params = {
            'code': code,
            'state': state
        }
        base_url = parsed_url.scheme + '://' + parsed_url.netloc + parsed_url.path

        session_id = session.cookies.get('SessionId')

        special_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'ru-RU,ru;q=0.9',
            'cookie': f'SessionId={session_id}',
            'cache-control': 'max-age=0',
            'priority': 'u=0, i',
            'referer': 'https://center.educom.ru/',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        }
        session.headers.update(special_headers)
        time.sleep(1)
        r_location = session.get(
            base_url,
            params=location_params,
            allow_redirects=False
        )

        # #ДЛЯ И.О.
        # URL_IO = 'https://center.educom.ru/oauth/sel'
        # data = {
        #      'sr': 'OQ==',
        #      'role': '450031',
        #  }
        # session.post(URL_IO, data=data)
        # #КОНЕЦ ДЛЯ И.О.

        logging.info('Успешная авторизация, СМС код подошел')
        bot.send_message(message.chat.id, 'Все отлично! Ждем писем')
        save_cookies_from_session(session)
        bot.stop_polling()
    except Exception as text_error:
        logging.error(f'Проблемы с вводом СМС пароля {text_error}')


def auth():
    """Весь путь авторизации"""
    prepare_authorize()
    bot.polling(none_stop=True, timeout=123)


def get_news(session):
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
    except Exception:
        raise NewsException


def download_attachment(news_id, attachments, session):
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


def mark_read(news, session):
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
            download_attachment(str(news['id']), data['attachments'], session)
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
    error_delay_time = MIN_ERROR_DELAY_TIME
    news_excep_count = 0
    send_messages(tg_id_list, 'Бот МАЯКер запущен')
    session = load_cookies()
    if not is_cookies_valid(session):
        auth()
    while True:
        try:
            newsfeed = get_news(session)
            for news in newsfeed:
                mark_read(news, session)
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
