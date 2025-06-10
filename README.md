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
    *   **Start Command:** When using Docker, Render typically uses the `CMD` instruction from your `Dockerfile`. However, if the "Start Command" field in the Render dashboard *cannot* be left blank, you should enter the command directly (without the `CMD` keyword from the Dockerfile syntax). For this project, use:
        `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
        The `Dockerfile` also specifies this as its default `CMD`, but providing it in the Render UI will ensure it's used if Render's policies require the field to be filled.
    *   **Instance Type:** Choose an appropriate instance type based on your expected load.
    *   **Health Check Path:** You can set this to `/` or a specific health check endpoint if you create one later. For now, `/` should suffice once the service is up.

3.  **Deploy:**
    *   Click "Create Web Service". Render will build the Docker image and deploy your application.
    *   Once deployed, Render will provide you with a URL for your service (e.g., `https://your-app-name.onrender.com`).

## Web Interface

The application provides an interactive web interface for uploading files directly through your browser.

1.  Navigate to the root URL of your deployed service (e.g., `https://your-app-name.onrender.com/`).
2.  You will see a page titled "Upload Property Data File".
3.  Click the "Choose file" button and select an Excel (.xls, .xlsx) or CSV (.csv) file from your computer.
4.  Click the "Upload and Process" button.
    *   An upload progress bar will show the file being sent to the server.
    *   Once uploaded, a status area will display a message like "Upload complete. Server is now processing the file...".
    *   The progress bar will then reset and fill up in stages to visualize the server-side processing. Simultaneously, the status area will show progress updates for major calculation blocks:
        *   "Step 1 of 4: Auto Offer calculations processing..." (Progress bar updates)
        *   "Step 2 of 4: Land Value Factor calculations processing..." (Progress bar updates)
        *   "Step 3 of 4: Improvement Factor calculations processing..." (Progress bar updates)
        *   "Step 4 of 4: ARV Factor calculations processing..." (Progress bar updates)
        *   And finally, "Saving File and Prepping for Download..." (Progress bar reaches 100%).
5.  After processing is complete, a "Download File" button will appear.
6.  Click the "Download File" button. The browser will then download the processed Excel file, typically named `processed_<your_original_filename>.xlsx`.

## API Endpoint (for programmatic access)

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
