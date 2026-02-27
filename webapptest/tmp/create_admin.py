from web.app import create_app
from models.user import User
from web.extensions import db

app = create_app()
with app.app_context():
    admin = db.session.query(User).filter_by(username='admin').first()
    if admin:
        db.session.delete(admin)
        db.session.commit()
        print("Старый администратор удалён")

    new_admin = User(username='admin')
    new_admin.set_password('0932324169a')
    new_admin.role = 'superadmin'
    db.session.add(new_admin)
    db.session.commit()
    print("Новый администратор создан с паролем: ваш_пароль")