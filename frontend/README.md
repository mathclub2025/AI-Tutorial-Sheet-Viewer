# AI-Tutorial-Sheet-Viewer - Frontend

Unified Next.js application containing both the **Student Practice Portal** and the **Admin Question Review & Ingestion Desk** for the Mathematics Club, VIT Chennai.

## Application Architecture & Routes

- **`/` & `/student`**: **Student Practice Portal**
  - Natural language topic search across tutorial sheets and PYQs.
  - Interactive chat interface with step-by-step solution reveals and formula tables.
  - Offline bookmarking, study projects, chat history, and JSON export.
  - Discreet "Admin Portal" access link inside the profile menu.
- **`/admin/upload`**: **Admin Question Sheet Upload Desk**
  - Dropzone for PDF and image question papers.
  - Academic metadata tagging (subject, sheet type, year, semester).
- **`/admin/review`**: **Admin Batch Review Dashboard**
  - Batch metrics, status filters (Pending, In Review, Completed), and search.
  - Question review, formula editing, difficulty calibration, and topic tagging.
- **`/admin/review/[batchId]`**: **Batch Detail & Question Inspector**

## Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env.local
```
- `NEXT_PUBLIC_API_URL`: *(Optional)* Base URL of the backend ingestion/search API. Leave empty to use the built-in mock question bank and local storage.

### 3. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the application.

### 4. Production Build & Type Check
```bash
npx tsc --noEmit
npm run build
```
