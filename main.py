from flask import Flask, request
import requests
from dotenv import dotenv_values
import json

# 🌍 Загружаем переменные окружения
env = dotenv_values(".env")
TELEGRAM_TOKEN = env.get("TELEGRAM_TOKEN")
DIFY_API_KEY = env.get("DIFY_API_KEY")
DIFY_API_URL = env.get("DIFY_API_URL")

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

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    print("✅ Webhook вызван")
    data = request.get_json()
    print("📦 Данные:", data)

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]
        user_name = USERS.get(chat_id, "Неизвестный")

        # Отправка в Dify
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

        response = requests.post(DIFY_API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            summary = response.json().get("answer", "❓ Нет ответа от Dify")
            collected_answers[chat_id] = {
                "name": user_name,
                "raw": user_message,
                "summary": summary
            }

            # ✅ Сохраняем ответы в файл
            with open("answers.json", "w", encoding="utf-8") as f:
                json.dump(collected_answers, f, ensure_ascii=False, indent=2)

            reply = f"✅ Спасибо! Я зафиксировал твой ответ.\n\n🧠 Резюме:\n{summary}"
        else:
            print("⛔ Ошибка от Dify:", response.status_code, response.text)
            reply = f"⚠️ Ошибка при обращении к Dify: {response.status_code}"

        # Ответ сотруднику в Telegram
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