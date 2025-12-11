# Generative-AI-Projects
Full-stack Generative AI application featuring RAG, LLM inference, semantic search, and a modern React interface and more

## Local RAG Ollama Assistant

<img width="1444" height="781" alt="Screenshot 2025-11-30 at 8 49 33 AM" src="https://github.com/user-attachments/assets/0df83d8a-00b8-4c4d-a75d-d33ef6c8abb5" />


End-to-end Retrieval-Augmented Generation (RAG) application leveraging Llama 3, LangChain, and ChromaDB. Supports document ingestion, intelligent chunking, embeddings, semantic retrieval, and hallucination-resistant answer generation. Includes an interactive React UI styled with Tailwind for a seamless ChatGPT-like experience. This project showcases practical LLMOps, vector search pipelines, local LLM inference, and modern GenAI system design.



## Personal Scheduler Agent


<img width="1217" height="786" alt="Screenshot 2025-12-04 at 6 44 25 PM" src="https://github.com/user-attachments/assets/08838b5a-433a-492b-819e-0388da8c9481" />

An AI-powered Calendar Agent that automatically manages my entire daily schedule using real-time Google Calendar integration. It reads my structured routine, detects conflicts with meetings, intelligently reschedules tasks, and updates my calendar autonomously. The backend uses FastAPI with smart scheduling logic, and the agent can also understand natural-language commands like “schedule my routine for the next 5 days” or “clear this week.” A React dashboard visualizes my tasks, daily plan, scheduling decisions, and the agent’s JSON responses, making it a complete end-to-end personal productivity AI system.

## Job Searh Co-Pilot - Google ADK Agent

<img width="1461" height="639" alt="Screenshot 2025-12-08 at 9 46 21 PM" src="https://github.com/user-attachments/assets/35876b40-acb5-4721-a17b-46a6f1f785fa" />

Job Searh Co-Pilot AI is an intelligent career copilot built with Google ADK and Gemini models. It analyzes job descriptions, compares them to my skills and experience, identifies fit and gaps, and even generates tailored resume bullets and recruiter outreach messages. The agent uses tool-calling to parse job descriptions, load my profile, and automatically log job opportunities into a Google Sheets tracker—turning the job search into an automated, AI-driven workflow.

## Multi Agent Clinician Knowledge Assistant


<img width="1470" height="883" alt="Screenshot 2025-12-10 at 9 27 11 PM" src="https://github.com/user-attachments/assets/bb951a59-f826-4339-a1da-6f750e0c0775" />


A lightweight, privacy-preserving clinical information assistant built using LangGraph and local open-source LLMs (Ollama). The system uses a multi-agent workflow to answer medical knowledge questions safely and responsibly—without providing diagnosis or treatment advice.

The assistant orchestrates four specialized agents:

Triage Agent – routes the question to the appropriate specialists

Literature Agent – retrieves and summarizes real PubMed studies

Guideline Agent – performs RAG retrieval over local clinical guidelines using FAISS + HuggingFace embeddings

Patient Educator Agent – generates simple, layperson-friendly explanations

Synthesizer Agent – merges insights from all agents into a coherent, safety-guarded final response

All processing runs locally using free models (e.g., llama3, mistral) and no proprietary APIs.
The project demonstrates practical multi-agent design, tool integration, retrieval-augmented workflows, and clinically safe LLM prompting—ideal for research, education, or proving hands-on ability to build multi-agent systems.
