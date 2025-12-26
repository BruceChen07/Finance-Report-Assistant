# Finance Report Assistant (FRA)

Finance Report Assistant is a powerful web application designed to convert complex PDF financial reports into clean, structured Markdown. It leverages **MinerU** and **Magic-PDF** to handle multi-column layouts, tables, and OCR for scanned documents.

## Key Features
- **High-Quality Conversion**: Handles complex layouts using Pipeline and VLM Transformer models.
- **Side-by-Side Preview**: Compare the original PDF with the converted Markdown in real-time.
- **OCR Support**: Built-in support for scanned documents.
- **ModelScope Integration**: Optimized for faster model downloads in various network environments.
- **Secure Authentication**: Simple JWT-based login system.
- **Job Management**: Track conversion progress, view history, and automatic cleanup of old files.

## Tech Stack
- **Frontend**: React (Vite), Material UI (MUI), React Router.
- **Backend**: FastAPI (Python), Uvicorn.
- **Core Engine**: MinerU, Magic-PDF.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js (for frontend development/build)
- NVIDIA GPU (Optional but recommended for VLM models)

### Backend Setup
1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd finance-report-assistant
   ```

2. **Create a virtual environment and install dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and adjust settings:
   ```bash
   cp .env.example .env
   ```

4. **Download Models**:
   Recommended to run manually before first use:
   ```bash
   .\.venv\Scripts\mineru-models-download.exe
   ```

5. **Start the Server**:
   ```bash
   python src/main.py --serve
   ```

### Frontend Setup
1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```
2. **Install dependencies**:
   ```bash
   npm install
   ```
3. **Build the production bundle**:
   ```bash
   npm run build
   ```
   *Note: The FastAPI backend serves the built frontend from `frontend/dist` by default.*

---

## Configuration (`.env`)
- `FRA_PORT`: Server port (default: 8000)
- `FRA_USERNAME`/`FRA_PASSWORD`: Initial login credentials.
- `FRA_USE_MODELSCOPE`: Set to `True` for faster downloads in China.
- `FRA_JOB_TTL_HOURS`: History retention period (default: 24h).

---

## License
[MIT License](LICENSE)
