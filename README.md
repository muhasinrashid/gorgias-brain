# Universal Support Brain - Technical Manifest

## Overview
Universal Support Brain is a B2B SaaS RAG integration designed to provide intelligent support responses by leveraging historical data from Gorgias and BigCommerce. It uses a Retrieval-Augmented Generation (RAG) approach to synthesize answers.

## Architecture

### Tech Stack
- **Frontend**: Next.js (App Router)
- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (Supabase/RDS)
- **Vector DB**: Pinecone (Serverless)
- **Infrastructure**: Docker for local development (Postgres, Redis)

### Core Components
- **Adapter Pattern**: Used to ensure platform-agnostic interactions with CRM (Gorgias) and E-commerce (BigCommerce) providers.

### Data Flow

1.  **Ingestion**:
    - **Gorgias Webhook**: Receives ticket creation or update events.
    - **BigCommerce Webhook** (Future): Receives order/customer updates.

2.  **Processing**:
    - **PII Scrubber**: Sanitizes incoming data to remove Personally Identifiable Information before storage/processing.
    - **Embedding Generation**: Converts sanitized text into vector embeddings using OpenAI models.

3.  **Storage**:
    - **Pinecone**: Stores vector embeddings for fast retrieval.
    - **PostgreSQL**: Stores metadata, raw (sanitized) records, and system configuration.

4.  **Synthesis**:
    - **Query**: System receives a user query or support context.
    - **Retrieval**: Fetches relevant context from Pinecone.
    - **LLM Synthesis**: Generates a response using the retrieved context and an LLM (e.g., GPT-4).

## Monorepo Structure

- `/backend`: FastAPI application handling API requests, webhooks, and background tasks.
- `/frontend`: Next.js application for the dashboard and configuration UI.
- `/shared`: Shared schemas and utilities.

## Setup

1.  **Prerequisites**:
    - Docker & Docker Compose
    - Node.js & npm
    - Python 3.11+

2.  **Installation**:
    ```bash
    # Backend
    cd backend
    pip install -r requirements.txt

    # Frontend
    cd frontend
    npm install
    ```

3.  **Running Locally**:
    ```bash
    docker-compose up -d
    # Start backend
    cd backend && uvicorn main:app --reload
    # Start frontend
    cd frontend && npm run dev
    ```
