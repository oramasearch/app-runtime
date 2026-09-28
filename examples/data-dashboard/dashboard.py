"""A small dashboard over a dataset in the bound workspace."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from orama_app import current_user, zetta


def main() -> None:
    st.title("Workspace data")
    user = current_user()
    if user:
        st.caption(f"Signed in as {user.get('name') or user.get('email') or user.get('id')}")
    with zetta() as workspace:
        datasets = workspace.datasets(intent="show the workspace data catalog")
        if not datasets:
            st.info("This workspace has no datasets yet.")
            return
        summary = pd.DataFrame(datasets)
        visible = [column for column in ("database", "name", "rows", "size_bytes") if column in summary]
        st.dataframe(summary[visible], use_container_width=True)
        choices = {
            f"{dataset['database']}.{dataset['name']}": dataset
            for dataset in datasets
        }
        selected = st.selectbox("Preview a dataset", list(choices))
        result = workspace.sql(
            preview_statement(choices[selected]),
            intent="preview the selected dataset",
        )
        st.dataframe(result.get("rows", []), use_container_width=True)


def preview_statement(dataset: dict[str, Any]) -> str:
    database = quote_identifier(str(dataset["database"]))
    name = quote_identifier(str(dataset["name"]))
    return f"SELECT * FROM {database}.{name} LIMIT 100"


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


if __name__ == "__main__":
    main()

