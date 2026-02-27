from web.app import create_app
from models.user import User
from web.extensions import db

app = create_app()
with app.app_context():
    confirm = input(
        "WARNING: This will DELETE ALL users and create a new admin. "
        "Type 'yes' to continue: "
    )
    if confirm.strip().lower() != 'yes':
        print("Aborted.")
        exit(1)

    # Удалить всех пользователей
    db.session.query(User).delete()
    db.session.commit()

    # Создать одного нового
    new_admin = User(username='admin')
    new_admin.set_password('0932324169a')
    new_admin.role = 'superadmin'
    db.session.add(new_admin)
    db.session.commit()

exit()