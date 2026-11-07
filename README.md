# RetailMind AI

A local retail business intelligence application with retrieval-grounded conversational analytics. Includes a synthetic dataset, Streamlit dashboard, CSV/XLSX ingestion, SQLite storage, Plotly charts, and customer segmentation. No API key is required.

## Vercel web version

Live application: https://retailmind-ai-zeta.vercel.app

### Dashboard login, registration and logout

The deployed web dashboard requires a username and password. Run `python scripts/configure_auth.py` once to create an `admin` account and random password. Its credentials are written to the git-ignored `LOGIN_CREDENTIALS.txt`; secrets and the bcrypt password hash are stored in the git-ignored `.env`. For Vercel, run `python scripts/push_auth_env.py` after preparing/linking `.vercel-deploy`, then redeploy. The script sends values through stdin and stores them as Vercel secrets, without printing values. Never publish the credential file or `.env`.

The login page is `/login.html`. Every business API action requires a server-verified session; the public GET health endpoint remains available. Successful login sets an eight-hour signed `HttpOnly`, `SameSite=Strict`, `Secure` cookie on Vercel. Passwords use bcrypt. The browser displays the account name and a **Log out** button; logout expires the cookie and returns to login. Sessions are revalidated on refresh/history restoration. Cross-origin POST requests are rejected. Failed sign-ins are throttled per function instance; this is not a distributed account lockout.

The login page has **Login** and **Create account** tabs. Both forms contain only **username and password**, then open the dashboard. The dashboard header also provides **Create account** and **Log out** controls. There are no username-format, minimum-length, or password-complexity rules; both fields must be nonempty. Usernames are trimmed, normalized to lowercase, and must be unique. New passwords are hashed in full with SHA-256, base64 encoded, then bcrypt hashed, supporting passwords beyond bcrypt's native 72-byte limit. Existing bcrypt accounts remain compatible. Sessions use fixed-size account identifiers so long usernames do not exceed cookie limits. Duplicate registrations cannot overwrite existing accounts; the configured admin username is reserved. Normal HTTP request size limits still apply.

Registered accounts persist in a **private Vercel Blob store** in production, using immutable per-user records with bcrypt hashes and atomic no-overwrite writes. The Vercel Python SDK authenticates using the store's connected credentials/OIDC; no storage secrets enter frontend code. For another Vercel project, create/connect private storage with `vercel blob create-store retailmind-accounts --access private --yes --environment production --cwd .vercel-deploy`. Local web development uses `data/accounts.db`, overridable with `AUTH_DATABASE_PATH`. Registration and login share a per-function attempt throttle. No email verification or password recovery is implemented; the form uses usernames rather than claiming verified email identities.

Logout clears the session from that browser. Signed sessions have no server-side revocation list: a previously stolen cookie remains valid until its eight-hour expiry or until the admin password hash/session secret changes. Changing either invalidates all existing sessions. Browser datasets are scoped to the account ID; older unowned datasets are not automatically assigned. Browser storage is not encrypted. Account credentials work across devices, while uploaded datasets remain browser-local. The original local Streamlit UI is unchanged.

The `web/` directory provides a responsive HTML/CSS/JavaScript frontend connected to the same Python analytics, retrieval, and answer engine through a stateless Vercel function. It includes all five workspace sections. This version does not run Streamlit on Vercel.

Uploaded datasets persist in **IndexedDB in the current browser**, rather than a shared SQLite file on a server. Each analysis request sends the dataset to the Python API. Demo data is generated on the backend. Browser data is not synchronized across devices and can be removed by clearing browser storage. The local Streamlit version retains SQLite persistence.

Web limits: 10,000 rows, 2.5 MB raw file uploads, and 4 MB JSON requests. Cleaned datasets above 3.6 MB are rejected before saving. CSV/XLSX uploads support schema validation, duplicates, rejection reports, Excel worksheet selection, preview, and browser persistence. CSV exports escape formula-like strings. The API never stores uploaded retail datasets in shared server files; requests require an authenticated account. Dashboard filters scope every backend calculation. Sentence Transformers models are not bundled for deployment; retrieval defaults to TF-IDF.

Run the web version locally:

```powershell
python -m pip install -r web/requirements.txt
python scripts/serve_web.py
```

Open http://localhost:3000. To prepare and deploy a clean web-only build:

```powershell
python scripts/prepare_vercel.py
npx vercel deploy .vercel-deploy --prod --yes
```

The preparation script copies only `web/` and `retailmind/` into `.vercel-deploy/`, leaving local databases, uploads, test caches, and local dependencies out of the deployment. Vercel uses Python 3.12. The health endpoint is `GET /api/index`; analytics, question answering, uploads, and customer segmentation use `POST /api/index`. Configure the Vercel project from this prepared directory, not the root Streamlit directory.

Additional web tests cover API health, synthetic data, filtered totals and answers, customer analysis, CSV/XLSX upload, and data isolation.

## Run locally

Use Python **3.11 or 3.12** for the broadest optional model compatibility. Core functionality is also tested with the available Python 3.14 environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the localhost address printed by Streamlit (usually http://localhost:8501). On first run, 5,000 reproducible synthetic records are saved to `data/retailmind.db`. Monetary examples use INR; set `currency` in `config.yaml` for the display label. Uploaded values are not converted between currencies.

## Workspace

- **Overview:** revenue, profit, orders, average order value, daily/weekly/monthly charts, category mix, store ranking, and CSV export.
- **Ask RetailMind:** twelve suggested questions, session conversation history, deterministic grounded answers, aggregate supporting tables, retrieved sources, and inspectable SQL.
- **Products & stores:** unit demand, sales, profitability, regional comparison, and trailing-period product changes.
- **Customers:** purchase frequency, spending, repeat rates, and K-Means clusters using frequency, spend, and recency.
- **Data studio:** preview CSV/XLSX worksheets, validate schema, clean duplicates, quarantine invalid financial records, download rejected rows, save datasets, and generate new demo data.

Sidebar filters apply to analytics and conversational results. Each dataset remains separate. Conversation history is scoped to the exact filtered data and stored only for the current Streamlit session.

## Input format and cleaning

Download a CSV template in Data studio. Required columns:

```text
transaction_id,date,store_id,product_id,category,product_name,quantity,unit_price,total_sales,discount,customer_id,region,payment_method,profit
```

Column headers are normalized to snake case; `product_category` is accepted as `category`. Dates must be parseable. Use fractional discounts (0.10 for 10%). Quantity must be positive; unit price and revenue nonnegative. Negative profit is allowed. Exact duplicate rows are removed; invalid dates or required numeric values are quarantined. Missing descriptive values become `Unknown`. Financial values are never imputed or silently recalculated. Transaction IDs may repeat for multiple line items; order counts use distinct IDs. Uploads should use a consistent currency. CSV output may contain original uploaded strings; treat untrusted exports as data when opening in spreadsheet software.

## Retrieval and grounding

1. Validated records are stored in SQLite using SQLAlchemy.
2. Selected records and category summaries become documents with dataset, store, date, category, and record metadata.
3. Documents are chunked with overlap, then embedded and indexed locally.
4. Default retrieval uses sparse TF-IDF vectors and cosine dot products. This is lexical vector retrieval, with no model downloads.
5. Optional Sentence Transformers embeddings provide semantic search using the same local cosine index.
6. Retrieval occurs before intent handling. Supported intents map to fixed analytical plans; Pandas computes totals and trends, while SQL performs grouped queries on an in-memory copy of the filtered scope.
7. Deterministic templates render only calculated values, supporting tables, source examples, caveats, and suggested actions.

There is no generative language model bundled: this implements the brief's deterministic fallback. Arbitrary conversational intent and contextual follow-up interpretation are not supported. Source examples are contextual evidence, not an exhaustive basis for aggregate totals; totals always use the whole selected scope. Unknown intents return an insufficient-support response.

### Optional semantic embeddings

```powershell
python -m pip install -r requirements-embeddings.txt
Copy-Item .env.example .env
```

Set `EMBEDDING_MODEL_PATH` to an existing local Sentence Transformers model directory, then restart. Only local models are loaded; no paid services or automatic model downloads. Failed/unavailable model loading falls back to TF-IDF. FAISS is unnecessary for the small local datasets; the vector index uses scikit-learn/NumPy.

## Safety and limitations

The assistant never executes generated Python or arbitrary model SQL. Its SQL comes from trusted intent templates, with bound parameters for limits. Database query access accepts single SELECT statements only, opens SQLite in read-only mode, enables query-only enforcement, and applies an execution budget. Dataset names are bound parameters. Monetary records are not inferred from retrieved samples.

This is a local single-user portfolio application, without authentication or tenant isolation. Do not expose the development server publicly or use it for sensitive production data. Bcrypt is included in the requested dependencies but login is not enabled: the supplied brief does not specify accounts. SQLite stores files locally and the optional model also runs locally.

Inventory suggestions are demand-based reviews, not stockout detection or reorder quantities. Causes of revenue decline cannot be established from transaction data alone. Trailing-period comparisons may contain incomplete periods; missing daily dates are treated as zero observed sales, not evidence of store closure. K-Means cluster numbers are descriptive identifiers. Typical intended scale is up to 50,000 records; larger uploads can be slow because indexing is in memory. The supplied brief ends mid-sentence in the inventory section; implementation covers the visible requirements.

## Validation

```powershell
python -m pytest -q
```

Tests cover cleaning/quarantine, parameterized SQL and mutation rejection, exact aggregate answers, retrieval source metadata, segmentation, and rendering/navigation through all five Streamlit pages including question submission.

## Layout

```text
app.py                    Streamlit interface and filter/session orchestration
retailmind/data.py        Synthetic generator, cleaning, SQLite persistence
retailmind/analytics.py   Metrics, time series, segmentation, product changes
retailmind/rag.py         Documents, chunks, local vectors, retrieval metadata
retailmind/assistant.py   Intent plans, read-only SQL, grounded answer templates
tests/                    Engine and Streamlit integration tests
config.yaml               Demo size and currency configuration
```
