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

- **Training data volume**  
  We trained on **27,978** articles (train), **6,996** (validation), and **1,300** (test)—about **36 000** labeled articles in total. Even this moderate corpus already benefits from distributed storage and compute to iterate quickly over feature engineering, hyperparameter sweeps, and cross-validation.

- **Researcher-level incoming volume**  
  Major news outlets collectively publish on the order of **500–1 000 articles per day**, which translates to **≈180 000–365 000 articles per year**. To study framing shifts over multi-year periods or rapidly respond to breaking events, researchers need to process hundreds of thousands of new articles efficiently—far beyond what a single-node setup can handle without long runtimes or frequent failures.

- **Analyst-level incoming volume**  
  A power user or policy analyst might ingest **50–100 articles per day** for targeted investigations or dashboard updates—roughly **18 000–36 000 articles per year**. While smaller than the full-corpus scenario, this volume still stresses local machines when run daily, and benefits greatly from elastic, fault-tolerant cluster resources.

**Key takeaways:**  
- **Partitioned Parquet** writes and **pruning** avoid full-table scans.  
- **EMR dynamic allocation** scales executors up/down to match daily load.  
- **Coalesced outputs** and optimized **S3A connector** settings ensure reliable, performant reads and writes at scale.

---

## 3. Repo Structure
