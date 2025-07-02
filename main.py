from flask import Flask, request
import requests
from dotenv import dotenv_values
import json

env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")
DIFY_API_KEY = env.get("DIFY_API_KEY")
DIFY_API_URL = env.get("DIFY_API_URL").rstrip('/')

app = Flask(__name__)

USERS = {
    731869173: "Татьяна Воронкова",
    946740162: "Александр Зайцев",
    368455189: "Наталья Голощапова",
    949507228: "Марьяна Дмитриевская",
    220691670: "Алексей Хван",
    775766895: "Кирилл Востриков",
    1010954244: "Константин Базаркин",
    398995895: "Антон Баронин",
    1038645944: "Андрей Часов",
    253240597: "Дмитрий Малютин"
}

MANAGER_ID = 949507228
collected_answers = {}
conversation_ids = {}

def get_conversation_id(chat_id):
    url = f"{DIFY_API_URL}/conversations"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}"}
    params = {"user": str(chat_id)}
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("data") and len(data["data"]) > 0:
            return data["data"][0]["id"]
        else:
            print(f"[INFO] Нет активных разговоров для пользователя {chat_id}")
            return None
    except Exception as e:
        print(f"[ERROR] Ошибка при получении conversation_id для {chat_id}: {e}")
        return None

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
        payload = {
            "inputs": {},
            "query": user_message,
            "response_mode": "blocking",
            "user": str(chat_id)
        }
        if conv_id:
            payload["conversation_id"] = conv_id

        try:
            response = requests.post(f"{DIFY_API_URL}/chat-messages", headers=headers, json=payload)
            if response.status_code == 200:
                answer_text = response.json().get("answer", "")

                if "sum" in answer_text.lower():
                    # Очищаем ответ, оставляя только от первого вхождения "sum" и далее
                    lower_answer = answer_text.lower()
                    idx = lower_answer.find("sum")
                    summary = answer_text[idx:]

                    collected_answers[chat_id] = {
                        "name": user_name,
                        "summary": summary
                    }
                    with open("answers.json", "w", encoding="utf-8") as f:
                        json.dump(collected_answers, f, ensure_ascii=False, indent=2)

                    reply = summary
                else:
                    reply = answer_text
            else:
                reply = f"⚠️ Ошибка при обращении к Dify: {response.status_code}"
        except Exception as e:
            reply = f"⚠️ Ошибка запроса к Dify: {e}"
            print(f"[ERROR] Ошибка запроса к Dify: {e}")

        send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            tg_resp = requests.post(send_url, json={"chat_id": chat_id, "text": reply})
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