import pandas as pd
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from io import BytesIO
import uvicorn
import os

from .processor import enforce_master_columns, calculate_columns

app = FastAPI()

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
    Accepts a CSV or Excel file, processes it, and returns an Excel file.
    """
    try:
        # Read the uploaded file into a pandas DataFrame
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        elif file.filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(file.file)
        else:
            return {"error": "Invalid file type. Please upload a CSV or Excel file."}

        # Process the DataFrame
        df_enforced = enforce_master_columns(df.copy()) # Use a copy to avoid modifying the original df if it's used elsewhere
        df_processed = calculate_columns(df_enforced)

        # Save the processed DataFrame to an in-memory Excel file
        output_buffer = BytesIO()
        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
            df_processed.to_excel(writer, index=False, sheet_name='Processed Data')
        output_buffer.seek(0)

        # Return the Excel file as a StreamingResponse
        return StreamingResponse(
            output_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=processed_{file.filename}"}
        )

    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
