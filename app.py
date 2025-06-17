import sqlite3
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, make_response, session, jsonify, send_file
import io
from weasyprint import HTML
import json
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import threading
from functools import wraps
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import xlsxwriter
from flask import Response

app = Flask(__name__)

DB_PATH = "banco/database.db"

app.secret_key = "sua_chave_secreta"  # Defina uma chave secreta para sessão

db_lock = threading.Lock()

def get_sqlite_conn():
    """
    Retorna uma conexão com o banco SQLite database.db.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Exemplo de configuração para PostgreSQL
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "nome_do_banco"
PG_USER = "usuario"
PG_PASSWORD = "senha"

def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )

def login_required(perfis=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "usuario_id" not in session or "perfil" not in session:
                return redirect(url_for("home"))
            if perfis and session["perfil"] not in perfis:
                # Se for requisição AJAX, retorna JSON, senão, retorna HTML com popup JS
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"acesso_negado": True}), 403
                # Renderiza a página atual com popup de acesso negado
                return render_template("acesso_negado.html")
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route("/")
def home():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = []
    for row in cur.fetchall():
        logo_url = row["logo"] if row["logo"] else "/static/logos/default.png"
        if not logo_url.startswith("/"):
            logo_url = "/static/logos/" + logo_url
        cooperativas.append({
            "id": row["id"],
            "nome_fantasia": row["nome_fantasia"],
            "logo_url": logo_url,
            "categoria": row["categoria"] if "categoria" in row.keys() else ""
        })
    conn.close()
    return render_template("index.html", cooperativas=cooperativas)

@app.route("/login", methods=["POST"])
def login():
    usuario = request.form.get("usuario")
    senha = request.form.get("senha")
    conn = get_sqlite_conn()
    cur = conn.cursor()
    # Certifique-se de que o campo 'login' e 'senha' existem e estão corretos no banco
    cur.execute("SELECT * FROM usuario WHERE login = ? AND senha = ?", (usuario, senha))
    user = cur.fetchone()
    conn.close()
    if user:
        session["usuario_id"] = user["id"]
        # Garante que o perfil seja string minúscula e sem espaços
        perfil = str(user["perfil"]).strip().lower()
        session["perfil"] = perfil
        # Redireciona para menu para todos os perfis
        return redirect(url_for("menu"))
    else:
        return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/menu")
@login_required(perfis=["administrador", "gerente", "preposto", "auditor"])
def menu():
    return render_template("menu.html")

@app.route("/cadastro")
@login_required(perfis=["administrador", "gerente", "preposto"])
def cadastro():
    return render_template("cadastro.html")

@app.route("/cadastro_cooperativa", methods=["GET", "POST"])
def cadastro_cooperativa():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if request.method == "POST":
        razao_social = request.form.get("razao")
        nome_fantasia = request.form.get("fantasia")
        cnpj = request.form.get("cnpj")
        endereco = request.form.get("endereco")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        logo = request.files.get("logo")
        logo_filename = ""
        if logo and logo.filename:
            logo_filename = logo.filename
            logo.save(f"static/logos/{logo_filename}")
        cur.execute(
            "INSERT INTO cooperativa (razao_social, nome_fantasia, cnpj, endereco, telefone, email, logo) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (razao_social, nome_fantasia, cnpj, endereco, telefone, email, logo_filename)
        )
        conn.commit()
        # Redireciona para GET para atualizar a listagem
        return redirect(url_for("cadastro_cooperativa"))
    cur.execute("SELECT * FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = []
    for row in cur.fetchall():
        logo_url = row["logo"] if row["logo"] else "/static/logos/default.png"
        if not logo_url.startswith("/"):
            logo_url = "/static/logos/" + logo_url
        # Mostra a categoria completa (campo categoria da tabela cooperativa)
        cooperativas.append({
            "id": row["id"],
            "nome_fantasia": row["nome_fantasia"],
            "logo_url": logo_url,
            "categoria": row["categoria"]
        })
    conn.close()
    return render_template("cadastro_cooperativa.html", cooperativas=cooperativas)

@app.route("/cadastro_profissional", methods=["GET"])
def cadastro_profissional():
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = []
    for row in cur.fetchall():
        logo_url = row["logo"] if row["logo"] else "/static/logos/default.png"
        if not logo_url.startswith("/"):
            logo_url = "/static/logos/" + logo_url
        cooperativas.append({
            "id": row["id"],
            "nome_fantasia": row["nome_fantasia"],
            "logo_url": logo_url,
            "categoria": row["categoria"] if "categoria" in row.keys() else ""
        })
    conn.close()
    return render_template("cadastro_profissional.html", cooperativas=cooperativas)

@app.route("/lista_profissional/<int:cooperativa_id>", methods=["GET"])
def lista_profissional(cooperativa_id):
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, c.nome as categoria
        FROM profissional p
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        WHERE p.cooperativa_id = ?
        ORDER BY p.nome_completo ASC
    """, (cooperativa_id,))
    profissionais = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("lista_profissional.html", profissionais=profissionais)

@app.route("/cadastro_usuario", methods=["GET", "POST"])
def cadastro_usuario():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Buscar cooperativas para o select
    cur.execute("SELECT id, nome_fantasia, categoria FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = cur.fetchall()
    if request.method == "POST":
        nome = request.form["nome"]
        login = request.form["login"]
        senha = request.form["senha"]
        perfil = request.form["perfil"]
        cooperativas_ids = request.form.getlist("cooperativas")
        cooperativas_str = ",".join(cooperativas_ids)
        cur.execute(
            "INSERT INTO usuario (nome, login, senha, perfil, cooperativas) VALUES (?, ?, ?, ?, ?)",
            (nome, login, senha, perfil, cooperativas_str)
        )
        conn.commit()
        return redirect(url_for("cadastro_usuario"))
    # Garante que a coluna cooperativas exista (para múltiplas cooperativas)
    cur.execute("PRAGMA table_info(usuario)")
    columns = [col[1] for col in cur.fetchall()]
    if "cooperativas" not in columns:
        cur.execute("ALTER TABLE usuario ADD COLUMN cooperativas TEXT")
        conn.commit()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL,
            cooperativas TEXT,
            ativo INTEGER DEFAULT 1
        )
    """)
    # Verifica se o usuário administrador já existe
    cur.execute("SELECT * FROM usuario WHERE login = ?", ("admin",))
    if not cur.fetchone():
        # Cria o usuário administrador com login 'admin' e senha 'admin'
        cur.execute("""
            INSERT INTO usuario (nome, login, senha, perfil, ativo)
            VALUES (?, ?, ?, ?, ?)
        """, ("Administrador", "admin", "admin", "administrador", 1))
        conn.commit()
    cur.execute("SELECT * FROM usuario ORDER BY nome ASC")
    usuarios = cur.fetchall()
    conn.close()
    return render_template("cadastro_usuario.html", usuarios=usuarios, cooperativas=cooperativas)

@app.route("/novo_usuario", methods=["GET", "POST"])
def novo_usuario():
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nome_fantasia, categoria FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = cur.fetchall()
    erro = None
    if request.method == "POST":
        nome = request.form["nome"]
        login = request.form["login"]
        senha = request.form["senha"]
        perfil = request.form["perfil"]
        cooperativas_ids = request.form.getlist("cooperativas")
        cooperativas_str = ",".join(cooperativas_ids)
        try:
            cur.execute(
                "INSERT INTO usuario (nome, login, senha, perfil, cooperativas) VALUES (?, ?, ?, ?, ?)",
                (nome, login, senha, perfil, cooperativas_str)
            )
            conn.commit()
            return redirect(url_for("cadastro_usuario"))
        except Exception as e:
            erro = f"Erro ao cadastrar usuário: {e}"
    cur.close()
    conn.close()
    return render_template("novo_usuario.html", erro=erro, cooperativas=cooperativas)

@app.route("/nova_cooperativa", methods=["GET", "POST"])
def nova_cooperativa():
    erro = None
    if request.method == "POST":
        razao_social = request.form.get("razao")
        nome_fantasia = request.form.get("fantasia")
        cnpj = request.form.get("cnpj")
        endereco = request.form.get("endereco")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        categoria = request.form.get("categoria")
        data_inicio = request.form.get("data_inicio")
        data_fim = request.form.get("data_fim")
        logo_file = request.files.get("logo")
        logo_filename = ""
        # Validação dos campos obrigatórios
        if not razao_social or not nome_fantasia or not categoria or not logo_file or not logo_file.filename or not data_inicio or not data_fim:
            erro = "Preencha todos os campos obrigatórios: Razão Social, Nome Fantasia, Categoria Profissional, Logo e Período de Faturamento."
            return render_template("nova_cooperativa.html", erro=erro)
        try:
            dia_inicio = int(data_inicio)
            dia_fim = int(data_fim)
            if dia_inicio < 1 or dia_inicio > 31 or dia_fim < 1 or dia_fim > 31:
                erro = "Os dias do período de faturamento devem estar entre 1 e 31."
                return render_template("nova_cooperativa.html", erro=erro)
        except Exception:
            erro = "Informe dias válidos para o período de faturamento."
            return render_template("nova_cooperativa.html", erro=erro)
        if logo_file and logo_file.filename:
            filename = secure_filename(logo_file.filename)
            logos_dir = os.path.join("static", "logos")
            os.makedirs(logos_dir, exist_ok=True)
            file_path = os.path.join(logos_dir, filename)
            logo_file.save(file_path)
            logo_filename = filename

        try:
            with db_lock:
                conn = get_sqlite_conn()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO cooperativa (razao_social, nome_fantasia, cnpj, endereco, telefone, email, categoria, logo, data_inicio, data_fim) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (razao_social, nome_fantasia, cnpj, endereco, telefone, email, categoria, logo_filename, data_inicio, data_fim)
                )
                conn.commit()
                conn.close()
                return redirect(url_for("cadastro_cooperativa"))
        except sqlite3.OperationalError as e:
            erro = "O banco de dados está ocupado. Tente novamente em instantes."
        except sqlite3.IntegrityError as e:
            erro = "Erro de integridade no banco de dados: " + str(e)
    return render_template("nova_cooperativa.html", erro=erro)

def contar_justificativas_periodo(profissional_id, data_ocorrencia, data_inicio_fat, data_fim_fat):
    """
    Conta quantas justificativas o profissional já possui no mesmo período de faturamento da data_ocorrencia.
    """
    conn = get_sqlite_conn()
    cur = conn.cursor()
    # Datas no formato datetime
    from datetime import datetime

    # Converte datas para datetime
    if isinstance(data_ocorrencia, str):
        if "/" in data_ocorrencia:
            data_ocorrencia_dt = datetime.strptime(data_ocorrencia, "%d/%m/%Y")
        else:
            data_ocorrencia_dt = datetime.strptime(data_ocorrencia, "%Y-%m-%d")
    else:
        data_ocorrencia_dt = data_ocorrencia

    # Calcula o início e fim do período de faturamento
    def periodo_faturamento(dt, dia_inicio, dia_fim):
        ano = dt.year
        mes = dt.month
        dia = dt.day
        if dia < dia_inicio:
            if mes == 1:
                mes_ini = 12
                ano_ini = ano - 1
            else:
                mes_ini = mes - 1
                ano_ini = ano
            data_inicio = datetime(ano_ini, mes_ini, dia_inicio)
            if dia_fim < dia_inicio:
                if mes == 1:
                    mes_fim = 1
                    ano_fim = ano
                else:
                    mes_fim = mes
                    ano_fim = ano
                data_fim = datetime(ano, mes, dia_fim)
            else:
                data_fim = datetime(ano, mes, dia_fim)
        else:
            data_inicio = datetime(ano, mes, dia_inicio)
            if dia_fim < dia_inicio:
                if mes == 12:
                    mes_fim = 1
                    ano_fim = ano + 1
                else:
                    mes_fim = mes + 1
                    ano_fim = ano
                data_fim = datetime(ano_fim, mes_fim, dia_fim)
            else:
                data_fim = datetime(ano, mes, dia_fim)
        return (data_inicio, data_fim)

    periodo_ini, periodo_fim = periodo_faturamento(data_ocorrencia_dt, data_inicio_fat, data_fim_fat)

    # Busca todas as justificativas do profissional no período
    cur.execute("""
        SELECT COUNT(*) as total
        FROM justificativa
        WHERE profissional_id = ?
          AND (
                (strftime('%Y-%m-%d', substr(data_ocorrencia,7,4)||'-'||substr(data_ocorrencia,4,2)||'-'||substr(data_ocorrencia,1,2)) >= ?)
            AND (strftime('%Y-%m-%d', substr(data_ocorrencia,7,4)||'-'||substr(data_ocorrencia,4,2)||'-'||substr(data_ocorrencia,1,2)) <= ?)
          )
    """, (
        profissional_id,
        periodo_ini.strftime("%Y-%m-%d"),
        periodo_fim.strftime("%Y-%m-%d")
    ))
    row = cur.fetchone()
    conn.close()
    return row["total"] if row else 0

@app.route("/formulario_justificativa/<int:cooperativa_id>", methods=["GET", "POST"])
def formulario_justificativa(cooperativa_id):
    from datetime import datetime, timedelta
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cooperativa WHERE id = ?", (cooperativa_id,))
    coop = cur.fetchone()
    if not coop:
        conn.close()
        return "Cooperativa não encontrada", 404
    logo_url = coop["logo"] if coop["logo"] else "/static/logos/default.png"
    if not logo_url.startswith("/"):
        logo_url = "/static/logos/" + logo_url
    nome_fantasia = coop["nome_fantasia"]
    categoria = coop["categoria"]

    cur.execute("""
        SELECT p.*, c.nome as categoria_nome
        FROM profissional p
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        WHERE p.cooperativa_id = ?
        ORDER BY p.nome_completo ASC
    """, (cooperativa_id,))
    profissionais = cur.fetchall()
    profissionais_categorias = {str(p["id"]): p["categoria_nome"] for p in profissionais}
    datahora_preenchimento = datetime.now().strftime("%d/%m/%Y %H:%M")
    mensagem = None

    if request.method == "POST":
        data_ocorrencia = request.form.get("data_ocorrencia")
        inicio_plantao = request.form.get("inicio_plantao")
        fim_plantao = request.form.get("fim_plantao")
        profissional_id = request.form.get("profissional")
        justificativa = request.form.get("justificativa")
        categoria_profissional = request.form.get("categoria_profissional")
        ocorrencia_file = request.files.get("ocorrencia")
        ocorrencia_arquivo = None
        if ocorrencia_file and ocorrencia_file.filename:
            filename = secure_filename(ocorrencia_file.filename)
            ocorrencias_dir = os.path.join("static", "ocorrencias")
            os.makedirs(ocorrencias_dir, exist_ok=True)
            file_path = os.path.join(ocorrencias_dir, filename)
            ocorrencia_file.save(file_path)
            ocorrencia_arquivo = filename

        # Converter data_ocorrencia de yyyy-mm-dd para dd/mm/aaaa
        if data_ocorrencia and "-" in data_ocorrencia:
            partes = data_ocorrencia.split("-")
            if len(partes) == 3:
                data_ocorrencia_fmt = f"{partes[2]}/{partes[1]}/{partes[0]}"
            else:
                data_ocorrencia_fmt = data_ocorrencia
        else:
            data_ocorrencia_fmt = data_ocorrencia

        # --- AUTORIZAÇÃO AUTOMÁTICA E LIMITE DE 3 JUSTIFICATIVAS POR PERÍODO ---
        autorizacao = None
        try:
            # Função para calcular o período de faturamento
            def periodo_faturamento(dt, dia_inicio, dia_fim):
                ano = dt.year
                mes = dt.month
                dia = dt.day
                if dia < dia_inicio:
                    if mes == 1:
                        mes_ini = 12
                        ano_ini = ano - 1
                    else:
                        mes_ini = mes - 1
                        ano_ini = ano
                    data_inicio = datetime(ano_ini, mes_ini, dia_inicio)
                    if dia_fim < dia_inicio:
                        if mes == 1:
                            mes_fim = 1
                            ano_fim = ano
                        else:
                            mes_fim = mes
                            ano_fim = ano
                        data_fim = datetime(ano, mes, dia_fim)
                    else:
                        data_fim = datetime(ano, mes, dia_fim)
                else:
                    data_inicio = datetime(ano, mes, dia_inicio)
                    if dia_fim < dia_inicio:
                        if mes == 12:
                            mes_fim = 1
                            ano_fim = ano + 1
                        else:
                            mes_fim = mes + 1
                            ano_fim = ano
                        data_fim = datetime(ano_fim, mes_fim, dia_fim)
                    else:
                        data_fim = datetime(ano, mes, dia_fim)
                return (data_inicio, data_fim)

            # Parse datas
            preenchimento_str = datahora_preenchimento.split()[0]
            if "/" in preenchimento_str:
                preenchimento = datetime.strptime(preenchimento_str, "%d/%m/%Y")
            else:
                preenchimento = datetime.strptime(preenchimento_str, "%Y-%m-%d")
            data_ocorrencia_str = data_ocorrencia_fmt
            if "/" in data_ocorrencia_str:
                data_ocorrencia_dt = datetime.strptime(data_ocorrencia_str, "%d/%m/%Y")
            else:
                data_ocorrencia_dt = datetime.strptime(data_ocorrencia_str, "%Y-%m-%d")

            # Período de faturamento
            data_inicio_fat = int(coop["data_inicio"]) if "data_inicio" in coop.keys() and coop["data_inicio"] else 1
            data_fim_fat = int(coop["data_fim"]) if "data_fim" in coop.keys() and coop["data_fim"] else 31

            # Conta justificativas no período
            total_justificativas = contar_justificativas_periodo(
                profissional_id,
                data_ocorrencia_fmt,
                data_inicio_fat,
                data_fim_fat
            )

            # Se já houver 3 ou mais, exige aprovação do gerente (autorizacao=None)
            if total_justificativas >= 3:
                autorizacao = None  # Necessita aprovação do gerente
            else:
                # Regra automática de autorização
                fat_ini_oc, fat_fim_oc = periodo_faturamento(data_ocorrencia_dt, data_inicio_fat, data_fim_fat)
                fat_ini_pr, fat_fim_pr = periodo_faturamento(preenchimento, data_inicio_fat, data_fim_fat)

                def add_business_days(start_date, days):
                    current = start_date
                    added = 0
                    while added < days:
                        current += timedelta(days=1)
                        if current.weekday() < 5:
                            added += 1
                    return current

                if fat_ini_oc == fat_ini_pr and fat_fim_oc == fat_fim_pr:
                    limite = add_business_days(data_ocorrencia_dt, 3)
                    if preenchimento <= limite:
                        autorizacao = 1
                else:
                    limite = add_business_days(data_ocorrencia_dt, 1)
                    if preenchimento <= limite:
                        autorizacao = 1
        except Exception:
            autorizacao = None

        try:
            cur.execute("""
                INSERT INTO justificativa (
                    cooperativa_id, profissional_id, categoria_profissional,
                    datahora_preenchimento, data_ocorrencia, inicio_plantao,
                    fim_plantao, justificativa, ocorrencia_arquivo, autorizacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cooperativa_id,
                profissional_id,
                categoria_profissional,
                datahora_preenchimento,
                data_ocorrencia_fmt,
                inicio_plantao,
                fim_plantao,
                justificativa,
                ocorrencia_arquivo,
                autorizacao
            ))
            conn.commit()
            # Buscar e-mail do profissional
            cur.execute("SELECT email FROM profissional WHERE id = ?", (profissional_id,))
            prof = cur.fetchone()
            email_prof = prof["email"] if prof and "email" in prof.keys() else ""
            # Tenta enviar o e-mail
            justificativa_id = cur.lastrowid
            email_enviado = enviar_email_justificativa_para_profissional(justificativa_id)
            if email_enviado:
                mensagem = f"Justificativa salva com sucesso! Uma cópia foi enviada para o e-mail: {email_prof}"
            else:
                mensagem = f"Justificativa salva com sucesso! (Não foi possível enviar a cópia para o e-mail: {email_prof})"
        except Exception as e:
            mensagem = f"Erro ao salvar justificativa: {e}"
    conn.close()
    return render_template(
        "formulario_justificativa.html",
        logo_url=logo_url,
        nome_fantasia=nome_fantasia,
        categoria_profissional=categoria,
        profissionais=profissionais,
        profissionais_categorias_json=json.dumps(profissionais_categorias),
        datahora_preenchimento=datahora_preenchimento,
        mensagem=mensagem
    )

def enviar_email_justificativa_para_profissional(justificativa_id):
    """
    Envia a justificativa por e-mail para o profissional usando a API do MailerSend.
    """
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT j.*, p.nome_completo, p.email, p.matricula, c.nome as categoria_profissional, coop.nome_fantasia, coop.logo as logo_url
        FROM justificativa j
        LEFT JOIN profissional p ON j.profissional_id = p.id
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        LEFT JOIN cooperativa coop ON p.cooperativa_id = coop.id
        WHERE j.id = ?
    """, (justificativa_id,))
    justificativa = cur.fetchone()
    conn.close()
    if not justificativa or not justificativa["email"]:
        print("E-mail do profissional não encontrado.")
        return False

    destinatario = justificativa["email"]
    assunto = "Cópia da Justificativa de Plantão"

    html_corpo = render_template(
        "visualizar_justificativa.html",
        justificativa=justificativa,
        nome_fantasia=justificativa["nome_fantasia"] if "nome_fantasia" in justificativa.keys() else "",
        logo_url=justificativa["logo_url"] if "logo_url" in justificativa.keys() else "/static/logos/default.png"
    )

    # MailerSend API integration
    MAILERSEND_API_TOKEN = "mlsn.4e02bec439680bae3ff34edec7ba385b8daae7e67211727a7d026c26bcd1656d"
    MAILERSEND_API_URL = "https://api.mailersend.com/v1/email"
    MAILERSEND_FROM_EMAIL = "justificativacooperativa@outlook.com.br"
    MAILERSEND_FROM_NAME = "Justificativa Cooperativa"

    payload = {
        "from": {
            "email": MAILERSEND_FROM_EMAIL,
            "name": MAILERSEND_FROM_NAME
        },
        "to": [
            {
                "email": destinatario,
                "name": justificativa["nome_completo"]
            }
        ],
        "subject": assunto,
        "html": html_corpo
    }

    headers = {
        "Authorization": f"Bearer {MAILERSEND_API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(MAILERSEND_API_URL, headers=headers, json=payload, timeout=20)
        print(f"MailerSend response status: {response.status_code}")
        print(f"MailerSend response body: {response.text}")
        if response.status_code in (200, 202):
            print(f"E-mail enviado para {destinatario} via MailerSend API")
            return True
        else:
            print(f"Erro ao enviar e-mail via MailerSend: {response.text}")
            return False
    except Exception as e:
        print(f"Erro ao enviar e-mail via MailerSend: {e}")
        return False

@app.route("/ver_banco_pg")
def ver_banco_pg():
    conn = get_pg_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM cooperativa")
    cooperativas = cur.fetchall()
    cur.execute("SELECT * FROM usuario")
    usuarios = cur.fetchall()
    cur.execute("SELECT * FROM profissional")
    profissionais = cur.fetchall()
    conn.close()
    return render_template(
        "ver_banco.html",
        cooperativas=cooperativas,
        usuarios=usuarios,
        profissionais=profissionais
    )

def salvar_logo_file(logo_file):
    if logo_file and logo_file.filename:
        filename = secure_filename(logo_file.filename)
        logos_dir = os.path.join("static", "logos")
        os.makedirs(logos_dir, exist_ok=True)
        file_path = os.path.join(logos_dir, filename)
        logo_file.save(file_path)
        return filename
    return ""

@app.route("/novo_profissional", methods=["GET", "POST"])
def novo_profissional():
    erro = None
    conn = get_sqlite_conn()
    cur = conn.cursor()
    # Buscar todas as cooperativas (nome fantasia e id)
    cur.execute("SELECT id, nome_fantasia FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = cur.fetchall()
    cooperativa_id = request.args.get("cooperativa_id") or request.form.get("cooperativa_id")
    categoria_id = request.args.get("categoria_id") or request.form.get("categoria_id")
    nome_fantasia_selecionado = None
    if cooperativa_id:
        for coop in cooperativas:
            if str(coop["id"]) == str(cooperativa_id):
                nome_fantasia_selecionado = coop["nome_fantasia"]
                break

    # Buscar todas as categorias distintas das cooperativas
    cur.execute("SELECT DISTINCT categoria FROM cooperativa WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria ASC")
    todas_categorias = [row["categoria"] for row in cur.fetchall()]

    if request.method == "POST":
        nome = request.form.get("nome")
        matricula = request.form.get("matricula")
        celular = request.form.get("celular")
        email = request.form.get("email")
        cooperativa_id_real = cooperativa_id
        categoria_nome = categoria_id
        # Buscar o id da categoria_profissional pelo nome, se não existir, criar
        cur.execute("SELECT id FROM categoria_profissional WHERE nome = ?", (categoria_nome,))
        cat_row = cur.fetchone()
        if not cat_row:
            cur.execute("INSERT INTO categoria_profissional (nome) VALUES (?)", (categoria_nome,))
            conn.commit()
            cur.execute("SELECT id FROM categoria_profissional WHERE nome = ?", (categoria_nome,))
            cat_row = cur.fetchone()
        categoria_id_real = cat_row["id"] if cat_row else None

        # Verifica duplicidade de matrícula
        cur.execute("SELECT id FROM profissional WHERE matricula = ?", (matricula,))
        if cur.fetchone():
            erro = "Já existe um profissional cadastrado com esta matrícula."
        elif not categoria_id_real:
            erro = "Selecione uma categoria profissional válida."
        else:
            try:
                cur.execute(
                    "INSERT INTO profissional (nome_completo, matricula, celular, email, cooperativa_id, categoria_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (nome, matricula, celular, email, cooperativa_id_real, categoria_id_real)
                )
                conn.commit()
            except Exception as e:
                erro = f"Ocorreu um erro ao cadastrar o profissional: {e}"
            if not erro:
                cur.close()
                conn.close()
                return redirect(url_for("cadastro_profissional"))
    cur.close()
    conn.close()
    return render_template(
        "novo_profissional.html",
        erro=erro,
        cooperativas=cooperativas,
        todas_categorias=todas_categorias,
        cooperativa_id=cooperativa_id,
        categoria_id=categoria_id,
        nome_fantasia_selecionado=nome_fantasia_selecionado
    )

@app.route("/editar_profissional/<int:profissional_id>", methods=["GET", "POST"])
def editar_profissional(profissional_id):
    erro = None
    conn = get_sqlite_conn()
    cur = conn.cursor()
    if request.method == "POST":
        nome = request.form.get("nome")
        matricula = request.form.get("matricula")
        celular = request.form.get("celular")
        email = request.form.get("email")
        # Buscar id da cooperativa e categoria pelo nome
        cooperativa_nome = request.form.get("cooperativa_id")
        categoria_nome = request.form.get("categoria_id")
        cur.execute("SELECT id FROM cooperativa WHERE nome_fantasia = ?", (cooperativa_nome,))
        coop_row = cur.fetchone()
        cooperativa_id_real = coop_row["id"] if coop_row else None
        cur.execute("SELECT id FROM categoria_profissional WHERE nome = ?", (categoria_nome,))
        cat_row = cur.fetchone()
        categoria_id_real = cat_row["id"] if cat_row else None
        cur.execute(
            "UPDATE profissional SET nome_completo=?, matricula=?, celular=?, email=?, cooperativa_id=?, categoria_id=? WHERE id=?",
            (nome, matricula, celular, email, cooperativa_id_real, categoria_id_real, profissional_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("lista_profissional", cooperativa_id=cooperativa_id_real))
    cur.execute("""
        SELECT p.*, c.nome as categoria_nome, coop.nome_fantasia as cooperativa_nome
        FROM profissional p
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        LEFT JOIN cooperativa coop ON p.cooperativa_id = coop.id
        WHERE p.id = ?
    """, (profissional_id,))
    profissional = cur.fetchone()
    conn.close()
    if not profissional:
        return "Profissional não encontrado", 404
    return render_template("editar_profissional.html", profissional=profissional, erro=erro)

@app.route("/excluir_profissional/<int:profissional_id>", methods=["POST"])
def excluir_profissional(profissional_id):
    conn = get_sqlite_conn()
    cur = conn.cursor()
    # Descobre a cooperativa antes de excluir para redirecionar corretamente
    cur.execute("SELECT cooperativa_id FROM profissional WHERE id = ?", (profissional_id,))
    row = cur.fetchone()
    cooperativa_id = row["cooperativa_id"] if row else None
    cur.execute("DELETE FROM profissional WHERE id = ?", (profissional_id,))
    conn.commit()
    conn.close()
    if cooperativa_id:
        return redirect(url_for("lista_profissional", cooperativa_id=cooperativa_id))
    else:
        return redirect(url_for("cadastro_profissional"))

@app.route("/editar_usuario/<int:usuario_id>", methods=["GET", "POST"])
def editar_usuario(usuario_id):
    erro = None
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nome_fantasia, categoria FROM cooperativa ORDER BY nome_fantasia ASC")
    cooperativas = cur.fetchall()
    if request.method == "POST":
        nome = request.form.get("nome")
        login = request.form.get("login")
        senha = request.form.get("senha")
        perfil = request.form.get("perfil")
        cooperativas_ids = request.form.get("cooperativas").split(",")  # Get cooperativa IDs from hidden input
        cooperativas_str = ",".join(cooperativas_ids)
        if senha:
            cur.execute(
                "UPDATE usuario SET nome=?, login=?, senha=?, perfil=?, cooperativas=? WHERE id=?",
                (nome, login, senha, perfil, cooperativas_str, usuario_id)
            )
        else:
            cur.execute(
                "UPDATE usuario SET nome=?, login=?, perfil=?, cooperativas=? WHERE id=?",
                (nome, login, perfil, cooperativas_str, usuario_id)
            )
        conn.commit()
        conn.close()
        return redirect(url_for("cadastro_usuario"))
    cur.execute("SELECT * FROM usuario WHERE id = ?", (usuario_id,))
    usuario = cur.fetchone()
    conn.close()
    if not usuario:
        return "Usuário não encontrado", 404
    # Preload cooperativas linked to the user
    usuario_cooperativas = []
    if usuario and usuario["cooperativas"]:
        usuario_cooperativas = usuario["cooperativas"].split(",")
    return render_template("editar_usuario.html", usuario=usuario, erro=erro, cooperativas=cooperativas, usuario_cooperativas=usuario_cooperativas)

@app.route("/editar_cooperativa/<int:cooperativa_id>", methods=["GET", "POST"])
def editar_cooperativa(cooperativa_id):
    erro = None
    conn = get_sqlite_conn()
    cur = conn.cursor()
    if request.method == "POST":
        razao_social = request.form.get("razao_social")
        nome_fantasia = request.form.get("nome_fantasia")
        cnpj = request.form.get("cnpj")
        endereco = request.form.get("endereco")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        categoria = request.form.get("categoria")
        data_inicio = request.form.get("data_inicio")
        data_fim = request.form.get("data_fim")
        # Atualiza os campos da cooperativa, incluindo período de faturamento
        cur.execute(
            "UPDATE cooperativa SET razao_social=?, nome_fantasia=?, cnpj=?, endereco=?, telefone=?, email=?, categoria=?, data_inicio=?, data_fim=? WHERE id=?",
            (razao_social, nome_fantasia, cnpj, endereco, telefone, email, categoria, data_inicio, data_fim, cooperativa_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("cadastro_cooperativa"))
    cur.execute("SELECT * FROM cooperativa WHERE id = ?", (cooperativa_id,))
    cooperativa = cur.fetchone()
    conn.close()
    if not cooperativa:
        return "Cooperativa não encontrada", 404
    return render_template("editar_cooperativa.html", cooperativa=cooperativa, erro=erro)

@app.route("/negar_justificativa/<int:justificativa_id>", methods=["POST"])
def negar_justificativa(justificativa_id):
    justificativa_negada = ""
    if request.is_json:
        data = request.get_json()
        justificativa_negada = data.get("justificativa", "")
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("UPDATE justificativa SET autorizacao = 0, justificativa_negada = ? WHERE id = ?", (justificativa_negada, justificativa_id))
    conn.commit()
    conn.close()
    return '', 204

@app.route("/autorizar_justificativa/<int:justificativa_id>", methods=["POST"])
def autorizar_justificativa(justificativa_id):
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("UPDATE justificativa SET autorizacao = 1 WHERE id = ?", (justificativa_id,))
    conn.commit()
    conn.close()
    return '', 204

@app.route("/reatorizar_justificativa/<int:justificativa_id>", methods=["POST"])
def reautorizar_justificativa(justificativa_id):
    """
    Update the status of a justificativa to 'Autorizado' and remove the denial justification.
    """
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("SELECT autorizacao FROM justificativa WHERE id = ?", (justificativa_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Justificativa not found"}), 404

    if row["autorizacao"] == 0:  # Only reauthorize if currently "Negado"
        cur.execute("UPDATE justificativa SET autorizacao = 1, justificativa_negada = NULL WHERE id = ?", (justificativa_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Justificativa reautorizada com sucesso"}), 200

    conn.close()
    return jsonify({"success": False, "message": "Justificativa não está no status 'Negado'"}), 400
@app.route("/ajustar_justificativa/<int:justificativa_id>", methods=["POST"])
def ajustar_justificativa(justificativa_id):
    from datetime import datetime
    datahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = get_sqlite_conn()
    cur = conn.cursor()
    # Adiciona campo ajuste_datahora se não existir
    cur.execute("PRAGMA table_info(justificativa)")
    columns = [col[1] for col in cur.fetchall()]
    if "ajuste_datahora" not in columns:
        cur.execute("ALTER TABLE justificativa ADD COLUMN ajuste_datahora TEXT")
        conn.commit()
    cur.execute("UPDATE justificativa SET ajuste_datahora = ? WHERE id = ?", (datahora, justificativa_id))
    conn.commit()
    conn.close()
    return {"datahora": datahora}

@app.route("/area_gerente")
@login_required(perfis=["administrador", "gerente"])
def area_gerente():
    conn = get_sqlite_conn()
    cur = conn.cursor()
    
    # Get cooperativas associated with the logged-in user
    cur.execute("SELECT cooperativas FROM usuario WHERE id = ?", (session["usuario_id"],))
    user_cooperativas = cur.fetchone()
    cooperativas_ids = user_cooperativas["cooperativas"].split(",") if user_cooperativas and "cooperativas" in user_cooperativas.keys() and user_cooperativas["cooperativas"] else []
    
    # Fetch justificativas for the user's cooperativas
    if cooperativas_ids:
        cur.execute("""
            SELECT j.*, p.nome_completo, p.matricula, c.nome as categoria_profissional, coop.nome_fantasia as cooperativa
            FROM justificativa j
            LEFT JOIN profissional p ON j.profissional_id = p.id
            LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
            LEFT JOIN cooperativa coop ON j.cooperativa_id = coop.id
            WHERE j.cooperativa_id IN ({})
        """.format(",".join("?" for _ in cooperativas_ids)), cooperativas_ids)
        justificativas = cur.fetchall()
        
        # Fetch autorizacoes (example: pending approvals)
        cur.execute("""
            SELECT j.*, p.nome_completo, p.matricula, c.nome as categoria_profissional, coop.nome_fantasia as cooperativa
            FROM justificativa j
            LEFT JOIN profissional p ON j.profissional_id = p.id
            LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
            LEFT JOIN cooperativa coop ON j.cooperativa_id = coop.id
            WHERE j.cooperativa_id IN ({}) AND j.autorizacao IS NULL
        """.format(",".join("?" for _ in cooperativas_ids)), cooperativas_ids)
        autorizacoes = cur.fetchall()
        
        # Fetch categories associated with the user's cooperativas
        cur.execute("""
            SELECT DISTINCT c.nome as categoria_profissional
            FROM categoria_profissional c
            INNER JOIN profissional p ON c.id = p.categoria_id
            INNER JOIN cooperativa coop ON p.cooperativa_id = coop.id
            WHERE coop.id IN ({}) AND c.nome IS NOT NULL
        """.format(",".join("?" for _ in cooperativas_ids)), cooperativas_ids)
        categorias = [row["categoria_profissional"] for row in cur.fetchall()]
    else:
        justificativas = []
        autorizacoes = []
        categorias = []
    
    # Generate summary data
    resumo = {}
    for j in justificativas:
        nome = j["nome_completo"]
        if nome not in resumo:
            resumo[nome] = {
                "categoria": j["categoria_profissional"],
                "cooperativa": j["cooperativa"],
                "autorizadas": 0,
                "negadas": 0,
                "total": 0
            }
        resumo[nome]["total"] += 1
        if j["autorizacao"] == 1:
            resumo[nome]["autorizadas"] += 1
        elif j["autorizacao"] == 0:
            resumo[nome]["negadas"] += 1

    conn.close()
    return render_template("area_gerente.html", justificativas=justificativas, autorizacoes=autorizacoes, categorias=categorias, resumo=resumo)

@app.route("/area_preposto")
@login_required(perfis=["administrador", "preposto"])
def area_preposto():
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT j.*, p.matricula, p.nome_completo, c.nome as categoria_profissional, coop.nome_fantasia as cooperativa
        FROM justificativa j
        LEFT JOIN profissional p ON j.profissional_id = p.id
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        LEFT JOIN cooperativa coop ON p.cooperativa_id = coop.id
        ORDER BY j.datahora_preenchimento DESC
    """)
    justificativas = cur.fetchall()

    # Generate summary data
    resumo = {}
    for j in justificativas:
        nome = j["nome_completo"]
        if nome not in resumo:
            resumo[nome] = {
                "categoria": j["categoria_profissional"],
                "cooperativa": j["cooperativa"],
                "autorizadas": 0,
                "negadas": 0,
                "total": 0
            }
        resumo[nome]["total"] += 1
        if j["autorizacao"] == 1:
            resumo[nome]["autorizadas"] += 1
        elif j["autorizacao"] == 0:
            resumo[nome]["negadas"] += 1

    conn.close()
    return render_template("area_preposto.html", justificativas=justificativas, resumo=resumo)

@app.route("/relatorio_justificativas")
def relatorio_justificativas():
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")
    if not data_inicio or not data_fim:
        return "Informe o período.", 400

    conn = get_sqlite_conn()
    cur = conn.cursor()

    # Ajuste: comparar datas como texto funciona apenas se o formato for yyyy-mm-dd.
    # Se as datas no banco estão como dd/mm/aaaa, a comparação >= e <= não funciona corretamente.
    # Solução: buscar todas as justificativas autorizadas e filtrar em Python.

    cur.execute("""
        SELECT j.*, p.matricula, p.nome_completo, coop.nome_fantasia, coop.logo as logo_url
        FROM justificativa j
        LEFT JOIN profissional p ON j.profissional_id = p.id
        LEFT JOIN cooperativa coop ON p.cooperativa_id = coop.id
        WHERE j.autorizacao = 1
        ORDER BY j.data_ocorrencia ASC
    """)
    justificativas = cur.fetchall()

    # Converter datas do filtro para datetime
    from datetime import datetime
    def parse_data_iso(data_iso):
        if data_iso and "-" in data_iso:
            partes = data_iso.split("-")
            if len(partes) == 3:
                return datetime(int(partes[0]), int(partes[1]), int(partes[2]))
        return None

    data_inicio_dt = parse_data_iso(data_inicio)
    data_fim_dt = parse_data_iso(data_fim)

    # Filtrar justificativas no Python
    justificativas_filtradas = []
    for j in justificativas:
        data_ocorrencia = j["data_ocorrencia"]
        # Espera dd/mm/aaaa
        try:
            partes = data_ocorrencia.split("/")
            if len(partes) == 3:
                data_ocorrencia_dt = datetime(int(partes[2]), int(partes[1]), int(partes[0]))
                if data_inicio_dt and data_fim_dt and data_inicio_dt <= data_ocorrencia_dt <= data_fim_dt:
                    justificativas_filtradas.append(j)
        except Exception:
            continue

    conn.close()
    rendered = render_template("relatorio_justificativas.html", justificativas=justificativas_filtradas)
    response = make_response(rendered)
    response.headers["Content-Type"] = "text/html"
    return response

@app.route("/importar_profissionais", methods=["POST"])
def importar_profissionais():
    file = request.files.get("csv_profissionais")
    if not file or not file.filename.endswith(".csv"):
        return redirect(url_for("cadastro_profissional"))
    conn = get_sqlite_conn()
    cur = conn.cursor()
    linhas = file.read().decode("utf-8").splitlines()
    reader = csv.reader(linhas, delimiter=";")
    for row in reader:
        if len(row) != 6:
            continue  # pula linhas inválidas
        nome_completo, matricula, celular, email, cooperativa_nome, categoria_nome = [item.strip() for item in row]
        # Busca cooperativa pelo nome_fantasia
        cur.execute("SELECT id FROM cooperativa WHERE nome_fantasia = ?", (cooperativa_nome,))
        coop_row = cur.fetchone()
        if not coop_row:
            continue  # pula se cooperativa não encontrada
        cooperativa_id = coop_row["id"]
        # Busca categoria_profissional pelo nome, cria se não existir
        cur.execute("SELECT id FROM categoria_profissional WHERE nome = ?", (categoria_nome,))
        cat_row = cur.fetchone()
        if not cat_row:
            cur.execute("INSERT INTO categoria_profissional (nome) VALUES (?)", (categoria_nome,))
            conn.commit()
            cur.execute("SELECT id FROM categoria_profissional WHERE nome = ?", (categoria_nome,))
            cat_row = cur.fetchone()
        categoria_id = cat_row["id"] if cat_row else None
        # Verifica duplicidade de matrícula
        cur.execute("SELECT id FROM profissional WHERE matricula = ?", (matricula,))
        if cur.fetchone():
            continue  # pula duplicados
        cur.execute(
            "INSERT INTO profissional (nome_completo, matricula, celular, email, cooperativa_id, categoria_id) VALUES (?, ?, ?, ?, ?, ?)",
            (nome_completo, matricula, celular, email, cooperativa_id, categoria_id)
        )
        conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("cadastro_profissional"))

@app.route("/modelo_csv_profissional")
def modelo_csv_profissional():
    from flask import Response
    csv_content = "nome_completo;matricula;celular;email;cooperativa;categoria\n"
    csv_content += "João da Silva;12345;11999999999;joao@email.com;CoopExemplo;Médico\n"
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=modelo_profissional.csv"}
    )

@app.route("/buscar_profissionais")
def buscar_profissionais():
    query = request.args.get("query", "").strip()
    if len(query) < 5:
        return jsonify([])

    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nome_completo
        FROM profissional
        WHERE nome_completo LIKE ?
        ORDER BY nome_completo ASC
    """, (f"%{query}%",))
    profissionais = [{"id": row["id"], "nome_completo": row["nome_completo"]} for row in cur.fetchall()]
    conn.close()
    return jsonify(profissionais)

@app.route("/justificativas_profissional/<int:profissional_id>")
def justificativas_profissional(profissional_id):
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, data_ocorrencia, justificativa,
               CASE 
                   WHEN autorizacao = 1 THEN 'Aprovada'
                   WHEN autorizacao = 0 THEN 'Negada'
                   ELSE 'Pendente'
               END as status
        FROM justificativa
        WHERE profissional_id = ?
        ORDER BY date(substr(data_ocorrencia, 7, 4) || '-' || substr(data_ocorrencia, 4, 2) || '-' || substr(data_ocorrencia, 1, 2)) DESC
    """, (profissional_id,))
    justificativas = [{"id": row["id"], "data_ocorrencia": row["data_ocorrencia"], "justificativa": row["justificativa"], "status": row["status"]} for row in cur.fetchall()]
    conn.close()
    return jsonify(justificativas)

@app.route("/area_auditoria")
def area_auditoria():
    conn = get_sqlite_conn()
    cur = conn.cursor()
    
    # Ensure the `usuario_ajuste_id` column exists in the `justificativa` table
    cur.execute("PRAGMA table_info(justificativa)")
    columns = [col[1] for col in cur.fetchall()]
    if "usuario_ajuste_id" not in columns:
        cur.execute("ALTER TABLE justificativa ADD COLUMN usuario_ajuste_id INTEGER")
        conn.commit()
    
    # Get cooperativas associated with the logged-in user
    cur.execute("SELECT cooperativas FROM usuario WHERE id = ?", (session["usuario_id"],))
    user_cooperativas = cur.fetchone()
    cooperativas_ids = user_cooperativas["cooperativas"].split(",") if user_cooperativas and "cooperativas" in user_cooperativas.keys() and user_cooperativas["cooperativas"] else []
    
    # Fetch justificativas for the user's cooperativas
    if cooperativas_ids:
        cur.execute("""
            SELECT j.*, p.nome_completo, p.matricula, c.nome as categoria_profissional, coop.nome_fantasia as cooperativa, u.nome as usuario_ajuste
            FROM justificativa j
            LEFT JOIN profissional p ON j.profissional_id = p.id
            LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
            LEFT JOIN cooperativa coop ON j.cooperativa_id = coop.id
            LEFT JOIN usuario u ON j.usuario_ajuste_id = u.id
            WHERE j.cooperativa_id IN ({})
            ORDER BY j.datahora_preenchimento DESC
        """.format(",".join("?" for _ in cooperativas_ids)), cooperativas_ids)
        justificativas = cur.fetchall()
        
        # Fetch categories associated with the user's cooperativas
        cur.execute("""
            SELECT DISTINCT c.nome as categoria_profissional
            FROM categoria_profissional c
            INNER JOIN profissional p ON c.id = p.categoria_id
            INNER JOIN cooperativa coop ON p.cooperativa_id = coop.id
            WHERE coop.id IN ({}) AND c.nome IS NOT NULL
        """.format(",".join("?" for _ in cooperativas_ids)), cooperativas_ids)
        categorias = [row["categoria_profissional"] for row in cur.fetchall()]
    else:
        justificativas = []
        categorias = []
    
    # Generate summary data
    resumo = {}
    for j in justificativas:
        nome = j["nome_completo"]
        if nome not in resumo:
            resumo[nome] = {
                "categoria": j["categoria_profissional"],
                "cooperativa": j["cooperativa"],
                "autorizadas": 0,
                "negadas": 0,
                "total": 0
            }
        resumo[nome]["total"] += 1
        if j["autorizacao"] == 1:
            resumo[nome]["autorizadas"] += 1
        elif j["autorizacao"] == 0:
            resumo[nome]["negadas"] += 1

    conn.close()
    return render_template("area_auditoria.html", justificativas=justificativas, categorias=categorias, resumo=resumo)

@app.route("/gerar_relatorio_resumo")
@login_required(perfis=["administrador", "gerente"])
def gerar_relatorio_resumo():
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.nome_completo, c.nome as categoria_profissional, coop.nome_fantasia as cooperativa,
               SUM(CASE WHEN j.autorizacao = 1 THEN 1 ELSE 0 END) as autorizadas,
               SUM(CASE WHEN j.autorizacao = 0 THEN 1 ELSE 0 END) as negadas,
               COUNT(j.id) as total
        FROM justificativa j
        LEFT JOIN profissional p ON j.profissional_id = p.id
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        LEFT JOIN cooperativa coop ON p.cooperativa_id = coop.id
        GROUP BY p.nome_completo, c.nome, coop.nome_fantasia
        ORDER BY p.nome_completo ASC
    """)
    resumo = cur.fetchall()
    conn.close()

    # Create an in-memory output file for the XLSX
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Resumo Justificativas")

    # Write headers
    headers = ["Nome", "Categoria", "Cooperativa", "Autorizadas", "Negadas", "Total"]
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header)

    # Write data
    for row_num, row in enumerate(resumo, start=1):
        worksheet.write(row_num, 0, row["nome_completo"])
        worksheet.write(row_num, 1, row["categoria_profissional"])
        worksheet.write(row_num, 2, row["cooperativa"])
        worksheet.write(row_num, 3, row["autorizadas"])
        worksheet.write(row_num, 4, row["negadas"])
        worksheet.write(row_num, 5, row["total"])

    workbook.close()
    output.seek(0)

    # Return the XLSX file as a response
    response = Response(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Content-Disposition"] = "attachment; filename=Resumo_Justificativas.xlsx"
    return response

@app.route("/registrar-ajuste/<int:justificativa_id>", methods=["POST"])
@login_required
def registrar_ajuste(justificativa_id):
    from datetime import datetime
    ajuste_datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_sqlite_conn()
    cur = conn.cursor()
    
    # Ensure the ajuste_datahora column exists
    cur.execute("PRAGMA table_info(justificativa)")
    columns = [col[1] for col in cur.fetchall()]
    if "ajuste_datahora" not in columns:
        cur.execute("ALTER TABLE justificativa ADD COLUMN ajuste_datahora TEXT")
        conn.commit()
    
    # Update the ajuste_datahora field
    cur.execute("UPDATE justificativa SET ajuste_datahora = ? WHERE id = ?", (ajuste_datahora, justificativa_id))
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Ajuste registrado com sucesso!", "ajuste_datahora": ajuste_datahora})

@app.route("/visualizar_justificativa/<int:justificativa_id>")
def visualizar_justificativa(justificativa_id):
    conn = get_sqlite_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT j.*, p.nome_completo, p.email, p.matricula, c.nome as categoria_profissional, 
               coop.nome_fantasia, coop.logo as logo_url
        FROM justificativa j
        LEFT JOIN profissional p ON j.profissional_id = p.id
        LEFT JOIN categoria_profissional c ON p.categoria_id = c.id
        LEFT JOIN cooperativa coop ON p.cooperativa_id = coop.id
        WHERE j.id = ?
    """, (justificativa_id,))
    justificativa = cur.fetchone()
    conn.close()
    if not justificativa:
        return "Justificativa não encontrada", 404

    # Renderiza o template com os dados da justificativa
    return render_template(
        "visualizar_justificativa.html",
        justificativa=justificativa,
        nome_fantasia=justificativa["nome_fantasia"] if "nome_fantasia" in justificativa.keys() else "",
        logo_url=justificativa["logo_url"] if justificativa["logo_url"] else "/static/logos/default.png"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
