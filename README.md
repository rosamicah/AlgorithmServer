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

### AWS S3 Bucket Configuration for Public Access

For the S3 links to processed files to be publicly accessible, your S3 bucket (specified by the `S3_BUCKET_NAME` environment variable) needs to be configured correctly. This application uploads files *without* setting an explicit Access Control List (ACL) like `public-read` at the object level (as this is often restricted by default S3 settings for new buckets). Therefore, public readability relies on your bucket's configuration:

1.  **Bucket Policy:** Ensure your S3 bucket has a bucket policy that allows public `s3:GetObject` access for the paths where files will be stored (e.g., `arn:aws:s3:::your-bucket-name/*`). An example policy statement is:
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::your-bucket-name/*"
            }
        ]
    }
    ```
    Replace `your-bucket-name` with your actual bucket name.

2.  **Block Public Access Settings:** The "Block Public Access" settings for your S3 bucket (found in the S3 console under the bucket's "Permissions" tab) must be configured to allow the public access granted by your bucket policy. If you intend for objects to be public via the bucket policy, ensure that settings such as:
    *   "Block public access to buckets and objects granted through new public bucket policies"
    *   "Block public access to buckets and objects granted through any public bucket policies"
    are **disabled (unchecked)**. Other "Block Public Access" settings might also need review depending on your specific security posture, but these two are key for bucket policies granting public read access.

If these settings are not correctly configured, the S3 upload by the application might still succeed (without an ACL error), but the S3 URLs provided will likely result in "Access Denied" errors when visited.

## Web Interface

The application provides an interactive web interface for uploading files directly through your browser.

1.  Navigate to the root URL of your deployed service (e.g., `https://your-app-name.onrender.com/`).
2.  You will see a page titled "Upload Property Data File".
3.  Click the "Choose file" button and select an Excel (.xls, .xlsx) or CSV (.csv) file from your computer.
4.  Click the "Upload and Process" button.
    *   An upload progress bar will show the file being sent to the server.
    *   Once the file is uploaded (upload progress will also be shown), a message like "File uploaded. Connecting to processing stream..." will appear.
    *   The application then uses Server-Sent Events (SSE) to provide real-time updates from the server as it starts reading and processing the file.
    *   The progress bar will fill, and the status area will display messages for each stage of processing *as they occur on the server*. These stages include:
        *   "Stream connected. Preparing to read data file..."
        *   "Data file successfully read. Standardizing columns..."
        *   "Columns standardized. Starting main calculations..."
        *   "Step 1 of 4: Auto Offer calculations processing..."
        *   "Step 2 of 4: Land Value Factor calculations processing..."
        *   "Step 3 of 4: Improvement Factor calculations processing..."
        *   "Step 4 of 4: ARV Factor calculations processing..."
        *   "Final calculations complete. Preparing data for Excel conversion..."
        *   "Data preparation complete. Starting Excel file generation..."
        *   "Excel file generated. Finalizing for download..."
    *   Each of these messages will correspond to an update on the progress bar, providing a live view of the server's work.
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
