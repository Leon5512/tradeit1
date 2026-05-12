import json
import os
import traceback

VAPID_PRIVATE_KEY = "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgMQY-OQ_CESunvmITjyHhhdOeIp-U92pzQ_BxV23qwhmhRANCAAQOEFEbgw0v1gsIS-6COZBAVwZZQFREPEgeFcpbcsexbN6joFG_0CjYkYluDIPHyHgmP4yoPVAwK6R4cFD3wN5u"

VAPID_PUBLIC_KEY = "BA4QURuDDS_WCwhL7oI5kEBXBllAVEQ8SB4Vyltyx7Fs3qOgUb_QKNiRiW4Mg8fIeCY_jKg9UDArpHhwUPfA3m4"

VAPID_CLAIMS = {"sub": "mailto:admin@tradeit.ru"}


def send_push(subscription_info: dict, title: str, body: str, url: str = "/", tag: str = "tradeit"):
    try:
        from pywebpush import webpush, WebPushException
        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "tag": tag,
        })
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
        return True
    except Exception:
        traceback.print_exc()
        return False


def send_push_to_user(db, user_id: int, title: str, body: str, url: str = "/", tag: str = "tradeit"):
    subs = db.execute(
        "SELECT * FROM push_subscriptions WHERE user_id=?", (user_id,)
    ).fetchall()
    for sub in subs:
        try:
            info = {
                "endpoint": sub["endpoint"],
                "keys": {
                    "p256dh": sub["p256dh"],
                    "auth":   sub["auth"],
                },
            }
            send_push(info, title, body, url, tag)
        except Exception:
            traceback.print_exc()