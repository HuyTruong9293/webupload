const express = require('express');
const cors = require('cors');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const { Client } = require('minio'); // Import the correct MinIO Client
const { exec } = require('child_process');

const app = express();
const PORT = 3000;
const HOST = '192.168.2.23';
const TIMEOUT_DURATION = 20000; // 5 seconds timeout

// MinIO Configuration
const minioClient = new Client({
  endPoint: '159.223.70.240',
  port: 9000,
  useSSL: false,
  accessKey: '7PNa6XyMNENmFDhzmZw2',
  secretKey: 'qqgkYhd8bXbYC7ZIkS04fGYZtYN3yoEc4gqh3fA7',
});

const bucketName = 'azure-log-office365-pre-clean'; // Your MinIO bucket name

// Ensure bucket exists or create it
minioClient.bucketExists(bucketName, (err) => {
  if (err) {
    if (err.code === 'NoSuchBucket') {
      minioClient.makeBucket(bucketName, '', (err) => {
        if (err) {
          console.error(`Error creating bucket: ${err}`);
        } else {
          console.log(`Bucket "${bucketName}" created successfully.`);
        }
      });
    } else {
      console.error(`Error checking bucket: ${err}`);
    }
  }
});


// Serve static files from the "public" directory
app.use(express.static('public'));

// Configure CORS
app.use(cors());

// Middleware to log incoming request IP addresses
app.use((req, res, next) => {
  console.log(`Incoming request from IP: ${req.ip}`);
  next();
});

// Middleware to set a timeout and abort stalled connections
app.use((req, res, next) => {
  req.setTimeout(TIMEOUT_DURATION, () => {
    console.warn(`Connection from IP ${req.ip} timed out.`);
    res.status(408).json({ message: 'Request timeout' });
    req.destroy(); // Explicitly abort the connection
  });

  res.on('close', () => {
    if (!res.writableEnded) {
      console.warn(`Connection from IP ${req.ip} closed before response completed.`);
      req.destroy(); // Abort incomplete connections
    }
  });

  next();
});

// Configure multer for file uploads (store files in memory for MinIO upload)
const storage = multer.memoryStorage(); // Store files in memory
const upload = multer({ storage: storage });

// Helper function to delete all objects in a MinIO bucket
const deleteAllObjectsInBucket = async (bucketName) => {
  try {
    const objectsStream = minioClient.listObjectsV2(bucketName, '', true); // Get the stream of objects

    const objectsToDelete = []; // Array to store object names

    for await (const obj of objectsStream) {
      objectsToDelete.push(obj.name); // Collect object names
    }

    if (objectsToDelete.length > 0) {
      console.log(`Deleting ${objectsToDelete.length} file(s) from bucket "${bucketName}"...`);

      // Delete objects in bulk
      await minioClient.removeObjects(bucketName, objectsToDelete);
      console.log('All files deleted successfully.');
    } else {
      console.log(`No files to delete in bucket "${bucketName}".`);
    }
  } catch (err) {
    console.error(`Error deleting files from bucket "${bucketName}": ${err.message}`);
  }
};

// Define the upload route
app.post('/upload', upload.single('file'), async (req, res) => {
  try {
    console.log('Starting file upload process...');

    // Check if a file was uploaded
    if (!req.file) {
      return res.status(400).json({ message: 'No file uploaded' });
    }

    const { originalname, buffer } = req.file;
    console.log(`Preparing to upload file "${originalname}" to MinIO...`);

    // Delete existing files in the bucket
    await deleteAllObjectsInBucket(bucketName);

    // Upload the new file to MinIO
    minioClient.putObject(bucketName, originalname, buffer, (err, etag) => {
      if (err) {
        console.error(`Error uploading file to MinIO: ${err.message}`);
        return res.status(500).json({ message: 'Error uploading file to MinIO' });
      }

      console.log(`File "${originalname}" uploaded to MinIO with etag: ${etag}`);

      // Run the Python script after successful upload
      exec('/volume1/web/khaienv/bin/python /volume1/web/Script_Clean.py', (error, stdout, stderr) => {
        if (error) {
          console.error(`Error executing Python script: ${error.message}`);
          return;
        }
        if (stderr) {
          console.error(`Python script stderr: ${stderr}`);
          return;
        }
        console.log(`Python script output: ${stdout}`);
      });

      // Respond with success
      res.json({ message: 'File uploaded successfully!' });
    });
  } catch (err) {
    console.error('Error processing upload:', err);
    res.status(500).json({ message: 'Error processing upload' });
  }
});

// Start the server
app.listen(PORT, HOST, () => {
  console.log(`Server running on http://${HOST}:${PORT}`);
});
