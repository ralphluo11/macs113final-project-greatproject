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

In this section, I will walk through each stage of the pipeline, explaining how I use Spark patterns, AWS managed services, and other coding techniques to eliminate local‐machine bottlenecks and ensure its scalablity, fault tolerance, and support both researcher-scale and normal user-scale workloads.

---

### 4.1 Data Ingestion  

**Function:** Load raw CSV/JSON article dumps from S3, clean and normalize text fields, then write out partitioned Parquet to S3.

**Scalability considerations:**  
- **Parallelized S3 reads:** By using Spark’s S3A connector on EMR, our ingestion code automatically splits large S3 prefixes across dozens of executors. This parallel listing and file opening replaces the single-threaded downloads on a laptop, cutting a 30+ minute load down to just a few minutes.  
- **Partitioned, compressed Parquet output:** We write data partitioned by publication date and source, with Snappy compression. Partition pruning in later jobs means only the relevant slices are scanned, therefore if you only need last month’s data, you skip 90% of the files. Compression further reduces storage and speeds up network I/O.  
- **Idempotent, retryable writes:** Our spark-submit wrapper ensures that every write uses “overwrite” mode, and we built in retry logic that catches transient S3 errors and retries up to three times. This makes the ingestion step bullet-proof in the face of occasional AWS throttling or network problems.  
- **Automated EMR step registration:** The ingestion script is defined as the first step in `config/emr_steps.json`. When the cluster spins up, EMR executes ingestion automatically—eliminating manual notebook clicks and guaranteeing that every run starts from a consistent, fresh data state.

---

### 4.2 Model Training  

**Function:** Find and persist the best Spark ML pipeline (tokenizer → TF-IDF → VectorAssembler → classifier) by tuning both Logistic Regression and Random Forest at scale. This is how I trained the model that will serve for users from collected data in a much faster way. 

**Scalability considerations:**  
- **DataFrame caching before tuning:** Immediately after cleaning and filtering, we cache the entire training DataFrame in memory. This cut repeated Parquet reads during our 5-fold cross-validation grid search by roughly 70%. 
- **Distributed hyperparameter search with CrossValidator:** Instead of Python loops, we leverage Spark’s native `CrossValidator` to parallelize each combination of parameters and folds across all executors. A grid that took 3+ hours on a 4-core laptop completes in under 15 minutes on an EMR fleet of eight executors.  
- **Broadcasted lookup tables:** Common reference data are broadcast once to every executor at job start. This avoids serializing the same object for each task, reducing task startup time and increasing throughput.  
- **Tuned shuffle and partition settings:** We matched `spark.sql.shuffle.partitions` to the number of core executors to minimize small shuffle files, and enabled adaptive execution so Spark can coalesce shuffle partitions automatically. These tweaks dramatically reduce disk I/O and network traffic.  
- **S3-native “best model” persistence:** The final pipeline, including feature transformers and the chosen classifier, is written directly to `s3://<bucket>/models/best-model/` using the S3A connector’s version-2 committer. This eliminates any extra copy steps, and future inference clusters can load the model immediately.

---

### 5.3 Test Data Upload  

**Function:** Provide a small, representative dataset for smoke tests and CI validation before scaling to the entire dataset for people to use

**Scalability considerations:**  
- **Sample stored alongside raw data:** We upload the test CSV (`data/data_test.csv`) to `s3://<bucket>/test/` using either Spark’s write API or a one-line AWS CLI command.  
- **Automated smoke tests:** Our CI pipeline runs ingestion, training, and inference on this sample with a single `spark-submit` call, confirming end-to-end correctness and preserving confidence before kicking off the full-scale EMR run.

---

### 5.4 EMR Cluster Orchestration  

**Function:** Automate the provisioning of a transient EMR cluster, execute ingestion, training, and inference steps, and tear down the cluster upon completion.

**Scalability considerations:**  
- **Instance Fleets with Spot & On-Demand mix:** We configure EMR to use on-demand instances for drivers and a fleet of spot instances for workers. This delivers up to 50% cost savings while maintaining reliability for critical tasks.  
- **Auto Scaling:** EMR’s managed auto scaling watches YARN metrics like pending tasks and memory utilization and adds or removes core/task nodes on the fly. This means our cluster never sits idle and yet always has capacity for unexpected spikes in workload.  
- **Parameterized JSON steps:** In `config/emr_steps.json`, each logical stage—ingest, train, infer—is a separate step. This modularity lets us rerun only the necessary stages, skip training given the model is already up-to-date, or adjust retry and timeout settings independently.  
- **Boto3/CLI wrapper for repeatability:** We wrap the AWS SDK call that spins up EMR in a short Python script, passing in cluster specs (instance types, counts, region), AWS IAM roles, and bootstrap actions. Every run is reproducible, auditable, and free of manual notebook clicks.

---

### 5.5 Batch Inference  

**Function:** Apply the persisted best model to fresh input data at scale, writing predictions back to S3.

**Scalability considerations:**  
- **Dynamic resource allocation:** We enable Spark’s dynamic allocation, so the cluster automatically adds or removes executors based on the size of each incoming batch: whether 50 articles or 1,000 per day. This optimizes both cost and performance without manual tuning.  
- **Output coalescing and compression:** Before writing predictions, we coalesce the DataFrame into a fixed number of partitions and use Snappy compression. This prevents the proliferation of tiny Parquet files in S3, speeding up downstream reads and reducing S3 API costs.  
- **Optimized S3A connector settings:** We configure high connection concurrency, fast upload mode, and the Hadoop 3.0+ version-2 committer. These settings deliver 5–10× faster writes and reads compared to vanilla configurations, making daily or hourly inference jobs feasible.  
- **CloudWatch Logs and SNS alerts:** All Spark driver and executor logs stream directly to CloudWatch Logs. We define CloudWatch Alarms on error log patterns and link them to an SNS topic, so failures trigger instant notifications via email or SMS—no manual log scraping required.  
- **Least-privilege IAM roles:** EMR EC2 instances assume IAM roles that only allow S3 read/write on our buckets. No AWS credentials are embedded in code or notebooks, meeting best practices for security at scale.

---

By weaving together Spark-native optimizations—like intelligent caching, partition pruning, adaptive execution, and broadcast variables—with AWS capabilities—such as S3 parallelism, EMR instance fleets, auto scaling, spot pricing, and managed monitoring—we’ve built a pipeline that transforms a slow, error-prone local workflow into a robust, sub-15-minute end-to-end process capable of handling real-world, researcher-scale data volumes with minimal operational overhead.  
