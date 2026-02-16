# 🚂 Deployment Guide for Railway

This guide will help you deploy the **Universal Support Brain** to Railway from scratch.

## 📋 Prerequisites

1.  **GitHub Account**: Your code must be in a GitHub repository.
2.  **Railway Account**: Sign up at [railway.app](https://railway.app).
3.  **Database URL**: Railway provides this automatically when you add a plugin.

---

## 🛠 Step 1: Create Project & Database

1.  Go to your [Railway Dashboard](https://railway.app/dashboard).
2.  Click **"New Project"** -> **"Provision PostgreSQL"**.
3.  This will create a new project with a database.
4.  Click on the **PostgreSQL** card -> **Variables**.
5.  Copy the `DATABASE_URL` (e.g., `postgresql://postgres:password@roundhouse.proxy.rlwy.net:1234/railway`). You will need this later.

---

## 🐍 Step 2: Deploy Backend

1.  **Add Service**:
    *   Right-click on the canvas -> **"Create"** -> **"GitHub Repo"**.
    *   Select your repository.
2.  **Configure Service**:
    *   Click on the new Service card (it might be named after your repo).
    *   Go to **Settings** -> **Root Directory**.
    *   Change it to: `/backend`  *(Important!)*
3.  **Set Environment Variables**:
    *   Go to the **Variables** tab. Add the following:
    *   `DATABASE_URL`: *(Paste the value from Step 1)*
    *   `PORT`: `8000`
    *   `ADMIN_API_KEY`: `my-secret-admin-key-123` *(Change this to a secure random string!)*
    *   `ALLOWED_CORS_ORIGINS`: `*`
    *   `PINECONE_API_KEY`: *(Your Pinecone Key)*
    *   `AZURE_OPENAI_API_KEY`: *(Your Azure Key)*
    *   `AZURE_OPENAI_ENDPOINT`: *(Your Azure Endpoint)*
    *   `AZURE_OPENAI_API_VERSION`: `2024-02-15-preview`
    *   `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: `gpt-4o-mini`
    *   `GORGIAS_API_KEY`: *(Your Gorgias Key)*
    *   `GORGIAS_USERNAME`: *(Your Email)*
    *   `GORGIAS_BASE_URL`: *(Your Gorgias Base URL)*
    *   `APIFY_API_KEY`: *(Your Apify API Token)*
4.  **Set Start Command**:
    *   Go to **Settings** -> **Deploy** -> **Start Command**.
    *   Paste this exact command:
        ```bash
        alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT
        ```
    *   *Explanation:* This automatically runs your database migrations (`alembic upgrade head`) every time you deploy, ensuring your DB is always up to date.
5.  **Get Public URL**:
    *   Go to **Settings** -> **Networking**.
    *   Click **"Generate Domain"**.
    *   Copy this URL (e.g., `https://backend-production.up.railway.app`). This is your **Backend URL**.

---

## ⚛️ Step 3: Deploy Frontend

1.  **Add Service**:
    *   Right-click on the canvas -> **"Create"** -> **"GitHub Repo"** (Select the *same* repo again).
2.  **Configure Service**:
    *   Click the new Service card.
    *   Go to **Settings** -> **Root Directory**.
    *   Change it to: `/frontend` *(Important!)*
3.  **Set Environment Variables**:
    *   Go to **Variables**. Add the following:
    *   `NEXT_PUBLIC_API_URL`: *(Paste the Backend URL from Step 2)* **Do not add a trailing slash `/`**
    *   `NEXT_PUBLIC_API_KEY`: *(Paste the `ADMIN_API_KEY` you created in Step 2)*
4.  **Deploy**:
    *   Railway should automatically detect `package.json` and build your app.
    *   Once deployed, go to **Settings** -> **Networking** -> **Generate Domain**.
    *   Opens this URL to see your Frontend!

---

## 🔒 Security Post-Deployment

Once both are working:
1.  Copy your **Frontend Domain** (e.g., `https://frontend-production.up.railway.app`).
2.  Go back to your **Backend Service** -> **Variables**.
3.  Update `ALLOWED_CORS_ORIGINS` to match your Frontend Domain (remove the `*`).
4.  Redeploy the Backend.

Now your API is secure and only accepts requests from your Frontend!
