from flask import Flask, request
import requests
from dotenv import dotenv_values
import json

# 🌍 Загружаем переменные окружения
env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")
DIFY_API_KEY = env.get("DIFY_API_KEY")
DIFY_API_URL = env.get("DIFY_API_URL").rstrip('/')  # убираем лишний слеш в конце, если есть

app = Flask(__name__)

# 📍 Список сотрудников
USERS = {
    731869173: "Татьяна Воронкова",
    946740162: "Александр Зайцев",
    368455189: "Наталья Голощапова",
    949507228: "Марьяна Дмитриевская",
    220691670: "Алексей Хван"
}

# 📍 Руководитель
MANAGER_ID = 949507228

# 🗃 Хранилище собранных ответов (в памяти и в файле)
collected_answers = {}

# 💾 Хранилище conversation_id для каждого chat_id (в памяти)
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
            return data["data"][0]["id"]  # берем самый последний разговор
        else:
            return None
    except Exception as e:
        print(f"Ошибка при получении conversation_id для {chat_id}: {e}")
        return None

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    print("✅ Webhook вызван")
    data = request.get_json()
    print("📦 Данные:", data)

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]
        user_name = USERS.get(chat_id, "Неизвестный")

        # Получаем или создаём conversation_id
        conv_id = conversation_ids.get(chat_id)
        if not conv_id:
            conv_id = get_conversation_id(chat_id)
            if conv_id:
                conversation_ids[chat_id] = conv_id

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

        response = requests.post(DIFY_API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            answer_text = response.json().get("answer", "")
            if "sum" in answer_text.lower():  # если в ответе есть "sum"
                summary = answer_text
                collected_answers[chat_id] = {
                    "name": user_name,
                    "summary": summary
                }
                # Сохраняем итоговые ответы в файл
                with open("answers.json", "w", encoding="utf-8") as f:
                    json.dump(collected_answers, f, ensure_ascii=False, indent=2)

                reply = f"✅ Зафиксировал итог:\n{summary}"
            else:
                # Просто пересылаем ответ от Dify, чтобы диалог продолжался
                reply = answer_text
        else:
            reply = f"⚠️ Ошибка при обращении к Dify: {response.status_code}"

        # Отправляем ответ сотруднику в Telegram
        send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(send_url, json={"chat_id": chat_id, "text": reply})

    return "ok"

@app.route("/test", methods=["POST"])
def test_route():
    print("📨 /test был вызван!")
    data = request.get_json()
    print("📦 Данные из /test:", data)
    return "OK"

if __name__ == "__main__":
    print("✅ TOKEN:", TELEGRAM_TOKEN)
    print("🔍 Зарегистрированные маршруты:")
    print(app.url_map)
    app.run(host="0.0.0.0", port=5001)