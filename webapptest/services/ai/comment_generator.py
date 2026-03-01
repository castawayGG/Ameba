"""
Сервис генерации комментариев на основе ИИ (OpenAI/Claude).

Используется для Блока 1: Автоматизация аккаунтов (Фарминг и Прогрев).
Генерирует реалистичные комментарии на основе контекста поста.
"""
import random
from typing import Optional
from core.config import Config
from core.logger import log


def _get_ai_config() -> dict:
    """Читает конфигурацию AI из настроек панели или config."""
    try:
        from core.database import SessionLocal
        from models.panel_settings import PanelSettings
        db = SessionLocal()
        try:
            settings = {s.key: s.value for s in db.query(PanelSettings).filter(
                PanelSettings.key.in_(['ai_provider', 'openai_api_key', 'claude_api_key', 'ai_model', 'ai_enabled'])
            ).all()}
            return settings
        finally:
            db.close()
    except Exception:
        return {}


def generate_comment(post_text: str, style: str = 'neutral', language: str = 'ru') -> Optional[str]:
    """
    Генерирует комментарий на основе текста поста с помощью AI.
    
    :param post_text: Текст поста для комментирования
    :param style: Стиль комментария ('positive', 'neutral', 'question', 'emoji')
    :param language: Язык комментария ('ru', 'en', 'uk')
    :return: Сгенерированный комментарий или None при ошибке
    """
    config = _get_ai_config()
    
    if config.get('ai_enabled', 'false') == 'false':
        return _fallback_comment(style)
    
    provider = config.get('ai_provider', 'openai')
    
    if provider == 'openai':
        return _generate_openai(post_text, style, language, config)
    elif provider == 'claude':
        return _generate_claude(post_text, style, language, config)
    else:
        return _fallback_comment(style)


def _generate_openai(post_text: str, style: str, language: str, config: dict) -> Optional[str]:
    """Генерация через OpenAI API."""
    api_key = config.get('openai_api_key', '')
    if not api_key:
        log.warning("OpenAI API key not configured, using fallback")
        return _fallback_comment(style)
    
    try:
        import requests
        model = config.get('ai_model', 'gpt-3.5-turbo')
        
        style_prompts = {
            'positive': 'восторженный и поддерживающий',
            'neutral': 'нейтральный и информативный',
            'question': 'в виде вопроса, проявляющего интерес',
            'emoji': 'с эмодзи, живой и непринуждённый',
        }
        style_desc = style_prompts.get(style, 'нейтральный')
        
        lang_map = {'ru': 'русском', 'en': 'английском', 'uk': 'украинском'}
        lang_desc = lang_map.get(language, 'русском')
        
        system_prompt = (
            f"Ты помощник, генерирующий короткие реалистичные комментарии к постам в Telegram. "
            f"Комментарий должен быть на {lang_desc} языке, {style_desc}, "
            f"длиной 10-60 слов. Только текст комментария, без пояснений."
        )
        
        resp = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': f"Пост: {post_text[:500]}"},
                ],
                'max_tokens': 150,
                'temperature': 0.9,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()['choices'][0]['message']['content'].strip()
        log.error(f"OpenAI API error: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log.error(f"generate_openai error: {e}")
    return _fallback_comment(style)


def _generate_claude(post_text: str, style: str, language: str, config: dict) -> Optional[str]:
    """Генерация через Claude (Anthropic) API."""
    api_key = config.get('claude_api_key', '')
    if not api_key:
        log.warning("Claude API key not configured, using fallback")
        return _fallback_comment(style)
    
    try:
        import requests
        style_prompts = {
            'positive': 'enthusiastic and supportive',
            'neutral': 'neutral and informative',
            'question': 'as a curious question',
            'emoji': 'casual with emojis',
        }
        style_desc = style_prompts.get(style, 'neutral')
        lang_map = {'ru': 'Russian', 'en': 'English', 'uk': 'Ukrainian'}
        lang_desc = lang_map.get(language, 'Russian')
        
        prompt = (
            f"Generate a short realistic Telegram comment in {lang_desc}, "
            f"{style_desc} style, 10-60 words. Post: {post_text[:500]}"
        )
        
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'claude-3-haiku-20240307',
                'max_tokens': 150,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()['content'][0]['text'].strip()
        log.error(f"Claude API error: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log.error(f"generate_claude error: {e}")
    return _fallback_comment(style)


def _fallback_comment(style: str) -> str:
    """Возвращает случайный комментарий-заглушку при недоступности AI."""
    fallbacks = {
        'positive': [
            'Отличный пост! 👍',
            'Очень полезно, спасибо!',
            'Согласен на все 100%! 🔥',
            'Интересно, буду следить за обновлениями!',
            'Круто! Продолжай в том же духе 💪',
        ],
        'neutral': [
            'Интересная точка зрения.',
            'Спасибо за информацию.',
            'Стоит обдумать.',
            'Хороший материал.',
        ],
        'question': [
            'А что вы думаете о практическом применении?',
            'Есть ли примеры из жизни?',
            'Как это работает на практике?',
            'Можно узнать подробнее?',
        ],
        'emoji': [
            '🔥🔥🔥',
            '👍❤️',
            '💯 согласен!',
            '🚀 отлично!',
        ],
    }
    pool = fallbacks.get(style, fallbacks['neutral'])
    return random.choice(pool)
