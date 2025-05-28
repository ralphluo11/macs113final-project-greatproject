#!/usr/bin/env python3
import argparse
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col
from pyspark.ml import PipelineModel
from pyspark.ml.linalg import Vectors
from pyspark.sql.types import DoubleType, VectorUDT


# UDFs for 50/50 averaging and argmax of the two models' probability vectors
# This is the best perforaming ensemble method based on my experiments 

avg_udf = udf(
    lambda a, b: Vectors.dense([(x + y) / 2 for x, y in zip(a, b)]),
    VectorUDT()
)
argmax_udf = udf(
    lambda v: float(max(range(len(v)), key=lambda i: v[i])),
    DoubleType()
)

# Main function to run the batch classification
def main(input_path: str, output_path: str):
    logging.info(f"Starting BatchClassify; reading from {input_path}")
    spark = (
        SparkSession.builder
        .appName("BatchClassify")
        .config("spark.hadoop.fs.s3a.connection.maximum", "100") 
        .config("spark.hadoop.fs.s3a.fast.upload", "true")   
        .config("spark.hadoop.fs.s3a.committer.name", "directory")
        .config(
           "spark.hadoop.mapreduce.outputcommitter.factory.scheme.s3a",
           "org.apache.hadoop.fs.s3a.commit.S3ACommitterFactory"
        )
        .getOrCreate()
    )


    # Read all parquet files under the input prefix
    df = spark.read.parquet(input_path).select("ID", "url", "content")
    logging.info(f"Loaded {df.count()} rows")

    # Load the two trained PipelineModels from S3
    lr = PipelineModel.load("s3://realralph/bias_classifier_pca_tuned")
    rf = PipelineModel.load("s3://realralph/bias_rf_pca100_tuned")
    logging.info("Loaded LR and RF models")

    # Score both models on the input data 
    p_lr = lr.transform(df) \
             .select("ID", "url", "probability") \
             .withColumnRenamed("probability", "prob_lr")
    p_rf = rf.transform(df) \
             .select("ID", "probability") \
             .withColumnRenamed("probability", "prob_rf")
    logging.info("Generated probability vectors")

    # Compute the average probability and final prediction for the input data 
    joined = p_lr.join(p_rf, on=["ID", "url"])
    pred = (
        joined
        .withColumn("avg_prob",   avg_udf("prob_lr", "prob_rf"))
        .withColumn("prediction", argmax_udf("avg_prob"))
    )

    # Map numeric→text label on predictions 
    mapping = {0.0: "Left", 1.0: "Center", 2.0: "Right"}
    map_udf = udf(lambda x: mapping.get(x, "Unknown"))
    result = (
        pred
        .withColumn("label", map_udf("prediction"))
        .select("ID", "url", "label")
    )
    logging.info("Mapped predictions to text labels")

    # Write results out as Parquet
    logging.info(f"Writing results to {output_path}")
    result.write.mode("overwrite").parquet(output_path)

    spark.stop()
    logging.info("BatchClassify complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="EMR Batch Classifier: reads input Parquet(s), "
                    "runs LR+RF 50/50 ensemble, writes out Parquet."
    )
    parser.add_argument(
        "--input-path", "-i",
        dest="input_path", required=True,
        help="S3 prefix or local path to input Parquet files (e.g. s3://bucket/incoming/)"
    )
    parser.add_argument(
        "--output-path", "-o",
        dest="output_path", required=True,
        help="S3 prefix or local path for output (e.g. s3://bucket/classified/)"
    )

    args = parser.parse_args()
    main(args.input_path, args.output_path)
