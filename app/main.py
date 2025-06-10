import pandas as pd
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from io import BytesIO
import uvicorn
import os
import uuid
from pathlib import Path
import asyncio
import tempfile
import shutil
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

from .processor import enforce_master_columns, calculate_columns

# AWS Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1") # Default if not set
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "serverliststoragebackup")

# Email Configuration
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
EMAIL_SENDER_NAME = os.getenv("EMAIL_SENDER_NAME", "PicLeads Results") # Default if not set
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))

# Initialize S3 client
s3_client = None
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        # Test connection/credentials by listing buckets (optional, can be noisy)
        # s3_client.list_buckets()
        print("S3 client initialized successfully.")
    except (NoCredentialsError, PartialCredentialsError):
        print("Error: AWS credentials not found or incomplete in environment variables.")
        s3_client = None
    except ClientError as e:
        print(f"Error initializing S3 client: {e}. Check region and credentials.")
        s3_client = None
    except Exception as e:
        print(f"An unexpected error occurred during S3 client initialization: {e}")
        s3_client = None
else:
    print("AWS Access Key ID or Secret Access Key not provided. S3 functionality will be disabled.")

# Placeholder for email library setup if needed globally, or handle per request.
# For smtplib, setup is usually done when sending.

app = FastAPI()

# In-memory cache for processed files
processed_files_cache = {}

# Temporary file storage directory
TEMP_FILE_DIR = tempfile.gettempdir()
# Optional: Create a specific subfolder if desired, e.g.,
# TEMP_FILE_DIR = os.path.join(tempfile.gettempdir(), "app_temp_files")
# if not os.path.exists(TEMP_FILE_DIR):
#     os.makedirs(TEMP_FILE_DIR)

# Mount static files directory
# Ensure the 'static' directory exists at the root of where main.py is run from,
# or adjust the path accordingly. For this project structure, it's sibling to 'app'.
# If 'static' is inside 'app', the path would be "static" or "./static".
# Assuming 'static' is at the project root, and main.py is in 'app/',
# the relative path from main.py to a root 'static' folder is '../static'.
# However, Render and Docker setups often place 'static' at the same level as 'app' in the container.
# Let's assume 'static' will be at the root of the container, alongside 'app' directory.
# If Dockerfile copies './app /app/app' and './static /app/static', then from /app/app/main.py,
# static would be at /app/static.
# The simplest approach is to create static dir path relative to this file.
# Let's assume the 'static' directory is at the same level as the 'app' directory,
# and the app runs from the project root.
# If the app is run from /app (WORKDIR in Docker), and main.py is in /app/app/main.py,
# and static is in /app/static, then the path for StaticFiles should be "static".
# Let's try a more robust way to define static_dir_path
# Path to the directory containing this main.py file
# current_dir = os.path.dirname(os.path.abspath(__file__))
# Path to the static directory, assuming it's one level up from 'app' directory, then into 'static'
# This means project_root/static
# static_dir_path = os.path.join(current_dir, "..", "static")

# Simplification: FastAPI's StaticFiles path is relative to the directory where `uvicorn` is run.
# If uvicorn runs from project root, and static is `project_root/static`, then path="static"
# If Dockerfile copies `COPY ./static /app/static` and WORKDIR is /app, then `path="static"` is correct.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    # Try to read the index.html file.
    # Path needs to be relative to where uvicorn is running from.
    # If uvicorn main:app --cwd app, then path is "../static/index.html"
    # If uvicorn app.main:app from project root, then path is "static/index.html"
    # Given Docker CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT"]
    # and WORKDIR /app, this implies uvicorn is run from /app.
    # If 'static' is also in /app (e.g. /app/static), then "static/index.html" is correct.
    index_html_path = "static/index.html"
    try:
        with open(index_html_path, "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: index.html not found</h1><p>Please check static file configuration.</p>", status_code=500)
    except Exception as e:
        return HTMLResponse(content=f"<h1>An error occurred</h1><p>{str(e)}</p>", status_code=500)

@app.post("/process/")
async def process_file(file: UploadFile = File(...)):
    """
    Accepts a CSV or Excel file, processes it using a generator,
    stores the result in a cache, and returns a JSON response with a file ID and status messages.
    """
    original_filename = file.filename
    status_messages = []
    df_processed = None

    try:
        # Read the uploaded file into a pandas DataFrame
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        elif file.filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(file.file)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid file type. Please upload a CSV or Excel file."}
            )

        # Process the DataFrame using the generator
        df_enforced = enforce_master_columns(df.copy())

        # Iterate through the generator
        for item in calculate_columns(df_enforced):
            if isinstance(item, str):
                status_messages.append(item)
            elif isinstance(item, pd.DataFrame):
                df_processed = item
                # Assuming the DataFrame is the last item yielded, as per processor.py refactor
                break
            else:
                # Should not happen based on current processor.py
                status_messages.append(f"Unexpected item type from processor: {type(item)}")

        if df_processed is None:
            # This case implies the generator didn't yield a DataFrame
            status_messages.append("Error: No processed data frame returned from processor.")
            return JSONResponse(
                status_code=500,
                content={"error": "Processing failed to produce a result.", "status_messages": status_messages}
            )

        # Save the processed DataFrame to an in-memory Excel file (BytesIO buffer)
        output_buffer = BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_processed.to_excel(writer, index=False, sheet_name='Processed Data')
        output_buffer.seek(0) # Reset buffer position to the beginning

        # Generate a unique file ID and store the buffer in the cache
        file_id = str(uuid.uuid4())
        # Store the buffer and original filename for Content-Disposition later
        processed_files_cache[file_id] = {"buffer": output_buffer, "filename": original_filename}

        status_messages.append("File processed successfully. Ready for download.")
        return JSONResponse(
            status_code=200,
            content={"file_id": file_id, "status_messages": status_messages, "original_filename": original_filename}
        )

    except Exception as e:
        # Log the exception details for debugging on the server
        print(f"Error during file processing: {str(e)}") # Basic logging
        # Consider more robust logging for production
        status_messages.append(f"An error occurred: {str(e)}")
        return JSONResponse(
            status_code=500, # Internal Server Error
            content={"error": f"An unexpected error occurred during processing: {str(e)}", "status_messages": status_messages}
        )

@app.post("/upload_for_sse/")
async def upload_for_sse_processing(file: UploadFile = File(...), email: str = Form(...)):
    try:
        file_id = str(uuid.uuid4()) # This ID is for the temporary file
        # Save the uploaded file to a temporary location
        temp_file_path = os.path.join(TEMP_FILE_DIR, f"{file_id}_{file.filename}")

        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # It's important to close the uploaded file explicitly
        # If file.file is an SpooledTemporaryFile, close() might not be async
        # For UploadFile, file.close() is available but might not be async.
        # The `with open(...)` context manager handles closing the buffer it writes to.
        # The original file object from UploadFile should be managed by FastAPI or Starlette.
        # However, explicitly calling close if available is good practice if not using `async with`.
        if hasattr(file, "close") and callable(file.close):
             file.close()


        return JSONResponse({
            "message": "File uploaded successfully. Starting processing stream.",
            "stream_id": file_id,
            "original_filename": file.filename,
            "stream_url": f"/stream_processing/{file_id}/?filename={file.filename}&email={email}"
        })
    except Exception as e:
        # Log the exception e
        print(f"Error during /upload_for_sse/: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.get("/stream_processing/{stream_id}/")
async def stream_processing(stream_id: str, filename: str, email: str): # email added from query param
    temp_file_path = os.path.join(TEMP_FILE_DIR, f"{stream_id}_{filename}")

    async def event_generator():
        try:
            if not os.path.exists(temp_file_path):
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Error: Processing file not found. It might have expired or an upload error occurred."})
                }
                return

            yield {
                "event": "message",
                "data": json.dumps({"message": "Stream connected. Preparing to read data file..."})
            }
            await asyncio.sleep(0.1)

            # Determine file type and read into DataFrame
            if filename.endswith(".csv"):
                df = pd.read_csv(temp_file_path)
            elif filename.endswith((".xls", ".xlsx")):
                df = pd.read_excel(temp_file_path)
            else:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Invalid file type for processing."})
                }
                return

            yield {
                "event": "message",
                "data": json.dumps({"message": "Data file successfully read. Standardizing columns..."})
            }
            await asyncio.sleep(0.1)

            df_enforced = enforce_master_columns(df.copy())

            yield {
                "event": "message",
                "data": json.dumps({"message": "Columns standardized. Starting main calculations..."})
            }
            await asyncio.sleep(0.1)

            processed_df = None
            for item in calculate_columns(df_enforced):
                if isinstance(item, str): # It's a status message
                    yield {
                        "event": "message",
                        "data": json.dumps({"message": item})
                    }
                    await asyncio.sleep(0.1)
                elif isinstance(item, pd.DataFrame):
                    processed_df = item
                    break

            if processed_df is not None:
                yield {
                    "event": "message",
                    "data": json.dumps({"message": "Data preparation complete. Starting Excel file generation..."})
                }
                await asyncio.sleep(0.1)

                output_buffer = BytesIO()
                with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                    processed_df.to_excel(writer, index=False, sheet_name='Processed Data')
                output_buffer.seek(0)

                yield {
                    "event": "message",
                    "data": json.dumps({"message": "Excel file generated. Finalizing for download..."})
                }
                await asyncio.sleep(0.1)

                # --- S3 Upload and Email Logic Start ---
                s3_object_name = f"SelfUploadedExcelBackups/{os.path.splitext(filename)[0]}_processed_{stream_id[:8]}.xlsx" # Added part of stream_id for uniqueness
                s3_public_url = None

                if s3_client and S3_BUCKET_NAME:
                    try:
                        yield {
                            "event": "message",
                            "data": json.dumps({"message": f"Uploading processed file to S3 bucket: {S3_BUCKET_NAME}..."})
                        }
                        await asyncio.sleep(0.1)

                        s3_client.put_object(
                            Bucket=S3_BUCKET_NAME,
                            Key=s3_object_name,
                            Body=output_buffer,
                            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        )
                        output_buffer.seek(0)

                        s3_public_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_object_name}"

                        yield {
                            "event": "message",
                            "data": json.dumps({"message": f"File successfully uploaded to S3. URL: {s3_public_url}"})
                        }
                        await asyncio.sleep(0.1)

                    except (NoCredentialsError, PartialCredentialsError) as e:
                        yield {"event": "error", "data": json.dumps({"message": f"S3 Upload Error: AWS credentials missing or incomplete. {str(e)}"})}
                        await asyncio.sleep(0.1)
                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code")
                        error_message = e.response.get("Error", {}).get("Message")
                        yield {"event": "error", "data": json.dumps({"message": f"S3 Upload Error ({error_code}): {error_message}"})}
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        yield {"event": "error", "data": json.dumps({"message": f"S3 Upload Error: {str(e)}"})}
                        await asyncio.sleep(0.1)
                else:
                    yield {"event": "message", "data": json.dumps({"message": "S3 client not configured; skipping S3 upload."})}
                    await asyncio.sleep(0.1)

                if s3_public_url and email and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD and EMAIL_HOST:
                    try:
                        yield {
                            "event": "message",
                            "data": json.dumps({"message": f"Sending email notification to {email}..."})
                        }
                        await asyncio.sleep(0.1)

                        msg = MIMEMultipart()
                        msg['From'] = f"{EMAIL_SENDER_NAME} <{EMAIL_HOST_USER}>"
                        msg['To'] = email
                        msg['Subject'] = f"{os.path.splitext(filename)[0]} is Processed and Ready for Download"

                        email_body = f"Hello,\n\nYour file '{filename}' has been processed.\n\nYou can download it from the following link:\n{s3_public_url}\n\nThank you,\n{EMAIL_SENDER_NAME}"
                        msg.attach(MIMEText(email_body, 'plain'))

                        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
                        server.starttls()
                        server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
                        server.sendmail(EMAIL_HOST_USER, email, msg.as_string())
                        server.quit()

                        yield {
                            "event": "message",
                            "data": json.dumps({"message": "Email notification sent successfully."})
                        }
                        await asyncio.sleep(0.1)

                    except smtplib.SMTPAuthenticationError:
                        yield {"event": "error", "data": json.dumps({"message": "Email Sending Error: SMTP authentication failed. Check EMAIL_HOST_USER/PASSWORD."})}
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        yield {"event": "error", "data": json.dumps({"message": f"Email Sending Error: {str(e)}"})}
                        await asyncio.sleep(0.1)
                elif s3_public_url:
                    yield {"event": "message", "data": json.dumps({"message": "Email client not configured; skipping email notification. File is on S3."})}
                    await asyncio.sleep(0.1)
                # --- S3 Upload and Email Logic End ---

                final_file_id = str(uuid.uuid4())
                processed_files_cache[final_file_id] = {
                    "data": output_buffer,
                    "filename": f"processed_{filename}" # For direct download link
                }

                # Modify complete message based on S3 success
                complete_message = "Processing complete. File is ready for direct download."
                if s3_public_url:
                    complete_message = f"Processing complete. File uploaded to S3 and link sent to {email} (if configured). Direct download also available."

                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "file_id": final_file_id, # For direct download
                        "s3_url": s3_public_url, # Include S3 URL in completion event
                        "message": complete_message
                    })
                }
            else:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Processing failed to return a DataFrame."})
                }

        except Exception as e:
            print(f"Error during /stream_processing/: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({"message": f"Error during processing: {str(e)}"})
            }
        finally:
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e_remove:
                    print(f"Error removing temp file {temp_file_path}: {str(e_remove)}")


    return EventSourceResponse(event_generator())

@app.get("/download/{file_id}")
async def download_file(file_id: str):
    """
    Serves the processed file from the cache using its file_id.
    The file is removed from the cache after retrieval.
    """
    cached_file_info = processed_files_cache.pop(file_id, None)

    if not cached_file_info:
        raise HTTPException(status_code=404, detail="File not found, may have expired or already been downloaded.")

    output_buffer = cached_file_info["data"]
    response_filename = cached_file_info["filename"]
    output_buffer.seek(0)

    return StreamingResponse(
        output_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={response_filename}"}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
