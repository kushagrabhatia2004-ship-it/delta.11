"""
SMS / WhatsApp alert sender for the early warning system.
Uses Twilio if credentials are set; otherwise prints a dry-run message.

Optional:  pip install twilio
Env vars:  TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM  (e.g. +1415...)
           For WhatsApp, TWILIO_FROM = "whatsapp:+14155238886" (Twilio sandbox)
"""
import os


def format_alert(field_name, warning):
    lines = [
        f"FARM ALERT - {field_name}",
        f"Nitrogen runoff risk: {warning['nitrogen_level']} ({warning['nitrogen_risk']})",
        f"Pesticide runoff risk: {warning['pesticide_level']} ({warning['pesticide_risk']})",
        "Actions:",
    ] + [f"- {a}" for a in warning["actions"][:4]]
    return "\n".join(lines)


def send_alert(to_number, message, whatsapp=False):
    """Returns (sent, info). info is a short message that explains the result."""
    sid, token, sender = (os.getenv("TWILIO_SID"), os.getenv("TWILIO_TOKEN"),
                          os.getenv("TWILIO_FROM"))
    if whatsapp:
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"
        if sender and not sender.startswith("whatsapp:"):
            sender = f"whatsapp:{sender}"

    if not (sid and token and sender):
        print(f"[DRY RUN] would send to {to_number}:\n{message}\n")
        return False, ("Dry run: Twilio credentials are not set, so nothing was sent. "
                       "The message is printed in the server terminal.")
    try:
        from twilio.rest import Client
    except ImportError:
        return False, "Twilio is not installed. Run: pip install twilio"
    try:
        msg = Client(sid, token).messages.create(body=message, from_=sender, to=to_number)
    except Exception as e:                      # wrong token, unverified number, etc.
        print("[TWILIO ERROR]", e)
        return False, f"Twilio refused the message: {e}"
    print("Sent:", msg.sid)
    return True, f"Alert sent (id {msg.sid})."


def notify_if_needed(field_name, warning, phone, whatsapp=False):
    """Send only when any risk is MEDIUM or HIGH."""
    if "LOW" == warning["nitrogen_level"] == warning["pesticide_level"]:
        return False
    return send_alert(phone, format_alert(field_name, warning), whatsapp)[0]