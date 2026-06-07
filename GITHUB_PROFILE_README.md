# Hi, I'm Ilay Lankin 👋

I am an engineering student at **Ariel University** specializing in high-performance backend development, LLM infrastructure, and MLOps. I build system-level software that bridges the gap between machine learning models and cost-effective production scaling.

---

## 🚀 Flagship Project: VIREN — LLM Cost Optimization Gateway

I engineered **VIREN**, an OpenAI-compatible gateway that sits between production SaaS apps and LLM providers. It dynamically routes and caches prompts to optimize cost without sacrificing quality.

* **GitHub Repository:** [ilay102/LLM](https://github.com/ilay102/LLM)
* **The Impact:**
  * 📉 **87% cost reduction** verified on standard SaaS eval datasets.
  * ⚖️ **90% factual equivalence** (measured using a 3-judge pairwise LLM-as-a-judge ensemble).
  * 💻 **100% code-generation pass rate** at **79% lower cost** (tested using real code execution and assertions).
  * ⚡ **<250ms p95 routing overhead** with **26ms p50 semantic cache hits**.
* **Key Architecture & Skills:**
  * **API Gateways:** Custom FastAPI reverse proxy with LiteLLM routing.
  * **Vector Database:** Redis Stack HNSW vector search for prompt semantic cache lookup.
  * **ML Engineering:** Learned nearest-centroid classifier in `bge-small-en-v1.5` embedding space.
  * **Observability:** Prometheus metrics collector scrape-ready for Grafana/CFO dashboards.
  * **Data & Privacy:** Hashed SHA-256 tenant keys, SQLite event logs, and Microsoft Presidio PII redaction.
  * **DevOps:** VPC-native automated deploy and teardown shell scripts (`pilot.sh`).

---

## 🛠️ Technical Stack

* **Languages:** Python, SQL, Shell Scripting, JavaScript
* **Web & APIs:** FastAPI, Uvicorn, REST, HTTP Proxies, WebSocket
* **Databases & Caches:** Redis (RediSearch / Vector Search), SQLite, PostgreSQL
* **AI & LLM Infra:** LiteLLM, Microsoft Presidio, spaCy, HuggingFace (SentenceTransformers), Ollama
* **Testing & MLOps:** Pytest, Pairwise A/B LLM-as-a-judge, Code execution assertion testing
* **DevOps & Infrastructure:** Docker, Docker Compose, Git/GitHub Actions, Linux/Debian environments

---

## 📫 How to Reach Me

* **Email:** [ilay10lankin@gmail.com](mailto:ilay10lankin@gmail.com)
* **GitHub Project:** [github.com/ilay102/LLM](https://github.com/ilay102/LLM)
* **LinkedIn:** *(Add your LinkedIn URL here)*

*(Tip: Create a new public repository named exactly `ilay102`, check the "Initialize this repository with a README" option, and paste this content in to make it display as your GitHub homepage!)*
