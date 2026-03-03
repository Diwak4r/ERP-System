## 2025-03-03 - [N+1 Query Optimization in FormSets and Admin]
**Learning:** In Django FormSets, expensive validation lookups (like TargetRule) that depend on form data can trigger N+1 queries. These can be optimized by pre-fetching the necessary data into a dictionary in the FormSet's `__init__` and passing it to individual forms via `get_form_kwargs`. Additionally, Django Admin list views often suffer from N+1 queries on ForeignKey fields, which can be resolved using `list_select_related`.

**Learning:** Tool output truncation (e.g., in `run_in_bash_session` or `read_file`) can obscure critical code sections. Using targeted `sed` commands or file splitting is necessary for complete verification of large files.

**Action:** Always inspect FormSet validation logic for hidden N+1 queries. Proactively use `list_select_related` in `ModelAdmin` for all ForeignKey fields in `list_display`. Use `sed` with specific line ranges to read large files reliably.
