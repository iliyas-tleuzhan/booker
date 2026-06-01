from app.telegram_bot import send_message


if __name__ == "__main__":
    message_id = send_message("HKU booking agent Telegram test message.")
    print(f"Sent Telegram message id: {message_id}")

