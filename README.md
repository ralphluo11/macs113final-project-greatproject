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
