import random
import hashlib
import uuid
from core.database import SessionLocal
from models.antidetect_profile import AntidetectProfile
from core.logger import log

_DEVICE_POOL = [
    {"device_model": "Samsung Galaxy S23", "system_version": "Android 13", "app_version": "10.6.2", "sdk_version": 33},
    {"device_model": "Samsung Galaxy S22", "system_version": "Android 12", "app_version": "10.5.4", "sdk_version": 32},
    {"device_model": "Samsung Galaxy S21", "system_version": "Android 12", "app_version": "10.4.1", "sdk_version": 32},
    {"device_model": "Samsung Galaxy A54", "system_version": "Android 13", "app_version": "10.6.1", "sdk_version": 33},
    {"device_model": "Samsung Galaxy A34", "system_version": "Android 13", "app_version": "10.6.0", "sdk_version": 33},
    {"device_model": "Samsung Galaxy S23 Ultra", "system_version": "Android 13", "app_version": "10.6.2", "sdk_version": 33},
    {"device_model": "Xiaomi 13 Pro", "system_version": "Android 13", "app_version": "10.6.2", "sdk_version": 33},
    {"device_model": "Xiaomi 12", "system_version": "Android 12", "app_version": "10.5.3", "sdk_version": 32},
    {"device_model": "Xiaomi Redmi Note 12", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "Xiaomi Redmi Note 11", "system_version": "Android 12", "app_version": "10.5.1", "sdk_version": 32},
    {"device_model": "Xiaomi POCO X5 Pro", "system_version": "Android 13", "app_version": "10.6.0", "sdk_version": 33},
    {"device_model": "Xiaomi Redmi 12", "system_version": "Android 13", "app_version": "10.6.1", "sdk_version": 33},
    {"device_model": "iPhone 15 Pro", "system_version": "17.1.2", "app_version": "10.6.2", "sdk_version": 0},
    {"device_model": "iPhone 15", "system_version": "17.1.1", "app_version": "10.6.1", "sdk_version": 0},
    {"device_model": "iPhone 14 Pro Max", "system_version": "16.6.1", "app_version": "10.5.4", "sdk_version": 0},
    {"device_model": "iPhone 14", "system_version": "16.6", "app_version": "10.5.3", "sdk_version": 0},
    {"device_model": "iPhone 13 Pro", "system_version": "16.5", "app_version": "10.4.4", "sdk_version": 0},
    {"device_model": "iPhone 13", "system_version": "16.4.1", "app_version": "10.4.2", "sdk_version": 0},
    {"device_model": "Google Pixel 8 Pro", "system_version": "Android 14", "app_version": "10.6.2", "sdk_version": 34},
    {"device_model": "Google Pixel 8", "system_version": "Android 14", "app_version": "10.6.1", "sdk_version": 34},
    {"device_model": "Google Pixel 7 Pro", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "Google Pixel 7", "system_version": "Android 13", "app_version": "10.5.3", "sdk_version": 33},
    {"device_model": "OnePlus 11", "system_version": "Android 13", "app_version": "10.6.0", "sdk_version": 33},
    {"device_model": "OnePlus Nord 3", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "OPPO Find X6 Pro", "system_version": "Android 13", "app_version": "10.6.1", "sdk_version": 33},
    {"device_model": "OPPO Reno 10", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "Realme 11 Pro", "system_version": "Android 13", "app_version": "10.5.3", "sdk_version": 33},
    {"device_model": "Motorola Edge 40", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "Sony Xperia 1 V", "system_version": "Android 13", "app_version": "10.6.0", "sdk_version": 33},
    {"device_model": "Nokia G60", "system_version": "Android 12", "app_version": "10.4.4", "sdk_version": 32},
    {"device_model": "Samsung Galaxy Z Fold 5", "system_version": "Android 13", "app_version": "10.6.2", "sdk_version": 33},
    {"device_model": "Samsung Galaxy Z Flip 5", "system_version": "Android 13", "app_version": "10.6.1", "sdk_version": 33},
    {"device_model": "Xiaomi 13 Ultra", "system_version": "Android 13", "app_version": "10.6.2", "sdk_version": 33},
    {"device_model": "Huawei P60 Pro", "system_version": "Android 12", "app_version": "10.5.2", "sdk_version": 32},
    {"device_model": "Vivo X90 Pro", "system_version": "Android 13", "app_version": "10.5.3", "sdk_version": 33},
    {"device_model": "Asus Zenfone 10", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "Google Pixel 6 Pro", "system_version": "Android 13", "app_version": "10.5.2", "sdk_version": 33},
    {"device_model": "iPhone 12 Pro", "system_version": "15.8.1", "app_version": "10.3.2", "sdk_version": 0},
    {"device_model": "iPhone 12", "system_version": "15.8", "app_version": "10.3.1", "sdk_version": 0},
    {"device_model": "Samsung Galaxy A53", "system_version": "Android 12", "app_version": "10.4.3", "sdk_version": 32},
    {"device_model": "Xiaomi Redmi 10C", "system_version": "Android 12", "app_version": "10.4.2", "sdk_version": 32},
    {"device_model": "Motorola Moto G73", "system_version": "Android 13", "app_version": "10.5.0", "sdk_version": 33},
    {"device_model": "Samsung Galaxy M54", "system_version": "Android 13", "app_version": "10.5.4", "sdk_version": 33},
    {"device_model": "Xiaomi POCO M5", "system_version": "Android 12", "app_version": "10.4.4", "sdk_version": 32},
    {"device_model": "Realme C55", "system_version": "Android 13", "app_version": "10.5.1", "sdk_version": 33},
    {"device_model": "OnePlus 10T", "system_version": "Android 13", "app_version": "10.5.2", "sdk_version": 33},
    {"device_model": "Sony Xperia 10 V", "system_version": "Android 13", "app_version": "10.5.3", "sdk_version": 33},
    {"device_model": "Google Pixel 7a", "system_version": "Android 14", "app_version": "10.6.0", "sdk_version": 34},
    {"device_model": "Samsung Galaxy A14", "system_version": "Android 13", "app_version": "10.5.2", "sdk_version": 33},
    {"device_model": "Xiaomi POCO F5", "system_version": "Android 13", "app_version": "10.5.3", "sdk_version": 33},
]

LANG_CODES = ['uk', 'ru', 'en', 'de', 'fr', 'pl', 'es', 'it', 'tr', 'ar']


def generate_random_profile(name=None, is_template=False):
    """Generate a random realistic antidetect profile from device pool."""
    device = random.choice(_DEVICE_POOL)
    lang = random.choice(LANG_CODES)
    device_hash = hashlib.sha256(
        f"{device['device_model']}{device['system_version']}{uuid.uuid4()}".encode()
    ).hexdigest()[:64]
    if not name:
        name = f"{device['device_model']} ({device['system_version']})"
    return AntidetectProfile(
        name=name,
        device_model=device['device_model'],
        system_version=device['system_version'],
        app_version=device['app_version'],
        sdk_version=device['sdk_version'],
        lang_code=lang,
        system_lang_code=lang,
        device_hash=device_hash,
        is_template=is_template,
    )


def assign_profile_to_account(account_id, profile_id=None):
    """Assign an antidetect profile to an account (or generate a new one)."""
    db = SessionLocal()
    try:
        if profile_id:
            profile = db.query(AntidetectProfile).filter_by(id=profile_id).first()
            if not profile:
                return None
        else:
            profile = generate_random_profile(name=f"Profile for {account_id}")
            db.add(profile)
            db.flush()
        # Unassign any previous profile for this account
        db.query(AntidetectProfile).filter(
            AntidetectProfile.account_id == account_id,
            AntidetectProfile.id != profile.id
        ).update({'account_id': None})
        profile.account_id = account_id
        db.commit()
        return profile.id
    except Exception as e:
        db.rollback()
        log.error(f"assign_profile_to_account error: {e}")
        return None
    finally:
        db.close()


def get_telethon_device_params(account_id):
    """Return dict with TelegramClient device parameters for the account."""
    db = SessionLocal()
    try:
        profile = db.query(AntidetectProfile).filter_by(account_id=account_id).first()
        if not profile:
            return {}
        return {
            'device_model': profile.device_model or '',
            'system_version': profile.system_version or '',
            'app_version': profile.app_version or '',
            'lang_code': profile.lang_code or 'uk',
            'system_lang_code': profile.system_lang_code or 'uk',
        }
    finally:
        db.close()


def bulk_generate_profiles(count, is_template=True):
    """Bulk generate antidetect profiles."""
    db = SessionLocal()
    try:
        profiles = []
        for i in range(count):
            p = generate_random_profile(name=f"Template #{i+1}", is_template=is_template)
            db.add(p)
            profiles.append(p)
        db.commit()
        return len(profiles)
    except Exception as e:
        db.rollback()
        log.error(f"bulk_generate_profiles error: {e}")
        return 0
    finally:
        db.close()


def auto_assign_profiles():
    """Auto-assign profiles to all accounts that don't have one."""
    db = SessionLocal()
    try:
        from models.account import Account
        accounts_without_profile = db.query(Account).filter(
            ~Account.id.in_(
                db.query(AntidetectProfile.account_id).filter(
                    AntidetectProfile.account_id.isnot(None)
                )
            )
        ).all()
        assigned = 0
        for account in accounts_without_profile:
            profile = generate_random_profile(name=f"Profile for {account.phone}")
            profile.account_id = account.id
            db.add(profile)
            assigned += 1
        db.commit()
        return assigned
    except Exception as e:
        db.rollback()
        log.error(f"auto_assign_profiles error: {e}")
        return 0
    finally:
        db.close()
