import os
import zipfile
import datetime
from pathlib import Path
from core.config import Config
from core.logger import log

def create_backup():
    """
    Создаёт ZIP-архив с данными (sessions, logs, stats.json) и сохраняет в папку backups.
    Возвращает путь к созданному файлу.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}.zip"
    backup_path = Path(Config.BACKUPS_DIR) / backup_filename

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Добавляем папку sessions
        sessions_dir = Path(Config.SESSIONS_DIR)
        if sessions_dir.exists():
            for file in sessions_dir.glob('*'):
                zf.write(file, arcname=f"sessions/{file.name}")

        # Добавляем логи (только app.log и admin_actions.json)
        logs_dir = Path(Config.LOGS_DIR)
        if logs_dir.exists():
            for log_file in ['app.log', 'admin_actions.json', 'errors.log']:
                f = logs_dir / log_file
                if f.exists():
                    zf.write(f, arcname=f"logs/{log_file}")

    log.info(f"Backup created: {backup_path}")
    return backup_path

def list_backups():
    """
    Возвращает список доступных бэкапов в папке backups.
    Каждый элемент содержит имя, размер и дату создания.
    """
    backups_dir = Path(Config.BACKUPS_DIR)
    backups = []
    for file in backups_dir.glob("backup_*.zip"):
        stat = file.stat()
        backups.append({
            'name': file.name,
            'size': stat.st_size,
            'created': datetime.datetime.fromtimestamp(stat.st_ctime).isoformat()
        })
    return sorted(backups, key=lambda x: x['created'], reverse=True)

def restore_backup(filename):
    """
    Восстанавливает данные из указанного бэкапа.
    ВНИМАНИЕ: перезаписывает текущие файлы!
    """
    backup_path = Path(Config.BACKUPS_DIR) / filename
    if not backup_path.exists():
        log.error(f"Backup file {filename} not found")
        return False

    # Распаковываем, перезаписывая существующие файлы
    with zipfile.ZipFile(backup_path, 'r') as zf:
        zf.extractall(Config.BASE_DIR)

    log.info(f"Restored from backup: {filename}")
    return True

def delete_backup(filename):
    """
    Удаляет указанный файл бэкапа.
    """
    backup_path = Path(Config.BACKUPS_DIR) / filename
    if backup_path.exists():
        backup_path.unlink()
        log.info(f"Backup deleted: {filename}")
        return True
    return False