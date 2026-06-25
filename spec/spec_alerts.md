

## Epic 7: Alerting Infrastructure & Environment Configuration

> **Description:** Extend the SQLite database to track alert states and configure the project environment to securely store Discord webhook credentials.

### Story 7.1: Discord Webhook Environment Configuration

* **User Story:** As an AI Developer Agent, I want to add Discord webhook configurations to the `.env` system so the app can securely transmit payloads.
* **Acceptance Criteria:**
* [ ] Add `DISCORD_WEBHOOK_URL` to the `.env.example` and validation logic.
* [ ] Throw a specific warning (but do not crash) if the webhook URL is missing, allowing the app to run without Discord if the user only wants UI alerts.



### Story 7.2: Alert Ledger Database Schema

* **User Story:** As an AI Developer Agent, I want to create a `portfolio_alerts` table in SQLite so the system can persistently track triggered alerts and their acknowledgment states.
* **Acceptance Criteria:**
* [ ] Create table `portfolio_alerts` with columns: `id`, `alert_hash` (VARCHAR, UNIQUE), `timestamp`, `alert_type` (e.g., 'PRICE_DROP', 'DRIFT'), `message`, `is_acknowledged` (BOOLEAN DEFAULT 0).
* [ ] Ensure the `alert_hash` has a unique constraint to prevent duplicate insertions for the same event.



---

## Epic 8: Background Monitoring & Detection Engine

> **Description:** Build the background processes that periodically evaluate portfolio states and market prices against user-defined thresholds.

### Story 8.1: Price Drop Detection Module

* **User Story:** As an AI Developer Agent, I want a module that calculates intraday or daily price drops against allowable limits (e.g., a **0.5%** abrupt drop) so the system can flag flash crashes.
* **Acceptance Criteria:**
* [ ] Implement a function to compare the latest extracted price of a security against its previous close or a user-defined trailing stop.
* [ ] Generate a detailed alert message string (e.g., *"🚨 VWRP.L dropped by 0.6%, exceeding the 0.5% threshold."*).



### Story 8.2: Portfolio Drift Detection Module

* **User Story:** As an AI Developer Agent, I want a module that compares current live allocations against target allocations so I am notified when structural rebalancing is required.
* **Acceptance Criteria:**
* [ ] Reuse the math from the Reconciliation layer (Epic 5) to calculate percentage drift.
* [ ] Trigger an alert condition if any asset class drifts beyond a predefined `.env` threshold (e.g., `DRIFT_TOLERANCE_PCT=5.0`).



### Story 8.3: Alert Hashing & Idempotency Engine

* **User Story:** As an AI Developer Agent, I want to cryptographically hash alert conditions before storing them so the system does not spam the database or Discord with the same active alert.
* **Acceptance Criteria:**
* [ ] Implement a hashing function (e.g., using `hashlib.sha256`) that concatenates the `alert_type`, `security_symbol`, and the `date`.
* [ ] Attempt to insert the alert into `portfolio_alerts`. If the `alert_hash` already exists and `is_acknowledged = 0`, gracefully ignore the duplicate.
* [ ] If the insert is successful (new hash), push the event to the Discord Dispatcher.



---

## Epic 9: Discord Notification Service

> **Description:** Create the outbound communication layer to format and push data to the Discord API.

### Story 9.1: Discord Webhook Dispatcher

* **User Story:** As an AI Developer Agent, I want a dedicated notification module that sends structured JSON payloads to Discord whenever a new alert hash is committed to the database.
* **Acceptance Criteria:**
* [ ] Use the `requests` library to POST messages to the `DISCORD_WEBHOOK_URL`.
* [ ] Format the Discord message using basic Discord Markdown (e.g., bolding tickers, using appropriate emoji for drift vs. price drops).
* [ ] Implement error handling (e.g., catching timeouts or `429 Too Many Requests` responses) without crashing the main background monitor.



---

## Epic 10: Gradio UI Alert Control Center

> **Description:** Add a dedicated interactive tab to the Gradio application for the user to monitor, filter, and acknowledge alerts.

### Story 10.1: "Alerts & Notifications" Gradio Tab

* **User Story:** As an AI Developer Agent, I want a new main tab in Gradio so the user can see all active and historical alerts queried from SQLite.
* **Acceptance Criteria:**
* [ ] Create a `gr.Tab("Alerts")`.
* [ ] Implement a `gr.Dataframe` that displays rows from `portfolio_alerts` where `is_acknowledged = 0`, sorted by timestamp descending.
* [ ] Add a toggle or separate table to view "Historical/Acknowledged" alerts.



### Story 10.2: Alert Acknowledgment Mechanism

* **User Story:** As an AI Developer Agent, I want an interactive way for the user to dismiss alerts in the UI, which updates the database and clears the state.
* **Acceptance Criteria:**
* [ ] Add a Gradio input field (e.g., `gr.Dropdown` or `gr.CheckboxGroup` loaded with active alert IDs) and an "Acknowledge Selected" button.
* [ ] When clicked, execute a SQL `UPDATE` statement setting `is_acknowledged = 1` for the selected hashes.
* [ ] Automatically refresh the active alerts dataframe in the UI to remove the dismissed items.



