# Final Project: Scalable Political Bias Classification Pipeline

**Team**: Solo project by **Jiahang Luo**

---

## 1. Social-science question
**How do major U.S. English-language media outlets frame political bias in news articles, and can we automatically classify such bias at scale to study patterns across outlets and over time?**

In democratic societies, the media plays an important role in shaping public understanding of political issues. The way news stories are framed—what is emphasized, omitted, or highlighted—profoundly influences public opinion, political polarization, and ultimately, policy outcomes. Media outlets are not neutral conveyors of information; rather, they often present news through ideologically biased frames, shaped either consciously or by structural and institutional constraints.

Understanding these framing patterns is essential for analyzing how media contributes to the formation of political beliefs and for safeguarding the quality of democratic engagement. Yet, the vast scale of modern news production—with millions of articles across diverse outlets and platforms—makes manual analysis unfeasible.

To address this challenge, this project focuses on developing scalable, automated tools capable of classifying ideological bias in news coverage with both consistency and transparency. These tools enable systematic detection of political bias, facilitate comparisons across media outlets reporting on the same events, and track shifts in media slant over time. In doing so, they aim to empower citizens to make more informed political decisions, thereby enhancing the quality of democratic participation. Moreover, these tools provide researchers with a means to study the evolution of media bias on a broad scale.

By establishing a high-throughput, reproducible method for identifying political bias in news content, this project lays the groundwork for large-scale empirical research into ideological bias, agenda-setting dynamics, and the broader role of media in democratic societies. Beyond academic contributions to political communication, this work addresses pressing societal concerns about truth, trust, and polarization in the digital age, offering both scholarly insights and practical benefits for the public.

---

## 2. Why Scale Matters

- **Training volume & local bottlenecks**  
  Our dataset includes approximately 28,000 articles for training, 7,000 for validation, and 1,300 for testing (~36,000 total). On a typical 4-core/16 GB machine, loading & tokenization takes 30+ minutes, and a 5-fold CV over a 10-point hyperparameter grid exceeds 3 hours—and often triggers OOM errors. This highlights local compute limits and motivates distributed solutions.

- **Researcher-level incoming volume**  
  Major news outlets publish **500–1,000 articles/day** (~180,000–365,000/year). Multi-year framing analyses or real-time responses to breaking events require processing hundreds of thousands of articles—well beyond single-node runtimes without crashes or delays.

- **Analyst-level incoming volume**  
  A power user or policy analyst might ingest **50–100 articles/day** (~18,000–36,000/year) for dashboards or alerts. Even these moderate loads can overwhelm local machines when run daily, benefiting greatly from elastic, fault-tolerant clusters.

---

## 3. Repo Structure

```text
final-project/
├── README.md                      # Project overview and instructions
├── requirements.txt               # Python dependencies
│
├── config/                        # Cluster and job definitions
│   └── emr_steps.json             # EMR steps configuration
│
├── notebooks/                     # Development and experimentation
│   ├── ingest_data.ipynb          # Data staging & ETL
│   ├── model_training.ipynb       # Training and hyperparameter search
│   └── setup_emr_cluster.ipynb    # Cluster provisioning and tuning
│
├── inference/                     # Batch scoring
│   └── classify_batch.py          # Batch inference script with UDF ensemble
│
└── data/                          # Sample or test datasets
    └── data_test.csv
````

---

# Pipeline & Scalable Methods

In this section, I walk through each stage of the pipeline, highlighting the scalable computing techniques that deliver a high-throughput, fault-tolerant Big Data workflow on AWS EMR. By layering parallelism, data locality, and adaptive resource management, this architecture can seamlessly scale from tens to hundreds of thousands of articles with minimal human intervention.

---

## 4.1 Data Upload & Parquet Staging

This phase handles new data ingest for running the pre-trained model—designed for tens to hundreds of thousands of articles.

* **Spark-based CSV → Parquet conversion & partitioning**

  * Using Spark’s DataFrame API instead of pandas:
    ```python
    df = spark.read.option("header", True) \
                   .csv("s3://bucket/raw_csv/")

    df.write.partitionBy("publish_date") \
            .option("compression", "snappy") \
            .mode("overwrite") \
            .parquet("s3://bucket/parquet/partitioned/")
    ```

  * **Why Spark & partitioning?** Columnar storage with predicate pushdown and vectorized reads means Spark scans only required columns, reducing I/O and improving query latency by up to **5×** on wide tables.

  * **Scalability Benefit:** Parquet compression reduces data volume by 60–80%, cutting storage costs and network transfer times across massive datasets.

* **Multithreaded S3 staging**

  * Using `boto3`’s `TransferConfig(max_concurrency=10, multipart_threshold=8MB, multipart_chunksize=8MB)` and `S3Transfer` for parallel uploads.

  * **Benefit:** Saturates network bandwidth—what once took minutes now completes in seconds, making cluster start-up latency negligible.

* **Incremental manifest-driven ingest**

  * Each run tracks new files using a manifest and compares with previous state to only process deltas.

  * **Fault Tolerance:** Checkpointed manifests and idempotent writes avoid duplication and enable safe recovery after interruption.

* **UUID-based path isolation**

  * Each run generates a unique S3 prefix via `uuid.uuid4()`, preventing collisions.

  * **Operational Scalability:** Isolated run directories simplify cleanup and rollback, avoiding contamination of production data.


---

## 4.2 Model Training Process

This section details how the model is trained on large datasets using scalable computing methods.

* **Spark ML Pipeline**

  * Chain `Tokenizer → HashingTF → IDF → VectorAssembler → Classifier` in a single `Pipeline`, allowing Spark to optimize across stages, reducing shuffle operations and task overhead.

* **In-memory caching & persistence**

  * Use `.cache()` and `.persist()` to hold processed partitions in executor memory (with disk spill)—5-fold CV reuses cached data instead of re-reading S3, cutting I/O by \~80%.

* **Distributed hyperparameter search**

  * Utilize `CrossValidator` + `ParamGridBuilder` to parallelize parameter-grid evaluations across executors and folds.
  * **Scalability Benefit:** A grid search that would take 8 hours on a single machine completes in under 15 minutes on an 8-node cluster, enabling rapid iteration.

* **Reproducibility & monitoring**

  * Seed with `random.seed(42)` and `numpy.random.seed(42)` for deterministic splits and results.
  * Leverage `logging` for real-time progress, warnings, and alerts on long-running jobs.

* **S3-native model persistence**

  * Save the best `PipelineModel` directly to S3 via the S3A v2 committer.
  * **Benefit:** Models are instantly available for downstream batch or streaming inference, eliminating manual transfers.

---

## 4.3 EMR Cluster Configuration

* **Instance Fleets (On-Demand + Spot)**

  * Master nodes on On-Demand, core nodes mixing On-Demand and Spot.
  * **Cost Efficiency:** Spot instances cut worker costs by up to **70%** while On-Demand masters ensure reliability.

* **Managed scaling policies**

  * EMR’s managed scaling adjusts core fleet size (4–16 nodes) based on YARN metrics (e.g., pending tasks).
  * **Elasticity Benefit:** Dynamically scales out for bulk ingest and scales in during idle periods, optimizing cost.

* **Cluster-wide Spark tuning**

  ```json
  {
    "spark.hadoop.fs.s3a.fast.upload": "true",
    "spark.hadoop.fs.s3a.connection.maximum": "100",
    "spark.dynamicAllocation.enabled": "true",
    "spark.sql.adaptive.enabled": "true"
  }
  ```

  * **Performance Benefit:** Fast S3A uploads, dynamic executor allocation, and adaptive query planning deliver consistent throughput under varying workloads.

* **Automated EMR steps**

  * `config/emr_steps.json` defines `IngestData` and `BiasClassification` steps executed by `command-runner.jar`.
  * **Operational Scalability:** Eliminates manual job submission; updating JSON propagates new pipeline versions for CI/CD workflows.

---

## 4.4 Batch Inference

* **Dynamic executor allocation**

  * `spark.dynamicAllocation.minExecutors=2` and `maxExecutors=20` let Spark scale executors based on task backlog.
  * **Benefit:** Balances cost-per-inference by avoiding over- or under-provisioning.

* **Adaptive execution & shuffle tuning**

  * `spark.sql.adaptive.enabled=true` and `spark.sql.shuffle.partitions=200` merge small partitions and tune shuffle parallelism at runtime, reducing I/O overhead.

* **Custom ensemble UDFs & vector operations**

  * A custom `avg_udf` blends logistic and random forest probability vectors in-cluster, enabling efficient ensemble predictions without external orchestration.
  * **Scalability Benefit:** Inline ensembles scale with the cluster, avoiding network hops and serialization costs of separate endpoints.

* **Coalesced, Snappy-compressed outputs**

  * After predictions, `.coalesce(20)` and `.option("compression", "snappy")` produce a fixed number of compressed files.
  * **Benefit:** Optimizes downstream read performance, lowers S3 request counts, and speeds up ad-hoc analysis.

---

**By combining** columnar storage, parallelized I/O, in-memory caching, distributed tuning, fleet-based provisioning, and adaptive Spark optimizations, **this pipeline** achieves both horizontal and vertical scalability—ensuring reliable, cost-effective processing as data volumes and complexity grow.

```
