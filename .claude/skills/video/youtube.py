#!/home/kabu/.venvs/video/bin/python
"""YouTube Data API で、けっさんノートのチャンネルに動画を上げる。

使い方:
  youtube.py auth                         # 最初の 1 回だけ。ユーザが SSH で対話的に流す
  youtube.py upload <名前>                # data/video/<名前>/ の動画とサムネイルを上げる
  youtube.py thumb <名前>                 # サムネイルだけ付け直す (upload で弾かれたとき)

upload は kessannote/videos/<名前>.youtube.md からタイトルと概要欄を読む。上げた動画の ID は
data/video/<名前>/youtube.json に残し、同じ週を二度上げない。

鍵は ~/.config/kabu/ に置く (どれも権限 600、リポジトリに入れない)。
  youtube-client.json  Google Cloud で作った OAuth クライアント (デスクトップ アプリ) の JSON
  youtube-token.json   auth で作るリフレッシュトークン

審査を通っていない API プロジェクトから上げた動画は非公開になる。公開はユーザが YouTube Studio で行う。
"""
import base64
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONF = Path.home() / ".config/kabu"
CLIENT = CONF / "youtube-client.json"
TOKEN = CONF / "youtube-token.json"
ROOT = Path(__file__).resolve().parents[3]  # kabu-terminal
REDIRECT = "http://localhost:8765"
# upload は動画を上げる、youtube は上げたあとにタイトルや概要欄を直すため
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"
CATEGORY = "25"  # ニュースと政治


def client():
    c = json.loads(CLIENT.read_text())
    c = c.get("installed") or c.get("web")
    return c["client_id"], c["client_secret"]


def post_form(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def write_secret(path, obj):
    old = os.umask(0o077)
    try:
        path.write_text(json.dumps(obj))
    finally:
        os.umask(old)
    path.chmod(0o600)


def auth():
    cid, secret = client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("1. 次の URL をブラウザで開き、Google アカウントを選んでから「けっさんノート」を選んで許可する")
    print(url)
    print("2. 許可すると localhost:8765 に飛んで「接続できません」になる。そのときのアドレス欄の URL を丸ごと貼る")
    while True:
        got = input("URL: ").strip()
        code = urllib.parse.parse_qs(urllib.parse.urlparse(got).query).get("code", [None])[0]
        if code:
            break
        if not got:
            raise SystemExit("中止した")
        print("これは途中のページの URL。ブラウザで先に進み、localhost:8765 で始まる URL を貼る")
        print("(「確認されていません」の画面なら「詳細」→「〜に移動」。やめるなら空のまま Enter)")
    tok = post_form("https://oauth2.googleapis.com/token", {
        "client_id": cid, "client_secret": secret, "code": code, "code_verifier": verifier,
        "grant_type": "authorization_code", "redirect_uri": REDIRECT})
    if "refresh_token" not in tok:
        raise SystemExit("リフレッシュトークンが返らなかった。もう一度 auth を流す")
    write_secret(TOKEN, {"refresh_token": tok["refresh_token"]})
    ch = api("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true")
    names = [i["snippet"]["title"] for i in ch.get("items", [])]
    print(f"保存した: {TOKEN}  チャンネル: {', '.join(names) or '(なし)'}")


def access_token():
    cid, secret = client()
    rt = json.loads(TOKEN.read_text())["refresh_token"]
    return post_form("https://oauth2.googleapis.com/token", {
        "client_id": cid, "client_secret": secret, "refresh_token": rt,
        "grant_type": "refresh_token"})["access_token"]


_TOKEN = None


def api(method, url, body=None, headers=None, raw=False):
    global _TOKEN
    _TOKEN = _TOKEN or access_token()
    h = {"Authorization": f"Bearer {_TOKEN}", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r if raw else json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {url.split('?')[0]} -> {e.code}: {e.read().decode()[:800]}")


def read_youtube_md(path):
    md = path.read_text()
    title = re.search(r"## タイトル\n\n(.+?)\n", md).group(1).strip()
    desc = md.split("## 概要欄\n\n", 1)[1].strip()
    for s in (title, desc):
        if "<" in s or ">" in s:
            raise SystemExit("タイトルと概要欄に < > は使えない")
    if len(title) > 100:
        raise SystemExit(f"タイトルが {len(title)} 字。100 字まで")
    return title, desc


def upload(name):
    out = ROOT / "data/video" / name
    rec = out / "youtube.json"
    if rec.exists():
        raise SystemExit(f"上げ済み: {rec.read_text()}")
    video, thumb = out / "video.mp4", out / "thumb.png"
    title, desc = read_youtube_md(ROOT / "kessannote/videos" / f"{name}.youtube.md")
    meta = {"snippet": {"title": title, "description": desc, "categoryId": CATEGORY,
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": False}}
    size = video.stat().st_size
    r = api("POST", "https://www.googleapis.com/upload/youtube/v3/videos"
                    "?uploadType=resumable&part=snippet,status",
            body=json.dumps(meta).encode(),
            headers={"Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
            raw=True)
    loc = r.headers["Location"]
    v = api("PUT", loc, body=video.read_bytes(), headers={"Content-Type": "video/mp4"})
    vid = v["id"]
    print(f"動画: https://youtu.be/{vid}  ({v['status']['privacyStatus']})")
    rec.write_text(json.dumps({"id": vid, "title": title}, ensure_ascii=False))
    if thumb.exists():
        set_thumb(name)


def set_thumb(name):
    """新しいチャンネルは電話番号の確認が済むまで 403 で弾かれる。動画は上がっているので、後でこれだけ流す。"""
    out = ROOT / "data/video" / name
    vid = json.loads((out / "youtube.json").read_text())["id"]
    api("POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}&uploadType=media",
        body=(out / "thumb.png").read_bytes(), headers={"Content-Type": "image/png"})
    print("サムネイル: 設定した")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "auth":
        auth()
    elif len(sys.argv) == 3 and sys.argv[1] == "upload":
        upload(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "thumb":
        set_thumb(sys.argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
