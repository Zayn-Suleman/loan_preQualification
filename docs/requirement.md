# Functional Scope Document: Loan Prequalification Service

## 1. Project Objective

To design, build, and test a "Loan Prequalification Service" as a set of event-driven microservices.

The project will demonstrate a practical understanding of building a RESTful API, database interaction, asynchronous processing with a message broker (Kafka), and implementing a conceptual CI/CD pipeline for code quality.

## 2. Business Context (Indian Financial Market)

In the fast-growing Indian credit market, lenders (Banks and NBFCs) need to provide instant, high-level decisions on loan eligibility to capture new customers.

This "prequalification" step is not a final approval but a quick check to see if an applicant meets the basic criteria.

This service will simulate this process by:

1.  Accepting a minimal loan application (with a PAN Number).
2.  Asynchronously simulating a CIBIL score check.
3.  Applying business rules to make a prequalification decision.

This decoupled, event-driven architecture ensures the user-facing API is fast and resilient, while the complex processing happens reliably in the background.

## 3. Functional Scope

| Feature | In Scope (What we will build) | Out of Scope (What we will not build) |
| :--- | :--- | :--- |
| **API** | A RESTful API to submit an application and check its status. | A full Ul/front-end for the application. |
| **Data** | Store application status and key details (PAN, income, amount) in a PostgreSQL DB. | Storing full personal identification data (Aadhaar, address, etc.) |
| **Credit Check** | A simulated CIBIL score service based on PAN and income. | Actual integration with a credit bureau (e.g., CIBIL, Experian). |
| **Processing** | Asynchronous, event-driven processing using Kafka. | Synchronous, blocking request processing. |
| **Security** | Basic data validation (Pydantic). | Authentication (e.g., OAuth2, JWT) or user management. |
| **CI/CD** | A local, conceptual pipeline using pre-commit, pytest, and a Makefile to automate linting, formatting, and testing. | A full, deployed CI/CD pipeline (e.g., to AWS, GCP) or any cloud infrastructure setup. |

## 4. High-Level Design

The system will consist of three independent Python services, one database, and one message broker, all orchestrated locally using docker-compose.

**Architecture Flow:**

1.  User POSTs a JSON application to the **API Service**.
2.  **API Service**:
    a. Validates the data.
    b. Saves the application to the PostgreSQL DB with status: `PENDING`.
    c. Returns a `202 Accepted` response with the `application_id`.
    d. Publishes a message to the `loan_applications_submitted` Kafka topic.
3.  **Credit Service (Consumer)**:
    a. Consumes the message from `loan_applications_submitted`.
    b. Simulates a CIBIL score based on the `pan_number` and `monthly_income`.
    c. Publishes a new message to the `credit_reports_generated` Kafka topic with the `application_id` and the `cibil_score`.
4.  **Decision Service (Consumer)**:
    a. Consumes the message from `credit_reports_generated`.
    b. Applies business rules (e.g., score + income-to-loan ratio).
    c. Updates the application in the PostgreSQL DB with the final status (`PRE_APPROVED`, `REJECTED`, `MANUAL_REVIEW`).
5.  User GETs the status from the **API Service**, which now reads the final status from the database.

## 5. Core Data Model (PostgreSQL)

**applications Table**

| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Primary Key | Unique identifier for the application. |
| `pan_number` | VARCHAR(10) | Not Null | Applicant's PAN. |
| `applicant_name` | VARCHAR(255) | | |
| `monthly_income_inr` | DECIMAL(12, 2) | Not Null | Applicant's gross monthly income. |
| `loan_amount_inr` | DECIMAL(12, 2) | Not Null | Requested loan amount. |
| `loan_type` | VARCHAR(20) | | e.g., "PERSONAL", "HOME", "AUTO" |
| `status` | VARCHAR(20) | Not Null | PENDING, PRE_APPROVED, REJECTED, MANUAL_REVIEW |
| `cibil_score` | INTEGER | Nullable | The simulated CIBIL score (300-900). |
| `created_at` | TIMESTAMP | Default: NOW() | |
| `updated_at` | TIMESTAMP | Default: NOW() | |

## 6. Service & Logic Definitions

### A. prequal-api (FastAPI)

* **Endpoint:** `POST /applications`
    * **Request Body:** `{ "pan_number": "...", "applicant_name": "...", "monthly_income_inr": 50000, "loan_amount_inr": 200000, "loan_type": "PERSONAL" }`
    * **Success Response (202):** `{ "application_id": "...", "status": "PENDING" }`
* **Endpoint:** `GET /applications/{application_id}/status`
    * **Success Response (200):** `{ "application_id": "...", "status": "PRE_APPROVED" }`

### B. credit-service (Kafka Consumer)

* **Subscribes to:** `loan_applications_submitted`
* **Publishes to:** `credit_reports_generated`
* **Business Logic (CIBIL Simulation):**
    * `pan_number` "ABCDE1234F" (Test PAN 1) -> `cibil_score`: 790
    * `pan_number` "FGHIJ5678K" (Test PAN 2) -> `cibil_score`: 610
    * **Default Logic (for all others):**
        * Start with `base_score`: 650
        * If `monthly_income_inr` > 75000: + 40 points
        * If `monthly_income_inr` < 30000: - 20 points
        * If `loan_type` == "PERSONAL": - 10 points (unsecured)
        * If `loan_type` == "HOME": + 10 points (secured)
        * Add a small random value (-5 to +5) to make it seem realistic.
        * Ensure the final score is capped between 300 and 900.

### C. decision-service (Kafka Consumer)

* **Subscribes to:** `credit_reports_generated`
* **Logic (Decision Engine):**
    * Reads message: `{ "application_id": "...", "cibil_score": 790,... (all other app data) }`
    * **Applies rules:**
        1.  If `cibil_score` < 650: `status` = `REJECTED` (High Risk)
        2.  If `cibil_score` >= 650 AND `monthly_income_inr` > (`loan_amount_inr` / 48) (i.e., income is sufficient for a 4-year loan EMI): `status` = `PRE_APPROVED`
        3.  If `cibil_score` >= 650 AND `monthly_income_inr` <= (`loan_amount_inr` / 48): `status` = `MANUAL_REVIEW` (Good score, but income ratio is tight)
* **Action:** Updates the `applications` table in PostgreSQL with the new `status` and the received `cibil_score`.

## 7. Local CI/CD Scope

* **Tools:** Poetry, Docker Compose, pre-commit, pytest, Makefile.
* **pre-commit Hooks:** Automatically run Ruff (lint) and Black (format) on every `git commit`.
* **pytest:** Unit tests must be written for all business logic (CIBIL simulation, decision rules) and API endpoints.
* **Makefile:** A Makefile will provide simple commands (`make lint`, `make test`, `make run-local`) to standardize the developer experience.

## User Stories & Acceptance Criteria

### Story 1: Submitting an Application

* **As an** API user (the applicant)
* **I want to** submit my loan prequalification application
* **So that** I can get it processed and receive an `application_id` for tracking.

**AC 1.1:**
**GIVEN** the `prequal-api` is running
**WHEN** I send a POST request to `/applications` with valid JSON (including `pan_number`, `monthly_income_inr`, `loan_amount_inr`)
**THEN** I receive a `202 Accepted` HTTP status code.

**AC 1.2:**
**GIVEN** AC 1.1
**WHEN** I check the response body
**THEN** it contains the new `application_id` and a `status` of "PENDING".

**AC 1.3:**
**GIVEN** AC 1.1
**WHEN** I inspect the `applications` table in the database
**THEN** a new row exists with my `application_id` and `status` "PENDING".

**AC 1.4:**
**GIVEN** AC 1.1
**WHEN** I inspect the `loan_applications_submitted` Kafka topic
**THEN** a new message exists containing the application details.

**AC 1.5:**
**GIVEN** the `prequal-api` is running
**WHEN** I send a POST request to `/applications` with missing `pan_number`
**THEN** I receive a `422 Unprocessable Entity` status code and a clear error message.

### Story 2: Checking Application Status

* **As an** API user (the applicant)
* **I want to** check the status of my submitted application
* **So that** I know the final prequalification decision.

**AC 2.1:**
**GIVEN** my application (`app-123`) has a `status` of "PENDING" in the database
**WHEN** I send a GET request to `/applications/app-123/status`
**THEN** I receive a `200 OK` response with `{ "application_id": "app-123", "status": "PENDING" }`.

**AC 2.2:**
**GIVEN** my application (`app-123`) has been processed and its `status` is "PRE_APPROVED" in the database
**WHEN** I send a GET request to `/applications/app-123/status`
**THEN** I receive a `200 OK` response with `{ "application_id": "app-1S23", "status": "PRE_APPROVED" }`.

### Story 3: Processing the CIBIL Score

* **As the** Credit Service
* **I want to** consume new applications and simulate a CIBIL score
* **So that** the decision-making process can begin.

**AC 3.1:**
**GIVEN** a message for a "standard" application is on the `loan_applications_submitted` topic
**WHEN** the `credit-service` consumes it
**THEN** it publishes a new message to the `credit_reports_generated` topic containing the `application_id` and a calculated `cibil_score` between 300-900.

**AC 3.2:**
**GIVEN** a message with `pan_number` "ABCDE1234F" is on the `loan_applications_submitted` topic
**WHEN** the `credit-service` consumes it
**THEN** it publishes a message with `cibil_score`: 790.

### Story 4: Making a Prequalification Decision

* **As the** Decision Service
* **I want to** consume credit reports and apply business rules
* **So that** a final decision is made and recorded.

**AC 4.1:**
**GIVEN** a message is on `credit_reports_generated` with `cibil_score`: 790 and a "sufficient" income ratio
**WHEN** the `decision-service` consumes it
**THEN** the corresponding application in the `applications` table is updated to `status`: `PRE_APPROVED` and `cibil_score`: 790.

**AC 4.2:**
**GIVEN** a message is on `credit_reports_generated` with `cibil_score`: 610
**WHEN** the `decision-service` consumes it
**THEN** the corresponding application in the `applications` table is updated to `status`: `REJECTED` and `cibil_score`: 610.

**AC 4.3:**
**GIVEN** a message is on `credit_reports_generated` with `cibil_score`: 750 but an "insufficient" income ratio
**WHEN** the `decision-service` consumes it
**THEN** the corresponding application in the `applications` table is updated to `status`: `MANUAL_REVIEW` and `cibil_score`: 750.

### Story 5: Ensuring Code Quality (Developer CI)

* **As a** Developer
* **I want to** my code to be automatically linted, formatted, and tested locally
* **So that** I can ensure high quality and prevent bugs before pushing my code.

**AC 5.1:**
**GIVEN** I have configured `pre-commit`
**WHEN** I try to `git commit` code that is poorly formatted (does not pass Black)
**THEN** my commit is rejected, and Black automatically formats the code for me.

**AC 5.2:**
**GIVEN** I have made a logic change
**WHEN** I run `make test`
**THEN** `pytest` runs all unit tests for the API, credit, and decision services, and all tests pass./
