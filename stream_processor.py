import json
import logging
import os
from pathlib import Path

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions


def load_dotenv(env_path: str = ".env") -> None:
    env_file = Path(env_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


# 1. Helper function to format the Pub/Sub message for BigQuery
class FormatForBigQuery(beam.DoFn):
    def process(self, element):
        try:
            # Decode the raw bytes from Pub/Sub into a string, then to a dictionary
            message_str = element.decode('utf-8')
            record = json.loads(message_str)
            
            # Extract the metadata and keep the whole payload as a string for safety
            yield {
                "job_id": record.get("job_id", "unknown"),
                "site": record.get("site", "unknown"),
                "published_at": record.get("published_at"),
                "raw_payload": json.dumps(record, ensure_ascii=False)
            }
        except Exception as e:
            logging.error(f"Failed to parse message: {e}")
            # In a production system, you'd send this to a Dead Letter Queue here


def run():
    load_dotenv()

    # 2. Set up your GCP variables
    project_id = get_required_env("GCP_PROJECT_ID")
    region = get_required_env("GCP_REGION")
    subscription_id = get_required_env("PUBSUB_SUBSCRIPTION")
    bq_dataset = get_required_env("BQ_DATASET")
    bq_table_name = get_required_env("BQ_TABLE")
    gcs_temp_location = get_required_env("DATAFLOW_TEMP_LOCATION")
    gcs_staging_location = get_required_env("DATAFLOW_STAGING_LOCATION")
    runner = get_required_env("DATAFLOW_RUNNER")
    service_account_email = get_required_env("DATAFLOW_SERVICE_ACCOUNT")
    worker_zone = get_required_env("DATAFLOW_WORKER_ZONE")

    subscription = f"projects/{project_id}/subscriptions/{subscription_id}"
    bq_table = f"{project_id}:{bq_dataset}.{bq_table_name}"

    # 3. Configure the Dataflow Pipeline Options
    options = PipelineOptions(
        project=project_id,
        region=region, # Make sure this matches your BQ dataset region
        temp_location=gcs_temp_location,
        staging_location=gcs_staging_location,
        service_account_email=service_account_email,
        worker_zone=worker_zone,
        streaming=True # Critical: Tells Beam this is an endless stream, not a batch file
    )
    options.view_as(StandardOptions).runner = runner # Run on GCP, not locally

    # 4. Build the Pipeline
    with beam.Pipeline(options=options) as p:
        (
            p
            | "Read from PubSub" >> beam.io.ReadFromPubSub(subscription=subscription)
            | "Format for BQ" >> beam.ParDo(FormatForBigQuery())
            | "Write to BigQuery" >> beam.io.WriteToBigQuery(
                table=bq_table,
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
                create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED
            )
        )

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    print("Submitting Dataflow job to GCP...")
    run()
