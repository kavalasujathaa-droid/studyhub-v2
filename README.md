# StudyHub V2 — Multi-Admin, Multi-Tenant Educational Digital Library

StudyHub V2 is a production-oriented, multi-tenant educational digital library SaaS engineered for multiple independent administrators, each managing their own completely isolated academic institution, curriculum, student roster, and PDF document repository.

---

## 1. System Architecture & Tech Stack

```
[ Platform Owner ]       [ Administrator ]         [ Student ]
        |                       |                       |
        v                       v                       v
 +---------------------------------------------------------------+
 |                        Flask 3.x App                          |
 |            (Argon2id, Flask-Login, Flask-Limiter)             |
 +---------------------------------------------------------------+
 |           Strict Multi-Tenant Boundary Enforcement            |
 |         (Session-Derived tenant_id, IDOR Prevention)          |
 +-------------------------------+-------------------------------+
                                 |
        +------------------------+------------------------+
        |                                                 |
        v                                                 v
+-------------------------------+ +-------------------------------+
|     TiDB Cloud Starter        | |     Cloudflare R2 Storage     |
|   (MySQL Wire Compatible)     | |    (Private S3-Compatible)    |
| - Users & Tenants             | | - Presigned PUT Direct Upload |
| - Subjects & Titles           | | - Presigned GET Stream/View   |
| - PDF Metadata & Versions     | | - Magic Bytes Verification    |
| - Bookmarks & History         | | - 100 MB Limit / 9 GiB Safety |
+-------------------------------+ +-------------------------------+
```

### Exact Technology Stack
- **Backend Framework**: Python 3.12 / 3.11, Flask 3.1, Gunicorn 27.0
- **Database ORM & Migrations**: SQLAlchemy 2.1, Flask-Migrate 4.1 (Alembic)
- **Database Engine**: TiDB Cloud Starter (MySQL 8.0 protocol via PyMySQL with verified TLS)
- **Object Storage**: Cloudflare R2 (S3-compatible API via Boto3, private bucket, presigned URLs)
- **Authentication & Security**: Argon2id (`argon2-cffi`), Flask-Login, Flask-WTF (CSRF), Flask-Limiter
- **Frontend**: HTML5, CSS3, Bootstrap 5.3, Bootstrap Icons, Vanilla JavaScript (zero Node.js/React overhead)
- **Deployment Platform**: GitHub + Render Free Web Service (ephemeral container, stateless compute)

---

## 2. Critical Multi-Tenant Isolation Design

1. **Server-Side Session Tenancy**: Every administrator and student account is bound to exactly one `tenant_id`. Every single entity (`subjects`, `subject_titles`, `pdf_materials`, `pdf_versions`, `bookmarks`, `viewing_history`, `audit_logs`) has a `tenant_id` foreign key.
2. **Zero Trust for Frontend Input**: `tenant_id` is derived exclusively from `current_user.tenant_id` on the server. Client-submitted IDs or URL manipulations are rejected.
3. **Insecure Direct Object Reference (IDOR) Protection**: Foreign tenant queries return `404 Not Found` without disclosing whether the record exists in another tenant's library.
4. **Hierarchical Validation**: When adding a title or PDF, the backend verifies that both the subject and the title belong to the user's authenticated tenant.
5. **Platform Owner Boundary**: The Platform Owner manages platform statistics, tenant statuses, and administrator provisioning, but has **zero** automatic access to individual tenant private subjects, titles, PDFs, or students.

---

## 3. Cloudflare R2 Storage & Direct Presigned Upload

- **Private Bucket Only**: No public bucket policies. All reads and writes occur via presigned URLs.
- **Tenant Partitioning**: Keys follow `tenants/{tenant_id}/pdfs/{uuid}.pdf`.
- **Direct Browser-to-R2 Upload**: Browser requests a presigned PUT URL from Flask, streams the file directly to Cloudflare R2, and then calls Flask to finalize metadata.
- **PDF Signature Integrity**: During finalization, the backend reads the first 1024 bytes from R2 to verify the `%PDF-` magic byte signature. Non-PDF files or corrupted uploads are automatically deleted from R2.
- **Free-Tier Protection**: Enforces 100 MB per-file limit and a 9 GiB aggregate safety ceiling per tenant.

### Cloudflare R2 CORS Configuration
In the Cloudflare Dashboard, navigate to **R2 -> Your Bucket -> Settings -> CORS Policy** and apply:

```json
[
  {
    "AllowedOrigins": [
      "https://*.onrender.com",
      "http://localhost:5000",
      "http://127.0.0.1:5000"
    ],
    "AllowedMethods": [
      "GET",
      "PUT",
      "HEAD"
    ],
    "AllowedHeaders": [
      "Content-Type",
      "Content-Disposition"
    ],
    "ExposeHeaders": [
      "ETag"
    ],
    "MaxAgeSeconds": 3600
  }
]
```

---

## 4. TiDB Cloud Starter Setup

1. Sign up or log in at [TiDB Cloud](https://tidbcloud.com/).
2. Click **Create Cluster** and select **Starter (Free)**.
3. Set your cluster name (e.g. `studyhub-v2`) and choose your preferred cloud provider and region.
4. Set the monthly spending limit to **$0** (guarantees 100% free tier usage).
5. In the cluster overview, click **Connect**.
6. Select **General Client** / **PyMySQL** connection details:
   - **Host**: `gateway01.<region>.prod.aws.tidbcloud.com`
   - **Port**: `4000`
   - **User**: (e.g. `<username>.root`)
   - **Password**: Your cluster password
   - **Database**: `studyhub_v2`
7. Ensure TLS is required (enabled by default in PyMySQL).

---

## 5. Render Free Web Service Deployment

1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New -> Web Service** and connect your GitHub repository.
3. Render automatically detects `render.yaml`, or configure manually:
   - **Runtime**: Python 3
   - **Plan**: Free
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run_migrations.py && gunicorn --workers 2 --bind 0.0.0.0:$PORT wsgi:app`
   - **Health Check Path**: `/healthz`
4. Set the required Environment Variables in the Render Dashboard:

| Environment Variable | Description / Value |
| :--- | :--- |
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `FLASK_SECRET_KEY` | Strong random secret (generated automatically by Render) |
| `OWNER_BOOTSTRAP_TOKEN` | Unique secret token used once for first-time `/setup` |
| `TIDB_HOST` | TiDB Cloud gateway host (e.g. `gateway01...tidbcloud.com`) |
| `TIDB_PORT` | `4000` |
| `TIDB_USER` | TiDB Cloud username |
| `TIDB_PASSWORD` | TiDB Cloud password |
| `TIDB_DATABASE` | `studyhub_v2` |
| `R2_ACCOUNT_ID` | Cloudflare R2 Account ID |
| `R2_BUCKET_NAME` | Cloudflare R2 bucket name |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 S3 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 S3 Secret Access Key |

5. Deploy the service.
6. Once deployed, navigate to `https://<your-render-subdomain>.onrender.com/auth/setup` to perform the one-time Platform Owner bootstrap!

---

## 6. Local Development & Testing Guide

### Windows PowerShell Setup

```powershell
# 1. Clone repository and navigate to folder
cd d:\pdf

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Verify dependencies
pip install -r requirements.txt

# 4. Run automated test suite (27 comprehensive unit & isolation tests)
python -m pytest -v

# 5. Run database migrations locally
python run_migrations.py

# 6. Start local development server
python wsgi.py
```

### Initial Platform Setup Locally
1. Open `http://localhost:5000/auth/setup` in your browser.
2. Enter the configured `OWNER_BOOTSTRAP_TOKEN` (default for testing is in `.env.example`).
3. Set your Platform Owner master credentials. Setup is permanently locked once completed.
4. From the Owner Console, provision an institution Administrator + Tenant.
5. Sign in as the Administrator to enroll students, create subjects & titles, and upload PDF documents!
