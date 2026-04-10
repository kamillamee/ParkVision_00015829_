"""Send notifications by email and SMS (reservation created, payment, cancel)."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from backend.config import (
    NOTIFY_EMAIL_ENABLED,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL,
    SMTP_USE_TLS,
    NOTIFY_SMS_ENABLED,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
)


def send_email(to_email: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """Send email via SMTP. Returns True if sent, False on error or disabled."""
    if not to_email or not to_email.strip() or "@" not in to_email:
        return False
    if not NOTIFY_EMAIL_ENABLED or not SMTP_HOST or not SMTP_USER:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email.strip()
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, to_email.strip(), msg.as_string())
        return True
    except Exception:
        return False


def send_sms(to_phone: str, body: str) -> bool:
    """Send SMS via Twilio. Returns True if sent, False on error or disabled."""
    if not to_phone or not body:
        return False
    if not NOTIFY_SMS_ENABLED or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return False
    try:
        import httpx
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        data = {
            "To": to_phone.strip(),
            "From": TWILIO_FROM_NUMBER,
            "Body": body[:1600],
        }
        with httpx.Client(timeout=10.0) as client:
            r = client.post(url, auth=auth, data=data)
            return r.status_code in (200, 201)
    except Exception:
        return False


def notify_reservation_created(
    user_email: Optional[str],
    user_phone: Optional[str],
    slot_number: str,
    car_plate: str,
    start_time: str,
    end_time: str,
    amount: float,
) -> None:
    """Send notification when reservation is created (email and/or SMS)."""
    text = (
        f"Smart Vision: Your reservation is created.\n"
        f"Slot: {slot_number}, Car: {car_plate}\n"
        f"Start: {start_time}, End: {end_time}\n"
        f"Amount: ${amount:.2f}. Please confirm payment in the app."
    )
    html = (
        f"<p>Smart Vision: Your reservation is created.</p>"
        f"<p><b>Slot:</b> {slot_number}, <b>Car:</b> {car_plate}</p>"
        f"<p><b>Start:</b> {start_time}, <b>End:</b> {end_time}</p>"
        f"<p><b>Amount:</b> ${amount:.2f}. Please confirm payment in the app.</p>"
    )
    if user_email:
        send_email(
            user_email,
            "Smart Vision: Reservation created",
            text,
            html,
        )
    if user_phone:
        send_sms(user_phone, text)


def notify_payment_confirmed(
    user_email: Optional[str],
    user_phone: Optional[str],
    slot_number: str,
    start_time: str,
    end_time: str,
) -> None:
    """Send notification when payment is confirmed (email and/or SMS)."""
    text = (
        f"Smart Vision: Payment confirmed. Your reservation is active.\n"
        f"Slot: {slot_number}, Start: {start_time}, End: {end_time}"
    )
    html = (
        f"<p>Smart Vision: Payment confirmed. Your reservation is active.</p>"
        f"<p><b>Slot:</b> {slot_number}, <b>Start:</b> {start_time}, <b>End:</b> {end_time}</p>"
    )
    if user_email:
        send_email(
            user_email,
            "Smart Vision: Payment confirmed",
            text,
            html,
        )
    if user_phone:
        send_sms(user_phone, text)


def notify_reservation_cancelled(
    user_email: Optional[str],
    user_phone: Optional[str],
    slot_number: str,
    start_time: str,
) -> None:
    """Send notification when reservation is cancelled (email and/or SMS)."""
    text = (
        f"Smart Vision: Your reservation has been cancelled.\n"
        f"Slot: {slot_number}, was from: {start_time}"
    )
    html = (
        f"<p>Smart Vision: Your reservation has been cancelled.</p>"
        f"<p><b>Slot:</b> {slot_number}, was from: {start_time}</p>"
    )
    if user_email:
        send_email(
            user_email,
            "Smart Vision: Reservation cancelled",
            text,
            html,
        )
    if user_phone:
        send_sms(user_phone, text)
