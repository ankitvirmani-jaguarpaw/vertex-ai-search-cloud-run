echo "web: streamlit run app.py --server.port=\$PORT --server.address=0.0.0.0" > Procfile


gcloud run deploy intellistore-chat-ui \
    --source . \
    --region us-central1 \
    --allow-unauthenticated
