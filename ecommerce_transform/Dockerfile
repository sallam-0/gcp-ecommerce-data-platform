# Use the official dbt BigQuery image
FROM ghcr.io/dbt-labs/dbt-bigquery:1.7.latest

# Set the working directory
WORKDIR /usr/app/

# Copy your dbt project files into the container
COPY . .

# Set the default command to run your models (dbt is the image entrypoint)
CMD ["run", "--profiles-dir", ".", "--project-dir", "."]
