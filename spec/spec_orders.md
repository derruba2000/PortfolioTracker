You are absolutely right to call that out. Losing those quality-of-life UI features—like the dynamic price trend tags, the external links to Yahoo Finance, and the specific underlying math for `total_value` calculations—would be a massive step backward.

When refactoring a system, we must ensure all legacy business logic and visual aids are ported over to the new architecture.

Here is the fully rewritten, comprehensive blueprint containing all the Epics and User Stories. You can feed this directly to your AI to implement the entire system seamlessly.

---

### Epic 1: Database Schema & Migration (The Foundation)

**Description:** Implement the underlying database structure to separate Order Intent from Transaction Reality, ensuring existing ledger data is preserved.

* **User Story 1.1: Create the `orders` Table**
* **As a** backend system, **I need** an `orders` table **so that** I can track trade intent and lifecycle states.
* **Acceptance Criteria:** Create a table with fields: `id` (PK), `portfolio_id` (FK), `security_id` (FK, nullable for cash actions), `order_type` (BUY, SELL, DEPOSIT, WITHDRAW), `status` (PENDING, EXECUTED, CANCELLED), `target_quantity`, `target_price`, `target_cash_amount`, `created_at`, and `executed_at`.


* **User Story 1.2: Alter the `transactions` Table**
* **As a** backend system, **I need** to link transactions to the orders that generated them **so that** the ledger has an audit trail.
* **Acceptance Criteria:** Add an `order_id` (FK, nullable) column to the existing `transactions` table.


* **User Story 1.3: Legacy Data Migration Script**
* **As a** database admin, **I need** a migration script for existing transactions **so that** legacy data does not break the new system.
* **Acceptance Criteria:** Write a script that iterates through all current rows in the `transactions` table. For each row, automatically generate a completed `orders` row and link the new `order_id` back to the existing transaction.



---

### Epic 2: Orders UI & Management (The Command Center)

**Description:** Build the new Orders dashboard where users can queue, filter, and manage intents, retaining all the rich data visualization from the old UI.

* **User Story 2.1: Orders Dashboard View with Rich UI**
* **As a** user, **I want** an Orders tab displaying my trade intents with dynamic visual aids **so that** I have immediate context on the asset's performance.
* **Acceptance Criteria:** * Display a data table including: Date, Portfolio, Type, Asset/Ticker, Quantity, Price, and Status.
* **Yahoo Finance Link:** The Asset/Ticker must be clickable, opening the respective Yahoo Finance quote page in a new tab.
* **Trend Tags:** The current market price must be displayed alongside the order's target price, using dynamic green/red tags to instantly indicate the price trend (positive/negative).




* **User Story 2.2: Order Creation Form**
* **As a** user, **I want** to add new orders (Buy, Sell, Deposit, Withdraw) **so that** I can queue up actions for my portfolios.
* **Acceptance Criteria:** * Form includes dropdowns for Portfolio and Action Type.
* If Buy/Sell: Show Security search/dropdown, Target Quantity, and Target Limit Price.
* If Deposit/Withdraw: Hide Security field, show Target Cash Amount field.
* New orders default to `PENDING` status.




* **User Story 2.3: Orders Filtering & Sorting**
* **As a** user, **I want** to filter my orders **so that** I can easily find specific data.
* **Acceptance Criteria:** Add UI filters for Status (Pending/Executed/Cancelled), Portfolio Name, and Date Range.


* **User Story 2.4: Cancel Pending Orders**
* **As a** user, **I want** a "Cancel" button on Pending orders **so that** I can abort a trade before it hits the ledger.
* **Acceptance Criteria:** Clicking Cancel changes the order status to `CANCELLED` and guarantees no transactions are generated.



---

### Epic 3: The Execution Engine (Double-Entry & Math Logic)

**Description:** The core backend logic that transforms an "Executed" order into perfectly balanced double-entry transactions, porting over the strict legacy calculation rules.

* **User Story 3.1: Manual Order Execution**
* **As a** user, **I want** to manually mark pending orders as completed **so that** I can confirm a trade actually occurred at my broker.
* **Acceptance Criteria:** * UI includes a "Mark as Completed" button on pending orders.
* Prompts the user to input the *actual* execution quantity, *actual* execution price, and *actual* broker fees.
* Updates the order status to `EXECUTED` and sets the `executed_at` timestamp.




* **User Story 3.2: Double-Entry Transaction Generation & Total Value Calculation**
* **As a** backend system, **I need** to automatically generate ledger entries using strict legacy math rules when an order is executed **so that** my cash and asset balances remain perfectly accurate.
* **Acceptance Criteria:** * If DEPOSIT/WITHDRAW: Generate exactly ONE transaction row crediting/debiting the cash balance (`security_id` = NULL).
* If BUY/SELL: Generate TWO transaction rows linked to the same `order_id`.
* **Row 1 (Asset Leg):** Record the positive/negative quantity of the `security_id`.
* **Row 2 (Cash Leg):** Record the cash impact (`security_id` = NULL).
* **Legacy Math Rule (Total Value):** The system must calculate the `total_value` identically to the old transactions form. For a BUY: `(Quantity * Price) + Fees`. For a SELL: `(Quantity * Price) - Fees`. The cash leg must debit/credit this exact `total_value`.





---

### Epic 4: Transactions Ledger Refactor (The Read-Only View)

**Description:** Downgrade the existing Transactions tab from a data-entry screen to a strict, read-only financial ledger, preserving the rich UI features.

* **User Story 4.1: Convert Transactions to Rich Read-Only Ledger**
* **As a** user, **I want** my Transactions tab to act as a secure, read-only ledger with my familiar visual aids **so that** the financial record cannot be bypassed, while still being easy to read.
* **Acceptance Criteria:** * Remove all "Add", "Edit", and "Delete" buttons from the view.
* Display the `order_id` in the table to show the source of the transaction.
* **Yahoo Finance Link:** Ensure the Asset/Ticker remains a clickable hyperlink to Yahoo Finance.
* **Trend Tags:** Ensure the green/red price trend tags remain visible on the row.




* **User Story 4.2: Ledger Filtering**
* **As a** user, **I want** advanced filters on the ledger **so that** I can audit my portfolio's history.
* **Acceptance Criteria:** Provide filters by Portfolio, Date Range, Asset Class (including Cash), and Transaction Type.