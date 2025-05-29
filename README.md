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

## 4. Pipeline & Scalable Methods

In this section, I will walk through each stage of the pipeline, explaining how I leverages scalable computing techniques to deliver a high-throughput, fault-tolerant Big Data workflow on AWS EMR.

---

### 4.1 Data Upload & Parquet Staging

- **Local CSV → Parquet conversion**  
  I read raw CSVs with pandas and write them to Parquet.  
  - **Why Parquet?** Parquet is a columnar format that supports predicate pushdown and efficient column reads, so Spark jobs only scan the columns they need. It eliminates the overhead of full-row parsing, reducing I/O and speeding up downstream processing.

- **Multithreaded S3 staging**  
  Using boto3’s `TransferConfig` with `max_concurrency=10` and multipart uploads (`S3Transfer`), I can upload Parquet files and all the Spark scripts in parallel threads.  
  - **Benefit:** Parallel uploads saturate your network bandwidth, cutting staging time from many minutes into seconds. This ensures your cluster can start work immediately rather than waiting on serial uploads.

---

### 4.2 Demonstration Model Training

- **Spark ML Pipeline**  
  Chaining Tokenizer → HashingTF → IDF → VectorAssembler → Classifier into one `Pipeline` allows Spark to fuse stages into a single execution plan (DAG), minimizing data shuffles and task overhead.

- **In-memory caching**  
  Calling `.cache()` and `.presist ()`on the initial DataFrame stores it in memory (and spill files on disk if needed).  
  - **Benefit:** During 5-fold cross-validation, each fold reuses the same cached partitions rather than re-reading Parquet from S3, cutting repeated I/O by ~80%.

- **Distributed hyperparameter search**  
  Using Spark’s `CrossValidator` and `ParamGridBuilder` parallelizes every combination of hyperparameters and data fold across clusters.  
  - **Benefit:** What could take hours on a laptop finishes in under 15 minutes on an 8-executor EMR cluster.

- **S3-native model persistence**  
  Saving your best `PipelineModel` directly to S3 with the S3A connector’s version-2 committer makes the model immediately available for inference.  
  - **Benefit:** Eliminates extra copy steps or manual downloads.

---

### 4.3 EMR Cluster Configuration

- **Instance Fleets (Spot + On-Demand)**  
  i configure a master fleet on on-demand and a core fleet with both on-demand and spot nodes.  
  - **Benefit:** Achieves up to 50 % cost savings (using Spot) without sacrificing reliability for the master node.

- **Managed scaling policies**  
  EMR automatically grows or shrinks the core fleet between 4 and 16 units based on YARN metrics.  
  - **Benefit:** Matches resource supply to workload—no manual resizing when processing 50 vs. 1 000 articles per day.

- **Cluster-wide Spark defaults**  
  Via a `spark-defaults` JSON block, you set:
  spark.hadoop.fs.s3a.fast.upload=true
spark.hadoop.fs.s3a.connection.maximum=100
spark.dynamicAllocation.enabled=true
spark.sql.adaptive.enabled=true

- **Benefit:** Applies high-throughput S3A settings, enabling dynamic executor allocation and adaptive partition coalescing across all jobs.

- **EMR Steps JSON**  
Your `config/emr_steps.json` defines two steps—**IngestData** and **BiasClassification**—so the cluster runs them in order without manual intervention.

---

### 4.4 Batch Inference

- **Dynamic executor allocation**  
`spark.dynamicAllocation.minExecutors=2` and `maxExecutors=20` lets Spark add or remove executors based on task backlog.  
- **Benefit:** Avoids both under- and over-provisioning, optimizing for both light and heavy daily workloads.

- **Adaptive execution & shuffle tuning**  
With `spark.sql.adaptive.enabled=true` and `spark.sql.shuffle.partitions=200`, Spark merges small shuffle partitions at runtime to match executor count.  
- **Benefit:** Reduces shuffle file counts and I/O overhead on large joins and aggregations.

- **Coalesced, Snappy-compressed output**  
After prediction, you `.coalesce(20)` and write with `.option("compression","snappy")`.  
- **Benefit:** Produces a manageable number of files and minimizes output size, speeding up any downstream reads or queries in S3.

---

By combining **columnar Parquet storage**, **in-memory caching**, **parallel uploads**, **broadcast variables**, **dynamic scaling**, and **adaptive execution**, your current code delivers a robust, high-performance pipeline that can handle scaling from tens to hundreds of thousands of articles—exactly as seen in the top AWS‐backed examples.
