import pandas as pd
from pymongo import MongoClient
from minio import Minio
import os
import uuid

# mongo_uri = "mongodb://localhost:localhost@10.225.0.22:27017/office_365_log"
mongo_uri = "mongodb://143.198.212.199:27017/azure_log_vbd_office"

# Connect to MongoDB
client = MongoClient(mongo_uri)

# Select the database and collection
db = client["azure_log_vbd_office"]
collection = db["log"]

# Retrieve the data from the MongoDB collection
data = list(collection.find())

# Load data into a Pandas DataFrame
df_mongo = pd.DataFrame(data).reset_index(drop=True)

# Keep the preset columns for PowerBI 
df_mongo = df_mongo[['Date (UTC)', 'User','Username','Resource', 'IP address', 'Location', 'Status', 'Sign-in error code', 'Failure reason', 'Client app', 'Browser', 'Operating System', 'Join Type', 'Authentication requirement', 'Sign-in identifier']]
df_mongo.sample(3)

# Create MinIO client
client = Minio(
    endpoint="159.223.70.240:9000",
    access_key="7PNa6XyMNENmFDhzmZw2",
    secret_key="qqgkYhd8bXbYC7ZIkS04fGYZtYN3yoEc4gqh3fA7",
    secure=False
)

# MinIO buckets and file details
source_bucket = "azure-log-office365-pre-clean"
target_bucket = "azure-log-office365"
cleaned_file = "data_update.csv"  # Name of the cleaned file to upload

# Get objects from the source bucket
objects = client.list_objects(source_bucket)
csv_object_name = None

def show_error(message):
    """Helper function to print error messages."""
    print(f"ERROR: {message}")

try:
    print(f"Checking objects in source bucket: '{source_bucket}'...")

    # Get objects from the source bucket
    objects = client.list_objects(source_bucket)
    csv_object_name = None

    for obj in objects:
        if obj.object_name.endswith('.csv'):
            csv_object_name = obj.object_name
            break

    if not csv_object_name:
        print(f"No CSV files found in bucket: '{source_bucket}'")
    else:
        print(f"Found CSV file: {csv_object_name}. Downloading...")

        # Generate a random filename for the temporary local file
        temp_local_file = f"{uuid.uuid4().hex}.csv"
        print(f"Temporary local file: {temp_local_file}")

        # Download the file from MinIO
        client.fget_object(source_bucket, csv_object_name, temp_local_file)

        print(f"File '{csv_object_name}' downloaded successfully. Starting cleaning process...")

        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(temp_local_file)

        if not df.empty:
            # Check if required columns are present
            required_columns = [
                'Date (UTC)', 'User', 'Username', 'Resource', 'IP address', 'Location',
                'Status', 'Sign-in error code', 'Failure reason', 'Client app', 'Browser',
                'Operating System', 'Join Type', 'Authentication requirement', 'Sign-in identifier', 'Request ID'
            ]
            if all(col in df.columns for col in required_columns):
                # Keep only required columns
                df_cleaned = df[required_columns].copy()

                # Merge both db before cleaning 
                df_merge = pd.concat([df_mongo, df_cleaned]).reset_index(drop=True)
                
                # Drop all duplicate available in both df: 
                df_merge.drop_duplicates(subset=['Request ID'], keep='first', inplace=True, ignore_index=True)
                
                # Save cleaned data to a new CSV
                df_merge.to_csv(cleaned_file)
                print(f"Cleaned data saved locally as: {cleaned_file}")

                # Ensure the target bucket exists
                if not client.bucket_exists(target_bucket):
                    print(f"Target bucket '{target_bucket}' does not exist. Creating it...")
                    client.make_bucket(target_bucket)   
                              
                # Upload the cleaned CSV to the target bucket
                print(f"Uploading cleaned data to bucket: '{target_bucket}'...")
                client.fput_object(target_bucket, cleaned_file, cleaned_file)
                print(f"Cleaned file '{cleaned_file}' uploaded successfully to bucket '{target_bucket}'.")
            else:
                missing_columns = [col for col in required_columns if col not in df.columns]
                message = f"The file '{csv_object_name}' does not meet the column requirements.\nMissing columns: {', '.join(missing_columns)}"
                show_error(message)
        else:
            print(f"The file '{csv_object_name}' is empty. Skipping cleaning and upload.")

except Exception as e:
    print(f"Error during processing: {e}")
    show_error(f"Error during processing: {e}")
finally:
    # Clean up temporary files
    if temp_local_file and os.path.exists(temp_local_file):
        os.remove(temp_local_file)
        print(f"Temporary file '{temp_local_file}' removed.")
    if os.path.exists(cleaned_file):
        os.remove(cleaned_file)
        print(f"Temporary file '{cleaned_file}' removed.")