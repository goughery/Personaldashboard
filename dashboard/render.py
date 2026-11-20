"""Render a responsive single-page dashboard; encrypt it with a passphrase (AES-GCM) so a
public host never exposes email subjects. Without DASHBOARD_PASSWORD it writes plain HTML (local use only)."""
import base64, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

APP = open(os.path.join(os.path.dirname(__file__), "app.html")).read()
GATE = open(os.path.join(os.path.dirname(__file__), "gate.html")).read()


def render(data, password, outdir):
    os.makedirs(outdir, exist_ok=True)
    payload = json.dumps(data)
    if not password:
        html = APP.replace("/*DATA*/null", payload.replace("</", "<\\/"))
    else:
        page = APP.replace("/*DATA*/null", "window.__DATA__").replace("<!--INIT-->", "")
        salt, iv = os.urandom(16), os.urandom(12)
        key = PBKDF2HMAC(hashes.SHA256(), 32, salt, 250000).derive(password.encode())
        ct = AESGCM(key).encrypt(iv, page.encode() + b"\0" + payload.encode(), None)
        blob = json.dumps({k: base64.b64encode(v).decode() for k, v in
                           {"salt": salt, "iv": iv, "ct": ct}.items()})
        html = GATE.replace("/*BLOB*/null", blob)
    open(os.path.join(outdir, "index.html"), "w").write(html)
