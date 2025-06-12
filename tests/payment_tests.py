import requests
import json

base_url = 'http://127.0.0.1:5000/'


def get_pay_url_no_data():
    url = base_url + 'api/payments/pay-link'
    payloads = {
        'duration': 30,
        'amount': 500,
        'user_id': 1,
    }
    # response = requests.post(url, json=json.dumps(payloads))
    response = requests.post(url, json=payloads)
    if response.status_code == 200:
        data: dict = response.json()
        for i in data.items():
            print(i)

    else:
        print(response.status_code)
        print(response.text)


def send_payment_succeeded_notification():
    url = base_url + 'api/payments/success'
    payload = {
  "type" : "notification",
  "event" : "payment.succeeded",
  "object" : {
    "id" : "2fdbbbed-000f-5000-8000-15ffce5fd4ec",
    "status" : "succeeded",
    "amount" : {
      "value" : "500.00",
      "currency" : "RUB"
    },
    "income_amount" : {
      "value" : "482.50",
      "currency" : "RUB"
    },
    "description" : "Оплата подписки",
    "recipient" : {
      "account_id" : "1067539",
      "gateway_id" : "2434504"
    },
    "payment_method" : {
      "type" : "bank_card",
      "id" : "2fdbb9f9-000f-5000-b000-17126dfdbcf6",
      "saved" : True,
      "status" : "active",
      "title" : "Bank card *4444",
      "card" : {
        "first6" : "555555",
        "last4" : "4444",
        "expiry_year" : "2025",
        "expiry_month" : "12",
        "card_type" : "MasterCard",
        "card_product" : {
          "code" : "E"
        },
        "issuer_country" : "US"
      }
    },
    "captured_at" : "2025-06-11T16:00:46.692Z",
    "created_at" : "2025-06-11T16:00:45.769Z",
    "test" : True,
    "refunded_amount" : {
      "value" : "0.00",
      "currency" : "RUB"
    },
    "paid" : True,
    "refundable" : True,
    "metadata" : {
      "duration_days" : "30",
      "next_amount" : "500.0",
      "is_trial" : "0",
      "user_id" : "1",
      "cms_name" : "yookassa_sdk_python",
      "email" : "35253ixrv@vpnservice.local"
    },
    "authorization_details" : {
      "rrn" : "107831417172716",
      "auth_code" : "788337",
      "three_d_secure" : {
        "applied" : False,
        "method_completed" : False,
        "challenge_completed" : False
      }
    }
  }
}
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
    print("Status code:", response.status_code)
    print("Response text:", response.text)
    return response


if __name__ == '__main__':
    # get_pay_url_no_data()
    send_payment_succeeded_notification()



