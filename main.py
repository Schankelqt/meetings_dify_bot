from flask import Flask, request
import requests
from dotenv import dotenv_values
import json
from users import USERS  # Импортируем USERS из users.py

env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")
DIFY_API_KEY = env.get("DIFY_API_KEY")
DIFY_API_URL = env.get("DIFY_API_URL").rstrip('/')

app = Flask(__name__)

collected_answers = {}
conversation_ids = {}

CONFIRMATION_PHRASES = [
    "да", "да, всё верно", "да все верно", "всё верно", "все верно", 
    "подтверждаю", "подтверждаю всё", "подтверждаю вариант", 
    "всё так", "все так", "всё ок", "все ок", "ок", "окей", 
    "точно", "верно", "ага", "готов", "готова", "готово",
    "да, всё так", "да, подтверждаю", "да, отправляй", 
    "да, можно отправлять", "всё правильно", "все правильно", "абсолютно","✅"
]

def get_conversation_id(chat_id):
    url = f"{DIFY_API_URL}/conversations"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}"}
    params = {"user": str(chat_id)}
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        print(f"[Dify] get_conversation_id response for {chat_id}: {data}")
        if data.get("data") and len(data["data"]) > 0:
            return data["data"][0]["id"]
        else:
            print(f"[INFO] Нет активных разговоров для пользователя {chat_id}")
            return None
    except Exception as e:
        print(f"[ERROR] Ошибка при получении conversation_id для {chat_id}: {e}")
        return None

def remove_sum_and_above(text: str) -> str:
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'sum' in line.lower():
            return "\n".join(lines[i+1:]).strip()
    return text.strip()

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    print(f"✅ Webhook вызван с данными: {data}")

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]
        user_name = USERS.get(chat_id, "Неизвестный")

        conv_id = conversation_ids.get(chat_id)
        if not conv_id:
            conv_id = get_conversation_id(chat_id)
            if conv_id:
                conversation_ids[chat_id] = conv_id
            else:
                print(f"[INFO] conversation_id не найден, создаём новую сессию для {chat_id}")

        headers = {
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json"
        }

        def send_to_dify(payload):
            try:
                response = requests.post(f"{DIFY_API_URL}/chat-messages", headers=headers, json=payload)
                print(f"[Dify] HTTP Status: {response.status_code}")
                print(f"[Dify] Ответ от сервера: {response.text}")
                return response
            except Exception as e:
                print(f"[ERROR] Ошибка запроса к Dify: {e}")
                return None

        payload = {
            "inputs": {},
            "query": user_message,
            "response_mode": "blocking",
            "user": str(chat_id)
        }
        if conv_id:
            payload["conversation_id"] = conv_id

        response = send_to_dify(payload)

        if response is not None and response.status_code == 404:
            print(f"[INFO] Conversation ID не существует, создаём новую сессию для {chat_id}")
            payload.pop("conversation_id", None)
            response = send_to_dify(payload)
            if response is not None and response.status_code == 200:
                data = response.json()
                new_conv_id = data.get("conversation_id")
                if new_conv_id:
                    conversation_ids[chat_id] = new_conv_id
                    print(f"[INFO] Новая сессия создана с ID: {new_conv_id}")

        if response is not None and response.status_code == 200:
            answer_text = response.json().get("answer", "")

            if user_message.strip().lower() in CONFIRMATION_PHRASES and "sum" in answer_text.lower():
                cleaned_summary = remove_sum_and_above(answer_text)

                collected_answers[str(chat_id)] = {
                    "name": user_name,
                    "summary": cleaned_summary
                }
                with open("answers.json", "w", encoding="utf-8") as f:
                    json.dump(collected_answers, f, ensure_ascii=False, indent=2)

                reply = "✅ Спасибо за ответы! Отчёт будет отправлен руководителю."
            else:
                reply = answer_text
        else:
            reply = f"⚠️ Ошибка при обращении к Dify: {response.status_code if response else 'Нет ответа'}"

        send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            tg_resp = requests.post(send_url, json={"chat_id": chat_id, "text": reply})
            print(f"[Telegram API] Status: {tg_resp.status_code}, Response: {tg_resp.text}")
            tg_resp.raise_for_status()
        except Exception as e:
            print(f"[ERROR] Ошибка при отправке сообщения в Telegram: {e}")

    return "ok"

@app.route("/test", methods=["POST"])
def test_route():
    print("📨 /test был вызван!")
    data = request.get_json()
    print(f"📦 Данные из /test: {data}")
    return "OK"

if __name__ == "__main__":
    print(f"✅ TOKEN: {TELEGRAM_TOKEN}")
    print("🔍 Зарегистрированные маршруты:")
    print(app.url_map)
    app.run(host="0.0.0.0", port=5001)
