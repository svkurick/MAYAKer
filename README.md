#  Проект МАЯКер

### С помощью этого приложения можно получать новости из МАЯКа в личный сообщения телеграм со всеми вложениями. Новости в самом МАЯКе отмечаются прочитанными!
Использованные технологии:

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

### Как пользоваться проектом?
Клонируем репозиторий:
```python
git clone https://github.com/svkurick/MAYAKer.git
```
Переходим в директорию проекта:
```python
cd MAYAKer
```
Устанавливаем зависимости:
```python
python3 -m pip install --upgrade pip
```
```python
pip install -r requirements.txt
```
Запускаем проект:
```python
python main.py
```
Указываем корректный досутп к МАЯКу и telegram-токен для бота, список id сотрудников, кому должны приходить письма в config.properties
```python
# telegram bot token
[details]
token:tg_bot_token

[mayak]
USERNAME=mayak_username
PASSWORD=mayak_password

[tg_id]
list_id=id_1,id_2
main_id=id_main
```
Запускаем бот
```python
python main.py
```
