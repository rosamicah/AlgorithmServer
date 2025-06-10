# Algorithm Server

## What is this?
A cloud API to process property Excel/CSV files and return enhanced real estate data.

## How to deploy

This application is designed to be deployed on Render.com as a web service using Docker.

1.  **Connect your Git Repository to Render:**
    *   Create a new "Web Service" on Render.
    *   Connect the Git repository containing this application.

2.  **Deployment Configuration:**
    *   **Runtime:** Select "Docker". Render should automatically detect the `Dockerfile` in your repository.
    *   **Build Command:** This is handled by the `Dockerfile` (typically `pip install -r requirements.txt`).
    *   **Start Command:** Render will use the `CMD` instruction from the `Dockerfile`. Ensure your `Dockerfile` has:
        `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT"]`
    *   **Instance Type:** Choose an appropriate instance type based on your expected load.
    *   **Health Check Path:** You can set this to `/` or a specific health check endpoint if you create one later. For now, `/` should suffice once the service is up.

3.  **Deploy:**
    *   Click "Create Web Service". Render will build the Docker image and deploy your application.
    *   Once deployed, Render will provide you with a URL for your service (e.g., `https://your-app-name.onrender.com`).

## How to use the API

Once deployed, the API will have one endpoint:

*   **POST `/process/`**
    *   **Purpose:** Accepts a CSV or Excel file, processes it using the defined business logic, and returns the processed data as a downloadable Excel file.
    *   **Request:**
        *   Method: `POST`
        *   Body: `multipart/form-data`
        *   Field: `file` (this should be the uploaded CSV or Excel file)
    *   **Response:**
        *   On success: An Excel file (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) named `processed_<original_filename>`.
        *   On error: A JSON object with an "error" key.

**Example using `curl`:**

```bash
curl -X POST -F "file=@/path/to/your/file.xlsx" https://your-app-name.onrender.com/process/ -o processed_output.xlsx
```
Replace `/path/to/your/file.xlsx` with the actual path to your input file and `https://your-app-name.onrender.com` with your actual Render service URL.
