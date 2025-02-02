# Use an official lightweight Python image.
FROM python:3.9-slim

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file and install dependencies.
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the rest of your project files.
COPY . /app/

# Expose port 5000 (optional, if your application requires it)
EXPOSE 5000

# Set the default command to run your ETL pipeline script.
CMD ["python", "main.py"]
