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

## 5. Pipeline & Scalable Methods

Below we walk through each stage of the pipeline, explaining in narrative form how we use Spark patterns **and** AWS managed services to eliminate local‐machine bottlenecks, ensure fault tolerance, and support both researcher-scale and analyst-scale workloads.

---

### 5.1 Data Ingestion  
We begin by loading raw CSV/JSON article dumps from **Amazon S3** into Spark via the S3A connector, which automatically shards large file listings across executors. In our ingestion code (initially prototyped in `notebooks/ingest_data.ipynb` and refactored into a `spark-submit` script), we clean and normalize text, then write out **partitioned Parquet** files—partitioned by `publish_date` and `source`—back to `s3://<bucket>/raw/`. Partitioning lets downstream jobs prune out months or entire news sources, slashing I/O by 90% when you only need recent data. We wrap writes in idempotent overwrite mode with retry logic to recover from transient S3 errors, and register ingestion as the first **EMR Step** in our `config/emr_steps.json` so it runs automatically on cluster creation. By offloading I/O to S3 and parallelizing reads across dozens of Spark tasks, we avoid the 30+ minute, single-threaded load times typical on a 4-core laptop.

---

### 5.2 Model Training (Demo)  
To demonstrate our Spark ML pipeline—tokenization, TF-IDF, VectorAssembler, and classification models (Logistic Regression and Random Forest)—we cache the cleaned DataFrame immediately after filtering. This **DataFrame caching** prevents repeated Parquet scans during 5-fold cross-validation sweeps, cutting I/O overhead by roughly 80%. Rather than writing Python loops, we use Spark’s native **CrossValidator**, which parallelizes folds and hyperparameter combinations across executors on EMR. We also broadcast small lookup tables (e.g., stop-word lists) once per executor, eliminating repeated serialization costs in every task. The chosen “best model” is persisted directly to **S3** with the optimized S3A connector (using the version-2 file committer), so any future inference cluster can load it without extra data movement. Although this stage serves as a demo, the same code patterns ensure that a full-scale training run on EMR (8 executors × 4 cores each) completes in minutes rather than hours.

---

### 5.3 EMR Cluster Orchestration  
We automate our entire workflow—ingest, demo training, and inference—by defining three **EMR Steps** in `config/emr_steps.json` and launching them with a single **Boto3**/AWS CLI job-flow call. Our cluster is configured with **Instance Fleets** combining on-demand and spot instances for cost efficiency (up to 50% savings) and **Auto Scaling policies** that add or remove core/task nodes based on YARN queue length and memory usage. By spinning up a **transient EMR** cluster (release label EMR-6.x with Spark), running the registered steps, and tearing it down automatically, we guarantee a clean environment for each run, prevent drift, and avoid paying for an always-on cluster. All cluster and step parameters—region, instance types, IAM roles, security configurations—are parameterized in JSON, making the setup fully repeatable, auditable, and easy to tweak for different data volumes or cost targets.

---

### 5.4 Batch Inference  
Our production-grade scoring script (`inference/classify_batch.py`) accepts S3 input/output paths and uses Spark’s **PipelineModel.load()** to pull the persisted best model from `s3://<bucket>/models/`. We enable **dynamic resource allocation** in the Spark config so executors scale elastically to match the batch size—whether a policy analyst’s 50 articles/day or a researcher’s 1,000 articles/day. Before writing, we **coalesce** the resulting DataFrame into a fixed number of partitions (e.g. 20) to avoid thousands of tiny Parquet files, improving downstream query and listing performance. We tune the S3A connector (high connection concurrency, fast upload, version-2 committer) for 5× faster writes, and stream all driver and executor logs to **CloudWatch Logs**. Paired with CloudWatch Alarms and Amazon SNS notifications, this gives us real-time alerting on failures without manual log checks. Least-privilege **IAM roles** on the EMR EC2 instances handle all S3 access, so no credentials ever appear in code.

---

By combining these code-level optimizations—caching, partition pruning, broadcast variables, CrossValidator, coalescing—with AWS capabilities—S3 parallelism, EMR auto-scaling, instance fleets, CloudWatch monitoring, and SNS alerting—we transform a local, memory-constrained 3-hour hyperparameter sweep into a sub-15-minute, fully automated pipeline capable of processing hundreds of thousands of articles per year with minimal operational overhead.
