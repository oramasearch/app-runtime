# app-runtime

The Python base runtime that runs lake Apps: it loads an app's code from a lake repository at a pinned revision and serves it (FastAPI, Streamlit or static), with the orama_app helper library for data apps. Epic: oramasearch/lake#297.

Private. Its image is published **private** as `oramasearch/app-runtime` on Docker Hub.
