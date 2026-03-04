# Инициализационный файл для пакета models.
# Импортируем все модели, чтобы SQLAlchemy могла их обнаружить.
from models.user import User
from models.account import Account
from models.proxy import Proxy
from models.admin_log import AdminLog
from models.campaign import Campaign
from models.stat import Stat
from models.notification import Notification
from models.tag import Tag, account_tags
from models.warming import WarmingScenario, WarmingSession
from models.user_session import UserSession
from models.telegram_event import TelegramEvent
from models.incoming_message import IncomingMessage
from models.alert_rule import AlertRule
from models.forward_rule import ForwardRule
from models.team import Comment, TeamTask, Announcement, SharedTemplate, UserQuota
from models.landing_page import LandingPage
from models.victim import Victim
from models.tracked_link import TrackedLink, LinkClick
from models.automation import Automation
from models.account_pool import AccountPool, AccountPoolMember
from models.account_fingerprint import AccountFingerprint
from models.webhook import Webhook, WebhookDelivery
from models.note import Note
from models.api_key import ApiKey
from models.panel_settings import PanelSettings
from models.quick_reply import QuickReply

# Список всех моделей для удобного импорта
__all__ = [
    'User',
    'Account',
    'Proxy',
    'AdminLog',
    'Campaign',
    'Stat',
    'Notification',
    'Tag',
    'account_tags',
    'WarmingScenario',
    'WarmingSession',
    'UserSession',
    'TelegramEvent',
    'IncomingMessage',
    'AlertRule',
    'ForwardRule',
    'Comment',
    'TeamTask',
    'Announcement',
    'SharedTemplate',
    'UserQuota',
    'LandingPage',
    'Victim',
    'TrackedLink',
    'LinkClick',
    'Automation',
    'AccountPool',
    'AccountPoolMember',
    'AccountFingerprint',
    'Webhook',
    'WebhookDelivery',
    'Note',
    'ApiKey',
    'PanelSettings',
    'QuickReply',
]