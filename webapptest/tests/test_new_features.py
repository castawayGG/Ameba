"""
Тесты для новых модулей из 7 тематических блоков.

Блок 1: AI Фарминг (comment_generator, personality)
Блок 3: Расширенный парсинг (lookalike, scrub)
Блок 4: Клоакинг, Turnstile
Блок 5: Ротация прокси
Блок 7: PDF/HTML отчёты
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Блок 1: AI генерация комментариев
# ---------------------------------------------------------------------------

class TestCommentGenerator:
    def test_fallback_positive(self):
        """Fallback-комментарий с стилем positive не пустой."""
        from services.ai.comment_generator import _fallback_comment
        result = _fallback_comment('positive')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_all_styles(self):
        from services.ai.comment_generator import _fallback_comment
        for style in ['positive', 'neutral', 'question', 'emoji', 'unknown']:
            result = _fallback_comment(style)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_generate_comment_disabled_ai_returns_fallback(self):
        """Если AI отключён — возвращает fallback-комментарий."""
        with patch('services.ai.comment_generator._get_ai_config', return_value={'ai_enabled': 'false'}):
            from services.ai.comment_generator import generate_comment
            result = generate_comment('Тестовый текст поста', style='neutral')
            assert isinstance(result, str)
            assert len(result) > 0

    def test_generate_comment_openai_success(self):
        """Успешный вызов OpenAI API возвращает сгенерированный текст."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'choices': [{'message': {'content': 'Отличный пост!'}}]
        }
        with patch('services.ai.comment_generator._get_ai_config', return_value={
            'ai_enabled': 'true', 'ai_provider': 'openai', 'openai_api_key': 'sk-test'
        }):
            with patch('requests.post', return_value=mock_resp):
                from services.ai.comment_generator import generate_comment
                result = generate_comment('Тест')
                assert result == 'Отличный пост!'

    def test_generate_comment_openai_error_returns_fallback(self):
        """При ошибке OpenAI API возвращает fallback."""
        with patch('services.ai.comment_generator._get_ai_config', return_value={
            'ai_enabled': 'true', 'ai_provider': 'openai', 'openai_api_key': 'sk-test'
        }):
            with patch('requests.post', side_effect=Exception('network error')):
                from services.ai.comment_generator import generate_comment
                result = generate_comment('Тест')
                assert isinstance(result, str)
                assert len(result) > 0


# ---------------------------------------------------------------------------
# Блок 1: Генератор личностей
# ---------------------------------------------------------------------------

class TestPersonalityGenerator:
    def test_generate_random_name_ru(self):
        from services.accounts.personality import generate_random_name
        name = generate_random_name('ru')
        assert 'first_name' in name
        assert 'last_name' in name
        assert len(name['first_name']) > 0
        assert len(name['last_name']) > 0

    def test_generate_random_name_en(self):
        from services.accounts.personality import generate_random_name
        name = generate_random_name('en')
        assert 'first_name' in name
        assert 'last_name' in name

    def test_generate_random_bio_ru(self):
        from services.accounts.personality import generate_random_bio
        bio = generate_random_bio('ru')
        assert isinstance(bio, str)
        assert len(bio) > 0

    def test_generate_random_bio_en(self):
        from services.accounts.personality import generate_random_bio
        bio = generate_random_bio('en')
        assert isinstance(bio, str)
        assert len(bio) > 0

    def test_fetch_ai_avatar_network_error_returns_none(self):
        """При ошибке сети avatar = None (не падает)."""
        with patch('requests.get', side_effect=Exception('connection refused')):
            from services.accounts.personality import fetch_ai_avatar
            result = fetch_ai_avatar()
            assert result is None

    def test_generate_full_personality_structure(self):
        """generate_full_personality возвращает корректную структуру."""
        with patch('services.accounts.personality.fetch_ai_avatar', return_value=None):
            from services.accounts.personality import generate_full_personality
            p = generate_full_personality('ru')
            assert 'first_name' in p
            assert 'last_name' in p
            assert 'bio' in p
            assert 'avatar_bytes' in p
            assert p['avatar_bytes'] is None


# ---------------------------------------------------------------------------
# Блок 3: Lookalike и скраббинг
# ---------------------------------------------------------------------------

class TestParserExtensions:
    def test_apply_lookalike_filter_finds_intersection(self):
        from services.telegram.parser import apply_lookalike_filter
        base = [
            {'user_id': 1, 'username': 'alice'},
            {'user_id': 2, 'username': 'bob'},
            {'user_id': 3, 'username': 'carol'},
        ]
        target = [
            {'user_id': 2, 'username': 'bob'},
            {'user_id': 4, 'username': 'dave'},
        ]
        result = apply_lookalike_filter(base, target)
        assert len(result) == 1
        assert result[0]['user_id'] == 2

    def test_apply_lookalike_filter_no_intersection(self):
        from services.telegram.parser import apply_lookalike_filter
        base = [{'user_id': 1}, {'user_id': 2}]
        target = [{'user_id': 5}, {'user_id': 6}]
        assert apply_lookalike_filter(base, target) == []

    def test_apply_lookalike_filter_empty_inputs(self):
        from services.telegram.parser import apply_lookalike_filter
        assert apply_lookalike_filter([], []) == []
        assert apply_lookalike_filter([{'user_id': 1}], []) == []

    def test_scrub_removes_bots(self):
        from services.telegram.parser import scrub_user_base
        users = [
            {'user_id': 1, 'is_bot': True, 'username': 'botuser'},
            {'user_id': 2, 'is_bot': False, 'username': 'realuser'},
        ]
        result = scrub_user_base(users, no_bots=True)
        assert len(result) == 1
        assert result[0]['user_id'] == 2

    def test_scrub_min_username(self):
        from services.telegram.parser import scrub_user_base
        users = [
            {'user_id': 1, 'is_bot': False, 'username': None},
            {'user_id': 2, 'is_bot': False, 'username': 'testuser'},
        ]
        result = scrub_user_base(users, min_username=True, no_bots=True)
        assert len(result) == 1
        assert result[0]['user_id'] == 2

    def test_scrub_has_photo(self):
        from services.telegram.parser import scrub_user_base
        users = [
            {'user_id': 1, 'is_bot': False, 'has_photo': False},
            {'user_id': 2, 'is_bot': False, 'has_photo': True},
        ]
        result = scrub_user_base(users, has_photo=True)
        assert len(result) == 1
        assert result[0]['user_id'] == 2


# ---------------------------------------------------------------------------
# Блок 4: Клоакинг
# ---------------------------------------------------------------------------

class TestCloaking:
    def test_is_bot_request_detects_googlebot(self):
        """Googlebot User-Agent должен определяться как бот."""
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context(headers={'User-Agent': 'Googlebot/2.1 (+http://www.google.com/bot.html)'}):
            from web.middlewares.cloaking import is_bot_request
            assert is_bot_request() is True

    def test_is_bot_request_normal_browser(self):
        """Обычный Chrome не является ботом."""
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}):
            from web.middlewares.cloaking import is_bot_request
            assert is_bot_request() is False

    def test_is_bot_request_python_requests(self):
        """python-requests User-Agent считается ботом."""
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context(headers={'User-Agent': 'python-requests/2.31.0'}):
            from web.middlewares.cloaking import is_bot_request
            assert is_bot_request() is True

    def test_get_fake_page_default(self):
        """Без настроек возвращает страницу по умолчанию."""
        with patch('web.middlewares.cloaking._get_cloak_config', return_value={}):
            from web.middlewares.cloaking import get_fake_page
            page = get_fake_page()
            assert 'Under Construction' in page

    def test_get_fake_page_custom(self):
        """Если задана кастомная страница — возвращает её."""
        with patch('web.middlewares.cloaking._get_cloak_config', return_value={
            'cloaking_fake_page': '<html>FAKE</html>'
        }):
            from web.middlewares.cloaking import get_fake_page
            page = get_fake_page()
            assert page == '<html>FAKE</html>'


# ---------------------------------------------------------------------------
# Блок 4: Cloudflare Turnstile
# ---------------------------------------------------------------------------

class TestTurnstile:
    def test_turnstile_no_secret_key_returns_true(self):
        """Если secret key не настроен — проверка пропускается."""
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            with patch('core.config.Config.TURNSTILE_SECRET_KEY', ''):
                from web.routes.public import _verify_turnstile_token
                assert _verify_turnstile_token('any_token') is True

    def test_turnstile_api_success(self):
        """При успешном ответе Cloudflare — возвращает True."""
        from flask import Flask
        app = Flask(__name__)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'success': True}
        with app.test_request_context():
            with patch('core.config.Config.TURNSTILE_SECRET_KEY', 'secret123'):
                with patch('requests.post', return_value=mock_resp):
                    from web.routes.public import _verify_turnstile_token
                    assert _verify_turnstile_token('valid_token') is True

    def test_turnstile_api_failure(self):
        """При неуспешном ответе Cloudflare — возвращает False."""
        from flask import Flask
        app = Flask(__name__)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'success': False}
        with app.test_request_context():
            with patch('core.config.Config.TURNSTILE_SECRET_KEY', 'secret123'):
                with patch('requests.post', return_value=mock_resp):
                    from web.routes.public import _verify_turnstile_token
                    assert _verify_turnstile_token('invalid_token') is False


# ---------------------------------------------------------------------------
# Блок 5: DNS ротация
# ---------------------------------------------------------------------------

class TestDNSManager:
    def test_rotate_domain_disabled(self):
        """Если DNS ротация отключена — возвращает ошибку."""
        with patch('services.dns.manager._get_dns_config', return_value={'dns_enabled': 'false'}):
            from services.dns.manager import rotate_domain
            result = rotate_domain('example.com', '1.2.3.4')
            assert result['success'] is False
            assert 'disabled' in result['error'].lower()

    def test_rotate_cloudflare_no_token(self):
        """Без Cloudflare токена — ошибка."""
        with patch('services.dns.manager._get_dns_config', return_value={
            'dns_enabled': 'true', 'dns_provider': 'cloudflare',
            'cloudflare_token': '', 'cloudflare_zone_id': ''
        }):
            from services.dns.manager import rotate_domain
            result = rotate_domain('example.com', '1.2.3.4')
            assert result['success'] is False

    def test_list_dns_records_no_config(self):
        """Без конфигурации list_dns_records возвращает пустой список."""
        with patch('services.dns.manager._get_dns_config', return_value={}):
            from services.dns.manager import list_dns_records
            records = list_dns_records()
            assert records == []


# ---------------------------------------------------------------------------
# Блок 5: Proxy rotation_url
# ---------------------------------------------------------------------------

class TestProxyModel:
    def test_proxy_has_rotation_url_field(self):
        """Модель Proxy должна иметь поле rotation_url."""
        from models.proxy import Proxy
        proxy = Proxy(host='127.0.0.1', port=1080, type='socks5')
        assert hasattr(proxy, 'rotation_url')
        proxy.rotation_url = 'http://provider.com/rotate?token=abc'
        assert proxy.rotation_url == 'http://provider.com/rotate?token=abc'


# ---------------------------------------------------------------------------
# Блок 7: PDF/HTML Отчёты
# ---------------------------------------------------------------------------

class TestPDFReport:
    def test_generate_summary_report_returns_bytes(self):
        """generate_summary_report возвращает байты HTML."""
        from services.export.pdf_report import generate_summary_report
        stats = {
            'accounts': {'total': 10, 'active': 8, 'banned': 1, 'flood_wait': 1},
            'campaigns': {'total': 3, 'active': 2, 'done': 1},
            'proxies': {'total': 5, 'working': 4, 'dead': 1},
            'account_rows': [],
        }
        result = generate_summary_report(stats)
        assert isinstance(result, bytes)
        assert b'Ameba' in result
        assert b'<!DOCTYPE html>' in result

    def test_generate_summary_report_contains_stats(self):
        """Отчёт содержит данные о статистике."""
        from services.export.pdf_report import generate_summary_report
        stats = {
            'accounts': {'total': 42, 'active': 35, 'banned': 5, 'flood_wait': 2},
            'campaigns': {'total': 7, 'active': 3, 'done': 4},
            'proxies': {'total': 20, 'working': 18, 'dead': 2},
            'account_rows': [
                {'phone': '+380991234567', 'username': 'testuser', 'status': 'active', 'last_active': '2026-03-01'}
            ],
        }
        html = generate_summary_report(stats).decode('utf-8')
        assert '42' in html  # total accounts
        assert '+380991234567' in html  # account in rows table

    def test_collect_report_stats_returns_dict(self):
        """collect_report_stats возвращает словарь (при ошибке БД — пустой)."""
        from services.export.pdf_report import collect_report_stats
        # Если нет БД — должен вернуть пустые словари, не упасть
        with patch('core.database.SessionLocal', side_effect=Exception('no db')):
            result = collect_report_stats()
            assert isinstance(result, dict)
            assert 'accounts' in result
