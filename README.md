# Final Project: Scalable Political Bias Classification Pipeline

**Team**: Solo project by **Jiahang Luo**

---

## 1. Social-science question
How do major U.S. English-language media outlets frame political bias in news articles, and can we automatically classify such bias at scale to study patterns across outlets and over time?


In democratic societies, the media plays an important role in shaping public understanding of political issues. The way news stories are framed, what is emphasized, omitted, or highlighted, profoundly influences public opinion, political polarization, and ultimately, policy outcomes. Media outlets are not neutral conveyors of information; rather, they often present news through ideologically biased frames, shaped either consciously or by structural and institutional constraints.

Understanding these framing patterns is essential for analyzing how media contributes to the formation of political beliefs and for safeguarding the quality of democratic engagement. Yet, the vast scale of modern news production with millions of articles across diverse outlets and platforms makes manual analysis unfeasible.

To address this challenge, my project focuses on developing scalable, automated tools capable of classifying ideological bias in news coverage with both consistency and transparency. These tools will enable systematic detection of political bias, facilitate comparisons across media outlets reporting on the same events, and track shifts in media slant over time. In doing so, they aim to empower citizens to make more informed political decisions, thereby enhancing the quality of democratic participation. Moreover, these tools will provide researchers with a means to study the evolution of media bias on a broad scale.

By establishing a high-throughput, reproducible method for identifying political bias in news content, this project lays the groundwork for large-scale empirical research into ideological bias, agenda-setting dynamics, and the broader role of media in democratic societies. Beyond academic contributions to political communication, this work addresses pressing societal concerns about truth, trust, and polarization in the digital age, offering both scholarly insights and practical benefits for the public.

---
## 2. Why Scale Matters

- **Training volume & local bottlenecks**  
  Our dataset includes approximately 28,000 articles for training, 7,000 for validation, and 1,300 for testing, for a total of around 36,000 articles. On a typical machine with four CPU cores and 16 GB of RAM, the preprocessing stage, including loading and tokenization, takes more than 30 minutes. Performing five-fold cross-validation across a ten-point hyperparameter grid typically requires over three hours and often results in out-of-memory errors. These limitations underscore the local computational bottlenecks present in our current setup. As we expand to larger datasets in future work, these bottlenecks are likely to become even more evident, highlighting the importance of improved infrastructure and more efficient processing strategies.

- **Researcher-level incoming volume**  
  Major news outlets publish **500–1 000 articles/day** (≈180 000–365 000/year). Studying multi-year framing shifts or responding to breaking events requires processing hundreds of thousands of articles, well beyond single-node runtimes without crashes or long delays.

- **Analyst-level incoming volume**  
  A power user or policy analyst might ingest **50–100 articles/day** (≈18 000–36 000/year) for dashboards or alerts. Even this load overwhelms local machines when run daily and benefits from elastic, fault-tolerant clusters.

## 3. Repo Structure

```text
final-project/
├── README.md                 
├── requirements.txt         
│
├── config/                   
│   └── emr_steps.json
│
├── notebooks/                
│   ├── ingest_data.ipynb
│   ├── model_training.ipynb
│   └── setup_emr_cluster.ipynb
│
├── inference/                
│   └── classify_batch.py
│
└── data/                    
    └── data_test.csv
```

# Pipeline & Scalable Methods

In this section, I walk through each stage of the pipeline, highlighting the scalable computing techniques that deliver a high-throughput, fault-tolerant Big Data workflow on AWS EMR. By layering parallelism, data locality, and adaptive resource management, this architecture can seamlessly scale from tens to hundreds of thousands of articles with minimal human intervention.

---

## 4.1 Data Upload & Parquet Staging

* **Local CSV → Parquet conversion**

  * Scripts leverage `pandas` to read raw CSVs and write them to Parquet files.
  * **Why Parquet?** Columnar storage supports predicate pushdown and vectorized reads, so Spark scans only required columns, dramatically reducing I/O and improving query latency by up to **5×** on wide tables.
  * **Scalability Benefit:** Reducing data volume by 60–80% via Parquet compression lowers both storage costs and network transfer times across massive datasets.

* **Multithreaded S3 staging**

  * Using `boto3`’s `TransferConfig(max_concurrency=10, multipart_threshold=8MB, multipart_chunksize=8MB)` and `S3Transfer` for parallel uploads.
  * **Benefit:** Parallel threads saturate network bandwidth—what once took minutes now completes in seconds, ensuring cluster start-up latency is negligible.

* **UUID-based path isolation**

  * Each run generates a unique S3 prefix via `uuid.uuid4()`, preventing collisions.
  * **Fault Tolerance:** Isolated run directories simplify cleanup and rollback, isolating partial uploads from production data.

---

## 4.2 Demonstration Model Training

* **Spark ML Pipeline**

  * Chaining `Tokenizer → HashingTF → IDF → VectorAssembler → Classifier` into one `Pipeline` enables Spark to optimize across transformer and estimator stages, reducing shuffle operations and minimizing task overhead.

* **In-memory caching & persistence**

  * Invoking `.cache()` (and `.persist()`) stores pre-processed partitions in executor memory (with disk spill) so that 5-fold cross-validation reuses them rather than re-reading S3—cutting I/O by \~80%.

* **Distributed hyperparameter search**

  * Using `CrossValidator` + `ParamGridBuilder` parallelizes grid evaluations across executors and data folds.
  * **Scalability Benefit:** A search that would take 8 hours on a single machine completes in under 15 minutes on an 8-node cluster, allowing rapid experimentation at scale.

* **Reproducibility & monitoring**

  * Seeding with `random.seed(42)` and `numpy.random.seed(42)` ensures consistent results across runs.
  * Logging via the `logging` module provides real-time visibility into long-running jobs, triggering alerts on failures.

* **S3-native model persistence**

  * Saving the best `PipelineModel` directly to S3 using the S3A v2 committer.
  * **Benefit:** Eliminates extra copy steps—models are immediately available for downstream batch or streaming inference pipelines.

---

## 4.3 EMR Cluster Configuration

* **Instance Fleets (On-Demand + Spot)**

  * A master fleet on On-Demand and a core fleet mixing On-Demand and Spot nodes.
  * **Cost Efficiency:** Spot instances can reduce worker node costs by up to **70%**, while On-Demand master nodes guarantee cluster stability.

* **Managed scaling policies**

  * EMR’s managed scaling automatically adjusts core fleet size (4–16 nodes) based on YARN metrics.
  * **Elasticity Benefit:** The cluster dynamically adapts to workload spikes—scaling out for bulk ingest and scaling in during idle periods to save costs.

* **Cluster-wide Spark tuning**

  ```json
  {
    "spark.hadoop.fs.s3a.fast.upload": "true",
    "spark.hadoop.fs.s3a.connection.maximum": "100",
    "spark.dynamicAllocation.enabled": "true",
    "spark.sql.adaptive.enabled": "true"
  }
  ```

  * **Performance Benefit:** Fast S3A uploads, dynamic executor allocation, and adaptive query planning guarantee optimal resource utilization across diverse workloads.

* **Automated EMR steps**

  * `config/emr_steps.json` defines logical steps (`IngestData`, `BiasClassification`) executed sequentially by `command-runner.jar`.
  * **Operational Scalability:** Automated steps remove manual handoffs—new pipeline versions deploy via updated JSON, enabling CI/CD of data workflows.

---

## 4.4 Batch Inference

* **Dynamic executor allocation**

  * `spark.dynamicAllocation.minExecutors=2` and `maxExecutors=20` allow Spark to elastically scale executors based on real-time backlog.
  * **Benefit:** Prevents over-provisioning during light loads and under-provisioning during peaks, optimizing cost-per-inference.

* **Adaptive execution & shuffle tuning**

  * `spark.sql.adaptive.enabled=true` and `spark.sql.shuffle.partitions=200` merge small partitions at runtime, reducing shuffle I/O and speeding up large joins.

* **Custom ensemble UDFs & vector operations**

  * A custom `avg_udf` combines logistic and random forest probability vectors in-cluster, enabling lightweight ensemble predictions without external orchestration.
  * **Scalability Benefit:** Inline UDF ensembles scale with the cluster, avoiding serialization overhead of separate model endpoints.

* **Coalesced, Snappy-compressed outputs**

  * After prediction, results `.coalesce(20)` and write with `.option("compression", "snappy")`.
  * **Benefit:** Produces a fixed number of smaller, compressed files for faster downstream queries, minimizing S3 request costs and accelerating ad-hoc analysis.

---

**By combining** columnar storage, parallelized I/O, in-memory caching, distributed tuning, fleet-based provisioning, and adaptive Spark optimizations, **this pipeline** achieves both horizontal and vertical scalability—ensuring reliable, cost-effective processing as data volumes and complexity grow.
