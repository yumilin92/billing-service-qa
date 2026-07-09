"""
Load-test SMOKE with Locust.

This is not a full performance benchmark — it's a quick "does the service stay
healthy under concurrent traffic?" check. Locust spawns many simulated users
that repeatedly hit the API; we watch that error rate stays at zero and
response times stay sane.

Run it (with the server already running on port 8000):

    locust -f tests/load/locustfile.py --host http://127.0.0.1:8000 \
           --headless -u 20 -r 5 -t 15s

  -u 20  = 20 concurrent users
  -r 5   = ramp up 5 users per second
  -t 15s = run for 15 seconds
"""
import random
from datetime import date, timedelta

from locust import HttpUser, between, task

DUE = (date.today() + timedelta(days=30)).isoformat()


class BillingUser(HttpUser):
    # Each simulated user waits 0.1–0.5s between actions (think time).
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Runs once when a simulated user starts: create a buyer with a large
        limit so invoice creation keeps succeeding during the run."""
        resp = self.client.post(
            "/buyers", json={"name": "Load Buyer", "credit_limit": 100_000_000}
        )
        self.buyer_id = resp.json()["id"]

    @task(3)  # weight 3: called most often
    def health(self):
        self.client.get("/health")

    @task(2)
    def create_invoice(self):
        self.client.post(
            "/invoices",
            json={"buyer_id": self.buyer_id, "amount": random.randint(100, 5_000), "due_date": DUE},
        )

    @task(1)
    def check_credit(self):
        self.client.get(f"/buyers/{self.buyer_id}/credit")
