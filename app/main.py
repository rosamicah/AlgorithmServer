import pandas as pd
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
from io import BytesIO
import uvicorn

from .processor import enforce_master_columns, calculate_columns

app = FastAPI()

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
