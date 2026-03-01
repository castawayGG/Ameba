"""
Генератор личностей для аккаунтов.

Блок 1: Автоматизация аккаунтов (Фарминг и Прогрев).
Создаёт реалистичные профили: имя из спинтакса, биография, аватар с thisPersonDoesNotExist.
"""
import io
import random
from typing import Optional
from core.logger import log


# Спинтакс-шаблоны для имён и биографий
_FIRST_NAMES_RU = [
    'Александр', 'Дмитрий', 'Максим', 'Иван', 'Андрей', 'Алексей', 'Никита',
    'Михаил', 'Сергей', 'Артём', 'Анастасия', 'Екатерина', 'Ольга', 'Мария',
    'Наталья', 'Татьяна', 'Юлия', 'Виктория', 'Елена', 'Светлана',
]
_FIRST_NAMES_EN = [
    'Alex', 'Mike', 'John', 'David', 'Chris', 'James', 'Daniel', 'Mark',
    'Emma', 'Sophia', 'Olivia', 'Isabella', 'Mia', 'Charlotte', 'Amelia',
]
_LAST_NAMES_RU = [
    'Иванов', 'Смирнов', 'Кузнецов', 'Попов', 'Васильев', 'Петров',
    'Соколов', 'Михайлов', 'Новиков', 'Фёдоров', 'Морозов', 'Волков',
]
_LAST_NAMES_EN = [
    'Smith', 'Johnson', 'Williams', 'Jones', 'Brown', 'Davis', 'Miller',
    'Wilson', 'Moore', 'Taylor', 'Anderson', 'Thomas',
]
_BIO_TEMPLATES_RU = [
    'Люблю путешествия и новые знакомства 🌍',
    'Предприниматель | Инвестиции | Саморазвитие',
    'Живу здесь и сейчас ✨ DM открыт',
    'Спорт, работа, семья — три кита моей жизни 💪',
    'Фотограф-любитель | Кофеман ☕',
    'Ищу интересных людей для общения',
    'Работаю на себя. Жизнь коротка 🚀',
    'Читаю книги, смотрю фильмы, думаю о жизни',
]
_BIO_TEMPLATES_EN = [
    'Love traveling and meeting new people 🌍',
    'Entrepreneur | Investments | Self-development',
    'Living in the moment ✨ DM open',
    'Sports, work, family — my three pillars 💪',
    'Amateur photographer | Coffee lover ☕',
    'Looking for interesting people to chat',
    'Self-employed. Life is short 🚀',
    'Reading books, watching movies, thinking about life',
]


def generate_random_name(lang: str = 'ru') -> dict:
    """
    Генерирует случайное имя и фамилию.
    
    :param lang: Язык ('ru' или 'en')
    :return: {'first_name': ..., 'last_name': ...}
    """
    if lang == 'ru':
        return {
            'first_name': random.choice(_FIRST_NAMES_RU),
            'last_name': random.choice(_LAST_NAMES_RU),
        }
    return {
        'first_name': random.choice(_FIRST_NAMES_EN),
        'last_name': random.choice(_LAST_NAMES_EN),
    }


def generate_random_bio(lang: str = 'ru') -> str:
    """
    Генерирует случайную биографию из шаблонов.
    
    :param lang: Язык ('ru' или 'en')
    :return: Строка биографии
    """
    templates = _BIO_TEMPLATES_RU if lang == 'ru' else _BIO_TEMPLATES_EN
    return random.choice(templates)


def fetch_ai_avatar() -> Optional[bytes]:
    """
    Скачивает случайное лицо с thisPersonDoesNotExist.com.
    
    :return: Байты JPEG-изображения или None при ошибке
    """
    try:
        import requests
        # thisPersonDoesNotExist отдаёт случайное лицо на каждый запрос
        resp = requests.get(
            'https://thispersondoesnotexist.com/',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            timeout=10,
        )
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception as e:
        log.warning(f"fetch_ai_avatar error: {e}")
    return None


def generate_full_personality(lang: str = 'ru') -> dict:
    """
    Генерирует полную личность: имя, биографию, аватар.
    
    :param lang: Язык ('ru' или 'en')
    :return: Словарь с полями first_name, last_name, bio, avatar_bytes
    """
    name = generate_random_name(lang)
    bio = generate_random_bio(lang)
    avatar = fetch_ai_avatar()
    return {
        'first_name': name['first_name'],
        'last_name': name['last_name'],
        'bio': bio,
        'avatar_bytes': avatar,
    }


def apply_personality_to_account(account_id: str, lang: str = 'ru') -> dict:
    """
    Применяет случайную личность к Telegram-аккаунту.
    Обновляет имя, биографию и фотографию профиля.
    
    :param account_id: ID аккаунта
    :param lang: Язык имени
    :return: Результат {'success': bool, 'applied': dict, 'error': str}
    """
    import asyncio
    from services.telegram.actions import get_telegram_client, update_profile, update_avatar
    
    personality = generate_full_personality(lang)
    results = {'applied': {}, 'errors': []}
    
    async def _apply():
        try:
            ok = await update_profile(
                account_id,
                first_name=personality['first_name'],
                last_name=personality['last_name'],
                about=personality['bio'],
            )
            if ok:
                results['applied']['name'] = f"{personality['first_name']} {personality['last_name']}"
                results['applied']['bio'] = personality['bio']
            else:
                results['errors'].append('Failed to update profile')
        except Exception as e:
            results['errors'].append(f"Profile update error: {e}")
        
        if personality.get('avatar_bytes'):
            try:
                ok = await update_avatar(account_id, personality['avatar_bytes'])
                if ok:
                    results['applied']['avatar'] = 'updated'
                else:
                    results['errors'].append('Failed to update avatar')
            except Exception as e:
                results['errors'].append(f"Avatar update error: {e}")
    
    try:
        asyncio.run(_apply())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_apply())
        loop.close()
    
    return {
        'success': len(results['errors']) == 0,
        'applied': results['applied'],
        'errors': results['errors'],
        'personality': {
            'first_name': personality['first_name'],
            'last_name': personality['last_name'],
            'bio': personality['bio'],
        },
    }
