import os
import operator
from typing import Annotated, List, Dict

import requests
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from langchain_community.chat_models import ChatOllama
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings


# =========================================================
# LLM + GLOBALS (FREE LOCAL LLM VIA OLLAMA)
# =========================================================

# Make sure Ollama is installed and running, and you’ve pulled a model like:
#   ollama pull llama3

llm = ChatOllama(model="llama3")  # e.g. "llama3", "mistral", etc.

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_EMAIL = os.getenv("PUBMED_EMAIL", "feenu.akhter@gmail.com")
NCBI_API_KEY = os.getenv("PUBMED_API_KEY") 

# Global retriever for guideline RAG
GUIDELINE_RETRIEVER = None  # will be initialized in main()


# =========================================================
# PUBMED HELPER + TOOL (REAL, FREE)
# =========================================================

def fetch_pubmed_abstracts(query: str, max_results: int = 3) -> str:
    """
    Query PubMed for up to `max_results` articles and return titles + abstracts as text.
    Uses NCBI E-utilities (esearch + efetch).
    """
    # 1) esearch to get PMIDs
    search_params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": str(max_results),
        "sort": "relevance",
        "term": query,
    }
    if NCBI_API_KEY:
        search_params["api_key"] = NCBI_API_KEY

    try:
        search_resp = requests.get(
            f"{PUBMED_BASE}/esearch.fcgi",
            params=search_params,
            timeout=10,
        )
        search_resp.raise_for_status()
    except Exception as e:
        return f"Error during PubMed esearch: {e}"

    try:
        data = search_resp.json()
    except Exception as e:
        return f"Error parsing PubMed esearch JSON: {e}"

    id_list = data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return "No PubMed results found for this query."

    # 2) efetch to get abstracts
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "rettype": "abstract",
        "retmode": "text",
        "email": PUBMED_EMAIL,
    }
    if NCBI_API_KEY:
        fetch_params["api_key"] = NCBI_API_KEY

    try:
        fetch_resp = requests.get(
            f"{PUBMED_BASE}/efetch.fcgi",
            params=fetch_params,
            timeout=10,
        )
        fetch_resp.raise_for_status()
    except Exception as e:
        return f"Error during PubMed efetch: {e}"

    text = fetch_resp.text
    if not text.strip():
        return "PubMed efetch returned empty content."

    # Limit length for LLM
    return text[:4000]


@tool
def web_search(query: str) -> str:
    """
    Search PubMed for biomedical literature and return a few abstracts.
    """
    return fetch_pubmed_abstracts(query)


# =========================================================
# GUIDELINE RAG (FAISS + HUGGINGFACE EMBEDDINGS, FREE)
# =========================================================

def build_guideline_retriever(guidelines_dir: str = "guidelines"):
    """
    Build a FAISS-based retriever over .txt files in `guidelines_dir`.

    Put plain-text clinical guideline / SOP snippets under:
        guidelines/*.txt
    """
    if not os.path.isdir(guidelines_dir):
        print(f"[guideline_retriever] No '{guidelines_dir}' directory found. Guideline search will be empty.")
        return None

    txt_paths = [
        os.path.join(guidelines_dir, f)
        for f in os.listdir(guidelines_dir)
        if f.endswith(".txt")
    ]

    if not txt_paths:
        print(f"[guideline_retriever] No .txt files in '{guidelines_dir}'. Guideline search will be empty.")
        return None

    docs = []
    for path in txt_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"[guideline_retriever] Error reading {path}: {e}")
            continue

        docs.append(
            Document(
                page_content=text,
                metadata={"source": os.path.basename(path)},
            )
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
    )
    split_docs = splitter.split_documents(docs)

    # Free local embedding model (downloads automatically)
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    vectorstore = FAISS.from_documents(split_docs, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    print(f"[guideline_retriever] Indexed {len(split_docs)} chunks from {len(txt_paths)} files.")
    return retriever


@tool
def vector_search(query: str) -> str:
    """
    Vector search over local clinical guidelines (real RAG, not stub).

    Looks in the 'guidelines/' folder for .txt files, which are embedded
    into a FAISS index at startup.
    """
    if GUIDELINE_RETRIEVER is None:
        return (
            "No guideline index is loaded. "
            "Add .txt files under a 'guidelines/' folder and restart the app."
        )

    try:
        docs = GUIDELINE_RETRIEVER.invoke(query)
    except Exception as e:
        return f"Error retrieving guidelines: {e}"

    if not docs:
        return "No relevant guideline snippets found."

    snippets = []
    for d in docs:
        src = d.metadata.get("source", "unknown")
        text = d.page_content.strip().replace("\n\n", " ").replace("\n", " ")
        snippets.append(f"[{src}] {text[:400]}...")

    return "\n\n".join(snippets)


# =========================================================
# GRAPH STATE
# =========================================================

class ClinicalQAState(TypedDict):
    question: str                    # Raw user question
    route: List[str]                 # Names of agents selected by triage
    partial_answers: Annotated[List[Dict], operator.add]  # agent outputs
    final_answer: str                # Final synthesized answer


# =========================================================
# AGENT NODES (MULTI-AGENT WORKFLOW)
# =========================================================

def triage_agent(state: ClinicalQAState) -> Dict:
    """
    Decide which specialist agents to use for this clinical question.
    Simple heuristic router; could be replaced with an LLM router later.
    """
    q = state["question"]
    lower = q.lower()
    route: List[str] = []

    # Rough routing based on keywords
    if any(k in lower for k in ["study", "studies", "trial", "trials", "evidence", "research"]):
        route.append("literature")

    if any(k in lower for k in ["guideline", "guidelines", "who", "cdc", "nice", "protocol", "sop"]):
        route.append("guideline")

    if any(k in lower for k in ["explain", "in simple terms", "for a patient", "lay terms", "non technical"]):
        route.append("patient_educator")

    # Safe default: guidelines + patient education
    if not route:
        route.extend(["guideline", "patient_educator"])

    return {"route": route}


def literature_agent(state: ClinicalQAState) -> Dict:
    """
    Literature agent:
    - Uses web_search (PubMed) to get real abstracts.
    - Summarizes evidence in neutral, non-prescriptive language.
    """
    query = state["question"]
    search_result = web_search.invoke({"query": query})

    prompt = f"""
You are a clinical literature assistant.
You are NOT a doctor and you do NOT provide medical advice.
You only summarize research at a high level.

User question:
{query}

PubMed search results (titles/abstracts or error message):
{search_result}

Tasks:
1. Identify any relevant types of evidence (e.g., randomized trials, observational studies,
   guidelines) based on the text.
2. Summarize general findings in neutral, non-prescriptive language
   (e.g., "Some studies suggest...", "Evidence has been mixed...", etc.).
3. Explicitly mention important limitations or uncertainty if appropriate.
4. Explicitly state that this is NOT medical advice and that clinical decisions
   must be made by a qualified health professional who knows the patient's context.

Never provide:
- Specific diagnoses
- Drug names with dosing
- Individual treatment plans
- Urgent care instructions
"""
    resp = llm.invoke(prompt)

    return {
        "partial_answers": [{
            "agent": "literature",
            "content": resp.content.strip()
        }]
    }


def guideline_agent(state: ClinicalQAState) -> Dict:
    """
    Guideline agent:
    - Uses vector_search to query local clinical guideline texts.
    - Explains guidelines in general, non-patient-specific terms.
    """
    query = state["question"]
    doc_snippets = vector_search.invoke({"query": query})

    prompt = f"""
You are a clinical guideline explainer.
You are NOT providing medical advice; you only summarize documents.

User question:
{query}

Retrieved guideline snippets (may be real excerpts or an error/placeholder message):
{doc_snippets}

Tasks:
1. Explain, at a high level, what typical guidelines might say on this topic
   based on the snippets provided.
2. Use cautious language (e.g., "Guidelines often recommend...", "In many settings...").
3. Do NOT give specific treatment plans or dosing.
4. Highlight that real clinical decisions depend on the patient's full context,
   local policies, and must be made by a qualified clinician.
5. Explicitly state that this is NOT medical advice.

Never:
- Tell the user what they personally should do.
- Provide emergency instructions.
- Give concrete prescriptions.
"""
    resp = llm.invoke(prompt)

    return {
        "partial_answers": [{
            "agent": "guideline",
            "content": resp.content.strip()
        }]
    }


def patient_educator_agent(state: ClinicalQAState) -> Dict:
    """
    Patient education agent:
    - Explains concepts in simple language.
    - Always encourages talking to a healthcare professional.
    """
    query = state["question"]

    prompt = f"""
You are a patient education assistant.

IMPORTANT SAFETY RULES:
- You are NOT a doctor.
- You must NOT provide medical advice, diagnosis, or treatment recommendations.
- You must encourage the user to talk to a healthcare professional.

User question:
{query}

Tasks:
1. If the question mentions a health topic or condition, briefly explain it in simple,
   non-technical terms.
2. Mention common general themes (e.g., the importance of follow-up, monitoring,
   lifestyle in very broad terms) without giving personalized advice.
3. Suggest neutral example questions the user could ask their clinician.
4. Clearly state: "This is general information only and not medical advice."

Never:
- Tell the user what medication they should take.
- Suggest specific tests, procedures, or dosages.
- Tell the user to ignore or delay professional care.
"""
    resp = llm.invoke(prompt)

    return {
        "partial_answers": [{
            "agent": "patient_educator",
            "content": resp.content.strip()
        }]
    }


def synthesizer_agent(state: ClinicalQAState) -> Dict:
    """
    Synthesizer:
    - Combines partial answers from all contributing agents.
    - Enforces strong disclaimers.
    """
    question = state["question"]
    parts = state["partial_answers"]

    prompt = f"""
You are a senior clinical knowledge assistant orchestrating multiple agents.

User question:
{question}

You received the following contributions from specialist agents:
{parts}

Tasks:
1. Synthesize these into a single, coherent summary.
2. Briefly mention which perspectives were used
   (e.g., literature, guidelines, patient education).
3. Keep the tone cautious and non-prescriptive.
4. VERY IMPORTANT: clearly state multiple times in the answer that:
   - This is NOT medical advice.
   - It is NOT a diagnosis.
   - The user MUST consult a healthcare professional for any decisions.
5. If the question appears urgent (e.g., severe symptoms, chest pain, shortness of breath),
   do NOT give advice. Instead, say that they should seek immediate medical care.

You must not:
- Provide treatment plans or dosing.
- Make diagnostic conclusions.
- Downplay the need to see a clinician.
"""
    resp = llm.invoke(prompt)

    return {"final_answer": resp.content.strip()}


# =========================================================
# ROUTING (FAN-OUT) FOR MULTI-AGENT WORKFLOW
# =========================================================

def route_from_triage(state: ClinicalQAState):
    """
    Convert triage_agent's route list into Send(...) objects
    so multiple agents can run in parallel within the graph.
    """
    sends: List[Send] = []
    for r in state["route"]:
        if r == "literature":
            sends.append(Send("literature_agent", state))
        elif r == "guideline":
            sends.append(Send("guideline_agent", state))
        elif r == "patient_educator":
            sends.append(Send("patient_educator_agent", state))
    return sends


# =========================================================
# GRAPH CONSTRUCTION
# =========================================================

def build_graph():
    builder = StateGraph(ClinicalQAState)

    # Add nodes
    builder.add_node("triage_agent", triage_agent)
    builder.add_node("literature_agent", literature_agent)
    builder.add_node("guideline_agent", guideline_agent)
    builder.add_node("patient_educator_agent", patient_educator_agent)
    builder.add_node("synthesizer_agent", synthesizer_agent)

    # Entry
    builder.add_edge(START, "triage_agent")

    # Multi-agent fan-out from triage_agent using Send API
    builder.add_conditional_edges("triage_agent", route_from_triage)

    # All specialist agents converge to synthesizer
    builder.add_edge("literature_agent", "synthesizer_agent")
    builder.add_edge("guideline_agent", "synthesizer_agent")
    builder.add_edge("patient_educator_agent", "synthesizer_agent")

    # Exit
    builder.add_edge("synthesizer_agent", END)

    return builder.compile()


# =========================================================
# CLI
# =========================================================

def ask_question(graph, question: str) -> str:
    initial_state: ClinicalQAState = {
        "question": question,
        "route": [],
        "partial_answers": [],
        "final_answer": "",
    }

    result = graph.invoke(initial_state)
    return result["final_answer"]


def main():
    global GUIDELINE_RETRIEVER

    # Build guideline retriever once
    GUIDELINE_RETRIEVER = build_guideline_retriever("guidelines")

    print("=== Clinician Knowledge Assistant (Multi-Agent, LangGraph, Free LLM) ===")
    print("Educational use only. NOT medical advice or diagnosis.")
    print("Always consult a qualified healthcare professional.\n")
    print("Type your question and press Enter.")
    print("Type 'exit' or 'quit' to leave.\n")

    graph = build_graph()

    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        answer = ask_question(graph, q)
        print("\n--- Assistant Response ---")
        print(answer)
        print("--------------------------\n")


if __name__ == "__main__":
    main()
