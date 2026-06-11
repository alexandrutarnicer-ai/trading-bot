"""Diagnosticare Telegram — ruleaza din orice terminal."""
import os, json, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

tok = os.environ.get("TELEGRAM_TOKEN", "")
cid = os.environ.get("TELEGRAM_CHAT_ID", "")

print(f"TELEGRAM_TOKEN:   {'SET ' + tok[:8] + '...' if tok else 'GOL - LIPSA'}")
print(f"TELEGRAM_CHAT_ID: {cid if cid else 'GOL - LIPSA'}")

if not tok or not cid:
    print()
    print("PROBLEMA: Credentialele lipsesc.")
    print(f"Creeaza fisierul {os.path.join(ROOT, '.env')} dupa modelul .env.example")
else:
    print()
    print("Trimit mesaj test pe Telegram...")
    try:
        payload = json.dumps({
            "chat_id": cid,
            "text": "<b>Test bot activ</b>\nDaca primesti asta, Telegram functioneaza!",
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"SUCCES: message_id={data['result']['message_id']}")
    except urllib.request.HTTPError as e:
        print(f"HTTP EROARE {e.code}: {e.read().decode()}")
    except Exception as e:
        print(f"EROARE retea: {e}")
