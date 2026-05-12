import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER     = "leon5512676@gmail.com"
GMAIL_PASSWORD = "lusr soya xbzo zwhw"
SITE_URL       = "https://tradeit.pythonanywhere.com"


def _send(to_email: str, subject: str, html: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"TradeIt <{GMAIL_USER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[email_sender] Ошибка отправки: {e}")
        return False


def send_2fa_code_email(to_email: str, username: str, code: str) -> bool:
    subject = "Код подтверждения TradeIt"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f0f4f8; margin:0; padding:40px 0; }}
        .wrap {{ max-width:520px; margin:0 auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.08); }}
        .header {{ background:linear-gradient(135deg,#00aeef,#6c47ff); padding:36px 40px; text-align:center; }}
        .header h1 {{ color:#fff; margin:0; font-size:26px; font-weight:800; letter-spacing:-.5px; }}
        .header p {{ color:rgba(255,255,255,.8); margin:6px 0 0; font-size:14px; }}
        .body {{ padding:36px 40px; }}
        .body p {{ color:#4a5568; font-size:15px; line-height:1.6; margin:0 0 16px; }}
        .code {{ display:block; margin:24px auto; text-align:center; font-size:36px; font-weight:800; letter-spacing:8px; color:#6c47ff; background:#f0f4f8; border-radius:12px; padding:18px 0; }}
        .footer {{ text-align:center; padding:20px 40px 28px; font-size:12px; color:#a0aec0; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>🔐 TradeIt</h1>
          <p>Двухфакторная аутентификация</p>
        </div>
        <div class="body">
          <p>Привет, <strong>{username}</strong>!</p>
          <p>Твой код подтверждения:</p>
          <span class="code">{code}</span>
          <p>Код действителен <strong>10 минут</strong>. Никому его не передавай.</p>
        </div>
        <div class="footer">
          Если ты не запрашивал этот код — просто игнори это письмо.
        </div>
      </div>
    </body>
    </html>
    """
    return _send(to_email, subject, html)


def send_verification_email(to_email: str, username: str, token: str) -> bool:
    verify_url = f"{SITE_URL}/verify/{token}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f0f4f8; margin:0; padding:40px 0; }}
        .wrap {{ max-width:520px; margin:0 auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.08); }}
        .header {{ background:linear-gradient(135deg,#00aeef,#6c47ff); padding:36px 40px; text-align:center; }}
        .header h1 {{ color:#fff; margin:0; font-size:26px; font-weight:800; letter-spacing:-.5px; }}
        .header p {{ color:rgba(255,255,255,.8); margin:6px 0 0; font-size:14px; }}
        .body {{ padding:36px 40px; }}
        .body p {{ color:#4a5568; font-size:15px; line-height:1.6; margin:0 0 16px; }}
        .btn {{ display:block; margin:28px auto 0; width:fit-content; background:linear-gradient(135deg,#00aeef,#6c47ff); color:#fff; text-decoration:none; padding:14px 36px; border-radius:12px; font-weight:700; font-size:16px; }}
        .link {{ margin-top:24px; padding:14px; background:#f7fafc; border-radius:8px; word-break:break-all; font-size:12px; color:#718096; }}
        .footer {{ text-align:center; padding:20px 40px 28px; font-size:12px; color:#a0aec0; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>🛍️ TradeIt</h1>
          <p>Подтверждение email</p>
        </div>
        <div class="body">
          <p>Привет, <strong>{username}</strong>!</p>
          <p>Ты зарегистрировался на TradeIt. Нажми кнопку ниже чтобы подтвердить email и активировать аккаунт.</p>
          <a class="btn" href="{verify_url}">✅ Подтвердить email</a>
          <div class="link">
            Или перейди по ссылке вручную:<br>{verify_url}
          </div>
        </div>
        <div class="footer">
          Ссылка действует 24 часа.<br>
          Если ты не регистрировался — просто игнорируй это письмо.
        </div>
      </div>
    </body>
    </html>
    """
    return _send(to_email, "Подтверди email — TradeIt", html)


def send_message_notification(to_email: str, sender_name: str, preview: str, link: str) -> bool:
    full_link = f"{SITE_URL}{link}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f0f4f8; margin:0; padding:40px 0; }}
        .wrap {{ max-width:520px; margin:0 auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.08); }}
        .header {{ background:linear-gradient(135deg,#00aeef,#6c47ff); padding:36px 40px; text-align:center; }}
        .header h1 {{ color:#fff; margin:0; font-size:26px; font-weight:800; }}
        .header p {{ color:rgba(255,255,255,.8); margin:6px 0 0; font-size:14px; }}
        .body {{ padding:36px 40px; }}
        .body p {{ color:#4a5568; font-size:15px; line-height:1.6; margin:0 0 16px; }}
        .bubble {{ background:#f0f4f8; border-left:4px solid #00aeef; border-radius:8px; padding:14px 18px; font-size:15px; color:#2d3748; margin:16px 0; }}
        .btn {{ display:block; margin:28px auto 0; width:fit-content; background:linear-gradient(135deg,#00aeef,#6c47ff); color:#fff; text-decoration:none; padding:14px 36px; border-radius:12px; font-weight:700; font-size:16px; }}
        .footer {{ text-align:center; padding:20px 40px 28px; font-size:12px; color:#a0aec0; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>✉️ TradeIt</h1>
          <p>Новое сообщение</p>
        </div>
        <div class="body">
          <p>Тебе написал <strong>{sender_name}</strong>:</p>
          <div class="bubble">«{preview}»</div>
          <a class="btn" href="{full_link}">Ответить</a>
        </div>
        <div class="footer">
          Ты получил это письмо, потому что тебе пришло сообщение на TradeIt.
        </div>
      </div>
    </body>
    </html>
    """
    return _send(to_email, f"✉️ Новое сообщение от {sender_name} — TradeIt", html)


def send_purchase_notification(to_email: str, buyer_name: str, ad_title: str, ad_id: int) -> bool:
    full_link = f"{SITE_URL}/ad/{ad_id}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f0f4f8; margin:0; padding:40px 0; }}
        .wrap {{ max-width:520px; margin:0 auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.08); }}
        .header {{ background:linear-gradient(135deg,#00aeef,#6c47ff); padding:36px 40px; text-align:center; }}
        .header h1 {{ color:#fff; margin:0; font-size:26px; font-weight:800; }}
        .header p {{ color:rgba(255,255,255,.8); margin:6px 0 0; font-size:14px; }}
        .body {{ padding:36px 40px; }}
        .body p {{ color:#4a5568; font-size:15px; line-height:1.6; margin:0 0 16px; }}
        .highlight {{ background:#f0fff4; border-left:4px solid #48bb78; border-radius:8px; padding:14px 18px; font-size:15px; color:#2d3748; margin:16px 0; }}
        .btn {{ display:block; margin:28px auto 0; width:fit-content; background:linear-gradient(135deg,#48bb78,#00aeef); color:#fff; text-decoration:none; padding:14px 36px; border-radius:12px; font-weight:700; font-size:16px; }}
        .footer {{ text-align:center; padding:20px 40px 28px; font-size:12px; color:#a0aec0; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>🎉 TradeIt</h1>
          <p>Твоё объявление куплено!</p>
        </div>
        <div class="body">
          <p>Привет! <strong>{buyer_name}</strong> купил твоё объявление:</p>
          <div class="highlight">«{ad_title}»</div>
          <p>Свяжись с покупателем через мессенджер TradeIt, чтобы договориться о передаче товара.</p>
          <a class="btn" href="{full_link}">Посмотреть объявление</a>
        </div>
        <div class="footer">
          TradeIt — маркетплейс для продажи товаров.
        </div>
      </div>
    </body>
    </html>
    """
    return _send(to_email, f"🎉 Твоё объявление куплено — TradeIt", html)


def send_call_notification(to_email: str, caller_name: str, caller_num: str, call_link: str) -> bool:
    full_link = f"{SITE_URL}{call_link}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f0f4f8; margin:0; padding:40px 0; }}
        .wrap {{ max-width:520px; margin:0 auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.08); }}
        .header {{ background:linear-gradient(135deg,#22c55e,#00aeef); padding:36px 40px; text-align:center; }}
        .header h1 {{ color:#fff; margin:0; font-size:26px; font-weight:800; }}
        .header p {{ color:rgba(255,255,255,.8); margin:6px 0 0; font-size:14px; }}
        .body {{ padding:36px 40px; }}
        .body p {{ color:#4a5568; font-size:15px; line-height:1.6; margin:0 0 16px; }}
        .bubble {{ background:#f0fff4; border-left:4px solid #22c55e; border-radius:8px; padding:14px 18px; font-size:15px; color:#2d3748; margin:16px 0; }}
        .btn {{ display:block; margin:28px auto 0; width:fit-content; background:linear-gradient(135deg,#22c55e,#00aeef); color:#fff; text-decoration:none; padding:14px 36px; border-radius:12px; font-weight:700; font-size:16px; }}
        .footer {{ text-align:center; padding:20px 40px 28px; font-size:12px; color:#a0aec0; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>📞 TradeIt</h1>
          <p>Входящий звонок</p>
        </div>
        <div class="body">
          <p>Тебе звонил <strong>{caller_name}</strong>:</p>
          <div class="bubble">Номер: {caller_num}</div>
          <p>Если ты пропустил звонок — нажми кнопку ниже, чтобы перезвонить.</p>
          <a class="btn" href="{full_link}">📞 Перезвонить</a>
        </div>
        <div class="footer">
          TradeIt — маркетплейс для продажи товаров.
        </div>
      </div>
    </body>
    </html>
    """
    return _send(to_email, f"📞 Входящий звонок от {caller_name} — TradeIt", html)