import html
import re
import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import discoveryengine_v1alpha as discoveryengine
from google.api_core.client_options import ClientOptions

# --- Configuration ---
PROJECT_ID = "agents-demo-495412"
LOCATION = "global"
DATA_STORE_ID = "schwab-gcs-ingestion-data-store"
REGION = "us-central1"

vertexai.init(project=PROJECT_ID, location=REGION)
model = GenerativeModel("gemini-2.5-flash")

def clean_html(raw_text: str) -> str:
    """Removes HTML tags for a clean prompt payload."""
    if not raw_text:
        return ""
    text = html.unescape(raw_text)
    text = re.sub(r'<[^>]+>', '', text)
    return " ".join(text.split())

# --- Discovery Engine Tool ---
def fetch_filing_context(query: str) -> str:
    client_options = ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
    search_client = discoveryengine.SearchServiceClient(client_options=client_options)
    serving_config = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/dataStores/{DATA_STORE_ID}/servingConfigs/default_search"
    
    # THE FIX: Removed extractive_content_spec because your DataStore uses a Chunking Config.
    # We compensate by increasing page_size to 10 and max_snippet_count to 5 to cast a wider net.
    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=10, 
        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                max_snippet_count=5, return_snippet=True
            )
        )
    )
    
    response = search_client.search(request=request)
    extracted_data = []
    
    for i, result in enumerate(response.results, 1):
        doc = result.document
        derived = doc.derived_struct_data
        
        doc_title = derived.get("title", f"Document_ID_{doc.id[:6]}") if derived else "Unknown_Source"
        
        chunks = []
        if derived and "snippets" in derived and derived["snippets"]:
            for snip in derived["snippets"]:
                chunks.append(clean_html(snip.get("snippet", "")))
                
        if chunks:
            combined_text = " ".join(chunks)
            extracted_data.append(f"[Source {i}: {doc_title}]\nContent: {combined_text}")
            
    if not extracted_data:
        return "No relevant context found."
        
    return "\n\n".join(extracted_data)

# --- Streamlit UI ---
st.title("📊 Financial RAG: Schwab Filings")
st.markdown("Query IntelliStore V3. The AI will cite the specific SEC filings or reports used for its answers.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about Schwab's financials, risk factors, or net revenues across multiple years..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving from Discovery Engine & Synthesizing..."):
            
            context = fetch_filing_context(prompt)
            
            augmented_prompt = f"""
            You are a senior financial analyst. Answer the user's query thoroughly based STRICTLY on the context below. 
            
            CRITICAL CITATION RULES:
            - Every time you state a fact, number, trend, or claim, you MUST append an inline citation using the exact Source tag provided in the context.
            - Format your citations like this: "Net revenue for 2022 was $20,762 million [Source 1: SEC_Form10k_2022]."
            - Use bullet points where appropriate to make the financial data easy to read.
            - If the context does not contain enough data to fully answer the query, state exactly what is missing.
            
            --- CONTEXT ---
            {context}
            
            --- USER QUERY ---
            {prompt}
            """
            
            response = model.generate_content(augmented_prompt)
            
            st.markdown(response.text)
            
            with st.expander("🔍 View Grounding Context (Search Results)"):
                st.text(context)
            
    st.session_state.messages.append({"role": "assistant", "content": response.text})
