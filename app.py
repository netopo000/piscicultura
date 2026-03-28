from flask import Flask, request, render_template, redirect, session
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, time

app = Flask(__name__)
app.secret_key = "piscicultura_super_secreta"

# Banco SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "piscicultura.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ====================== MODELOS ======================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    senha = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200))

class TaskLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"))
    inicio = db.Column(db.DateTime)
    fim = db.Column(db.DateTime)
    user = db.relationship("User")
    task = db.relationship("Task")

class TanqueBloqueado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20))

# ====================== ROTAS ======================
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        nome = request.form.get("nome")
        senha = request.form.get("senha")
        user = User.query.filter_by(nome=nome, senha=senha).first()
        if user:
            session["user_id"] = user.id
            session["admin"] = user.is_admin  # ✅ salva admin na sessão
            if user.is_admin:
                return redirect("/admin")
            else:
                return redirect("/funcionario")
        else:
            return "Usuário ou senha inválidos"
    return render_template("login.html")

@app.route("/admin")
def admin():
    if not session.get("user_id"):
        return redirect("/")
    user = User.query.get(session["user_id"])
    if not user.is_admin:
        return redirect("/funcionario")

    logs = TaskLog.query.all()

    # formata horário para BR
    tz = pytz.timezone("America/Sao_Paulo")
    for log in logs:
        if log.inicio:
            log.inicio_br = log.inicio.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")
        else:
            log.inicio_br = None
        if log.fim:
            log.fim_br = log.fim.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")
        else:
            log.fim_br = None

    return render_template(
        "admin.html",
        tasks=Task.query.all(),
        users=User.query.all(),
        logs=logs,
        tanques=TanqueBloqueado.query.all(),
        is_admin=user.is_admin
    )

from datetime import datetime
import pytz  # para fuso horário BR

@app.route("/funcionario")
def funcionario():
    if not session.get("user_id"):
        return redirect("/")

    user_id = session.get("user_id")
    tasks = Task.query.order_by(Task.id.desc()).all()
    tanques = TanqueBloqueado.query.all()
    
    # pega logs do usuário atual
    logs = TaskLog.query.filter_by(user_id=user_id).all()

    # formata horário para BR
    tz = pytz.timezone("America/Sao_Paulo")
    for log in logs:
        if log.inicio:
            log.inicio_br = log.inicio.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")
        else:
            log.inicio_br = None
        if log.fim:
            log.fim_br = log.fim.astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")
        else:
            log.fim_br = None

    return render_template(
        "funcionario.html",
        tasks=tasks,
        tanques=tanques,
        logs=logs
    )

# Criar tarefas
@app.route("/criar_tarefa", methods=["POST"])
def criar_tarefa():
    if not session.get("admin"):
        return redirect("/")
    nome = request.form["nome"]
    db.session.add(Task(nome=nome))
    db.session.commit()
    return redirect("/admin")

# Criar usuário
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if not session.get("admin"):
        return redirect("/")
    nome = request.form["nome"]
    senha = request.form["senha"]
    db.session.add(User(nome=nome, senha=senha, is_admin=False))
    db.session.commit()
    return redirect("/admin")

# Remover usuário
@app.route("/remover_usuario/<int:id>")
def remover_usuario(id):
    if not session.get("admin"):
        return redirect("/")
    user = User.query.get(id)
    if user and not user.is_admin:
        db.session.delete(user)
        db.session.commit()
    return redirect("/admin")

# Adicionar tanque
@app.route("/add_tanque", methods=["POST"])
def add_tanque():
    if not session.get("admin"):
        return redirect("/")
    numero = request.form["numero"]
    db.session.add(TanqueBloqueado(numero=numero))
    db.session.commit()
    return redirect("/admin")

# Iniciar tarefa
@app.route("/iniciar/<int:task_id>")
def iniciar(task_id):
    user_id = session.get("user_id")
    db.session.add(TaskLog(user_id=user_id, task_id=task_id, inicio=datetime.now()))
    db.session.commit()
    return redirect("/funcionario")

# Finalizar tarefa
@app.route("/finalizar/<int:log_id>")
def finalizar(log_id):
    log = TaskLog.query.get(log_id)
    log.fim = datetime.now()
    db.session.commit()
    return redirect("/funcionario")

# Remover tarefa
@app.route("/remover_tarefa/<int:task_id>")
def remover_tarefa(task_id):
    if not session.get("admin"):
        return redirect("/")

    task = Task.query.get(task_id)
    if task:
        # Também apaga logs relacionados a essa tarefa
        TaskLog.query.filter_by(task_id=task.id).delete()
        db.session.delete(task)
        db.session.commit()

    return redirect("/admin")

@app.route("/reset_dia", methods=["POST"])
def reset_dia():
    if not session.get("admin"):
        return redirect("/")
    # Apaga tudo
    TaskLog.query.delete()
    TanqueBloqueado.query.delete()
    Task.query.delete()  # opcional, se quiser reiniciar tarefas também
    db.session.commit()
    return redirect("/admin")

# ====================== CRIAR BANCO E ADMIN ======================
# função de reset diário
def reset_diario():
    TaskLog.query.delete()
    TanqueBloqueado.query.delete()
    db.session.commit()
    print("✅ Reset diário feito às", datetime.now())

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

# TESTE: roda 30 segundos após iniciar
trigger = DateTrigger(run_date=datetime.now() + timedelta(seconds=30))
scheduler.add_job(reset_diario, trigger=trigger)

scheduler.start()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(is_admin=True).first():
            admin = User(nome="admin", senha="123", is_admin=True)
            db.session.add(admin)
            db.session.commit()
            print("Admin criado! Login: admin / Senha: 123")
    app.run(debug=True)